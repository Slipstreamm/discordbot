import discord
from discord.ext import commands
import random
import asyncio
import os
import json
import aiohttp
import datetime
import time
import re
import traceback # Added for error logging
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple, Union # Added Union

# Third-party imports for tools
from tavily import TavilyClient
import docker
import aiodocker # Use aiodocker for async operations
from asteval import Interpreter # Added for calculate tool
from langchain_core.tools import tool # Import the tool decorator

# Relative imports from within the gurt package and parent
from .memory import MemoryManager # Import from local memory.py
from .config import (
    TAVILY_API_KEY, PISTON_API_URL, PISTON_API_KEY, SAFETY_CHECK_MODEL,
    DOCKER_EXEC_IMAGE, DOCKER_COMMAND_TIMEOUT, DOCKER_CPU_LIMIT, DOCKER_MEM_LIMIT,
    SUMMARY_CACHE_TTL, SUMMARY_API_TIMEOUT, DEFAULT_MODEL,
    # Add these:
    TAVILY_DEFAULT_SEARCH_DEPTH, TAVILY_DEFAULT_MAX_RESULTS, TAVILY_DISABLE_ADVANCED
)
# Assume these helpers will be moved or are accessible via cog
# We might need to pass 'cog' to these tool functions if they rely on cog state heavily
# from .utils import format_message # This will be needed by context tools
# Removed: from .api import get_internal_ai_json_response # Moved into functions to avoid circular import

# --- Tool Implementations ---
# Note: Most of these functions will need the 'cog' instance passed to them
#       to access things like cog.bot, cog.session, cog.current_channel, cog.memory_manager etc.
#       We will add 'cog' as the first parameter to each. (Wrapper in api.py handles this)

