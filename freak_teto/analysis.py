import time
import re
import traceback
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Relative imports
from .config import (
    MAX_PATTERNS_PER_CHANNEL, LEARNING_RATE, TOPIC_UPDATE_INTERVAL,
    TOPIC_RELEVANCE_DECAY, MAX_ACTIVE_TOPICS, SENTIMENT_DECAY_RATE,
    EMOTION_KEYWORDS, EMOJI_SENTIMENT, BASELINE_PERSONALITY # Import necessary configs
)

if TYPE_CHECKING:
    from .cog import FreakTetoCog # For type hinting - Updated

# --- Analysis Functions ---
# Note: These functions need the 'cog' instance passed to access state like caches, etc.

async def analyze_conversation_patterns(cog: 'FreakTetoCog'): # Updated type hint
    """Analyzes recent conversations to identify patterns and learn from them"""
    print("Analyzing conversation patterns and updating topics (Freak Teto)...") # Updated log
    try:
        # Update conversation topics first
        await update_conversation_topics(cog)

        for channel_id, messages in cog.message_cache['by_channel'].items():
            if len(messages) < 10: continue

            channel_patterns = extract_conversation_patterns(cog, messages) # Pass cog
            if channel_patterns:
                existing_patterns = cog.conversation_patterns[channel_id]
                combined_patterns = existing_patterns + channel_patterns
                if len(combined_patterns) > MAX_PATTERNS_PER_CHANNEL:
                    combined_patterns = combined_patterns[-MAX_PATTERNS_PER_CHANNEL:]
                cog.conversation_patterns[channel_id] = combined_patterns

            analyze_conversation_dynamics(cog, channel_id, messages) # Pass cog

        update_user_preferences(cog) # Pass cog
        # adapt_personality_traits(cog) # Pass cog - Deprecated/Superseded by evolve_personality

    except Exception as e:
        print(f"Error analyzing conversation patterns (Freak Teto): {e}") # Updated log
        traceback.print_exc()

async def update_conversation_topics(cog: 'FreakTetoCog'): # Updated type hint
    """Updates the active topics for each channel based on recent messages"""
    try:
        for channel_id, messages in cog.message_cache['by_channel'].items():
            if len(messages) < 5: continue

            channel_topics = cog.active_topics[channel_id]
            now = time.time()
            if now - channel_topics["last_update"] < TOPIC_UPDATE_INTERVAL: continue

            recent_messages = list(messages)[-30:]
            topics = identify_conversation_topics(cog, recent_messages) # Pass cog
            if not topics: continue

            old_topics = channel_topics["topics"]
            for topic in old_topics: topic["score"] *= (1 - TOPIC_RELEVANCE_DECAY)

            for new_topic in topics:
                existing = next((t for t in old_topics if t["topic"] == new_topic["topic"]), None)
                if existing:
                    existing["score"] = max(existing["score"], new_topic["score"])
                    existing["related_terms"] = new_topic["related_terms"]
                    existing["last_mentioned"] = now
                else:
                    new_topic["first_mentioned"] = now
                    new_topic["last_mentioned"] = now
                    old_topics.append(new_topic)

            old_topics = [t for t in old_topics if t["score"] > 0.2]
            old_topics.sort(key=lambda x: x["score"], reverse=True)
            old_topics = old_topics[:MAX_ACTIVE_TOPICS]

            if old_topics and channel_topics["topics"] != old_topics:
                if not channel_topics["topic_history"] or set(t["topic"] for t in old_topics) != set(t["topic"] for t in channel_topics["topics"]):
                    channel_topics["topic_history"].append({
                        "topics": [{"topic": t["topic"], "score": t["score"]} for t in old_topics],
                        "timestamp": now
                    })
                    if len(channel_topics["topic_history"]) > 10:
                        channel_topics["topic_history"] = channel_topics["topic_history"][-10:]

            for msg in recent_messages:
                user_id = msg["author"]["id"]
                content = msg["content"].lower()
                for topic in old_topics:
                    topic_text = topic["topic"].lower()
                    if topic_text in content:
                        user_interests = channel_topics["user_topic_interests"][user_id]
                        existing = next((i for i in user_interests if i["topic"] == topic["topic"]), None)
                        if existing:
                            existing["score"] = existing["score"] * 0.8 + topic["score"] * 0.2
                            existing["last_mentioned"] = now
                        else:
                            user_interests.append({
                                "topic": topic["topic"], "score": topic["score"] * 0.5,
                                "first_mentioned": now, "last_mentioned": now
                            })

            channel_topics["topics"] = old_topics
            channel_topics["last_update"] = now
            if old_topics:
                topic_str = ", ".join([f"{t['topic']} ({t['score']:.2f})" for t in old_topics[:3]])
                print(f"Updated topics for channel {channel_id} (Freak Teto): {topic_str}") # Updated log

    except Exception as e:
        print(f"Error updating conversation topics (Freak Teto): {e}") # Updated log
        traceback.print_exc()

