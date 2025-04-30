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
    REFLECTION_INTERVAL_SECONDS # Import reflection interval
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
                    cog.last_stats_push = now # Update timestamp even on error

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

    # Ensure these except blocks match the initial 'try' at the function start
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
# (Commented out or removed if not needed)
# async def maybe_change_mood(cog: 'GurtCog'):
# ...

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
                except Exception as topic_e: print(f"  - Error determining topic for reaction msg {message_id}: {topic_e}"); continue # Corrected indent

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
