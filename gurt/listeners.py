import discord
from discord.ext import commands
import random
import asyncio
import time
import re
import os # Added for file handling in error case
from typing import TYPE_CHECKING, Union, Dict, Any, Optional

# Relative imports
from .utils import format_message # Import format_message
from .config import CONTEXT_WINDOW_SIZE # Import context window size
# Assuming api, utils, analysis functions are defined and imported correctly later
# We might need to adjust these imports based on final structure
# from .api import get_ai_response, get_proactive_ai_response
# from .utils import format_message, simulate_human_typing
# from .analysis import analyze_message_sentiment, update_conversation_sentiment

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting

# Note: These listener functions need to be registered within the GurtCog class setup.
# They are defined here for separation but won't work standalone without being
# attached to the cog instance (e.g., self.bot.add_listener(on_message_listener(self), 'on_message')).

async def on_ready_listener(cog: 'GurtCog'):
    """Listener function for on_ready."""
    print(f'Gurt Bot is ready! Logged in as {cog.bot.user.name} ({cog.bot.user.id})')
    print('------')

    # Now that the bot is ready, we can sync commands with Discord
    try:
        print("GurtCog: Syncing commands with Discord...")
        synced = await cog.bot.tree.sync()
        print(f"GurtCog: Synced {len(synced)} command(s)")

        # List the synced commands
        gurt_commands = [cmd.name for cmd in cog.bot.tree.get_commands() if cmd.name.startswith("gurt")]
        print(f"GurtCog: Available Gurt commands: {', '.join(gurt_commands)}")
    except Exception as e:
        print(f"GurtCog: Failed to sync commands: {e}")
        import traceback
        traceback.print_exc()

    # --- Pre-load message history ---
    print("GurtCog: Starting to pre-load message history for accessible channels...")
    loaded_count = 0
    skipped_count = 0
    error_count = 0
    start_time = time.time()
    for guild in cog.bot.guilds:
        for channel in guild.text_channels:
            # Check permissions
            perms = channel.permissions_for(guild.me)
            if perms.read_message_history and perms.read_messages:
                try:
                    print(f"GurtCog: Loading history for #{channel.name} in {guild.name}...")
                    history = []
                    async for msg in channel.history(limit=CONTEXT_WINDOW_SIZE, oldest_first=False):
                        # Avoid adding messages already potentially cached by recent activity during startup
                        if msg.id not in [m['id'] for m in cog.message_cache['by_channel'].get(channel.id, [])]:
                            history.append(format_message(cog, msg)) # Use imported function

                    # Prepend history (oldest messages first in deque)
                    # The history is fetched newest first, so reverse it before extending
                    history.reverse()
                    cog.message_cache['by_channel'][channel.id].extendleft(history) # Use extendleft to add to the beginning
                    if history:
                        print(f"GurtCog: Loaded {len(history)} messages for #{channel.name}.")
                        loaded_count += 1
                    else:
                        print(f"GurtCog: No new messages found to load for #{channel.name}.")
                        skipped_count += 1 # Count channels where no *new* history was loaded

                except discord.Forbidden:
                    print(f"GurtCog: Permission denied (Forbidden) for #{channel.name} in {guild.name}.")
                    error_count += 1
                except discord.HTTPException as e:
                    print(f"GurtCog: HTTP error loading history for #{channel.name} in {guild.name}: {e}")
                    error_count += 1
                except Exception as e:
                    print(f"GurtCog: Unexpected error loading history for #{channel.name} in {guild.name}: {e}")
                    error_count += 1
            else:
                # print(f"GurtCog: Skipping #{channel.name} in {guild.name} due to missing permissions.") # Too verbose maybe
                skipped_count += 1
    end_time = time.time()
    print(f"GurtCog: Finished pre-loading history. Loaded: {loaded_count}, Skipped/No New: {skipped_count}, Errors: {error_count}. Took {end_time - start_time:.2f}s.")
    # --- End Pre-load ---