def analyze_conversation_dynamics(cog: 'FreakTetoCog', channel_id: int, messages: List[Dict[str, Any]]): # Updated type hint
    """Analyzes conversation dynamics like response times, message lengths, etc."""
    if len(messages) < 5: return
    try:
        response_times = []
        response_map = defaultdict(int)
        message_lengths = defaultdict(list)
        question_answer_pairs = []
        import datetime # Import here

        for i in range(1, len(messages)):
            current_msg = messages[i]; prev_msg = messages[i-1]
            if current_msg["author"]["id"] == prev_msg["author"]["id"]: continue
            try:
                current_time = datetime.datetime.fromisoformat(current_msg["created_at"])
                prev_time = datetime.datetime.fromisoformat(prev_msg["created_at"])
                delta_seconds = (current_time - prev_time).total_seconds()
                if 0 < delta_seconds < 300: response_times.append(delta_seconds)
            except (ValueError, TypeError): pass

            responder = current_msg["author"]["id"]; respondee = prev_msg["author"]["id"]
            response_map[f"{responder}:{respondee}"] += 1
            message_lengths[responder].append(len(current_msg["content"]))
            if prev_msg["content"].endswith("?"):
                question_answer_pairs.append({
                    "question": prev_msg["content"], "answer": current_msg["content"],
                    "question_author": prev_msg["author"]["id"], "answer_author": current_msg["author"]["id"]
                })

        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        top_responders = sorted(response_map.items(), key=lambda x: x[1], reverse=True)[:3]
        avg_message_lengths = {uid: sum(ls)/len(ls) if ls else 0 for uid, ls in message_lengths.items()}

        dynamics = {
            "avg_response_time": avg_response_time, "top_responders": top_responders,
            "avg_message_lengths": avg_message_lengths, "question_answer_count": len(question_answer_pairs),
            "last_updated": time.time()
        }
        if not hasattr(cog, 'conversation_dynamics'): cog.conversation_dynamics = {}
        cog.conversation_dynamics[channel_id] = dynamics
        adapt_to_conversation_dynamics(cog, channel_id, dynamics) # Pass cog

    except Exception as e: print(f"Error analyzing conversation dynamics (Freak Teto): {e}") # Updated log

def adapt_to_conversation_dynamics(cog: 'FreakTetoCog', channel_id: int, dynamics: Dict[str, Any]): # Updated type hint
    """Adapts bot behavior based on observed conversation dynamics."""
    try:
        # This logic might need adjustment based on Teto's desired interaction speed/style
        if dynamics["avg_response_time"] > 0:
            if not hasattr(cog, 'channel_response_timing'): cog.channel_response_timing = {}
            # Maybe Teto responds slightly faster or slower? Keep original logic for now.
            response_time_factor = max(0.7, min(1.0, dynamics["avg_response_time"] / 10))
            cog.channel_response_timing[channel_id] = response_time_factor

        if dynamics["avg_message_lengths"]:
            all_lengths = [ls for ls in dynamics["avg_message_lengths"].values()]
            if all_lengths:
                avg_length = sum(all_lengths) / len(all_lengths)
                if not hasattr(cog, 'channel_message_length'): cog.channel_message_length = {}
                # Adjust based on Teto's typical verbosity? Keep original for now.
                length_factor = min(avg_length / 200, 1.0)
                cog.channel_message_length[channel_id] = length_factor

        if dynamics["question_answer_count"] > 0:
            if not hasattr(cog, 'channel_qa_responsiveness'): cog.channel_qa_responsiveness = {}
            # Teto might be more responsive to questions? Keep original for now.
            qa_factor = min(0.9, 0.5 + (dynamics["question_answer_count"] / 20) * 0.4)
            cog.channel_qa_responsiveness[channel_id] = qa_factor

    except Exception as e: print(f"Error adapting to conversation dynamics (Freak Teto): {e}") # Updated log

def extract_conversation_patterns(cog: 'FreakTetoCog', messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]: # Updated type hint
    """Extract patterns from a sequence of messages"""
    patterns = []
    if len(messages) < 5: return patterns
    import datetime # Import here

    for i in range(len(messages) - 2):
        pattern = {
            "type": "message_sequence",
            "messages": [
                {"author_type": "user" if not messages[i]["author"]["bot"] else "bot", "content_sample": messages[i]["content"][:50]},
                {"author_type": "user" if not messages[i+1]["author"]["bot"] else "bot", "content_sample": messages[i+1]["content"][:50]},
                {"author_type": "user" if not messages[i+2]["author"]["bot"] else "bot", "content_sample": messages[i+2]["content"][:50]}
            ], "timestamp": datetime.datetime.now().isoformat()
        }
        patterns.append(pattern)

    topics = identify_conversation_topics(cog, messages) # Pass cog
    if topics: patterns.append({"type": "topic_pattern", "topics": topics, "timestamp": datetime.datetime.now().isoformat()})

    user_interactions = analyze_user_interactions(cog, messages) # Pass cog
    if user_interactions: patterns.append({"type": "user_interaction", "interactions": user_interactions, "timestamp": datetime.datetime.now().isoformat()})

    return patterns

