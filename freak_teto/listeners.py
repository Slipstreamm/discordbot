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
    from .cog import FreakTetoCog # For type hinting - Updated

# Note: These listener functions need to be registered within the FreakTetoCog class setup. # Updated comment
# They are defined here for separation but won't work standalone without being
# attached to the cog instance (e.g., self.bot.add_listener(on_message_listener(self), 'on_message')).

async def on_ready_listener(cog: 'FreakTetoCog'): # Updated type hint
    """Listener function for on_ready."""
    print(f'Freak Teto Bot is ready! Logged in as {cog.bot.user.name} ({cog.bot.user.id})') # Updated log
    print('------')

    # Now that the bot is ready, we can sync commands with Discord
    try:
        print("FreakTetoCog: Syncing commands with Discord...") # Updated log
        synced = await cog.bot.tree.sync()
        print(f"FreakTetoCog: Synced {len(synced)} command(s)") # Updated log

        # List the synced commands
        freak_teto_commands = [cmd.name for cmd in cog.bot.tree.get_commands() if cmd.name.startswith("freakteto")] # Updated filter and variable name
        print(f"FreakTetoCog: Available Freak Teto commands: {', '.join(freak_teto_commands)}") # Updated log
    except Exception as e:
        print(f"FreakTetoCog: Failed to sync commands: {e}") # Updated log
        import traceback
        traceback.print_exc()

    # --- Message history pre-loading removed ---


