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
#       We will add 'cog' as the first parameter to each.

async def get_recent_messages(cog: commands.Cog, limit: int, channel_id: str = None) -> Dict[str, Any]:
    """Get recent messages from a Discord channel"""
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

async def search_user_messages(cog: commands.Cog, user_id: str, limit: int, channel_id: str = None) -> Dict[str, Any]:
    """Search for messages from a specific user"""
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

async def search_messages_by_content(cog: commands.Cog, search_term: str, limit: int, channel_id: str = None) -> Dict[str, Any]:
    """Search for messages containing specific content"""
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

async def get_channel_info(cog: commands.Cog, channel_id: str = None) -> Dict[str, Any]:
    """Get information about a Discord channel"""
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

async def get_conversation_context(cog: commands.Cog, message_count: int, channel_id: str = None) -> Dict[str, Any]:
    """Get the context of the current conversation in a channel"""
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

async def get_thread_context(cog: commands.Cog, thread_id: str, message_count: int) -> Dict[str, Any]:
    """Get the context of a thread conversation"""
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

async def get_user_interaction_history(cog: commands.Cog, user_id_1: str, limit: int, user_id_2: str = None) -> Dict[str, Any]:
    """Get the history of interactions between two users (or user and bot)"""
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

async def get_conversation_summary(cog: commands.Cog, channel_id: str = None, message_limit: int = 25) -> Dict[str, Any]:
    """Generates and returns a summary of the recent conversation in a channel using an LLM call."""
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
        # Unpack the tuple, we only need the parsed data here
        summary_parsed_data, _ = summary_data if summary_data else (None, None)

        summary = "Error generating summary."
        if summary_parsed_data and isinstance(summary_parsed_data.get("summary"), str):
            summary = summary_parsed_data["summary"].strip()
            print(f"Summary generated for {target_channel_id}: {summary[:100]}...")
        else:
            error_detail = f"Invalid format or missing 'summary' key. Parsed Response: {summary_parsed_data}" # Log parsed data on error
            summary = f"Failed summary for {target_channel_id}. Error: {error_detail}"
            print(summary)

        cog.conversation_summaries[target_channel_id] = {"summary": summary, "timestamp": time.time()}
        return {"channel_id": target_channel_id_str, "summary": summary, "source": "generated", "timestamp": datetime.datetime.now().isoformat()}

    except Exception as e:
        error_msg = f"General error in get_conversation_summary: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return {"error": error_msg}

async def get_message_context(cog: commands.Cog, message_id: str, before_count: int = 5, after_count: int = 5) -> Dict[str, Any]:
    """Get the context (messages before and after) around a specific message"""
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

async def web_search(cog: commands.Cog, query: str, search_depth: str = TAVILY_DEFAULT_SEARCH_DEPTH, max_results: int = TAVILY_DEFAULT_MAX_RESULTS, topic: str = "general", include_domains: Optional[List[str]] = None, exclude_domains: Optional[List[str]] = None, include_answer: bool = True, include_raw_content: bool = False, include_images: bool = False) -> Dict[str, Any]:
    """Search the web using Tavily API"""
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

async def remember_user_fact(cog: commands.Cog, user_id: str, fact: str) -> Dict[str, Any]:
    """Stores a fact about a user using the MemoryManager."""
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