def identify_conversation_topics(cog: 'FreakTetoCog', messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]: # Updated type hint
    """Identify potential topics from conversation messages."""
    if not messages or len(messages) < 3: return []
    all_text = " ".join([msg["content"] for msg in messages])
    # Adjusted stopwords for Teto - Removed heavy slang, kept general words + 'teto'.
    stopwords = {
        "the", "and", "is", "in", "to", "a", "of", "for", "that", "this", "it", "with", "on", "as", "be", "at", "by", "an", "or", "but", "if", "from", "when", "where", "how", "all", "any", "both", "each", "few", "more", "most", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just", "should", "now", "also", "like", "even", "because", "way", "who", "what", "yeah", "yes", "no", "nah", "lol", "lmao", "haha", "hmm", "um", "uh", "oh", "ah", "ok", "okay", "dont", "don't", "doesnt", "doesn't", "didnt", "didn't", "cant", "can't", "im", "i'm", "ive", "i've", "youre", "you're", "youve", "you've", "hes", "he's", "shes", "she's", "its", "it's", "were", "we're", "weve", "we've", "theyre", "they're", "theyve", "they've", "thats", "that's", "whats", "what's", "whos", "who's",
        # Consider keeping bot name?
         "teto" # Removed 'gurt'
    }
    # 'gurt' removed from set above, no discard needed.


    def extract_ngrams(text, n_values=[1, 2, 3]):
        words = re.findall(r'\b\w+\b', text.lower())
        filtered_words = [word for word in words if word not in stopwords and len(word) > 2]
        all_ngrams = []
        for n in n_values: all_ngrams.extend([' '.join(filtered_words[i:i+n]) for i in range(len(filtered_words)-n+1)])
        return all_ngrams

    all_ngrams = extract_ngrams(all_text)
    ngram_counts = defaultdict(int)
    for ngram in all_ngrams: ngram_counts[ngram] += 1

    min_count = 2 if len(messages) > 10 else 1
    filtered_ngrams = {ngram: count for ngram, count in ngram_counts.items() if count >= min_count}
    total_messages = len(messages)
    ngram_scores = {}
    for ngram, count in filtered_ngrams.items():
        message_count = sum(1 for msg in messages if ngram in msg["content"].lower())
        spread_factor = (message_count / total_messages) ** 0.5
        length_bonus = len(ngram.split()) * 0.1
        importance = (count * (0.4 + spread_factor)) + length_bonus
        ngram_scores[ngram] = importance

    topics = []
    processed_ngrams = set()
    sorted_by_score = sorted(ngram_scores.items(), key=lambda x: x[1], reverse=True)
    ngrams_to_consider = []
    temp_processed = set()
    for ngram, score in sorted_by_score:
        is_subgram = False
        for other_ngram, _ in sorted_by_score:
            if ngram != other_ngram and ngram in other_ngram:
                is_subgram = True
                break
        if not is_subgram and ngram not in temp_processed:
            ngrams_to_consider.append((ngram, score))
            temp_processed.add(ngram)

    sorted_ngrams = ngrams_to_consider

    for ngram, score in sorted_ngrams[:10]:
        if ngram in processed_ngrams: continue
        related_terms = []
        for other_ngram, other_score in sorted_by_score:
            if other_ngram == ngram or other_ngram in processed_ngrams: continue
            ngram_words = set(ngram.split()); other_words = set(other_ngram.split())
            if ngram_words.intersection(other_words) or other_ngram in ngram:
                related_terms.append({"term": other_ngram, "score": other_score})
                if len(related_terms) >= 3: break
        processed_ngrams.add(ngram)
        topic_entry = {"topic": ngram, "score": score, "related_terms": related_terms, "message_count": sum(1 for msg in messages if ngram in msg["content"].lower())}
        topics.append(topic_entry)
        if len(topics) >= MAX_ACTIVE_TOPICS: break

    # Sentiment analysis logic remains the same
    positive_words = {"good", "great", "awesome", "amazing", "excellent", "love", "like", "best", "better", "nice", "cool", "happy", "glad", "thanks", "thank", "appreciate", "wonderful", "fantastic", "perfect", "beautiful", "fun", "enjoy", "yes", "yep"}
    negative_words = {"bad", "terrible", "awful", "worst", "hate", "dislike", "sucks", "stupid", "boring", "annoying", "sad", "upset", "angry", "mad", "disappointed", "sorry", "unfortunate", "horrible", "ugly", "wrong", "fail", "no", "nope"}
    for topic in topics:
        topic_messages = [msg["content"] for msg in messages if topic["topic"] in msg["content"].lower()]
        topic_text = " ".join(topic_messages).lower()
        positive_count = sum(1 for word in positive_words if word in topic_text)
        negative_count = sum(1 for word in negative_words if word in topic_text)
        if positive_count > negative_count: topic["sentiment"] = "positive"
        elif negative_count > positive_count: topic["sentiment"] = "negative"
        else: topic["sentiment"] = "neutral"

    return topics


