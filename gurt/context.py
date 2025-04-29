import discord
import time
import datetime
import re
from typing import TYPE_CHECKING, Optional, List, Dict, Any

# Relative imports
from .config import CONTEXT_WINDOW_SIZE # Import necessary config

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting

# --- Context Gathering Functions ---
# Note: These functions need the 'cog' instance passed to access state like caches, etc.

def gather_conversation_context(cog: 'GurtCog', channel_id: int, current_message_id: int) -> List[Dict[str, str]]:
    """Gathers and formats conversation history from cache for API context."""
    context_api_messages = []
    if channel_id in cog.message_cache['by_channel']:
        cached = list(cog.message_cache['by_channel'][channel_id])
        # Ensure the current message isn't duplicated
        if cached and cached[-1]['id'] == str(current_message_id):
            cached = cached[:-1]
        context_messages_data = cached[-CONTEXT_WINDOW_SIZE:] # Use config value

        for msg_data in context_messages_data:
            role = "assistant" if msg_data['author']['id'] == str(cog.bot.user.id) else "user"

            # Build the content string, including reply and attachment info
            content_parts = []
            author_name = msg_data['author']['display_name']

            # Add reply prefix if applicable
            if msg_data.get("is_reply"):
                reply_author = msg_data.get('replied_to_author_name', 'Unknown User')
                reply_snippet = msg_data.get('replied_to_content_snippet', '...')
                # Keep snippet very short for context
                reply_snippet_short = (reply_snippet[:25] + '...') if len(reply_snippet) > 28 else reply_snippet
                content_parts.append(f"{author_name} (replying to {reply_author} '{reply_snippet_short}'):")
            else:
                content_parts.append(f"{author_name}:")

            # Add main message content
            if msg_data.get('content'):
                content_parts.append(msg_data['content'])

            # Add attachment descriptions
            attachments = msg_data.get("attachment_descriptions", [])
            if attachments:
                # Join descriptions into a single string
                attachment_str = " ".join([att['description'] for att in attachments])
                content_parts.append(attachment_str)

            # Join all parts with spaces
            content = " ".join(content_parts).strip()

            context_api_messages.append({"role": role, "content": content})
    return context_api_messages

