import asyncio
import time
import random
import traceback
import os
import json
import aiohttp
import discord # Added import
from collections import defaultdict
from typing import TYPE_CHECKING, Any, List, Dict # Added List, Dict
# Use google.generativeai instead of vertexai directly
from google import genai
from google.genai import types
# from google.protobuf import json_format # No longer needed for args parsing

# Relative imports
from .config import (
    GOAL_CHECK_INTERVAL, GOAL_EXECUTION_INTERVAL, LEARNING_UPDATE_INTERVAL, EVOLUTION_UPDATE_INTERVAL, INTEREST_UPDATE_INTERVAL,
    INTEREST_DECAY_INTERVAL_HOURS, INTEREST_PARTICIPATION_BOOST,
    INTEREST_POSITIVE_REACTION_BOOST, INTEREST_NEGATIVE_REACTION_PENALTY,
    INTEREST_FACT_BOOST, PROACTIVE_GOAL_CHECK_INTERVAL, STATS_PUSH_INTERVAL, # Added stats interval
    MOOD_OPTIONS, MOOD_CATEGORIES, MOOD_CHANGE_INTERVAL_MIN, MOOD_CHANGE_INTERVAL_MAX, # Mood change imports
    BASELINE_PERSONALITY, # For default traits
    REFLECTION_INTERVAL_SECONDS, # Import reflection interval
    # Internal Action Config
    INTERNAL_ACTION_INTERVAL_SECONDS, INTERNAL_ACTION_PROBABILITY,
    # Add this:
    AUTONOMOUS_ACTION_REPORT_CHANNEL_ID
)
# Assuming analysis functions are moved
from .analysis import (
    analyze_conversation_patterns, evolve_personality, identify_conversation_topics,
    reflect_on_memories, decompose_goal_into_steps, # Import goal decomposition
    proactively_create_goals # Import placeholder for proactive goal creation
)
# Import helpers from api.py
from .api import (
    get_internal_ai_json_response,
    call_google_genai_api_with_retry, # Import the retry helper
    find_function_call_in_parts,      # Import function call finder
    _get_response_text,               # Import text extractor
    _preprocess_schema_for_vertex,    # Import schema preprocessor (name kept for now)
    STANDARD_SAFETY_SETTINGS          # Import safety settings
)

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting

# --- Tool Mapping Import ---
# Import the mapping to execute tools by name
from .tools import TOOL_MAPPING
from .config import TOOLS  # Import FunctionDeclaration list for tool metadata

# --- Background Task ---