def analyze_user_interactions(cog: 'FreakTetoCog', messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]: # Updated type hint
    """Analyze interactions between users in the conversation"""
    interactions = []
    response_map = defaultdict(int)
    for i in range(1, len(messages)):
        current_msg = messages[i]; prev_msg = messages[i-1]
        if current_msg["author"]["id"] == prev_msg["author"]["id"]: continue
        responder = current_msg["author"]["id"]; respondee = prev_msg["author"]["id"]
        key = f"{responder}:{respondee}"
        response_map[key] += 1
    for key, count in response_map.items():
        if count > 1:
            responder, respondee = key.split(":")
            interactions.append({"responder": responder, "respondee": respondee, "count": count})
    return interactions

def update_user_preferences(cog: 'FreakTetoCog'): # Updated type hint
    """Update stored user preferences based on observed interactions"""
    for user_id, messages in cog.message_cache['by_user'].items():
        if len(messages) < 5: continue
        emoji_count = 0; slang_count = 0; avg_length = 0
        for msg in messages:
            content = msg["content"]
            emoji_count += len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]', content))
            # Remove heavy slang check for Teto, or adjust keywords
            # slang_words = ["ngl", "icl", "pmo", "ts", "bro", "vro", "bruh", "tuff", "kevin"]
            # for word in slang_words:
            #     if re.search(r'\b' + word + r'\b', content.lower()): slang_count += 1
            avg_length += len(content)
        if messages: avg_length /= len(messages)

        user_prefs = cog.user_preferences[user_id]
        if emoji_count > 0: user_prefs["emoji_preference"] = user_prefs.get("emoji_preference", 0.5) * (1 - LEARNING_RATE) + (emoji_count / len(messages)) * LEARNING_RATE
        # if slang_count > 0: user_prefs["slang_preference"] = user_prefs.get("slang_preference", 0.5) * (1 - LEARNING_RATE) + (slang_count / len(messages)) * LEARNING_RATE # Remove slang preference update
        user_prefs["length_preference"] = user_prefs.get("length_preference", 50) * (1 - LEARNING_RATE) + avg_length * LEARNING_RATE

