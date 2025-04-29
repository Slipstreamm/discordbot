import discord
import asyncio
import json
import base64
import re
import time
import datetime
import functools # Added for partial tool application
import logging # Added for logging
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Union, AsyncIterable
import jsonschema # For manual JSON validation

# Vertex AI and LangChain Imports
try:
    import vertexai
    from vertexai import agent_engines
    from vertexai.generative_models import ( # Keep specific types if needed elsewhere, otherwise remove
         Part, Content, GenerationConfig, HarmCategory, HarmBlockThreshold
    )
    from google.api_core import exceptions as google_exceptions
    # Langchain specific imports (add as needed)
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.tools import Tool as LangchainTool # Rename to avoid conflict
    # Import specific chat model and message types
    from langchain_google_vertexai import ChatVertexAI
    from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage

except ImportError:
    print("WARNING: google-cloud-vertexai, langchain-google-vertexai or langchain-core not installed. API calls will fail.")
    # Define dummy classes/exceptions if library isn't installed
    class DummyAgent:
        def __init__(self, model, tools, chat_history, prompt, model_kwargs): pass
        async def query(self, input, config): return {"output": '{"should_respond": false, "content": "Error: Vertex/LangChain SDK not installed."}'} # Simulate error response
    agent_engines = type('agent_engines', (object,), {'LangchainAgent': DummyAgent})() # Mock the class structure
    # Define other dummies if needed by remaining code
    # Keep Part and Content if used by format_message or other retained logic
    class DummyPart:
        @staticmethod
        def from_text(text): return None
        @staticmethod
        def from_data(data, mime_type): return None
        @staticmethod
        def from_uri(uri, mime_type): return None
    Part = DummyPart
    Content = dict
    GenerationConfig = dict # Keep if model_kwargs uses it, otherwise remove
    class DummyGoogleExceptions:
        ResourceExhausted = type('ResourceExhausted', (Exception,), {})
        InternalServerError = type('InternalServerError', (Exception,), {})
        ServiceUnavailable = type('ServiceUnavailable', (Exception,), {})
        InvalidArgument = type('InvalidArgument', (Exception,), {})
        GoogleAPICallError = type('GoogleAPICallError', (Exception,), {}) # Generic fallback
    google_exceptions = DummyGoogleExceptions()
    # Dummy Langchain types
    ChatPromptTemplate = object
    MessagesPlaceholder = object
    LangchainTool = object # Use renamed dummy
    ChatVertexAI = object # Dummy Chat Model
    BaseMessage = object
    SystemMessage = object
    HumanMessage = object
    AIMessage = object


# Relative imports for components within the 'gurt' package
from .config import (
    PROJECT_ID, LOCATION, DEFAULT_MODEL, FALLBACK_MODEL,
    API_TIMEOUT, API_RETRY_ATTEMPTS, API_RETRY_DELAY, # Keep retry config? LangchainAgent might handle it.
    RESPONSE_SCHEMA, PROACTIVE_PLAN_SCHEMA, BASELINE_PERSONALITY # Keep schemas
)
from .prompt import build_dynamic_system_prompt
# from .context import gather_conversation_context # No longer needed directly here
from .memory import get_gurt_session_history # Import the history factory
from .tools import TOOL_MAPPING, get_conversation_summary # Import tool mapping AND specific tools if needed directly
from .utils import format_message, log_internal_api_call # Keep format_message AND re-import log helper

if TYPE_CHECKING:
    from .cog import GurtCog # Import GurtCog for type hinting only

# Setup logging
logger = logging.getLogger(__name__)

# --- Initialize Vertex AI ---
# LangchainAgent handles initialization implicitly if needed,
# but explicit init is good practice.
try:
    if PROJECT_ID and LOCATION:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        logger.info(f"Vertex AI initialized for project '{PROJECT_ID}' in location '{LOCATION}'.")
    else:
        logger.warning("PROJECT_ID or LOCATION not set. Vertex AI initialization skipped.")
except NameError:
    logger.warning("Vertex AI SDK not imported, skipping initialization.")
except Exception as e:
    logger.error(f"Error initializing Vertex AI: {e}", exc_info=True)

