import discord
from discord.ext import commands
import random
import asyncio
import time
import re
import os # Added for file handling in error case
from typing import TYPE_CHECKING, Union, Dict, Any, Optional

# Relative imports
# Assuming api, utils, analysis functions are defined and imported correctly later
# We might need to adjust these imports based on final structure
# from .api import get_ai_response, get_proactive_ai_response
# from .utils import format_message, simulate_human_typing
# from .analysis import analyze_message_sentiment, update_conversation_sentiment

if TYPE_CHECKING:
    from .cog import WheatleyCog # Updated type hint

# Note: These listener functions need to be registered within the WheatleyCog class setup.
# They are defined here for separation but won't work standalone without being
# attached to the cog instance (e.g., self.bot.add_listener(on_message_listener(self), 'on_message')).

async def on_ready_listener(cog: 'WheatleyCog'): # Updated type hint
    """Listener function for on_ready."""
    print(f'Wheatley Bot is ready! Logged in as {cog.bot.user.name} ({cog.bot.user.id})') # Updated text
    print('------')

    # Now that the bot is ready, we can sync commands with Discord
    try:
        print("WheatleyCog: Syncing commands with Discord...") # Updated text
        synced = await cog.bot.tree.sync()
        print(f"WheatleyCog: Synced {len(synced)} command(s)") # Updated text

        # List the synced commands
        wheatley_commands = [cmd.name for cmd in cog.bot.tree.get_commands() if cmd.name.startswith("wheatley")] # Updated prefix check
        print(f"WheatleyCog: Available Wheatley commands: {', '.join(wheatley_commands)}") # Updated text
    except Exception as e:
        print(f"WheatleyCog: Failed to sync commands: {e}") # Updated text
        import traceback
        traceback.print_exc()