async def get_memory_context(cog: 'GurtCog', message: discord.Message) -> Optional[str]:
    """Retrieves relevant past interactions and facts to provide memory context."""
    channel_id = message.channel.id
    user_id = str(message.author.id)
    memory_parts = []
    current_message_content = message.content

    # 1. Retrieve Relevant User Facts
    try:
        user_facts = await cog.memory_manager.get_user_facts(user_id, context=current_message_content)
        if user_facts:
            facts_str = "; ".join(user_facts)
            memory_parts.append(f"Relevant facts about {message.author.display_name}: {facts_str}")
    except Exception as e: print(f"Error retrieving relevant user facts for memory context: {e}")

    # 1b. Retrieve Relevant General Facts
    try:
        general_facts = await cog.memory_manager.get_general_facts(context=current_message_content, limit=5)
        if general_facts:
            facts_str = "; ".join(general_facts)
            memory_parts.append(f"Relevant general knowledge: {facts_str}")
    except Exception as e: print(f"Error retrieving relevant general facts for memory context: {e}")

    # 2. Retrieve Recent Interactions with the User in this Channel
    try:
        user_channel_messages = [msg for msg in cog.message_cache['by_channel'].get(channel_id, []) if msg['author']['id'] == user_id]
        if user_channel_messages:
            recent_user_msgs = user_channel_messages[-3:]
            msgs_str = "\n".join([f"- {m['content'][:80]} (at {m['created_at']})" for m in recent_user_msgs])
            memory_parts.append(f"Recent messages from {message.author.display_name} in this channel:\n{msgs_str}")
    except Exception as e: print(f"Error retrieving user channel messages for memory context: {e}")

    # 3. Retrieve Recent Bot Replies in this Channel
    try:
        bot_replies = list(cog.message_cache['replied_to'].get(channel_id, []))
        if bot_replies:
            recent_bot_replies = bot_replies[-3:]
            replies_str = "\n".join([f"- {m['content'][:80]} (at {m['created_at']})" for m in recent_bot_replies])
            memory_parts.append(f"Your (gurt's) recent replies in this channel:\n{replies_str}")
    except Exception as e: print(f"Error retrieving bot replies for memory context: {e}")

    # 4. Retrieve Conversation Summary
    cached_summary_data = cog.conversation_summaries.get(channel_id)
    if cached_summary_data and isinstance(cached_summary_data, dict):
        summary_text = cached_summary_data.get("summary")
        # Add TTL check if desired, e.g., if time.time() - cached_summary_data.get("timestamp", 0) < 900:
        if summary_text and not summary_text.startswith("Error"):
             memory_parts.append(f"Summary of the ongoing conversation: {summary_text}")

    # 5. Add information about active topics the user has engaged with
    try:
        channel_topics_data = cog.active_topics.get(channel_id)
        if channel_topics_data:
            user_interests = channel_topics_data["user_topic_interests"].get(user_id, [])
            if user_interests:
                sorted_interests = sorted(user_interests, key=lambda x: x.get("score", 0), reverse=True)
                top_interests = sorted_interests[:3]
                interests_str = ", ".join([f"{interest['topic']} (score: {interest['score']:.2f})" for interest in top_interests])
                memory_parts.append(f"{message.author.display_name}'s topic interests: {interests_str}")
                for interest in top_interests:
                    if "last_mentioned" in interest:
                        time_diff = time.time() - interest["last_mentioned"]
                        if time_diff < 3600:
                            minutes_ago = int(time_diff / 60)
                            memory_parts.append(f"They discussed '{interest['topic']}' about {minutes_ago} minutes ago.")
    except Exception as e: print(f"Error retrieving user topic interests for memory context: {e}")

    # 6. Add information about user's conversation patterns
    try:
        user_messages = cog.message_cache['by_user'].get(user_id, [])
        if len(user_messages) >= 5:
            last_5_msgs = user_messages[-5:]
            avg_length = sum(len(msg["content"]) for msg in last_5_msgs) / 5
            emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]')
            emoji_count = sum(len(emoji_pattern.findall(msg["content"])) for msg in last_5_msgs)
            slang_words = ["ngl", "icl", "pmo", "ts", "bro", "vro", "bruh", "tuff", "kevin"]
            slang_count = sum(1 for msg in last_5_msgs for word in slang_words if re.search(r'\b' + word + r'\b', msg["content"].lower()))

            style_parts = []
            if avg_length < 20: style_parts.append("very brief messages")
            elif avg_length < 50: style_parts.append("concise messages")
            elif avg_length > 150: style_parts.append("detailed/lengthy messages")
            if emoji_count > 5: style_parts.append("frequent emoji use")
            elif emoji_count == 0: style_parts.append("no emojis")
            if slang_count > 3: style_parts.append("heavy slang usage")
            if style_parts: memory_parts.append(f"Communication style: {', '.join(style_parts)}")
    except Exception as e: print(f"Error analyzing user communication patterns: {e}")

    # 7. Add sentiment analysis of user's recent messages
    try:
        channel_sentiment = cog.conversation_sentiment[channel_id]
        user_sentiment = channel_sentiment["user_sentiments"].get(user_id)
        if user_sentiment:
            sentiment_desc = f"{user_sentiment['sentiment']} tone"
            if user_sentiment["intensity"] > 0.7: sentiment_desc += " (strongly so)"
            elif user_sentiment["intensity"] < 0.4: sentiment_desc += " (mildly so)"
            memory_parts.append(f"Recent message sentiment: {sentiment_desc}")
            if user_sentiment.get("emotions"):
                emotions_str = ", ".join(user_sentiment["emotions"])
                memory_parts.append(f"Detected emotions from user: {emotions_str}")
    except Exception as e: print(f"Error retrieving user sentiment/emotions for memory context: {e}")

    # 8. Add Relationship Score with User
    try:
        user_id_str = str(user_id)
        bot_id_str = str(cog.bot.user.id)
        key_1, key_2 = (user_id_str, bot_id_str) if user_id_str < bot_id_str else (bot_id_str, user_id_str)
        relationship_score = cog.user_relationships.get(key_1, {}).get(key_2, 0.0)
        memory_parts.append(f"Relationship score with {message.author.display_name}: {relationship_score:.1f}/100")
    except Exception as e: print(f"Error retrieving relationship score for memory context: {e}")

    # 9. Retrieve Semantically Similar Messages
    try:
        if current_message_content and cog.memory_manager.semantic_collection:
            filter_metadata = None # Example: {"channel_id": str(channel_id)}
            semantic_results = await cog.memory_manager.search_semantic_memory(
                query_text=current_message_content, n_results=3, filter_metadata=filter_metadata
            )
            if semantic_results:
                semantic_memory_parts = ["Semantically similar past messages:"]
                for result in semantic_results:
                    if result.get('id') == str(message.id): continue
                    doc = result.get('document', 'N/A')
                    meta = result.get('metadata', {})
                    dist = result.get('distance', 1.0)
                    similarity_score = 1.0 - dist
                    timestamp_str = datetime.datetime.fromtimestamp(meta.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M') if meta.get('timestamp') else 'Unknown time'
                    author_name = meta.get('display_name', meta.get('user_name', 'Unknown user'))
                    semantic_memory_parts.append(f"- (Similarity: {similarity_score:.2f}) {author_name} (at {timestamp_str}): {doc[:100]}")
                if len(semantic_memory_parts) > 1: memory_parts.append("\n".join(semantic_memory_parts))
    except Exception as e: print(f"Error retrieving semantic memory context: {e}")

    # 10. Add information about recent attachments
    try:
        channel_messages = cog.message_cache['by_channel'].get(channel_id, [])
        messages_with_attachments = [msg for msg in channel_messages if msg.get("attachment_descriptions")]
        if messages_with_attachments:
            recent_attachments = messages_with_attachments[-5:] # Get last 5
            attachment_memory_parts = ["Recently Shared Files/Images:"]
            for msg in recent_attachments:
                author_name = msg.get('author', {}).get('display_name', 'Unknown User')
                timestamp_str = 'Unknown time'
                try:
                    # Safely parse timestamp
                    if msg.get('created_at'):
                        timestamp_str = datetime.datetime.fromisoformat(msg['created_at']).strftime('%H:%M')
                except ValueError: pass # Ignore invalid timestamp format

                descriptions = " ".join([att['description'] for att in msg.get('attachment_descriptions', [])])
                attachment_memory_parts.append(f"- By {author_name} (at {timestamp_str}): {descriptions}")

            if len(attachment_memory_parts) > 1:
                memory_parts.append("\n".join(attachment_memory_parts))
    except Exception as e: print(f"Error retrieving recent attachments for memory context: {e}")


    if not memory_parts: return None
    memory_context_str = "--- Memory Context ---\n" + "\n\n".join(memory_parts) + "\n--- End Memory Context ---"
    return memory_context_str
