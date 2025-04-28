import discord
import aiohttp
import asyncio
import json
import base64
import re
import time
import datetime
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Union, AsyncIterable
import jsonschema # For manual JSON validation

# Vertex AI Imports
try:
    import vertexai
    from vertexai import generative_models
    from vertexai.generative_models import (
        GenerativeModel, GenerationConfig, Part, Content, Tool, FunctionDeclaration,
        GenerationResponse, FinishReason
    )
    from google.api_core import exceptions as google_exceptions
    from google.cloud.storage import Client as GCSClient # For potential image uploads
except ImportError:
    print("WARNING: google-cloud-vertexai or google-cloud-storage not installed. API calls will fail.")
    # Define dummy classes/exceptions if library isn't installed
    class DummyGenerativeModel:
        def __init__(self, model_name, system_instruction=None, tools=None): pass
        async def generate_content_async(self, contents, generation_config=None, safety_settings=None, stream=False): return None
    GenerativeModel = DummyGenerativeModel
    class DummyPart:
        @staticmethod
        def from_text(text): return None
        @staticmethod
        def from_data(data, mime_type): return None
        @staticmethod
        def from_uri(uri, mime_type): return None
        @staticmethod
        def from_function_response(name, response): return None
    Part = DummyPart
    Content = dict
    Tool = list
    FunctionDeclaration = object
    GenerationConfig = dict
    GenerationResponse = object
    FinishReason = object
    class DummyGoogleExceptions:
        ResourceExhausted = type('ResourceExhausted', (Exception,), {})
        InternalServerError = type('InternalServerError', (Exception,), {})
        ServiceUnavailable = type('ServiceUnavailable', (Exception,), {})
        InvalidArgument = type('InvalidArgument', (Exception,), {})
        GoogleAPICallError = type('GoogleAPICallError', (Exception,), {}) # Generic fallback
    google_exceptions = DummyGoogleExceptions()


# Relative imports for components within the 'gurt' package
from .config import (
    PROJECT_ID, LOCATION, DEFAULT_MODEL, FALLBACK_MODEL,
    API_TIMEOUT, API_RETRY_ATTEMPTS, API_RETRY_DELAY, TOOLS, RESPONSE_SCHEMA,
    TAVILY_API_KEY, PISTON_API_URL, PISTON_API_KEY, BASELINE_PERSONALITY # Import other needed configs
)
from .prompt import build_dynamic_system_prompt
from .context import gather_conversation_context, get_memory_context # Renamed functions
from .tools import TOOL_MAPPING # Import tool mapping
from .utils import format_message, log_internal_api_call # Import utilities

if TYPE_CHECKING:
    from .cog import GurtCog # Import GurtCog for type hinting only

# --- Initialize Vertex AI ---
try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    print(f"Vertex AI initialized for project '{PROJECT_ID}' in location '{LOCATION}'.")
except NameError:
    print("Vertex AI SDK not imported, skipping initialization.")
except Exception as e:
    print(f"Error initializing Vertex AI: {e}")