async def get_user_facts(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Retrieves stored facts about a user using the MemoryManager."""
    if not user_id: return {"error": "user_id required."}
    print(f"Retrieving facts for user {user_id}")
    try:
        user_facts = await cog.memory_manager.get_user_facts(user_id) # Context not needed for basic retrieval tool
        return {"user_id": user_id, "facts": user_facts, "count": len(user_facts), "timestamp": datetime.datetime.now().isoformat()}
    except Exception as e:
        error_message = f"Error calling MemoryManager for user facts {user_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

async def remember_general_fact(cog: commands.Cog, fact: str) -> Dict[str, Any]:
    """Stores a general fact using the MemoryManager."""
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

async def get_general_facts(cog: commands.Cog, query: Optional[str] = None, limit: Optional[int] = 10) -> Dict[str, Any]:
    """Retrieves stored general facts using the MemoryManager."""
    print(f"Retrieving general facts (query='{query}', limit={limit})")
    limit = min(max(1, limit or 10), 50)
    try:
        general_facts = await cog.memory_manager.get_general_facts(query=query, limit=limit) # Context not needed here
        return {"query": query, "facts": general_facts, "count": len(general_facts), "timestamp": datetime.datetime.now().isoformat()}
    except Exception as e:
        error_message = f"Error calling MemoryManager for general facts: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

async def timeout_user(cog: commands.Cog, user_id: str, duration_minutes: int, reason: Optional[str] = None) -> Dict[str, Any]:
    """Times out a user in the current server."""
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

async def remove_timeout(cog: commands.Cog, user_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """Removes an active timeout from a user."""
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

async def calculate(cog: commands.Cog, expression: str) -> Dict[str, Any]:
    """Evaluates a mathematical expression using asteval."""
    print(f"Calculating expression: {expression}")
    aeval = Interpreter()
    try:
        result = aeval(expression)
        if aeval.error:
            error_details = '; '.join(err.get_error() for err in aeval.error)
            error_message = f"Calculation error: {error_details}"
            print(error_message)
            return {"error": error_message, "expression": expression}

        if isinstance(result, (int, float, complex)): result_str = str(result)
        else: result_str = repr(result) # Fallback

        print(f"Calculation result: {result_str}")
        return {"expression": expression, "result": result_str, "status": "success"}
    except Exception as e:
        error_message = f"Unexpected error during calculation: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message, "expression": expression}

async def run_python_code(cog: commands.Cog, code: str) -> Dict[str, Any]:
    """Executes a Python code snippet using the Piston API."""
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

async def create_poll(cog: commands.Cog, question: str, options: List[str]) -> Dict[str, Any]:
    """Creates a simple poll message."""
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

# Helper function to convert memory string (e.g., "128m") to bytes
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
    """Uses a secondary AI call to check if a command is potentially harmful."""
    from .api import get_internal_ai_json_response # Import here
    print(f"Performing AI safety check for command: '{command}' using model {SAFETY_CHECK_MODEL}")
    safety_schema = {
        "type": "object",
        "properties": {
            "is_safe": {"type": "boolean", "description": "True if safe for restricted container, False otherwise."},
            "reason": {"type": "string", "description": "Brief explanation why the command is safe or unsafe."}
        }, "required": ["is_safe", "reason"]
    }
    # Enhanced system prompt with more examples of safe commands
    system_prompt_content = (
        f"Analyze shell command safety for execution in an isolated, network-disabled Docker container ({DOCKER_EXEC_IMAGE}) "
        f"with CPU ({DOCKER_CPU_LIMIT} core) and Memory ({DOCKER_MEM_LIMIT}) limits. "
        "Focus on preventing: data destruction (outside container's ephemeral storage), resource exhaustion (fork bombs, crypto mining), "
        "container escape vulnerabilities, network attacks (network is disabled), sensitive environment variable leakage (assume only safe vars are mounted). "
        "Commands that only read system info, list files, print text, or manipulate text are generally SAFE. "
        "Examples of SAFE commands: whoami, id, uname, hostname, pwd, ls, echo, cat, grep, sed, awk, date, time, env, df, du, ps, top, htop, find (read-only), file. "
        "Examples of UNSAFE commands: rm, mkfs, shutdown, reboot, poweroff, wget, curl, apt, yum, apk, pip install, npm install, git clone (network disabled, but still potentially risky), "
        "any command trying to modify system files outside /tmp or /home, fork bombs like ':(){ :|:& };:', commands enabling network access. "
        "Be cautious with file writing/modification commands if not clearly limited to temporary directories. "
        "Respond ONLY with the raw JSON object matching the provided schema."
    )
    prompt_messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": f"Analyze safety of this command: ```\n{command}\n```"}
    ]
    # Update to receive tuple: (parsed_data, raw_text)
    safety_response_parsed, safety_response_raw = await get_internal_ai_json_response(
        cog=cog,
        prompt_messages=prompt_messages,
        task_description="Command Safety Check",
         response_schema_dict=safety_schema, # Pass the schema dict directly
         model_name=SAFETY_CHECK_MODEL,
         temperature=0.1,
         max_tokens=1000 # Increased token limit
     )

    # --- Log the raw response text ---
    print(f"--- Raw AI Safety Check Response Text ---\n{safety_response_raw}\n---------------------------------------")

    if safety_response_parsed and isinstance(safety_response_parsed.get("is_safe"), bool):
        is_safe = safety_response_parsed["is_safe"]
        reason = safety_response_parsed.get("reason", "No reason provided.")
        print(f"AI Safety Check Result (Parsed): is_safe={is_safe}, reason='{reason}'")
        return {"safe": is_safe, "reason": reason}
    else:
        # Include part of the raw response in the error for debugging if parsing failed
        raw_response_excerpt = str(safety_response_raw)[:200] if safety_response_raw else "N/A"
        error_msg = f"AI safety check failed to parse or returned invalid format. Raw Response: {raw_response_excerpt}"
        print(f"AI Safety Check Error: {error_msg}")
        # Also log the parsed attempt if it exists but was invalid
        if safety_response_parsed:
             print(f"Parsed attempt was: {safety_response_parsed}")
        return {"safe": False, "reason": error_msg}

async def run_terminal_command(cog: commands.Cog, command: str) -> Dict[str, Any]:
    """Executes a shell command in an isolated Docker container after an AI safety check."""
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
async def get_user_id(cog: commands.Cog, user_name: str) -> Dict[str, Any]:
    """Finds the Discord User ID for a given username or display name."""
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


async def execute_internal_command(cog: commands.Cog, command: str, timeout_seconds: int = 60) -> Dict[str, Any]:
    """
    Executes a shell command directly on the host machine where the bot is running.
    WARNING: This tool is intended ONLY for internal Gurt operations and MUST NOT
    be used to execute arbitrary commands requested by users due to significant security risks.
    It bypasses safety checks and containerization. Use with extreme caution.
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

async def extract_web_content(cog: commands.Cog, urls: Union[str, List[str]], extract_depth: str = "basic", include_images: bool = False) -> Dict[str, Any]:
    """Extract content from URLs using Tavily API"""
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

async def read_file_content(cog: commands.Cog, file_path: str) -> Dict[str, Any]:
    """
    Reads the content of a specified file. WARNING: No safety checks are performed.
    Reads files relative to the bot's current working directory.
    """
    print(f"--- UNSAFE READ: Attempting to read file: {file_path} ---")
    try:
        # Normalize path relative to CWD
        base_path = os.path.abspath(os.getcwd())
        full_path = os.path.abspath(os.path.join(base_path, file_path))
        # Minimal check: Ensure it's still somehow within a reasonable project structure if possible?
        # Or just allow anything? For now, allow anything but log the path.
        print(f"--- UNSAFE READ: Reading absolute path: {full_path} ---")

        # Use async file reading if available/needed, otherwise sync with to_thread
        def sync_read():
            with open(full_path, 'r', encoding='utf-8') as f:
                # Limit file size read? For now, read whole file. Consider adding limit later.
                return f.read()

        content = await asyncio.to_thread(sync_read)
        max_len = 10000 # Increased limit for potentially larger reads
        content_trunc = content[:max_len] + ('...' if len(content) > max_len else '')
        print(f"--- UNSAFE READ: Successfully read {len(content)} bytes from {file_path}. Returning {len(content_trunc)} bytes. ---")
        return {"status": "success", "file_path": file_path, "content": content_trunc}

    except FileNotFoundError:
        error_message = "File not found."
        print(f"--- UNSAFE READ Error: {error_message} (Path: {full_path}) ---")
        return {"error": error_message, "file_path": file_path}
    except PermissionError:
        error_message = "Permission denied."
        print(f"--- UNSAFE READ Error: {error_message} (Path: {full_path}) ---")
        return {"error": error_message, "file_path": file_path}
    except UnicodeDecodeError:
        error_message = "Cannot decode file content (likely not a text file)."
        print(f"--- UNSAFE READ Error: {error_message} (Path: {full_path}) ---")
        return {"error": error_message, "file_path": file_path}
    except IsADirectoryError:
        error_message = "Specified path is a directory, not a file."
        print(f"--- UNSAFE READ Error: {error_message} (Path: {full_path}) ---")
        return {"error": error_message, "file_path": file_path}
    except Exception as e:
        error_message = f"An unexpected error occurred: {str(e)}"
        print(f"--- UNSAFE READ Error: {error_message} (Path: {full_path}) ---")
        traceback.print_exc()
        return {"error": error_message, "file_path": file_path}

async def write_file_content_unsafe(cog: commands.Cog, file_path: str, content: str, mode: str = 'w') -> Dict[str, Any]:
    """
    Writes content to a specified file. WARNING: No safety checks are performed.
    Uses 'w' (overwrite) or 'a' (append) mode. Creates directories if needed.
    """
    print(f"--- UNSAFE WRITE: Attempting to write to file: {file_path} (Mode: {mode}) ---")
    if mode not in ['w', 'a']:
        return {"error": "Invalid mode. Use 'w' (overwrite) or 'a' (append).", "file_path": file_path}

    try:
        # Normalize path relative to CWD
        base_path = os.path.abspath(os.getcwd())
        full_path = os.path.abspath(os.path.join(base_path, file_path))
        print(f"--- UNSAFE WRITE: Writing to absolute path: {full_path} ---")

        # Create directories if they don't exist
        dir_path = os.path.dirname(full_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"--- UNSAFE WRITE: Created directory: {dir_path} ---")

        # Use async file writing if available/needed, otherwise sync with to_thread
        def sync_write():
            with open(full_path, mode, encoding='utf-8') as f:
                bytes_written = f.write(content)
            return bytes_written

        bytes_written = await asyncio.to_thread(sync_write)
        print(f"--- UNSAFE WRITE: Successfully wrote {bytes_written} bytes to {file_path} (Mode: {mode}). ---")
        return {"status": "success", "file_path": file_path, "bytes_written": bytes_written, "mode": mode}

    except PermissionError:
        error_message = "Permission denied."
        print(f"--- UNSAFE WRITE Error: {error_message} (Path: {full_path}) ---")
        return {"error": error_message, "file_path": file_path}
    except IsADirectoryError:
        error_message = "Specified path is a directory, cannot write to it."
        print(f"--- UNSAFE WRITE Error: {error_message} (Path: {full_path}) ---")
        return {"error": error_message, "file_path": file_path}
    except Exception as e:
        error_message = f"An unexpected error occurred during write: {str(e)}"
        print(f"--- UNSAFE WRITE Error: {error_message} (Path: {full_path}) ---")
        traceback.print_exc()
        return {"error": error_message, "file_path": file_path}

async def execute_python_unsafe(cog: commands.Cog, code: str, timeout_seconds: int = 30) -> Dict[str, Any]:
    """
    Executes arbitrary Python code directly on the host using exec().
    WARNING: EXTREMELY DANGEROUS. No sandboxing. Can access/modify anything the bot process can.
    Captures stdout/stderr and handles timeouts.
    """
    print(f"--- UNSAFE PYTHON EXEC: Attempting to execute code: {code[:200]}... ---")
    import io
    import contextlib
    import threading

    local_namespace = {'cog': cog, 'asyncio': asyncio, 'discord': discord, 'random': random, 'os': os, 'time': time} # Provide some context
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result = {"status": "unknown", "stdout": "", "stderr": "", "error": None}
    exec_exception = None

    def target():
        nonlocal exec_exception
        try:
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                # Execute the code in a restricted namespace? For now, use globals() + locals
                exec(code, globals(), local_namespace)
        except Exception as e:
            nonlocal exec_exception
            exec_exception = e
            print(f"--- UNSAFE PYTHON EXEC: Exception during execution: {e} ---")
            traceback.print_exc(file=stderr_capture) # Also print traceback to stderr capture

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Timeout occurred - This is tricky to kill reliably from another thread in Python
        # For now, we just report the timeout. The code might still be running.
        result["status"] = "timeout"
        result["error"] = f"Execution timed out after {timeout_seconds} seconds. Code might still be running."
        print(f"--- UNSAFE PYTHON EXEC: Timeout after {timeout_seconds}s ---")
    elif exec_exception:
        result["status"] = "execution_error"
        result["error"] = f"Exception during execution: {str(exec_exception)}"
    else:
        result["status"] = "success"
        print("--- UNSAFE PYTHON EXEC: Execution completed successfully. ---")

    stdout_val = stdout_capture.getvalue()
    stderr_val = stderr_capture.getvalue()
    max_len = 2000
    result["stdout"] = stdout_val[:max_len] + ('...' if len(stdout_val) > max_len else '')
    result["stderr"] = stderr_val[:max_len] + ('...' if len(stderr_val) > max_len else '')

    stdout_capture.close()
    stderr_capture.close()

    return result

async def send_discord_message(cog: commands.Cog, channel_id: str, message_content: str) -> Dict[str, Any]:
    """Sends a message to a specified Discord channel."""
    print(f"Attempting to send message to channel {channel_id}: {message_content[:100]}...")
    if not message_content:
        return {"error": "Message content cannot be empty."}
    # Limit message length
    max_msg_len = 1900 # Slightly less than Discord limit
    message_content = message_content[:max_msg_len] + ('...' if len(message_content) > max_msg_len else '')

    try:
        channel_id_int = int(channel_id)
        channel = cog.bot.get_channel(channel_id_int)
        if not channel:
            # Try fetching if not in cache
            channel = await cog.bot.fetch_channel(channel_id_int)

        if not channel:
            return {"error": f"Channel {channel_id} not found or inaccessible."}
        if not isinstance(channel, discord.abc.Messageable):
            return {"error": f"Channel {channel_id} is not messageable (Type: {type(channel)})."}

        # Check permissions if it's a guild channel
        if isinstance(channel, discord.abc.GuildChannel):
            bot_member = channel.guild.me
            if not channel.permissions_for(bot_member).send_messages:
                return {"error": f"Missing 'Send Messages' permission in channel {channel_id}."}

        sent_message = await channel.send(message_content)
        print(f"Successfully sent message {sent_message.id} to channel {channel_id}.")
        return {"status": "success", "channel_id": channel_id, "message_id": str(sent_message.id)}

    except ValueError:
        return {"error": f"Invalid channel ID format: {channel_id}."}
    except discord.NotFound:
        return {"error": f"Channel {channel_id} not found."}
    except discord.Forbidden:
        return {"error": f"Forbidden: Missing permissions to send message in channel {channel_id}."}
    except discord.HTTPException as e:
        error_message = f"API error sending message to {channel_id}: {e}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:
        error_message = f"Unexpected error sending message to {channel_id}: {str(e)}"
        print(error_message)
        traceback.print_exc()
        return {"error": error_message}


# --- Meta Tool: Create New Tool ---
# WARNING: HIGHLY EXPERIMENTAL AND DANGEROUS. Allows AI to write and load code.
async def create_new_tool(cog: commands.Cog, tool_name: str, description: str, parameters_json: str, returns_description: str) -> Dict[str, Any]:
    """
    EXPERIMENTAL/DANGEROUS: Attempts to create a new tool by generating Python code
    and its definition using an LLM, then writing it to tools.py and config.py.
    Requires manual reload/restart of the bot for the tool to be fully active.
    Parameters JSON should be a JSON string describing the 'properties' and 'required' fields
    for the tool's parameters, similar to other FunctionDeclarations.
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
        max_tokens=5000 # Allow ample space for code generation
    )
    # Unpack the tuple, we only need the parsed data here
    generated_parsed_data, _ = generated_data if generated_data else (None, None)

    if not generated_parsed_data or "python_function_code" not in generated_parsed_data or "function_declaration_params" not in generated_parsed_data:
        error_msg = f"Failed to generate code for tool '{tool_name}'. LLM response invalid: {generated_parsed_data}" # Log parsed data on error
        print(error_msg)
        return {"error": error_msg}

    python_code = generated_parsed_data["python_function_code"].strip()
    declaration_params_str = generated_parsed_data["function_declaration_params"].strip()
    declaration_desc = generated_parsed_data["function_declaration_desc"].strip()
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
        # Use FunctionDeclaration directly, assuming it's imported in config.py
        declaration_code = (
            f"    tool_declarations.append(\n"
            f"        FunctionDeclaration( # Use imported FunctionDeclaration\n"
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
        #   thon_code, globals()) # Avoid exec if possible
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

async def no_operation(cog: commands.Cog) -> Dict[str, Any]:
    """
    Does absolutely nothing. Used when a tool call is forced but no action is needed.
    """
    print("Executing no_operation tool.")
    return {"status": "success", "message": "No operation performed."}


# --- Tool Mapping ---
# This dictionary maps tool names (used in the AI prompt) to their implementation functions.
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
    # Point memory tools to the methods on the MemoryManager instance (accessed via cog)
    "remember_user_fact": lambda cog, **kwargs: cog.memory_manager.add_user_fact(**kwargs),
    "get_user_facts": lambda cog, **kwargs: cog.memory_manager.get_user_facts(**kwargs),
    "remember_general_fact": lambda cog, **kwargs: cog.memory_manager.add_general_fact(**kwargs),
    "get_general_facts": lambda cog, **kwargs: cog.memory_manager.get_general_facts(**kwargs),
    "timeout_user": timeout_user,
    "calculate": calculate,
    "run_python_code": run_python_code,
    "create_poll": create_poll,
    "run_terminal_command": run_terminal_command,
    "remove_timeout": remove_timeout,
    "extract_web_content": extract_web_content,
    "read_file_content": read_file_content, # Now unsafe
    "write_file_content_unsafe": write_file_content_unsafe, # New unsafe tool
    "execute_python_unsafe": execute_python_unsafe, # New unsafe tool
    "send_discord_message": send_discord_message, # New tool
    "create_new_tool": create_new_tool, # Added the meta-tool
    "execute_internal_command": execute_internal_command, # Added internal command execution
    "get_user_id": get_user_id, # Added user ID lookup tool
    "no_operation": no_operation # Added no-op tool
}