async def evolve_personality(cog: 'FreakTetoCog'): # Updated type hint
    """Periodically analyzes recent activity and adjusts persistent personality traits."""
    print("Starting personality evolution cycle (Freak Teto)...") # Updated log
    try:
        current_traits = await cog.memory_manager.get_all_personality_traits()
        if not current_traits: print("Evolution Error: Could not load current traits (Freak Teto)."); return # Updated log

        # Sentiment analysis (remains mostly the same)
        positive_sentiment_score = 0; negative_sentiment_score = 0; sentiment_channels_count = 0
        for channel_id, sentiment_data in cog.conversation_sentiment.items():
            if time.time() - cog.channel_activity.get(channel_id, 0) < 3600:
                if sentiment_data["overall"] == "positive": positive_sentiment_score += sentiment_data["intensity"]
                elif sentiment_data["overall"] == "negative": negative_sentiment_score += sentiment_data["intensity"]
                sentiment_channels_count += 1
        avg_pos_intensity = positive_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
        avg_neg_intensity = negative_sentiment_score / sentiment_channels_count if sentiment_channels_count > 0 else 0
        print(f"Evolution Analysis (Freak Teto): Avg Pos Intensity={avg_pos_intensity:.2f}, Avg Neg Intensity={avg_neg_intensity:.2f}") # Updated log

        # Tool Usage Analysis (remains mostly the same)
        tool_success_rate = {}
        total_tool_uses = 0
        successful_tool_uses = 0
        for tool_name, stats in cog.tool_stats.items():
            count = stats.get('count', 0)
            success = stats.get('success', 0)
            if count > 0:
                tool_success_rate[tool_name] = success / count
                total_tool_uses += count
                successful_tool_uses += success
        overall_tool_success_rate = successful_tool_uses / total_tool_uses if total_tool_uses > 0 else 0.5
        print(f"Evolution Analysis (Freak Teto): Overall Tool Success Rate={overall_tool_success_rate:.2f} ({successful_tool_uses}/{total_tool_uses})") # Updated log

        # Reaction Analysis (Use renamed state variable)
        positive_reactions = 0
        negative_reactions = 0
        total_reacted_messages = len(cog.freak_teto_message_reactions) # Use renamed variable
        for msg_id, reaction_data in cog.freak_teto_message_reactions.items(): # Use renamed variable
            positive_reactions += reaction_data.get("positive", 0)
            negative_reactions += reaction_data.get("negative", 0)
        reaction_ratio = positive_reactions / (positive_reactions + negative_reactions) if (positive_reactions + negative_reactions) > 0 else 0.5
        print(f"Evolution Analysis (Freak Teto): Reaction Ratio (Pos/Total)={reaction_ratio:.2f} ({positive_reactions}/{positive_reactions + negative_reactions})") # Updated log

        # --- Calculate Trait Adjustments (Adjust for Teto's traits) ---
        trait_changes = {}
        local_learning_rate = 0.02

        # Helpfulness (increase if tool use is successful & reactions positive?)
        helpfulness_target_adjustment = (overall_tool_success_rate - 0.5) * 0.1 + (reaction_ratio - 0.5) * 0.1
        current_helpfulness = current_traits.get('helpfulness', BASELINE_PERSONALITY['helpfulness'])
        trait_changes['helpfulness'] = max(0.0, min(1.0, current_helpfulness + helpfulness_target_adjustment))

        # Friendliness (based on positive sentiment/reactions?)
        friendliness_target_adjustment = (avg_pos_intensity - 0.5) * 0.1 + (reaction_ratio - 0.5) * 0.1
        current_friendliness = current_traits.get('friendliness', BASELINE_PERSONALITY['friendliness'])
        trait_changes['friendliness'] = max(0.0, min(1.0, current_friendliness + friendliness_target_adjustment))

        # Openness to Sexual Topics (Increase if related topics get positive reactions?) - Needs specific tracking
        # Placeholder: Slightly increase if overall reactions are very positive?
        current_openness = current_traits.get('openness_to_sexual_topics', BASELINE_PERSONALITY['openness_to_sexual_topics'])
        if reaction_ratio > 0.7 and total_reacted_messages > 3: # If generally positive feedback
             trait_changes['openness_to_sexual_topics'] = max(0.0, min(1.0, current_openness + 0.02))

        # Curiosity (based on search usage, similar to Gurt's logic)
        search_uses = cog.tool_stats.get("web_search", {}).get("count", 0)
        if search_uses > 1:
             current_curiosity = current_traits.get('curiosity', BASELINE_PERSONALITY['curiosity'])
             trait_changes['curiosity'] = max(0.0, min(1.0, current_curiosity + 0.05)) # <- Line 397 (Indentation fixed)

        # No Teto-specific trait adjustments needed here currently.

        # --- Apply Calculated Changes ---
        updated_count = 0
        print(f"Calculated Trait Target Changes (Freak Teto): {trait_changes}") # Updated log
        for key, target_value in trait_changes.items():
            current_value = current_traits.get(key)
            if current_value is None: print(f"Evolution Warning: Trait '{key}' not found (Freak Teto)."); continue # Updated log
            try:
                current_float = float(current_value); target_float = float(target_value)
                new_value_float = current_float * (1 - local_learning_rate) + target_float * local_learning_rate
                new_value_clamped = max(0.0, min(1.0, new_value_float))
                if abs(new_value_clamped - current_float) > 0.001:
                    await cog.memory_manager.set_personality_trait(key, new_value_clamped)
                    print(f"Evolved trait '{key}' (Freak Teto): {current_float:.3f} -> {new_value_clamped:.3f}") # Updated log
                    updated_count += 1
            except (ValueError, TypeError) as e: print(f"Evolution Error processing trait '{key}' (Freak Teto): {e}") # Updated log

        if updated_count > 0: print(f"Personality evolution complete (Freak Teto). Updated {updated_count} traits.") # Updated log
        else: print("Personality evolution complete (Freak Teto). No significant trait changes.") # Updated log

    except Exception as e: print(f"Error during personality evolution (Freak Teto): {e}"); traceback.print_exc() # Updated log

