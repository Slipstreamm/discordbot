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
    from .cog import FreakTetoCog # For type hinting - Updated

# --- Tool Mapping Import ---
# Import the mapping to execute tools by name
from .tools import TOOL_MAPPING, send_discord_message # Also import send_discord_message directly for goal execution reporting
from .config import TOOLS  # Import FunctionDeclaration list for tool metadata

# --- Background Task ---

async def background_processing_task(cog: 'FreakTetoCog'): # Updated type hint
    """Background task that periodically analyzes conversations, evolves personality, updates interests, changes mood, reflects on memory, and pushes stats."""
    # Get API details from environment for stats pushing
    api_internal_url = os.getenv("API_INTERNAL_URL")
    # Use a potentially different secret for Freak Teto stats, no fallback needed conceptually
    freak_teto_stats_push_secret = os.getenv("FREAK_TETO_STATS_PUSH_SECRET") # Removed fallback to Gurt's secret

    if not api_internal_url:
        print("WARNING: API_INTERNAL_URL not set. Freak Teto stats will not be pushed.") # Updated log
    if not freak_teto_stats_push_secret:
        print("WARNING: FREAK_TETO_STATS_PUSH_SECRET not set. Freak Teto stats push endpoint is insecure and likely won't work.") # Updated log

    try:
        while True:
            await asyncio.sleep(15) # Check more frequently for stats push
            now = time.time()

            # --- Push Stats (Runs frequently) ---
            if api_internal_url and freak_teto_stats_push_secret and (now - cog.last_stats_push > STATS_PUSH_INTERVAL):
                print("Pushing Freak Teto stats to API server...") # Updated log
                try:
                    # Call renamed stats method
                    stats_data = await cog.get_freak_teto_stats()
                    headers = {
                        "Authorization": f"Bearer {freak_teto_stats_push_secret}",
                        "Content-Type": "application/json"
                    }
                    # Use the cog's session, ensure it's created
                    if cog.session:
                        # Set a reasonable timeout for the stats push
                        push_timeout = aiohttp.ClientTimeout(total=10) # 10 seconds total timeout
                        async with cog.session.post(api_internal_url, json=stats_data, headers=headers, timeout=push_timeout, ssl=True) as response: # Explicitly enable SSL verification
                            if response.status == 200:
                                print(f"Successfully pushed Freak Teto stats (Status: {response.status})") # Log already updated
                            else:
                                error_text = await response.text()
                                print(f"Failed to push Freak Teto stats (Status: {response.status}): {error_text[:200]}") # Log already updated
                    else:
                        print("Error pushing stats: FreakTetoCog session not initialized.") # Log already updated

                except aiohttp.ClientConnectorSSLError as ssl_err:
                     print(f"SSL Error pushing Freak Teto stats: {ssl_err}. Ensure the API server's certificate is valid and trusted, or check network configuration.") # Log already updated
                     print("If using a self-signed certificate for development, the bot process might need to trust it.")
                except aiohttp.ClientError as client_err:
                    print(f"HTTP Client Error pushing Freak Teto stats: {client_err}") # Updated log
                except asyncio.TimeoutError:
                    print("Timeout error pushing Freak Teto stats.") # Log already updated
                except Exception as e:
                    print(f"Unexpected error pushing Freak Teto stats: {e}") # Log already updated
                    traceback.print_exc()
                finally:
                    cog.last_stats_push = now # Update timestamp even on failure/success to avoid spamming logs

            # --- Learning Analysis (Runs less frequently) ---
            if now - cog.last_learning_update > LEARNING_UPDATE_INTERVAL:
                if cog.message_cache['global_recent']:
                    print("Running conversation pattern analysis (Freak Teto)...") # Updated log
                    # Ensure analysis uses FreakTetoCog instance
                    await analyze_conversation_patterns(cog)
                    cog.last_learning_update = now
                    print("Learning analysis cycle complete (Freak Teto).") # Updated log
                else:
                    print("Skipping learning analysis (Freak Teto): No recent messages.") # Updated log

            # --- Evolve Personality (Runs moderately frequently) ---
            if now - cog.last_evolution_update > EVOLUTION_UPDATE_INTERVAL:
                print("Running personality evolution (Freak Teto)...") # Updated log
                # Ensure analysis uses FreakTetoCog instance
                await evolve_personality(cog)
                cog.last_evolution_update = now
                print("Personality evolution complete (Freak Teto).") # Updated log

            # --- Update Interests (Runs moderately frequently) ---
            if now - cog.last_interest_update > INTEREST_UPDATE_INTERVAL:
                print("Running interest update (Freak Teto)...") # Updated log
                await update_interests(cog) # Call the local helper function below
                print("Running interest decay check (Freak Teto)...") # Updated log
                # Ensure MemoryManager uses FreakTeto DB paths
                await cog.memory_manager.decay_interests(
                    decay_interval_hours=INTEREST_DECAY_INTERVAL_HOURS
                )
                cog.last_interest_update = now # Reset timer after update and decay check
                print("Interest update and decay check complete (Freak Teto).") # Updated log

            # --- Memory Reflection (Runs less frequently) ---
            if now - cog.last_reflection_time > REFLECTION_INTERVAL_SECONDS:
                print("Running memory reflection (Freak Teto)...") # Updated log
                # Ensure analysis uses FreakTetoCog instance
                await reflect_on_memories(cog)
                cog.last_reflection_time = now # Update timestamp
                print("Memory reflection cycle complete (Freak Teto).") # Updated log

            # --- Goal Decomposition (Runs periodically) ---
            if now - cog.last_goal_check_time > GOAL_CHECK_INTERVAL:
                print("Checking for pending goals to decompose (Freak Teto)...") # Updated log
                try:
                    # Ensure MemoryManager uses FreakTeto DB paths
                    pending_goals = await cog.memory_manager.get_goals(status='pending', limit=3)
                    for goal in pending_goals:
                        goal_id = goal.get('goal_id')
                        description = goal.get('description')
                        if not goal_id or not description: continue

                        print(f"  - Decomposing goal ID {goal_id}: '{description}' (Freak Teto)") # Updated log
                        # Ensure analysis uses FreakTetoCog instance
                        plan = await decompose_goal_into_steps(cog, description)

                        if plan and plan.get('goal_achievable') and plan.get('steps'):
                            await cog.memory_manager.update_goal(goal_id, status='active', details=plan)
                            print(f"  - Goal ID {goal_id} decomposed and set to active (Freak Teto).") # Updated log
                        elif plan:
                            await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": plan.get('reasoning', 'Deemed unachievable by planner.')})
                            print(f"  - Goal ID {goal_id} marked as failed (unachievable, Freak Teto). Reason: {plan.get('reasoning')}") # Updated log
                        else:
                            await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": "Goal decomposition process failed."})
                            print(f"  - Goal ID {goal_id} marked as failed (decomposition error, Freak Teto).") # Updated log
                        await asyncio.sleep(1)

                    cog.last_goal_check_time = now
                except Exception as goal_e:
                    print(f"Error during goal decomposition check (Freak Teto): {goal_e}") # Updated log
                    traceback.print_exc()
                    cog.last_goal_check_time = now

            # --- Goal Execution (Runs periodically) ---
            if now - cog.last_goal_execution_time > GOAL_EXECUTION_INTERVAL:
                print("Checking for active goals to execute (Freak Teto)...") # Updated log
                try:
                    # Ensure MemoryManager uses FreakTeto DB paths
                    active_goals = await cog.memory_manager.get_goals(status='active', limit=1)
                    if active_goals:
                        goal = active_goals[0]
                        goal_id = goal.get('goal_id')
                        description = goal.get('description')
                        plan = goal.get('details')
                        goal_context_guild_id = goal.get('guild_id')
                        goal_context_channel_id = goal.get('channel_id')
                        goal_context_user_id = goal.get('user_id')

                        if goal_id and description and plan and isinstance(plan.get('steps'), list):
                            print(f"--- Executing Goal ID {goal_id}: '{description}' (Freak Teto, Context: G={goal_context_guild_id}, C={goal_context_channel_id}, U={goal_context_user_id}) ---") # Updated log
                            steps = plan['steps']
                            current_step_index = plan.get('current_step_index', 0)
                            goal_failed = False
                            goal_completed = False

                            if current_step_index < len(steps):
                                step = steps[current_step_index]
                                step_desc = step.get('step_description')
                                tool_name = step.get('tool_name')
                                tool_args = step.get('tool_arguments')

                                print(f"  - Step {current_step_index + 1}/{len(steps)}: {step_desc} (Freak Teto)") # Updated log

                                if tool_name:
                                    print(f"    - Attempting tool: {tool_name} with args: {tool_args} (Freak Teto)") # Updated log
                                    tool_func = TOOL_MAPPING.get(tool_name)
                                    tool_result = None
                                    tool_error = None
                                    tool_success = False

                                    if tool_func:
                                        try:
                                            args_to_pass = tool_args if isinstance(tool_args, dict) else {}
                                            print(f"    - Executing: {tool_name}(cog, **{args_to_pass}) (Freak Teto)") # Updated log
                                            start_time = time.monotonic()
                                            # Ensure tool function uses FreakTetoCog instance correctly
                                            tool_result = await tool_func(cog, **args_to_pass)
                                            end_time = time.monotonic()
                                            print(f"    - Tool '{tool_name}' returned: {str(tool_result)[:200]}... (Freak Teto)") # Updated log

                                            if isinstance(tool_result, dict) and "error" in tool_result:
                                                tool_error = tool_result["error"]
                                                print(f"    - Tool '{tool_name}' reported error: {tool_error} (Freak Teto)") # Updated log
                                                cog.tool_stats[tool_name]["failure"] += 1
                                            else:
                                                tool_success = True
                                                print(f"    - Tool '{tool_name}' executed successfully (Freak Teto).") # Updated log
                                                cog.tool_stats[tool_name]["success"] += 1
                                            cog.tool_stats[tool_name]["count"] += 1
                                            cog.tool_stats[tool_name]["total_time"] += (end_time - start_time)

                                        except Exception as exec_e:
                                            tool_error = f"Exception during execution: {str(exec_e)}"
                                            print(f"    - Tool '{tool_name}' raised exception: {exec_e} (Freak Teto)") # Updated log
                                            traceback.print_exc()
                                            cog.tool_stats[tool_name]["failure"] += 1
                                            cog.tool_stats[tool_name]["count"] += 1
                                    else:
                                        tool_error = f"Tool '{tool_name}' not found in TOOL_MAPPING."
                                        print(f"    - Error: {tool_error} (Freak Teto)") # Updated log

                                    # --- Send Update Message ---
                                    if goal_context_channel_id:
                                        step_number_display = current_step_index + 1
                                        status_emoji = "✅" if tool_success else "❌"
                                        step_result_summary = _create_result_summary(tool_result if tool_success else {"error": tool_error})

                                        update_message = (
                                            f"**Goal Update (Freak Teto, ID: {goal_id}, Step {step_number_display}/{len(steps)})** {status_emoji}\n" # Updated title
                                            f"> **Goal:** {description}\n"
                                            f"> **Step:** {step_desc}\n"
                                            f"> **Tool:** `{tool_name}`\n"
                                            f"> **Result:** `{step_result_summary}`"
                                        )
                                        if len(update_message) > 1900:
                                            update_message = update_message[:1900] + "...`"

                                        try:
                                            # Ensure send_discord_message uses FreakTetoCog instance
                                            await send_discord_message(cog, channel_id=goal_context_channel_id, message_content=update_message)
                                            print(f"    - Sent goal update to channel {goal_context_channel_id} (Freak Teto)") # Updated log
                                        except Exception as msg_err:
                                            print(f"    - Failed to send goal update message to channel {goal_context_channel_id}: {msg_err} (Freak Teto)") # Updated log

                                    # --- Handle Tool Outcome ---
                                    if tool_success:
                                        current_step_index += 1
                                    else:
                                        goal_failed = True
                                        plan['error_message'] = f"Failed at step {current_step_index + 1} ({tool_name}): {tool_error}"
                                else:
                                    print("    - No tool required for this step (internal check/reasoning, Freak Teto).") # Updated log
                                    current_step_index += 1

                                # Check if goal completed
                                if not goal_failed and current_step_index >= len(steps):
                                    goal_completed = True

                                # --- Update Goal Status ---
                                plan['current_step_index'] = current_step_index
                                if goal_completed:
                                    await cog.memory_manager.update_goal(goal_id, status='completed', details=plan)
                                    print(f"--- Goal ID {goal_id} completed successfully (Freak Teto). ---") # Updated log
                                elif goal_failed:
                                    await cog.memory_manager.update_goal(goal_id, status='failed', details=plan)
                                    print(f"--- Goal ID {goal_id} failed (Freak Teto). ---") # Updated log
                                else:
                                    await cog.memory_manager.update_goal(goal_id, details=plan)
                                    print(f"  - Goal ID {goal_id} progress updated to step {current_step_index} (Freak Teto).") # Updated log

                            else:
                                print(f"  - Goal ID {goal_id} is active but has invalid steps. Marking as failed (Freak Teto).") # Updated log
                                await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": "Active goal has invalid step data."})

                        else:
                             print(f"  - Skipping active goal ID {goal_id}: Missing description or valid plan (Freak Teto).") # Updated log
                             if goal_id:
                                 await cog.memory_manager.update_goal(goal_id, status='failed', details={"reason": "Invalid plan structure found during execution."})

                    else:
                        print("No active goals found to execute (Freak Teto).") # Updated log

                    cog.last_goal_execution_time = now
                except Exception as goal_exec_e:
                    print(f"Error during goal execution check (Freak Teto): {goal_exec_e}") # Updated log
                    traceback.print_exc()
                    cog.last_goal_execution_time = now

            # --- Automatic Mood Change ---
            # Mood change logic might need persona adjustments if kept
            # await maybe_change_mood(cog)

            # --- Proactive Goal Creation Check ---
            if now - cog.last_proactive_goal_check > PROACTIVE_GOAL_CHECK_INTERVAL:
                print("Checking if Freak Teto should proactively create goals...") # Updated log
                try:
                    # Ensure analysis uses FreakTetoCog instance
                    await proactively_create_goals(cog)
                    cog.last_proactive_goal_check = now
                    print("Proactive goal check complete (Freak Teto).") # Updated log
                except Exception as proactive_e:
                    print(f"Error during proactive goal check (Freak Teto): {proactive_e}") # Updated log
                    traceback.print_exc()
                    cog.last_proactive_goal_check = now

    except asyncio.CancelledError:
        print("Background processing task cancelled (Freak Teto)") # Updated log
    except Exception as e:
        print(f"Error in background processing task (Freak Teto): {e}") # Updated log
        traceback.print_exc()
        await asyncio.sleep(300)