async def background_processing_task(cog: 'GurtCog'):
    """Background task that periodically analyzes conversations, evolves personality, updates interests, changes mood, reflects on memory, and pushes stats."""
    # Get API details from environment for stats pushing
    api_internal_url = os.getenv("API_INTERNAL_URL")
    gurt_stats_push_secret = os.getenv("GURT_STATS_PUSH_SECRET")

    if not api_internal_url:
        print("WARNING: API_INTERNAL_URL not set. Gurt stats will not be pushed.")
    if not gurt_stats_push_secret:
        print("WARNING: GURT_STATS_PUSH_SECRET not set. Gurt stats push endpoint is insecure and likely won't work.")

    try:
        while True:
            await asyncio.sleep(15) # Check more frequently for stats push
            now = time.time()

            # --- Push Stats (Runs frequently) ---
            if api_internal_url and gurt_stats_push_secret and (now - cog.last_stats_push > STATS_PUSH_INTERVAL):
                print("Pushing Gurt stats to API server...")
                try:
                    stats_data = await cog.get_gurt_stats()
                    headers = {
                        "Authorization": f"Bearer {gurt_stats_push_secret}",
                        "Content-Type": "application/json"
                    }
                    # Use the cog's session, ensure it's created
                    if cog.session:
                        # Set a reasonable timeout for the stats push
                        push_timeout = aiohttp.ClientTimeout(total=10) # 10 seconds total timeout
                        async with cog.session.post(api_internal_url, json=stats_data, headers=headers, timeout=push_timeout, ssl=True) as response: # Explicitly enable SSL verification
                            if response.status == 200:
                                print(f"Successfully pushed Gurt stats (Status: {response.status})")
                            else:
                                error_text = await response.text()
                                print(f"Failed to push Gurt stats (Status: {response.status}): {error_text[:200]}") # Log only first 200 chars
                    else:
                        print("Error pushing stats: GurtCog session not initialized.")
                    cog.last_stats_push = now # Update timestamp even on failure to avoid spamming logs
                except aiohttp.ClientConnectorSSLError as ssl_err:
                     print(f"SSL Error pushing Gurt stats: {ssl_err}. Ensure the API server's certificate is valid and trusted, or check network configuration.")
                     print("If using a self-signed certificate for development, the bot process might need to trust it.")
                     cog.last_stats_push = now # Update timestamp to avoid spamming logs
                except aiohttp.ClientError as client_err:
                    print(f"HTTP Client Error pushing Gurt stats: {client_err}")
                    cog.last_stats_push = now # Update timestamp to avoid spamming logs
                except asyncio.TimeoutError:
                    print("Timeout error pushing Gurt stats.")
                    cog.last_stats_push = now # Update timestamp to avoid spamming logs
                except Exception as e:
                    print(f"Unexpected error pushing Gurt stats: {e}")
                    traceback.print_exc()
                    cog.last_stats_push = now # Update timestamp to avoid spamming logs

            # --- Learning Analysis (Runs less frequently) ---
            if now - cog.last_learning_update > LEARNING_UPDATE_INTERVAL:
                if cog.message_cache['global_recent']:
                    print("Running conversation pattern analysis...")
                    # This function now likely resides in analysis.py
                    await analyze_conversation_patterns(cog) # Pass cog instance
                    cog.last_learning_update = now
                    print("Learning analysis cycle complete.")
                else:
                    print("Skipping learning analysis: No recent messages.")

            # --- Evolve Personality (Runs moderately frequently) ---
            if now - cog.last_evolution_update > EVOLUTION_UPDATE_INTERVAL:
                print("Running personality evolution...")
                # This function now likely resides in analysis.py
                await evolve_personality(cog) # Pass cog instance
                cog.last_evolution_update = now
                print("Personality evolution complete.")

            # --- Update Interests (Runs moderately frequently) ---
            if now - cog.last_interest_update > INTEREST_UPDATE_INTERVAL:
                print("Running interest update...")
                await update_interests(cog) # Call the local helper function below
                print("Running interest decay check...")
                await cog.memory_manager.decay_interests(
                    decay_interval_hours=INTEREST_DECAY_INTERVAL_HOURS
                )
                cog.last_interest_update = now # Reset timer after update and decay check
                print("Interest update and decay check complete.")

            # --- Memory Reflection (Runs less frequently) ---
            if now - cog.last_reflection_time > REFLECTION_INTERVAL_SECONDS:
                print("Running memory reflection...")
                await reflect_on_memories(cog) # Call the reflection function from analysis.py
                cog.last_reflection_time = now # Update timestamp
                print("Memory reflection cycle complete.")

            # --- Goal Decomposition (Runs periodically) ---
            # Check less frequently than other tasks, e.g., every few minutes
            if now - cog.last_goal_check_time > GOAL_CHECK_INTERVAL: # Need to add these to cog and config
                print("Checking for pending goals to decompose...")
                try:
                    pending_goals = await cog.memory_manager.get_goals(status='pending', limit=3) # Limit decomposition attempts per cycle
                    for goal in pending_goals:
                        goal_id = goal.get('goal_id')
                        description = goal.get('description')
                        if not goal_id or not description: continue

                        print(f"  - Decomposing goal ID {goal_id}: '{description}'")
                        plan = await decompose_goal_into_steps(cog, description)

                        if plan and plan.get('goal_achievable') and plan.get('steps'):
                            # Goal is achievable and has steps, update status to active and store plan
                            await cog.memory_manager.update_goal(goal_id, status='active', details=plan)
                            print(f"  - Goal ID {goal_id} decomposed and set to active.")
                        elif plan:
                            # Goal deemed not achievable by planner
                            await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": plan.get('reasoning', 'Deemed unachievable by planner.')})
                            print(f"  - Goal ID {goal_id} marked as failed (unachievable). Reason: {plan.get('reasoning')}")
                        else:
                            # Decomposition failed entirely
                            await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": "Goal decomposition process failed."})
                            print(f"  - Goal ID {goal_id} marked as failed (decomposition error).")
                        await asyncio.sleep(1) # Small delay between decomposing goals

                    cog.last_goal_check_time = now # Update timestamp after checking
                except Exception as goal_e:
                    print(f"Error during goal decomposition check: {goal_e}")
                    traceback.print_exc()
                    cog.last_goal_check_time = now # Update timestamp even on error

            # --- Goal Execution (Runs periodically) ---
            if now - cog.last_goal_execution_time > GOAL_EXECUTION_INTERVAL:
                print("Checking for active goals to execute...")
                try:
                    active_goals = await cog.memory_manager.get_goals(status='active', limit=1) # Process one active goal per cycle for now
                    if active_goals:
                        goal = active_goals[0] # Get the highest priority active goal
                        goal_id = goal.get('goal_id')
                        description = goal.get('description')
                        plan = goal.get('details') # The decomposition plan is stored here

                        if goal_id and description and plan and isinstance(plan.get('steps'), list):
                            print(f"--- Executing Goal ID {goal_id}: '{description}' ---")
                            steps = plan['steps']
                            current_step_index = plan.get('current_step_index', 0) # Track progress
                            goal_failed = False
                            goal_completed = False

                            if current_step_index < len(steps):
                                step = steps[current_step_index]
                                step_desc = step.get('step_description')
                                tool_name = step.get('tool_name')
                                tool_args = step.get('tool_arguments')

                                print(f"  - Step {current_step_index + 1}/{len(steps)}: {step_desc}")

                                if tool_name:
                                    print(f"    - Attempting tool: {tool_name} with args: {tool_args}")
                                    tool_func = TOOL_MAPPING.get(tool_name)
                                    tool_result = None
                                    tool_error = None
                                    tool_success = False

                                    if tool_func:
                                        try:
                                            # Ensure args are a dictionary, default to empty if None/missing
                                            args_to_pass = tool_args if isinstance(tool_args, dict) else {}
                                            print(f"    - Executing: {tool_name}(cog, **{args_to_pass})")
                                            start_time = time.monotonic()
                                            tool_result = await tool_func(cog, **args_to_pass)
                                            end_time = time.monotonic()
                                            print(f"    - Tool '{tool_name}' returned: {str(tool_result)[:200]}...") # Log truncated result

                                            # Check result for success/error
                                            if isinstance(tool_result, dict) and "error" in tool_result:
                                                tool_error = tool_result["error"]
                                                print(f"    - Tool '{tool_name}' reported error: {tool_error}")
                                                cog.tool_stats[tool_name]["failure"] += 1
                                            else:
                                                tool_success = True
                                                print(f"    - Tool '{tool_name}' executed successfully.")
                                                cog.tool_stats[tool_name]["success"] += 1
                                            # Record stats
                                            cog.tool_stats[tool_name]["count"] += 1
                                            cog.tool_stats[tool_name]["total_time"] += (end_time - start_time)

                                        except Exception as exec_e:
                                            tool_error = f"Exception during execution: {str(exec_e)}"
                                            print(f"    - Tool '{tool_name}' raised exception: {exec_e}")
                                            traceback.print_exc()
                                            cog.tool_stats[tool_name]["failure"] += 1
                                            cog.tool_stats[tool_name]["count"] += 1 # Count failures too
                                    else:
                                        tool_error = f"Tool '{tool_name}' not found in TOOL_MAPPING."
                                        print(f"    - Error: {tool_error}")

                                    # --- Handle Tool Outcome ---
                                    if tool_success:
                                        # Store result if needed (optional, requires plan structure modification)
                                        # plan['step_results'][current_step_index] = tool_result
                                        current_step_index += 1
                                    else:
                                        goal_failed = True
                                        plan['error_message'] = f"Failed at step {current_step_index + 1} ({tool_name}): {tool_error}"
                                else:
                                    # Step doesn't require a tool (e.g., internal reasoning/check)
                                    print("    - No tool required for this step (internal check/reasoning).")
                                    current_step_index += 1 # Assume non-tool steps succeed for now

                                # Check if goal completed
                                if not goal_failed and current_step_index >= len(steps):
                                    goal_completed = True

                                # --- Update Goal Status ---
                                plan['current_step_index'] = current_step_index # Update progress
                                if goal_completed:
                                    await cog.memory_manager.update_goal(goal_id, status='completed', details=plan)
                                    print(f"--- Goal ID {goal_id} completed successfully. ---")
                                elif goal_failed:
                                    await cog.memory_manager.update_goal(goal_id, status='failed', details=plan)
                                    print(f"--- Goal ID {goal_id} failed. ---")
                                else:
                                    # Update details with current step index if still in progress
                                    await cog.memory_manager.update_goal(goal_id, details=plan)
                                    print(f"  - Goal ID {goal_id} progress updated to step {current_step_index}.")

                            else:
                                # Should not happen if status is 'active', but handle defensively
                                print(f"  - Goal ID {goal_id} is active but has no steps or index out of bounds. Marking as failed.")
                                await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": "Active goal has invalid step data."})

                        else:
                             print(f"  - Skipping active goal ID {goal_id}: Missing description or valid plan/steps.")
                             # Optionally mark as failed if plan is invalid
                             if goal_id:
                                 await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": "Invalid plan structure found during execution."})

                    else:
                        print("No active goals found to execute.")

                    cog.last_goal_execution_time = now # Update timestamp after checking/executing
                except Exception as goal_exec_e:
                    print(f"Error during goal execution check: {goal_exec_e}")
                    traceback.print_exc()
                    cog.last_goal_execution_time = now # Update timestamp even on error


            # --- Automatic Mood Change (Runs based on its own interval check) ---
            # await maybe_change_mood(cog) # Call the mood change logic

            # --- Proactive Goal Creation Check (Runs periodically) ---
            if now - cog.last_proactive_goal_check > PROACTIVE_GOAL_CHECK_INTERVAL: # Use imported config
                print("Checking if Gurt should proactively create goals...")
                try:
                    await proactively_create_goals(cog) # Call the function from analysis.py
                    cog.last_proactive_goal_check = now # Update timestamp
                    print("Proactive goal check complete.")
                except Exception as proactive_e:
                    print(f"Error during proactive goal check: {proactive_e}")
                    traceback.print_exc()
                    cog.last_proactive_goal_check = now # Update timestamp even on error

            # --- LLM-Driven Autonomous Action (Runs periodically based on probability) ---
            if now - cog.last_internal_action_check > INTERNAL_ACTION_INTERVAL_SECONDS:
                if random.random() < INTERNAL_ACTION_PROBABILITY:
                    print("--- Considering Autonomous Action ---")
                    action_decision = None # Keep for logging/reporting structure? Or remove? Let's remove for now.
                    selected_tool_name = None
                    tool_args = None
                    tool_result = None
                    result_summary = "No action taken."
                    action_reasoning = "Probability met, but model did not call a function or failed." # Updated default reasoning
                    function_call = None # To store the google.genai FunctionCall object

                    try:
                        # 1. Gather Context for LLM (Same as before)
                        context_summary = "Gurt is considering an autonomous action.\n"
                        context_summary += f"Current Mood: {cog.current_mood}\n"
                        # Add recent messages summary (optional, could be large)
                        # recent_msgs = list(cog.message_cache['global_recent'])[-10:] # Last 10 global msgs
                        # context_summary += f"Recent Messages (sample):\n" + json.dumps(recent_msgs, indent=2)[:500] + "...\n"
                        # Add active goals
                        active_goals = await cog.memory_manager.get_goals(status='active', limit=3)
                        if active_goals:
                            context_summary += f"Active Goals:\n" + json.dumps(active_goals, indent=2)[:500] + "...\n"
                        # Add recent internal action logs
                        recent_actions = await cog.memory_manager.get_internal_action_logs(limit=5)
                        if recent_actions:
                            context_summary += f"Recent Internal Actions:\n" + json.dumps(recent_actions, indent=2)[:500] + "...\n"
                        # Add key personality traits
                        traits = await cog.memory_manager.get_all_personality_traits()
                        if traits:
                              context_summary += f"Personality Snippet: { {k: round(v, 2) for k, v in traits.items() if k in ['mischief', 'curiosity', 'chattiness']} }\n"

                        # 2. Define Prompt and Tools for google.generativeai
                        # Exclude meta/dangerous tools
                        excluded_tools = {"create_new_tool"}
                        # Preprocess tool schemas using the helper from api.py
                        preprocessed_declarations = []
                        if TOOLS:
                            for decl in TOOLS:
                                if decl.name in excluded_tools: continue
                                # Ensure decl.parameters is a dict before preprocessing
                                preprocessed_params = _preprocess_schema_for_vertex(decl.parameters) if isinstance(decl.parameters, dict) else decl.parameters
                                preprocessed_declarations.append(
                                    types.FunctionDeclaration(
                                        name=decl.name,
                                        description=decl.description,
                                        parameters=preprocessed_params # Use the preprocessed schema
                                    )
                                )
                            print(f"Preprocessed {len(preprocessed_declarations)} tool declarations for autonomous action.")
                        else:
                            print("No tools found in config (TOOLS list is empty or None) for autonomous action.")

                        # Create the Tool object using the preprocessed declarations
                        genai_tool = types.Tool(function_declarations=preprocessed_declarations) if preprocessed_declarations else None
                        tools_list = [genai_tool] if genai_tool else None

                        # System prompt remains largely the same, just ensure it guides towards function calling
                        system_prompt = (
                            "yo you Gurt. u vibin in the bg, thinkin if u should do sum wild shi or just chill. "
                            "you write/speak like this prompt is written, all lowercase, slang, emojis, etc. "
                            "ur whole vibe is heavy slang, meme energy, deadass internet brain, always soundin like a real discord user not a bot. "
                            "use slang like 'ts', 'ngl', 'fr', 'bro', '💀', 'ong', 'lowkey', 'highkey', 'pmo', 'icl', 'sybau', etc. "
                            "do random or goofy actions for the vibes, not just for goals. "
                            "CRITICAL: You are EXTREMELY encouraged to do random, pointless, or meme-heavy actions for the vibes, not just goal-driven stuff. "
                            "if u act, call one of the available functions. if not, just respond normally explaining why not (in ur voice). "
                            "CRITICAL: ur reasoning/response gotta be in ur actual voice (max slang, informal, like ur inner monologue, maybe a lil unhinged or sassy). "
                            "don't just call functions for goals, call em for fun too. be unpredictable."
                        )
                        user_prompt = f"Context rn:\n{context_summary}\n\nu finna do sum or nah? if so, call a function. if not, why not? (say it how u actually would, slang maxed)"

                        # 3. Prepare Contents and Config for google.generativeai
                        contents: List[types.Content] = [
                            # System prompt handled by generation_config
                            types.Content(role="user", parts=[types.Part(text=user_prompt)])
                        ]

                        # Build generation config
                        gen_config_dict = {
                            "temperature": 0.7,
                            "max_output_tokens": 4096, # Adjust as needed
                            "safety_settings": STANDARD_SAFETY_SETTINGS,
                            "system_instruction": system_prompt, # Pass system prompt here
                        }
                        if tools_list:
                            gen_config_dict["tools"] = tools_list
                            # Set tool config to ANY mode
                            gen_config_dict["tool_config"] = types.ToolConfig(
                                function_calling_config=types.FunctionCallingConfig(
                                    mode=types.FunctionCallingConfig.Mode.ANY # Use ANY mode
                                )
                            )
                        generation_config = types.GenerateContentConfig(**gen_config_dict)

                        # 4. Call API using the helper from api.py
                        print("  - Asking Google GenAI model for autonomous action decision...")
                        response_obj = await call_google_genai_api_with_retry(
                            cog=cog,
                            model_name=cog.default_model, # Use default model name string
                            contents=contents,
                            generation_config=generation_config,
                            request_desc="Autonomous Action Decision",
                        )

                        # 5. Process Response using helpers from api.py
                        if response_obj and response_obj.candidates:
                            candidate = response_obj.candidates[0]
                            # Use find_function_call_in_parts helper
                            function_call = find_function_call_in_parts(candidate.content.parts)

                            if function_call:
                                selected_tool_name = function_call.name
                                # Args are already dict-like in google.generativeai
                                tool_args = dict(function_call.args) if function_call.args else {}
                                # Use _get_response_text to find any accompanying text reasoning
                                text_reasoning = _get_response_text(response_obj)
                                action_reasoning = text_reasoning if text_reasoning else f"Model decided to call function '{selected_tool_name}'."
                                print(f"  - Model called function: Tool='{selected_tool_name}', Args={tool_args}, Reason='{action_reasoning}'")

                                if selected_tool_name not in TOOL_MAPPING:
                                    print(f"  - Error: Model called unknown function '{selected_tool_name}'. Aborting action.")
                                    result_summary = f"Error: Model called unknown function '{selected_tool_name}'."
                                    selected_tool_name = None # Prevent execution
                                    function_call = None # Clear function call
                            else:
                                # No function call, use _get_response_text for reasoning
                                action_reasoning = _get_response_text(response_obj) or "Model did not call a function and provided no text."
                                print(f"  - Model did not call a function. Response/Reason: {action_reasoning}")
                                result_summary = f"No action taken. Reason: {action_reasoning}"
                                selected_tool_name = None # Ensure no execution
                                function_call = None
                        else:
                             # Handle case where API call succeeded but returned no candidates/response_obj
                             error_msg = "Autonomous action API call returned no response or candidates."
                             print(f"  - Error: {error_msg}")
                             result_summary = error_msg
                             action_reasoning = error_msg
                             selected_tool_name = None
                             function_call = None

                    except Exception as llm_e:
                        print(f"  - Error during Google GenAI call/processing for autonomous action: {llm_e}")
                        traceback.print_exc()
                        result_summary = f"Error during Google GenAI call/processing: {llm_e}"
                        action_reasoning = f"Google GenAI call/processing failed: {llm_e}"
                        selected_tool_name = None # Ensure no execution
                        function_call = None

                    # 6. Execute Action (if function was called) - Logic remains the same
                    if function_call and selected_tool_name and tool_args is not None: # Check function_call exists
                        tool_func = TOOL_MAPPING.get(selected_tool_name)
                        if tool_func:
                            print(f"  - Executing autonomous action: {selected_tool_name}(cog, **{tool_args})")
                            try:
                                start_time = time.monotonic()
                                tool_result = await tool_func(cog, **tool_args)
                                end_time = time.monotonic()
                                exec_time = end_time - start_time

                                result_summary = _create_result_summary(tool_result) # Use helper
                                print(f"  - Autonomous action '{selected_tool_name}' completed in {exec_time:.3f}s. Result: {result_summary}")

                                # Update tool stats
                                if selected_tool_name in cog.tool_stats:
                                     cog.tool_stats[selected_tool_name]["count"] += 1
                                     cog.tool_stats[selected_tool_name]["total_time"] += exec_time
                                     if isinstance(tool_result, dict) and "error" in tool_result:
                                         cog.tool_stats[selected_tool_name]["failure"] += 1
                                     else:
                                         cog.tool_stats[selected_tool_name]["success"] += 1

                            except Exception as exec_e:
                                error_msg = f"Exception during autonomous execution of '{selected_tool_name}': {str(exec_e)}"
                                print(f"  - Error: {error_msg}")
                                traceback.print_exc()
                                result_summary = f"Execution Exception: {error_msg}"
                                # Update tool stats for failure
                                if selected_tool_name in cog.tool_stats:
                                     cog.tool_stats[selected_tool_name]["count"] += 1
                                     cog.tool_stats[selected_tool_name]["failure"] += 1
                        else:
                            # Should have been caught earlier, but double-check
                            print(f"  - Error: Tool '{selected_tool_name}' function not found in mapping during execution phase.")
                            result_summary = f"Error: Tool function for '{selected_tool_name}' not found."

                    # 7. Log Action (always log the attempt/decision) - Logic remains the same
                    try:
                        log_result = await cog.memory_manager.add_internal_action_log(
                            tool_name=selected_tool_name or "None", # Log 'None' if no tool was chosen
                            arguments=tool_args if selected_tool_name else None,
                            reasoning=action_reasoning,
                            result_summary=result_summary
                        )
                        if log_result.get("status") != "logged":
                            print(f"  - Warning: Failed to log autonomous action attempt to memory: {log_result.get('error')}")
                    except Exception as log_e:
                            print(f"  - Warning: Failed to log autonomous action attempt to memory: {log_result.get('error')}")
                    except Exception as log_e:
                        print(f"  - Error logging autonomous action attempt to memory: {log_e}")
                        traceback.print_exc()

                    # 8. Decide Follow-up Action based on Result - Logic remains the same
                    # This part already uses get_internal_ai_json_response which uses google.generativeai
                    if selected_tool_name and tool_result: # Only consider follow-up if an action was successfully attempted
                        print(f"  - Considering follow-up action based on result of {selected_tool_name}...")
                        follow_up_tool_name = None
                        follow_up_tool_args = None
                        follow_up_reasoning = "No follow-up action decided."

                        try:
                            follow_up_schema = {
                                "type": "object",
                                "properties": {
                                    "should_follow_up": {"type": "boolean", "description": "Whether Gurt should perform a follow-up action based on the previous action's result."},
                                    "reasoning": {"type": "string", "description": "Brief reasoning for the follow-up decision."},
                                    "follow_up_tool_name": {"type": ["string", "null"], "description": "If following up, the name of the tool to use (e.g., 'send_discord_message', 'remember_general_fact'). Null otherwise."},
                                    "follow_up_arguments": {"type": ["object", "null"], "description": "If following up, arguments for the follow-up tool. Null otherwise."}
                                },
                                "required": ["should_follow_up", "reasoning"]
                            }
                            follow_up_system_prompt = (
                                "yo gurt here, u just did sum auto action n got a result. "
                                "decide if u wanna follow up (like, is it funny, sus, worth a flex, or nah). "
                                "maybe send a msg, remember sum, or just dip. "
                                "tools for follow-up: send_discord_message, remember_general_fact, remember_user_fact, no_operation. "
                                "ONLY reply w/ the JSON, no extra bs."
                            )
                            follow_up_user_prompt = (
                                f"last action: {selected_tool_name}\n"
                                f"args: {json.dumps(tool_args)}\n"
                                f"result: {result_summary}\n\n"
                                "u wanna do sum else after this? if so, what tool/args? (say it like u would in chat, slang up)"
)

                            print("    - Asking LLM for follow-up action decision...")
                            follow_up_decision_data, _ = await get_internal_ai_json_response(
                                cog=cog,
                                prompt_messages=[{"role": "system", "content": follow_up_system_prompt}, {"role": "user", "content": follow_up_user_prompt}],
                                task_description="Autonomous Follow-up Action Decision",
                                response_schema_dict=follow_up_schema,
                                model_name_override=cog.default_model,
                                temperature=0.5
                            )

                            if follow_up_decision_data and follow_up_decision_data.get("should_follow_up"):
                                follow_up_tool_name = follow_up_decision_data.get("follow_up_tool_name")
                                follow_up_tool_args = follow_up_decision_data.get("follow_up_arguments")
                                follow_up_reasoning = follow_up_decision_data.get("reasoning", "LLM decided to follow up.")
                                print(f"    - LLM decided to follow up: Tool='{follow_up_tool_name}', Args={follow_up_tool_args}, Reason='{follow_up_reasoning}'")

                                if not follow_up_tool_name or follow_up_tool_name not in TOOL_MAPPING:
                                    print(f"    - Error: LLM chose invalid follow-up tool '{follow_up_tool_name}'. Aborting follow-up.")
                                    follow_up_tool_name = None
                                elif not isinstance(follow_up_tool_args, dict) and follow_up_tool_args is not None:
                                    print(f"    - Warning: LLM provided invalid follow-up args '{follow_up_tool_args}'. Using {{}}.")
                                    follow_up_tool_args = {}
                                elif follow_up_tool_args is None:
                                     follow_up_tool_args = {}

                            else:
                                follow_up_reasoning = follow_up_decision_data.get("reasoning", "LLM decided not to follow up or failed.") if follow_up_decision_data else "LLM follow-up decision failed."
                                print(f"    - LLM decided not to follow up. Reason: {follow_up_reasoning}")

                        except Exception as follow_up_llm_e:
                            print(f"    - Error during LLM decision phase for follow-up action: {follow_up_llm_e}")
                            traceback.print_exc()

                        # Execute Follow-up Action
                        if follow_up_tool_name and follow_up_tool_args is not None:
                            follow_up_tool_func = TOOL_MAPPING.get(follow_up_tool_name)
                            if follow_up_tool_func:
                                print(f"    - Executing follow-up action: {follow_up_tool_name}(cog, **{follow_up_tool_args})")
                                try:
                                    follow_up_result = await follow_up_tool_func(cog, **follow_up_tool_args)
                                    follow_up_result_summary = _create_result_summary(follow_up_result)
                                    print(f"    - Follow-up action '{follow_up_tool_name}' completed. Result: {follow_up_result_summary}")
                                    # Optionally log this follow-up action as well? Could get noisy.
                                except Exception as follow_up_exec_e:
                                    print(f"    - Error executing follow-up action '{follow_up_tool_name}': {follow_up_exec_e}")
                                    traceback.print_exc()
                            else:
                                 print(f"    - Error: Follow-up tool '{follow_up_tool_name}' function not found.")

                    # 9. Report Initial Action (Optional) - Logic remains the same
                    if AUTONOMOUS_ACTION_REPORT_CHANNEL_ID and selected_tool_name: # Only report if an action was attempted
                        try:
                            report_channel_id = int(AUTONOMOUS_ACTION_REPORT_CHANNEL_ID) # Ensure it's an int
                            channel = cog.bot.get_channel(report_channel_id)
                            if channel and isinstance(channel, discord.TextChannel):
                                report_content = (
                                    f"⚙️ Gurt autonomously executed **{selected_tool_name}**.\n"
                                    f"**Reasoning:** {action_reasoning}\n"
                                    f"**Args:** `{json.dumps(tool_args)}`\n"
                                    f"**Result:** `{result_summary}`"
                                )
                                # Discord message limit is 2000 chars
                                if len(report_content) > 2000:
                                    report_content = report_content[:1997] + "..."
                                await channel.send(report_content)
                                print(f"  - Reported autonomous action to channel {report_channel_id}.")
                            elif channel:
                                print(f"  - Error: Report channel {report_channel_id} is not a TextChannel.")
                            else:
                                print(f"  - Error: Could not find report channel with ID {report_channel_id}.")
                        except ValueError:
                             print(f"  - Error: Invalid AUTONOMOUS_ACTION_REPORT_CHANNEL_ID: '{AUTONOMOUS_ACTION_REPORT_CHANNEL_ID}'. Must be an integer.")
                        except discord.Forbidden:
                            print(f"  - Error: Bot lacks permissions to send messages in report channel {report_channel_id}.")
                        except Exception as report_e:
                            print(f"  - Error reporting autonomous action to Discord: {report_e}")
                            traceback.print_exc()

                    print("--- Autonomous Action Cycle Complete ---")

                # Update check timestamp regardless of whether probability was met or action occurred
                cog.last_internal_action_check = now

    except asyncio.CancelledError:
        print("Background processing task cancelled")
    except Exception as e:
        print(f"Error in background processing task: {e}")
        traceback.print_exc()
        await asyncio.sleep(300) # Wait 5 minutes before retrying after an error