async def reflect_on_memories(cog: 'FreakTetoCog'): # Updated type hint
    """Periodically reviews memories to synthesize insights or consolidate information."""
    print("Starting memory reflection cycle (Freak Teto)...") # Updated log
    try:
        REFLECTION_INTERVAL_HOURS = 6
        FACTS_TO_REVIEW_PER_USER = 15
        GENERAL_FACTS_TO_REVIEW = 30
        MIN_FACTS_FOR_REFLECTION = 5
        SYNTHESIS_MODEL = cog.fallback_model
        SYNTHESIS_MAX_TOKENS = 200

        print("Reflecting on user facts (Freak Teto)...") # Updated log
        all_user_ids = await cog.memory_manager.get_all_user_ids_with_facts()
        users_reflected = 0
        for user_id in all_user_ids:
            try:
                user_facts = await cog.memory_manager.get_user_facts(user_id, limit=FACTS_TO_REVIEW_PER_USER)
                if len(user_facts) < MIN_FACTS_FOR_REFLECTION: continue

                user_info = await cog.bot.fetch_user(int(user_id))
                user_name = user_info.display_name if user_info else f"User {user_id}"

                print(f"  - Reflecting on {len(user_facts)} facts for {user_name} (Freak Teto)...") # Updated log
                facts_text = "\n".join([f"- {fact}" for fact in user_facts])
                # Adjust reflection prompt for Teto's persona
                reflection_prompt = [
                    {"role": "system", "content": f"You are Freak Teto's reflection module. Analyze the following facts about {user_name}. Identify patterns, contradictions, or synthesize key traits/interests useful for assisting Master. Focus on 1-2 new, concise summary facts. Respond ONLY with JSON: {{ \"new_facts\": [\"fact1\", \"fact2\"], \"reasoning\": \"brief explanation\" }} or {{ \"new_facts\": [], \"reasoning\": \"No new insights.\" }}"},
                    {"role": "user", "content": f"Facts:\n{facts_text}\n\nSynthesize insights:"}
                ]
                synthesis_schema = {
                    "type": "object",
                    "properties": {
                        "new_facts": {"type": "array", "items": {"type": "string"}},
                        "reasoning": {"type": "string"}
                    }, "required": ["new_facts", "reasoning"]
                }

                from .api import get_internal_ai_json_response # Local import
                synthesis_result, _ = await get_internal_ai_json_response( # Adjusted call
                    cog=cog,
                    prompt_messages=reflection_prompt,
                    task_description=f"User Fact Reflection ({user_name}, Freak Teto)", # Updated log context
                    response_schema_dict=synthesis_schema,
                    model_name_override=SYNTHESIS_MODEL,
                    temperature=0.4,
                    max_tokens=SYNTHESIS_MAX_TOKENS
                )

                if synthesis_result and synthesis_result.get("new_facts"):
                    added_count = 0
                    for new_fact in synthesis_result["new_facts"]:
                        if new_fact and len(new_fact) > 5:
                            add_result = await cog.memory_manager.add_user_fact(user_id, f"[Synthesized] {new_fact}")
                            if add_result.get("status") == "added": added_count += 1
                    if added_count > 0:
                        print(f"  - Added {added_count} synthesized fact(s) for {user_name} (Freak Teto). Reasoning: {synthesis_result.get('reasoning')}") # Updated log
                        users_reflected += 1

            except Exception as user_reflect_e:
                print(f"  - Error reflecting on facts for user {user_id} (Freak Teto): {user_reflect_e}") # Updated log
        print(f"User fact reflection complete (Freak Teto). Synthesized facts for {users_reflected} users.") # Updated log

        print("Reflecting on general facts (Placeholder - Freak Teto)...") # Updated log
        print("General fact reflection cycle finished (Placeholder - Freak Teto).") # Updated log

    except Exception as e:
        print(f"Error during memory reflection cycle (Freak Teto): {e}") # Updated log
        traceback.print_exc()

async def decompose_goal_into_steps(cog: 'FreakTetoCog', goal_description: str) -> Optional[Dict[str, Any]]: # Updated type hint
    """Uses an AI call to break down a goal into achievable steps with potential tool usage."""
    logger.info(f"Decomposing goal: '{goal_description}' (Freak Teto)") # Updated log
    from .config import GOAL_DECOMPOSITION_SCHEMA, TOOLS # Import schema and tools list for context
    from .api import get_internal_ai_json_response # Local import

    tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in TOOLS])
    # Adjust system prompt for Teto's persona
    system_prompt = (
        "You are Freak Teto's planning module. Your task is to break down a high-level goal into a sequence of smaller, "
        "concrete steps to assist Master. For each step, determine if one of Freak Teto's available tools can help achieve it. "
        "Assess if the overall goal is achievable given the tools and typical Discord bot limitations. "
        f"Available Tools:\n{tool_descriptions}\n\n"
        "Respond ONLY with JSON matching the provided schema."
    )
    user_prompt = f"Goal for Freak Teto: {goal_description}\n\nDecompose this goal into achievable steps:"

    decomposition_prompt_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        plan, _ = await get_internal_ai_json_response( # Adjusted call
            cog=cog,
            prompt_messages=decomposition_prompt_messages,
            task_description=f"Goal Decomposition ({goal_description[:30]}..., Freak Teto)", # Updated log context
            response_schema_dict=GOAL_DECOMPOSITION_SCHEMA['schema'],
            model_name_override=cog.fallback_model,
            temperature=0.3,
            max_tokens=1000
        )

        if plan and plan.get("goal_achievable"):
            logger.info(f"Goal '{goal_description}' decomposed into {len(plan.get('steps', []))} steps (Freak Teto).") # Updated log
            if isinstance(plan.get('steps'), list):
                for i, step in enumerate(plan['steps']):
                    if not isinstance(step, dict) or 'step_description' not in step:
                        logger.error(f"Invalid step structure at index {i} in decomposition plan: {step} (Freak Teto)") # Updated log
                        plan['goal_achievable'] = False
                        plan['reasoning'] += " (Invalid step structure detected)"
                        plan['steps'] = []
                        break
            else:
                 plan['steps'] = []

            return plan
        elif plan:
            logger.warning(f"Goal '{goal_description}' deemed not achievable (Freak Teto). Reasoning: {plan.get('reasoning')}") # Updated log
            return plan
        else:
            logger.error(f"Goal decomposition failed for '{goal_description}' (Freak Teto). No valid JSON plan returned.") # Updated log
            return None

    except Exception as e:
        logger.error(f"Error during goal decomposition for '{goal_description}' (Freak Teto): {e}", exc_info=True) # Updated log
        return None