# --- Constants ---
# Define standard safety settings (adjust as needed)
# Use actual types if import succeeded, otherwise fallback to Any
_HarmCategory = globals().get('HarmCategory', Any)
_HarmBlockThreshold = globals().get('HarmBlockThreshold', Any)
STANDARD_SAFETY_SETTINGS = {
    getattr(_HarmCategory, 'HARM_CATEGORY_HATE_SPEECH', 'HARM_CATEGORY_HATE_SPEECH'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
    getattr(_HarmCategory, 'HARM_CATEGORY_DANGEROUS_CONTENT', 'HARM_CATEGORY_DANGEROUS_CONTENT'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
    getattr(_HarmCategory, 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'HARM_CATEGORY_SEXUALLY_EXPLICIT'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
    getattr(_HarmCategory, 'HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_HARASSMENT'): getattr(_HarmBlockThreshold, 'BLOCK_MEDIUM_AND_ABOVE', 'BLOCK_MEDIUM_AND_ABOVE'),
}
# Note: LangchainAgent might handle safety settings differently or via model_kwargs. Check documentation.


# --- JSON Parsing and Validation Helper (Keep this) ---
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
        logger.debug(f"Parsing ({context_description}): Response text is None.")
        return None

    parsed_data = None
    raw_json_text = response_text # Start with the full text

    # Attempt 1: Try parsing the whole string directly
    try:
        # Handle potential markdown code blocks around the JSON
        match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response_text, re.DOTALL)
        if match:
            json_str = match.group(1)
            logger.debug(f"Parsing ({context_description}): Found JSON within markdown code block.")
        else:
            # If no code block, assume the whole text is JSON (or just the object part)
            # Find the first '{' and last '}'
            start_index = response_text.find('{')
            end_index = response_text.rfind('}')
            if start_index != -1 and end_index != -1 and end_index > start_index:
                 json_str = response_text[start_index : end_index + 1]
                 logger.debug(f"Parsing ({context_description}): Extracted potential JSON between braces.")
            else:
                 json_str = raw_json_text # Fallback to using the whole text
                 logger.debug(f"Parsing ({context_description}): No code block or braces found, attempting parse on raw text.")

        parsed_data = json.loads(json_str)
        logger.info(f"Parsing ({context_description}): Successfully parsed JSON.")

    except json.JSONDecodeError as e:
        logger.warning(f"Parsing ({context_description}): Failed to decode JSON: {e}\nContent: {raw_json_text[:500]}")
        parsed_data = None

    # Validation step
    if parsed_data is not None:
        if not isinstance(parsed_data, dict):
            logger.warning(f"Parsing ({context_description}): Parsed data is not a dictionary: {type(parsed_data)}")
            return None # Fail validation if not a dict

        try:
            jsonschema.validate(instance=parsed_data, schema=schema)
            logger.info(f"Parsing ({context_description}): JSON successfully validated against schema.")
            # Ensure default keys exist after validation
            parsed_data.setdefault("should_respond", False)
            parsed_data.setdefault("content", None)
            parsed_data.setdefault("react_with_emoji", None)
            # Add reply_to_message_id default if not present
            parsed_data.setdefault("reply_to_message_id", None)
            return parsed_data
        except jsonschema.ValidationError as e:
            logger.error(f"Parsing ({context_description}): JSON failed schema validation: {e.message}\nData: {parsed_data}")
            # Optionally log more details: e.path, e.schema_path, e.instance
            return None # Validation failed
        except Exception as e: # Catch other potential validation errors
            logger.error(f"Parsing ({context_description}): Unexpected error during JSON schema validation: {e}", exc_info=True)
            return None
    else:
        # Parsing failed before validation could occur
        return None


# --- Main AI Response Function (Refactored for LangchainAgent) ---
async def get_ai_response(cog: 'GurtCog', message: discord.Message, model_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Gets responses using Vertex AI LangchainAgent, handling tools and history.

    Args:
        cog: The GurtCog instance.
        message: The triggering discord.Message.
        model_name: Optional override for the AI model name.

    Returns:
        A dictionary containing:
        - "final_response": Parsed JSON data from the final AI call (or None if parsing/validation fails).
        - "error": An error message string if a critical error occurred, otherwise None.
        - "fallback_initial": Optional minimal response if parsing failed critically.
    """
    if not PROJECT_ID or not LOCATION:
         return {"final_response": None, "error": "Google Cloud Project ID or Location not configured", "fallback_initial": None}

    channel_id = message.channel.id
    user_id = message.author.id
    final_parsed_data = None
    error_message = None
    fallback_response = None
    start_time = time.monotonic()
    request_desc = f"LangchainAgent response for message {message.id}"
    selected_model_name = model_name or DEFAULT_MODEL

    try:
        # --- 1. Build System Prompt ---
        # This now includes dynamic context like mood, facts, etc.
        system_prompt_text = await build_dynamic_system_prompt(cog, message)
        # Create a LangChain prompt template
        # LangchainAgent default prompt includes placeholders for chat_history and agent_scratchpad
        # We just need to provide the system message part.
        # Note: The exact structure might depend on the agent type used by LangchainAgent.
        # Assuming a standard structure:
        # Use the variable names provided by the agent ('history', 'intermediate_steps')
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt_text),
            MessagesPlaceholder(variable_name="history"), # Matches agent input
            ("user", "{input}"), # User input placeholder
            MessagesPlaceholder(variable_name="intermediate_steps"), # Matches agent input
        ])

        # --- 2. Prepare Tools ---
        # Collect decorated tool functions from the TOOL_MAPPING
        # The @tool decorator handles schema generation and description.
        # We still need to bind the 'cog' instance to each tool call.
        prepared_tools = []
        for tool_name, tool_func in TOOL_MAPPING.items():
            # Check if the function is actually decorated (optional, but good practice)
            # The @tool decorator adds attributes like .name, .description, .args_schema
            if not hasattr(tool_func, 'is_lc_tool') and not hasattr(tool_func, 'name'):
                 # Skip functions not decorated with @tool, or internal/experimental ones
                 if tool_name not in ["create_new_tool", "execute_internal_command", "_check_command_safety"]:
                     logger.warning(f"Tool function '{tool_name}' in TOOL_MAPPING is missing the @tool decorator. Skipping.")
                 continue

            try:
                # Create a partial function that includes the 'cog' instance
                # Langchain agents can often handle partial functions directly.
                # The agent will call this partial, which in turn calls the original tool with 'cog'.
                # The @tool decorator ensures Langchain gets the correct signature from the *original* func.
                tool_with_cog = functools.partial(tool_func, cog)

                # Copy essential attributes from the original decorated tool function to the partial
                # This helps ensure the agent framework recognizes it correctly.
                functools.update_wrapper(tool_with_cog, tool_func)

                # Add the partial function (which now includes cog) to the list
                prepared_tools.append(tool_with_cog)
                logger.debug(f"Prepared tool '{tool_name}' with cog instance bound.")

            except Exception as tool_prep_e:
                 logger.error(f"Error preparing tool '{tool_name}' with functools.partial: {tool_prep_e}", exc_info=True)
                 # Optionally skip this tool

        # --- 3. Prepare Chat History Factory ---
        # Create a partial function for the history factory, binding the cog instance
        chat_history_factory = functools.partial(get_gurt_session_history, cog=cog)

        # --- 4. Define Model Kwargs ---
        # These are passed to the underlying LLM (Gemini)
        model_kwargs = {
            "temperature": 0.75, # Adjust as needed
            "max_output_tokens": 4096, # Adjust based on model and expected output size
            # "safety_settings": STANDARD_SAFETY_SETTINGS, # Pass safety settings if needed
            # "top_k": ...,
            # "top_p": ...,
        }

        # --- 5. Instantiate LangchainAgent ---
        logger.info(f"Instantiating LangchainAgent with model: {selected_model_name}")
        agent = agent_engines.LangchainAgent(
            model=selected_model_name,
            tools=prepared_tools,
            chat_history=chat_history_factory, # Pass the factory function
            prompt=prompt_template, # Pass the constructed prompt template
            model_kwargs=model_kwargs,
            # verbose=True, # Enable for debugging agent steps
            # handle_parsing_errors=True, # Let the agent try to recover from parsing errors
            # max_iterations=10, # Limit tool execution loops
        )

        # --- 6. Format Input Message ---
        # LangchainAgent expects a simple string input.
        # Use format_message utility and combine parts.
        formatted_current_message = format_message(cog, message)
        input_parts = []

        # Add reply context if applicable
        if formatted_current_message.get("is_reply") and formatted_current_message.get("replied_to_author_name"):
            reply_author = formatted_current_message["replied_to_author_name"]
            reply_content = formatted_current_message.get("replied_to_content", "...")
            max_reply_len = 150
            if len(reply_content) > max_reply_len:
                reply_content = reply_content[:max_reply_len] + "..."
            input_parts.append(f"(Replying to {reply_author}: \"{reply_content}\")")

        # Add current message author and content
        input_parts.append(f"{formatted_current_message['author']['display_name']}: {formatted_current_message['content']}")

        # Add mention details
        if formatted_current_message.get("mentioned_users_details"):
            mentions_str = ", ".join([f"{m['display_name']}(id:{m['id']})" for m in formatted_current_message["mentioned_users_details"]])
            input_parts.append(f"(Message Details: Mentions=[{mentions_str}])")

        # Add attachment info (as text description)
        if formatted_current_message.get("attachment_descriptions"):
            attachment_str = " ".join([att['description'] for att in formatted_current_message["attachment_descriptions"]])
            input_parts.append(f"[Attachments: {attachment_str}]")

        final_input_string = "\n".join(input_parts).strip()
        logger.debug(f"Formatted input string for LangchainAgent: {final_input_string[:200]}...")

        # --- 7. Query the Agent ---
        logger.info(f"Querying LangchainAgent for message {message.id}...")
        # The agent handles retries, tool calls, history management internally.
        # We pass the channel_id as the session_id for history persistence.
        # NOTE: agent.query() appears to be synchronous, removed await.
        agent_response = agent.query(
            input=final_input_string,
            config={"configurable": {"session_id": str(channel_id)}}
        )
        # Note: agent.query might raise exceptions on failure.

        elapsed_time = time.monotonic() - start_time
        logger.info(f"LangchainAgent query successful for {request_desc} in {elapsed_time:.2f}s.")
        logger.debug(f"Raw LangchainAgent response: {agent_response}")

        # --- 8. Parse and Validate Output ---
        # The final response should be in the 'output' key
        final_response_text = agent_response.get("output")
        final_parsed_data = parse_and_validate_json_response(
            final_response_text, RESPONSE_SCHEMA['schema'], "final response (LangchainAgent)"
        )

        if final_parsed_data is None:
             logger.error(f"Failed to parse/validate final JSON output from LangchainAgent for {request_desc}. Raw output: {final_response_text}")
             error_message = "Failed to parse/validate final AI JSON response."
             # Create a basic fallback if the bot was mentioned
             replied_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user
             if cog.bot.user.mentioned_in(message) or replied_to_bot:
                 fallback_response = {"should_respond": True, "content": "...", "react_with_emoji": "❓"}

        # --- 9. Log Stats (Simplified) ---
        # LangchainAgent doesn't expose detailed retry/timing stats easily. Log basic success/failure.
        if selected_model_name not in cog.api_stats:
            cog.api_stats[selected_model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
        if final_parsed_data:
            cog.api_stats[selected_model_name]['success'] += 1
        else:
            cog.api_stats[selected_model_name]['failure'] += 1
        cog.api_stats[selected_model_name]['total_time'] += elapsed_time
        cog.api_stats[selected_model_name]['count'] += 1
        # Note: Tool stats logging needs integration within the tool functions themselves or via LangChain callbacks.

    except Exception as e:
        elapsed_time = time.monotonic() - start_time
        error_message = f"Error in get_ai_response (LangchainAgent) for message {message.id}: {type(e).__name__}: {str(e)}"
        logger.error(error_message, exc_info=True)
        final_parsed_data = None # Ensure None on critical error

        # Log failure stat
        if selected_model_name not in cog.api_stats:
            cog.api_stats[selected_model_name] = {'success': 0, 'failure': 0, 'retries': 0, 'total_time': 0.0, 'count': 0}
        cog.api_stats[selected_model_name]['failure'] += 1
        cog.api_stats[selected_model_name]['total_time'] += elapsed_time
        cog.api_stats[selected_model_name]['count'] += 1

    return {
        "final_response": final_parsed_data,
        "error": error_message,
        "fallback_initial": fallback_response # Keep this key for compatibility, though less likely needed
    }


# --- Proactive AI Response Function (Refactored) ---
async def get_proactive_ai_response(cog: 'GurtCog', message: discord.Message, trigger_reason: str) -> Dict[str, Any]:
    """Generates a proactive response based on a specific trigger using LangChain components."""
    if not PROJECT_ID or not LOCATION:
        return {"should_respond": False, "content": None, "react_with_emoji": None, "error": "Google Cloud Project ID or Location not configured"}

    logger.info(f"--- Proactive Response Triggered: {trigger_reason} ---")
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
        # Add recent messages summary using the tool function directly
        try:
            # Ensure get_conversation_summary is called correctly (might need channel_id as string)
            summary_data = await get_conversation_summary(cog, str(channel_id), message_limit=15)
            if summary_data and not summary_data.get("error"):
                planning_context_parts.append(f"Recent Conversation Summary: {summary_data['summary']}")
        except Exception as summary_e:
            logger.error(f"Error getting summary for proactive planning: {summary_e}", exc_info=True)

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
        except Exception as int_e: logger.error(f"Error getting interests for planning: {int_e}", exc_info=True)

        planning_context = "\n".join(planning_context_parts)

        # --- Planning Step (using refactored internal call) ---
        logger.info("Generating proactive response plan...")
        planning_prompt_messages = [
            {"role": "system", "content": "You are Gurt's planning module. Analyze the context and trigger reason to decide if Gurt should respond proactively and, if so, outline a plan (goal, key info, tone). Focus on natural, in-character engagement. Respond ONLY with JSON matching the provided schema."},
            {"role": "user", "content": f"Context:\n{planning_context}\n\nBased on this context and the trigger reason, create a plan for Gurt's proactive response."}
        ]

        plan = await get_internal_ai_json_response( # Call the refactored function
            cog=cog,
            prompt_messages=planning_prompt_messages,
            task_description=f"Proactive Planning ({trigger_reason})",
            response_schema_dict=PROACTIVE_PLAN_SCHEMA['schema'],
            model_name=FALLBACK_MODEL, # Use a potentially faster/cheaper model for planning
            temperature=0.5,
            max_tokens=500 # Increased slightly for planning
        )

        if not plan or not plan.get("should_respond"):
            reason = plan.get('reasoning', 'Planning failed or decided against responding.') if plan else 'Planning failed.'
            logger.info(f"Proactive response aborted by plan: {reason}")
            return {"should_respond": False, "content": None, "react_with_emoji": None, "note": f"Plan: {reason}"}

        logger.info(f"Proactive Plan Generated: Goal='{plan.get('response_goal', 'N/A')}', Reasoning='{plan.get('reasoning', 'N/A')}'")

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

        # --- Call Final LLM API (using direct ChatVertexAI call) ---
        logger.info("Generating final proactive response using direct ChatVertexAI call...")
        final_model = ChatVertexAI(
            model_name=DEFAULT_MODEL,
            temperature=0.8, # Use original proactive temp
            max_output_tokens=200,
            # Pass safety settings if needed, e.g., safety_settings=STANDARD_SAFETY_SETTINGS
        )

        # Construct final messages for the direct call
        final_messages = [
            SystemMessage(content=final_proactive_system_prompt),
            HumanMessage(content=(
                f"Generate the response based on your plan. **CRITICAL: Your response MUST be ONLY the raw JSON object matching this schema:**\n\n"
                f"{json.dumps(RESPONSE_SCHEMA['schema'], indent=2)}\n\n"
                f"**Ensure nothing precedes or follows the JSON.**"
            ))
        ]

        # Invoke the model
        # Add retry logic here if needed, or rely on LangChain's potential built-in retries
        try:
            ai_response: BaseMessage = await final_model.ainvoke(final_messages)
            final_response_text = ai_response.content
            logger.debug(f"Raw proactive generation response content: {final_response_text}")
        except Exception as gen_e:
             logger.error(f"Error invoking final proactive generation model: {gen_e}", exc_info=True)
             raise Exception("Final proactive API call failed.") from gen_e


        # --- Parse and Validate Final Response ---
        final_parsed_data = parse_and_validate_json_response(
            final_response_text, RESPONSE_SCHEMA['schema'], f"final proactive response ({trigger_reason})"
        )

        if final_parsed_data is None:
            logger.error(f"Failed to parse/validate final proactive JSON response for {trigger_reason}. Raw: {final_response_text}")
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
                     logger.info(f"Tracked Gurt participation (proactive) in topic: '{topic}'")


    except Exception as e:
        error_message = f"Error getting proactive AI response for channel {channel_id} ({trigger_reason}): {type(e).__name__}: {str(e)}"
        logger.error(error_message, exc_info=True)
        final_parsed_data = {"should_respond": False, "content": None, "react_with_emoji": None, "error": error_message}

    # Ensure default keys exist
    if final_parsed_data is None: final_parsed_data = {} # Ensure dict exists
    final_parsed_data.setdefault("should_respond", False)
    final_parsed_data.setdefault("content", None)
    final_parsed_data.setdefault("react_with_emoji", None)
    if error_message and "error" not in final_parsed_data:
         final_parsed_data["error"] = error_message

    return final_parsed_data


# --- Internal AI Call for Specific Tasks (Refactored) ---
async def get_internal_ai_json_response(
    cog: 'GurtCog',
    prompt_messages: List[Dict[str, Any]], # Keep OpenAI format for input convenience
    task_description: str,
    response_schema_dict: Dict[str, Any], # Expect schema as dict
    model_name: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 5000,
) -> Optional[Dict[str, Any]]: # Keep return type hint simple
    """
    Makes a direct Vertex AI call using LangChain expecting a specific JSON response format.

    Args:
        cog: The GurtCog instance.
        prompt_messages: List of message dicts (OpenAI format: {'role': 'user'/'system', 'content': '...'}).
        task_description: Description for logging.
        response_schema_dict: The expected JSON output schema as a dictionary.
        model_name: Optional model override.
        temperature: Generation temperature.
        max_tokens: Max output tokens.

    Returns:
        The parsed and validated JSON dictionary if successful, None otherwise.
    """
    if not PROJECT_ID or not LOCATION:
        logger.error(f"Error in get_internal_ai_json_response ({task_description}): GCP Project/Location not set.")
        return None

    final_parsed_data = None
    error_occurred = None
    request_payload_for_logging = {} # For logging
    start_time = time.monotonic()
    selected_model_name = model_name or FALLBACK_MODEL # Use fallback if not specified

    try:
        # --- Convert prompt messages to LangChain format ---
        langchain_messages: List[BaseMessage] = []
        system_instruction_parts = []
        for msg in prompt_messages:
            role = msg.get("role", "user")
            content_value = msg.get("content", "")

            if role == "system":
                system_instruction_parts.append(str(content_value))
                continue # Collect system messages separately

            # --- Process content (string or list with images) ---
            message_content_parts = []
            if isinstance(content_value, str):
                message_content_parts.append({"type": "text", "text": content_value})
            elif isinstance(content_value, list):
                 # Handle multimodal content (assuming format from ProfileUpdater)
                 for part_data in content_value:
                     part_type = part_data.get("type")
                     if part_type == "text":
                         message_content_parts.append({"type": "text", "text": part_data.get("text", "")})
                     elif part_type == "image_data":
                         mime_type = part_data.get("mime_type")
                         base64_data = part_data.get("data")
                         if mime_type and base64_data:
                             # Format for LangChain message content list
                             message_content_parts.append({
                                 "type": "image_url",
                                 "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
                             })
                         else:
                             logger.warning("image_data part missing mime_type or data in internal call.")
                             message_content_parts.append({"type": "text", "text": "(System Note: Invalid image data provided)"})
                     else:
                         logger.warning(f"Unknown part type '{part_type}' in internal prompt message.")
            else:
                 logger.warning(f"Unexpected content type '{type(content_value)}' in internal prompt message.")
                 message_content_parts.append({"type": "text", "text": str(content_value)})


            # Add message to list
            if role == "user":
                langchain_messages.append(HumanMessage(content=message_content_parts))
            elif role == "assistant": # Map assistant to AIMessage
                langchain_messages.append(AIMessage(content=message_content_parts))
            else:
                 logger.warning(f"Unsupported role '{role}' in internal prompt message, treating as user.")
                 langchain_messages.append(HumanMessage(content=message_content_parts))


        # Prepend combined system instruction if any
        if system_instruction_parts:
            full_system_instruction = "\n\n".join(system_instruction_parts)
            langchain_messages.insert(0, SystemMessage(content=full_system_instruction))

        # Add the critical JSON instruction to the last message
        json_instruction_content = (
            f"\n\n**CRITICAL: Your response MUST consist *only* of the raw JSON object itself, matching this schema:**\n"
            f"{json.dumps(response_schema_dict, indent=2)}\n"
            f"**Ensure nothing precedes or follows the JSON.**"
        )
        if langchain_messages and isinstance(langchain_messages[-1], HumanMessage):
             # Append instruction to the last HumanMessage's content
             last_msg_content = langchain_messages[-1].content
             if isinstance(last_msg_content, str):
                 langchain_messages[-1].content += json_instruction_content
             elif isinstance(last_msg_content, list):
                  # Append as a new text part
                  last_msg_content.append({"type": "text", "text": json_instruction_content})
             else:
                  logger.warning("Could not append JSON instruction to last message content (unexpected type).")
                  # Add as a new message instead?
                  langchain_messages.append(HumanMessage(content=json_instruction_content))

        else:
             # If no messages or last wasn't Human, add as new HumanMessage
             langchain_messages.append(HumanMessage(content=json_instruction_content))


        # --- Initialize Model ---
        # Use ChatVertexAI for direct interaction
        chat_model = ChatVertexAI(
            model_name=selected_model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
            # Pass safety settings if needed
            # safety_settings=STANDARD_SAFETY_SETTINGS
            # Consider adding .with_structured_output(response_schema_dict) if supported and reliable
            # for Vertex AI integration. This simplifies prompting but might have limitations.
            # For now, rely on prompt instructions.
        )

        # Prepare payload for logging (approximate)
        request_payload_for_logging = {
            "model": selected_model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [ # Simplified representation for logging
                 {"role": type(m).__name__, "content": str(m.content)[:200] + "..."} # Log type and truncated content
                 for m in langchain_messages
             ],
             "response_schema": response_schema_dict # Log the target schema
         }
        logger.debug(f"--- Request payload for {task_description} ---\n{json.dumps(request_payload_for_logging, indent=2, default=str)}\n--- End Request payload ---")


        # --- Call API ---
        # Add retry logic here if needed, or rely on LangChain's potential built-in retries
        # Simple retry example:
        last_exception = None
        for attempt in range(API_RETRY_ATTEMPTS + 1):
            try:
                logger.info(f"Invoking ChatVertexAI for {task_description} (Attempt {attempt + 1}/{API_RETRY_ATTEMPTS + 1})...")
                ai_response: BaseMessage = await chat_model.ainvoke(langchain_messages)
                final_response_text = ai_response.content
                logger.debug(f"--- Raw response content for {task_description} ---\n{final_response_text}\n--- End Raw response content ---")
                last_exception = None # Clear exception on success
                break # Exit retry loop on success
            except (google_exceptions.ResourceExhausted, google_exceptions.InternalServerError, google_exceptions.ServiceUnavailable) as e:
                last_exception = e
                logger.warning(f"Retryable API error for {task_description} (Attempt {attempt+1}): {type(e).__name__}: {e}")
                if attempt < API_RETRY_ATTEMPTS:
                    wait_time = API_RETRY_DELAY * (2 ** attempt)
                    logger.info(f"Waiting {wait_time:.2f}s before retrying...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"API request failed for {task_description} after {attempt + 1} attempts.")
                    break # Max retries reached
            except Exception as e: # Catch other errors (non-retryable by default)
                last_exception = e
                logger.error(f"Non-retryable error invoking ChatVertexAI for {task_description}: {type(e).__name__}: {e}", exc_info=True)
                final_response_text = None
                break # Exit loop on non-retryable error

        if last_exception:
             raise Exception(f"Internal API call failed for {task_description} after retries.") from last_exception
        if final_response_text is None:
             raise Exception(f"Internal API call for {task_description} resulted in no content.")


        # --- Parse and Validate ---
        final_parsed_data = parse_and_validate_json_response(
            final_response_text, response_schema_dict, f"internal task ({task_description})"
        )

        if final_parsed_data is None:
            logger.error(f"Internal task '{task_description}' failed JSON validation. Raw response: {final_response_text}")
            # No re-prompting for internal tasks, just return None

    except Exception as e:
        logger.error(f"Error in get_internal_ai_json_response ({task_description}): {type(e).__name__}: {e}", exc_info=True)
        error_occurred = e # Capture the exception object
        final_parsed_data = None
