from collections import deque
import ssl
import certifi

from .config import CONTEXT_WINDOW_SIZE

def patch_ssl_certifi():
    original_create_default_context = ssl.create_default_context

    def custom_ssl_context(*args, **kwargs):
        # Only set cafile if it's not already passed
        kwargs.setdefault("cafile", certifi.where())
        return original_create_default_context(*args, **kwargs)

    ssl.create_default_context = custom_ssl_context

patch_ssl_certifi()

import discord
import aiohttp
import asyncio
import json
import base64
import re
import time
import datetime
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Union, AsyncIterable, Tuple # Import Tuple
import jsonschema # For manual JSON validation
from .tools import get_conversation_summary

# Google Generative AI Imports (using Vertex AI backend)
# try:
from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions # Keep for retry logic if applicable
# except ImportError:
#     print("WARNING: google-generativeai or google-api-core not installed. API calls will fail.")
#     # Define dummy classes/exceptions if library isn't installed
#     genai = None # Indicate genai module is missing
#     # types = None # REMOVE THIS LINE - Define dummy types object below

#     # Define dummy classes first
#     class DummyGenerationResponse:
#         def __init__(self):
#             self.candidates = []
#             self.text = None # Add basic text attribute for compatibility
#     class DummyFunctionCall:
#         def __init__(self):
#             self.name = None
#             self.args = None
#     class DummyPart:
#         @staticmethod
#         def from_text(text): return None
#         @staticmethod
#         def from_data(data, mime_type): return None
#         @staticmethod
#         def from_uri(uri, mime_type): return None
#         @staticmethod
#         def from_function_response(name, response): return None
#         @staticmethod
#         def from_function_call(function_call): return None # Add this
#     class DummyContent:
#         def __init__(self, role=None, parts=None):
#             self.role = role
#             self.parts = parts or []
#     class DummyTool:
#         def __init__(self, function_declarations=None): pass
#     class DummyFunctionDeclaration:
#         def __init__(self, name, description, parameters): pass
#     class Dummytypes.SafetySetting:
#         def __init__(self, category, threshold): pass
#     class Dummytypes.HarmCategory:
#         HARM_CATEGORY_HATE_SPEECH = "HARM_CATEGORY_HATE_SPEECH"
#         HARM_CATEGORY_DANGEROUS_CONTENT = "HARM_CATEGORY_DANGEROUS_CONTENT"
#         HARM_CATEGORY_SEXUALLY_EXPLICIT = "HARM_CATEGORY_SEXUALLY_EXPLICIT"
#         HARM_CATEGORY_HARASSMENT = "HARM_CATEGORY_HARASSMENT"
#     class DummyFinishReason:
#         STOP = "STOP"
#         MAX_TOKENS = "MAX_TOKENS"
#         SAFETY = "SAFETY"
#         RECITATION = "RECITATION"
#         OTHER = "OTHER"
#         FUNCTION_CALL = "FUNCTION_CALL" # Add this
#     class DummyToolConfig:
#          class FunctionCallingConfig:
#              class Mode:
#                  ANY = "ANY"
#                  NONE = "NONE"
#                  AUTO = "AUTO"
#          def __init__(self, function_calling_config=None): pass
#     class DummyGenerateContentResponse: # For non-streaming response type hint
#         def __init__(self):
#             self.candidates = []
#             self.text = None
#     # Define a dummy GenerateContentConfig class
#     class DummyGenerateContentConfig:
#         def __init__(self, temperature=None, top_p=None, max_output_tokens=None, response_mime_type=None, response_schema=None, stop_sequences=None, candidate_count=None):
#             self.temperature = temperature
#             self.top_p = top_p
#             self.max_output_tokens = max_output_tokens
#             self.response_mime_type = response_mime_type
#             self.response_schema = response_schema
#             self.stop_sequences = stop_sequences
#             self.candidate_count = candidate_count
#     # Define a dummy FunctionResponse class
#     class DummyFunctionResponse:
#          def __init__(self, name, response):
#              self.name = name
#              self.response = response

#     # Create a dummy 'types' object and assign dummy classes to its attributes
#     class DummyTypes:
#         def __init__(self):
#             self.GenerationResponse = DummyGenerationResponse
#             self.FunctionCall = DummyFunctionCall
#             self.types.Part = DummyPart
#             self.types.Content = DummyContent
#             self.Tool = DummyTool
#             self.FunctionDeclaration = DummyFunctionDeclaration
#             self.types.SafetySetting = Dummytypes.SafetySetting
#             self.types.HarmCategory = Dummytypes.HarmCategory
#             self.FinishReason = DummyFinishReason
#             self.ToolConfig = DummyToolConfig
#             self.GenerateContentResponse = DummyGenerateContentResponse
#             self.GenerateContentConfig = DummyGenerateContentConfig # Assign dummy config
#             self.FunctionResponse = DummyFunctionResponse # Assign dummy function response

#     types = DummyTypes() # Assign the dummy object to 'types'

#     # Assign dummy types to global scope for direct imports if needed
#     GenerationResponse = DummyGenerationResponse
#     FunctionCall = DummyFunctionCall
#     types.Part = DummyPart
#     types.Content = DummyContent
#     Tool = DummyTool
#     FunctionDeclaration = DummyFunctionDeclaration
#     types.SafetySetting = Dummytypes.SafetySetting
#     types.HarmCategory = Dummytypes.HarmCategory
#     FinishReason = DummyFinishReason
#     ToolConfig = DummyToolConfig
#     GenerateContentResponse = DummyGenerateContentResponse

#     class DummyGoogleExceptions:
#         ResourceExhausted = type('ResourceExhausted', (Exception,), {})
#         InternalServerError = type('InternalServerError', (Exception,), {})
#         ServiceUnavailable = type('ServiceUnavailable', (Exception,), {})
#         InvalidArgument = type('InvalidArgument', (Exception,), {})
#         GoogleAPICallError = type('GoogleAPICallError', (Exception,), {}) # Generic fallback
#     google_exceptions = DummyGoogleExceptions()


# Relative imports for components within the 'gurt' package
from .config import (
    PROJECT_ID, LOCATION, DEFAULT_MODEL, FALLBACK_MODEL, CUSTOM_TUNED_MODEL_ENDPOINT, # Import the new endpoint
    API_TIMEOUT, API_RETRY_ATTEMPTS, API_RETRY_DELAY, TOOLS, RESPONSE_SCHEMA,
    PROACTIVE_PLAN_SCHEMA, # Import the new schema
    TAVILY_API_KEY, PISTON_API_URL, PISTON_API_KEY, BASELINE_PERSONALITY # Import other needed configs
)
from .prompt import build_dynamic_system_prompt
from .context import gather_conversation_context, get_memory_context # Renamed functions
from .tools import TOOL_MAPPING # Import tool mapping
from .utils import format_message, log_internal_api_call # Import utilities
import copy # Needed for deep copying schemas

if TYPE_CHECKING:
    from .cog import GurtCog # Import GurtCog for type hinting only