@tool
async def get_recent_messages(limit: int, channel_id: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves the most recent messages from a specified Discord channel or the current channel.

    Args:
        cog: The GurtCog instance (automatically passed).
        limit: The maximum number of messages to retrieve (1-100).
        channel_id: Optional ID of the channel to fetch messages from. If None, uses the current channel context.

    Returns:
        A dictionary containing channel info, a list of formatted messages, the count, and a timestamp, or an error dictionary.
    """
    from .utils import format_message # Import here to avoid circular dependency at module level
    limit = min(max(1, limit), 100)
    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found"}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context"}

        messages = []
        async for message in channel.history(limit=limit):
            messages.append(format_message(cog, message)) # Use formatter

        return {
            "channel": {"id": str(channel.id), "name": getattr(channel, 'name', 'DM Channel')},
            "messages": messages, "count": len(messages),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Error retrieving messages: {str(e)}", "timestamp": datetime.datetime.now().isoformat()}

@tool
async def search_user_messages(user_id: str, limit: int, channel_id: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Searches recent channel history for messages sent by a specific user.

    Args:
        cog: The GurtCog instance (automatically passed).
        user_id: The Discord ID of the user whose messages to search for.
        limit: The maximum number of messages to return (1-100).
        channel_id: Optional ID of the channel to search in. If None, uses the current channel context.

    Returns:
        A dictionary containing channel info, user info, a list of formatted messages, the count, and a timestamp, or an error dictionary.
    """
    from .utils import format_message # Import here
    limit = min(max(1, limit), 100)
    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found"}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context"}

        try: user_id_int = int(user_id)
        except ValueError: return {"error": f"Invalid user ID: {user_id}"}

        messages = []
        user_name = "Unknown User"
        async for message in channel.history(limit=500):
            if message.author.id == user_id_int:
                formatted_msg = format_message(cog, message) # Use formatter
                messages.append(formatted_msg)
                user_name = formatted_msg["author"]["name"] # Get name from formatted msg
                if len(messages) >= limit: break

        return {
            "channel": {"id": str(channel.id), "name": getattr(channel, 'name', 'DM Channel')},
            "user": {"id": user_id, "name": user_name},
            "messages": messages, "count": len(messages),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Error searching user messages: {str(e)}", "timestamp": datetime.datetime.now().isoformat()}

@tool
async def search_messages_by_content(search_term: str, limit: int, channel_id: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Searches recent channel history for messages containing specific text content (case-insensitive).

    Args:
        cog: The GurtCog instance (automatically passed).
        search_term: The text content to search for within messages.
        limit: The maximum number of matching messages to return (1-100).
        channel_id: Optional ID of the channel to search in. If None, uses the current channel context.

    Returns:
        A dictionary containing channel info, the search term, a list of formatted messages, the count, and a timestamp, or an error dictionary.
    """
    from .utils import format_message # Import here
    limit = min(max(1, limit), 100)
    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found"}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context"}

        messages = []
        search_term_lower = search_term.lower()
        async for message in channel.history(limit=500):
            if search_term_lower in message.content.lower():
                messages.append(format_message(cog, message)) # Use formatter
                if len(messages) >= limit: break

        return {
            "channel": {"id": str(channel.id), "name": getattr(channel, 'name', 'DM Channel')},
            "search_term": search_term,
            "messages": messages, "count": len(messages),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Error searching messages by content: {str(e)}", "timestamp": datetime.datetime.now().isoformat()}

@tool
async def get_channel_info(channel_id: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves detailed information about a specified Discord channel or the current channel.

    Args:
        cog: The GurtCog instance (automatically passed).
        channel_id: Optional ID of the channel to get info for. If None, uses the current channel context.

    Returns:
        A dictionary containing detailed channel information (ID, name, topic, type, guild, etc.) or an error dictionary.
    """
    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found"}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context"}

        channel_info = {"id": str(channel.id), "type": str(channel.type), "timestamp": datetime.datetime.now().isoformat()}
        if isinstance(channel, discord.TextChannel): # Use isinstance for type checking
            channel_info.update({
                "name": channel.name, "topic": channel.topic, "position": channel.position,
                "nsfw": channel.is_nsfw(),
                "category": {"id": str(channel.category_id), "name": channel.category.name} if channel.category else None,
                "guild": {"id": str(channel.guild.id), "name": channel.guild.name, "member_count": channel.guild.member_count}
            })
        elif isinstance(channel, discord.DMChannel):
            channel_info.update({
                "type": "DM",
                "recipient": {"id": str(channel.recipient.id), "name": channel.recipient.name, "display_name": channel.recipient.display_name}
            })
        # Add handling for other channel types (VoiceChannel, Thread, etc.) if needed

        return channel_info
    except Exception as e:
        return {"error": f"Error getting channel info: {str(e)}", "timestamp": datetime.datetime.now().isoformat()}

@tool
async def get_conversation_context(message_count: int, channel_id: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves recent messages to provide context for the ongoing conversation in a channel.

    Args:
        cog: The GurtCog instance (automatically passed).
        message_count: The number of recent messages to retrieve (5-50).
        channel_id: Optional ID of the channel. If None, uses the current channel context.

    Returns:
        A dictionary containing channel info, a list of formatted context messages, the count, and a timestamp, or an error dictionary.
    """
    from .utils import format_message # Import here
    message_count = min(max(5, message_count), 50)
    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found"}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context"}

        messages = []
        # Prefer cache if available
        if channel.id in cog.message_cache['by_channel']:
             messages = list(cog.message_cache['by_channel'][channel.id])[-message_count:]
        else:
            async for msg in channel.history(limit=message_count):
                messages.append(format_message(cog, msg))
            messages.reverse()

        return {
            "channel_id": str(channel.id), "channel_name": getattr(channel, 'name', 'DM Channel'),
            "context_messages": messages, "count": len(messages),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Error getting conversation context: {str(e)}"}

@tool
async def get_thread_context(thread_id: str, message_count: int, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves recent messages from a specific Discord thread to provide conversation context.

    Args:
        cog: The GurtCog instance (automatically passed).
        thread_id: The ID of the thread to retrieve context from.
        message_count: The number of recent messages to retrieve (5-50).

    Returns:
        A dictionary containing thread info, parent channel ID, a list of formatted context messages, the count, and a timestamp, or an error dictionary.
    """
    from .utils import format_message # Import here
    message_count = min(max(5, message_count), 50)
    try:
        thread = cog.bot.get_channel(int(thread_id))
        if not thread or not isinstance(thread, discord.Thread):
            return {"error": f"Thread {thread_id} not found or is not a thread"}

        messages = []
        if thread.id in cog.message_cache['by_thread']:
             messages = list(cog.message_cache['by_thread'][thread.id])[-message_count:]
        else:
            async for msg in thread.history(limit=message_count):
                messages.append(format_message(cog, msg))
            messages.reverse()

        return {
            "thread_id": str(thread.id), "thread_name": thread.name,
            "parent_channel_id": str(thread.parent_id),
            "context_messages": messages, "count": len(messages),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Error getting thread context: {str(e)}"}

@tool
async def get_user_interaction_history(user_id_1: str, limit: int, user_id_2: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves the recent message history involving interactions (replies, mentions) between two users.
    If user_id_2 is not provided, it defaults to interactions between user_id_1 and the bot (Gurt).

    Args:
        cog: The GurtCog instance (automatically passed).
        user_id_1: The Discord ID of the first user.
        limit: The maximum number of interaction messages to return (1-50).
        user_id_2: Optional Discord ID of the second user. Defaults to the bot's ID.

    Returns:
        A dictionary containing info about both users, a list of formatted interaction messages, the count, and a timestamp, or an error dictionary.
    """
    limit = min(max(1, limit), 50)
    try:
        user_id_1_int = int(user_id_1)
        user_id_2_int = int(user_id_2) if user_id_2 else cog.bot.user.id

        interactions = []
        # Simplified: Search global cache
        for msg_data in list(cog.message_cache['global_recent']):
            author_id = int(msg_data['author']['id'])
            mentioned_ids = [int(m['id']) for m in msg_data.get('mentions', [])]
            replied_to_author_id = int(msg_data.get('replied_to_author_id')) if msg_data.get('replied_to_author_id') else None

            is_interaction = False
            if (author_id == user_id_1_int and replied_to_author_id == user_id_2_int) or \
               (author_id == user_id_2_int and replied_to_author_id == user_id_1_int): is_interaction = True
            elif (author_id == user_id_1_int and user_id_2_int in mentioned_ids) or \
                 (author_id == user_id_2_int and user_id_1_int in mentioned_ids): is_interaction = True

            if is_interaction:
                interactions.append(msg_data)
                if len(interactions) >= limit: break

        user1 = await cog.bot.fetch_user(user_id_1_int)
        user2 = await cog.bot.fetch_user(user_id_2_int)

        return {
            "user_1": {"id": str(user_id_1_int), "name": user1.name if user1 else "Unknown"},
            "user_2": {"id": str(user_id_2_int), "name": user2.name if user2 else "Unknown"},
            "interactions": interactions, "count": len(interactions),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Error getting user interaction history: {str(e)}"}

@tool
async def get_conversation_summary(channel_id: Optional[str] = None, message_limit: int = 25, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Generates and returns a concise summary of the recent conversation in a specified channel or the current channel.
    Uses an internal LLM call for summarization and caches the result.

    Args:
        cog: The GurtCog instance (automatically passed).
        channel_id: Optional ID of the channel to summarize. If None, uses the current channel context.
        message_limit: The number of recent messages to consider for the summary (default 25).

    Returns:
        A dictionary containing the channel ID, the generated summary, the source (cache or generated), and a timestamp, or an error dictionary.
    """
    from .config import SUMMARY_RESPONSE_SCHEMA, DEFAULT_MODEL # Import schema and model
    from .api import get_internal_ai_json_response # Import here
    try:
        target_channel_id_str = channel_id or (str(cog.current_channel.id) if cog.current_channel else None)
        if not target_channel_id_str: return {"error": "No channel context"}
        target_channel_id = int(target_channel_id_str)
        channel = cog.bot.get_channel(target_channel_id)
        if not channel: return {"error": f"Channel {target_channel_id_str} not found"}

        now = time.time()
        cached_data = cog.conversation_summaries.get(target_channel_id)
        if cached_data and (now - cached_data.get("timestamp", 0) < SUMMARY_CACHE_TTL):
            print(f"Returning cached summary for channel {target_channel_id}")
            return {
                "channel_id": target_channel_id_str, "summary": cached_data.get("summary", "Cache error"),
                "source": "cache", "timestamp": datetime.datetime.fromtimestamp(cached_data.get("timestamp", now)).isoformat()
            }

        print(f"Generating new summary for channel {target_channel_id}")
        # No need to check API_KEY or cog.session for Vertex AI calls via get_internal_ai_json_response

        recent_messages_text = []
        try:
            async for msg in channel.history(limit=message_limit):
                recent_messages_text.append(f"{msg.author.display_name}: {msg.content}")
            recent_messages_text.reverse()
        except discord.Forbidden: return {"error": f"Missing permissions in channel {target_channel_id_str}"}
        except Exception as hist_e: return {"error": f"Error fetching history: {str(hist_e)}"}

        if not recent_messages_text:
            summary = "No recent messages found."
            cog.conversation_summaries[target_channel_id] = {"summary": summary, "timestamp": time.time()}
            return {"channel_id": target_channel_id_str, "summary": summary, "source": "generated (empty)", "timestamp": datetime.datetime.now().isoformat()}

        conversation_context = "\n".join(recent_messages_text)
        summarization_prompt = f"Summarize the main points and current topic of this Discord chat snippet:\n\n---\n{conversation_context}\n---\n\nSummary:"

        # Use get_internal_ai_json_response
        prompt_messages = [
            {"role": "system", "content": "You are an expert summarizer. Provide a concise summary of the following conversation."},
            {"role": "user", "content": summarization_prompt}
        ]

        summary_data = await get_internal_ai_json_response(
            cog=cog,
            prompt_messages=prompt_messages,
            task_description=f"Summarization for channel {target_channel_id}",
            response_schema_dict=SUMMARY_RESPONSE_SCHEMA['schema'], # Pass the schema dict
            model_name=DEFAULT_MODEL, # Consider a cheaper/faster model if needed
            temperature=0.3,
            max_tokens=200 # Adjust as needed
        )

        summary = "Error generating summary."
        if summary_data and isinstance(summary_data.get("summary"), str):
            summary = summary_data["summary"].strip()
            print(f"Summary generated for {target_channel_id}: {summary[:100]}...")
        else:
            error_detail = f"Invalid format or missing 'summary' key. Response: {summary_data}"
            summary = f"Failed summary for {target_channel_id}. Error: {error_detail}"
            print(summary)

        cog.conversation_summaries[target_channel_id] = {"summary": summary, "timestamp": time.time()}
        return {"channel_id": target_channel_id_str, "summary": summary, "source": "generated", "timestamp": datetime.datetime.now().isoformat()}

    except Exception as e:
        error_msg = f"General error in get_conversation_summary: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return {"error": error_msg}

@tool
async def get_message_context(message_id: str, before_count: int = 5, after_count: int = 5, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves messages immediately before and after a specific message ID within the current channel.

    Args:
        cog: The GurtCog instance (automatically passed).
        message_id: The ID of the target message to get context around.
        before_count: The number of messages to retrieve before the target message (1-25).
        after_count: The number of messages to retrieve after the target message (1-25).

    Returns:
        A dictionary containing the formatted target message, lists of messages before and after, the channel ID, and a timestamp, or an error dictionary.
    """
    from .utils import format_message # Import here
    before_count = min(max(1, before_count), 25)
    after_count = min(max(1, after_count), 25)
    try:
        target_message = None
        channel = cog.current_channel
        if not channel: return {"error": "No current channel context"}

        try:
            message_id_int = int(message_id)
            target_message = await channel.fetch_message(message_id_int)
        except discord.NotFound: return {"error": f"Message {message_id} not found in {channel.id}"}
        except discord.Forbidden: return {"error": f"No permission for message {message_id} in {channel.id}"}
        except ValueError: return {"error": f"Invalid message ID: {message_id}"}
        if not target_message: return {"error": f"Message {message_id} not fetched"}

        messages_before = [format_message(cog, msg) async for msg in channel.history(limit=before_count, before=target_message)]
        messages_before.reverse()
        messages_after = [format_message(cog, msg) async for msg in channel.history(limit=after_count, after=target_message)]

        return {
            "target_message": format_message(cog, target_message),
            "messages_before": messages_before, "messages_after": messages_after,
            "channel_id": str(channel.id), "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": f"Error getting message context: {str(e)}"}

@tool
async def web_search(query: str, search_depth: str = TAVILY_DEFAULT_SEARCH_DEPTH, max_results: int = TAVILY_DEFAULT_MAX_RESULTS, topic: str = "general", include_domains: Optional[List[str]] = None, exclude_domains: Optional[List[str]] = None, include_answer: bool = True, include_raw_content: bool = False, include_images: bool = False, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Performs a web search using the Tavily API based on the provided query and parameters.

    Args:
        cog: The GurtCog instance (automatically passed).
        query: The search query string.
        search_depth: Search depth ('basic' or 'advanced'). Advanced costs more credits. Defaults to basic.
        max_results: Maximum number of search results to return (5-20). Defaults to 5.
        topic: Optional topic hint for the search (e.g., "news", "finance"). Defaults to "general".
        include_domains: Optional list of domains to prioritize in the search.
        exclude_domains: Optional list of domains to exclude from the search.
        include_answer: Whether to include a concise answer generated by Tavily (default True).
        include_raw_content: Whether to include raw scraped content from result URLs (default False).
        include_images: Whether to include relevant images found during the search (default False).

    Returns:
        A dictionary containing the search query parameters, a list of results (title, url, content, etc.), an optional answer, optional follow-up questions, the count, and a timestamp, or an error dictionary.
    """
    if not hasattr(cog, 'tavily_client') or not cog.tavily_client:
        return {"error": "Tavily client not initialized.", "timestamp": datetime.datetime.now().isoformat()}

    # Cost control / Logging for advanced search
    final_search_depth = search_depth
    if search_depth.lower() == "advanced":
        if TAVILY_DISABLE_ADVANCED:
            print(f"Warning: Advanced Tavily search requested but disabled by config. Falling back to basic.")
            final_search_depth = "basic"
        else:
            print(f"Performing advanced Tavily search (cost: 10 credits) for query: '{query}'")
    elif search_depth.lower() != "basic":
        print(f"Warning: Invalid search_depth '{search_depth}' provided. Using 'basic'.")
        final_search_depth = "basic"

    # Validate max_results
    final_max_results = max(5, min(20, max_results)) # Clamp between 5 and 20

    try:
        # Pass parameters to Tavily search
        response = await asyncio.to_thread(
            cog.tavily_client.search,
            query=query,
            search_depth=final_search_depth, # Use validated depth
            max_results=final_max_results, # Use validated results count
            topic=topic,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            include_images=include_images
        )
        # Extract relevant information from results
        results = []
        for r in response.get("results", []):
            result = {"title": r.get("title"), "url": r.get("url"), "content": r.get("content"), "score": r.get("score"), "published_date": r.get("published_date")}
            if include_raw_content: result["raw_content"] = r.get("raw_content")
            if include_images: result["images"] = r.get("images")
            results.append(result)

        return {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "topic": topic,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "include_images": include_images,
            "results": results,
            "answer": response.get("answer"),
            "follow_up_questions": response.get("follow_up_questions"),
            "count": len(results),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error during Tavily search for '{query}': {str(e)}"
        print(error_message)
        return {"error": error_message, "timestamp": datetime.datetime.now().isoformat()}

@tool
async def remember_user_fact(user_id: str, fact: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Stores a specific fact about a given user in the bot's long-term memory.

    Args:
        cog: The GurtCog instance (automatically passed).
        user_id: The Discord ID of the user the fact is about.
        fact: The string containing the fact to remember about the user.

    Returns:
        A dictionary indicating success, duplication, or an error. May include a note if an old fact was deleted due to limits.
    """
    if not user_id or not fact: return {"error": "user_id and fact required."}
    print(f"Remembering fact for user {user_id}: '{fact}'")
    try:
        result = await cog.memory_manager.add_user_fact(user_id, fact)
        if result.get("status") == "added": return {"status": "success", "user_id": user_id, "fact_added": fact}
        elif result.get("status") == "duplicate": return {"status": "duplicate", "user_id": user_id, "fact": fact}
        elif result.get("status") == "limit_reached": return {"status": "success", "user_id": user_id, "fact_added": fact, "note": "Oldest fact deleted."}
        else: return {"error": result.get("error", "Unknown MemoryManager error")}
    except Exception as e:
        error_message = f"Error calling MemoryManager for user fact {user_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

@tool
async def get_user_facts(user_id: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves all stored facts associated with a specific user from the bot's long-term memory.

    Args:
        cog: The GurtCog instance (automatically passed).
        user_id: The Discord ID of the user whose facts to retrieve.

    Returns:
        A dictionary containing the user ID, a list of retrieved facts, the count, and a timestamp, or an error dictionary.
    """
    if not user_id: return {"error": "user_id required."}
    print(f"Retrieving facts for user {user_id}")
    try:
        user_facts = await cog.memory_manager.get_user_facts(user_id) # Context not needed for basic retrieval tool
        return {"user_id": user_id, "facts": user_facts, "count": len(user_facts), "timestamp": datetime.datetime.now().isoformat()}
    except Exception as e:
        error_message = f"Error calling MemoryManager for user facts {user_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

@tool
async def remember_general_fact(fact: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Stores a general fact (not specific to any user) in the bot's long-term memory.

    Args:
        cog: The GurtCog instance (automatically passed).
        fact: The string containing the general fact to remember.

    Returns:
        A dictionary indicating success, duplication, or an error. May include a note if an old fact was deleted due to limits.
    """
    if not fact: return {"error": "fact required."}
    print(f"Remembering general fact: '{fact}'")
    try:
        result = await cog.memory_manager.add_general_fact(fact)
        if result.get("status") == "added": return {"status": "success", "fact_added": fact}
        elif result.get("status") == "duplicate": return {"status": "duplicate", "fact": fact}
        elif result.get("status") == "limit_reached": return {"status": "success", "fact_added": fact, "note": "Oldest fact deleted."}
        else: return {"error": result.get("error", "Unknown MemoryManager error")}
    except Exception as e:
        error_message = f"Error calling MemoryManager for general fact: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

@tool
async def get_general_facts(query: Optional[str] = None, limit: Optional[int] = 10, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Retrieves general facts from the bot's long-term memory. Can optionally filter by a query string.

    Args:
        cog: The GurtCog instance (automatically passed).
        query: Optional string to search for within the general facts. If None, retrieves the most recent facts.
        limit: The maximum number of facts to return (1-50, default 10).

    Returns:
        A dictionary containing the query (if any), a list of retrieved facts, the count, and a timestamp, or an error dictionary.
    """
    print(f"Retrieving general facts (query='{query}', limit={limit})")
    limit = min(max(1, limit or 10), 50)
    try:
        general_facts = await cog.memory_manager.get_general_facts(query=query, limit=limit) # Context not needed here
        return {"query": query, "facts": general_facts, "count": len(general_facts), "timestamp": datetime.datetime.now().isoformat()}
    except Exception as e:
        error_message = f"Error calling MemoryManager for general facts: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

@tool
async def timeout_user(user_id: str, duration_minutes: int, reason: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Applies a timeout to a specified user within the current server (guild).

    Args:
        cog: The GurtCog instance (automatically passed).
        user_id: The Discord ID of the user to timeout.
        duration_minutes: The duration of the timeout in minutes (1-1440).
        reason: Optional reason for the timeout, displayed in the audit log.

    Returns:
        A dictionary indicating success (with user details, duration, reason) or an error (e.g., permissions, user not found).
    """
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot timeout outside of a server."}
    guild = cog.current_channel.guild
    if not guild: return {"error": "Could not determine server."}
    if not 1 <= duration_minutes <= 1440: return {"error": "Duration must be 1-1440 minutes."}

    try:
        member_id = int(user_id)
        member = guild.get_member(member_id) or await guild.fetch_member(member_id) # Fetch if not cached
        if not member: return {"error": f"User {user_id} not found in server."}
        if member == cog.bot.user: return {"error": "lol i cant timeout myself vro"}
        if member.id == guild.owner_id: return {"error": f"Cannot timeout owner {member.display_name}."}

        bot_member = guild.me
        if not bot_member.guild_permissions.moderate_members: return {"error": "I lack permission to timeout."}
        if bot_member.id != guild.owner_id and bot_member.top_role <= member.top_role: return {"error": f"Cannot timeout {member.display_name} (role hierarchy)."}

        until = discord.utils.utcnow() + datetime.timedelta(minutes=duration_minutes)
        timeout_reason = reason or "gurt felt like it"
        await member.timeout(until, reason=timeout_reason)
        print(f"Timed out {member.display_name} ({user_id}) for {duration_minutes} mins. Reason: {timeout_reason}")
        return {"status": "success", "user_timed_out": member.display_name, "user_id": user_id, "duration_minutes": duration_minutes, "reason": timeout_reason}
    except ValueError: return {"error": f"Invalid user ID: {user_id}"}
    except discord.NotFound: return {"error": f"User {user_id} not found in server."}
    except discord.Forbidden as e: print(f"Forbidden error timeout {user_id}: {e}"); return {"error": f"Permission error timeout {user_id}."}
    except discord.HTTPException as e: print(f"API error timeout {user_id}: {e}"); return {"error": f"API error timeout {user_id}: {e}"}
    except Exception as e: print(f"Unexpected error timeout {user_id}: {e}"); traceback.print_exc(); return {"error": f"Unexpected error timeout {user_id}: {str(e)}"}

@tool
async def remove_timeout(user_id: str, reason: Optional[str] = None, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Removes an active timeout from a specified user within the current server (guild).

    Args:
        cog: The GurtCog instance (automatically passed).
        user_id: The Discord ID of the user whose timeout should be removed.
        reason: Optional reason for removing the timeout, displayed in the audit log.

    Returns:
        A dictionary indicating success (with user details, reason), that the user wasn't timed out, or an error.
    """
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot remove timeout outside of a server."}
    guild = cog.current_channel.guild
    if not guild: return {"error": "Could not determine server."}

    try:
        member_id = int(user_id)
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        if not member: return {"error": f"User {user_id} not found."}
        # Define bot_member before using it
        bot_member = guild.me
        if not bot_member.guild_permissions.moderate_members: return {"error": "I lack permission to remove timeouts."}
        if member.timed_out_until is None: return {"status": "not_timed_out", "user_id": user_id, "user_name": member.display_name}

        timeout_reason = reason or "Gurt decided to be nice."
        await member.timeout(None, reason=timeout_reason) # None removes timeout
        print(f"Removed timeout from {member.display_name} ({user_id}). Reason: {timeout_reason}")
        return {"status": "success", "user_timeout_removed": member.display_name, "user_id": user_id, "reason": timeout_reason}
    except ValueError: return {"error": f"Invalid user ID: {user_id}"}
    except discord.NotFound: return {"error": f"User {user_id} not found."}
    except discord.Forbidden as e: print(f"Forbidden error remove timeout {user_id}: {e}"); return {"error": f"Permission error remove timeout {user_id}."}
    except discord.HTTPException as e: print(f"API error remove timeout {user_id}: {e}"); return {"error": f"API error remove timeout {user_id}: {e}"}
    except Exception as e: print(f"Unexpected error remove timeout {user_id}: {e}"); traceback.print_exc(); return {"error": f"Unexpected error remove timeout {user_id}: {str(e)}"}

@tool
def calculate(expression: str, *, cog: commands.Cog) -> str:
    """
    Evaluates a mathematical expression using the asteval library. Supports common math functions. Returns the result as a string.

    Args:
        cog: The GurtCog instance (automatically passed).
        expression: The mathematical expression string to evaluate (e.g., "2 * (pi + 1)").

    Args:
        cog: The GurtCog instance (automatically passed).
        expression: The mathematical expression string to evaluate (e.g., "2 * (pi + 1)").

    Returns:
        The calculated result as a string, or an error message string if calculation fails.
    """
    print(f"Calculating expression: {expression}")
    aeval = Interpreter()
    try:
        result = aeval(expression)
        if aeval.error:
            error_details = '; '.join(err.get_error() for err in aeval.error)
            error_message = f"Calculation error: {error_details}"
            print(error_message)
            return f"Error: {error_message}" # Return error as string

        result_str = str(result) # Convert result to string
        print(f"Calculation result: {result_str}")
        return result_str # Return result as string
    except Exception as e:
        error_message = f"Unexpected error during calculation: {str(e)}"
        print(error_message); traceback.print_exc()
        return f"Error: {error_message}" # Return error as string

@tool
async def run_python_code(code: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Executes a provided Python code snippet remotely using the Piston API.
    The execution environment is sandboxed and has limitations.

    Args:
        cog: The GurtCog instance (automatically passed).
        code: The Python code string to execute.

    Returns:
        A dictionary containing the execution status ('success' or 'execution_error'), truncated stdout and stderr, exit code, and signal (if any), or an error dictionary if the API call fails.
    """
    if not PISTON_API_URL: return {"error": "Piston API URL not configured (PISTON_API_URL)."}
    if not cog.session: return {"error": "aiohttp session not initialized."}
    print(f"Executing Python via Piston: {code[:100]}...")
    payload = {"language": "python", "version": "3.10.0", "files": [{"name": "main.py", "content": code}]}
    headers = {"Content-Type": "application/json"}
    if PISTON_API_KEY: headers["Authorization"] = PISTON_API_KEY

    try:
        async with cog.session.post(PISTON_API_URL, headers=headers, json=payload, timeout=20) as response:
            if response.status == 200:
                data = await response.json()
                run_info = data.get("run", {})
                compile_info = data.get("compile", {})
                stdout = run_info.get("stdout", "")
                stderr = run_info.get("stderr", "")
                exit_code = run_info.get("code", -1)
                signal = run_info.get("signal")
                full_stderr = (compile_info.get("stderr", "") + "\n" + stderr).strip()
                max_len = 500
                stdout_trunc = stdout[:max_len] + ('...' if len(stdout) > max_len else '')
                stderr_trunc = full_stderr[:max_len] + ('...' if len(full_stderr) > max_len else '')
                result = {"status": "success" if exit_code == 0 and not signal else "execution_error", "stdout": stdout_trunc, "stderr": stderr_trunc, "exit_code": exit_code, "signal": signal}
                print(f"Piston execution result: {result}")
                return result
            else:
                error_text = await response.text()
                error_message = f"Piston API error (Status {response.status}): {error_text[:200]}"
                print(error_message)
                return {"error": error_message}
    except asyncio.TimeoutError: print("Piston API timed out."); return {"error": "Piston API timed out."}
    except aiohttp.ClientError as e: print(f"Piston network error: {e}"); return {"error": f"Network error connecting to Piston: {str(e)}"}
    except Exception as e: print(f"Unexpected Piston error: {e}"); traceback.print_exc(); return {"error": f"Unexpected error during Python execution: {str(e)}"}

@tool
async def create_poll(question: str, options: List[str], *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Creates a simple poll message in the current channel with numbered reaction options.

    Args:
        cog: The GurtCog instance (automatically passed).
        question: The question for the poll.
        options: A list of strings representing the poll options (2-10 options).

    Returns:
        A dictionary indicating success (with message ID, question, option count) or an error (e.g., permissions, invalid options).
    """
    if not cog.current_channel: return {"error": "No current channel context."}
    if not isinstance(cog.current_channel, discord.abc.Messageable): return {"error": "Channel not messageable."}
    if not isinstance(options, list) or not 2 <= len(options) <= 10: return {"error": "Poll needs 2-10 options."}

    if isinstance(cog.current_channel, discord.abc.GuildChannel):
        bot_member = cog.current_channel.guild.me
        if not cog.current_channel.permissions_for(bot_member).send_messages or \
           not cog.current_channel.permissions_for(bot_member).add_reactions:
            return {"error": "Missing permissions for poll."}

    try:
        poll_content = f"**📊 Poll: {question}**\n\n"
        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i, option in enumerate(options): poll_content += f"{number_emojis[i]} {option}\n"
        poll_message = await cog.current_channel.send(poll_content)
        print(f"Sent poll {poll_message.id}: {question}")
        for i in range(len(options)): await poll_message.add_reaction(number_emojis[i]); await asyncio.sleep(0.1)
        return {"status": "success", "message_id": str(poll_message.id), "question": question, "options_count": len(options)}
    except discord.Forbidden: print("Poll Forbidden"); return {"error": "Forbidden: Missing permissions for poll."}
    except discord.HTTPException as e: print(f"Poll API error: {e}"); return {"error": f"API error creating poll: {e}"}
    except Exception as e: print(f"Poll unexpected error: {e}"); traceback.print_exc(); return {"error": f"Unexpected error creating poll: {str(e)}"}

# Helper function to convert memory string (e.g., "128m") to bytes (Not a tool)
def parse_mem_limit(mem_limit_str: str) -> Optional[int]:
    if not mem_limit_str: return None
    mem_limit_str = mem_limit_str.lower()
    if mem_limit_str.endswith('m'):
        try: return int(mem_limit_str[:-1]) * 1024 * 1024
        except ValueError: return None
    elif mem_limit_str.endswith('g'):
        try: return int(mem_limit_str[:-1]) * 1024 * 1024 * 1024
        except ValueError: return None
    try: return int(mem_limit_str) # Assume bytes if no suffix
    except ValueError: return None

async def _check_command_safety(cog: commands.Cog, command: str) -> Dict[str, Any]:
    """
    Internal helper: Uses an LLM call to assess the safety of a shell command before execution.
    Analyzes potential risks like data destruction, resource exhaustion, etc., within the context
    of a restricted Docker container environment.

    Args:
        cog: The GurtCog instance (automatically passed).
        command: The shell command string to analyze.

    Returns:
        A dictionary containing 'safe' (boolean) and 'reason' (string) based on the AI's assessment, or indicates an error during the check.
    """
    from .api import get_internal_ai_json_response # Import here
    print(f"Performing AI safety check for command: '{command}' using model {SAFETY_CHECK_MODEL}")
    safety_schema = {
        "type": "object",
        "properties": {
            "is_safe": {"type": "boolean", "description": "True if safe for restricted container, False otherwise."},
            "reason": {"type": "string", "description": "Brief explanation."}
        }, "required": ["is_safe", "reason"]
    }
    prompt_messages = [
        {"role": "system", "content": f"Analyze shell command safety for execution in isolated, network-disabled Docker ({DOCKER_EXEC_IMAGE}) with CPU/Mem limits. Focus on data destruction, resource exhaustion, container escape, network attacks (disabled), env var leaks. Simple echo/ls/pwd safe. rm/mkfs/shutdown/wget/curl/install/fork bombs unsafe. Respond ONLY with JSON matching the provided schema."},
        {"role": "user", "content": f"Analyze safety: ```{command}```"}
    ]
    safety_response = await get_internal_ai_json_response(
        cog=cog,
        prompt_messages=prompt_messages,
        task_description="Command Safety Check",
        response_schema_dict=safety_schema, # Pass the schema dict directly
        model_name=SAFETY_CHECK_MODEL,
        temperature=0.1,
        max_tokens=150
    )
    if safety_response and isinstance(safety_response.get("is_safe"), bool):
        is_safe = safety_response["is_safe"]
        reason = safety_response.get("reason", "No reason provided.")
        print(f"AI Safety Check Result: is_safe={is_safe}, reason='{reason}'")
        return {"safe": is_safe, "reason": reason}
    else:
        error_msg = "AI safety check failed or returned invalid format."
        print(f"AI Safety Check Error: Response was {safety_response}")
        return {"safe": False, "reason": error_msg}

@tool
async def run_terminal_command(command: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Executes a shell command within an isolated, network-disabled Docker container.
    Performs an AI safety check before execution. Resource limits (CPU, memory) are applied.

    Args:
        cog: The GurtCog instance (automatically passed).
        command: The shell command string to execute.

    Returns:
        A dictionary containing the execution status ('success', 'execution_error', 'timeout', 'docker_error'), truncated stdout and stderr, and the exit code, or an error dictionary if the safety check fails or Docker setup fails.
    """
    print(f"Attempting terminal command: {command}")
    safety_check_result = await _check_command_safety(cog, command)
    if not safety_check_result.get("safe"):
        error_message = f"Command blocked by AI safety check: {safety_check_result.get('reason', 'Unknown')}"
        print(error_message)
        return {"error": error_message, "command": command}

    try: cpu_limit = float(DOCKER_CPU_LIMIT); cpu_period = 100000; cpu_quota = int(cpu_limit * cpu_period)
    except ValueError: print(f"Warning: Invalid DOCKER_CPU_LIMIT '{DOCKER_CPU_LIMIT}'. Using default."); cpu_quota = 50000; cpu_period = 100000

    mem_limit_bytes = parse_mem_limit(DOCKER_MEM_LIMIT)
    if mem_limit_bytes is None:
        print(f"Warning: Invalid DOCKER_MEM_LIMIT '{DOCKER_MEM_LIMIT}'. Disabling memory limit.")

    client = None
    container = None
    try:
        client = aiodocker.Docker()
        print(f"Running command in Docker ({DOCKER_EXEC_IMAGE})...")

        config = {
            'Image': DOCKER_EXEC_IMAGE,
            'Cmd': ["/bin/sh", "-c", command],
            'AttachStdout': True,
            'AttachStderr': True,
            'HostConfig': {
                'NetworkDisabled': True,
                'AutoRemove': False, # Changed to False
                'CpuPeriod': cpu_period,
                'CpuQuota': cpu_quota,
            }
        }
        if mem_limit_bytes is not None:
            config['HostConfig']['Memory'] = mem_limit_bytes

        # Use wait_for for the run call itself in case image pulling takes time
        container = await asyncio.wait_for(
            client.containers.run(config=config),
            timeout=DOCKER_COMMAND_TIMEOUT + 15 # Add buffer for container start/stop/pull
        )

        # Wait for the container to finish execution
        wait_result = await asyncio.wait_for(
            container.wait(),
            timeout=DOCKER_COMMAND_TIMEOUT
        )
        exit_code = wait_result.get('StatusCode', -1)

        # Get logs after container finishes
        # container.log() returns a list of strings when stream=False (default)
        stdout_lines = await container.log(stdout=True, stderr=False)
        stderr_lines = await container.log(stdout=False, stderr=True)

        stdout = "".join(stdout_lines) if stdout_lines else ""
        stderr = "".join(stderr_lines) if stderr_lines else ""

        max_len = 1000
        stdout_trunc = stdout[:max_len] + ('...' if len(stdout) > max_len else '')
        stderr_trunc = stderr[:max_len] + ('...' if len(stderr) > max_len else '')

        result = {"status": "success" if exit_code == 0 else "execution_error", "stdout": stdout_trunc, "stderr": stderr_trunc, "exit_code": exit_code}
        print(f"Docker command finished. Exit Code: {exit_code}. Output length: {len(stdout)}, Stderr length: {len(stderr)}")
        return result

    except asyncio.TimeoutError:
        print("Docker command run, wait, or log retrieval timed out.")
        # Attempt to stop/remove container if it exists and timed out
        if container:
            try:
                print(f"Attempting to stop timed-out container {container.id[:12]}...")
                await container.stop(t=1)
                print(f"Container {container.id[:12]} stopped.")
                # AutoRemove should handle removal, but log deletion attempt if needed
                # print(f"Attempting to delete timed-out container {container.id[:12]}...")
                # await container.delete(force=True) # Force needed if stop failed?
                # print(f"Container {container.id[:12]} deleted.")
            except aiodocker.exceptions.DockerError as stop_err:
                print(f"Error stopping/deleting timed-out container {container.id[:12]}: {stop_err}")
            except Exception as stop_exc:
                print(f"Unexpected error stopping/deleting timed-out container {container.id[:12]}: {stop_exc}")
        # No need to delete here, finally block will handle it
        return {"error": f"Command execution/log retrieval timed out after {DOCKER_COMMAND_TIMEOUT}s", "command": command, "status": "timeout"}
    except aiodocker.exceptions.DockerError as e: # Catch specific aiodocker errors
        print(f"Docker API error: {e} (Status: {e.status})")
        # Check for ImageNotFound specifically
        if e.status == 404 and ("No such image" in str(e) or "not found" in str(e)):
             print(f"Docker image not found: {DOCKER_EXEC_IMAGE}")
             return {"error": f"Docker image '{DOCKER_EXEC_IMAGE}' not found.", "command": command, "status": "docker_error"}
        return {"error": f"Docker API error ({e.status}): {str(e)}", "command": command, "status": "docker_error"}
    except Exception as e:
        print(f"Unexpected Docker error: {e}")
        traceback.print_exc()
        return {"error": f"Unexpected error during Docker execution: {str(e)}", "command": command, "status": "error"}
    finally:
        # Explicitly remove the container since AutoRemove is False
        if container:
            try:
                print(f"Attempting to delete container {container.id[:12]}...")
                await container.delete(force=True)
                print(f"Container {container.id[:12]} deleted.")
            except aiodocker.exceptions.DockerError as delete_err:
                # Log error but don't raise, primary error is more important
                print(f"Error deleting container {container.id[:12]}: {delete_err}")
            except Exception as delete_exc:
                print(f"Unexpected error deleting container {container.id[:12]}: {delete_exc}")
        # Ensure the client connection is closed
        if client:
            await client.close()

@tool
async def get_user_id(user_name: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Finds the Discord User ID associated with a given username or display name.
    Searches the current server's members first, then falls back to recent message authors if not in a server context.

    Args:
        cog: The GurtCog instance (automatically passed).
        user_name: The username (e.g., "Gurt") or display name (e.g., "GurtBot") to search for. Case-insensitivity is attempted.

    Returns:
        A dictionary containing the status ('success'), user ID, username, and display name if found, or an error dictionary if the user is not found.
    """
    print(f"Attempting to find user ID for: '{user_name}'")
    if not cog.current_channel or not cog.current_channel.guild:
        # Search recent global messages if not in a guild context
        print("No guild context, searching recent global message authors...")
        user_name_lower = user_name.lower()
        found_user = None
        # Check recent message authors (less reliable)
        for msg_data in reversed(list(cog.message_cache['global_recent'])): # Check newest first
            author_info = msg_data.get('author', {})
            if user_name_lower == author_info.get('name', '').lower() or \
               user_name_lower == author_info.get('display_name', '').lower():
                found_user = {"id": author_info.get('id'), "name": author_info.get('name'), "display_name": author_info.get('display_name')}
                break
        if found_user and found_user.get("id"):
            print(f"Found user ID {found_user['id']} for '{user_name}' in global message cache.")
            return {"status": "success", "user_id": found_user["id"], "user_name": found_user["name"], "display_name": found_user["display_name"]}
        else:
            print(f"User '{user_name}' not found in recent global message cache.")
            return {"error": f"User '{user_name}' not found in recent messages.", "user_name": user_name}

    # If in a guild, search members
    guild = cog.current_channel.guild
    member = guild.get_member_named(user_name) # Case-sensitive username#discriminator or exact display name

    if not member: # Try case-insensitive display name search
        user_name_lower = user_name.lower()
        for m in guild.members:
            if m.display_name.lower() == user_name_lower:
                member = m
                break

    if member:
        print(f"Found user ID {member.id} for '{user_name}' in guild '{guild.name}'.")
        return {"status": "success", "user_id": str(member.id), "user_name": member.name, "display_name": member.display_name}
    else:
        print(f"User '{user_name}' not found in guild '{guild.name}'.")
        return {"error": f"User '{user_name}' not found in this server.", "user_name": user_name}

# NOT decorating execute_internal_command as it's marked unsafe for general agent use
async def execute_internal_command(command: str, timeout_seconds: int = 60, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Executes a shell command directly on the host machine where the bot is running.
    **WARNING:** This tool is intended ONLY for internal Gurt operations (e.g., git pull, service restart)
    and MUST NOT be used to execute arbitrary commands requested by users due to significant security risks.
    It bypasses safety checks and containerization. Use with extreme caution and only for trusted, predefined operations.

    Args:
        cog: The GurtCog instance (automatically passed).
        command: The shell command string to execute.
        timeout_seconds: Maximum execution time in seconds (default 60).

    Returns:
        A dictionary containing the execution status ('success', 'execution_error', 'timeout', 'not_found', 'error'),
        truncated stdout and stderr, the exit code, and the original command, or an error dictionary if the command fails.
    """
    print(f"--- INTERNAL EXECUTION (UNSAFE): Running command: {command} ---")
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        exit_code = process.returncode

        stdout = stdout_bytes.decode(errors='replace').strip()
        stderr = stderr_bytes.decode(errors='replace').strip()

        max_len = 1000
        stdout_trunc = stdout[:max_len] + ('...' if len(stdout) > max_len else '')
        stderr_trunc = stderr[:max_len] + ('...' if len(stderr) > max_len else '')

        result = {
            "status": "success" if exit_code == 0 else "execution_error",
            "stdout": stdout_trunc,
            "stderr": stderr_trunc,
            "exit_code": exit_code,
            "command": command
        }
        print(f"Internal command finished. Exit Code: {exit_code}. Output length: {len(stdout)}, Stderr length: {len(stderr)}")
        return result

    except asyncio.TimeoutError:
        print(f"Internal command timed out after {timeout_seconds}s: {command}")
        # Attempt to kill the process if it timed out
        if process and process.returncode is None:
            try:
                process.kill()
                await process.wait() # Ensure it's cleaned up
                print(f"Killed timed-out internal process (PID: {process.pid})")
            except ProcessLookupError:
                print(f"Internal process (PID: {process.pid}) already finished.")
            except Exception as kill_e:
                print(f"Error killing timed-out internal process (PID: {process.pid}): {kill_e}")
        return {"error": f"Command execution timed out after {timeout_seconds}s", "command": command, "status": "timeout"}
    except FileNotFoundError:
        error_message = f"Command not found: {command.split()[0]}"
        print(f"Internal command error: {error_message}")
        return {"error": error_message, "command": command, "status": "not_found"}
    except Exception as e:
        error_message = f"Unexpected error during internal command execution: {str(e)}"
        print(f"Internal command error: {error_message}")
        traceback.print_exc()
        return {"error": error_message, "command": command, "status": "error"}

@tool
async def extract_web_content(urls: Union[str, List[str]], extract_depth: str = "basic", include_images: bool = False, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Extracts the main textual content and optionally images from one or more web URLs using the Tavily API.
    This is useful for getting the content of a webpage without performing a full search.

    Args:
        cog: The GurtCog instance (automatically passed).
        urls: A single URL string or a list of URL strings to extract content from.
        extract_depth: Extraction depth ('basic' or 'advanced'). Advanced costs more credits but may yield better results. Defaults to 'basic'.
        include_images: Whether to include images found on the pages (default False).

    Returns:
        A dictionary containing the original URLs, parameters used, a list of successful results (URL, raw_content, images), a list of failed URLs, and a timestamp, or an error dictionary.
    """
    if not hasattr(cog, 'tavily_client') or not cog.tavily_client:
        return {"error": "Tavily client not initialized.", "timestamp": datetime.datetime.now().isoformat()}

    # Cost control / Logging for advanced extract
    final_extract_depth = extract_depth
    if extract_depth.lower() == "advanced":
        if TAVILY_DISABLE_ADVANCED:
            print(f"Warning: Advanced Tavily extract requested but disabled by config. Falling back to basic.")
            final_extract_depth = "basic"
        else:
            print(f"Performing advanced Tavily extract (cost: 2 credits per 5 URLs) for URLs: {urls}")
    elif extract_depth.lower() != "basic":
        print(f"Warning: Invalid extract_depth '{extract_depth}' provided. Using 'basic'.")
        final_extract_depth = "basic"

    try:
        response = await asyncio.to_thread(
            cog.tavily_client.extract,
            urls=urls,
            extract_depth=final_extract_depth, # Use validated depth
            include_images=include_images
        )
        results = [{"url": r.get("url"), "raw_content": r.get("raw_content"), "images": r.get("images")} for r in response.get("results", [])]
        failed_results = response.get("failed_results", [])
        return {"urls": urls, "extract_depth": extract_depth, "include_images": include_images, "results": results, "failed_results": failed_results, "timestamp": datetime.datetime.now().isoformat()}
    except Exception as e:
        error_message = f"Error during Tavily extract for '{urls}': {str(e)}"
        print(error_message)
        return {"error": error_message, "timestamp": datetime.datetime.now().isoformat()}

@tool
async def read_file_content(file_path: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    Reads the content of a specified file located on the bot's host machine.
    Access is restricted to specific allowed directories and file extensions within the project
    to prevent unauthorized access to sensitive system files.

    Args:
        cog: The GurtCog instance (automatically passed).
        file_path: The relative path to the file from the bot's project root directory.

    Returns:
        A dictionary containing the status ('success'), the file path, and the truncated file content (up to 5000 characters), or an error dictionary if access is denied, the file is not found, or another error occurs.
    """
    print(f"Attempting to read file: {file_path}")
    # --- Basic Safety Check (Needs significant enhancement for production) ---
    # 1. Normalize path
    try:
        # WARNING: This assumes the bot runs from a specific root. Adjust as needed.
        # For now, let's assume the bot runs from the 'combined' directory level.
        # We need to prevent accessing files outside the project directory.
        base_path = os.path.abspath(os.getcwd()) # z:/projects_git/combined
        full_path = os.path.abspath(os.path.join(base_path, file_path))

        # Prevent path traversal (../)
        if not full_path.startswith(base_path):
            error_message = "Access denied: Path traversal detected."
            print(f"Read file error: {error_message} (Attempted: {full_path}, Base: {base_path})")
            return {"error": error_message, "file_path": file_path}

        # 2. Check allowed directories/extensions (Example - very basic)
        allowed_dirs = [os.path.join(base_path, "discordbot"), os.path.join(base_path, "api_service")] # Example allowed dirs
        allowed_extensions = [".py", ".txt", ".md", ".json", ".log", ".cfg", ".ini", ".yaml", ".yml", ".html", ".css", ".js"]
        is_allowed_dir = any(full_path.startswith(allowed) for allowed in allowed_dirs)
        _, ext = os.path.splitext(full_path)
        is_allowed_ext = ext.lower() in allowed_extensions

        # Allow reading only within specific subdirectories of the project
        # For now, let's restrict to reading within 'discordbot' or 'api_service' for safety
        if not is_allowed_dir:
             error_message = f"Access denied: Reading files outside allowed directories is forbidden."
             print(f"Read file error: {error_message} (Path: {full_path})")
             return {"error": error_message, "file_path": file_path}

        if not is_allowed_ext:
            error_message = f"Access denied: Reading files with extension '{ext}' is forbidden."
            print(f"Read file error: {error_message} (Path: {full_path})")
            return {"error": error_message, "file_path": file_path}

    except Exception as path_e:
        error_message = f"Error processing file path: {str(path_e)}"
        print(f"Read file error: {error_message}")
        return {"error": error_message, "file_path": file_path}

    # --- Read File ---
    try:
        # Use async file reading if available/needed, otherwise sync with to_thread
        # For simplicity, using standard open with asyncio.to_thread
        def sync_read():
            with open(full_path, 'r', encoding='utf-8') as f:
                # Limit file size read? For now, read whole file.
                return f.read()

        content = await asyncio.to_thread(sync_read)
        max_len = 5000 # Limit returned content length
        content_trunc = content[:max_len] + ('...' if len(content) > max_len else '')
        print(f"Successfully read {len(content)} bytes from {file_path}. Returning {len(content_trunc)} bytes.")
        return {"status": "success", "file_path": file_path, "content": content_trunc}

    except FileNotFoundError:
        error_message = "File not found."
        print(f"Read file error: {error_message} (Path: {full_path})")
        return {"error": error_message, "file_path": file_path}
    except PermissionError:
        error_message = "Permission denied."
        print(f"Read file error: {error_message} (Path: {full_path})")
        return {"error": error_message, "file_path": file_path}
    except UnicodeDecodeError:
        error_message = "Cannot decode file content (likely not a text file)."
        print(f"Read file error: {error_message} (Path: {full_path})")
        return {"error": error_message, "file_path": file_path}
    except Exception as e:
        error_message = f"An unexpected error occurred: {str(e)}"
        print(f"Read file error: {error_message} (Path: {full_path})")
        traceback.print_exc()
        return {"error": error_message, "file_path": file_path}

# --- Meta Tool: Create New Tool --- (Not decorating as it's experimental/dangerous)
# WARNING: HIGHLY EXPERIMENTAL AND DANGEROUS. Allows AI to write and load code.
async def create_new_tool(tool_name: str, description: str, parameters_json: str, returns_description: str, *, cog: commands.Cog) -> Dict[str, Any]:
    """
    **EXPERIMENTAL & DANGEROUS:** Attempts to dynamically create a new tool for Gurt.
    This involves using an LLM to generate Python code for the tool's function and its
    corresponding FunctionDeclaration definition based on the provided descriptions.
    The generated code is then written directly into `tools.py` and `config.py`.

    **WARNING:** This tool modifies the bot's source code directly and poses significant
    security risks if the generated code is malicious or flawed. It bypasses standard
    code review and testing processes. Use with extreme caution and only in controlled
    development environments. A bot reload or restart is typically required for the
    new tool to become fully active and available to the LLM.

    Args:
        cog: The GurtCog instance (automatically passed).
        tool_name: The desired name for the new tool (must be a valid Python function name).
        description: A natural language description of what the tool does (for the FunctionDeclaration).
        parameters_json: A JSON string defining the tool's input parameters. Must follow the
                         OpenAPI schema format, containing 'type: object', 'properties: {...}',
                         and optionally 'required: [...]'.
        returns_description: A natural language description of what the tool's function should return upon success or error.

    Returns:
        A dictionary indicating the status ('success' or 'error'). On success, includes the
        tool name and a message indicating that a reload is needed. On error, provides an
        error message detailing the failure (e.g., invalid name, generation failure, file write error).
        May include generated code snippets in case of certain errors for debugging.
    """
    print(f"--- DANGEROUS OPERATION: Attempting to create new tool: {tool_name} ---")
    from .api import get_internal_ai_json_response # Local import
    from .config import TOOLS # Import for context, though modifying it runtime is hard

    # Basic validation
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tool_name):
        return {"error": "Invalid tool name. Must be a valid Python function name."}
    if tool_name in TOOL_MAPPING:
        return {"error": f"Tool '{tool_name}' already exists."}
    try:
        params_dict = json.loads(parameters_json)
        if not isinstance(params_dict.get('properties'), dict) or not isinstance(params_dict.get('required'), list):
            raise ValueError("Invalid parameters_json structure. Must contain 'properties' (dict) and 'required' (list).")
    except json.JSONDecodeError:
        return {"error": "Invalid parameters_json. Must be valid JSON."}
    except ValueError as e:
        return {"error": str(e)}

    # --- Prompt LLM to generate code and definition ---
    generation_schema = {
        "type": "object",
        "properties": {
            "python_function_code": {"type": "string", "description": "The complete Python async function code for the new tool, including imports if necessary."},
            "function_declaration_params": {"type": "string", "description": "The JSON string for the 'parameters' part of the FunctionDeclaration."},
            "function_declaration_desc": {"type": "string", "description": "The 'description' string for the FunctionDeclaration."}
        },
        "required": ["python_function_code", "function_declaration_params", "function_declaration_desc"]
    }
    system_prompt = (
        "You are a Python code generation assistant for Gurt, a Discord bot. "
        "Generate the Python code for a new asynchronous tool function and the necessary details for its FunctionDeclaration. "
        "The function MUST be async (`async def`), take `cog: commands.Cog` as its first argument, and accept other arguments as defined in parameters_json. "
        "It MUST return a dictionary, including an 'error' key if something goes wrong, or other relevant keys on success. "
        "Ensure necessary imports are included within the function if not standard library or already likely imported in tools.py (like discord, asyncio, aiohttp, os, json, re, time, random, traceback, Dict, List, Any, Optional). "
        "For the FunctionDeclaration, provide the description and the parameters JSON string based on the user's request. "
        "Respond ONLY with JSON matching the schema."
    )
    user_prompt = (
        f"Create a new tool named '{tool_name}'.\n"
        f"Description for FunctionDeclaration: {description}\n"
        f"Parameters JSON for FunctionDeclaration: {parameters_json}\n"
        f"Description of what the function should return: {returns_description}\n\n"
        "Generate the Python function code and the FunctionDeclaration details:"
    )

    generation_prompt_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    print(f"Generating code for tool '{tool_name}'...")
    generated_data = await get_internal_ai_json_response(
        cog=cog,
        prompt_messages=generation_prompt_messages,
        task_description=f"Generate code for new tool '{tool_name}'",
        response_schema_dict=generation_schema,
        model_name=cog.default_model, # Use default model for generation
        temperature=0.3, # Lower temperature for more predictable code
        max_tokens=1500 # Allow ample space for code generation
    )

    if not generated_data or "python_function_code" not in generated_data or "function_declaration_params" not in generated_data:
        error_msg = f"Failed to generate code for tool '{tool_name}'. LLM response invalid: {generated_data}"
        print(error_msg)
        return {"error": error_msg}

    python_code = generated_data["python_function_code"].strip()
    declaration_params_str = generated_data["function_declaration_params"].strip()
    declaration_desc = generated_data["function_declaration_desc"].strip()
    # Escape quotes in the description *before* using it in the f-string
    escaped_declaration_desc = declaration_desc.replace('"', '\\"')

    # Basic validation of generated code (very superficial)
    if not python_code.startswith("async def") or f" {tool_name}(" not in python_code or "cog: commands.Cog" not in python_code:
         error_msg = f"Generated Python code for '{tool_name}' seems invalid (missing async def, cog param, or function name)."
         print(error_msg)
         print("--- Generated Code ---")
         print(python_code)
         print("----------------------")
         return {"error": error_msg, "generated_code": python_code} # Return code for debugging

    # --- Attempt to write to files (HIGH RISK) ---
    # Note: This is brittle. Concurrent writes or errors could corrupt files.
    # A more robust solution involves separate files and dynamic loading.

    # 1. Write function to tools.py
    tools_py_path = "discordbot/gurt/tools.py"
    try:
        print(f"Attempting to append function to {tools_py_path}...")
        # We need to insert *before* the TOOL_MAPPING definition
        with open(tools_py_path, "r+", encoding="utf-8") as f:
            content = f.readlines()
            insert_line = -1
            for i, line in enumerate(content):
                if line.strip().startswith("TOOL_MAPPING = {"):
                    insert_line = i
                    break
            if insert_line == -1:
                raise RuntimeError("Could not find TOOL_MAPPING definition in tools.py")

            # Insert the new function code before the mapping
            new_function_lines = ["\n"] + [line + "\n" for line in python_code.splitlines()] + ["\n"]
            content[insert_line:insert_line] = new_function_lines

            f.seek(0)
            f.writelines(content)
            f.truncate()
        print(f"Successfully appended function '{tool_name}' to {tools_py_path}")
    except Exception as e:
        error_msg = f"Failed to write function to {tools_py_path}: {e}"
        print(error_msg); traceback.print_exc()
        return {"error": error_msg}

    # 2. Add tool to TOOL_MAPPING in tools.py
    try:
        print(f"Attempting to add '{tool_name}' to TOOL_MAPPING in {tools_py_path}...")
        with open(tools_py_path, "r+", encoding="utf-8") as f:
            content = f.readlines()
            mapping_end_line = -1
            in_mapping = False
            for i, line in enumerate(content):
                if line.strip().startswith("TOOL_MAPPING = {"):
                    in_mapping = True
                if in_mapping and line.strip() == "}":
                    mapping_end_line = i
                    break
            if mapping_end_line == -1:
                 raise RuntimeError("Could not find end of TOOL_MAPPING definition '}' in tools.py")

            # Add the new mapping entry before the closing brace
            new_mapping_line = f'    "{tool_name}": {tool_name},\n'
            content.insert(mapping_end_line, new_mapping_line)

            f.seek(0)
            f.writelines(content)
            f.truncate()
        print(f"Successfully added '{tool_name}' to TOOL_MAPPING.")
    except Exception as e:
        error_msg = f"Failed to add '{tool_name}' to TOOL_MAPPING in {tools_py_path}: {e}"
        print(error_msg); traceback.print_exc()
        # Attempt to revert the function addition if mapping fails? Complex.
        return {"error": error_msg}

    # 3. Add FunctionDeclaration to config.py
    config_py_path = "discordbot/gurt/config.py"
    try:
        print(f"Attempting to add FunctionDeclaration for '{tool_name}' to {config_py_path}...")
        declaration_code = (
            f"    tool_declarations.append(\n"
            f"        generative_models.FunctionDeclaration(\n"
            f"            name=\"{tool_name}\",\n"
            f"            description=\"{escaped_declaration_desc}\", # Use escaped description\n"
            f"            parameters={declaration_params_str} # Generated parameters\n"
            f"        )\n"
            f"    )\n"
        )
        with open(config_py_path, "r+", encoding="utf-8") as f:
            content = f.readlines()
            insert_line = -1
            # Find the line 'return tool_declarations' within create_tools_list
            in_function = False
            for i, line in enumerate(content):
                if "def create_tools_list():" in line:
                    in_function = True
                if in_function and line.strip() == "return tool_declarations":
                    insert_line = i
                    break
            if insert_line == -1:
                raise RuntimeError("Could not find 'return tool_declarations' in config.py")

            # Insert the new declaration code before the return statement
            new_declaration_lines = ["\n"] + [line + "\n" for line in declaration_code.splitlines()]
            content[insert_line:insert_line] = new_declaration_lines

            f.seek(0)
            f.writelines(content)
            f.truncate()
        print(f"Successfully added FunctionDeclaration for '{tool_name}' to {config_py_path}")
    except Exception as e:
        error_msg = f"Failed to add FunctionDeclaration to {config_py_path}: {e}"
        print(error_msg); traceback.print_exc()
        # Attempt to revert previous changes? Very complex.
        return {"error": error_msg}

    # --- Attempt Runtime Update (Limited Scope) ---
    # This will only affect the *current* running instance and won't persist restarts.
    # It also won't update the TOOLS list used by the LLM without a reload.
    try:
        # Dynamically execute the generated code to define the function in the current scope
        # This is risky and might fail depending on imports/scope.
        # exec(python_code, globals()) # Avoid exec if possible
        # A safer way might involve importlib, but that's more complex.

        # For now, just update the runtime TOOL_MAPPING if possible.
        # This requires the function to be somehow available in the current scope.
        # Let's assume for now it needs a restart/reload.
        print(f"Runtime update of TOOL_MAPPING for '{tool_name}' skipped. Requires bot reload.")
        # If we could dynamically import:
        # TOOL_MAPPING[tool_name] = dynamically_imported_function

    except Exception as e:
        print(f"Error during runtime update attempt for '{tool_name}': {e}")
        # Don't return error here, as file writes succeeded.

    return {
        "status": "success",
        "tool_name": tool_name,
        "message": f"Tool '{tool_name}' code and definition written to files. Bot reload/restart likely required for full activation.",
        "generated_function_code": python_code, # Return for inspection
        "generated_declaration_desc": declaration_desc,
        "generated_declaration_params": declaration_params_str
    }


# --- Tool Mapping ---
# This dictionary maps tool names (used in the AI prompt) to their implementation functions.
# The agent should discover tools via the @tool decorator, but this mapping might still be used elsewhere.
# Keep it updated, but the primary mechanism for the agent is the decorator.
TOOL_MAPPING = {
    "get_recent_messages": get_recent_messages,
    "search_user_messages": search_user_messages,
    "search_messages_by_content": search_messages_by_content,
    "get_channel_info": get_channel_info,
    "get_conversation_context": get_conversation_context,
    "get_thread_context": get_thread_context,
    "get_user_interaction_history": get_user_interaction_history,
    "get_conversation_summary": get_conversation_summary,
    "get_message_context": get_message_context,
    "web_search": web_search,
    # Memory tools using direct function references
    "remember_user_fact": remember_user_fact,
    "get_user_facts": get_user_facts,
    "remember_general_fact": remember_general_fact,
    "get_general_facts": get_general_facts,
    "timeout_user": timeout_user,
    "calculate": calculate,
    "run_python_code": run_python_code,
    "create_poll": create_poll,
    "run_terminal_command": run_terminal_command,
    "remove_timeout": remove_timeout,
    "extract_web_content": extract_web_content,
    "read_file_content": read_file_content,
    "create_new_tool": create_new_tool, # Meta-tool (not decorated)
    "execute_internal_command": execute_internal_command, # Internal command execution (not decorated)
    "get_user_id": get_user_id # Added user ID lookup tool
}
