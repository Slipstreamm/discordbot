import asyncio
import time
import random
import traceback
import os
import json
import aiohttp
from collections import defaultdict
from typing import TYPE_CHECKING

# Relative imports
from .config import (
    LEARNING_UPDATE_INTERVAL, EVOLUTION_UPDATE_INTERVAL, INTEREST_UPDATE_INTERVAL,
    INTEREST_DECAY_INTERVAL_HOURS, INTEREST_PARTICIPATION_BOOST,
    INTEREST_POSITIVE_REACTION_BOOST, INTEREST_NEGATIVE_REACTION_PENALTY,
    INTEREST_FACT_BOOST, STATS_PUSH_INTERVAL, # Added stats interval
    MOOD_OPTIONS, MOOD_CATEGORIES, MOOD_CHANGE_INTERVAL_MIN, MOOD_CHANGE_INTERVAL_MAX, # Mood change imports
    BASELINE_PERSONALITY # For default traits
)
# Assuming analysis functions are moved
from .analysis import (
    analyze_conversation_patterns, evolve_personality, identify_conversation_topics
)

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting

# --- Background Task ---

async def background_processing_task(cog: 'GurtCog'):
    """Background task that periodically analyzes conversations, evolves personality, updates interests, changes mood, and pushes stats."""
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

            # --- Automatic Mood Change (Runs based on its own interval check) ---
            await maybe_change_mood(cog) # Call the mood change logic

    except asyncio.CancelledError:
        print("Background processing task cancelled")
    except Exception as e:
        print(f"Error in background processing task: {e}")
        traceback.print_exc()
        await asyncio.sleep(300) # Wait 5 minutes before retrying after an error

# --- Automatic Mood Change Logic ---

async def maybe_change_mood(cog: 'GurtCog'):
    """Checks if enough time has passed and changes mood based on context."""
    now = time.time()
    time_since_last_change = now - cog.last_mood_change
    next_change_interval = random.uniform(MOOD_CHANGE_INTERVAL_MIN, MOOD_CHANGE_INTERVAL_MAX)

    if time_since_last_change > next_change_interval:
        print(f"Time for a mood change (interval: {next_change_interval:.0f}s). Analyzing context...")
        try:
            # 1. Analyze Sentiment
            positive_sentiment_score = 0
            negative_sentiment_score = 0
            neutral_sentiment_score = 0
            sentiment_channels_count = 0
            for channel_id, sentiment_data in cog.conversation_sentiment.items():
                # Consider only channels active recently (e.g., within the last hour)
                if now - cog.channel_activity.get(channel_id, 0) < 3600:
                    if sentiment_data["overall"] == "positive":
                        positive_sentiment_score += sentiment_data["intensity"]
                    elif sentiment_data["overall"] == "negative":
                        negative_sentiment_score += sentiment_data["intensity"]
                    else:
                        neutral_sentiment_score += sentiment_data["intensity"]
                    sentiment_channels_count += 1

            avg_pos_intensity = positive_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
            avg_neg_intensity = negative_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
            avg_neu_intensity = neutral_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
            print(f"  - Sentiment Analysis: Pos={avg_pos_intensity:.2f}, Neg={avg_neg_intensity:.2f}, Neu={avg_neu_intensity:.2f}")

            # Determine dominant sentiment category
            dominant_sentiment = "neutral"
            if avg_pos_intensity > avg_neg_intensity and avg_pos_intensity > avg_neu_intensity:
                dominant_sentiment = "positive"
            elif avg_neg_intensity > avg_pos_intensity and avg_neg_intensity > avg_neu_intensity:
                dominant_sentiment = "negative"

            # 2. Get Personality Traits
            personality_traits = await cog.memory_manager.get_all_personality_traits()
            if not personality_traits:
                personality_traits = BASELINE_PERSONALITY.copy()
                print("  - Warning: Using baseline personality traits for mood change.")
            else:
                print(f"  - Personality Traits: Mischief={personality_traits.get('mischief', 0):.2f}, Sarcasm={personality_traits.get('sarcasm_level', 0):.2f}, Optimism={personality_traits.get('optimism', 0.5):.2f}")

            # 3. Calculate Mood Weights
            mood_weights = {mood: 1.0 for mood in MOOD_OPTIONS} # Start with base weight

            # Apply Sentiment Bias (e.g., boost factor of 2)
            sentiment_boost = 2.0
            if dominant_sentiment == "positive":
                for mood in MOOD_CATEGORIES.get("positive", []):
                    mood_weights[mood] *= sentiment_boost
            elif dominant_sentiment == "negative":
                for mood in MOOD_CATEGORIES.get("negative", []):
                    mood_weights[mood] *= sentiment_boost
            else: # Neutral sentiment
                 for mood in MOOD_CATEGORIES.get("neutral", []):
                    mood_weights[mood] *= (sentiment_boost * 0.75) # Slightly boost neutral too

            # Apply Personality Bias
            mischief_trait = personality_traits.get('mischief', 0.5)
            sarcasm_trait = personality_traits.get('sarcasm_level', 0.3)
            optimism_trait = personality_traits.get('optimism', 0.5)

            if mischief_trait > 0.6: # If high mischief
                mood_weights["mischievous"] *= (1.0 + mischief_trait) # Boost mischievous based on trait level
            if sarcasm_trait > 0.5: # If high sarcasm
                mood_weights["sarcastic"] *= (1.0 + sarcasm_trait)
                mood_weights["sassy"] *= (1.0 + sarcasm_trait * 0.5) # Also boost sassy a bit
            if optimism_trait > 0.7: # If very optimistic
                for mood in MOOD_CATEGORIES.get("positive", []):
                    mood_weights[mood] *= (1.0 + (optimism_trait - 0.5)) # Boost positive moods
            elif optimism_trait < 0.3: # If pessimistic
                 for mood in MOOD_CATEGORIES.get("negative", []):
                    mood_weights[mood] *= (1.0 + (0.5 - optimism_trait)) # Boost negative moods

            # Ensure current mood has very low weight to avoid picking it again
            mood_weights[cog.current_mood] = 0.01

            # Filter out moods with zero weight before choices
            valid_moods = [mood for mood, weight in mood_weights.items() if weight > 0]
            valid_weights = [mood_weights[mood] for mood in valid_moods]

            if not valid_moods:
                 print("  - Error: No valid moods with positive weight found. Skipping mood change.")
                 return # Skip change if something went wrong

            # 4. Select New Mood
            new_mood = random.choices(valid_moods, weights=valid_weights, k=1)[0]

            # 5. Update State & Log
            old_mood = cog.current_mood
            cog.current_mood = new_mood
            cog.last_mood_change = now
            print(f"Mood automatically changed: {old_mood} -> {new_mood} (Influenced by: Sentiment={dominant_sentiment}, Traits)")

        except Exception as e:
            print(f"Error during automatic mood change: {e}")
            traceback.print_exc()
            # Still update timestamp to avoid retrying immediately on error
            cog.last_mood_change = now

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