# --- Helper for Summarizing Tool Results ---
def _create_result_summary(tool_result: Any, max_len: int = 200) -> str:
    # This helper seems generic enough, no changes needed unless specific keys are Gurt-only
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
            return summary[:max_len]
        else:
            return f"Dict Result: {str(tool_result)[:max_len]}"
    elif isinstance(tool_result, str):
        return f"String Result: {tool_result[:max_len]}"
    elif tool_result is None:
        return "Result: None"
    else:
        return f"Result Type {type(tool_result)}: {str(tool_result)[:max_len]}"

# --- Automatic Mood Change Logic ---
# (Re-evaluate if mood changes make sense for Teto's persona)
# async def maybe_change_mood(cog: 'FreakTetoCog'):
# ...

# --- Interest Update Logic ---
async def update_interests(cog: 'FreakTetoCog'): # Updated type hint
    """Analyzes recent activity and updates Freak Teto's interest levels.""" # Updated docstring
    print("Starting interest update cycle (Freak Teto)...") # Updated log
    try:
        interest_changes = defaultdict(float)

        # 1. Analyze participation in topics
        # Use renamed state variable
        print(f"Analyzing Freak Teto participation topics: {dict(cog.freak_teto_participation_topics)}") # Updated log and variable
        for topic, count in cog.freak_teto_participation_topics.items():
            boost = INTEREST_PARTICIPATION_BOOST * count
            interest_changes[topic] += boost
            print(f"  - Participation boost for '{topic}': +{boost:.3f} (Count: {count})")

        # 2. Analyze reactions to bot's messages
        # Use renamed state variable
        print(f"Analyzing {len(cog.freak_teto_message_reactions)} reactions to Freak Teto's messages...") # Updated log and variable
        processed_reaction_messages = set()
        reactions_to_process = list(cog.freak_teto_message_reactions.items()) # Use renamed variable

        for message_id, reaction_data in reactions_to_process:
            if message_id in processed_reaction_messages: continue
            topic = reaction_data.get("topic")
            if not topic:
                try:
                    # Ensure message cache access is correct for FreakTetoCog
                    teto_msg_data = next((msg for msg in cog.message_cache['global_recent'] if msg['id'] == message_id), None)
                    if teto_msg_data and teto_msg_data['content']:
                         # Ensure analysis uses FreakTetoCog instance
                         identified_topics = identify_conversation_topics(cog, [teto_msg_data])
                         if identified_topics:
                             topic = identified_topics[0]['topic']
                             print(f"  - Determined topic '{topic}' for reaction msg {message_id} retrospectively (Freak Teto).") # Updated log
                         else: print(f"  - Could not determine topic for reaction msg {message_id} retrospectively (Freak Teto)."); continue # Updated log
                    else: print(f"  - Could not find Freak Teto msg {message_id} in cache for reaction analysis."); continue # Updated log
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
                    print(f"  - Reaction change for '{topic}' on msg {message_id}: {change:+.3f} ({pos_reactions} pos, {neg_reactions} neg) (Freak Teto)") # Updated log
                processed_reaction_messages.add(message_id)

        # 3. Analyze recently learned facts
        try:
            # Ensure MemoryManager uses FreakTeto DB paths
            recent_facts = await cog.memory_manager.get_general_facts(limit=10)
            print(f"Analyzing {len(recent_facts)} recent general facts for interest boosts (Freak Teto)...") # Updated log
            for fact in recent_facts:
                fact_lower = fact.lower()
                # Update keyword checks for Teto's interests
                if "game" in fact_lower or "gaming" in fact_lower: interest_changes["gaming"] += INTEREST_FACT_BOOST; print(f"  - Fact boost for 'gaming'")
                if "anime" in fact_lower or "manga" in fact_lower: interest_changes["anime/manga"] += INTEREST_FACT_BOOST; print(f"  - Fact boost for 'anime/manga'")
                if "teto" in fact_lower: interest_changes["kasane teto"] += INTEREST_FACT_BOOST * 2; print(f"  - Fact boost for 'kasane teto'")
                if "vocaloid" in fact_lower or "utau" in fact_lower: interest_changes["vocaloid/utau"] += INTEREST_FACT_BOOST * 1.5; print(f"  - Fact boost for 'vocaloid/utau'")
                if "music" in fact_lower: interest_changes["music"] += INTEREST_FACT_BOOST; print(f"  - Fact boost for 'music'")
                if "bread" in fact_lower: interest_changes["french bread"] += INTEREST_FACT_BOOST; print(f"  - Fact boost for 'french bread'")
                # Add checks for other interests if needed
        except Exception as fact_e: print(f"  - Error analyzing recent facts (Freak Teto): {fact_e}") # Updated log

        # --- Apply Changes ---
        print(f"Applying interest changes (Freak Teto): {dict(interest_changes)}") # Updated log
        if interest_changes:
            # Ensure MemoryManager uses FreakTeto DB paths
            for topic, change in interest_changes.items():
                if change != 0: await cog.memory_manager.update_interest(topic, change)
        else: print("No interest changes to apply (Freak Teto).") # Updated log

        # Clear temporary tracking data
        # Use renamed state variable
        cog.freak_teto_participation_topics.clear()
        now = time.time()
        # Use renamed state variable
        reactions_to_keep = {
            msg_id: data for msg_id, data in cog.freak_teto_message_reactions.items()
            if data.get("timestamp", 0) > (now - INTEREST_UPDATE_INTERVAL * 1.1)
        }
        # Use renamed state variable
        cog.freak_teto_message_reactions = defaultdict(lambda: {"positive": 0, "negative": 0, "topic": None}, reactions_to_keep)

        print("Interest update cycle finished (Freak Teto).") # Updated log

    except Exception as e:
        print(f"Error during interest update (Freak Teto): {e}") # Updated log
        traceback.print_exc()