async def on_message_listener(cog: 'WheatleyCog', message: discord.Message): # Updated type hint
    """Listener function for on_message."""
    # Import necessary functions dynamically or ensure they are passed/accessible via cog
    from .api import get_ai_response, get_proactive_ai_response
    from .utils import format_message, simulate_human_typing
    from .analysis import analyze_message_sentiment, update_conversation_sentiment, identify_conversation_topics
    # Removed WHEATLEY_RESPONSES import, can be added back if simple triggers are needed

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

        # --- Removed Relationship Strength Updates ---

        # Analyze message sentiment and update conversation sentiment tracking (Kept for context)
        if message.content:
            message_sentiment = analyze_message_sentiment(cog, message.content) # Use analysis function
            update_conversation_sentiment(cog, channel_id, str(user_id), message_sentiment) # Use analysis function

        # --- Add message to semantic memory (Kept for context) ---
        if message.content and cog.memory_manager.semantic_collection:
            semantic_metadata = {
                "user_id": str(user_id), "user_name": message.author.name, "display_name": message.author.display_name,
                "channel_id": str(channel_id), "channel_name": getattr(message.channel, 'name', 'DM'),
                "guild_id": str(message.guild.id) if message.guild else None,
                "timestamp": message.created_at.timestamp()
            }
            asyncio.create_task(
                cog.memory_manager.add_message_embedding(
                    message_id=str(message.id), text=message.content, metadata=semantic_metadata
                )
            )

    except Exception as e:
        print(f"Error during message caching/tracking/embedding: {e}")
    # --- End Caching & Embedding ---

    # Check conditions for potentially responding
    bot_mentioned = cog.bot.user.mentioned_in(message)
    replied_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == cog.bot.user
    wheatley_in_message = "wheatley" in message.content.lower() # Changed variable name
    now = time.time()
    time_since_last_activity = now - cog.channel_activity.get(channel_id, 0)
    time_since_bot_spoke = now - cog.bot_last_spoke.get(channel_id, 0)

    should_consider_responding = False
    consideration_reason = "Default"
    proactive_trigger_met = False

    if bot_mentioned or replied_to_bot or wheatley_in_message: # Changed variable name
        should_consider_responding = True
        consideration_reason = "Direct mention/reply/name"
    else:
        # --- Proactive Engagement Triggers (Simplified for Wheatley) ---
        from .config import (PROACTIVE_LULL_THRESHOLD, PROACTIVE_BOT_SILENCE_THRESHOLD, PROACTIVE_LULL_CHANCE,
                             PROACTIVE_TOPIC_RELEVANCE_THRESHOLD, PROACTIVE_TOPIC_CHANCE,
                             # Removed Relationship/Interest/Goal proactive configs
                             PROACTIVE_SENTIMENT_SHIFT_THRESHOLD, PROACTIVE_SENTIMENT_DURATION_THRESHOLD,
                             PROACTIVE_SENTIMENT_CHANCE)

        # 1. Lull Trigger (Kept)
        if time_since_last_activity > PROACTIVE_LULL_THRESHOLD and time_since_bot_spoke > PROACTIVE_BOT_SILENCE_THRESHOLD:
            # Check if there's *any* recent message context to potentially respond to
            has_relevant_context = bool(cog.message_cache['by_channel'].get(channel_id))
            if has_relevant_context and random.random() < PROACTIVE_LULL_CHANCE:
                should_consider_responding = True
                proactive_trigger_met = True
                consideration_reason = f"Proactive: Lull ({time_since_last_activity:.0f}s idle, bot silent {time_since_bot_spoke:.0f}s)"

        # 2. Topic Relevance Trigger (Kept - uses semantic memory)
        if not proactive_trigger_met and message.content and cog.memory_manager.semantic_collection:
            try:
                semantic_results = await cog.memory_manager.search_semantic_memory(query_text=message.content, n_results=1)
                if semantic_results:
                    # Distance is often used, lower is better. Convert to similarity if needed.
                    # Assuming distance is 0 (identical) to 2 (opposite). Similarity = 1 - (distance / 2)
                    distance = semantic_results[0].get('distance', 2.0) # Default to max distance
                    similarity_score = max(0.0, 1.0 - (distance / 2.0)) # Calculate similarity

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

        # 3. Relationship Score Trigger (REMOVED)

        # 4. Sentiment Shift Trigger (Kept)
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

        # 5. User Interest Trigger (REMOVED)
        # 6. Active Goal Relevance Trigger (REMOVED)

        # --- Fallback Contextual Chance (Simplified - No Chattiness Trait) ---
        if not should_consider_responding:
            # Base chance can be a fixed value or slightly randomized
            base_chance = 0.1 # Lower base chance without personality traits
            activity_bonus = 0
            if time_since_last_activity > 120: activity_bonus += 0.05 # Smaller bonus
            if time_since_bot_spoke > 300: activity_bonus += 0.05 # Smaller bonus
            topic_bonus = 0
            active_channel_topics = cog.active_topics.get(channel_id, {}).get("topics", [])
            if message.content and active_channel_topics:
                topic_keywords = set(t['topic'].lower() for t in active_channel_topics)
                message_words = set(re.findall(r'\b\w+\b', message.content.lower()))
                if topic_keywords.intersection(message_words): topic_bonus += 0.10 # Smaller bonus
            sentiment_modifier = 0
            channel_sentiment_data = cog.conversation_sentiment.get(channel_id, {})
            overall_sentiment = channel_sentiment_data.get("overall", "neutral")
            sentiment_intensity = channel_sentiment_data.get("intensity", 0.5)
            if overall_sentiment == "negative" and sentiment_intensity > 0.6: sentiment_modifier = -0.05 # Smaller penalty

            final_chance = min(max(base_chance + activity_bonus + topic_bonus + sentiment_modifier, 0.02), 0.3) # Lower max chance
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
            error_notification = f"Bollocks! Something went sideways processing that. (`{error_msg[:100]}`)" # Updated text
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
        async def send_response_content(response_data: Optional[Dict[str, Any]], response_label: str) -> bool:
            nonlocal sent_any_message # Allow modification of the outer scope variable
            if response_data and isinstance(response_data, dict) and \
               response_data.get("should_respond") and response_data.get("content"):
                response_text = response_data["content"]
                print(f"Attempting to send {response_label} content...")
                if len(response_text) > 1900:
                    filepath = f'wheatley_{response_label}_{message.id}.txt' # Changed filename prefix
                    try:
                        with open(filepath, 'w', encoding='utf-8') as f: f.write(response_text)
                        await message.channel.send(f"{response_label.capitalize()} response too long, have a look at this:", file=discord.File(filepath)) # Updated text
                        sent_any_message = True
                        print(f"Sent {response_label} content as file.")
                        return True
                    except Exception as file_e: print(f"Error writing/sending long {response_label} response file: {file_e}")
                    finally:
                        try: os.remove(filepath)
                        except OSError as os_e: print(f"Error removing temp file {filepath}: {os_e}")
                else:
                    try:
                        async with message.channel.typing():
                            await simulate_human_typing(cog, message.channel, response_text) # Use simulation
                        sent_msg = await message.channel.send(response_text)
                        sent_any_message = True
                        # Cache this bot response
                        bot_response_cache_entry = format_message(cog, sent_msg)
                        cog.message_cache['by_channel'][channel_id].append(bot_response_cache_entry)
                        cog.message_cache['global_recent'].append(bot_response_cache_entry)
                        cog.bot_last_spoke[channel_id] = time.time()
                        # Track participation topic - NOTE: Participation tracking might be removed for Wheatley
                        # identified_topics = identify_conversation_topics(cog, [bot_response_cache_entry])
                        # if identified_topics:
                        #     topic = identified_topics[0]['topic'].lower().strip()
                        #     cog.wheatley_participation_topics[topic] += 1 # Changed attribute name
                        #     print(f"Tracked Wheatley participation ({response_label}) in topic: '{topic}'") # Changed text
                        print(f"Sent {response_label} content.")
                        return True
                    except Exception as send_e:
                        print(f"Error sending {response_label} content: {send_e}")
            return False

        # Send initial response content if valid
        sent_initial_message = await send_response_content(initial_response, "initial")

        # Send final response content if valid (and different from initial, if initial was sent)
        sent_final_message = False
        # Ensure initial_response exists before accessing its content for comparison
        initial_content = initial_response.get("content") if initial_response else None
        if final_response and (not sent_initial_message or initial_content != final_response.get("content")):
             sent_final_message = await send_response_content(final_response, "final")

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
            await message.channel.send(random.choice(["Uh oh.", "What was that?", "Did I break it?", "Bollocks!", "That wasn't supposed to happen."])) # Changed fallback