async def on_message_listener(cog: 'FreakTetoCog', message: discord.Message): # Updated type hint
    """Listener function for on_message."""
    # Import necessary functions dynamically or ensure they are passed/accessible via cog
    from .api import get_ai_response, get_proactive_ai_response # Ensure these are refactored if needed
    from .utils import format_message, simulate_human_typing # Ensure these are refactored if needed
    from .analysis import analyze_message_sentiment, update_conversation_sentiment, identify_conversation_topics # Ensure these are refactored if needed
    # from .config import GURT_RESPONSES # Removed GURT_RESPONSES import

    # Don't respond to our own messages
    if message.author == cog.bot.user:
        return

    # Don't process commands here
    if message.content.startswith(cog.bot.command_prefix):
        return

    # --- Cache and Track Incoming Message ---
    try:
        # Ensure format_message uses the FreakTetoCog instance correctly
        formatted_message = format_message(cog, message)
        channel_id = message.channel.id
        user_id = message.author.id
        thread_id = message.channel.id if isinstance(message.channel, discord.Thread) else None

        # Update caches (accessing cog's state)
        # Deduplicate by message ID before appending
        def _dedup_and_append(cache_deque, msg):
            if not any(m.get("id") == msg.get("id") for m in cache_deque):
                cache_deque.append(msg)

        _dedup_and_append(cog.message_cache['by_channel'][channel_id], formatted_message)
        _dedup_and_append(cog.message_cache['by_user'][user_id], formatted_message)
        _dedup_and_append(cog.message_cache['global_recent'], formatted_message)
        if thread_id:
            _dedup_and_append(cog.message_cache['by_thread'][thread_id], formatted_message)
        if cog.bot.user.mentioned_in(message):
            _dedup_and_append(cog.message_cache['mentioned'], formatted_message)

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
            # Ensure analysis uses FreakTetoCog instance correctly
            message_sentiment_data = analyze_message_sentiment(cog, message.content)
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
            # Ensure analysis uses FreakTetoCog instance correctly
            message_sentiment = analyze_message_sentiment(cog, message.content)
            update_conversation_sentiment(cog, channel_id, str(user_id), message_sentiment)

        # --- Add message to semantic memory ---
        # Ensure MemoryManager instance uses FreakTeto DB paths
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


    # Simple response removed

    # Check conditions for potentially responding
    bot_mentioned = cog.bot.user.mentioned_in(message)
    replied_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user
    # Check for "teto" or "freak teto"
    teto_in_message = "teto" in message.content.lower() or "freak teto" in message.content.lower()
    now = time.time()
    time_since_last_activity = now - cog.channel_activity.get(channel_id, 0)
    time_since_bot_spoke = now - cog.bot_last_spoke.get(channel_id, 0)

    should_consider_responding = False
    consideration_reason = "Default"
    proactive_trigger_met = False

    if bot_mentioned or replied_to_bot or teto_in_message: # Use teto_in_message
        should_consider_responding = True
        consideration_reason = "Direct mention/reply/name"
    else:
        # --- Proactive Engagement Triggers --- (Keep logic, LLM prompt handles persona interpretation)
        # Ensure config imports FreakTeto specific values if they differ
        from .config import (PROACTIVE_LULL_THRESHOLD, PROACTIVE_BOT_SILENCE_THRESHOLD, PROACTIVE_LULL_CHANCE,
                             PROACTIVE_TOPIC_RELEVANCE_THRESHOLD, PROACTIVE_TOPIC_CHANCE,
                             PROACTIVE_RELATIONSHIP_SCORE_THRESHOLD, PROACTIVE_RELATIONSHIP_CHANCE,
                             PROACTIVE_SENTIMENT_SHIFT_THRESHOLD, PROACTIVE_SENTIMENT_DURATION_THRESHOLD,
                             PROACTIVE_SENTIMENT_CHANCE, PROACTIVE_USER_INTEREST_THRESHOLD,
                             PROACTIVE_USER_INTEREST_CHANCE)

        # 1. Lull Trigger
        if time_since_last_activity > PROACTIVE_LULL_THRESHOLD and time_since_bot_spoke > PROACTIVE_BOT_SILENCE_THRESHOLD:
            # Ensure MemoryManager uses FreakTeto DB paths
            has_relevant_context = bool(cog.active_topics.get(channel_id, {}).get("topics", [])) or \
                                   bool(await cog.memory_manager.get_general_facts(limit=1))
            if has_relevant_context and random.random() < PROACTIVE_LULL_CHANCE:
                should_consider_responding = True
                proactive_trigger_met = True
                consideration_reason = f"Proactive: Lull ({time_since_last_activity:.0f}s idle, bot silent {time_since_bot_spoke:.0f}s)"

        # 2. Topic Relevance Trigger
        # Ensure MemoryManager uses FreakTeto DB paths
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
                        # Log potentially adjusted for FreakTeto if needed
                        print(f"Topic relevance trigger skipped (Sim {similarity_score:.2f} < {PROACTIVE_TOPIC_RELEVANCE_THRESHOLD} or Chance {PROACTIVE_TOPIC_CHANCE}).")
            except Exception as semantic_e:
                print(f"Error during semantic search for topic trigger: {semantic_e}")

        # 3. Relationship Score Trigger
        # Ensure user_relationships uses FreakTeto data
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
                        # Log potentially adjusted
                        print(f"Relationship trigger skipped by chance ({PROACTIVE_RELATIONSHIP_CHANCE}). Score: {relationship_score:.1f}")
            except Exception as rel_e:
                print(f"Error during relationship trigger check: {rel_e}")

        # 4. Sentiment Shift Trigger
        # Ensure conversation_sentiment uses FreakTeto data
        if not proactive_trigger_met:
            channel_sentiment_data = cog.conversation_sentiment.get(channel_id, {})
            overall_sentiment = channel_sentiment_data.get("overall", "neutral")
            sentiment_intensity = channel_sentiment_data.get("intensity", 0.5)
            sentiment_last_update = channel_sentiment_data.get("last_update", 0)
            sentiment_duration = now - sentiment_last_update

            if overall_sentiment != "neutral" and \
               sentiment_intensity >= PROACTIVE_SENTIMENT_SHIFT_THRESHOLD and \
               sentiment_duration >= PROACTIVE_SENTIMENT_DURATION_THRESHOLD and \
               time_since_bot_spoke > 180:
                if random.random() < PROACTIVE_SENTIMENT_CHANCE:
                    should_consider_responding = True
                    proactive_trigger_met = True
                    consideration_reason = f"Proactive: Sentiment Shift ({overall_sentiment}, Intensity: {sentiment_intensity:.2f}, Duration: {sentiment_duration:.0f}s)"
                    print(f"Sentiment Shift trigger met for channel {channel_id}. Sentiment: {overall_sentiment}, Intensity: {sentiment_intensity:.2f}, Duration: {sentiment_duration:.0f}s")
                else:
                     # Log potentially adjusted
                    print(f"Sentiment Shift trigger skipped by chance ({PROACTIVE_SENTIMENT_CHANCE}). Sentiment: {overall_sentiment}")

        # 5. User Interest Trigger (Based on Freak Teto's interests)
        if not proactive_trigger_met and message.content:
            try:
                # Ensure memory_manager fetches Teto's interests
                teto_interests = await cog.memory_manager.get_interests(limit=10, min_level=PROACTIVE_USER_INTEREST_THRESHOLD)
                if teto_interests:
                    message_content_lower = message.content.lower()
                    mentioned_interest = None
                    for interest_topic, interest_level in teto_interests:
                        # Simple check if interest topic is in message
                        if re.search(r'\b' + re.escape(interest_topic.lower()) + r'\b', message_content_lower):
                            mentioned_interest = interest_topic
                            break # Found a mentioned interest

                    if mentioned_interest and time_since_bot_spoke > 90:  # Bot hasn't spoken recently
                        if random.random() < PROACTIVE_USER_INTEREST_CHANCE:
                            should_consider_responding = True
                            proactive_trigger_met = True
                            consideration_reason = f"Proactive: Freak Teto Interest Mentioned ('{mentioned_interest}')" # Updated log message
                            print(f"Freak Teto Interest trigger met for message {message.id}. Interest: '{mentioned_interest}'") # Updated log
                        else:
                            print(f"Freak Teto Interest trigger skipped by chance ({PROACTIVE_USER_INTEREST_CHANCE}). Interest: '{mentioned_interest}'") # Updated log
            except Exception as interest_e:
                print(f"Error during Freak Teto Interest trigger check: {interest_e}") # Updated log

        # 6. Active Goal Relevance Trigger
        if not proactive_trigger_met and message.content:
            try:
                # Ensure memory_manager uses FreakTeto DB paths
                active_goals = await cog.memory_manager.get_goals(status='active', limit=2)
                if active_goals:
                    message_content_lower = message.content.lower()
                    relevant_goal = None
                    for goal in active_goals:
                        goal_keywords = set(re.findall(r'\b\w{3,}\b', goal.get('description', '').lower()))
                        message_words = set(re.findall(r'\b\w{3,}\b', message_content_lower))
                        if len(goal_keywords.intersection(message_words)) > 1:
                            relevant_goal = goal
                            break

                    if relevant_goal and time_since_bot_spoke > 120:
                        goal_relevance_chance = PROACTIVE_USER_INTEREST_CHANCE * 1.2
                        if random.random() < goal_relevance_chance:
                            should_consider_responding = True
                            proactive_trigger_met = True
                            goal_desc_short = relevant_goal.get('description', 'N/A')[:40]
                            consideration_reason = f"Proactive: Relevant Active Goal ('{goal_desc_short}...')"
                            print(f"Active Goal trigger met for message {message.id}. Goal ID: {relevant_goal.get('goal_id')}")
                        else:
                             # Log potentially adjusted
                            print(f"Active Goal trigger skipped by chance ({goal_relevance_chance:.2f}).")
            except Exception as goal_trigger_e:
                print(f"Error during Active Goal trigger check: {goal_trigger_e}")


        # --- Fallback Contextual Chance ---
        if not should_consider_responding:
            # Ensure MemoryManager uses FreakTeto DB paths
            persistent_traits = await cog.memory_manager.get_all_personality_traits()
            # Use FreakTeto's baseline 'helpfulness' or 'friendliness' instead of 'chattiness'
            helpfulness_trait = persistent_traits.get('helpfulness', 0.8) # Default Teto helpfulness

            base_chance = helpfulness_trait * 0.2 # Lower base chance for Teto?
            activity_bonus = 0
            if time_since_last_activity > 180: activity_bonus += 0.05 # Slightly less eager on lull
            if time_since_bot_spoke > 400: activity_bonus += 0.1
            topic_bonus = 0
            active_channel_topics = cog.active_topics.get(channel_id, {}).get("topics", [])
            if message.content and active_channel_topics:
                topic_keywords = set(t['topic'].lower() for t in active_channel_topics)
                message_words = set(re.findall(r'\b\w+\b', message.content.lower()))
                if topic_keywords.intersection(message_words): topic_bonus += 0.10 # Lower bonus for topic match?
            sentiment_modifier = 0
            channel_sentiment_data = cog.conversation_sentiment.get(channel_id, {})
            overall_sentiment = channel_sentiment_data.get("overall", "neutral")
            sentiment_intensity = channel_sentiment_data.get("intensity", 0.5)
            # Teto might be less likely to respond negatively
            if overall_sentiment == "negative" and sentiment_intensity > 0.6: sentiment_modifier = -0.15

            final_chance = min(max(base_chance + activity_bonus + topic_bonus + sentiment_modifier, 0.02), 0.5) # Lower max chance?
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
        # Ensure API calls use FreakTetoCog instance
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
            # Updated error notification for Teto
            error_notification = f"Ah! Master, something went wrong while I was thinking... (`{error_msg[:100]}`)"
            try:
                await message.channel.send(error_notification)
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
            original_message: discord.Message
        ) -> bool:
            nonlocal sent_any_message
            if not response_data or not isinstance(response_data, dict) or \
               not response_data.get("should_respond") or not response_data.get("content"):
                return False

            response_text = response_data["content"]
            reply_to_id = response_data.get("reply_to_message_id")
            message_reference = None

            print(f"Preparing to send {response_label} content...")

            # --- Handle Reply (Logic remains the same) ---
            if reply_to_id and isinstance(reply_to_id, str) and reply_to_id.isdigit():
                try:
                    original_reply_msg = await original_message.channel.fetch_message(int(reply_to_id))
                    if original_reply_msg:
                        message_reference = original_reply_msg.to_reference(fail_if_not_exists=False)
                        print(f"Will reply to message ID: {reply_to_id}")
                    else:
                        print(f"Warning: Could not fetch message {reply_to_id} to reply to.")
                except (ValueError, discord.NotFound, discord.Forbidden) as fetch_err:
                    print(f"Warning: Error fetching message {reply_to_id} to reply to: {fetch_err}")
                except Exception as e:
                     print(f"Unexpected error fetching reply message {reply_to_id}: {e}")
            elif reply_to_id:
                print(f"Warning: Invalid reply_to_id format received: {reply_to_id}")


            # --- Handle Pings (Logic remains the same, uses get_user_id tool) ---
            ping_matches = re.findall(r'\[PING:\s*([^\]]+)\s*\]', response_text)
            if ping_matches:
                print(f"Found ping placeholders: {ping_matches}")
                # Ensure tools uses FreakTetoCog instance
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
                             response_text = response_text.replace(f'[PING: {user_name_to_ping}]', user_name_to_ping, 1)
                    else:
                        print(f"Warning: Could not find user ID for ping placeholder '{user_name_to_ping}'. Error: {user_id_result.get('error')}")
                        response_text = response_text.replace(f'[PING: {user_name_to_ping}]', user_name_to_ping, 1)

            # --- Send Message ---
            if len(response_text) > 1900:
                # Update filepath name
                filepath = f'freak_teto_{response_label}_{original_message.id}.txt'
                try:
                    with open(filepath, 'w', encoding='utf-8') as f: f.write(response_text)
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
                    # Ensure utils uses FreakTetoCog instance
                    async with original_message.channel.typing():
                        await simulate_human_typing(cog, original_message.channel, response_text)
                    sent_msg = await original_message.channel.send(response_text, reference=message_reference, mention_author=False)
                    sent_any_message = True
                    # Cache this bot response using FreakTetoCog
                    bot_response_cache_entry = format_message(cog, sent_msg)
                    cog.message_cache['by_channel'][channel_id].append(bot_response_cache_entry)
                    cog.message_cache['global_recent'].append(bot_response_cache_entry)
                    cog.bot_last_spoke[channel_id] = time.time()
                    # Track participation topic using FreakTetoCog
                    # Ensure analysis uses FreakTetoCog instance
                    identified_topics = identify_conversation_topics(cog, [bot_response_cache_entry])
                    if identified_topics:
                        topic = identified_topics[0]['topic'].lower().strip()
                        # Use renamed state var for FreakTeto
                        cog.freak_teto_participation_topics[topic] += 1 # Use renamed state var
                        # Update log message
                        print(f"Tracked Freak Teto participation ({response_label}) in topic: '{topic}'")
                    print(f"Sent {response_label} content (Reply: {bool(message_reference)}).")
                    return True
                except Exception as send_e:
                    print(f"Error sending {response_label} content: {send_e}")
            return False

        # Send initial response content if valid
        sent_initial_message = await send_response_content(initial_response, "initial", message)

        # Send final response content if valid
        sent_final_message = False
        initial_content = initial_response.get("content") if initial_response else None
        if final_response and (not sent_initial_message or initial_content != final_response.get("content")):
             sent_final_message = await send_response_content(final_response, "final", message)

        # Handle Reaction (Logic remains same)
        reaction_source = final_response if final_response else initial_response
        if reaction_source and isinstance(reaction_source, dict):
            emoji_to_react = reaction_source.get("react_with_emoji")
            if emoji_to_react and isinstance(emoji_to_react, str):
                try:
                    if 1 <= len(emoji_to_react) <= 4 and not re.match(r'<a?:.+?:\d+>', emoji_to_react):
                        if not sent_any_message:
                            await message.add_reaction(emoji_to_react)
                            reacted = True
                            print(f"Bot reacted to message {message.id} with {emoji_to_react}")
                        else:
                            print(f"Skipping reaction {emoji_to_react} because a message was already sent.")
                    else: print(f"Invalid emoji format: {emoji_to_react}")
                except Exception as e: print(f"Error adding reaction '{emoji_to_react}': {e}")

        # Log if response was intended but nothing happened (Logic remains same)
        initial_intended_action = initial_response and initial_response.get("should_respond")
        initial_action_taken = sent_initial_message or (reacted and reaction_source == initial_response)
        final_intended_action = final_response and final_response.get("should_respond")
        final_action_taken = sent_final_message or (reacted and reaction_source == final_response)

        if (initial_intended_action and not initial_action_taken) or \
           (final_intended_action and not final_action_taken):
             print(f"Warning: AI response intended action but nothing sent/reacted. Initial: {initial_response}, Final: {final_response}")

    except Exception as e:
        print(f"Exception in on_message listener main block: {str(e)}")
        import traceback
        traceback.print_exc()
        if bot_mentioned or replied_to_bot:
            # Updated fallback message for Teto
            await message.channel.send(random.choice(["Hmm?", "I'm sorry, Master, I seem to be malfunctioning...", "...", "🍞?"]))