async def on_message_listener(cog: 'GurtCog', message: discord.Message):
    """Listener function for on_message."""
    # Import necessary functions dynamically or ensure they are passed/accessible via cog
    from .api import get_ai_response, get_proactive_ai_response
    from .utils import format_message, simulate_human_typing
    from .analysis import analyze_message_sentiment, update_conversation_sentiment, identify_conversation_topics
    from .config import GURT_RESPONSES # Import simple responses

    # Don't respond to our own messages
    if message.author == cog.bot.user:
        return

    # Don't process commands here
    if message.content.startswith(cog.bot.command_prefix):
        return

    # --- Cache and Track Incoming Message ---
    try:
        formatted_message = format_message(cog, message) # Use utility function
        channel_id = message.channel.id
        user_id = message.author.id
        thread_id = message.channel.id if isinstance(message.channel, discord.Thread) else None

        # Update caches (accessing cog's state)
        cog.message_cache['by_channel'][channel_id].append(formatted_message)
        cog.message_cache['by_user'][user_id].append(formatted_message)
        cog.message_cache['global_recent'].append(formatted_message)
        if thread_id:
            cog.message_cache['by_thread'][thread_id].append(formatted_message)
        if cog.bot.user.mentioned_in(message):
             cog.message_cache['mentioned'].append(formatted_message)

        cog.conversation_history[channel_id].append(formatted_message)
        if thread_id:
            cog.thread_history[thread_id].append(formatted_message)

        cog.channel_activity[channel_id] = time.time()
        cog.user_conversation_mapping[user_id].add(channel_id)

        if channel_id not in cog.active_conversations:
            cog.active_conversations[channel_id] = {'participants': set(), 'start_time': time.time(), 'last_activity': time.time(), 'topic': None}
        cog.active_conversations[channel_id]['participants'].add(user_id)
        cog.active_conversations[channel_id]['last_activity'] = time.time()

        # --- Update Relationship Strengths ---
        if user_id != cog.bot.user.id:
            message_sentiment_data = analyze_message_sentiment(cog, message.content) # Use analysis function
            sentiment_score = 0.0
            if message_sentiment_data["sentiment"] == "positive": sentiment_score = message_sentiment_data["intensity"] * 0.5
            elif message_sentiment_data["sentiment"] == "negative": sentiment_score = -message_sentiment_data["intensity"] * 0.3

            cog._update_relationship(str(user_id), str(cog.bot.user.id), 1.0 + sentiment_score) # Access cog method

            if formatted_message.get("is_reply") and formatted_message.get("replied_to_author_id"):
                replied_to_id = formatted_message["replied_to_author_id"]
                if replied_to_id != str(cog.bot.user.id) and replied_to_id != str(user_id):
                     cog._update_relationship(str(user_id), replied_to_id, 1.5 + sentiment_score)

            mentioned_ids = [m["id"] for m in formatted_message.get("mentions", [])]
            for mentioned_id in mentioned_ids:
                if mentioned_id != str(cog.bot.user.id) and mentioned_id != str(user_id):
                    cog._update_relationship(str(user_id), mentioned_id, 1.2 + sentiment_score)

        # Analyze message sentiment and update conversation sentiment tracking
        if message.content:
            message_sentiment = analyze_message_sentiment(cog, message.content) # Use analysis function
            update_conversation_sentiment(cog, channel_id, str(user_id), message_sentiment) # Use analysis function

        # --- Add message to semantic memory ---
        if message.content and cog.memory_manager.semantic_collection:
            semantic_metadata = {
                "user_id": str(user_id), "user_name": message.author.name, "display_name": message.author.display_name,
                "channel_id": str(channel_id), "channel_name": getattr(message.channel, 'name', 'DM'),
                "guild_id": str(message.guild.id) if message.guild else None,
                "timestamp": message.created_at.timestamp()
            }
            # Pass the entire formatted_message dictionary now
            asyncio.create_task(
                cog.memory_manager.add_message_embedding(
                    message_id=str(message.id), formatted_message_data=formatted_message, metadata=semantic_metadata
                )
            )

    except Exception as e:
        print(f"Error during message caching/tracking/embedding: {e}")
    # --- End Caching & Embedding ---


    # Simple response for messages just containing "gurt"
    if message.content.lower() == "gurt":
        response = random.choice(GURT_RESPONSES)
        await message.channel.send(response)
        return

    # Check conditions for potentially responding
    bot_mentioned = cog.bot.user.mentioned_in(message)
    replied_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user
    gurt_in_message = "gurt" in message.content.lower()
    now = time.time()
    time_since_last_activity = now - cog.channel_activity.get(channel_id, 0)
    time_since_bot_spoke = now - cog.bot_last_spoke.get(channel_id, 0)

    should_consider_responding = False
    consideration_reason = "Default"
    proactive_trigger_met = False

    if bot_mentioned or replied_to_bot or gurt_in_message:
        should_consider_responding = True
        consideration_reason = "Direct mention/reply/name"
    else:
        # --- Proactive Engagement Triggers ---
        from .config import (PROACTIVE_LULL_THRESHOLD, PROACTIVE_BOT_SILENCE_THRESHOLD, PROACTIVE_LULL_CHANCE,
                             PROACTIVE_TOPIC_RELEVANCE_THRESHOLD, PROACTIVE_TOPIC_CHANCE,
                             PROACTIVE_RELATIONSHIP_SCORE_THRESHOLD, PROACTIVE_RELATIONSHIP_CHANCE,
                         # Import new config values
                             # Import new config values
                             PROACTIVE_SENTIMENT_SHIFT_THRESHOLD, PROACTIVE_SENTIMENT_DURATION_THRESHOLD,
                             PROACTIVE_SENTIMENT_CHANCE, PROACTIVE_USER_INTEREST_THRESHOLD,
                             PROACTIVE_USER_INTEREST_CHANCE)

        # 1. Lull Trigger
        if time_since_last_activity > PROACTIVE_LULL_THRESHOLD and time_since_bot_spoke > PROACTIVE_BOT_SILENCE_THRESHOLD:
            has_relevant_context = bool(cog.active_topics.get(channel_id, {}).get("topics", [])) or \
                                   bool(await cog.memory_manager.get_general_facts(limit=1))
            if has_relevant_context and random.random() < PROACTIVE_LULL_CHANCE:
                should_consider_responding = True
                proactive_trigger_met = True
                consideration_reason = f"Proactive: Lull ({time_since_last_activity:.0f}s idle, bot silent {time_since_bot_spoke:.0f}s)"

        # 2. Topic Relevance Trigger
        if not proactive_trigger_met and message.content and cog.memory_manager.semantic_collection:
            try:
                semantic_results = await cog.memory_manager.search_semantic_memory(query_text=message.content, n_results=1)
                if semantic_results:
                    similarity_score = 1.0 - semantic_results[0].get('distance', 1.0)
                    if similarity_score >= PROACTIVE_TOPIC_RELEVANCE_THRESHOLD and time_since_bot_spoke > 120:
                        if random.random() < PROACTIVE_TOPIC_CHANCE:
                            should_consider_responding = True
                            proactive_trigger_met = True
                            consideration_reason = f"Proactive: Relevant topic (Sim: {similarity_score:.2f})"
                            print(f"Topic relevance trigger met for msg {message.id}. Sim: {similarity_score:.2f}")
                    else:
                        print(f"Topic relevance trigger skipped by chance ({PROACTIVE_TOPIC_CHANCE}). Sim: {similarity_score:.2f}")
            except Exception as semantic_e:
                print(f"Error during semantic search for topic trigger: {semantic_e}")

        # 3. Relationship Score Trigger
        if not proactive_trigger_met:
            try:
                user_id_str = str(message.author.id)
                bot_id_str = str(cog.bot.user.id)
                key_1, key_2 = (user_id_str, bot_id_str) if user_id_str < bot_id_str else (bot_id_str, user_id_str)
                relationship_score = cog.user_relationships.get(key_1, {}).get(key_2, 0.0)
                if relationship_score >= PROACTIVE_RELATIONSHIP_SCORE_THRESHOLD and time_since_bot_spoke > 60:
                    if random.random() < PROACTIVE_RELATIONSHIP_CHANCE:
                        should_consider_responding = True
                        proactive_trigger_met = True
                        consideration_reason = f"Proactive: High relationship ({relationship_score:.1f})"
                        print(f"Relationship trigger met for user {user_id_str}. Score: {relationship_score:.1f}")
                    else:
                        print(f"Relationship trigger skipped by chance ({PROACTIVE_RELATIONSHIP_CHANCE}). Score: {relationship_score:.1f}")
            except Exception as rel_e:
                print(f"Error during relationship trigger check: {rel_e}")

        # 4. Sentiment Shift Trigger
        if not proactive_trigger_met:
            channel_sentiment_data = cog.conversation_sentiment.get(channel_id, {})
            overall_sentiment = channel_sentiment_data.get("overall", "neutral")
            sentiment_intensity = channel_sentiment_data.get("intensity", 0.5)
            sentiment_last_update = channel_sentiment_data.get("last_update", 0) # Need last update time
            sentiment_duration = now - sentiment_last_update # How long has this sentiment been dominant?

            if overall_sentiment != "neutral" and \
               sentiment_intensity >= PROACTIVE_SENTIMENT_SHIFT_THRESHOLD and \
               sentiment_duration >= PROACTIVE_SENTIMENT_DURATION_THRESHOLD and \
               time_since_bot_spoke > 180: # Bot hasn't spoken recently about this
                if random.random() < PROACTIVE_SENTIMENT_CHANCE:
                    should_consider_responding = True
                    proactive_trigger_met = True
                    consideration_reason = f"Proactive: Sentiment Shift ({overall_sentiment}, Intensity: {sentiment_intensity:.2f}, Duration: {sentiment_duration:.0f}s)"
                    print(f"Sentiment Shift trigger met for channel {channel_id}. Sentiment: {overall_sentiment}, Intensity: {sentiment_intensity:.2f}, Duration: {sentiment_duration:.0f}s")
                else:
                    print(f"Sentiment Shift trigger skipped by chance ({PROACTIVE_SENTIMENT_CHANCE}). Sentiment: {overall_sentiment}")

        # 5. User Interest Trigger (Based on Gurt's interests mentioned in message)
        if not proactive_trigger_met and message.content:
            try:
                gurt_interests = await cog.memory_manager.get_interests(limit=10, min_level=PROACTIVE_USER_INTEREST_THRESHOLD)
                if gurt_interests:
                    message_content_lower = message.content.lower()
                    mentioned_interest = None
                    for interest_topic, interest_level in gurt_interests:
                        # Simple check if interest topic is in message
                        if re.search(r'\b' + re.escape(interest_topic.lower()) + r'\b', message_content_lower):
                            mentioned_interest = interest_topic
                            break # Found a mentioned interest

                    if mentioned_interest and time_since_bot_spoke > 90:  # Bot hasn't spoken recently
                        if random.random() < PROACTIVE_USER_INTEREST_CHANCE:
                            should_consider_responding = True
                            proactive_trigger_met = True
                            consideration_reason = f"Proactive: Gurt Interest Mentioned ('{mentioned_interest}')"
                            print(f"Gurt Interest trigger met for message {message.id}. Interest: '{mentioned_interest}'")
                        else:
                            print(f"Gurt Interest trigger skipped by chance ({PROACTIVE_USER_INTEREST_CHANCE}). Interest: '{mentioned_interest}'")
            except Exception as interest_e:
                print(f"Error during Gurt Interest trigger check: {interest_e}")

        # 6. Active Goal Relevance Trigger
        if not proactive_trigger_met and message.content:
            try:
                # Fetch 1-2 active goals with highest priority
                active_goals = await cog.memory_manager.get_goals(status='active', limit=2)
                if active_goals:
                    message_content_lower = message.content.lower()
                    relevant_goal = None
                    for goal in active_goals:
                        # Simple check: does message content relate to goal description?
                        # TODO: Improve this check, maybe use semantic similarity or keyword extraction from goal details
                        goal_keywords = set(re.findall(r'\b\w{3,}\b', goal.get('description', '').lower())) # Basic keywords from description
                        message_words = set(re.findall(r'\b\w{3,}\b', message_content_lower))
                        if len(goal_keywords.intersection(message_words)) > 1: # Require >1 keyword overlap
                            relevant_goal = goal
                            break

                    if relevant_goal and time_since_bot_spoke > 120: # Bot hasn't spoken recently
                        # Use a slightly higher chance for goal-related triggers?
                        goal_relevance_chance = PROACTIVE_USER_INTEREST_CHANCE * 1.2 # Example: Reuse interest chance slightly boosted
                        if random.random() < goal_relevance_chance:
                            should_consider_responding = True
                            proactive_trigger_met = True
                            goal_desc_short = relevant_goal.get('description', 'N/A')[:40]
                            consideration_reason = f"Proactive: Relevant Active Goal ('{goal_desc_short}...')"
                            print(f"Active Goal trigger met for message {message.id}. Goal ID: {relevant_goal.get('goal_id')}")
                        else:
                            print(f"Active Goal trigger skipped by chance ({goal_relevance_chance:.2f}).")
            except Exception as goal_trigger_e:
                print(f"Error during Active Goal trigger check: {goal_trigger_e}")


        # --- Fallback Contextual Chance ---
        if not should_consider_responding:  # Check if already decided to respond
            # Fetch current personality traits for chattiness
            persistent_traits = await cog.memory_manager.get_all_personality_traits()
            chattiness = persistent_traits.get('chattiness', 0.7) # Use default if fetch fails

            base_chance = chattiness * 0.5
            activity_bonus = 0
            if time_since_last_activity > 120: activity_bonus += 0.1
            if time_since_bot_spoke > 300: activity_bonus += 0.1
            topic_bonus = 0
            active_channel_topics = cog.active_topics.get(channel_id, {}).get("topics", [])
            if message.content and active_channel_topics:
                topic_keywords = set(t['topic'].lower() for t in active_channel_topics)
                message_words = set(re.findall(r'\b\w+\b', message.content.lower()))
                if topic_keywords.intersection(message_words): topic_bonus += 0.15
            sentiment_modifier = 0
            channel_sentiment_data = cog.conversation_sentiment.get(channel_id, {})
            overall_sentiment = channel_sentiment_data.get("overall", "neutral")
            sentiment_intensity = channel_sentiment_data.get("intensity", 0.5)
            if overall_sentiment == "negative" and sentiment_intensity > 0.6: sentiment_modifier = -0.1

            final_chance = min(max(base_chance + activity_bonus + topic_bonus + sentiment_modifier, 0.05), 0.8)
            if random.random() < final_chance:
                should_consider_responding = True
                consideration_reason = f"Contextual chance ({final_chance:.2f})"
            else:
                consideration_reason = f"Skipped (chance {final_chance:.2f})"

    print(f"Consideration check for message {message.id}: {should_consider_responding} (Reason: {consideration_reason})")

    if not should_consider_responding:
        return

    # --- Call AI and Handle Response ---
    cog.current_channel = message.channel # Ensure current channel is set for API calls/tools

    try:
        response_bundle = None
        if proactive_trigger_met:
            print(f"Calling get_proactive_ai_response for message {message.id} due to: {consideration_reason}")
            response_bundle = await get_proactive_ai_response(cog, message, consideration_reason)
        else:
            print(f"Calling get_ai_response for message {message.id}")
            response_bundle = await get_ai_response(cog, message)

        # --- Handle AI Response Bundle ---
        initial_response = response_bundle.get("initial_response")
        final_response = response_bundle.get("final_response")
        error_msg = response_bundle.get("error")
        fallback_initial = response_bundle.get("fallback_initial")

        if error_msg:
            print(f"Critical Error from AI response function: {error_msg}")
            # NEW LOGIC: Always send a notification if an error occurred here
            error_notification = f"Oops! Something went wrong while processing that. (`{error_msg[:100]}`)" # Include part of the error
            try:
                print('disabled error notification')
                #await message.channel.send(error_notification)
            except Exception as send_err:
                print(f"Failed to send error notification to channel: {send_err}")
            return # Still exit after handling the error

        # --- Process and Send Responses ---
        sent_any_message = False
        reacted = False

        # Helper function to handle sending a single response text and caching
        async def send_response_content(
            response_data: Optional[Dict[str, Any]],
            response_label: str,
            original_message: discord.Message # Add original message for context
        ) -> bool:
            nonlocal sent_any_message # Allow modification of the outer scope variable
            if not response_data or not isinstance(response_data, dict) or \
               not response_data.get("should_respond") or not response_data.get("content"):
                return False # Nothing to send

            response_text = response_data["content"]
            reply_to_id = response_data.get("reply_to_message_id")
            message_reference = None

            print(f"Preparing to send {response_label} content...")

            # --- Handle Reply ---
            if reply_to_id:
                try:
                    original_reply_msg = await original_message.channel.fetch_message(int(reply_to_id))
                    if original_reply_msg:
                        message_reference = original_reply_msg.to_reference(fail_if_not_exists=False) # Don't error if deleted
                        print(f"Will reply to message ID: {reply_to_id}")
                    else:
                        print(f"Warning: Could not fetch message {reply_to_id} to reply to.")
                except (ValueError, discord.NotFound, discord.Forbidden) as fetch_err:
                    print(f"Warning: Error fetching message {reply_to_id} to reply to: {fetch_err}")
                except Exception as e:
                     print(f"Unexpected error fetching reply message {reply_to_id}: {e}")


            # --- Handle Pings ---
            ping_matches = re.findall(r'\[PING:\s*([^\]]+)\s*\]', response_text)
            if ping_matches:
                print(f"Found ping placeholders: {ping_matches}")
                # Import get_user_id tool function dynamically or ensure it's accessible
                from .tools import get_user_id
                for user_name_to_ping in ping_matches:
                    user_id_result = await get_user_id(cog, user_name_to_ping.strip())
                    if user_id_result and user_id_result.get("status") == "success":
                        user_id_to_ping = user_id_result.get("user_id")
                        if user_id_to_ping:
                            response_text = response_text.replace(f'[PING: {user_name_to_ping}]', f'<@{user_id_to_ping}>', 1)
                            print(f"Replaced ping placeholder for '{user_name_to_ping}' with <@{user_id_to_ping}>")
                        else:
                             print(f"Warning: get_user_id succeeded for '{user_name_to_ping}' but returned no ID.")
                             response_text = response_text.replace(f'[PING: {user_name_to_ping}]', user_name_to_ping, 1) # Replace with name as fallback
                    else:
                        print(f"Warning: Could not find user ID for ping placeholder '{user_name_to_ping}'. Error: {user_id_result.get('error')}")
                        response_text = response_text.replace(f'[PING: {user_name_to_ping}]', user_name_to_ping, 1) # Replace with name as fallback

            # --- Send Message ---
            if len(response_text) > 1900:
                filepath = f'gurt_{response_label}_{original_message.id}.txt'
                try:
                    with open(filepath, 'w', encoding='utf-8') as f: f.write(response_text)
                    # Send file with reference if applicable
                    await original_message.channel.send(f"{response_label.capitalize()} response too long:", file=discord.File(filepath), reference=message_reference, mention_author=False)
                    sent_any_message = True
                    print(f"Sent {response_label} content as file (Reply: {bool(message_reference)}).")
                    return True
                except Exception as file_e: print(f"Error writing/sending long {response_label} response file: {file_e}")
                finally:
                    try: os.remove(filepath)
                    except OSError as os_e: print(f"Error removing temp file {filepath}: {os_e}")
            else:
                try:
                    async with original_message.channel.typing():
                        await simulate_human_typing(cog, original_message.channel, response_text) # Use simulation
                    # Send message with reference if applicable
                    sent_msg = await original_message.channel.send(response_text, reference=message_reference, mention_author=False) # mention_author=False is usually preferred for bots
                    sent_any_message = True
                    # Cache this bot response
                    bot_response_cache_entry = format_message(cog, sent_msg) # Pass cog
                    cog.message_cache['by_channel'][channel_id].append(bot_response_cache_entry)
                    cog.message_cache['global_recent'].append(bot_response_cache_entry)
                    cog.bot_last_spoke[channel_id] = time.time()
                    # Track participation topic
                    identified_topics = identify_conversation_topics(cog, [bot_response_cache_entry]) # Pass cog
                    if identified_topics:
                        topic = identified_topics[0]['topic'].lower().strip()
                        cog.gurt_participation_topics[topic] += 1
                        print(f"Tracked Gurt participation ({response_label}) in topic: '{topic}'")
                    print(f"Sent {response_label} content (Reply: {bool(message_reference)}).")
                    return True
                except Exception as send_e:
                    print(f"Error sending {response_label} content: {send_e}")
            return False

        # Send initial response content if valid
        # Pass the original message object 'message' here
        sent_initial_message = await send_response_content(initial_response, "initial", message)

        # Send final response content if valid (and different from initial, if initial was sent)
        sent_final_message = False
        initial_content = initial_response.get("content") if initial_response else None
        if final_response and (not sent_initial_message or initial_content != final_response.get("content")):
             # Pass the original message object 'message' here too
             sent_final_message = await send_response_content(final_response, "final", message)

        # Handle Reaction (prefer final response for reaction if it exists)
        reaction_source = final_response if final_response else initial_response
        if reaction_source and isinstance(reaction_source, dict):
            emoji_to_react = reaction_source.get("react_with_emoji")
            if emoji_to_react and isinstance(emoji_to_react, str):
                try:
                    # Basic validation for standard emoji
                    if 1 <= len(emoji_to_react) <= 4 and not re.match(r'<a?:.+?:\d+>', emoji_to_react):
                        # Only react if we haven't sent any message content (avoid double interaction)
                        if not sent_any_message:
                            await message.add_reaction(emoji_to_react)
                            reacted = True
                            print(f"Bot reacted to message {message.id} with {emoji_to_react}")
                        else:
                            print(f"Skipping reaction {emoji_to_react} because a message was already sent.")
                    else: print(f"Invalid emoji format: {emoji_to_react}")
                except Exception as e: print(f"Error adding reaction '{emoji_to_react}': {e}")

        # Log if response was intended but nothing was sent/reacted
        # Check if initial response intended action but nothing happened
        initial_intended_action = initial_response and initial_response.get("should_respond")
        initial_action_taken = sent_initial_message or (reacted and reaction_source == initial_response)
        # Check if final response intended action but nothing happened
        final_intended_action = final_response and final_response.get("should_respond")
        final_action_taken = sent_final_message or (reacted and reaction_source == final_response)

        if (initial_intended_action and not initial_action_taken) or \
           (final_intended_action and not final_action_taken):
             print(f"Warning: AI response intended action but nothing sent/reacted. Initial: {initial_response}, Final: {final_response}")

    except Exception as e:
        print(f"Exception in on_message listener main block: {str(e)}")
        import traceback
        traceback.print_exc()
        if bot_mentioned or replied_to_bot: # Check again in case error happened before response handling
            await message.channel.send(random.choice(["...", "*confused gurting*", "brain broke sorry"]))


