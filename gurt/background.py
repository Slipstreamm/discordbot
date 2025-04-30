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
    STANDARD_SAFETY_SETTINGS,         # Import safety settings
    process_requested_tools           # Import tool processor
)

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting

# --- Tool Mapping Import ---
# Import the mapping to execute tools by name
from .tools import TOOL_MAPPING, send_discord_message # Also import send_discord_message directly for goal execution reporting
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
                        # Retrieve context saved with the goal
                        goal_context_guild_id = goal.get('guild_id')
                        goal_context_channel_id = goal.get('channel_id')
                        goal_context_user_id = goal.get('user_id')

                        if goal_id and description and plan and isinstance(plan.get('steps'), list):
                            print(f"--- Executing Goal ID {goal_id}: '{description}' (Context: G={goal_context_guild_id}, C={goal_context_channel_id}, U={goal_context_user_id}) ---")
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

                                    # --- Send Update Message (if channel context exists) --- ### MODIFICATION START ###
                                    if goal_context_channel_id:
                                        step_number_display = current_step_index + 1 # Human-readable step number for display
                                        status_emoji = "✅" if tool_success else "❌"
                                        # Use the helper function to create a summary
                                        step_result_summary = _create_result_summary(tool_result if tool_success else {"error": tool_error})

                                        update_message = (
                                            f"**Goal Update (ID: {goal_id}, Step {step_number_display}/{len(steps)})** {status_emoji}\n"
                                            f"> **Goal:** {description}\n"
                                            f"> **Step:** {step_desc}\n"
                                            f"> **Tool:** `{tool_name}`\n"
                                            # f"> **Args:** `{json.dumps(tool_args)}`\n" # Args might be too verbose
                                            f"> **Result:** `{step_result_summary}`"
                                        )
                                        # Limit message length
                                        if len(update_message) > 1900:
                                            update_message = update_message[:1900] + "...`"

                                        try:
                                            # Use the imported send_discord_message function
                                            await send_discord_message(cog, channel_id=goal_context_channel_id, message_content=update_message)
                                            print(f"    - Sent goal update to channel {goal_context_channel_id}")
                                        except Exception as msg_err:
                                            print(f"    - Failed to send goal update message to channel {goal_context_channel_id}: {msg_err}")
                                    ### MODIFICATION END ###

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
                                    # Send update message for non-tool steps too? Optional. For now, only for tool steps.
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
                    # --- Refactored Autonomous Action Logic ---
                    selected_tool_name = None
                    tool_args = None
                    tool_result = None
                    action_reasoning = "No decision made." # Default reasoning
                    result_summary = "No action taken."
                    final_response_obj = None # Store the last response object from the loop
                    max_tool_calls = 2 # Limit autonomous sequential calls
                    tool_calls_made = 0
                    action_error = None

                    try:
                        # 1. Gather Context
                        context_summary = "Gurt is considering an autonomous action.\n"
                        context_summary += f"Current Mood: {cog.current_mood}\n"
                        active_goals = await cog.memory_manager.get_goals(status='active', limit=3)
                        if active_goals: context_summary += f"Active Goals:\n" + json.dumps(active_goals, indent=2)[:500] + "...\n"
                        recent_actions = await cog.memory_manager.get_internal_action_logs(limit=5)
                        if recent_actions: context_summary += f"Recent Internal Actions:\n" + json.dumps(recent_actions, indent=2)[:500] + "...\n"
                        traits = await cog.memory_manager.get_all_personality_traits()
                        if traits: context_summary += f"Personality Snippet: { {k: round(v, 2) for k, v in traits.items() if k in ['mischief', 'curiosity', 'chattiness']} }\n"

                        # 2. Prepare Tools
                        excluded_tools = {"create_new_tool"}
                        preprocessed_declarations = []
                        if TOOLS:
                            for decl in TOOLS:
                                if decl.name in excluded_tools: continue
                                preprocessed_params = _preprocess_schema_for_vertex(decl.parameters) if isinstance(decl.parameters, dict) else decl.parameters
                                preprocessed_declarations.append(types.FunctionDeclaration(name=decl.name, description=decl.description, parameters=preprocessed_params))
                        genai_tool = types.Tool(function_declarations=preprocessed_declarations) if preprocessed_declarations else None
                        tools_list = [genai_tool] if genai_tool else None

                        # 3. Define Prompt
                        system_prompt = (
                            "You are the decision-making module for Gurt's autonomous actions. Evaluate the context and decide if an action is appropriate. "
                            "Your goal is natural, proactive engagement aligned with Gurt's persona (informal, slang, tech/internet savvy, sometimes mischievous). "
                            "Actions can be random, goal-related, or contextually relevant. Avoid repetitive patterns.\n\n"
                            "**RESPONSE PROTOCOL (CRITICAL):**\n"
                            "Based on the context, determine if an autonomous action is necessary or desirable. Your response MUST be a native function call to one of the provided tools.\n"
                            "   - If you decide to perform a specific action, call the relevant tool function.\n"
                            "   - If you decide NOT to perform any specific action, call the `no_operation` tool. Do NOT output any text other than a function call."
                        )
                        user_prompt = f"Context:\n{context_summary}\n\nBased on the context, should Gurt perform an autonomous action now? If yes, call the appropriate tool function. If no, respond with 'NO_ACTION' and reasoning."

                        # 4. Prepare Initial Contents
                        contents: List[types.Content] = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]

                        # 5. Tool Execution Loop (Limited Iterations)
                        while tool_calls_made < max_tool_calls:
                            print(f"Autonomous Action: Making API call (Iteration {tool_calls_made + 1}/{max_tool_calls})...")

                            # Prepare Generation Config for this iteration
                            current_gen_config_dict = {
                                "temperature": 0.7, "max_output_tokens": 4096,
                                "safety_settings": STANDARD_SAFETY_SETTINGS, "system_instruction": system_prompt,
                            }
                            if tools_list:
                                current_gen_config_dict["tools"] = tools_list
                                current_gen_config_dict["tool_config"] = types.ToolConfig(
                                    function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.ANY)
                                )
                            current_gen_config = types.GenerateContentConfig(**current_gen_config_dict)

                            # Call API
                            current_response_obj = await call_google_genai_api_with_retry(
                                cog=cog, model_name=cog.default_model, contents=contents,
                                generation_config=current_gen_config, request_desc=f"Autonomous Action Loop {tool_calls_made + 1}"
                            )
                            final_response_obj = current_response_obj # Store the latest response

                            if not current_response_obj or not current_response_obj.candidates:
                                action_error = "API call failed to return candidates."
                                print(f"  - Error: {action_error}")
                                break # Exit loop on critical API failure

                            candidate = current_response_obj.candidates[0]

                            # --- Check for Native Function Call(s) and Text Parts in this turn's response ---
                            function_calls_found_in_turn = []
                            text_parts_in_turn = []
                            if candidate.content and candidate.content.parts:
                                function_calls_found_in_turn = [part.function_call for part in candidate.content.parts if hasattr(part, 'function_call') and isinstance(part.function_call, types.FunctionCall) and part.function_call.name]
                                text_parts_in_turn = [part.text for part in candidate.content.parts if hasattr(part, 'text') and part.text is not None and isinstance(part.text, str) and part.text.strip()]

                            if text_parts_in_turn:
                                # Log a warning if unexpected text is present alongside potential function calls
                                all_text_from_parts = " ".join(text_parts_in_turn)
                                print(f"⚠️ WARNING: Autonomous action model response included text alongside function calls ({[fc.name for fc in function_calls_found_in_turn]}). Text: '{all_text_from_parts[:200]}...'")
                                # Note: The text content is NOT processed or acted upon here, only logged.

                            if function_calls_found_in_turn:
                                # Append model's response (containing calls and possibly text)
                                contents.append(candidate.content)
                                # Count this turn as making tool requests (even if it also had text)
                                tool_calls_made += 1

                                # Check if the ONLY call is no_operation - this signals sequence end
                                if len(function_calls_found_in_turn) == 1 and function_calls_found_in_turn[0].name == "no_operation":
                                    print("  - AI called only no_operation. Ending action sequence.")
                                    action_reasoning = "AI explicitly chose no_operation."
                                    # Process the no_operation call to get its standard result format for logging
                                    no_op_response_part = await process_requested_tools(cog, function_calls_found_in_turn[0])
                                    # Append the function response part
                                    contents.append(types.Content(role="function", parts=[no_op_response_part]))
                                    result_summary = _create_result_summary(no_op_response_part.function_response.response)
                                    selected_tool_name = "no_operation" # Log the tool name
                                    tool_args = {} # no_operation usually has no args
                                    break # Exit loop after processing no_operation

                                # Process all tool calls found in this turn (excluding no_operation if others are present)
                                print(f"  - AI requested {len(function_calls_found_in_turn)} tool(s): {[fc.name for fc in function_calls_found_in_turn]} (Turn {tool_calls_made}/{max_tool_calls})")

                                function_response_parts = []
                                # Execute all requested tools in this turn
                                for func_call in function_calls_found_in_turn:
                                     # Only process if it's not a solitary no_operation (handled above)
                                     if not (len(function_calls_found_in_turn) == 1 and func_call.name == "no_operation"):
                                         print(f"    - Executing tool: {func_call.name}")
                                         response_part = await process_requested_tools(cog, func_call)
                                         function_response_parts.append(response_part)
                                         # Store details of the *last* executed tool for logging/reporting AFTER the loop
                                         selected_tool_name = func_call.name
                                         tool_args = dict(func_call.args) if func_call.args else {}
                                         tool_result = response_part.function_response.response # Store the result dict
                                         # Check if the tool itself returned an error
                                         if isinstance(tool_result, dict) and "error" in tool_result:
                                             print(f"  - Tool execution failed: {tool_result['error']}. Ending sequence.")
                                             action_error = f"Tool {selected_tool_name} failed: {tool_result['error']}"
                                             # Append the function response part even on error
                                             if function_response_parts:
                                                contents.append(types.Content(role="function", parts=function_response_parts))
                                             break # Stop processing tools in this turn and exit the main loop

                                # Append a single function role turn containing ALL executed tool response parts
                                if function_response_parts:
                                    contents.append(types.Content(role="function", parts=function_response_parts))
                                    result_summary = _create_result_summary(tool_result) # Use the result of the last executed tool
                                    # If we broke due to tool error, action_error is already set.
                                    if action_error:
                                        break # Exit main loop if a tool failed execution

                                # Continue loop if tool limit not reached and no tool execution error
                                if not action_error and tool_calls_made < max_tool_calls:
                                    print("  - Tools processed. Continuing tool execution loop.")
                                    continue # Continue to the next iteration
                                else:
                                    break # Exit loop (either hit max calls or tool error)

                            else: # No function calls found in this turn's response
                                # No function call found - check if any text was present (already logged above)
                                print("  - No function calls requested by AI in this turn. Exiting loop.")
                                # If there was text, it's already logged. If not, the model might have outputted nothing actionable.
                                # Action reasoning will be set below based on loop exit condition.
                                break # Exit loop

                        # End of while loop

                        # Determine final reasoning if not set by NO_ACTION or explicit call reasoning
                        if action_reasoning == "No decision made." and selected_tool_name:
                             action_reasoning = f"Executed tool '{selected_tool_name}' based on autonomous decision."
                        elif action_reasoning == "No decision made.":
                             # This case is reached if the loop finished without any function calls being requested
                             # The model might have outputted text instead, or nothing actionable.
                             # The text presence is logged.
                             if text_parts_in_turn:
                                 # Use the logged text as the reasoning if available
                                 action_reasoning = f"Autonomous sequence ended. Model outputted text: '{all_text_from_parts[:100]}...'"
                                 result_summary = action_reasoning
                             else:
                                action_reasoning = "Autonomous sequence completed without specific action or reasoning provided (model outputted no function call)."
                                result_summary = "No action taken."


                        # Handle loop limit reached
                        if tool_calls_made >= max_tool_calls:
                            print(f"  - Reached max tool call limit ({max_tool_calls}).")
                            if not action_error: # If no error occurred on the last call
                                action_error = "Max tool call limit reached."
                                if not action_reasoning or action_reasoning == "No decision made.":
                                     action_reasoning = action_error
                                if result_summary == "No action taken.":
                                    result_summary = action_error


                    except Exception as auto_e:
                        print(f"  - Error during autonomous action processing: {auto_e}")
                        traceback.print_exc()
                        action_error = f"Error during processing: {type(auto_e).__name__}: {auto_e}"
                        result_summary = action_error
                        # Ensure these are None if an error occurred before execution
                        selected_tool_name = selected_tool_name or ("Error" if action_error else "None")
                        tool_args = tool_args or {}

                    # 7. Log Action (always log the attempt/decision)
                    try:
                        # Use the state determined by the loop/error handling
                        await cog.memory_manager.add_internal_action_log(
                            # Log the tool name that was *intended* or *executed* if any, otherwise indicate None/Error
                            tool_name= selected_tool_name,
                            arguments=tool_args,
                            reasoning=action_reasoning,
                            result_summary=result_summary
                        )
                    except Exception as log_e:
                        print(f"  - Error logging autonomous action attempt to memory: {log_e}")
                        traceback.print_exc()

                    # 8. Report Initial Action (Optional) - Report only if a tool was successfully called AND it wasn't no_operation
                    if AUTONOMOUS_ACTION_REPORT_CHANNEL_ID and selected_tool_name and selected_tool_name != "no_operation" and not action_error:
                        try:
                            report_channel_id = int(AUTONOMOUS_ACTION_REPORT_CHANNEL_ID)
                            channel = cog.bot.get_channel(report_channel_id)
                            if channel and isinstance(channel, discord.TextChannel):
                                report_content = (
                                    f"⚙️ Gurt autonomously executed **{selected_tool_name}**.\n"
                                    f"**Reasoning:** {action_reasoning}\n"
                                    f"**Args:** `{json.dumps(tool_args)}`\n"
                                    f"**Result:** `{result_summary}`"
                                )
                                if len(report_content) > 2000: report_content = report_content[:1997] + "..."
                                await channel.send(report_content)
                                print(f"  - Reported autonomous action to channel {report_channel_id}.")
                            # ... (rest of reporting error handling) ...
                        except Exception as report_e:
                            print(f"  - Error reporting autonomous action to Discord: {report_e}")
                            traceback.print_exc()

                    print("--- Autonomous Action Cycle Complete ---")
                    # --- End Refactored Autonomous Action Logic ---

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