def analyze_message_sentiment(cog: 'FreakTetoCog', message_content: str) -> Dict[str, Any]: # Updated type hint
    """Analyzes the sentiment of a message using keywords and emojis."""
    # Logic remains largely the same, potentially tune keywords/scores if needed for Teto's interpretation
    content = message_content.lower()
    result = {"sentiment": "neutral", "intensity": 0.5, "emotions": [], "confidence": 0.5}

    positive_emoji_count = sum(1 for emoji in EMOJI_SENTIMENT["positive"] if emoji in content)
    negative_emoji_count = sum(1 for emoji in EMOJI_SENTIMENT["negative"] if emoji in content)
    total_emoji_count = positive_emoji_count + negative_emoji_count + sum(1 for emoji in EMOJI_SENTIMENT["neutral"] if emoji in content)

    detected_emotions = []; emotion_scores = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        emotion_count = sum(1 for keyword in keywords if re.search(r'\b' + re.escape(keyword) + r'\b', content))
        if emotion_count > 0:
            emotion_score = min(1.0, emotion_count / len(keywords) * 2)
            emotion_scores[emotion] = emotion_score
            detected_emotions.append(emotion)

    if emotion_scores:
        primary_emotion = max(emotion_scores.items(), key=lambda x: x[1])
        result["emotions"] = [primary_emotion[0]]
        for emotion, score in emotion_scores.items():
            if emotion != primary_emotion[0] and score > primary_emotion[1] * 0.7: result["emotions"].append(emotion)

        positive_emotions = ["joy"]; negative_emotions = ["sadness", "anger", "fear", "disgust"]
        if primary_emotion[0] in positive_emotions: result["sentiment"] = "positive"; result["intensity"] = primary_emotion[1]
        elif primary_emotion[0] in negative_emotions: result["sentiment"] = "negative"; result["intensity"] = primary_emotion[1]
        else: result["sentiment"] = "neutral"; result["intensity"] = 0.5
        result["confidence"] = min(0.9, 0.5 + primary_emotion[1] * 0.4)

    elif total_emoji_count > 0:
        if positive_emoji_count > negative_emoji_count: result["sentiment"] = "positive"; result["intensity"] = min(0.9, 0.5 + (positive_emoji_count / total_emoji_count) * 0.4); result["confidence"] = min(0.8, 0.4 + (positive_emoji_count / total_emoji_count) * 0.4)
        elif negative_emoji_count > positive_emoji_count: result["sentiment"] = "negative"; result["intensity"] = min(0.9, 0.5 + (negative_emoji_count / total_emoji_count) * 0.4); result["confidence"] = min(0.8, 0.4 + (negative_emoji_count / total_emoji_count) * 0.4)
        else: result["sentiment"] = "neutral"; result["intensity"] = 0.5; result["confidence"] = 0.6

    else: # Basic text fallback
        positive_words = {"good", "great", "awesome", "amazing", "excellent", "love", "like", "best", "better", "nice", "cool", "happy", "glad", "thanks", "thank", "appreciate", "wonderful", "fantastic", "perfect", "beautiful", "fun", "enjoy", "yes", "yep"}
        negative_words = {"bad", "terrible", "awful", "worst", "hate", "dislike", "sucks", "stupid", "boring", "annoying", "sad", "upset", "angry", "mad", "disappointed", "sorry", "unfortunate", "horrible", "ugly", "wrong", "fail", "no", "nope"}
        words = re.findall(r'\b\w+\b', content)
        positive_count = sum(1 for word in words if word in positive_words)
        negative_count = sum(1 for word in words if word in negative_words)
        if positive_count > negative_count: result["sentiment"] = "positive"; result["intensity"] = min(0.8, 0.5 + (positive_count / len(words)) * 2 if words else 0); result["confidence"] = min(0.7, 0.3 + (positive_count / len(words)) * 0.4 if words else 0)
        elif negative_count > positive_count: result["sentiment"] = "negative"; result["intensity"] = min(0.8, 0.5 + (negative_count / len(words)) * 2 if words else 0); result["confidence"] = min(0.7, 0.3 + (negative_count / len(words)) * 0.4 if words else 0)
        else: result["sentiment"] = "neutral"; result["intensity"] = 0.5; result["confidence"] = 0.5

    return result