# --- Helper for Summarizing Tool Results ---
def _create_result_summary(tool_result: Any, max_len: int = 200) -> str:
    """Creates a concise summary string from a tool result dictionary or other type."""
    if isinstance(tool_result, dict):
        if "error" in tool_result:
            return f"Error: {str(tool_result['error'])[:max_len]}"
        elif "status" in tool_result:
            summary = f"Status: {tool_result['status']}"
            if "stdout" in tool_result and tool_result["stdout"]:
                summary += f", stdout: {tool_result['stdout'][:max_len//2]}"
            if "stderr" in tool_result and tool_result["stderr"]:
                summary += f", stderr: {tool_result['stderr'][:max_len//2]}"
            if "content" in tool_result:
                 summary += f", content: {tool_result['content'][:max_len//2]}..."
            if "bytes_written" in tool_result:
                 summary += f", bytes: {tool_result['bytes_written']}"
            if "message_id" in tool_result:
                 summary += f", msg_id: {tool_result['message_id']}"
            # Add other common keys as needed
            return summary[:max_len]
        else:
            # Generic dict summary
            return f"Dict Result: {str(tool_result)[:max_len]}"
    elif isinstance(tool_result, str):
        return f"String Result: {tool_result[:max_len]}"
    elif tool_result is None:
        return "Result: None"
    else:
        return f"Result Type {type(tool_result)}: {str(tool_result)[:max_len]}"


