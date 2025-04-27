import discord
from discord.ext import commands
import random
import asyncio
import time
import re
import os # Added for file handling in error case
from typing import TYPE_CHECKING, Union, Dict, Any

# Relative imports
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
            asyncio.create_task(
                cog.memory_manager.add_message_embedding(
                    message_id=str(message.id), text=message.content, metadata=semantic_metadata
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
                             PROACTIVE_RELATIONSHIP_SCORE_THRESHOLD, PROACTIVE_RELATIONSHIP_CHANCE)

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
                        else: print(f"Topic relevance trigger skipped by chance ({PROACTIVE_TOPIC_CHANCE}). Sim: {similarity_score:.2f}")
            except Exception as semantic_e: print(f"Error during semantic search for topic trigger: {semantic_e}")

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
                    else: print(f"Relationship trigger skipped by chance ({PROACTIVE_RELATIONSHIP_CHANCE}). Score: {relationship_score:.1f}")
            except Exception as rel_e: print(f"Error during relationship trigger check: {rel_e}")

        # --- Fallback Contextual Chance ---
        if not should_consider_responding: # Check if already decided to respond
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
            if fallback_initial and (bot_mentioned or replied_to_bot):
                initial_response = fallback_initial
            elif bot_mentioned or replied_to_bot:
                await message.channel.send(random.choice(["...", "*confused gurting*", "brain broke sorry"]))
            return

        # Determine which response to use (prefer final if available)
        response_to_use = final_response if final_response else initial_response

        if response_to_use and isinstance(response_to_use, dict):
            sent_message = False
            reacted = False

            # Handle Reaction
            emoji_to_react = response_to_use.get("react_with_emoji")
            if emoji_to_react and isinstance(emoji_to_react, str):
                try:
                    # Basic validation for standard emoji
                    if 1 <= len(emoji_to_react) <= 4 and not re.match(r'<a?:.+?:\d+>', emoji_to_react):
                        await message.add_reaction(emoji_to_react)
                        reacted = True
                        print(f"Bot reacted to message {message.id} with {emoji_to_react}")
                    else: print(f"Invalid emoji format: {emoji_to_react}")
                except Exception as e: print(f"Error adding reaction '{emoji_to_react}': {e}")

            # Handle Text Response
            if response_to_use.get("should_respond") and response_to_use.get("content"):
                response_text = response_to_use["content"]
                if len(response_text) > 1900:
                    filepath = f'gurt_response_{message.id}.txt'
                    try:
                        with open(filepath, 'w', encoding='utf-8') as f: f.write(response_text)
                        await message.channel.send("Response too long:", file=discord.File(filepath))
                        sent_message = True
                    except Exception as file_e: print(f"Error writing/sending long response file: {file_e}")
                    finally:
                        try: os.remove(filepath)
                        except OSError as os_e: print(f"Error removing temp file {filepath}: {os_e}")
                else:
                    async with message.channel.typing():
                        await simulate_human_typing(cog, message.channel, response_text) # Use simulation
                    sent_msg = await message.channel.send(response_text)
                    sent_message = True
                    # Cache this bot response
                    bot_response_cache_entry = format_message(cog, sent_msg)
                    cog.message_cache['by_channel'][channel_id].append(bot_response_cache_entry)
                    cog.message_cache['global_recent'].append(bot_response_cache_entry)
                    cog.message_cache['replied_to'][channel_id].append(bot_response_cache_entry) # Track replies
                    cog.bot_last_spoke[channel_id] = time.time()
                    # Track participation topic
                    identified_topics = identify_conversation_topics(cog, [bot_response_cache_entry])
                    if identified_topics:
                        topic = identified_topics[0]['topic'].lower().strip()
                        cog.gurt_participation_topics[topic] += 1
                        print(f"Tracked Gurt participation in topic: '{topic}'")


            if response_to_use.get("should_respond") and not sent_message and not reacted:
                 print(f"Warning: AI response intended but no valid content/reaction. Data: {response_to_use}")

        elif not error_msg: # No valid response and no critical error
            print(f"Warning: No valid response generated for message {message.id}, and no critical error reported.")

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