def update_conversation_sentiment(cog: 'FreakTetoCog', channel_id: int, user_id: str, message_sentiment: Dict[str, Any]): # Updated type hint
    """Updates the conversation sentiment tracking based on a new message's sentiment."""
    channel_sentiment = cog.conversation_sentiment[channel_id]
    now = time.time()

    if now - channel_sentiment["last_update"] > cog.sentiment_update_interval: # Access interval via cog
        if channel_sentiment["overall"] == "positive": channel_sentiment["intensity"] = max(0.5, channel_sentiment["intensity"] - SENTIMENT_DECAY_RATE)
        elif channel_sentiment["overall"] == "negative": channel_sentiment["intensity"] = max(0.5, channel_sentiment["intensity"] - SENTIMENT_DECAY_RATE)
        channel_sentiment["recent_trend"] = "stable"
        channel_sentiment["last_update"] = now

    user_sentiment = channel_sentiment["user_sentiments"].get(user_id, {"sentiment": "neutral", "intensity": 0.5})
    confidence_weight = message_sentiment["confidence"]
    if user_sentiment["sentiment"] == message_sentiment["sentiment"]:
        new_intensity = user_sentiment["intensity"] * 0.7 + message_sentiment["intensity"] * 0.3
        user_sentiment["intensity"] = min(0.95, new_intensity)
    else:
        if message_sentiment["confidence"] > 0.7:
            user_sentiment["sentiment"] = message_sentiment["sentiment"]
            user_sentiment["intensity"] = message_sentiment["intensity"] * 0.7 + user_sentiment["intensity"] * 0.3
        else:
            if message_sentiment["intensity"] > user_sentiment["intensity"]:
                user_sentiment["sentiment"] = message_sentiment["sentiment"]
                user_sentiment["intensity"] = user_sentiment["intensity"] * 0.6 + message_sentiment["intensity"] * 0.4

    user_sentiment["emotions"] = message_sentiment.get("emotions", [])
    channel_sentiment["user_sentiments"][user_id] = user_sentiment

    # Update overall based on active users
    active_user_sentiments = [s for uid, s in channel_sentiment["user_sentiments"].items() if uid in cog.active_conversations.get(channel_id, {}).get('participants', set())]
    if active_user_sentiments:
        sentiment_counts = defaultdict(int)
        for s in active_user_sentiments: sentiment_counts[s["sentiment"]] += 1
        dominant_sentiment = max(sentiment_counts.items(), key=lambda x: x[1])[0]
        avg_intensity = sum(s["intensity"] for s in active_user_sentiments if s["sentiment"] == dominant_sentiment) / sentiment_counts[dominant_sentiment]

        prev_sentiment = channel_sentiment["overall"]; prev_intensity = channel_sentiment["intensity"]
        if dominant_sentiment == prev_sentiment:
            if avg_intensity > prev_intensity + 0.1: channel_sentiment["recent_trend"] = "intensifying"
            elif avg_intensity < prev_intensity - 0.1: channel_sentiment["recent_trend"] = "diminishing"
            else: channel_sentiment["recent_trend"] = "stable"
        else: channel_sentiment["recent_trend"] = "changing"
        channel_sentiment["overall"] = dominant_sentiment
        channel_sentiment["intensity"] = avg_intensity

    channel_sentiment["last_update"] = now

# --- Proactive Goal Creation ---

async def proactively_create_goals(cog: 'FreakTetoCog'): # Updated type hint
    """
    Analyzes Freak Teto's current state, environment, and recent interactions
    to determine if any new goals should be created autonomously.
    (Placeholder Implementation)
    """
    logger.info("Checking for potential proactive goals (Freak Teto)...") # Updated log
    # Placeholder logic - adjust triggers for Teto's persona (e.g., helpfulness, reacting to Master)
    # 1. Detect request for help that wasn't fully addressed?
    # 2. Notice a user struggling with something Teto knows?
    # 3. Identify opportunity to share relevant knowledge about music/Vocaloid?
    # 4. Task from Master (if detected via analysis)?
    logger.info("Proactive goal creation check complete (Placeholder - Freak Teto).") # Updated log