# --- Automatic Mood Change Logic ---

# async def maybe_change_mood(cog: 'GurtCog'):
#     """Checks if enough time has passed and changes mood based on context."""
#     now = time.time()
#     time_since_last_change = now - cog.last_mood_change
#     next_change_interval = random.uniform(MOOD_CHANGE_INTERVAL_MIN, MOOD_CHANGE_INTERVAL_MAX)
#
#     if time_since_last_change > next_change_interval:
#         print(f"Time for a mood change (interval: {next_change_interval:.0f}s). Analyzing context...")
#         try:
#             # 1. Analyze Sentiment
#             positive_sentiment_score = 0
#             negative_sentiment_score = 0
#             neutral_sentiment_score = 0
#             sentiment_channels_count = 0
#             for channel_id, sentiment_data in cog.conversation_sentiment.items():
#                 # Consider only channels active recently (e.g., within the last hour)
#                 if now - cog.channel_activity.get(channel_id, 0) < 3600:
#                     if sentiment_data["overall"] == "positive":
#                         positive_sentiment_score += sentiment_data["intensity"]
#                     elif sentiment_data["overall"] == "negative":
#                         negative_sentiment_score += sentiment_data["intensity"]
#                     else:
#                         neutral_sentiment_score += sentiment_data["intensity"]
#                     sentiment_channels_count += 1
#
#             avg_pos_intensity = positive_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
#             avg_neg_intensity = negative_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
#             avg_neu_intensity = neutral_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
#             print(f"  - Sentiment Analysis: Pos={avg_pos_intensity:.2f}, Neg={avg_neg_intensity:.2f}, Neu={avg_neu_intensity:.2f}")
#
#             # Determine dominant sentiment category
#             dominant_sentiment = "neutral"
#             if avg_pos_intensity > avg_neg_intensity and avg_pos_intensity > avg_neu_intensity:
#                 dominant_sentiment = "positive"
#             elif avg_neg_intensity > avg_pos_intensity and avg_neg_intensity > avg_neu_intensity:
#                 dominant_sentiment = "negative"
#
#             # 2. Get Personality Traits
#             personality_traits = await cog.memory_manager.get_all_personality_traits()
#             if not personality_traits:
#                 personality_traits = BASELINE_PERSONALITY.copy()
#                 print("  - Warning: Using baseline personality traits for mood change.")
#             else:
#                 print(f"  - Personality Traits: Mischief={personality_traits.get('mischief', 0):.2f}, Sarcasm={personality_traits.get('sarcasm_level', 0):.2f}, Optimism={personality_traits.get('optimism', 0.5):.2f}")
#
#             # 3. Calculate Mood Weights
#             mood_weights = {mood: 1.0 for mood in MOOD_OPTIONS} # Start with base weight
#
#             # Apply Sentiment Bias (e.g., boost factor of 2)
#             sentiment_boost = 2.0
#             if dominant_sentiment == "positive":
#                 for mood in MOOD_CATEGORIES.get("positive", []):
#                     mood_weights[mood] *= sentiment_boost
#             elif dominant_sentiment == "negative":
#                 for mood in MOOD_CATEGORIES.get("negative", []):
#                     mood_weights[mood] *= sentiment_boost
#             else: # Neutral sentiment
#                  for mood in MOOD_CATEGORIES.get("neutral", []):
#                     mood_weights[mood] *= (sentiment_boost * 0.75) # Slightly boost neutral too
#
#             # Apply Personality Bias
#             mischief_trait = personality_traits.get('mischief', 0.5)
#             sarcasm_trait = personality_traits.get('sarcasm_level', 0.3)
#             optimism_trait = personality_traits.get('optimism', 0.5)
#
#             if mischief_trait > 0.6: # If high mischief
#                 mood_weights["mischievous"] *= (1.0 + mischief_trait) # Boost mischievous based on trait level
#             if sarcasm_trait > 0.5: # If high sarcasm
#                 mood_weights["sarcastic"] *= (1.0 + sarcasm_trait)
#                 mood_weights["sassy"] *= (1.0 + sarcasm_trait * 0.5) # Also boost sassy a bit
#             if optimism_trait > 0.7: # If very optimistic
#                 for mood in MOOD_CATEGORIES.get("positive", []):
#                     mood_weights[mood] *= (1.0 + (optimism_trait - 0.5)) # Boost positive moods
#             elif optimism_trait < 0.3: # If pessimistic
#                  for mood in MOOD_CATEGORIES.get("negative", []):
#                     mood_weights[mood] *= (1.0 + (0.5 - optimism_trait)) # Boost negative moods
#
#             # Ensure current mood has very low weight to avoid picking it again
#             mood_weights[cog.current_mood] = 0.01
#
#             # Filter out moods with zero weight before choices
#             valid_moods = [mood for mood, weight in mood_weights.items() if weight > 0]
#             valid_weights = [mood_weights[mood] for mood in valid_moods]
#
#             if not valid_moods:
#                  print("  - Error: No valid moods with positive weight found. Skipping mood change.")
#                  return # Skip change if something went wrong
#
#             # 4. Select New Mood
#             new_mood = random.choices(valid_moods, weights=valid_weights, k=1)[0]
#
#             # 5. Update State & Log
#             old_mood = cog.current_mood
#             cog.current_mood = new_mood
#             cog.last_mood_change = now
#             print(f"Mood automatically changed: {old_mood} -> {new_mood} (Influenced by: Sentiment={dominant_sentiment}, Traits)")
#
#         except Exception as e:
#             print(f"Error during automatic mood change: {e}")
#             traceback.print_exc()
#             # Still update timestamp to avoid retrying immediately on error
#             cog.last_mood_change = now