@commands.Cog.listener()
# Update type hint and variable names for FreakTeto
async def on_reaction_add_listener(cog: 'FreakTetoCog', reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
    """Listener function for on_reaction_add."""
    from .config import EMOJI_SENTIMENT
    # Ensure analysis uses FreakTetoCog instance
    from .analysis import identify_conversation_topics

    if user.bot or reaction.message.author.id != cog.bot.user.id:
        return

    message_id = str(reaction.message.id)
    emoji_str = str(reaction.emoji)
    sentiment = "neutral"
    if emoji_str in EMOJI_SENTIMENT["positive"]: sentiment = "positive"
    elif emoji_str in EMOJI_SENTIMENT["negative"]: sentiment = "negative"

    # Use renamed state var for FreakTeto
    reaction_state = cog.freak_teto_message_reactions[message_id]

    if sentiment == "positive": reaction_state["positive"] += 1
    elif sentiment == "negative": reaction_state["negative"] += 1
    reaction_state["timestamp"] = time.time()

    if not reaction_state.get("topic"):
        try:
            # Ensure message cache is FreakTeto's
            teto_msg_data = next((msg for msg in cog.message_cache['global_recent'] if msg['id'] == message_id), None)
            if teto_msg_data and teto_msg_data['content']:
                # Ensure analysis uses FreakTetoCog instance
                identified_topics = identify_conversation_topics(cog, [teto_msg_data])
                if identified_topics:
                    topic = identified_topics[0]['topic'].lower().strip()
                    reaction_state["topic"] = topic
                    # Update log message
                    print(f"Reaction added to Freak Teto msg ({message_id}) on topic '{topic}'. Sentiment: {sentiment}")
                else: print(f"Reaction added to Freak Teto msg ({message_id}), topic unknown.") # Update log
            else: print(f"Reaction added, but Freak Teto msg {message_id} not in cache.") # Update log
        except Exception as e: print(f"Error determining topic for reaction on msg {message_id}: {e}")
    else: print(f"Reaction added to Freak Teto msg ({message_id}) on known topic '{reaction_state['topic']}'. Sentiment: {sentiment}") # Update log


@commands.Cog.listener()
# Update type hint and variable names for FreakTeto
async def on_reaction_remove_listener(cog: 'FreakTetoCog', reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
    """Listener function for on_reaction_remove."""
    from .config import EMOJI_SENTIMENT

    if user.bot or reaction.message.author.id != cog.bot.user.id:
        return

    message_id = str(reaction.message.id)
    emoji_str = str(reaction.emoji)
    sentiment = "neutral"
    if emoji_str in EMOJI_SENTIMENT["positive"]: sentiment = "positive"
    elif emoji_str in EMOJI_SENTIMENT["negative"]: sentiment = "negative"

    # Use renamed state var for FreakTeto
    if message_id in cog.freak_teto_message_reactions:
        reaction_state = cog.freak_teto_message_reactions[message_id]
        if sentiment == "positive": reaction_state["positive"] = max(0, reaction_state["positive"] - 1)
        elif sentiment == "negative": reaction_state["negative"] = max(0, reaction_state["negative"] - 1)
        # Update log message
        print(f"Reaction removed from Freak Teto msg ({message_id}). Sentiment: {sentiment}")