@commands.Cog.listener()
async def on_reaction_add_listener(cog: 'GurtCog', reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
    """Listener function for on_reaction_add."""
    # Import necessary config/functions if not globally available
    from .config import EMOJI_SENTIMENT
    from .analysis import identify_conversation_topics

    if user.bot or reaction.message.author.id != cog.bot.user.id:
        return

    message_id = str(reaction.message.id)
    emoji_str = str(reaction.emoji)
    sentiment = "neutral"
    if emoji_str in EMOJI_SENTIMENT["positive"]: sentiment = "positive"
    elif emoji_str in EMOJI_SENTIMENT["negative"]: sentiment = "negative"

    if sentiment == "positive": cog.gurt_message_reactions[message_id]["positive"] += 1
    elif sentiment == "negative": cog.gurt_message_reactions[message_id]["negative"] += 1
    cog.gurt_message_reactions[message_id]["timestamp"] = time.time()

    if not cog.gurt_message_reactions[message_id].get("topic"):
        try:
            gurt_msg_data = next((msg for msg in cog.message_cache['global_recent'] if msg['id'] == message_id), None)
            if gurt_msg_data and gurt_msg_data['content']:
                identified_topics = identify_conversation_topics(cog, [gurt_msg_data]) # Pass cog
                if identified_topics:
                    topic = identified_topics[0]['topic'].lower().strip()
                    cog.gurt_message_reactions[message_id]["topic"] = topic
                    print(f"Reaction added to Gurt msg ({message_id}) on topic '{topic}'. Sentiment: {sentiment}")
                else: print(f"Reaction added to Gurt msg ({message_id}), topic unknown.")
            else: print(f"Reaction added, but Gurt msg {message_id} not in cache.")
        except Exception as e: print(f"Error determining topic for reaction on msg {message_id}: {e}")
    else: print(f"Reaction added to Gurt msg ({message_id}) on known topic '{cog.gurt_message_reactions[message_id]['topic']}'. Sentiment: {sentiment}")


@commands.Cog.listener()
async def on_reaction_remove_listener(cog: 'GurtCog', reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
    """Listener function for on_reaction_remove."""
    from .config import EMOJI_SENTIMENT # Import necessary config

    if user.bot or reaction.message.author.id != cog.bot.user.id:
        return

    message_id = str(reaction.message.id)
    emoji_str = str(reaction.emoji)
    sentiment = "neutral"
    if emoji_str in EMOJI_SENTIMENT["positive"]: sentiment = "positive"
    elif emoji_str in EMOJI_SENTIMENT["negative"]: sentiment = "negative"

    if message_id in cog.gurt_message_reactions:
        if sentiment == "positive": cog.gurt_message_reactions[message_id]["positive"] = max(0, cog.gurt_message_reactions[message_id]["positive"] - 1)
        elif sentiment == "negative": cog.gurt_message_reactions[message_id]["negative"] = max(0, cog.gurt_message_reactions[message_id]["negative"] - 1)
        print(f"Reaction removed from Gurt msg ({message_id}). Sentiment: {sentiment}")