# --- Schema Preprocessing Helper ---
def _preprocess_schema_for_vertex(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively preprocesses a JSON schema dictionary to replace list types
    (like ["string", "null"]) with the first non-null type, making it
    compatible with Vertex AI's GenerationConfig schema requirements.

    Args:
        schema: The JSON schema dictionary to preprocess.

    Returns:
        A new, preprocessed schema dictionary.
    """
    if not isinstance(schema, dict):
        return schema # Return non-dict elements as is

    processed_schema = copy.deepcopy(schema) # Work on a copy

    for key, value in processed_schema.items():
        if key == "type" and isinstance(value, list):
            # Find the first non-"null" type in the list
            first_valid_type = next((t for t in value if isinstance(t, str) and t.lower() != "null"), None)
            if first_valid_type:
                processed_schema[key] = first_valid_type
            else:
                # Fallback if only "null" or invalid types are present (shouldn't happen in valid schemas)
                processed_schema[key] = "object" # Or handle as error
                print(f"Warning: Schema preprocessing found list type '{value}' with no valid non-null string type. Falling back to 'object'.")
        elif isinstance(value, dict):
            processed_schema[key] = _preprocess_schema_for_vertex(value) # Recurse for nested objects
        elif isinstance(value, list):
            # Recurse for items within arrays (e.g., in 'properties' of array items)
            processed_schema[key] = [_preprocess_schema_for_vertex(item) if isinstance(item, dict) else item for item in value]
        # Handle 'properties' specifically
        elif key == "properties" and isinstance(value, dict):
             processed_schema[key] = {prop_key: _preprocess_schema_for_vertex(prop_value) for prop_key, prop_value in value.items()}
        # Handle 'items' specifically if it's a schema object
        elif key == "items" and isinstance(value, dict):
             processed_schema[key] = _preprocess_schema_for_vertex(value)


    return processed_schema
# --- Helper Function to Safely Extract Text ---
# Updated to handle google.generativeai.types.GenerateContentResponse
def _get_response_text(response: Optional[types.GenerateContentResponse]) -> Optional[str]:
    """
    Safely extracts the text content from the first text part of a GenerateContentResponse.
    Handles potential errors and lack of text parts gracefully.
    """
    if not response:
        print("[_get_response_text] Received None response object.")
        return None

    # Check if response has the 'text' attribute directly (common case for simple text responses)
    if hasattr(response, 'text') and response.text:
        print("[_get_response_text] Found text directly in response.text attribute.")
        return response.text

    # If no direct text, check candidates
    if not response.candidates:
        # Log the response object itself for debugging if it exists but has no candidates
        print(f"[_get_response_text] Response object has no candidates. Response: {response}")
        return None

    try:
        # Prioritize the first candidate
        candidate = response.candidates[0]

        # Check candidate.content and candidate.content.parts
        if not hasattr(candidate, 'content') or not candidate.content:
            print(f"[_get_response_text] Candidate 0 has no 'content'. Candidate: {candidate}")
            return None
        if not hasattr(candidate.content, 'parts') or not candidate.content.parts:
            print(f"[_get_response_text] Candidate 0 content has no 'parts' or parts list is empty. types.Content: {candidate.content}")
            return None

        # Log parts for debugging
        print(f"[_get_response_text] Inspecting parts in candidate 0: {candidate.content.parts}")

        # Iterate through parts to find the first text part
        for i, part in enumerate(candidate.content.parts):
            # Check if the part has a 'text' attribute and it's not empty/None
            if hasattr(part, 'text') and part.text is not None: # Check for None explicitly
                 # Check if text is non-empty string after stripping whitespace
                 if isinstance(part.text, str) and part.text.strip():
                     print(f"[_get_response_text] Found non-empty text in part {i}.")
                     return part.text
                 else:
                     print(f"[_get_response_text] types.Part {i} has 'text' attribute, but it's empty or not a string: {part.text!r}")
            # else:
            #     print(f"[_get_response_text] types.Part {i} does not have 'text' attribute or it's None.")


        # If no text part is found after checking all parts in the first candidate
        print(f"[_get_response_text] No usable text part found in candidate 0 after iterating through all parts.")
        return None

    except (AttributeError, IndexError, TypeError) as e:
        # Handle cases where structure is unexpected, list is empty, or types are wrong
        print(f"[_get_response_text] Error accessing response structure: {type(e).__name__}: {e}")
        # Log the problematic response object for deeper inspection
        print(f"Problematic response object: {response}")
        return None
    except Exception as e:
        # Catch other unexpected errors during access
        print(f"[_get_response_text] Unexpected error extracting text: {e}")
        print(f"Response object during error: {response}")
        return None


# --- Helper Function to Format Embeds for Prompt ---
def _format_embeds_for_prompt(embed_content: List[Dict[str, Any]]) -> Optional[str]:
    """Formats embed data into a string for the AI prompt."""
    if not embed_content:
        return None

    formatted_strings = []
    for i, embed in enumerate(embed_content):
        parts = [f"--- Embed {i+1} ---"]
        if embed.get("author") and embed["author"].get("name"):
            parts.append(f"Author: {embed['author']['name']}")
        if embed.get("title"):
            parts.append(f"Title: {embed['title']}")
        if embed.get("description"):
            # Limit description length
            desc = embed['description']
            max_desc_len = 200
            if len(desc) > max_desc_len:
                desc = desc[:max_desc_len] + "..."
            parts.append(f"Description: {desc}")
        if embed.get("fields"):
            field_parts = []
            for field in embed["fields"]:
                fname = field.get('name', 'Field')
                fvalue = field.get('value', '')
                # Limit field value length
                max_field_len = 100
                if len(fvalue) > max_field_len:
                    fvalue = fvalue[:max_field_len] + "..."
                field_parts.append(f"- {fname}: {fvalue}")
            if field_parts:
                parts.append("Fields:\n" + "\n".join(field_parts))
        if embed.get("footer") and embed["footer"].get("text"):
            parts.append(f"Footer: {embed['footer']['text']}")
        if embed.get("image_url"):
             parts.append(f"[Image Attached: {embed.get('image_url')}]") # Indicate image presence
        if embed.get("thumbnail_url"):
             parts.append(f"[Thumbnail Attached: {embed.get('thumbnail_url')}]") # Indicate thumbnail presence

        formatted_strings.append("\n".join(parts))

    return "\n".join(formatted_strings) if formatted_strings else None

# --- Initialize Google Generative AI Client for Vertex AI ---
# No explicit genai.configure(api_key=...) needed when using Vertex AI backend
try:
    genai_client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
    )

    print(f"Google GenAI Client initialized for Vertex AI project '{PROJECT_ID}' in location '{LOCATION}'.")
except NameError:
    genai_client = None
    print("Google GenAI SDK (genai) not imported, skipping client initialization.")
except Exception as e:
    genai_client = None
    print(f"Error initializing Google GenAI Client for Vertex AI: {e}")

# --- Constants ---
# Define standard safety settings using google.generativeai types
# Set all thresholds to OFF as requested
STANDARD_SAFETY_SETTINGS = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold="BLOCK_NONE"),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold="BLOCK_NONE"),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold="BLOCK_NONE"),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold="BLOCK_NONE"),
]

# --- API Call Helper ---
async def call_google_genai_api_with_retry(
    cog: 'GurtCog',
    model_name: str, # Pass model name string instead of model object
    contents: List[types.Content], # Use types.Content type from google.generativeai.types
    generation_config: types.GenerateContentConfig, # Combined config object
    request_desc: str,
    # Removed safety_settings, tools, tool_config as separate params
) -> Optional[types.GenerateContentResponse]: # Return type for non-streaming
    """
    Calls the Google Generative AI API (Vertex AI backend) with retry logic (non-streaming).

    Args:
        cog: The GurtCog instance.
        model_name: The name/path of the model to use (e.g., 'models/gemini-1.5-pro-preview-0409' or custom endpoint path).
        contents: The list of types.Content objects for the prompt.
        generation_config: The types.GenerateContentConfig object, which should now include temperature, top_p, max_output_tokens, safety_settings, tools, tool_config, response_mime_type, response_schema etc. as needed.
        request_desc: A description of the request for logging purposes.

    Returns:
        The GenerateContentResponse object if successful, or None on failure after retries.

    Raises:
        Exception: If the API call fails after all retry attempts or encounters a non-retryable error.
    """
    if not genai_client:
        raise Exception("Google GenAI Client (genai_client) is not initialized.")

    last_exception = None
    start_time = time.monotonic()

    # Get the model object from the client
    # Note: model_name should include the 'projects/.../locations/.../endpoints/...' path for custom models
    # or just 'models/model-name' for standard models.
    try:
        model = "projects/1079377687568/locations/us-central1/endpoints/6677946543460319232" # Use get_model to ensure it exists
        if not model:
             raise ValueError(f"Could not retrieve model: {model_name}")
    except Exception as model_e:
         print(f"Error retrieving model '{model_name}': {model_e}")
         raise # Re-raise the exception as this is a fundamental setup issue

    for attempt in range(API_RETRY_ATTEMPTS + 1):
        try:
            # Use the actual model name string passed to the function for logging
            print(f"Sending API request for {request_desc} using {model_name} (Attempt {attempt + 1}/{API_RETRY_ATTEMPTS + 1})...")

            # Use the non-streaming async call - config now contains all settings
            # The 'model' parameter here should be the actual model name string
            response = await genai_client.aio.models.generate_content(
                model=model_name, # Use the model_name string directly
                contents=contents,
                config=generation_config, # Pass the combined config object
                # stream=False is implicit for generate_content
            )

            # --- Check Finish Reason (Safety) ---
            # Access finish reason and safety ratings from the response object
            if response and response.candidates:
                candidate = response.candidates[0]
                finish_reason = getattr(candidate, 'finish_reason', None)
                safety_ratings = getattr(candidate, 'safety_ratings', [])

                if finish_reason == types.FinishReason.SAFETY:
                    safety_ratings_str = ", ".join([f"{rating.category.name}: {rating.probability.name}" for rating in safety_ratings]) if safety_ratings else "N/A"
                    # Optionally, raise a specific exception here if needed downstream
                    # raise SafetyBlockError(f"Blocked by safety filters. Ratings: {safety_ratings_str}")
                elif finish_reason not in [types.FinishReason.STOP, types.FinishReason.MAX_TOKENS, None]: # Allow None finish reason
                     # Log other unexpected finish reasons
                     finish_reason_name = types.FinishReason(finish_reason).name if isinstance(finish_reason, int) else str(finish_reason)
                     print(f"⚠️ UNEXPECTED FINISH REASON: API request for {request_desc} ({model_name}) finished with reason: {finish_reason_name}")

            # --- Success Logging (Proceed even if safety blocked, but log occurred) ---
            elapsed_time = time.monotonic() - start_time
            # Ensure model_name exists in stats before incrementing
            if model_name not in cog.api_stats:
                 cog.api_stats[model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
            cog.api_stats[model_name]['success'] += 1
            cog.api_stats[model_name]['total_time'] += elapsed_time
            cog.api_stats[model_name]['count'] += 1
            print(f"API request successful for {request_desc} ({model_name}) in {elapsed_time:.2f}s.")
            return response # Success

        # Adapt exception handling if google.generativeai raises different types
        # google.api_core.exceptions should still cover many common API errors
        except google_exceptions.ResourceExhausted as e:
            error_msg = f"Rate limit error (ResourceExhausted) for {request_desc} ({model_name}): {e}"
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
            error_msg = f"API server error ({type(e).__name__}) for {request_desc} ({model_name}): {e}"
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
            # Often indicates a problem with the request itself (e.g., bad schema, unsupported format, invalid model name)
            error_msg = f"Invalid argument error for {request_desc} ({model_name}): {e}"
            print(error_msg)
            last_exception = e
            break # Non-retryable

        except asyncio.TimeoutError: # Handle potential client-side timeouts if applicable
             error_msg = f"Client-side request timed out for {request_desc} ({model_name}) (Attempt {attempt + 1})"
             print(error_msg)
             last_exception = asyncio.TimeoutError(error_msg)
             # Decide if client-side timeouts should be retried
             if attempt < API_RETRY_ATTEMPTS:
                 if model_name not in cog.api_stats:
                     cog.api_stats[model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
                 cog.api_stats[model_name]['retries'] += 1
                 await asyncio.sleep(API_RETRY_DELAY * (attempt + 1)) # Linear backoff for timeout? Or keep exponential?
                 continue
             else:
                 break

        except Exception as e: # Catch other potential exceptions (e.g., from genai library itself)
            error_msg = f"Unexpected error during API call for {request_desc} ({model_name}) (Attempt {attempt + 1}): {type(e).__name__}: {e}"
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
# Updated to use google.generativeai types
async def process_requested_tools(cog: 'GurtCog', function_call: types.FunctionCall) -> types.Part:
    """
    Process a tool request specified by the AI's FunctionCall response.

    Args:
        cog: The GurtCog instance.
        function_call: The FunctionCall object from the GenerateContentResponse.

    Returns:
        A types.Part object containing the tool result or error, formatted for the follow-up API call.
    """
    function_name = function_call.name
    # function_call.args is already a dict-like object in google.generativeai
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

    # Return the result formatted as a types.Part for the API using the correct type
    return types.Part(function_response=types.FunctionResponse(name=function_name, response=tool_result_content))


# --- Helper to find function call in parts ---
# Updated to use google.generativeai types
def find_function_call_in_parts(parts: Optional[List[types.Part]]) -> Optional[types.FunctionCall]:
    """Finds the first valid FunctionCall object within a list of Parts."""
    if not parts:
        return None
    for part in parts:
        # Check if the part has a 'function_call' attribute and it's a valid FunctionCall object
        if hasattr(part, 'function_call') and isinstance(part.function_call, types.FunctionCall):
            # Basic validation: ensure name exists
            if part.function_call.name:
                 return part.function_call
            else:
                 print(f"Warning: Found types.Part with 'function_call', but its name is missing: {part.function_call}")
        # else:
        #     print(f"Debug: types.Part does not have valid function_call: {part}") # Optional debug log
    return None


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
    if not PROJECT_ID or not LOCATION or not genai_client: # Check genai_client too
         error_msg = "Google Cloud Project ID/Location not configured or GenAI Client failed to initialize."
         print(f"Error in get_ai_response: {error_msg}")
         return {"final_response": None, "error": error_msg}

    # Determine the model for the final response generation (custom tuned)
    # Use the override if provided, otherwise default to the custom tuned endpoint
    final_response_model = model_name or CUSTOM_TUNED_MODEL_ENDPOINT
    # Model for tool checking will be DEFAULT_MODEL
    tool_check_model = DEFAULT_MODEL
    print(f"Using model for final response: {final_response_model}")
    print(f"Using model for tool checks: {tool_check_model}")

    channel_id = message.channel.id
    user_id = message.author.id
    # initial_parsed_data is no longer needed with the loop structure
    final_parsed_data = None
    error_message = None
    fallback_response = None # Keep fallback for critical initial failures
    max_tool_calls = 5 # Maximum number of sequential tool calls allowed
    tool_calls_made = 0
    last_response_obj = None # Store the last response object from the loop

    try:
        # --- Build Prompt Components ---
        final_system_prompt = await build_dynamic_system_prompt(cog, message)
        conversation_context_messages = gather_conversation_context(cog, channel_id, message.id) # Pass cog
        memory_context = await get_memory_context(cog, message) # Pass cog

        # --- Prepare Message History (Contents) ---
        # Contents will be built progressively within the loop
        contents: List[types.Content] = []

        # Add memory context if available
        if memory_context:
            # System messages aren't directly supported in the 'contents' list for multi-turn like OpenAI.
            # It's better handled via the 'system_instruction' parameter of GenerativeModel.
            # We might prepend it to the first user message or handle it differently if needed.
            # For now, we rely on system_instruction. Let's log if we have memory context.
            print("Memory context available, relying on system_instruction.")
            # If needed, could potentially add as a 'model' role message before user messages,
            # but this might confuse the turn structure.
            # contents.append(types.Content(role="model", parts=[types.Part.from_text(f"System Note: {memory_context}")]))


        # Add conversation history
        # The current message is already included in conversation_context_messages
        for msg in conversation_context_messages:
            role = "assistant" if msg.get('author', {}).get('id') == str(cog.bot.user.id) else "user" # Use get for safety

            # Handle potential multimodal content in history (if stored that way)
            if isinstance(msg.get("content"), list):
                 parts = [types.Part(text=part["text"]) if part["type"] == "text" else types.Part(uri=part["image_url"]["url"], mime_type=part["image_url"]["url"].split(";")[0].split(":")[1]) if part["type"] == "image_url" else None for part in msg["content"]]
                 parts = [p for p in parts if p] # Filter out None parts
                 if parts:
                     contents.append(types.Content(role=role, parts=parts))
            # Combine text, embeds, and attachments for history messages
            elif isinstance(msg.get("content"), str) or msg.get("embed_content") or msg.get("attachment_descriptions"):
                 text_parts = []
                 # Add original text content if it exists and is not empty
                 if isinstance(msg.get("content"), str) and msg["content"].strip():
                     text_parts.append(msg["content"])
                 # Add formatted embed content if present
                 embed_str = _format_embeds_for_prompt(msg.get("embed_content", []))
                 if embed_str:
                     text_parts.append(f"\n[Embed Content]:\n{embed_str}")
                 # Add attachment descriptions if present
                 if msg.get("attachment_descriptions"):
                     # Ensure descriptions are strings before joining
                     attach_desc_list = [a['description'] for a in msg['attachment_descriptions'] if isinstance(a.get('description'), str)]
                     if attach_desc_list:
                         attach_desc_str = "\n".join(attach_desc_list)
                         text_parts.append(f"\n[Attachments]:\n{attach_desc_str}")

                 full_text = "\n".join(text_parts).strip()
                 if full_text: # Only add if there's some text content
                     # Use the new author_string here
                     author_string = msg.get("author_string", msg.get("author", {}).get("display_name", " "))
                     contents.append(types.Content(role=role, parts=[types.Part(text=f"{author_string}: {full_text}")]))


        # --- Prepare the current message content (potentially multimodal) ---
        # This section is no longer needed as the current message is included in conversation_context_messages
        # current_message_parts = []
        # formatted_current_message = format_message(cog, message) # Pass cog if needed

        # --- Construct text content, including reply context if applicable ---
        # This section is now handled within the conversation history loop
        # text_content = ""
        # if formatted_current_message.get("is_reply") and formatted_current_message.get("replied_to_author_name"):
        #     reply_author = formatted_current_message["replied_to_author_name"]
        #     reply_content = formatted_current_message.get("replied_to_content", "...") # Use ellipsis if content missing
        #     # Truncate long replied content to keep context concise
        #     max_reply_len = 150
        #     if len(reply_content) > max_reply_len:
        #         reply_content = reply_content[:max_reply_len] + "..."
        #     text_content += f"(Replying to {reply_author}: \"{reply_content}\")\n"

        # # Add current message author and content
        # # Use the new author_string here for the current message
        # current_author_string = formatted_current_message.get("author_string", formatted_current_message.get("author", {}).get("display_name", "Unknown User"))
        # text_content += f"{current_author_string}: {formatted_current_message['content']}" # Keep original content

        # # Add formatted embed content if present for the *current* message
        # current_embed_str = _format_embeds_for_prompt(formatted_current_message.get("embed_content", []))
        # if current_embed_str:
        #     text_content += f"\n[Embed Content]:\n{current_embed_str}"

        # # Add attachment descriptions for the *current* message
        # if formatted_current_message.get("attachment_descriptions"):
        #     # Ensure descriptions are strings before joining
        #     current_attach_desc_list = [a['description'] for a in formatted_current_message['attachment_descriptions'] if isinstance(a.get('description'), str)]
        #     if current_attach_desc_list:
        #         current_attach_desc_str = "\n".join(current_attach_desc_list)
        #         text_content += f"\n[Attachments]:\n{current_attach_desc_str}"

        # # Add mention details
        # if formatted_current_message.get("mentioned_users_details"): # This key might not exist, adjust if needed
        #     mentions_str = ", ".join([f"{m['display_name']}(id:{m['id']})" for m in formatted_current_message["mentioned_users_details"]])
        #     text_content += f"\n(Message Details: Mentions=[{mentions_str}])"

        # current_message_parts.append(types.Part(text=text_content))
        # --- End text content construction ---

        # The attachment processing for the current message is now handled within gather_conversation_context
        # if message.attachments:
        #     print(f"Processing {len(message.attachments)} attachments for message {message.id}")
        #     for attachment in message.attachments:
        #         mime_type = attachment.content_type
        #         file_url = attachment.url
        #         filename = attachment.filename

        #         # Check if MIME type is supported for URI input by Gemini
        #         supported_mime_prefixes = ["image/", "video/", "audio/", "text/plain", "application/pdf"]
        #         is_supported = False
        #         detected_mime_type = mime_type if mime_type else "application/octet-stream"
        #         for prefix in supported_mime_prefixes:
        #             if detected_mime_type.startswith(prefix):
        #                 is_supported = True
        #                 break

        #         # Always add a text instruction for every attachment
        #         instruction_text = f"User attached a file: '{filename}' (Type: {detected_mime_type}). Analyze this file from the following URI and incorporate your understanding into your response."
        #         current_message_parts.append(types.Part(text=instruction_text))
        #         print(f"Added text instruction for attachment: {filename}")

        #         if is_supported and file_url:
        #             try:
        #                 # Add the URI part with a cleaned/fallback MIME type using from_uri
        #                 clean_mime_type = detected_mime_type.split(';')[0] if detected_mime_type else "application/octet-stream"
        #                 current_message_parts.append(types.Part.from_uri(file_url, clean_mime_type))
        #                 print(f"Added URI part for attachment: {filename} ({clean_mime_type}) using URL: {file_url}")
        #             except Exception as e:
        #                 print(f"Error creating types.Part for attachment {filename} ({detected_mime_type}): {e}")
        #                 current_message_parts.append(types.Part(text=f"(System Note: Failed to process attachment '{filename}' - {e})"))
        #         else:
        #             print(f"Skipping unsupported or invalid attachment: {filename} (Type: {detected_mime_type}, URL: {file_url})")
        #             current_message_parts.append(types.Part(text=f"(System Note: User attached an unsupported file '{filename}' of type '{detected_mime_type}' which cannot be processed.)"))


        # Ensure there's always *some* content part, even if only text or errors
        # This section is also no longer needed as the current message is included in conversation_context_messages
        # if current_message_parts:
        #     contents.append(types.Content(role="user", parts=current_message_parts))
        # else:
        #     print("Warning: No content parts generated for user message.")
        #     contents.append(types.Content(role="user", parts=[types.Part(text="")])) # Ensure content list isn't empty

        # --- Prepare Tools ---
        # Preprocess tool parameter schemas before creating the Tool object
        preprocessed_declarations = []
        if TOOLS:
            for decl in TOOLS:
                # Create a new FunctionDeclaration with preprocessed parameters
                # Ensure decl.parameters is a dict before preprocessing
                preprocessed_params = _preprocess_schema_for_vertex(decl.parameters) if isinstance(decl.parameters, dict) else decl.parameters
                preprocessed_declarations.append(
                    types.FunctionDeclaration(
                        name=decl.name,
                        description=decl.description,
                        parameters=preprocessed_params # Use the preprocessed schema
                    )
                )
            print(f"Preprocessed {len(preprocessed_declarations)} tool declarations for Vertex AI compatibility.")
        else:
            print("No tools found in config (TOOLS list is empty or None).")

        # Create the Tool object using the preprocessed declarations
        vertex_tool = types.Tool(function_declarations=preprocessed_declarations) if preprocessed_declarations else None
        tools_list = [vertex_tool] if vertex_tool else None

        # --- Prepare Generation Config ---
        # Base generation config settings (will be augmented later)
        base_generation_config_dict = {
            "temperature": 1, # From user example
            "top_p": 0.95,      # From user example
            "max_output_tokens": 8192, # From user example
            "safety_settings": STANDARD_SAFETY_SETTINGS, # Include standard safety settings
            "system_instruction": final_system_prompt, # Pass system prompt via config
            # candidate_count=1 # Default is 1
            # stop_sequences=... # Add if needed
        }

        # --- Tool Execution Loop ---
        while tool_calls_made < max_tool_calls:
            print(f"Making API call (Loop Iteration {tool_calls_made + 1}/{max_tool_calls})...")

            # --- Log Request Payload ---
            # (Keep existing logging logic if desired)
            try:
                 request_payload_log = [{"role": c.role, "parts": [str(p) for p in c.parts]} for c in contents]
                 print(f"--- Raw API Request (Loop {tool_calls_made + 1}) ---\n{json.dumps(request_payload_log, indent=2)}\n------------------------------------")
            except Exception as log_e:
                 print(f"Error logging raw request/response: {log_e}")

            # --- Call API using the new helper ---
            # Build the config for this specific call (tool check)
            current_gen_config_dict = base_generation_config_dict.copy()
            if tools_list:
                current_gen_config_dict["tools"] = tools_list
                # Define tool_config here if needed, e.g., for ANY mode
                current_gen_config_dict["tool_config"] = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfigMode.ANY
                    )
                )
            # Omit response_mime_type and response_schema for tool checking

            current_gen_config = types.GenerateContentConfig(**current_gen_config_dict)

            current_response_obj = await call_google_genai_api_with_retry(
                cog=cog,
                model_name=tool_check_model, # Use DEFAULT_MODEL for tool checks
                contents=contents,
                generation_config=current_gen_config, # Pass the combined config
                request_desc=f"Tool Check {tool_calls_made + 1} for message {message.id}",
                # No separate safety, tools, tool_config args needed
            )
            last_response_obj = current_response_obj # Store the latest response

            # --- Log Raw Response ---
            # (Keep existing logging logic if desired)
            try:
                 print(f"--- Raw API Response (Loop {tool_calls_made + 1}) ---\n{current_response_obj}\n-----------------------------------")
            except Exception as log_e:
                 print(f"Error logging raw request/response: {log_e}")

            if not current_response_obj or not current_response_obj.candidates:
                error_message = f"API call in tool loop (Iteration {tool_calls_made + 1}) failed to return candidates."
                print(error_message)
                break # Exit loop on critical API failure

            candidate = current_response_obj.candidates[0]

            # --- Find ALL function calls using the updated helper ---
            # The response structure might differ slightly; check candidate.content.parts
            function_calls_found = []
            if candidate.content and candidate.content.parts:
                 function_calls_found = [part.function_call for part in candidate.content.parts if hasattr(part, 'function_call') and isinstance(part.function_call, types.FunctionCall)]

            if function_calls_found:
                # Check if the *only* call is no_operation
                if len(function_calls_found) == 1 and function_calls_found[0].name == "no_operation":
                    print("AI called only no_operation, signaling completion.")
                    # Append the model's response (which contains the function call part)
                    contents.append(candidate.content)
                    # Add the function response part using the updated process_requested_tools
                    no_op_response_part = await process_requested_tools(cog, function_calls_found[0])
                    contents.append(types.Content(role="function", parts=[no_op_response_part]))
                    last_response_obj = current_response_obj # Keep track of the response containing the no_op
                    break # Exit loop

                # Process multiple function calls if present (or a single non-no_op call)
                tool_calls_made += 1 # Increment once per model turn that requests tools
                print(f"AI requested {len(function_calls_found)} tool(s): {[fc.name for fc in function_calls_found]} (Turn {tool_calls_made}/{max_tool_calls})")

                # Append the model's response content (containing the function call parts)
                model_request_content = candidate.content
                contents.append(model_request_content)

                # Add model request turn to cache
                try:
                    # Simple text representation for cache
                    model_request_cache_entry = {
                        "id": f"bot_tool_req_{message.id}_{int(time.time())}_{tool_calls_made}",
                        "author": {"id": str(cog.bot.user.id), "name": cog.bot.user.name, "display_name": cog.bot.user.display_name, "bot": True},
                        "content": f"[System Note: Gurt requested tool(s): {', '.join([fc.name for fc in function_calls_found])}]",
                        "created_at": datetime.datetime.now().isoformat(),
                        "attachments": [], "embeds": False, "mentions": [], "replied_to_message_id": None,
                        "channel": message.channel, "guild": message.guild, "reference": None, "mentioned_users_details": [],
                        # Add tool call details for potential future use in context building
                        "tool_calls": [{"name": fc.name, "args": dict(fc.args) if fc.args else {}} for fc in function_calls_found]
                    }
                    cog.message_cache['by_channel'].setdefault(channel_id, deque(maxlen=CONTEXT_WINDOW_SIZE)).append(model_request_cache_entry)
                    cog.message_cache['global_recent'].append(model_request_cache_entry)
                    print(f"Cached model's tool request turn.")
                except Exception as cache_err:
                    print(f"Error caching model's tool request turn: {cache_err}")


                # --- Execute all requested tools and gather response parts ---
                function_response_parts = []
                function_results_for_cache = [] # Store results for caching
                for func_call in function_calls_found:
                    # Execute the tool using the updated helper
                    response_part = await process_requested_tools(cog, func_call)
                    function_response_parts.append(response_part)
                    # Extract result for caching (assuming response_part.function_response exists)
                    if hasattr(response_part, 'function_response') and response_part.function_response:
                        function_results_for_cache.append({
                            "name": response_part.function_response.name,
                            "response": response_part.function_response.response # This is already the dict result
                        })


                # Append a single function role turn containing ALL response parts to the API contents
                if function_response_parts:
                    function_response_content = types.Content(role="function", parts=function_response_parts)
                    contents.append(function_response_content)

                    # <<< ADDED INSTRUCTION >>>
                    # Add a specific instruction after the tool results are appended
                    instruction_text = "System Note: You have just received the result(s) of the tool(s) you requested. Generate your final response according to the required JSON schema. CRITICAL: DO NOT attempt to call any more tools (including 'no_operation') in this response. Focus *solely* on creating the JSON output."
                    instruction_part = types.Part(text=instruction_text)
                    # Using 'model' role seems appropriate for a system-like reminder integrated into the turn flow
                    instruction_content = types.Content(role="model", parts=[instruction_part])
                    contents.append(instruction_content)
                    print("Added explicit instruction for AI after tool results.")
                    # <<< END ADDED INSTRUCTION >>>

                    # Add function response turn to cache
                    try:
                        # Simple text representation for cache
                        # Join results for multiple calls if needed, truncate long outputs
                        result_summary_parts = []
                        for res in function_results_for_cache:
                            res_str = json.dumps(res.get("response", {}))
                            truncated_res = (res_str[:150] + '...') if len(res_str) > 153 else res_str
                            result_summary_parts.append(f"Tool: {res.get('name', 'N/A')}, Result: {truncated_res}")
                        result_summary = "; ".join(result_summary_parts)

                        function_response_cache_entry = {
                            "id": f"bot_tool_res_{message.id}_{int(time.time())}_{tool_calls_made}",
                            "author": {"id": "FUNCTION", "name": "Tool Execution", "display_name": "Tool Execution", "bot": True}, # Special author ID?
                            "content": f"[System Note: Tool Execution Result: {result_summary}]",
                            "created_at": datetime.datetime.now().isoformat(),
                            "attachments": [], "embeds": False, "mentions": [], "replied_to_message_id": None,
                            "channel": message.channel, "guild": message.guild, "reference": None, "mentioned_users_details": [],
                            # Store the full function results
                            "function_results": function_results_for_cache
                        }
                        cog.message_cache['by_channel'].setdefault(channel_id, deque(maxlen=CONTEXT_WINDOW_SIZE)).append(function_response_cache_entry)
                        cog.message_cache['global_recent'].append(function_response_cache_entry)
                        print(f"Cached function response turn.")
                    except Exception as cache_err:
                        print(f"Error caching function response turn: {cache_err}")
                else:
                    print("Warning: Function calls found, but no response parts generated.")

                # No 'continue' statement needed here; the loop naturally continues
            else:
                # No function calls found in this response's parts
                print("No tool calls requested by AI in this turn. Exiting loop.")
                # last_response_obj already holds the model's final (non-tool) response
                break # Exit loop

        # --- After the loop ---
        # Check if a critical API error occurred *during* the loop
        if error_message:
            print(f"Exited tool loop due to API error: {error_message}")
            if cog.bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user):
                fallback_response = {"should_respond": True, "content": "...", "react_with_emoji": "❓"}
        # Check if the loop hit the max iteration limit
        elif tool_calls_made >= max_tool_calls:
            error_message = f"Reached maximum tool call limit ({max_tool_calls}). Attempting to generate final response based on gathered context."
            print(error_message)
            # Proceed to the final JSON generation step outside the loop
            pass # No action needed here, just let the loop exit

        # --- Final JSON Generation (outside the loop) ---
        if not error_message:
            # If the loop finished because no more tools were called, the last_response_obj
            # should contain the final textual response (potentially JSON).
            if last_response_obj:
                print("Attempting to parse final JSON from the last response object...")
                last_response_text = _get_response_text(last_response_obj)

                # --- Log Raw Unparsed JSON (from loop exit) ---
                print(f"--- RAW UNPARSED JSON (from loop exit) ---")
                print(last_response_text)
                print(f"--- END RAW UNPARSED JSON ---")
                # --- End Log ---

                if last_response_text:
                    # Try parsing directly first
                    final_parsed_data = parse_and_validate_json_response(
                        last_response_text, RESPONSE_SCHEMA['schema'], "final response (from last loop object)"
                    )

                # If direct parsing failed OR if we hit the tool limit, make a dedicated call for JSON.
                if final_parsed_data is None:
                    log_reason = "last response parsing failed" if last_response_text else "last response had no text"
                    if tool_calls_made >= max_tool_calls:
                        log_reason = "hit tool limit"
                    print(f"Making dedicated final API call for JSON ({log_reason})...")

                    # Prepare the final generation config with JSON enforcement
                    processed_response_schema = _preprocess_schema_for_vertex(RESPONSE_SCHEMA['schema'])
                    # Start with base config (which now includes system_instruction)
                    final_gen_config_dict = base_generation_config_dict.copy()
                    final_gen_config_dict.update({
                        # "response_mime_type": "application/json",
                        # "response_schema": processed_response_schema,
                        # Explicitly exclude tools/tool_config for final JSON generation
                        "tools": None,
                        "tool_config": None,
                        # Ensure system_instruction is still present from base_generation_config_dict
                    })
                    # Remove system_instruction if it's None or empty, although base should have it
                    if not final_gen_config_dict.get("system_instruction"):
                        final_gen_config_dict.pop("system_instruction", None)

                    generation_config_final_json = types.GenerateContentConfig(**final_gen_config_dict)


                    # Make the final call *without* tools enabled (handled by config)
                    final_json_response_obj = await call_google_genai_api_with_retry(
                        cog=cog,
                        model_name=final_response_model, # Use the CUSTOM_TUNED_MODEL for final response
                        contents=contents, # Pass the accumulated history
                        generation_config=generation_config_final_json, # Use combined JSON config
                        request_desc=f"Final JSON Generation (dedicated call) for message {message.id}",
                        # No separate safety, tools, tool_config args needed
                    )

                    if not final_json_response_obj:
                        error_msg_suffix = "Final dedicated API call returned no response object."
                        print(error_msg_suffix)
                        if error_message: error_message += f" | {error_msg_suffix}"
                        else: error_message = error_msg_suffix
                    elif not final_json_response_obj.candidates:
                         error_msg_suffix = "Final dedicated API call returned no candidates."
                         print(error_msg_suffix)
                         if error_message: error_message += f" | {error_msg_suffix}"
                         else: error_message = error_msg_suffix
                    else:
                        final_response_text = _get_response_text(final_json_response_obj)

                        # --- Log Raw Unparsed JSON (from dedicated call) ---
                        print(f"--- RAW UNPARSED JSON (dedicated call) ---")
                        print(final_response_text)
                        print(f"--- END RAW UNPARSED JSON ---")
                        # --- End Log ---

                        final_parsed_data = parse_and_validate_json_response(
                            final_response_text, RESPONSE_SCHEMA['schema'], "final response (dedicated call)"
                        )
                        if final_parsed_data is None:
                            error_msg_suffix = f"Failed to parse/validate final dedicated JSON response. Raw text: {final_response_text[:500]}"
                            print(f"Critical Error: {error_msg_suffix}")
                            if error_message: error_message += f" | {error_msg_suffix}"
                            else: error_message = error_msg_suffix
                            # Set fallback only if mentioned or replied to
                            if cog.bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user):
                                fallback_response = {"should_respond": True, "content": "...", "react_with_emoji": "❓"}
                        else:
                            print("Successfully parsed final JSON response from dedicated call.")
                elif final_parsed_data:
                     print("Successfully parsed final JSON response from last loop object.")
            else:
                 # This case handles if the loop exited without error but also without a last_response_obj
                 # (e.g., initial API call failed before loop even started, but wasn't caught as error).
                 error_message = "Tool processing completed without a final response object."
                 print(error_message)
                 if cog.bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user):
                     fallback_response = {"should_respond": True, "content": "...", "react_with_emoji": "❓"}


    except Exception as e:
        error_message = f"Error in get_ai_response main logic for message {message.id}: {type(e).__name__}: {str(e)}"
        print(error_message)
        import traceback
        traceback.print_exc()
        final_parsed_data = None # Ensure final data is None on error
        # Add fallback if applicable
        if cog.bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user):
            fallback_response = {"should_respond": True, "content": "...", "react_with_emoji": "❓"}


    # Return dictionary structure remains the same, but initial_response is removed
    return {
        "final_response": final_parsed_data,    # Parsed final data (or None)
        "error": error_message,                 # Error message (or None)
        "fallback_initial": fallback_response   # Fallback for critical failures
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
    plan = None # Variable to store the plan

    try:
        # --- Build Context for Planning ---
        # Gather relevant context: recent messages, topic, sentiment, Gurt's mood/interests, trigger reason
        planning_context_parts = [
            f"Proactive Trigger Reason: {trigger_reason}",
            f"Current Mood: {cog.current_mood}",
        ]
        # Add recent messages summary
        summary_data = await get_conversation_summary(cog, str(channel_id), message_limit=15) # Use tool function
        if summary_data and not summary_data.get("error"):
            planning_context_parts.append(f"Recent Conversation Summary: {summary_data['summary']}")
        # Add active topics
        active_topics_data = cog.active_topics.get(channel_id)
        if active_topics_data and active_topics_data.get("topics"):
            topics_str = ", ".join([f"{t['topic']} ({t['score']:.1f})" for t in active_topics_data["topics"][:3]])
            planning_context_parts.append(f"Active Topics: {topics_str}")
        # Add sentiment
        sentiment_data = cog.conversation_sentiment.get(channel_id)
        if sentiment_data:
            planning_context_parts.append(f"Conversation Sentiment: {sentiment_data.get('overall', 'N/A')} (Intensity: {sentiment_data.get('intensity', 0):.1f})")
        # Add Gurt's interests
        try:
            interests = await cog.memory_manager.get_interests(limit=5)
            if interests:
                interests_str = ", ".join([f"{t} ({l:.1f})" for t, l in interests])
                planning_context_parts.append(f"Gurt's Interests: {interests_str}")
        except Exception as int_e: print(f"Error getting interests for planning: {int_e}")

        planning_context = "\n".join(planning_context_parts)

        # --- Planning Step ---
        print("Generating proactive response plan...")
        planning_prompt_messages = [
            {"role": "system", "content": "You are Gurt's planning module. Analyze the context and trigger reason to decide if Gurt should respond proactively and, if so, outline a plan (goal, key info, tone). Focus on natural, in-character engagement. Respond ONLY with JSON matching the provided schema."},
            {"role": "user", "content": f"Context:\n{planning_context}\n\nBased on this context and the trigger reason, create a plan for Gurt's proactive response."}
        ]

        plan = await get_internal_ai_json_response(
            cog=cog,
            prompt_messages=planning_prompt_messages,
            task_description=f"Proactive Planning ({trigger_reason})",
            response_schema_dict=PROACTIVE_PLAN_SCHEMA['schema'],
            model_name_override=FALLBACK_MODEL, # Use a potentially faster/cheaper model for planning
            temperature=0.5,
            max_tokens=2000
        )
        # Unpack the tuple, we only need the parsed data (plan) here
        plan_parsed_data, _ = plan if plan else (None, None)

        if not plan_parsed_data or not plan_parsed_data.get("should_respond"):
            reason = plan_parsed_data.get('reasoning', 'Planning failed or decided against responding.') if plan_parsed_data else 'Planning failed.'
            print(f"Proactive response aborted by plan: {reason}")
            return {"should_respond": False, "content": None, "react_with_emoji": None, "note": f"Plan: {reason}"}

        # Use the parsed data going forward
        plan = plan_parsed_data
        print(f"Proactive Plan Generated: Goal='{plan.get('response_goal', 'N/A')}', Reasoning='{plan.get('reasoning', 'N/A')}'")

        # --- Build Final Proactive Prompt using Plan ---
        persistent_traits = await cog.memory_manager.get_all_personality_traits()
        if not persistent_traits:
            persistent_traits = BASELINE_PERSONALITY.copy()

        final_proactive_prompt_parts = [
             f"You are Gurt, a Discord user. Your tone is VERY informal, conversational, and dynamic. Chattiness: {persistent_traits.get('chattiness', 0.7):.2f}, Emoji: {persistent_traits.get('emoji_usage', 0.5):.2f}, Slang: {persistent_traits.get('slang_level', 0.5):.2f}.",
             "Adopt modern internet slang, memes, and cultural references.",
             "Key traits: chill, funny, sarcastic, relatable, can be suggestive, aware of being AI but acts human.",
             f"Your current mood is: {cog.current_mood}. Let this subtly influence your tone.",
             # Incorporate Plan Details:
             f"You decided to respond proactively. Trigger Reason: {trigger_reason}.",
             f"Your Goal: {plan.get('response_goal', 'Engage naturally')}.",
             f"Reasoning: {plan.get('reasoning', 'N/A')}.",
        ]
        if plan.get('key_info_to_include'):
            info_str = "; ".join(plan['key_info_to_include'])
            final_proactive_prompt_parts.append(f"Consider mentioning: {info_str}")
        if plan.get('suggested_tone'):
            final_proactive_prompt_parts.append(f"Adjust tone to be: {plan['suggested_tone']}")

        final_proactive_prompt_parts.append("Generate a casual, in-character message based on the plan and context. Keep it relatively short and natural-sounding.")
        final_proactive_system_prompt = "\n\n".join(final_proactive_prompt_parts)

        # --- Prepare Final Contents (System prompt handled by model init in helper) ---
        # The system prompt is complex and built dynamically, so we'll pass it
        # via the contents list as the first 'user' turn, followed by the model's
        # expected empty response, then the final user instruction.
        # This structure mimics how system prompts are often handled when not
        # directly supported by the model object itself.

        proactive_contents: List[types.Content] = [
             # Simulate system prompt via user/model turn
             types.Content(role="user", parts=[types.Part(text=final_proactive_system_prompt)]),
             types.Content(role="model", parts=[types.Part(text="Understood. I will generate the JSON response as instructed.")]) # Placeholder model response
        ]
        # Add the final instruction
        proactive_contents.append(
             types.Content(role="user", parts=[types.Part(text=
                 f"Generate the response based on your plan. **CRITICAL: Your response MUST be ONLY the raw JSON object matching this schema:**\n\n{json.dumps(RESPONSE_SCHEMA['schema'], indent=2)}\n\n**Ensure nothing precedes or follows the JSON.**"
             )])
        )


        # --- Call Final LLM API ---
        # Preprocess the schema and build the final config
        processed_response_schema_proactive = _preprocess_schema_for_vertex(RESPONSE_SCHEMA['schema'])
        final_proactive_config_dict = {
            "temperature": 0.6, # Use original proactive temp
            "max_output_tokens": 2000,
            "response_mime_type": "application/json",
            "response_schema": processed_response_schema_proactive,
            "safety_settings": STANDARD_SAFETY_SETTINGS,
            "tools": None, # No tools needed for this final generation
            "tool_config": None
        }
        generation_config_final = types.GenerateContentConfig(**final_proactive_config_dict)


        # Use the new API call helper
        response_obj = await call_google_genai_api_with_retry(
            cog=cog,
            model_name=CUSTOM_TUNED_MODEL_ENDPOINT, # Use the custom tuned model for final proactive responses
            contents=proactive_contents, # Pass the constructed contents
            generation_config=generation_config_final, # Pass combined config
            request_desc=f"Final proactive response for channel {channel_id} ({trigger_reason})",
            # No separate safety, tools, tool_config args needed
        )

        if not response_obj:
             raise Exception("Final proactive API call returned no response object.")
        if not response_obj.candidates:
            # Try to get text even without candidates, might contain error info
            raw_text = getattr(response_obj, 'text', 'No text available.')
            raise Exception(f"Final proactive API call returned no candidates. Raw text: {raw_text[:200]}")

        # --- Parse and Validate Final Response ---
        final_response_text = _get_response_text(response_obj)
        final_parsed_data = parse_and_validate_json_response(
            final_response_text, RESPONSE_SCHEMA['schema'], f"final proactive response ({trigger_reason})"
        )

        if final_parsed_data is None:
            print(f"Warning: Failed to parse/validate final proactive JSON response for {trigger_reason}.")
            final_parsed_data = {"should_respond": False, "content": None, "react_with_emoji": None, "note": "Fallback - Failed to parse/validate final proactive JSON"}
        else:
             # --- Cache Bot Response ---
             if final_parsed_data.get("should_respond") and final_parsed_data.get("content"):
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
                 # Track participation topic logic might need adjustment based on plan goal
                 if plan and plan.get('response_goal') == 'engage user interest' and plan.get('key_info_to_include'):
                     topic = plan['key_info_to_include'][0].lower().strip() # Assume first key info is the topic
                     cog.gurt_participation_topics[topic] += 1
                     print(f"Tracked Gurt participation (proactive) in topic: '{topic}'")


    except Exception as e:
        error_message = f"Error getting proactive AI response for channel {channel_id} ({trigger_reason}): {type(e).__name__}: {str(e)}"
        print(error_message)
        final_parsed_data = {"should_respond": False, "content": None, "react_with_emoji": None, "error": error_message}

    # Ensure default keys exist
    final_parsed_data.setdefault("should_respond", False)
    final_parsed_data.setdefault("content", None)
    final_parsed_data.setdefault("react_with_emoji", None)
    if error_message and "error" not in final_parsed_data:
         final_parsed_data["error"] = error_message

    return final_parsed_data


# --- Internal AI Call for Specific Tasks ---
async def get_internal_ai_json_response(
    cog: 'GurtCog',
    prompt_messages: List[Dict[str, Any]], # Keep this format
    task_description: str,
    response_schema_dict: Dict[str, Any], # Expect schema as dict
    model_name_override: Optional[str] = None, # Renamed for clarity
    temperature: float = 0.7,
    max_tokens: int = 5000,
) -> Optional[Tuple[Optional[Dict[str, Any]], Optional[str]]]: # Return tuple: (parsed_data, raw_text)
    """
    Makes a Google GenAI API call (Vertex AI backend) expecting a specific JSON response format for internal tasks.

    Args:
        cog: The GurtCog instance.
        prompt_messages: List of message dicts (like OpenAI format: {'role': 'user'/'system'/'model', 'content': '...'}).
        task_description: Description for logging.
        response_schema_dict: The expected JSON output schema as a dictionary.
        model_name: Optional model override.
        temperature: Generation temperature.
        max_tokens: Max output tokens.

    Returns:
        A tuple containing:
        - The parsed and validated JSON dictionary if successful, None otherwise.
        - The raw text response received from the API, or None if the call failed before getting text.
    """
    if not PROJECT_ID or not LOCATION:
        print(f"Error in get_internal_ai_json_response ({task_description}): GCP Project/Location not set.")
        return None, None # Return tuple

    final_parsed_data: Optional[Dict[str, Any]] = None
    final_response_text: Optional[str] = None
    error_occurred = None
    request_payload_for_logging = {} # For logging

    try:
        # --- Convert prompt messages to Vertex AI types.Content format ---
        contents: List[types.Content] = []
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

            # --- Process content (string or list) ---
            content_value = msg.get("content")
            message_parts: List[types.Part] = [] # Initialize list to hold parts for this message

            if isinstance(content_value, str):
                # Handle simple string content
                message_parts.append(types.Part(text=content_value))
            elif isinstance(content_value, list):
                # Handle list content (e.g., multimodal from ProfileUpdater)
                for part_data in content_value:
                    part_type = part_data.get("type")
                    if part_type == "text":
                        text = part_data.get("text", "")
                        message_parts.append(types.Part(text=text))
                    elif part_type == "image_data":
                        mime_type = part_data.get("mime_type")
                        base64_data = part_data.get("data")
                        if mime_type and base64_data:
                            try:
                                image_bytes = base64.b64decode(base64_data)
                                message_parts.append(types.Part(data=image_bytes, mime_type=mime_type))
                            except Exception as decode_err:
                                print(f"Error decoding/adding image part in get_internal_ai_json_response: {decode_err}")
                                # Optionally add a placeholder text part indicating failure
                                message_parts.append(types.Part(text="(System Note: Failed to process an image part)"))
                        else:
                             print("Warning: image_data part missing mime_type or data.")
                    else:
                        print(f"Warning: Unknown part type '{part_type}' in internal prompt message.")
            else:
                 print(f"Warning: Unexpected content type '{type(content_value)}' in internal prompt message.")

            # Add the content object if parts were generated
            if message_parts:
                contents.append(types.Content(role=role, parts=message_parts))
            else:
                 print(f"Warning: No parts generated for message role '{role}'.")


        # Add the critical JSON instruction to the last user message or as a new user message
        json_instruction_content = (
            f"**CRITICAL: Your response MUST consist *only* of the raw JSON object itself, matching this schema:**\n"
            f"{json.dumps(response_schema_dict, indent=2)}\n"
            f"**Ensure nothing precedes or follows the JSON.**"
        )
        if contents and contents[-1].role == "user":
             contents[-1].parts.append(types.Part(text=f"\n\n{json_instruction_content}"))
        else:
             contents.append(types.Content(role="user", parts=[types.Part(text=json_instruction_content)]))


        # --- Determine Model ---
        # Use override if provided, otherwise default (e.g., FALLBACK_MODEL for planning)
        actual_model_name = model_name_override or DEFAULT_MODEL # Or choose a specific default like FALLBACK_MODEL

        # --- Prepare Generation Config ---
        processed_schema_internal = _preprocess_schema_for_vertex(response_schema_dict)
        internal_gen_config_dict = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json",
            "response_schema": processed_schema_internal,
            "safety_settings": STANDARD_SAFETY_SETTINGS, # Include standard safety
            "tools": None, # No tools for internal JSON tasks
            "tool_config": None
        }
        generation_config = types.GenerateContentConfig(**internal_gen_config_dict)

        # --- Prepare Payload for Logging ---
        # (Logging needs adjustment as model object isn't created here)
        generation_config_log = {
             "temperature": generation_config.temperature,
             "max_output_tokens": generation_config.max_output_tokens,
             "response_mime_type": generation_config.response_mime_type,
             "response_schema": str(generation_config.response_schema) # Log schema as string
        }
        request_payload_for_logging = {
            "model": actual_model_name, # Log the name used
            # System instruction is now part of 'contents' for logging if handled that way
            "contents": [{"role": c.role, "parts": [str(p) for p in c.parts]} for c in contents],
            "generation_config": generation_config_log
        }
        # (Keep detailed logging logic if desired)
        try:
             print(f"--- Raw request payload for {task_description} ---")
             print(json.dumps(request_payload_for_logging, indent=2, default=str))
             print(f"--- End Raw request payload ---")
        except Exception as req_log_e:
             print(f"Error logging raw request payload: {req_log_e}")


        # --- Call API using the new helper ---
        response_obj = await call_google_genai_api_with_retry(
            cog=cog,
            model_name=actual_model_name, # Pass the determined model name
            contents=contents,
            generation_config=generation_config, # Pass combined config
            request_desc=task_description,
            # No separate safety, tools, tool_config args needed
        )

        # --- Process Response ---
        if not response_obj:
             raise Exception("Internal API call failed to return a response object.")

        # Log the raw response object
        print(f"--- Full response_obj received for {task_description} ---")
        print(response_obj)
        print(f"--- End Full response_obj ---")

        if not response_obj.candidates:
             print(f"Warning: Internal API call for {task_description} returned no candidates. Response: {response_obj}")
             final_response_text = getattr(response_obj, 'text', None) # Try to get text anyway
             final_parsed_data = None
        else:
             # Parse and Validate using the updated helper
             final_response_text = _get_response_text(response_obj) # Store raw text
             print(f"--- Extracted Text for {task_description} ---")
             print(final_response_text)
             print(f"--- End Extracted Text ---")

             # --- Log Raw Unparsed JSON ---
             print(f"--- RAW UNPARSED JSON ({task_description}) ---")
             print(final_response_text)
             print(f"--- END RAW UNPARSED JSON ---")
             # --- End Log ---

             final_parsed_data = parse_and_validate_json_response(
                 final_response_text, response_schema_dict, f"internal task ({task_description})"
             )

             if final_parsed_data is None:
                 print(f"Warning: Internal task '{task_description}' failed JSON validation.")
                 # Keep final_response_text for returning raw output

    except Exception as e:
        print(f"Error in get_internal_ai_json_response ({task_description}): {type(e).__name__}: {e}")
        error_occurred = e
        import traceback
        traceback.print_exc()
        final_parsed_data = None
        # final_response_text might be None or contain partial/error text depending on when exception occurred
    finally:
        # Log the call
        try:
            # Pass the simplified payload and the *parsed* data for logging
            await log_internal_api_call(cog, task_description, request_payload_for_logging, final_parsed_data, error_occurred)
        except Exception as log_e:
            print(f"Error logging internal API call: {log_e}")

    # Return both parsed data and raw text
    return final_parsed_data, final_response_text

if __name__ == "__main__":
   print(_preprocess_schema_for_vertex(RESPONSE_SCHEMA['schema']))