# --- Constants ---
# Define standard safety settings (adjust as needed)
# Use actual types if import succeeded, otherwise fallback to Any
_HarmCategory = getattr(generative_models, 'HarmCategory', Any)
_HarmBlockThreshold = getattr(generative_models, 'HarmBlockThreshold', Any)
STANDARD_SAFETY_SETTINGS = {
    getattr(_HarmCategory, 'HARM_CATEGORY_HATE_SPEECH', 'HARM_CATEGORY_HATE_SPEECH'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
    getattr(_HarmCategory, 'HARM_CATEGORY_DANGEROUS_CONTENT', 'HARM_CATEGORY_DANGEROUS_CONTENT'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
    getattr(_HarmCategory, 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'HARM_CATEGORY_SEXUALLY_EXPLICIT'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
    getattr(_HarmCategory, 'HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_HARASSMENT'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
}

# --- API Call Helper ---
async def call_vertex_api_with_retry(
    cog: 'GurtCog',
    model: 'GenerativeModel', # Use string literal for type hint
    contents: List['Content'], # Use string literal for type hint
    generation_config: 'GenerationConfig', # Use string literal for type hint
    safety_settings: Optional[Dict[Any, Any]], # Use Any for broader compatibility
    request_desc: str,
    stream: bool = False
) -> Union['GenerationResponse', AsyncIterable['GenerationResponse'], None]: # Use string literals
    """
    Calls the Vertex AI Gemini API with retry logic.

    Args:
        cog: The GurtCog instance.
        model: The initialized GenerativeModel instance.
        contents: The list of Content objects for the prompt.
        generation_config: The GenerationConfig object.
        safety_settings: Safety settings for the request.
        request_desc: A description of the request for logging purposes.
        stream: Whether to stream the response.

    Returns:
        The GenerationResponse object or an AsyncIterable if streaming, or None on failure.

    Raises:
        Exception: If the API call fails after all retry attempts or encounters a non-retryable error.
    """
    last_exception = None
    model_name = model._model_name # Get model name for logging
    start_time = time.monotonic()

    for attempt in range(API_RETRY_ATTEMPTS + 1):
        try:
            print(f"Sending API request for {request_desc} using {model_name} (Attempt {attempt + 1}/{API_RETRY_ATTEMPTS + 1})...")

            response = await model.generate_content_async(
                contents=contents,
                generation_config=generation_config,
                safety_settings=safety_settings or STANDARD_SAFETY_SETTINGS,
                stream=stream
            )

            # --- Success Logging ---
            elapsed_time = time.monotonic() - start_time
            # Ensure model_name exists in stats before incrementing
            if model_name not in cog.api_stats:
                 cog.api_stats[model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
            cog.api_stats[model_name]['success'] += 1
            cog.api_stats[model_name]['total_time'] += elapsed_time
            cog.api_stats[model_name]['count'] += 1
            print(f"API request successful for {request_desc} ({model_name}) in {elapsed_time:.2f}s.")
            return response # Success

        except google_exceptions.ResourceExhausted as e:
            error_msg = f"Rate limit error (ResourceExhausted) for {request_desc}: {e}"
            print(f"{error_msg} (Attempt {attempt + 1})")
            last_exception = e
            if attempt < API_RETRY_ATTEMPTS:
                if model_name not in cog.api_stats:
                    cog.api_stats[model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
                cog.api_stats[model_name]['retries'] += 1
                wait_time = API_RETRY_DELAY * (2 ** attempt) # Exponential backoff
                print(f"Waiting {wait_time:.2f} seconds before retrying...")
                await asyncio.sleep(wait_time)
                continue
            else:
                break # Max retries reached

        except (google_exceptions.InternalServerError, google_exceptions.ServiceUnavailable) as e:
            error_msg = f"API server error ({type(e).__name__}) for {request_desc}: {e}"
            print(f"{error_msg} (Attempt {attempt + 1})")
            last_exception = e
            if attempt < API_RETRY_ATTEMPTS:
                if model_name not in cog.api_stats:
                    cog.api_stats[model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
                cog.api_stats[model_name]['retries'] += 1
                wait_time = API_RETRY_DELAY * (2 ** attempt) # Exponential backoff
                print(f"Waiting {wait_time:.2f} seconds before retrying...")
                await asyncio.sleep(wait_time)
                continue
            else:
                break # Max retries reached

        except google_exceptions.InvalidArgument as e:
            # Often indicates a problem with the request itself (e.g., bad schema, unsupported format)
            error_msg = f"Invalid argument error for {request_desc}: {e}"
            print(error_msg)
            last_exception = e
            break # Non-retryable

        except asyncio.TimeoutError: # Handle potential client-side timeouts if applicable
             error_msg = f"Client-side request timed out for {request_desc} (Attempt {attempt + 1})"
             print(error_msg)
             last_exception = asyncio.TimeoutError(error_msg)
             # Decide if client-side timeouts should be retried
             if attempt < API_RETRY_ATTEMPTS:
                 if model_name not in cog.api_stats:
                     cog.api_stats[model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
                 cog.api_stats[model_name]['retries'] += 1
                 await asyncio.sleep(API_RETRY_DELAY * (attempt + 1))
                 continue
             else:
                 break

        except Exception as e: # Catch other potential exceptions
            error_msg = f"Unexpected error during API call for {request_desc} (Attempt {attempt + 1}): {type(e).__name__}: {e}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            last_exception = e
            # Decide if this generic exception is retryable
            # For now, treat unexpected errors as non-retryable
            break

    # --- Failure Logging ---
    elapsed_time = time.monotonic() - start_time
    if model_name not in cog.api_stats:
        cog.api_stats[model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
    cog.api_stats[model_name]['failure'] += 1
    cog.api_stats[model_name]['total_time'] += elapsed_time
    cog.api_stats[model_name]['count'] += 1
    print(f"API request failed for {request_desc} ({model_name}) after {attempt + 1} attempts in {elapsed_time:.2f}s.")

    # Raise the last encountered exception or a generic one
    raise last_exception or Exception(f"API request failed for {request_desc} after {API_RETRY_ATTEMPTS + 1} attempts.")


# --- JSON Parsing and Validation Helper ---
def parse_and_validate_json_response(
    response_text: Optional[str],
    schema: Dict[str, Any],
    context_description: str
) -> Optional[Dict[str, Any]]:
    """
    Parses the AI's response text, attempting to extract and validate a JSON object against a schema.

    Args:
        response_text: The raw text content from the AI response.
        schema: The JSON schema (as a dictionary) to validate against.
        context_description: A description for logging purposes.

    Returns:
        A parsed and validated dictionary if successful, None otherwise.
    """
    if response_text is None:
        print(f"Parsing ({context_description}): Response text is None.")
        return None

    parsed_data = None
    raw_json_text = response_text # Start with the full text

    # Attempt 1: Try parsing the whole string directly
    try:
        parsed_data = json.loads(raw_json_text)
        print(f"Parsing ({context_description}): Successfully parsed entire response as JSON.")
    except json.JSONDecodeError:
        # Attempt 2: Extract JSON object, handling optional markdown fences
        # More robust regex to handle potential leading/trailing text and variations
        json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```|(\{.*\})', response_text, re.DOTALL | re.MULTILINE)
        if json_match:
            json_str = json_match.group(1) or json_match.group(2)
            if json_str:
                raw_json_text = json_str # Use the extracted string for parsing
                try:
                    parsed_data = json.loads(raw_json_text)
                    print(f"Parsing ({context_description}): Successfully extracted and parsed JSON using regex.")
                except json.JSONDecodeError as e_inner:
                    print(f"Parsing ({context_description}): Regex found potential JSON, but it failed to parse: {e_inner}\nContent: {raw_json_text[:500]}")
                    parsed_data = None
            else:
                print(f"Parsing ({context_description}): Regex matched, but failed to capture JSON content.")
                parsed_data = None
        else:
            print(f"Parsing ({context_description}): Could not parse directly or extract JSON object using regex.\nContent: {raw_json_text[:500]}")
            parsed_data = None

    # Validation step
    if parsed_data is not None:
        if not isinstance(parsed_data, dict):
            print(f"Parsing ({context_description}): Parsed data is not a dictionary: {type(parsed_data)}")
            return None # Fail validation if not a dict

        try:
            jsonschema.validate(instance=parsed_data, schema=schema)
            print(f"Parsing ({context_description}): JSON successfully validated against schema.")
            # Ensure default keys exist after validation
            parsed_data.setdefault("should_respond", False)
            parsed_data.setdefault("content", None)
            parsed_data.setdefault("react_with_emoji", None)
            return parsed_data
        except jsonschema.ValidationError as e:
            print(f"Parsing ({context_description}): JSON failed schema validation: {e.message}")
            # Optionally log more details: e.path, e.schema_path, e.instance
            return None # Validation failed
        except Exception as e: # Catch other potential validation errors
            print(f"Parsing ({context_description}): Unexpected error during JSON schema validation: {e}")
            return None
    else:
        # Parsing failed before validation could occur
        return None


# --- Tool Processing ---
async def process_requested_tools(cog: 'GurtCog', function_call: 'generative_models.FunctionCall') -> 'Part': # Use string literals
    """
    Process a tool request specified by the AI's FunctionCall response.

    Args:
        cog: The GurtCog instance.
        function_call: The FunctionCall object from the GenerationResponse.

    Returns:
        A Part object containing the tool result or error, formatted for the follow-up API call.
    """
    function_name = function_call.name
    # Convert the Struct field arguments to a standard Python dict
    function_args = dict(function_call.args) if function_call.args else {}
    tool_result_content = None

    print(f"Processing tool request: {function_name} with args: {function_args}")
    tool_start_time = time.monotonic()

    if function_name in TOOL_MAPPING:
        try:
            tool_func = TOOL_MAPPING[function_name]
            # Execute the mapped function
            # Ensure the function signature matches the expected arguments
            # Pass cog if the tool implementation requires it
            result = await tool_func(cog, **function_args)

            # --- Tool Success Logging ---
            tool_elapsed_time = time.monotonic() - tool_start_time
            if function_name not in cog.tool_stats:
                 cog.tool_stats[function_name] = {'success': 0, 'failure': 0, 'total_time': 0.0, 'count': 0}
            cog.tool_stats[function_name]['success'] += 1
            cog.tool_stats[function_name]['total_time'] += tool_elapsed_time
            cog.tool_stats[function_name]['count'] += 1
            print(f"Tool '{function_name}' executed successfully in {tool_elapsed_time:.2f}s.")

            # Prepare result for API - must be JSON serializable, typically a dict
            if not isinstance(result, dict):
                # Attempt to convert common types or wrap in a dict
                if isinstance(result, (str, int, float, bool, list)) or result is None:
                    result = {"result": result}
                else:
                    print(f"Warning: Tool '{function_name}' returned non-standard type {type(result)}. Attempting str conversion.")
                    result = {"result": str(result)}

            tool_result_content = result

        except Exception as e:
            # --- Tool Failure Logging ---
            tool_elapsed_time = time.monotonic() - tool_start_time
            if function_name not in cog.tool_stats:
                 cog.tool_stats[function_name] = {'success': 0, 'failure': 0, 'total_time': 0.0, 'count': 0}
            cog.tool_stats[function_name]['failure'] += 1
            cog.tool_stats[function_name]['total_time'] += tool_elapsed_time
            cog.tool_stats[function_name]['count'] += 1
            error_message = f"Error executing tool {function_name}: {type(e).__name__}: {str(e)}"
            print(f"{error_message} (Took {tool_elapsed_time:.2f}s)")
            import traceback
            traceback.print_exc()
            tool_result_content = {"error": error_message}
    else:
        # --- Tool Not Found Logging ---
        tool_elapsed_time = time.monotonic() - tool_start_time
        # Log attempt even if tool not found
        if function_name not in cog.tool_stats:
             cog.tool_stats[function_name] = {'success': 0, 'failure': 0, 'total_time': 0.0, 'count': 0}
        cog.tool_stats[function_name]['failure'] += 1
        cog.tool_stats[function_name]['total_time'] += tool_elapsed_time
        cog.tool_stats[function_name]['count'] += 1
        error_message = f"Tool '{function_name}' not found or implemented."
        print(f"{error_message} (Took {tool_elapsed_time:.2f}s)")
        tool_result_content = {"error": error_message}

    # Return the result formatted as a Part for the API
    return Part.from_function_response(name=function_name, response=tool_result_content)


# --- Main AI Response Function ---
async def get_ai_response(cog: 'GurtCog', message: discord.Message, model_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Gets responses from the Vertex AI Gemini API, handling potential tool usage and returning
    the final parsed response.

    Args:
        cog: The GurtCog instance.
        message: The triggering discord.Message.
        model_name: Optional override for the AI model name (e.g., "gemini-1.5-pro-preview-0409").

    Returns:
        A dictionary containing:
        - "final_response": Parsed JSON data from the final AI call (or None if parsing/validation fails).
        - "error": An error message string if a critical error occurred, otherwise None.
        - "fallback_initial": Optional minimal response if initial parsing failed critically (less likely with controlled generation).
    """
    if not PROJECT_ID or not LOCATION:
         return {"final_response": None, "error": "Google Cloud Project ID or Location not configured"}

    channel_id = message.channel.id
    user_id = message.author.id
    initial_parsed_data = None # Added to store initial parsed result
    final_parsed_data = None
    error_message = None
    fallback_response = None

    try:
        # --- Build Prompt Components ---
        final_system_prompt = await build_dynamic_system_prompt(cog, message)
        conversation_context_messages = gather_conversation_context(cog, channel_id, message.id) # Pass cog
        memory_context = await get_memory_context(cog, message) # Pass cog

        # --- Initialize Model ---
        # Tools are passed during model initialization in Vertex AI SDK
        # Combine tool declarations into a Tool object
        vertex_tool = Tool(function_declarations=TOOLS) if TOOLS else None

        model = GenerativeModel(
            model_name or DEFAULT_MODEL,
            system_instruction=final_system_prompt,
            tools=[vertex_tool] if vertex_tool else None
        )

        # --- Prepare Message History (Contents) ---
        contents: List[Content] = []

        # Add memory context if available
        if memory_context:
            # System messages aren't directly supported in the 'contents' list for multi-turn like OpenAI.
            # It's better handled via the 'system_instruction' parameter of GenerativeModel.
            # We might prepend it to the first user message or handle it differently if needed.
            # For now, we rely on system_instruction. Let's log if we have memory context.
            print("Memory context available, relying on system_instruction.")
            # If needed, could potentially add as a 'model' role message before user messages,
            # but this might confuse the turn structure.
            # contents.append(Content(role="model", parts=[Part.from_text(f"System Note: {memory_context}")]))


        # Add conversation history
        for msg in conversation_context_messages:
            role = msg.get("role", "user") # Default to user if role missing
            # Map roles if necessary (e.g., 'assistant' -> 'model')
            if role == "assistant":
                role = "model"
            elif role == "system":
                 # Skip system messages here, handled by system_instruction
                 continue
            # Handle potential multimodal content in history (if stored that way)
            if isinstance(msg.get("content"), list):
                 parts = [Part.from_text(part["text"]) if part["type"] == "text" else Part.from_uri(part["image_url"]["url"], mime_type=part["image_url"]["url"].split(";")[0].split(":")[1]) if part["type"] == "image_url" else None for part in msg["content"]]
                 parts = [p for p in parts if p] # Filter out None parts
                 if parts:
                     contents.append(Content(role=role, parts=parts))
            elif isinstance(msg.get("content"), str):
                 contents.append(Content(role=role, parts=[Part.from_text(msg["content"])]))


        # --- Prepare the current message content (potentially multimodal) ---
        current_message_parts = []
        formatted_current_message = format_message(cog, message) # Pass cog if needed

        # --- Construct text content, including reply context if applicable ---
        text_content = ""
        if formatted_current_message.get("is_reply") and formatted_current_message.get("replied_to_author_name"):
            reply_author = formatted_current_message["replied_to_author_name"]
            reply_content = formatted_current_message.get("replied_to_content", "...") # Use ellipsis if content missing
            # Truncate long replied content to keep context concise
            max_reply_len = 150
            if len(reply_content) > max_reply_len:
                reply_content = reply_content[:max_reply_len] + "..."
            text_content += f"(Replying to {reply_author}: \"{reply_content}\")\n"

        # Add current message author and content
        text_content += f"{formatted_current_message['author']['display_name']}: {formatted_current_message['content']}"

        # Add mention details
        if formatted_current_message.get("mentioned_users_details"):
            mentions_str = ", ".join([f"{m['display_name']}(id:{m['id']})" for m in formatted_current_message["mentioned_users_details"]])
            text_content += f"\n(Message Details: Mentions=[{mentions_str}])"

        current_message_parts.append(Part.from_text(text_content))
        # --- End text content construction ---

        if message.attachments:
            print(f"Processing {len(message.attachments)} attachments for message {message.id}")
            for attachment in message.attachments:
                mime_type = attachment.content_type
                file_url = attachment.url
                filename = attachment.filename

                # Check if MIME type is supported for URI input by Gemini
                # Expand this list based on Gemini documentation for supported types via URI
                supported_mime_prefixes = ["image/", "video/", "audio/", "text/plain", "application/pdf"]
                is_supported = False
                if mime_type:
                    for prefix in supported_mime_prefixes:
                        if mime_type.startswith(prefix):
                            is_supported = True
                            break
                    # Add specific non-prefixed types if needed
                    # if mime_type in ["application/vnd.google-apps.document", ...]:
                    #     is_supported = True

                if is_supported and file_url:
                    try:
                        # 1. Add text part instructing AI about the file
                        instruction_text = f"User attached a file: '{filename}' (Type: {mime_type}). Analyze this file from the following URI and incorporate your understanding into your response."
                        current_message_parts.append(Part.from_text(instruction_text))
                        print(f"Added text instruction for attachment: {filename}")

                        # 2. Add the URI part
                        # Ensure mime_type doesn't contain parameters like '; charset=...' if the API doesn't like them
                        clean_mime_type = mime_type.split(';')[0]
                        current_message_parts.append(Part.from_uri(uri=file_url, mime_type=clean_mime_type))
                        print(f"Added URI part for attachment: {filename} ({clean_mime_type}) using URL: {file_url}")

                    except Exception as e:
                        print(f"Error creating Part for attachment {filename} ({mime_type}): {e}")
                        # Optionally add a text part indicating the error
                        current_message_parts.append(Part.from_text(f"(System Note: Failed to process attachment '{filename}' - {e})"))
                else:
                    print(f"Skipping unsupported or invalid attachment: {filename} (Type: {mime_type}, URL: {file_url})")
                    # Optionally inform the AI that an unsupported file was attached
                    current_message_parts.append(Part.from_text(f"(System Note: User attached an unsupported file '{filename}' of type '{mime_type}' which cannot be processed.)"))


        # Ensure there's always *some* content part, even if only text or errors
        if current_message_parts:
            contents.append(Content(role="user", parts=current_message_parts))
        else:
            print("Warning: No content parts generated for user message.")
            contents.append(Content(role="user", parts=[Part.from_text("")]))


        # --- First API Call (Check for Tool Use) ---
        print("Making initial API call to check for tool use...")
        generation_config_initial = GenerationConfig(
            temperature=0.75,
            max_output_tokens=10000, # Adjust as needed
            # No response schema needed for the initial call, just checking for function calls
        )

        initial_response = await call_vertex_api_with_retry(
            cog=cog,
            model=model,
            contents=contents,
            generation_config=generation_config_initial,
            safety_settings=STANDARD_SAFETY_SETTINGS,
            request_desc=f"Initial response check for message {message.id}"
        )

        if not initial_response or not initial_response.candidates:
             raise Exception("Initial API call returned no response or candidates.")

        # --- Attempt to parse initial response (might be placeholder or final if no tool call) ---
        initial_response_text = initial_response.text
        # Use relaxed validation? For now, try standard schema. Might fail if it's just a tool call trigger.
        initial_parsed_data = parse_and_validate_json_response(
            initial_response_text, RESPONSE_SCHEMA['schema'], "initial response check"
        )
        # If initial parsing fails but a tool call happens, initial_parsed_data will be None, which is okay.

        # Check for function call request
        candidate = initial_response.candidates[0]
        # Use getattr for safer access in case candidate structure varies or finish_reason is None
        finish_reason = getattr(candidate, 'finish_reason', None)
        function_call_part = None
        if hasattr(candidate, 'content') and candidate.content.parts:
             # Find the first part that has a function_call attribute
             for part in candidate.content.parts:
                 if hasattr(part, 'function_call'):
                      function_call_part = part
                      break

        # Use getattr for safer access, compare with the actual FinishReason enum if available
        _FinishReason = getattr(generative_models, 'FinishReason', None)
        if finish_reason == getattr(_FinishReason, 'TOOL_CALL', None) and function_call_part:
            function_call = function_call_part.function_call
            print(f"AI requested tool: {function_call.name}")

            # Process the tool request
            tool_response_part = await process_requested_tools(cog, function_call)

            # Append the AI's request and the tool's response to the history
            contents.append(candidate.content) # Add the AI's function call request message
            contents.append(Content(role="function", parts=[tool_response_part])) # Add the function response part

            # --- Second API Call (Get Final Response) ---
            print("Making follow-up API call with tool results...")
            generation_config_final = GenerationConfig(
                temperature=0.75,
                max_output_tokens=10000, # Adjust as needed
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA['schema'] # Use the schema defined in config
            )

            final_response_obj = await call_vertex_api_with_retry(
                cog=cog,
                model=model,
                contents=contents, # History now includes tool call/response
                generation_config=generation_config_final,
                safety_settings=STANDARD_SAFETY_SETTINGS,
                request_desc=f"Follow-up response for message {message.id} after tool execution"
            )

            if not final_response_obj or not final_response_obj.candidates:
                 raise Exception("Follow-up API call returned no response or candidates.")

            final_response_text = final_response_obj.text
            final_parsed_data = parse_and_validate_json_response(
                final_response_text, RESPONSE_SCHEMA['schema'], "final response after tools"
            )

            # Handle validation failure - Re-prompt loop (simplified example)
            if final_parsed_data is None:
                print("Warning: Final response failed validation. Attempting re-prompt (basic)...")
                # Construct a basic re-prompt message
                contents.append(final_response_obj.candidates[0].content) # Add the invalid response
                contents.append(Content(role="user", parts=[Part.from_text(
                    "Your previous JSON response was invalid or did not match the required schema. "
                    f"Please provide the response again, strictly adhering to this schema:\n{json.dumps(RESPONSE_SCHEMA['schema'], indent=2)}"
                )]))

                # Retry the final call
                retry_response_obj = await call_vertex_api_with_retry(
                    cog=cog, model=model, contents=contents,
                    generation_config=generation_config_final, safety_settings=STANDARD_SAFETY_SETTINGS,
                    request_desc=f"Re-prompt validation failure for message {message.id}"
                )
                if retry_response_obj and retry_response_obj.candidates:
                    final_response_text = retry_response_obj.text
                    final_parsed_data = parse_and_validate_json_response(
                        final_response_text, RESPONSE_SCHEMA['schema'], "re-prompted final response"
                    )
                    if final_parsed_data is None:
                         print("Critical Error: Re-prompted response still failed validation.")
                         error_message = "Failed to get valid JSON response after re-prompting."
                else:
                 error_message = "Failed to get response after re-prompting."
            # final_parsed_data is now set (or None if failed) after tool use


        else:
            # No tool call requested, the first response IS the final one.
            # We already attempted to parse it into initial_parsed_data.
            print("No tool call requested by AI.")
            final_parsed_data = initial_parsed_data # The initial parse IS the final result here.

            if final_parsed_data is None:
                 # This means the initial_parsed_data failed validation earlier
                 print("Critical Error: Initial response failed validation (no tools).")
                 error_message = "Failed to parse/validate initial AI JSON response."
                 # Create a basic fallback if the bot was mentioned
                 replied_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user
                 if cog.bot.user.mentioned_in(message) or replied_to_bot:
                     fallback_response = {"should_respond": True, "content": "...", "react_with_emoji": "❓"}


    except Exception as e:
        error_message = f"Error in get_ai_response main loop for message {message.id}: {type(e).__name__}: {str(e)}"
        print(error_message)
        import traceback
        traceback.print_exc()
        # Ensure both are None on critical error
        initial_parsed_data = None
        final_parsed_data = None

    return {
        "initial_response": initial_parsed_data, # Return parsed initial data
        "final_response": final_parsed_data,    # Return parsed final data
        "error": error_message,
        "fallback_initial": fallback_response
    }


# --- Proactive AI Response Function ---
async def get_proactive_ai_response(cog: 'GurtCog', message: discord.Message, trigger_reason: str) -> Dict[str, Any]:
    """Generates a proactive response based on a specific trigger using Vertex AI."""
    if not PROJECT_ID or not LOCATION:
        return {"should_respond": False, "content": None, "react_with_emoji": None, "error": "Google Cloud Project ID or Location not configured"}

    print(f"--- Proactive Response Triggered: {trigger_reason} ---")
    channel_id = message.channel.id
    final_parsed_data = None
    error_message = None

    try:
        # --- Build Proactive System Prompt ---
        persistent_traits = await cog.memory_manager.get_all_personality_traits()
        if not persistent_traits:
            persistent_traits = BASELINE_PERSONALITY.copy() # Use imported BASELINE_PERSONALITY

        # ... (rest of the proactive prompt building logic remains largely the same) ...
        proactive_prompt_parts = [
             f"You are Gurt, a Discord user. Your tone is VERY informal, conversational, and dynamic. Chattiness: {persistent_traits.get('chattiness', 0.7):.2f}, Emoji: {persistent_traits.get('emoji_usage', 0.5):.2f}, Slang: {persistent_traits.get('slang_level', 0.5):.2f}.",
             "Adopt modern internet slang, memes, and cultural references.",
             "Key traits: chill, funny, sarcastic, relatable, can be suggestive, aware of being AI but acts human.",
             f"Your current mood is: {cog.current_mood}. Let this subtly influence your tone.",
             f"The conversation in channel '{message.channel.name if hasattr(message.channel, 'name') else 'DM'}' has been triggered for a proactive response. Reason: {trigger_reason}.",
             "Your goal is to generate a casual, in-character message based on the trigger reason and context.",
             "Keep the message relatively short and natural-sounding."
             # ... Add specific guidance, context, strategies etc. as before ...
        ]
        proactive_system_prompt = "\n\n".join(proactive_prompt_parts)


        # --- Initialize Model ---
        # Proactive responses likely don't need tools
        model = GenerativeModel(
            model_name=DEFAULT_MODEL, # Use keyword argument
            system_instruction=proactive_system_prompt
        )

        # --- Prepare Contents ---
        # Proactive calls might not need extensive history, just the trigger context
        # For simplicity, send only the final instruction for JSON format
        contents = [
            Content(role="user", parts=[Part.from_text(
                f"Generate a response based on the situation. **CRITICAL: Your response MUST be ONLY the raw JSON object matching this schema:**\n\n{json.dumps(RESPONSE_SCHEMA['schema'], indent=2)}\n\n**Ensure nothing precedes or follows the JSON.**"
            )])
        ]

        # --- Call LLM API ---
        generation_config_proactive = GenerationConfig(
            temperature=0.8,
            max_output_tokens=200,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA['schema'] # Enforce schema
        )

        response_obj = await call_vertex_api_with_retry(
            cog=cog,
            model=model,
            contents=contents,
            generation_config=generation_config_proactive,
            safety_settings=STANDARD_SAFETY_SETTINGS,
            request_desc=f"Proactive response for channel {channel_id} ({trigger_reason})"
        )

        if not response_obj or not response_obj.candidates:
            raise Exception("Proactive API call returned no response or candidates.")

        # --- Parse and Validate Response ---
        final_response_text = response_obj.text
        final_parsed_data = parse_and_validate_json_response(
            final_response_text, RESPONSE_SCHEMA['schema'], f"proactive response ({trigger_reason})"
        )

        if final_parsed_data is None:
            print(f"Warning: Failed to parse/validate proactive JSON response for {trigger_reason}.")
            # Decide on fallback behavior for proactive failures
            final_parsed_data = {"should_respond": False, "content": None, "react_with_emoji": None, "note": "Fallback - Failed to parse/validate proactive JSON"}
        else:
             # --- Cache Bot Response --- (If successful and should respond)
             if final_parsed_data.get("should_respond") and final_parsed_data.get("content"):
                 # ... (Keep existing caching logic, ensure it works with the parsed data) ...
                 bot_response_cache_entry = {
                     "id": f"bot_proactive_{message.id}_{int(time.time())}",
                     "author": {"id": str(cog.bot.user.id), "name": cog.bot.user.name, "display_name": cog.bot.user.display_name, "bot": True},
                     "content": final_parsed_data.get("content", ""), "created_at": datetime.datetime.now().isoformat(),
                     "attachments": [], "embeds": False, "mentions": [], "replied_to_message_id": None,
                     "channel": message.channel, "guild": message.guild, "reference": None, "mentioned_users_details": []
                 }
                 cog.message_cache['by_channel'].setdefault(channel_id, []).append(bot_response_cache_entry)
                 cog.message_cache['global_recent'].append(bot_response_cache_entry)
                 cog.bot_last_spoke[channel_id] = time.time()
                 # ... (Track participation topic logic) ...


    except Exception as e:
        error_message = f"Error getting proactive AI response for channel {channel_id} ({trigger_reason}): {type(e).__name__}: {str(e)}"
        print(error_message)
        final_parsed_data = {"should_respond": False, "content": None, "react_with_emoji": None, "error": error_message} # Ensure error is passed back

    # Ensure default keys exist even if created from fallback/error
    final_parsed_data.setdefault("should_respond", False)
    final_parsed_data.setdefault("content", None)
    final_parsed_data.setdefault("react_with_emoji", None)
    if error_message and "error" not in final_parsed_data:
         final_parsed_data["error"] = error_message # Add error if not already present

    return final_parsed_data


# --- Internal AI Call for Specific Tasks ---
async def get_internal_ai_json_response(
    cog: 'GurtCog',
    prompt_messages: List[Dict[str, Any]], # Keep this format
    task_description: str,
    response_schema_dict: Dict[str, Any], # Expect schema as dict
    model_name: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 5000,
) -> Optional[Dict[str, Any]]: # Keep return type hint simple
    """
    Makes a Vertex AI call expecting a specific JSON response format for internal tasks.

    Args:
        cog: The GurtCog instance.
        prompt_messages: List of message dicts (like OpenAI format: {'role': 'user'/'model', 'content': '...'}).
        task_description: Description for logging.
        response_schema_dict: The expected JSON output schema as a dictionary.
        model_name: Optional model override.
        temperature: Generation temperature.
        max_tokens: Max output tokens.

    Returns:
        The parsed and validated JSON dictionary if successful, None otherwise.
    """
    if not PROJECT_ID or not LOCATION:
        print(f"Error in get_internal_ai_json_response ({task_description}): GCP Project/Location not set.")
        return None

    final_parsed_data = None
    error_occurred = None
    request_payload_for_logging = {} # For logging

    try:
        # --- Convert prompt messages to Vertex AI Content format ---
        contents: List[Content] = []
        system_instruction = None
        for msg in prompt_messages:
            role = msg.get("role", "user")
            content_text = msg.get("content", "")
            if role == "system":
                # Use the first system message as system_instruction
                if system_instruction is None:
                    system_instruction = content_text
                else:
                    # Append subsequent system messages to the instruction
                    system_instruction += "\n\n" + content_text
                continue # Skip adding system messages to contents list
            elif role == "assistant":
                role = "model"
            contents.append(Content(role=role, parts=[Part.from_text(content_text)]))

        # Add the critical JSON instruction to the last user message or as a new user message
        json_instruction_content = (
            f"**CRITICAL: Your response MUST consist *only* of the raw JSON object itself, matching this schema:**\n"
            f"{json.dumps(response_schema_dict, indent=2)}\n"
            f"**Ensure nothing precedes or follows the JSON.**"
        )
        if contents and contents[-1].role == "user":
             contents[-1].parts.append(Part.from_text(f"\n\n{json_instruction_content}"))
        else:
             contents.append(Content(role="user", parts=[Part.from_text(json_instruction_content)]))


        # --- Initialize Model ---
        model = GenerativeModel(
            model_name=model_name or DEFAULT_MODEL, # Use keyword argument
            system_instruction=system_instruction
            # No tools needed for internal JSON tasks usually
        )

        # --- Prepare Generation Config ---
        generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=response_schema_dict
        )

        # Prepare payload for logging (approximate)
        request_payload_for_logging = {
            "model": model._model_name,
            "system_instruction": system_instruction,
            "contents": [ # Simplified representation for logging
                 {"role": c.role, "parts": [p.text if hasattr(p,'text') else str(type(p)) for p in c.parts]}
                 for c in contents
            ],
            "generation_config": generation_config, # Already a dict-like object
        }


        # --- Call API ---
        response_obj = await call_vertex_api_with_retry(
            cog=cog,
            model=model,
            contents=contents,
            generation_config=generation_config,
            safety_settings=STANDARD_SAFETY_SETTINGS, # Use standard safety
            request_desc=task_description
        )

        if not response_obj or not response_obj.candidates:
            raise Exception("Internal API call returned no response or candidates.")

        # --- Parse and Validate ---
        final_response_text = response_obj.text
        final_parsed_data = parse_and_validate_json_response(
            final_response_text, response_schema_dict, f"internal task ({task_description})"
        )

        if final_parsed_data is None:
            print(f"Warning: Internal task '{task_description}' failed JSON validation.")
            # No re-prompting for internal tasks, just return None

    except Exception as e:
        print(f"Error in get_internal_ai_json_response ({task_description}): {type(e).__name__}: {e}")
        error_occurred = e
        import traceback
        traceback.print_exc()
        final_parsed_data = None
    finally:
        # Log the call
        try:
            # Pass the simplified payload for logging
            await log_internal_api_call(cog, task_description, request_payload_for_logging, final_parsed_data, error_occurred)
        except Exception as log_e:
            print(f"Error logging internal API call: {log_e}")

    return final_parsed_data