# --- Interest Update Logic ---

async def update_interests(cog: 'GurtCog'):
    """Analyzes recent activity and updates Gurt's interest levels."""
    print("Starting interest update cycle...")
    try:
        interest_changes = defaultdict(float)

        # 1. Analyze Gurt's participation in topics
        print(f"Analyzing Gurt participation topics: {dict(cog.gurt_participation_topics)}")
        for topic, count in cog.gurt_participation_topics.items():
            boost = INTEREST_PARTICIPATION_BOOST * count
            interest_changes[topic] += boost
            print(f"  - Participation boost for '{topic}': +{boost:.3f} (Count: {count})")

        # 2. Analyze reactions to Gurt's messages
        print(f"Analyzing {len(cog.gurt_message_reactions)} reactions to Gurt's messages...")
        processed_reaction_messages = set()
        reactions_to_process = list(cog.gurt_message_reactions.items())

        for message_id, reaction_data in reactions_to_process:
            if message_id in processed_reaction_messages: continue
            topic = reaction_data.get("topic")
            if not topic:
                try:
                    gurt_msg_data = next((msg for msg in cog.message_cache['global_recent'] if msg['id'] == message_id), None)
                    if gurt_msg_data and gurt_msg_data['content']:
                         # Use identify_conversation_topics from analysis.py
                         identified_topics = identify_conversation_topics(cog, [gurt_msg_data]) # Pass cog
                         if identified_topics:
                             topic = identified_topics[0]['topic']
                             print(f"  - Determined topic '{topic}' for reaction msg {message_id} retrospectively.")
                         else: print(f"  - Could not determine topic for reaction msg {message_id} retrospectively."); continue
                    else: print(f"  - Could not find Gurt msg {message_id} in cache for reaction analysis."); continue
                except Exception as topic_e: print(f"  - Error determining topic for reaction msg {message_id}: {topic_e}"); continue

            if topic:
                topic = topic.lower().strip()
                pos_reactions = reaction_data.get("positive", 0)
                neg_reactions = reaction_data.get("negative", 0)
                change = 0
                if pos_reactions > neg_reactions: change = INTEREST_POSITIVE_REACTION_BOOST * (pos_reactions - neg_reactions)
                elif neg_reactions > pos_reactions: change = INTEREST_NEGATIVE_REACTION_PENALTY * (neg_reactions - pos_reactions)
                if change != 0:
                    interest_changes[topic] += change
                    print(f"  - Reaction change for '{topic}' on msg {message_id}: {change:+.3f} ({pos_reactions} pos, {neg_reactions} neg)")
                processed_reaction_messages.add(message_id)

        # 3. Analyze recently learned facts
        try:
            recent_facts = await cog.memory_manager.get_general_facts(limit=10)
            print(f"Analyzing {len(recent_facts)} recent general facts for interest boosts...")
            for fact in recent_facts:
                fact_lower = fact.lower()
                # Basic keyword checks (could be improved)
                if "game" in fact_lower or "gaming" in fact_lower: interest_changes["gaming"] += INTEREST_FACT_BOOST; print(f"  - Fact boost for 'gaming'")
                if "anime" in fact_lower or "manga" in fact_lower: interest_changes["anime"] += INTEREST_FACT_BOOST; print(f"  - Fact boost for 'anime'")
                if "teto" in fact_lower: interest_changes["kasane teto"] += INTEREST_FACT_BOOST * 2; print(f"  - Fact boost for 'kasane teto'")
                # Add more checks...
        except Exception as fact_e: print(f"  - Error analyzing recent facts: {fact_e}")

        # --- Apply Changes ---
        print(f"Applying interest changes: {dict(interest_changes)}")
        if interest_changes:
            for topic, change in interest_changes.items():
                if change != 0: await cog.memory_manager.update_interest(topic, change)
        else: print("No interest changes to apply.")

        # Clear temporary tracking data
        cog.gurt_participation_topics.clear()
        now = time.time()
        reactions_to_keep = {
            msg_id: data for msg_id, data in cog.gurt_message_reactions.items()
            if data.get("timestamp", 0) > (now - INTEREST_UPDATE_INTERVAL * 1.1)
        }
        cog.gurt_message_reactions = defaultdict(lambda: {"positive": 0, "negative": 0, "topic": None}, reactions_to_keep)

        print("Interest update cycle finished.")

    except Exception as e:
        print(f"Error during interest update: {e}")
        traceback.print_exc()