@commands.Cog.listener()
async def on_reaction_add_listener(cog: 'WheatleyCog', reaction: discord.Reaction, user: Union[discord.Member, discord.User]): # Updated type hint
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

    if sentiment == "positive": cog.wheatley_message_reactions[message_id]["positive"] += 1 # Changed attribute name
    elif sentiment == "negative": cog.wheatley_message_reactions[message_id]["negative"] += 1 # Changed attribute name
    cog.wheatley_message_reactions[message_id]["timestamp"] = time.time() # Changed attribute name

    # Topic identification for reactions might be less relevant for Wheatley, but kept for now
    if not cog.wheatley_message_reactions[message_id].get("topic"): # Changed attribute name
        try:
            # Changed variable name
            wheatley_msg_data = next((msg for msg in cog.message_cache['global_recent'] if msg['id'] == message_id), None)
            if wheatley_msg_data and wheatley_msg_data['content']: # Changed variable name
                identified_topics = identify_conversation_topics(cog, [wheatley_msg_data]) # Pass cog, changed variable name
                if identified_topics:
                    topic = identified_topics[0]['topic'].lower().strip()
                    cog.wheatley_message_reactions[message_id]["topic"] = topic # Changed attribute name
                    print(f"Reaction added to Wheatley msg ({message_id}) on topic '{topic}'. Sentiment: {sentiment}") # Changed text
                else: print(f"Reaction added to Wheatley msg ({message_id}), topic unknown.") # Changed text
            else: print(f"Reaction added, but Wheatley msg {message_id} not in cache.") # Changed text
        except Exception as e: print(f"Error determining topic for reaction on msg {message_id}: {e}")
    else: print(f"Reaction added to Wheatley msg ({message_id}) on known topic '{cog.wheatley_message_reactions[message_id]['topic']}'. Sentiment: {sentiment}") # Changed text, attribute name


@commands.Cog.listener()
async def on_reaction_remove_listener(cog: 'WheatleyCog', reaction: discord.Reaction, user: Union[discord.Member, discord.User]): # Updated type hint
    """Listener function for on_reaction_remove."""
    from .config import EMOJI_SENTIMENT # Import necessary config

    if user.bot or reaction.message.author.id != cog.bot.user.id:
        return

    message_id = str(reaction.message.id)
    emoji_str = str(reaction.emoji)
    sentiment = "neutral"
    if emoji_str in EMOJI_SENTIMENT["positive"]: sentiment = "positive"
    elif emoji_str in EMOJI_SENTIMENT["negative"]: sentiment = "negative"

    if message_id in cog.wheatley_message_reactions: # Changed attribute name
        if sentiment == "positive": cog.wheatley_message_reactions[message_id]["positive"] = max(0, cog.wheatley_message_reactions[message_id]["positive"] - 1) # Changed attribute name
        elif sentiment == "negative": cog.wheatley_message_reactions[message_id]["negative"] = max(0, cog.wheatley_message_reactions[message_id]["negative"] - 1) # Changed attribute name
        print(f"Reaction removed from Wheatley msg ({message_id}). Sentiment: {sentiment}") # Changed text
