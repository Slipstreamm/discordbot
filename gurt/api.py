import discord
import aiohttp
import asyncio
import json
import base64
import re
import time
import datetime
from typing import TYPE_CHECKING, Optional, List, Dict, Any

# Relative imports for components within the 'gurt' package
from .config import (
    API_KEY, BASELINE_PERSONALITY, OPENROUTER_API_URL, DEFAULT_MODEL, FALLBACK_MODEL,
    API_TIMEOUT, API_RETRY_ATTEMPTS, API_RETRY_DELAY, TOOLS, RESPONSE_SCHEMA
)
from .prompt import build_dynamic_system_prompt
from .context import gather_conversation_context, get_memory_context # Renamed functions
from .tools import TOOL_MAPPING # Import tool mapping

if TYPE_CHECKING:
    from .cog import GurtCog # Import GurtCog for type hinting only

# --- API Call Helper ---
async def call_llm_api_with_retry(
    cog: 'GurtCog', # Pass cog instance for session access
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int,
    request_desc: str
) -> Dict[str, Any]:
    """
    Calls the OpenRouter API with retry logic for specific errors.

    Args:
        cog: The GurtCog instance containing the aiohttp session.
        payload: The JSON payload for the API request.
        headers: The request headers.
        timeout: Request timeout in seconds.
        request_desc: A description of the request for logging purposes.

    Returns:
        The JSON response data from the API.

    Raises:
        Exception: If the API call fails after all retry attempts or encounters a non-retryable error.
    """
    last_exception = None
    original_model = payload.get("model")
    current_model_key = original_model # Track the model used in the current attempt
    using_fallback = False
    start_time = time.monotonic() # Start timer before the loop

    if not cog.session:
        raise Exception(f"aiohttp session not initialized in GurtCog for {request_desc}")

    for attempt in range(API_RETRY_ATTEMPTS + 1): # Corrected range
        try:
            current_model_key = payload["model"] # Get model for this attempt
            model_desc = f"fallback model {FALLBACK_MODEL}" if using_fallback else f"primary model {original_model}"
            print(f"Sending API request for {request_desc} using {model_desc} (Attempt {attempt + 1}/{API_RETRY_ATTEMPTS + 1})...")

            async with cog.session.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Basic format check
                    if "choices" not in data or not data["choices"] or "message" not in data["choices"][0]:
                        error_msg = f"Unexpected API response format for {request_desc}: {json.dumps(data)}"
                        print(error_msg)
                        last_exception = ValueError(error_msg) # Treat as non-retryable format error
                        break # Exit retry loop

                    # --- Success Logging ---
                    elapsed_time = time.monotonic() - start_time
                    cog.api_stats[current_model_key]['success'] += 1
                    cog.api_stats[current_model_key]['total_time'] += elapsed_time
                    cog.api_stats[current_model_key]['count'] += 1
                    print(f"API request successful for {request_desc} ({current_model_key}) in {elapsed_time:.2f}s.")
                    return data # Success

                elif response.status == 429:  # Rate limit error
                    error_text = await response.text()
                    error_msg = f"Rate limit error for {request_desc} (Status 429): {error_text[:200]}"
                    print(error_msg)

                    if using_fallback or original_model != DEFAULT_MODEL:
                        if attempt < API_RETRY_ATTEMPTS:
                            cog.api_stats[current_model_key]['retries'] += 1 # Log retry
                            wait_time = API_RETRY_DELAY * (attempt + 2)
                            print(f"Waiting {wait_time} seconds before retrying...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            last_exception = Exception(error_msg)
                            break
                    else:
                        print(f"Switching from {DEFAULT_MODEL} to fallback model {FALLBACK_MODEL}")
                        payload["model"] = FALLBACK_MODEL
                        using_fallback = True
                        await asyncio.sleep(1)
                        continue # Retry immediately with fallback

                elif response.status >= 500: # Retry on server errors
                    error_text = await response.text()
                    error_msg = f"API server error for {request_desc} (Status {response.status}): {error_text[:100]}"
                    print(f"{error_msg} (Attempt {attempt + 1})")
                    last_exception = Exception(error_msg)
                    if attempt < API_RETRY_ATTEMPTS:
                        cog.api_stats[current_model_key]['retries'] += 1 # Log retry
                        await asyncio.sleep(API_RETRY_DELAY * (attempt + 1))
                        continue
                    else:
                        break
                else: # Non-retryable client error (4xx) or other issue
                    error_text = await response.text()
                    error_msg = f"API client error for {request_desc} (Status {response.status}): {error_text[:200]}"
                    print(error_msg)

                    if response.status in (400, 404, 422) and not using_fallback and original_model == DEFAULT_MODEL:
                        print(f"Model-specific error. Switching to fallback model {FALLBACK_MODEL}")
                        payload["model"] = FALLBACK_MODEL
                        using_fallback = True
                        await asyncio.sleep(1)
                        continue # Retry immediately with fallback

                    last_exception = Exception(error_msg)
                    break

        except asyncio.TimeoutError:
            error_msg = f"Request timed out for {request_desc} (Attempt {attempt + 1})"
            print(error_msg)
            last_exception = asyncio.TimeoutError(error_msg)
            if attempt < API_RETRY_ATTEMPTS:
                cog.api_stats[current_model_key]['retries'] += 1 # Log retry
                await asyncio.sleep(API_RETRY_DELAY * (attempt + 1))
                continue
            else:
                break
        except Exception as e:
            error_msg = f"Error during API call for {request_desc} (Attempt {attempt + 1}): {str(e)}"
            print(error_msg)
            last_exception = e
            if attempt < API_RETRY_ATTEMPTS:
                 cog.api_stats[current_model_key]['retries'] += 1 # Log retry
                 await asyncio.sleep(API_RETRY_DELAY * (attempt + 1))
                 continue
            else:
                 break

    # --- Failure Logging ---
    elapsed_time = time.monotonic() - start_time
    final_model_key = payload["model"] # Model used in the last failed attempt
    cog.api_stats[final_model_key]['failure'] += 1
    cog.api_stats[final_model_key]['total_time'] += elapsed_time
    cog.api_stats[final_model_key]['count'] += 1
    print(f"API request failed for {request_desc} ({final_model_key}) after {attempt + 1} attempts in {elapsed_time:.2f}s.")

    raise last_exception or Exception(f"API request failed for {request_desc} after {API_RETRY_ATTEMPTS + 1} attempts.")

# --- JSON Parsing Helper ---
def parse_ai_json_response(cog: 'GurtCog', response_text: Optional[str], context_description: str) -> Optional[Dict[str, Any]]:
    """
    Parses the AI's response text, attempting to extract a JSON object.
    Handles potential markdown code fences and returns a parsed dictionary or None.
    Updates the cog's needs_json_reminder flag.
    """
    if response_text is None:
        print(f"Parsing ({context_description}): Response text is None.")
        return None

    response_data = None
    try:
        # Attempt 1: Parse whole string as JSON
        response_data = json.loads(response_text)
        print(f"Parsing ({context_description}): Successfully parsed entire response as JSON.")
        cog.needs_json_reminder = False # Assume success resets reminder need
    except json.JSONDecodeError:
        # Attempt 2: Extract JSON object, handling optional markdown fences
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```|(\{.*\})', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1) or json_match.group(2)
            if json_str:
                try:
                    response_data = json.loads(json_str)
                    print(f"Parsing ({context_description}): Successfully extracted and parsed JSON using regex.")
                    cog.needs_json_reminder = False # Assume success resets reminder need
                except json.JSONDecodeError as e:
                    print(f"Parsing ({context_description}): Regex found potential JSON, but it failed to parse: {e}")
                    response_data = None # Parsing failed
            else:
                print(f"Parsing ({context_description}): Regex matched, but failed to capture JSON content.")
                response_data = None
        else:
            print(f"Parsing ({context_description}): Could not extract JSON object using regex.")
            response_data = None

    # Basic validation: Ensure it's a dictionary
    if response_data is not None and not isinstance(response_data, dict):
        print(f"Parsing ({context_description}): Parsed data is not a dictionary: {type(response_data)}")
        response_data = None

    # Ensure default keys exist if parsing was successful
    if isinstance(response_data, dict):
        response_data.setdefault("should_respond", False)
        response_data.setdefault("content", None)
        response_data.setdefault("react_with_emoji", None)
        response_data.setdefault("tool_requests", None) # Keep tool_requests if present
    elif response_data is None:
        # If parsing failed, set the reminder flag
        print(f"Parsing ({context_description}): Failed to parse JSON, setting reminder flag.")
        cog.needs_json_reminder = True


    return response_data

# --- Tool Processing ---
async def process_requested_tools(cog: 'GurtCog', tool_requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process tool requests specified in the AI's JSON response ('tool_requests' field).

    Args:
        cog: The GurtCog instance.
        tool_requests: A list of dictionaries, where each dict has "name" and "arguments".

    Returns:
        A list of dictionaries formatted for the follow-up API call, containing tool results or errors.
    """
    tool_results_for_api = []

    if not isinstance(tool_requests, list):
        print(f"Error: tool_requests is not a list: {tool_requests}")
        return [{
            "role": "tool",
            "content": json.dumps({"error": "Invalid format: tool_requests was not a list."}),
            "name": "tool_processing_error"
        }]

    print(f"Processing {len(tool_requests)} tool requests...")
    for i, request in enumerate(tool_requests):
        if not isinstance(request, dict):
            print(f"Error: Tool request at index {i} is not a dictionary: {request}")
            tool_results_for_api.append({
                "role": "tool",
                "content": json.dumps({"error": f"Invalid format: Tool request at index {i} was not a dictionary."}),
                "name": "tool_processing_error"
            })
            continue

        function_name = request.get("name")
        function_args = request.get("arguments", {})

        if not function_name or not isinstance(function_name, str):
             print(f"Error: Missing or invalid 'name' in tool request at index {i}: {request}")
             tool_results_for_api.append({
                "role": "tool",
                "content": json.dumps({"error": f"Missing or invalid 'name' in tool request at index {i}."}),
                "name": "tool_processing_error"
             })
             continue

        if not isinstance(function_args, dict):
             print(f"Error: Invalid 'arguments' format (not a dict) in tool request '{function_name}' at index {i}: {request}")
             tool_results_for_api.append({
                "role": "tool",
                "content": json.dumps({"error": f"Invalid 'arguments' format (not a dict) for tool '{function_name}' at index {i}."}),
                "name": function_name
             })
             continue

        print(f"Executing tool: {function_name} with args: {function_args}")
        tool_start_time = time.monotonic() # Start timer for this tool
        if function_name in TOOL_MAPPING:
            try:
                # Get the actual function implementation from the mapping
                tool_func = TOOL_MAPPING[function_name]
                # Execute the mapped function, passing the cog instance implicitly if it's a method,
                # or explicitly if needed (though tool functions shouldn't ideally rely on cog directly).
                # We assume tool functions are defined to accept their specific args.
                # If a tool needs cog state, it should be passed via arguments or refactored.
                # Let's assume the tool functions are standalone or methods of another class (like MemoryManager)
                # and don't directly need the `cog` instance passed here.
                # If they *are* methods of GurtCog, they'll have `self` automatically.
                result = await tool_func(cog, **function_args) # Pass cog if needed by tool impl

                # --- Tool Success Logging ---
                tool_elapsed_time = time.monotonic() - tool_start_time
                cog.tool_stats[function_name]['success'] += 1
                cog.tool_stats[function_name]['total_time'] += tool_elapsed_time
                cog.tool_stats[function_name]['count'] += 1
                print(f"Tool '{function_name}' executed successfully in {tool_elapsed_time:.2f}s.")

                tool_results_for_api.append({
                    "role": "tool",
                    "content": json.dumps(result),
                    "name": function_name
                })
            except Exception as e:
                # --- Tool Failure Logging ---
                tool_elapsed_time = time.monotonic() - tool_start_time
                cog.tool_stats[function_name]['failure'] += 1
                cog.tool_stats[function_name]['total_time'] += tool_elapsed_time
                cog.tool_stats[function_name]['count'] += 1
                error_message = f"Error executing tool {function_name}: {str(e)}"
                print(f"{error_message} (Took {tool_elapsed_time:.2f}s)")
                import traceback # Keep traceback for debugging
                traceback.print_exc()
                tool_results_for_api.append({
                    "role": "tool",
                    "content": json.dumps({"error": error_message}),
                    "name": function_name
                })
        else:
            # --- Tool Not Found Logging ---
            tool_elapsed_time = time.monotonic() - tool_start_time # Still record time even if not found
            cog.tool_stats[function_name]['failure'] += 1 # Count as failure
            cog.tool_stats[function_name]['total_time'] += tool_elapsed_time
            cog.tool_stats[function_name]['count'] += 1
            error_message = f"Tool '{function_name}' not found or implemented."
            print(f"{error_message} (Took {tool_elapsed_time:.2f}s)")
            tool_results_for_api.append({
                "role": "tool",
                "content": json.dumps({"error": error_message}),
                "name": function_name
            })

    return tool_results_for_api


# --- Main AI Response Function ---
async def get_ai_response(cog: 'GurtCog', message: discord.Message, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Gets responses from the OpenRouter API, handling potential tool usage and returning
    both initial and final parsed responses.

    Args:
        cog: The GurtCog instance.
        message: The triggering discord.Message.
        model: Optional override for the AI model.

    Returns:
        A dictionary containing:
        - "initial_response": Parsed JSON data from the first AI call (or None).
        - "final_response": Parsed JSON data from the second AI call after tools (or None).
        - "error": An error message string if a critical error occurred, otherwise None.
        - "fallback_initial": Optional minimal response if initial parsing failed critically.
    """
    if not API_KEY:
        return {"initial_response": None, "final_response": None, "error": "OpenRouter API key not configured"}

    # Store the current channel for context in tools (handled by cog instance state)
    # cog.current_channel = message.channel # This should be set in the listener before calling
    channel_id = message.channel.id
    user_id = message.author.id

    try:
        # --- Build Prompt Components ---
        final_system_prompt = await build_dynamic_system_prompt(cog, message)
        conversation_context_messages = gather_conversation_context(cog, channel_id, message.id) # Pass cog
        memory_context = await get_memory_context(cog, message) # Pass cog

        # Create messages array
        messages_list = [{"role": "system", "content": final_system_prompt}] # Renamed variable

        if memory_context:
            messages_list.append({"role": "system", "content": memory_context})

        if cog.needs_json_reminder:
            reminder_message = {
                "role": "system",
                "content": "**CRITICAL REMINDER:** Your previous response did not follow the required JSON format. You MUST respond ONLY with a valid JSON object matching the specified schema. Do NOT include any other text, explanations, or markdown formatting outside the JSON structure."
            }
            messages_list.append(reminder_message)
            print("Added JSON format reminder message.")
            # Don't reset the flag here, reset it only on successful parse in parse_ai_json_response

        messages_list.extend(conversation_context_messages)

        # --- Prepare the current message content (potentially multimodal) ---
        current_message_content_parts = []
        # Use a utility function for formatting (assuming it's moved to utils.py)
        from .utils import format_message # Import here or pass cog if it's a method
        formatted_current_message = format_message(cog, message) # Pass cog if needed

        text_content = f"{formatted_current_message['author']['display_name']}: {formatted_current_message['content']}"
        if formatted_current_message.get("mentioned_users_details"):
            mentions_str = ", ".join([f"{m['display_name']}(id:{m['id']})" for m in formatted_current_message["mentioned_users_details"]])
            text_content += f"\n(Message Details: Mentions=[{mentions_str}])"
        current_message_content_parts.append({"type": "text", "text": text_content})

        if message.attachments:
            print(f"Processing {len(message.attachments)} attachments for message {message.id}")
            for attachment in message.attachments:
                content_type = attachment.content_type
                if content_type and content_type.startswith("image/"):
                    try:
                        print(f"Downloading image: {attachment.filename} ({content_type})")
                        image_bytes = await attachment.read()
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        mime_type = content_type.split(';')[0]
                        image_url = f"data:{mime_type};base64,{base64_image}"
                        current_message_content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        })
                        print(f"Added image {attachment.filename} to payload.")
                    except discord.HTTPException as e: print(f"Failed to download image {attachment.filename}: {e}")
                    except Exception as e: print(f"Error processing image {attachment.filename}: {e}")
                else: print(f"Skipping non-image attachment: {attachment.filename} ({content_type})")

        if len(current_message_content_parts) == 1 and current_message_content_parts[0]["type"] == "text":
            messages_list.append({"role": "user", "content": current_message_content_parts[0]["text"]})
            print("Appended text-only content to messages.")
        elif len(current_message_content_parts) > 1:
            messages_list.append({"role": "user", "content": current_message_content_parts})
            print("Appended multimodal content (text + images) to messages.")
        else:
            print("Warning: No content parts generated for user message.")
            messages_list.append({"role": "user", "content": ""})

        # --- Add final instruction for the AI ---
        message_length_guidance = ""
        if hasattr(cog, 'channel_message_length') and channel_id in cog.channel_message_length:
            length_factor = cog.channel_message_length[channel_id]
            if length_factor < 0.3: message_length_guidance = " Keep your response brief."
            elif length_factor > 0.7: message_length_guidance = " You can be more detailed."

        # Use RESPONSE_SCHEMA from config
        response_schema_json = json.dumps(RESPONSE_SCHEMA['schema'], indent=2)
        messages_list.append({
            "role": "user",
            "content": f"Given the preceding context, decide if you (gurt) should respond. **ABSOLUTELY CRITICAL: Your response MUST consist *only* of the raw JSON object itself, with NO additional text, explanations, or markdown formatting (like \\`\\`\\`json ... \\`\\`\\`) surrounding it. The entire response must be *just* the JSON matching this schema:**\n\n{response_schema_json}\n\n**Ensure there is absolutely nothing before or after the JSON object.**{message_length_guidance}"
        })

        # Prepare the request payload
        payload = {
            "model": model or DEFAULT_MODEL,
            "messages": messages_list,
            "tools": TOOLS, # Use TOOLS from config
            "temperature": 0.75,
            "max_tokens": 10000,
            # "response_format": { # Still potentially problematic with tools
            #     "type": "json_schema",
            #     "json_schema": RESPONSE_SCHEMA
            # }
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
            "HTTP-Referer": "https://discord-gurt-bot.example.com",
            "X-Title": "Gurt Discord Bot"
        }

        # Make the initial API request
        data = await call_llm_api_with_retry(
            cog=cog, # Pass cog instance
            payload=payload,
            headers=headers,
            timeout=API_TIMEOUT,
            request_desc=f"Initial response for message {message.id}"
        )

        print(f"Raw API Response: {json.dumps(data, indent=2)}")
        ai_message = data["choices"][0]["message"]
        messages_list.append(ai_message) # Add AI response for potential tool use context

        # --- Parse Initial Response ---
        initial_response_text = ai_message.get("content")
        initial_parsed_data = parse_ai_json_response(cog, initial_response_text, "initial response") # Pass cog

        if initial_parsed_data is None:
            print("Critical Error: Failed to parse initial AI response.")
            # cog.needs_json_reminder is set within parse_ai_json_response
            fallback_content = None
            replied_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user
            if cog.bot.user.mentioned_in(message) or replied_to_bot:
                fallback_content = "..."
            return {
                "initial_response": None, "final_response": None,
                "error": "Failed to parse initial AI JSON response.",
                "fallback_initial": {"should_respond": bool(fallback_content), "content": fallback_content, "react_with_emoji": "❓"} if fallback_content else None
            }

        # --- Check for Tool Requests ---
        requested_tools = initial_parsed_data.get("tool_requests")
        final_parsed_data = None

        if requested_tools and isinstance(requested_tools, list) and len(requested_tools) > 0:
            print(f"AI requested {len(requested_tools)} tools. Processing...")
            tool_results_for_api = await process_requested_tools(cog, requested_tools) # Pass cog

            messages_for_follow_up = messages_list[:-1] # Exclude the final user instruction
            messages_for_follow_up.append(ai_message)
            messages_for_follow_up.extend(tool_results_for_api)
            messages_for_follow_up.append({
                "role": "user",
                "content": f"Okay, the requested tools have been executed. Here are the results. Now, generate the final user-facing response based on these results and the previous conversation context. **CRITICAL: Your response MUST be ONLY the raw JSON object matching the standard schema (should_respond, content, react_with_emoji). Do NOT include the 'tool_requests' field this time.**\n\n**Ensure nothing precedes or follows the JSON.**{message_length_guidance}"
            })

            follow_up_payload = {
                "model": model or DEFAULT_MODEL,
                "messages": messages_for_follow_up,
                "temperature": 0.75,
                "max_tokens": 10000,
            }

            print("Making follow-up API call with tool results...")
            follow_up_data = await call_llm_api_with_retry(
                cog=cog, # Pass cog
                payload=follow_up_payload,
                headers=headers,
                timeout=API_TIMEOUT,
                request_desc=f"Follow-up response for message {message.id} after tool execution"
            )

            follow_up_ai_message = follow_up_data["choices"][0]["message"]
            final_response_text = follow_up_ai_message.get("content")
            final_parsed_data = parse_ai_json_response(cog, final_response_text, "final response after tools") # Pass cog

            if final_parsed_data is None:
                print("Warning: Failed to parse final AI response after tool use.")
                # cog.needs_json_reminder is set within parse_ai_json_response
        else:
            final_parsed_data = None

        if initial_parsed_data:
            initial_parsed_data.pop("tool_requests", None)

        return {
            "initial_response": initial_parsed_data,
            "final_response": final_parsed_data,
            "error": None
        }

    except Exception as e:
        error_message = f"Error in get_ai_response main loop for message {message.id}: {str(e)}"
        print(error_message)
        import traceback
        traceback.print_exc()
        return {"initial_response": None, "final_response": None, "error": error_message}


# --- Proactive AI Response Function ---
async def get_proactive_ai_response(cog: 'GurtCog', message: discord.Message, trigger_reason: str) -> Dict[str, Any]:
    """Generates a proactive response based on a specific trigger."""
    if not API_KEY:
        return {"should_respond": False, "content": None, "react_with_emoji": None, "error": "OpenRouter API key not configured"}

    print(f"--- Proactive Response Triggered: {trigger_reason} ---")
    channel_id = message.channel.id
    channel_name = message.channel.name if hasattr(message.channel, 'name') else "DM"

    # --- Enhanced Context Gathering ---
    recent_participants_info = []
    semantic_context_str = ""
    pre_lull_messages_content = []

    try:
        cached_messages = list(cog.message_cache['by_channel'].get(channel_id, []))
        if cached_messages and cached_messages[-1]['id'] == str(message.id):
            cached_messages = cached_messages[:-1]
        pre_lull_messages = cached_messages[-5:]

        if pre_lull_messages:
            pre_lull_messages_content = [msg['content'] for msg in pre_lull_messages if msg['content']]
            recent_authors = {}
            for msg in reversed(pre_lull_messages):
                author_id = msg['author']['id']
                if author_id != str(cog.bot.user.id) and author_id not in recent_authors:
                    recent_authors[author_id] = {"name": msg['author']['name'], "display_name": msg['author']['display_name']}
                    if len(recent_authors) >= 2: break

            for user_id, author_info in recent_authors.items():
                user_info = {"name": author_info['display_name']}
                user_facts = await cog.memory_manager.get_user_facts(user_id, context="general conversation lull")
                if user_facts: user_info["facts"] = "; ".join(user_facts)
                bot_id_str = str(cog.bot.user.id)
                key_1, key_2 = (user_id, bot_id_str) if user_id < bot_id_str else (bot_id_str, user_id)
                relationship_score = cog.user_relationships.get(key_1, {}).get(key_2, 0.0)
                user_info["relationship_score"] = f"{relationship_score:.1f}/100"
                recent_participants_info.append(user_info)

        if pre_lull_messages_content and cog.memory_manager.semantic_collection:
            query_text = " ".join(pre_lull_messages_content)
            semantic_results = await cog.memory_manager.search_semantic_memory(query_text=query_text, n_results=3)
            if semantic_results:
                semantic_parts = ["Semantically similar past messages:"]
                for result in semantic_results:
                    if result.get('id') in [msg['id'] for msg in pre_lull_messages]: continue
                    doc = result.get('document', 'N/A')
                    meta = result.get('metadata', {})
                    dist = result.get('distance', 1.0)
                    similarity_score = 1.0 - dist
                    timestamp_str = datetime.datetime.fromtimestamp(meta.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M') if meta.get('timestamp') else 'Unknown time'
                    author_name = meta.get('display_name', meta.get('user_name', 'Unknown user'))
                    semantic_parts.append(f"- (Similarity: {similarity_score:.2f}) {author_name} (at {timestamp_str}): {doc[:100]}")
                if len(semantic_parts) > 1: semantic_context_str = "\n".join(semantic_parts)

    except Exception as e:
        print(f"Error gathering enhanced context for proactive prompt: {e}")
        import traceback
        traceback.print_exc()

    # --- Build Proactive System Prompt ---
    # Fetch current traits for the base prompt part
    persistent_traits = await cog.memory_manager.get_all_personality_traits()
    if not persistent_traits: persistent_traits = BASELINE_PERSONALITY.copy()

    proactive_prompt_parts = [
        f"You are Gurt, a Discord user. Your tone is VERY informal, conversational, and dynamic. Chattiness: {persistent_traits.get('chattiness', 0.7):.2f}, Emoji: {persistent_traits.get('emoji_usage', 0.5):.2f}, Slang: {persistent_traits.get('slang_level', 0.5):.2f}.", # Simplified base
        "Adopt modern internet slang, memes, and cultural references.",
        "Key traits: chill, funny, sarcastic, relatable, can be suggestive, aware of being AI but acts human.",
        f"Your current mood is: {cog.current_mood}. Let this subtly influence your tone.",
        f"The conversation in channel '{channel_name}' has been triggered for a proactive response. Reason: {trigger_reason}.",
        "Your goal is to generate a casual, in-character message based on the trigger reason and context.",
        "Keep the message relatively short and natural-sounding."
    ]

    # Add Specific Guidance based on Trigger Reason
    if "Relevant topic mentioned" in trigger_reason:
        similarity_match = re.search(r'Similarity: (\d\.\d+)', trigger_reason)
        similarity_score = similarity_match.group(1) if similarity_match else "high"
        proactive_prompt_parts.append(f"A topic relevant to your knowledge (similarity: {similarity_score}) was just mentioned. Consider chiming in.")
    elif "Conversation lull" in trigger_reason:
         proactive_prompt_parts.append("The chat has gone quiet. Consider commenting on the silence, asking a question, or sharing a thought.")
    elif "High relationship score" in trigger_reason:
        score_match = re.search(r'\((\d+\.\d+)\)', trigger_reason)
        score = score_match.group(1) if score_match else "high"
        proactive_prompt_parts.append(f"You have a high relationship score ({score}/100) with {message.author.display_name}. Consider engaging them directly.")

    # Add Existing Context
    try:
        active_channel_topics = cog.active_topics.get(channel_id, {}).get("topics", [])
        if active_channel_topics:
             top_topics = sorted(active_channel_topics, key=lambda t: t["score"], reverse=True)[:2]
             topics_str = ", ".join([f"'{t['topic']}'" for t in top_topics])
             proactive_prompt_parts.append(f"Recent topics: {topics_str}.")
        general_facts = await cog.memory_manager.get_general_facts(limit=3)
        if general_facts: proactive_prompt_parts.append(f"General knowledge: {'; '.join(general_facts)}")
        interests = await cog.memory_manager.get_interests(limit=3, min_level=0.4)
        if interests: proactive_prompt_parts.append(f"Your interests: {', '.join([f'{t} ({l:.1f})' for t, l in interests])}.")
    except Exception as e: print(f"Error gathering context for proactive prompt: {e}")

    # Add Enhanced Context
    if recent_participants_info:
        participants_str = "\n".join([f"- {p['name']} (Rel: {p.get('relationship_score', 'N/A')}, Facts: {p.get('facts', 'None')})" for p in recent_participants_info])
        proactive_prompt_parts.append(f"Recent participants:\n{participants_str}")
    if semantic_context_str: proactive_prompt_parts.append(semantic_context_str)

    # Add Lull Strategies if applicable
    if "Conversation lull" in trigger_reason:
        proactive_prompt_parts.extend([
            "--- Strategies for Lull ---",
            "- Comment on silence.", "- Ask open question on recent topics/interests.",
            "- Share brief thought on facts/memories/interests.", "- Mention participant fact casually.",
            "- Bring up high interest.", "- Avoid generic 'what's up?'.",
            "--- End Strategies ---"
        ])

    proactive_system_prompt = "\n\n".join(proactive_prompt_parts)

    # --- Prepare API Messages & Payload ---
    messages_list = [ # Renamed variable
        {"role": "system", "content": proactive_system_prompt},
        {"role": "user", "content": f"Generate a response based on the situation. **CRITICAL: Your response MUST be ONLY the raw JSON object matching this schema:**\n\n{{{{\n  \"should_respond\": boolean,\n  \"content\": string,\n  \"react_with_emoji\": string | null\n}}}}\n\n**Ensure nothing precedes or follows the JSON.**"}
    ]
    payload = {
        "model": DEFAULT_MODEL, "messages": messages_list,
        "temperature": 0.8, "max_tokens": 200,
    }
    headers = {
        "Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}",
        "HTTP-Referer": "https://discord-gurt-bot.example.com", "X-Title": f"Gurt Discord Bot (Proactive)"
    }

    # --- Call LLM API ---
    try:
        data = await call_llm_api_with_retry(
            cog=cog, payload=payload, headers=headers, timeout=API_TIMEOUT,
            request_desc=f"Proactive response for channel {channel_id} ({trigger_reason})"
        )
        ai_message = data["choices"][0]["message"]
        final_response_text = ai_message.get("content")

        # --- Parse Response ---
        response_data = parse_ai_json_response(cog, final_response_text, f"proactive response ({trigger_reason})") # Pass cog

        if response_data is None: # Handle parse failure
             response_data = {"should_respond": False, "content": None, "react_with_emoji": None, "note": "Fallback - Failed to parse proactive JSON"}

        # Ensure default keys exist
        response_data.setdefault("should_respond", False)
        response_data.setdefault("content", None)
        response_data.setdefault("react_with_emoji", None)

        # --- Cache Bot Response ---
        if response_data.get("should_respond") and response_data.get("content"):
            # Need to import format_message if not already done
            from .utils import format_message # Assuming it's moved
            # Create a mock message object or dict for formatting
            # This is tricky as we don't have a real message object
            bot_response_cache_entry = {
                "id": f"bot_proactive_{message.id}_{int(time.time())}",
                "author": {"id": str(cog.bot.user.id), "name": cog.bot.user.name, "display_name": cog.bot.user.display_name, "bot": True},
                "content": response_data.get("content", ""), "created_at": datetime.datetime.now().isoformat(),
                "attachments": [], "embeds": False, "mentions": [], "replied_to_message_id": None,
                # Add other fields format_message might expect, potentially with defaults
                "channel": message.channel, # Pass channel object if needed by format_message
                "guild": message.guild,     # Pass guild object if needed
                "reference": None,
                "mentioned_users_details": [] # Add empty list
            }
            # We might need to simplify caching here or adjust format_message
            cog.message_cache['by_channel'][channel_id].append(bot_response_cache_entry)
            cog.message_cache['global_recent'].append(bot_response_cache_entry)
            cog.bot_last_spoke[channel_id] = time.time()
            # Track participation topic
            # Need _identify_conversation_topics - assuming it's moved to analysis.py
            from .analysis import identify_conversation_topics # Import here
            identified_topics = identify_conversation_topics(cog, [bot_response_cache_entry]) # Pass cog
            if identified_topics:
                topic = identified_topics[0]['topic'].lower().strip()
                cog.gurt_participation_topics[topic] += 1
                print(f"Tracked Gurt proactive participation in topic: '{topic}'")

        return response_data

    except Exception as e:
        error_message = f"Error getting proactive AI response for channel {channel_id} ({trigger_reason}): {str(e)}"
        print(error_message)
        return {"should_respond": False, "content": None, "react_with_emoji": None, "error": error_message}


# --- Internal AI Call for Specific Tasks ---
async def get_internal_ai_json_response(
    cog: 'GurtCog', # Pass cog instance
    prompt_messages: List[Dict[str, Any]],
    task_description: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 5000,
    response_format: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Makes an AI call expecting a specific JSON response format for internal tasks.

    Args:
        cog: The GurtCog instance.
        ... (other args)

    Returns:
        The parsed JSON dictionary if successful, None otherwise.
    """
    if not API_KEY or not cog.session:
        print(f"Error in get_internal_ai_json_response ({task_description}): API key or session not available.")
        return None

    response_data = None
    error_occurred = None
    payload = {}

    try:
        json_instruction_content = "**CRITICAL: Your response MUST consist *only* of the raw JSON object itself.**"
        if response_format and response_format.get("type") == "json_schema":
             schema_for_prompt = response_format.get("json_schema", {}).get("schema", {})
             if schema_for_prompt:
                 json_format_instruction = json.dumps(schema_for_prompt, indent=2)
                 json_instruction_content = f"**CRITICAL: Your response MUST consist *only* of the raw JSON object itself, matching this schema:**\n{json_format_instruction}\n**Ensure nothing precedes or follows the JSON.**"

        prompt_messages.append({"role": "user", "content": json_instruction_content})

        payload = {
            "model": model or DEFAULT_MODEL,
            "messages": prompt_messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if response_format: payload["response_format"] = response_format

        headers = {
            "Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}",
            "HTTP-Referer": "https://discord-gurt-bot.example.com",
            "X-Title": f"Gurt Discord Bot ({task_description})"
        }

        api_response_data = await call_llm_api_with_retry(
            cog=cog, payload=payload, headers=headers, timeout=API_TIMEOUT,
            request_desc=task_description
        )

        ai_message = api_response_data["choices"][0]["message"]
        print(f"get_internal_ai_json_response ({task_description}): Raw AI Response: {json.dumps(api_response_data, indent=2)}")
        final_response_text = ai_message.get("content")

        if not final_response_text:
            print(f"get_internal_ai_json_response ({task_description}): Warning - AI response content is empty.")

        if final_response_text:
            # Use the centralized parsing function
            response_data = parse_ai_json_response(cog, final_response_text, f"internal task ({task_description})") # Pass cog

            if response_data and not isinstance(response_data, dict):
                print(f"get_internal_ai_json_response ({task_description}): Parsed data not a dict.")
                response_data = None
        else:
            response_data = None

    except Exception as e:
        print(f"Error in get_internal_ai_json_response ({task_description}): {e}")
        error_occurred = e
        import traceback
        traceback.print_exc()
        response_data = None
    finally:
        # Log the call (needs _log_internal_api_call, assuming moved to utils.py)
        try:
            from .utils import log_internal_api_call # Import here
            await log_internal_api_call(cog, task_description, payload, response_data, error_occurred) # Pass cog
        except ImportError:
            print("Warning: Could not import log_internal_api_call from utils.")
        except Exception as log_e:
            print(f"Error logging internal API call: {log_e}")


    return response_data
