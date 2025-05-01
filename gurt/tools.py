import sys
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
    TOOLS, # Import the TOOLS list
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
        user_name = " "
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
            model_name_override=DEFAULT_MODEL, # Consider a cheaper/faster model if needed
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
         model_name_override=SAFETY_CHECK_MODEL,
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


async def execute_internal_command(cog: commands.Cog, command: str, timeout_seconds: int = 60, user_id: str = None) -> Dict[str, Any]:
    """
    Executes a shell command directly on the host machine where the bot is running.
    WARNING: This tool is intended ONLY for internal Gurt operations and MUST NOT
    be used to execute arbitrary commands requested by users due to significant security risks.
    It bypasses safety checks and containerization. Use with extreme caution.
    Only user ID 452666956353503252 is allowed to execute this command.
    """
    if user_id != "452666956353503252":
        return {"error": "The requesting user is not authorized to execute commands.", "status": "unauthorized"}
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

async def restart_gurt_bot(cog: commands.Cog, channel_id: str = None) -> Dict[str, Any]:
    """
    Restarts the Gurt bot process by re-executing the current Python script.
    Sends a message in the specified channel before restarting.
    The caller MUST provide a valid channel_id where the restart was invoked.
    Returns a status dictionary. Only works if the bot process has permission.
    """
    import sys
    import os
    if not channel_id:
        return {"error": "channel_id must be provided to send the restart message in the correct channel."}
    try:
        await send_discord_message(cog, channel_id, "Restart tool was called.")
    except Exception as msg_exc:
        print(f"Failed to send restart message: {msg_exc}")
    try:
        python = sys.executable
        os.execv(python, [python] + sys.argv)
        return {"status": "restarting", "message": "Gurt bot is restarting..."}
    except Exception as e:
        return {"status": "error", "error": f"Failed to restart: {str(e)}"}

async def run_git_pull(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """
    Runs 'git pull' in the bot's current working directory on the host machine.
    Requires authorization via user_id. Returns the output and status.
    """
    return await execute_internal_command(cog=cog, command="git pull", user_id=user_id)

async def send_discord_message(cog: commands.Cog, channel_id: str, message_content: str) -> Dict[str, Any]:
    """Sends a message to a specified Discord channel."""
    print(f"Attempting to send message to channel {channel_id}: {message_content[:100]}...")
    # Ensure this function doesn't contain the logic accidentally put in the original run_git_pull
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
        model_name_override=cog.default_model, # Use default model for generation
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


async def get_channel_id(cog: commands.Cog, channel_name: str = None) -> Dict[str, Any]:
    """
    Returns the Discord channel ID for a given channel name in the current guild.
    If no channel_name is provided, returns the ID of the current channel.
    """
    try:
        if channel_name:
            if not cog.current_channel or not cog.current_channel.guild:
                return {"error": "No guild context to search for channel."}
            guild = cog.current_channel.guild
            # Try to find by name (case-insensitive)
            for channel in guild.channels:
                if hasattr(channel, "name") and channel.name.lower() == channel_name.lower():
                    return {"status": "success", "channel_id": str(channel.id), "channel_name": channel.name}
            return {"error": f"Channel '{channel_name}' not found in this server."}
        else:
            channel = cog.current_channel
            if not channel:
                return {"error": "No current channel context."}
            return {"status": "success", "channel_id": str(channel.id), "channel_name": getattr(channel, "name", "DM Channel")}
    except Exception as e:
        return {"error": f"Error getting channel ID: {str(e)}"}

# Tool 1: get_guild_info
async def get_guild_info(cog: commands.Cog) -> Dict[str, Any]:
    """Gets information about the current Discord server."""
    print("Executing get_guild_info tool.")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot get guild info outside of a server channel."}
    guild = cog.current_channel.guild
    if not guild:
        return {"error": "Could not determine the current server."}

    try:
        owner = guild.owner or await guild.fetch_member(guild.owner_id) # Fetch if not cached
        owner_info = {"id": str(owner.id), "name": owner.name, "display_name": owner.display_name} if owner else None

        return {
            "status": "success",
            "guild_id": str(guild.id),
            "name": guild.name,
            "description": guild.description,
            "member_count": guild.member_count,
            "created_at": guild.created_at.isoformat(),
            "owner": owner_info,
            "icon_url": str(guild.icon.url) if guild.icon else None,
            "banner_url": str(guild.banner.url) if guild.banner else None,
            "features": guild.features,
            "preferred_locale": guild.preferred_locale,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error getting guild info: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 2: list_guild_members
async def list_guild_members(cog: commands.Cog, limit: int = 50, status_filter: Optional[str] = None, role_id_filter: Optional[str] = None) -> Dict[str, Any]:
    """Lists members in the current server, with optional filters."""
    print(f"Executing list_guild_members tool (limit={limit}, status={status_filter}, role={role_id_filter}).")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot list members outside of a server channel."}
    guild = cog.current_channel.guild
    if not guild:
        return {"error": "Could not determine the current server."}

    limit = min(max(1, limit), 1000) # Limit fetch size
    members_list = []
    role_filter_obj = None
    if role_id_filter:
        try:
            role_filter_obj = guild.get_role(int(role_id_filter))
            if not role_filter_obj:
                return {"error": f"Role ID {role_id_filter} not found."}
        except ValueError:
            return {"error": f"Invalid role ID format: {role_id_filter}."}

    valid_statuses = ["online", "idle", "dnd", "offline"]
    status_filter_lower = status_filter.lower() if status_filter else None
    if status_filter_lower and status_filter_lower not in valid_statuses:
        return {"error": f"Invalid status_filter. Use one of: {', '.join(valid_statuses)}"}

    try:
        # Fetching all members can be intensive, use guild.members if populated, otherwise fetch cautiously
        # Note: Fetching all members requires the Members privileged intent.
        fetched_members = guild.members # Use cached first
        if len(fetched_members) < guild.member_count and cog.bot.intents.members:
             print(f"Fetching members for guild {guild.id} as cache seems incomplete...")
             # This might take time and requires the intent
             # Consider adding a timeout or limiting the fetch if it's too slow
             fetched_members = await guild.fetch_members(limit=None).flatten() # Fetch all if intent is enabled

        count = 0
        for member in fetched_members:
            if status_filter_lower and str(member.status) != status_filter_lower:
                continue
            if role_filter_obj and role_filter_obj not in member.roles:
                continue

            members_list.append({
                "id": str(member.id),
                "name": member.name,
                "display_name": member.display_name,
                "bot": member.bot,
                "status": str(member.status),
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "roles": [{"id": str(r.id), "name": r.name} for r in member.roles if r.name != "@everyone"]
            })
            count += 1
            if count >= limit:
                break

        return {
            "status": "success",
            "guild_id": str(guild.id),
            "filters_applied": {"limit": limit, "status": status_filter, "role_id": role_id_filter},
            "members": members_list,
            "count": len(members_list),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except discord.Forbidden:
         return {"error": "Missing permissions or intents (Members) to list guild members."}
    except Exception as e:
        error_message = f"Error listing guild members: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 3: get_user_avatar
async def get_user_avatar(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets the avatar URL for a given user ID."""
    print(f"Executing get_user_avatar tool for user ID: {user_id}.")
    try:
        user_id_int = int(user_id)
        user = cog.bot.get_user(user_id_int) or await cog.bot.fetch_user(user_id_int)
        if not user:
            return {"error": f"User with ID {user_id} not found."}

        avatar_url = str(user.display_avatar.url) # display_avatar handles default/server avatar

        return {
            "status": "success",
            "user_id": user_id,
            "user_name": user.name,
            "avatar_url": avatar_url,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except ValueError:
        return {"error": f"Invalid user ID format: {user_id}."}
    except discord.NotFound:
        return {"error": f"User with ID {user_id} not found."}
    except Exception as e:
        error_message = f"Error getting user avatar: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 4: get_bot_uptime
async def get_bot_uptime(cog: commands.Cog) -> Dict[str, Any]:
    """Gets the uptime of the bot."""
    print("Executing get_bot_uptime tool.")
    if not hasattr(cog, 'start_time'):
         return {"error": "Bot start time not recorded in cog."} # Assumes cog has a start_time attribute

    try:
        uptime_delta = datetime.datetime.now(datetime.timezone.utc) - cog.start_time
        total_seconds = int(uptime_delta.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        return {
            "status": "success",
            "start_time": cog.start_time.isoformat(),
            "current_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "uptime_seconds": total_seconds,
            "uptime_formatted": uptime_str,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error calculating bot uptime: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 5: schedule_message
# This requires a persistent scheduling mechanism (like APScheduler or storing in DB)
# For simplicity, this example won't implement persistence, making it non-functional across restarts.
# A real implementation needs a background task scheduler.
async def schedule_message(cog: commands.Cog, channel_id: str, message_content: str, send_at_iso: str) -> Dict[str, Any]:
    """Schedules a message to be sent in a channel at a specific ISO 8601 time."""
    print(f"Executing schedule_message tool: Channel={channel_id}, Time={send_at_iso}, Content='{message_content[:50]}...'")
    if not hasattr(cog, 'scheduler') or not cog.scheduler:
         return {"error": "Scheduler not available in the cog. Cannot schedule messages persistently."}

    try:
        send_time = datetime.datetime.fromisoformat(send_at_iso)
        # Ensure timezone awareness, assume UTC if naive? Or require timezone? Let's require it.
        if send_time.tzinfo is None:
            return {"error": "send_at_iso must include timezone information (e.g., +00:00 or Z)."}

        now = datetime.datetime.now(datetime.timezone.utc)
        if send_time <= now:
            return {"error": "Scheduled time must be in the future."}

        channel_id_int = int(channel_id)
        channel = cog.bot.get_channel(channel_id_int)
        if not channel:
            # Try fetching if not in cache
            channel = await cog.bot.fetch_channel(channel_id_int)
        if not channel or not isinstance(channel, discord.abc.Messageable):
             return {"error": f"Channel {channel_id} not found or not messageable."}

        # Limit message length
        max_msg_len = 1900
        message_content = message_content[:max_msg_len] + ('...' if len(message_content) > max_msg_len else '')

        # --- Scheduling Logic ---
        # This uses cog.scheduler.add_job which needs to be implemented using e.g., APScheduler
        job = cog.scheduler.add_job(
            send_discord_message, # Use the existing tool function
            'date',
            run_date=send_time,
            args=[cog, channel_id, message_content], # Pass necessary args
            id=f"scheduled_msg_{channel_id}_{int(time.time())}", # Unique job ID
            misfire_grace_time=600 # Allow 10 mins grace period
        )
        print(f"Scheduled job {job.id} to send message at {send_time.isoformat()}")

        return {
            "status": "success",
            "job_id": job.id,
            "channel_id": channel_id,
            "message_content_preview": message_content[:100],
            "scheduled_time_utc": send_time.astimezone(datetime.timezone.utc).isoformat(),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except ValueError as e:
        return {"error": f"Invalid format for channel_id or send_at_iso: {e}"}
    except (discord.NotFound, discord.Forbidden):
         return {"error": f"Cannot access or send messages to channel {channel_id}."}
    except Exception as e: # Catch scheduler errors too
        error_message = f"Error scheduling message: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}


# Tool 6: delete_message
async def delete_message(cog: commands.Cog, message_id: str, channel_id: Optional[str] = None) -> Dict[str, Any]:
    """Deletes a specific message by its ID."""
    print(f"Executing delete_message tool for message ID: {message_id}.")
    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found."}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context."}
        if not isinstance(channel, discord.abc.Messageable):
             return {"error": f"Channel {getattr(channel, 'id', 'N/A')} is not messageable."}

        message_id_int = int(message_id)
        message = await channel.fetch_message(message_id_int)

        # Permission Check (if in guild)
        if isinstance(channel, discord.abc.GuildChannel):
            bot_member = channel.guild.me
            # Need 'manage_messages' to delete others' messages, can always delete own
            if message.author != bot_member and not channel.permissions_for(bot_member).manage_messages:
                return {"error": "Missing 'Manage Messages' permission to delete this message."}

        await message.delete()
        print(f"Successfully deleted message {message_id} in channel {channel.id}.")
        return {"status": "success", "message_id": message_id, "channel_id": str(channel.id)}

    except ValueError:
        return {"error": f"Invalid message_id or channel_id format."}
    except discord.NotFound:
        return {"error": f"Message {message_id} not found in channel {channel_id or getattr(channel, 'id', 'N/A')}."}
    except discord.Forbidden:
        return {"error": f"Forbidden: Missing permissions to delete message {message_id}."}
    except discord.HTTPException as e:
        error_message = f"API error deleting message {message_id}: {e}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:
        error_message = f"Unexpected error deleting message {message_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 7: edit_message
async def edit_message(cog: commands.Cog, message_id: str, new_content: str, channel_id: Optional[str] = None) -> Dict[str, Any]:
    """Edits a message sent by the bot."""
    print(f"Executing edit_message tool for message ID: {message_id}.")
    if not new_content: return {"error": "New content cannot be empty."}
    # Limit message length
    max_msg_len = 1900
    new_content = new_content[:max_msg_len] + ('...' if len(new_content) > max_msg_len else '')

    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found."}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context."}
        if not isinstance(channel, discord.abc.Messageable):
             return {"error": f"Channel {getattr(channel, 'id', 'N/A')} is not messageable."}

        message_id_int = int(message_id)
        message = await channel.fetch_message(message_id_int)

        # IMPORTANT: Bots can ONLY edit their own messages.
        if message.author != cog.bot.user:
            return {"error": "Cannot edit messages sent by other users."}

        await message.edit(content=new_content)
        print(f"Successfully edited message {message_id} in channel {channel.id}.")
        return {"status": "success", "message_id": message_id, "channel_id": str(channel.id), "new_content_preview": new_content[:100]}

    except ValueError:
        return {"error": f"Invalid message_id or channel_id format."}
    except discord.NotFound:
        return {"error": f"Message {message_id} not found in channel {channel_id or getattr(channel, 'id', 'N/A')}."}
    except discord.Forbidden:
        # This usually shouldn't happen if we check author == bot, but include for safety
        return {"error": f"Forbidden: Missing permissions to edit message {message_id} (shouldn't happen for own message)."}
    except discord.HTTPException as e:
        error_message = f"API error editing message {message_id}: {e}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:
        error_message = f"Unexpected error editing message {message_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 8: get_voice_channel_info
async def get_voice_channel_info(cog: commands.Cog, channel_id: str) -> Dict[str, Any]:
    """Gets information about a specific voice channel."""
    print(f"Executing get_voice_channel_info tool for channel ID: {channel_id}.")
    try:
        channel_id_int = int(channel_id)
        channel = cog.bot.get_channel(channel_id_int)

        if not channel:
            return {"error": f"Channel {channel_id} not found."}
        if not isinstance(channel, discord.VoiceChannel):
            return {"error": f"Channel {channel_id} is not a voice channel (Type: {type(channel)})."}

        members_info = []
        for member in channel.members:
            members_info.append({
                "id": str(member.id),
                "name": member.name,
                "display_name": member.display_name,
                "voice_state": {
                    "deaf": member.voice.deaf, "mute": member.voice.mute,
                    "self_deaf": member.voice.self_deaf, "self_mute": member.voice.self_mute,
                    "self_stream": member.voice.self_stream, "self_video": member.voice.self_video,
                    "suppress": member.voice.suppress, "afk": member.voice.afk
                } if member.voice else None
            })

        return {
            "status": "success",
            "channel_id": str(channel.id),
            "name": channel.name,
            "bitrate": channel.bitrate,
            "user_limit": channel.user_limit,
            "rtc_region": str(channel.rtc_region) if channel.rtc_region else None,
            "category": {"id": str(channel.category_id), "name": channel.category.name} if channel.category else None,
            "guild_id": str(channel.guild.id),
            "connected_members": members_info,
            "member_count": len(members_info),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except ValueError:
        return {"error": f"Invalid channel ID format: {channel_id}."}
    except Exception as e:
        error_message = f"Error getting voice channel info: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 9: move_user_to_voice_channel
async def move_user_to_voice_channel(cog: commands.Cog, user_id: str, target_channel_id: str) -> Dict[str, Any]:
    """Moves a user to a specified voice channel within the same server."""
    print(f"Executing move_user_to_voice_channel tool: User={user_id}, TargetChannel={target_channel_id}.")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot move users outside of a server context."}
    guild = cog.current_channel.guild
    if not guild: return {"error": "Could not determine server."}

    try:
        user_id_int = int(user_id)
        target_channel_id_int = int(target_channel_id)

        member = guild.get_member(user_id_int) or await guild.fetch_member(user_id_int)
        if not member: return {"error": f"User {user_id} not found in this server."}

        target_channel = guild.get_channel(target_channel_id_int)
        if not target_channel: return {"error": f"Target voice channel {target_channel_id} not found."}
        if not isinstance(target_channel, discord.VoiceChannel):
            return {"error": f"Target channel {target_channel_id} is not a voice channel."}

        # Permission Checks
        bot_member = guild.me
        if not bot_member.guild_permissions.move_members:
            return {"error": "I lack the 'Move Members' permission."}
        # Check bot permissions in both origin (if user is connected) and target channels
        if member.voice and member.voice.channel:
            origin_channel = member.voice.channel
            if not origin_channel.permissions_for(bot_member).connect or not origin_channel.permissions_for(bot_member).move_members:
                 return {"error": f"I lack Connect/Move permissions in the user's current channel ({origin_channel.name})."}
        if not target_channel.permissions_for(bot_member).connect or not target_channel.permissions_for(bot_member).move_members:
             return {"error": f"I lack Connect/Move permissions in the target channel ({target_channel.name})."}
        # Cannot move user if bot's top role is not higher (unless bot is owner)
        if bot_member.id != guild.owner_id and bot_member.top_role <= member.top_role:
             return {"error": f"Cannot move {member.display_name} due to role hierarchy."}

        await member.move_to(target_channel, reason="Moved by Gurt tool")
        print(f"Successfully moved {member.display_name} ({user_id}) to voice channel {target_channel.name} ({target_channel_id}).")
        return {
            "status": "success",
            "user_id": user_id,
            "user_name": member.display_name,
            "target_channel_id": target_channel_id,
            "target_channel_name": target_channel.name
        }

    except ValueError:
        return {"error": "Invalid user_id or target_channel_id format."}
    except discord.NotFound:
        return {"error": "User or target channel not found."}
    except discord.Forbidden as e:
        print(f"Forbidden error moving user {user_id}: {e}")
        return {"error": f"Permission error moving user {user_id}."}
    except discord.HTTPException as e:
        print(f"API error moving user {user_id}: {e}")
        return {"error": f"API error moving user {user_id}: {e}"}
    except Exception as e:
        error_message = f"Unexpected error moving user {user_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 10: get_guild_roles
async def get_guild_roles(cog: commands.Cog) -> Dict[str, Any]:
    """Lists all roles in the current server."""
    print("Executing get_guild_roles tool.")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot get roles outside of a server channel."}
    guild = cog.current_channel.guild
    if not guild:
        return {"error": "Could not determine the current server."}

    try:
        roles_list = []
        # Roles are ordered by position, highest first (excluding @everyone)
        for role in reversed(guild.roles): # Iterate from lowest to highest position
            if role.name == "@everyone": continue
            roles_list.append({
                "id": str(role.id),
                "name": role.name,
                "color": str(role.color),
                "position": role.position,
                "is_mentionable": role.mentionable,
                "member_count": len(role.members) # Can be slow on large servers
            })

        return {
            "status": "success",
            "guild_id": str(guild.id),
            "roles": roles_list,
            "count": len(roles_list),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error listing guild roles: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}


# Tool 11: assign_role_to_user
async def assign_role_to_user(cog: commands.Cog, user_id: str, role_id: str) -> Dict[str, Any]:
    """Assigns a specific role to a user."""
    print(f"Executing assign_role_to_user tool: User={user_id}, Role={role_id}.")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot manage roles outside of a server context."}
    guild = cog.current_channel.guild
    if not guild: return {"error": "Could not determine server."}

    try:
        user_id_int = int(user_id)
        role_id_int = int(role_id)

        member = guild.get_member(user_id_int) or await guild.fetch_member(user_id_int)
        if not member: return {"error": f"User {user_id} not found in this server."}

        role = guild.get_role(role_id_int)
        if not role: return {"error": f"Role {role_id} not found in this server."}
        if role.name == "@everyone": return {"error": "Cannot assign the @everyone role."}

        # Permission Checks
        bot_member = guild.me
        if not bot_member.guild_permissions.manage_roles:
            return {"error": "I lack the 'Manage Roles' permission."}
        # Check role hierarchy: Bot's top role must be higher than the role being assigned
        if bot_member.id != guild.owner_id and bot_member.top_role <= role:
             return {"error": f"Cannot assign role '{role.name}' because my highest role is not above it."}
        # Check if user already has the role
        if role in member.roles:
            return {"status": "already_has_role", "user_id": user_id, "role_id": role_id, "role_name": role.name}

        await member.add_roles(role, reason="Assigned by Gurt tool")
        print(f"Successfully assigned role '{role.name}' ({role_id}) to {member.display_name} ({user_id}).")
        return {
            "status": "success",
            "user_id": user_id,
            "user_name": member.display_name,
            "role_id": role_id,
            "role_name": role.name
        }

    except ValueError:
        return {"error": "Invalid user_id or role_id format."}
    except discord.NotFound:
        return {"error": "User or role not found."}
    except discord.Forbidden as e:
        print(f"Forbidden error assigning role {role_id} to {user_id}: {e}")
        return {"error": f"Permission error assigning role: {e}"}
    except discord.HTTPException as e:
        print(f"API error assigning role {role_id} to {user_id}: {e}")
        return {"error": f"API error assigning role: {e}"}
    except Exception as e:
        error_message = f"Unexpected error assigning role {role_id} to {user_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 12: remove_role_from_user
async def remove_role_from_user(cog: commands.Cog, user_id: str, role_id: str) -> Dict[str, Any]:
    """Removes a specific role from a user."""
    print(f"Executing remove_role_from_user tool: User={user_id}, Role={role_id}.")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot manage roles outside of a server context."}
    guild = cog.current_channel.guild
    if not guild: return {"error": "Could not determine server."}

    try:
        user_id_int = int(user_id)
        role_id_int = int(role_id)

        member = guild.get_member(user_id_int) or await guild.fetch_member(user_id_int)
        if not member: return {"error": f"User {user_id} not found in this server."}

        role = guild.get_role(role_id_int)
        if not role: return {"error": f"Role {role_id} not found in this server."}
        if role.name == "@everyone": return {"error": "Cannot remove the @everyone role."}

        # Permission Checks
        bot_member = guild.me
        if not bot_member.guild_permissions.manage_roles:
            return {"error": "I lack the 'Manage Roles' permission."}
        # Check role hierarchy: Bot's top role must be higher than the role being removed
        if bot_member.id != guild.owner_id and bot_member.top_role <= role:
             return {"error": f"Cannot remove role '{role.name}' because my highest role is not above it."}
        # Check if user actually has the role
        if role not in member.roles:
            return {"status": "does_not_have_role", "user_id": user_id, "role_id": role_id, "role_name": role.name}

        await member.remove_roles(role, reason="Removed by Gurt tool")
        print(f"Successfully removed role '{role.name}' ({role_id}) from {member.display_name} ({user_id}).")
        return {
            "status": "success",
            "user_id": user_id,
            "user_name": member.display_name,
            "role_id": role_id,
            "role_name": role.name
        }

    except ValueError:
        return {"error": "Invalid user_id or role_id format."}
    except discord.NotFound:
        return {"error": "User or role not found."}
    except discord.Forbidden as e:
        print(f"Forbidden error removing role {role_id} from {user_id}: {e}")
        return {"error": f"Permission error removing role: {e}"}
    except discord.HTTPException as e:
        print(f"API error removing role {role_id} from {user_id}: {e}")
        return {"error": f"API error removing role: {e}"}
    except Exception as e:
        error_message = f"Unexpected error removing role {role_id} from {user_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 13: fetch_emoji_list
async def fetch_emoji_list(cog: commands.Cog) -> Dict[str, Any]:
    """Lists all custom emojis available in the current server."""
    print("Executing fetch_emoji_list tool.")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot fetch emojis outside of a server context."}
    guild = cog.current_channel.guild
    if not guild: return {"error": "Could not determine server."}

    try:
        emojis_list = []
        for emoji in guild.emojis:
            emojis_list.append({
                "id": str(emoji.id),
                "name": emoji.name,
                "url": str(emoji.url),
                "is_animated": emoji.animated,
                "is_managed": emoji.managed, # e.g., Twitch integration emojis
                "available": emoji.available, # If the bot can use it
                "created_at": emoji.created_at.isoformat() if emoji.created_at else None
            })

        return {
            "status": "success",
            "guild_id": str(guild.id),
            "emojis": emojis_list,
            "count": len(emojis_list),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error fetching emoji list: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 14: get_guild_invites
async def get_guild_invites(cog: commands.Cog) -> Dict[str, Any]:
    """Lists active invite links for the current server. Requires 'Manage Server' permission."""
    print("Executing get_guild_invites tool.")
    if not cog.current_channel or not isinstance(cog.current_channel, discord.abc.GuildChannel):
        return {"error": "Cannot get invites outside of a server context."}
    guild = cog.current_channel.guild
    if not guild: return {"error": "Could not determine server."}

    # Permission Check
    bot_member = guild.me
    if not bot_member.guild_permissions.manage_guild:
        return {"error": "I lack the 'Manage Server' permission required to view invites."}

    try:
        invites = await guild.invites()
        invites_list = []
        for invite in invites:
            inviter_info = {"id": str(invite.inviter.id), "name": invite.inviter.name} if invite.inviter else None
            channel_info = {"id": str(invite.channel.id), "name": invite.channel.name} if invite.channel else None
            invites_list.append({
                "code": invite.code,
                "url": invite.url,
                "inviter": inviter_info,
                "channel": channel_info,
                "uses": invite.uses,
                "max_uses": invite.max_uses,
                "max_age": invite.max_age, # In seconds, 0 means infinite
                "is_temporary": invite.temporary,
                "created_at": invite.created_at.isoformat() if invite.created_at else None,
                "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
            })

        return {
            "status": "success",
            "guild_id": str(guild.id),
            "invites": invites_list,
            "count": len(invites_list),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except discord.Forbidden:
        # Should be caught by initial check, but good practice
        return {"error": "Forbidden: Missing 'Manage Server' permission."}
    except discord.HTTPException as e:
        print(f"API error getting invites: {e}")
        return {"error": f"API error getting invites: {e}"}
    except Exception as e:
        error_message = f"Unexpected error getting invites: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 15: purge_messages
async def purge_messages(cog: commands.Cog, limit: int, channel_id: Optional[str] = None, user_id: Optional[str] = None, before_message_id: Optional[str] = None, after_message_id: Optional[str] = None) -> Dict[str, Any]:
    """Bulk deletes messages in a channel. Requires 'Manage Messages' permission."""
    print(f"Executing purge_messages tool: Limit={limit}, Channel={channel_id}, User={user_id}, Before={before_message_id}, After={after_message_id}.")
    if not 1 <= limit <= 1000: # Discord's practical limit is often lower, but API allows up to 100 per call
        return {"error": "Limit must be between 1 and 1000."}

    try:
        if channel_id:
            channel = cog.bot.get_channel(int(channel_id))
            if not channel: return {"error": f"Channel {channel_id} not found."}
        else:
            channel = cog.current_channel
            if not channel: return {"error": "No current channel context."}
        if not isinstance(channel, discord.TextChannel): # Purge usually only for text channels
             return {"error": f"Channel {getattr(channel, 'id', 'N/A')} must be a text channel."}

        # Permission Check
        bot_member = channel.guild.me
        if not channel.permissions_for(bot_member).manage_messages:
            return {"error": "I lack the 'Manage Messages' permission required to purge."}

        target_user = None
        if user_id:
            target_user = await cog.bot.fetch_user(int(user_id)) # Fetch user object if ID provided
            if not target_user: return {"error": f"User {user_id} not found."}

        before_obj = discord.Object(id=int(before_message_id)) if before_message_id else None
        after_obj = discord.Object(id=int(after_message_id)) if after_message_id else None

        check_func = (lambda m: m.author == target_user) if target_user else None

        # discord.py handles bulk deletion in batches of 100 automatically
        deleted_messages = await channel.purge(
            limit=limit,
            check=check_func,
            before=before_obj,
            after=after_obj,
            reason="Purged by Gurt tool"
        )

        deleted_count = len(deleted_messages)
        print(f"Successfully purged {deleted_count} messages from channel {channel.id}.")
        return {
            "status": "success",
            "channel_id": str(channel.id),
            "deleted_count": deleted_count,
            "limit_requested": limit,
            "filters_applied": {"user_id": user_id, "before": before_message_id, "after": after_message_id},
            "timestamp": datetime.datetime.now().isoformat()
        }

    except ValueError:
        return {"error": "Invalid ID format for channel, user, before, or after message."}
    except discord.NotFound:
        return {"error": "Channel, user, before, or after message not found."}
    except discord.Forbidden:
        return {"error": "Forbidden: Missing 'Manage Messages' permission."}
    except discord.HTTPException as e:
        print(f"API error purging messages: {e}")
        # Provide more specific feedback if possible (e.g., messages too old)
        if "too old" in str(e).lower():
             return {"error": "API error: Cannot bulk delete messages older than 14 days."}
        return {"error": f"API error purging messages: {e}"}
    except Exception as e:
        error_message = f"Unexpected error purging messages: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}


# Tool 16: get_bot_stats
async def get_bot_stats(cog: commands.Cog) -> Dict[str, Any]:
    """Gets various statistics about the bot's current state."""
    print("Executing get_bot_stats tool.")
    # This requires access to bot-level stats, potentially stored in the main bot class or cog
    try:
        # Example stats (replace with actual data sources)
        guild_count = len(cog.bot.guilds)
        user_count = len(cog.bot.users) # Might not be accurate without intents
        total_users = sum(g.member_count for g in cog.bot.guilds if g.member_count) # Requires member intent
        latency_ms = round(cog.bot.latency * 1000)
        # Command usage would need tracking within the cog/bot
        command_count = cog.command_usage_count if hasattr(cog, 'command_usage_count') else "N/A"
        # Memory usage (platform specific, using psutil is common)
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except ImportError:
            memory_mb = "N/A (psutil not installed)"
        except Exception as mem_e:
            memory_mb = f"Error ({mem_e})"

        uptime_dict = await get_bot_uptime(cog) # Reuse uptime tool

        return {
            "status": "success",
            "guild_count": guild_count,
            "cached_user_count": user_count,
            "total_member_count_approx": total_users, # Note intent requirement
            "latency_ms": latency_ms,
            "command_usage_count": command_count,
            "memory_usage_mb": memory_mb,
            "uptime_info": uptime_dict, # Include uptime details
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "discord_py_version": discord.__version__,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error getting bot stats: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

# Tool 17: get_weather (Placeholder - Requires Weather API)
async def get_weather(cog: commands.Cog, location: str) -> Dict[str, Any]:
    """Gets the current weather for a specified location (requires external API setup)."""
    print(f"Executing get_weather tool for location: {location}.")
    # --- Placeholder Implementation ---
    # A real implementation would use a weather API (e.g., OpenWeatherMap, WeatherAPI)
    # It would require an API key stored in config and use aiohttp to make the request.
    # Example using a hypothetical API call:
    # weather_api_key = os.getenv("WEATHER_API_KEY")
    # if not weather_api_key: return {"error": "Weather API key not configured."}
    # if not cog.session: return {"error": "aiohttp session not available."}
    # api_url = f"https://api.some_weather_service.com/current?q={location}&appid={weather_api_key}&units=metric"
    # try:
    #     async with cog.session.get(api_url) as response:
    #         if response.status == 200:
    #             data = await response.json()
    #             # Parse data and return relevant info
    #             temp = data.get('main', {}).get('temp')
    #             desc = data.get('weather', [{}])[0].get('description')
    #             city = data.get('name')
    #             return {"status": "success", "location": city, "temperature_celsius": temp, "description": desc}
    #         else:
    #             return {"error": f"Weather API error (Status {response.status}): {await response.text()}"}
    # except Exception as e: return {"error": f"Error fetching weather: {e}"}
    # --- End Placeholder ---

    return {
        "status": "placeholder",
        "error": "Weather tool not fully implemented. Requires external API integration.",
        "location_requested": location,
        "timestamp": datetime.datetime.now().isoformat()
    }

# Tool 18: translate_text (Placeholder - Requires Translation API)
async def translate_text(cog: commands.Cog, text: str, target_language: str, source_language: Optional[str] = None) -> Dict[str, Any]:
    """Translates text to a target language (requires external API setup)."""
    print(f"Executing translate_text tool: Target={target_language}, Source={source_language}, Text='{text[:50]}...'")
    # --- Placeholder Implementation ---
    # A real implementation would use a translation API (e.g., Google Translate API, DeepL)
    # It would require API keys/credentials and use a suitable library or aiohttp.
    # Example using a hypothetical API call:
    # translate_api_key = os.getenv("TRANSLATE_API_KEY")
    # if not translate_api_key: return {"error": "Translation API key not configured."}
    # if not cog.session: return {"error": "aiohttp session not available."}
    # api_url = "https://api.some_translate_service.com/translate"
    # payload = {"text": text, "target": target_language}
    # if source_language: payload["source"] = source_language
    # headers = {"Authorization": f"Bearer {translate_api_key}"}
    # try:
    #     async with cog.session.post(api_url, json=payload, headers=headers) as response:
    #         if response.status == 200:
    #             data = await response.json()
    #             translated = data.get('translations', [{}])[0].get('text')
    #             detected_source = data.get('translations', [{}])[0].get('detected_source_language')
    #             return {"status": "success", "original_text": text, "translated_text": translated, "target_language": target_language, "detected_source_language": detected_source}
    #         else:
    #             return {"error": f"Translation API error (Status {response.status}): {await response.text()}"}
    # except Exception as e: return {"error": f"Error translating text: {e}"}
    # --- End Placeholder ---

    return {
        "status": "placeholder",
        "error": "Translation tool not fully implemented. Requires external API integration.",
        "text_preview": text[:100],
        "target_language": target_language,
        "timestamp": datetime.datetime.now().isoformat()
    }

# Tool 19: remind_user (Placeholder - Requires Scheduler/DB)
async def remind_user(cog: commands.Cog, user_id: str, reminder_text: str, remind_at_iso: str) -> Dict[str, Any]:
    """Sets a reminder for a user to be delivered via DM at a specific time."""
    print(f"Executing remind_user tool: User={user_id}, Time={remind_at_iso}, Reminder='{reminder_text[:50]}...'")
    # --- Placeholder Implementation ---
    # This requires a persistent scheduler (like APScheduler) and likely a way to store reminders
    # in case the bot restarts. It also needs to fetch the user and send a DM.
    # if not hasattr(cog, 'scheduler') or not cog.scheduler:
    #      return {"error": "Scheduler not available. Cannot set reminders."}
    # try:
    #     remind_time = datetime.datetime.fromisoformat(remind_at_iso)
    #     if remind_time.tzinfo is None: return {"error": "remind_at_iso must include timezone."}
    #     now = datetime.datetime.now(datetime.timezone.utc)
    #     if remind_time <= now: return {"error": "Reminder time must be in the future."}
    #
    #     user = await cog.bot.fetch_user(int(user_id))
    #     if not user: return {"error": f"User {user_id} not found."}
    #
    #     # Define the function to be called by the scheduler
    #     async def send_reminder_dm(target_user_id, text):
    #         try:
    #             user_to_dm = await cog.bot.fetch_user(target_user_id)
    #             await user_to_dm.send(f"⏰ Reminder: {text}")
    #             print(f"Sent reminder DM to {user_to_dm.name} ({target_user_id})")
    #         except Exception as dm_e:
    #             print(f"Failed to send reminder DM to {target_user_id}: {dm_e}")
    #
    #     job = cog.scheduler.add_job(
    #         send_reminder_dm,
    #         'date',
    #         run_date=remind_time,
    #         args=[user.id, reminder_text],
    #         id=f"reminder_{user.id}_{int(time.time())}",
    #         misfire_grace_time=600
    #     )
    #     print(f"Scheduled reminder job {job.id} for user {user.id} at {remind_time.isoformat()}")
    #     return {"status": "success", "job_id": job.id, "user_id": user_id, "reminder_text": reminder_text, "remind_time_utc": remind_time.astimezone(datetime.timezone.utc).isoformat()}
    # except ValueError: return {"error": "Invalid user_id or remind_at_iso format."}
    # except discord.NotFound: return {"error": f"User {user_id} not found."}
    # except Exception as e: return {"error": f"Error setting reminder: {e}"}
    # --- End Placeholder ---

    return {
        "status": "placeholder",
        "error": "Reminder tool not fully implemented. Requires scheduler and DM functionality.",
        "user_id": user_id,
        "reminder_text_preview": reminder_text[:100],
        "remind_at_iso": remind_at_iso,
        "timestamp": datetime.datetime.now().isoformat()
    }

# Tool 20: fetch_random_image (Placeholder - Requires Image API/Source)
async def fetch_random_image(cog: commands.Cog, query: Optional[str] = None) -> Dict[str, Any]:
    """Fetches a random image, optionally based on a query (requires external API setup)."""
    print(f"Executing fetch_random_image tool: Query='{query}'")
    # --- Placeholder Implementation ---
    # A real implementation could use APIs like Unsplash, Giphy (for GIFs), Reddit (PRAW), etc.
    # Example using a hypothetical Unsplash call:
    # unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    # if not unsplash_key: return {"error": "Unsplash API key not configured."}
    # if not cog.session: return {"error": "aiohttp session not available."}
    # api_url = f"https://api.unsplash.com/photos/random?client_id={unsplash_key}"
    # if query: api_url += f"&query={query}"
    # try:
    #     async with cog.session.get(api_url) as response:
    #         if response.status == 200:
    #             data = await response.json()
    #             image_url = data.get('urls', {}).get('regular')
    #             alt_desc = data.get('alt_description')
    #             photographer = data.get('user', {}).get('name')
    #             if image_url:
    #                 return {"status": "success", "image_url": image_url, "description": alt_desc, "photographer": photographer, "source": "Unsplash"}
    #             else:
    #                 return {"error": "Failed to extract image URL from Unsplash response."}
    #         else:
    #             return {"error": f"Image API error (Status {response.status}): {await response.text()}"}
    # except Exception as e: return {"error": f"Error fetching random image: {e}"}
    # --- End Placeholder ---

    return {
        "status": "placeholder",
        "error": "Random image tool not fully implemented. Requires external API integration.",
        "query": query,
        "timestamp": datetime.datetime.now().isoformat()
    }


# --- Random System/Meme Tools ---

async def read_temps(cog: commands.Cog) -> Dict[str, Any]:
    """Reads the system temperatures using the 'sensors' command (Linux/Unix)."""
    import platform
    import subprocess
    import asyncio # Ensure asyncio is imported

    try:
        if platform.system() == "Windows":
            # Windows doesn't have 'sensors' command typically
            return {
                "status": "not_supported",
                "output": None,
                "error": "The 'sensors' command is typically not available on Windows."
            }
        else:
            # Try to run the 'sensors' command
            try:
                proc = await asyncio.create_subprocess_shell(
                    "sensors",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=10) # Add timeout
                stdout = stdout_bytes.decode(errors="replace").strip()
                stderr = stderr_bytes.decode(errors="replace").strip()

                if proc.returncode == 0:
                    # Command succeeded, return the full stdout
                    max_len = 1800 # Limit output length slightly
                    stdout_trunc = stdout[:max_len] + ('...' if len(stdout) > max_len else '')
                    return {
                        "status": "success",
                        "output": stdout_trunc, # Return truncated stdout
                        "error": None
                    }
                else:
                    # Command failed
                    error_msg = f"'sensors' command failed with exit code {proc.returncode}."
                    if stderr:
                        error_msg += f" Stderr: {stderr[:200]}" # Include some stderr
                    print(f"read_temps error: {error_msg}")
                    return {
                        "status": "execution_error",
                        "output": None,
                        "error": error_msg
                    }
            except FileNotFoundError:
                 print("read_temps error: 'sensors' command not found.")
                 return {
                    "status": "error",
                    "output": None,
                    "error": "'sensors' command not found. Is lm-sensors installed and in PATH?"
                 }
            except asyncio.TimeoutError:
                print("read_temps error: 'sensors' command timed out.")
                return {
                    "status": "timeout",
                    "output": None,
                    "error": "'sensors' command timed out after 10 seconds."
                }
            except Exception as cmd_e:
                # Catch other potential errors during subprocess execution
                error_msg = f"Error running 'sensors' command: {str(cmd_e)}"
                print(f"read_temps error: {error_msg}")
                traceback.print_exc()
                return {
                    "status": "error",
                    "output": None,
                    "error": error_msg
                }
    except Exception as e:
        # Catch unexpected errors in the function itself
        error_msg = f"Unexpected error in read_temps: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return {"status": "error", "output": None, "error": error_msg}

async def check_disk_space(cog: commands.Cog) -> Dict[str, Any]:
    """Checks disk space on the main drive."""
    import shutil
    try:
        total, used, free = shutil.disk_usage("/")
        gb = 1024 ** 3
        percent = round(used / total * 100, 1)
        return {
            "status": "success",
            "total_gb": round(total / gb, 2),
            "used_gb": round(used / gb, 2),
            "free_gb": round(free / gb, 2),
            "percent_used": percent,
            "msg": None
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def fetch_random_joke(cog: commands.Cog) -> Dict[str, Any]:
    """Fetches a random joke from an API."""
    url = "https://official-joke-api.appspot.com/random_joke"
    try:
        if not cog.session:
            return {"status": "error", "error": "aiohttp session not initialized"}
        async with cog.session.get(url, timeout=8) as resp:
            if resp.status == 200:
                data = await resp.json()
                setup = data.get("setup", "")
                punchline = data.get("punchline", "")
                return {
                    "status": "success",
                    "joke": f"{setup} ... {punchline}"
                }
            else:
                return {"status": "error", "error": f"API returned {resp.status}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# --- New Tools: Guild/Channel Listing ---

async def list_bot_guilds(cog: commands.Cog) -> Dict[str, Any]:
    """Lists all guilds (servers) the bot is currently connected to."""
    print("Executing list_bot_guilds tool.")
    try:
        guilds_list = [{"id": str(guild.id), "name": guild.name} for guild in cog.bot.guilds]
        return {
            "status": "success",
            "guilds": guilds_list,
            "count": len(guilds_list),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error listing bot guilds: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

async def list_guild_channels(cog: commands.Cog, guild_id: str) -> Dict[str, Any]:
    """Lists all channels (text, voice, category, etc.) in a specified guild."""
    print(f"Executing list_guild_channels tool for guild ID: {guild_id}.")
    try:
        guild_id_int = int(guild_id)
        guild = cog.bot.get_guild(guild_id_int)
        if not guild:
            return {"error": f"Guild with ID {guild_id} not found or bot is not in it."}

        channels_list = []
        for channel in guild.channels:
            channels_list.append({
                "id": str(channel.id),
                "name": channel.name,
                "type": str(channel.type),
                "position": channel.position,
                "category_id": str(channel.category_id) if channel.category_id else None
            })
        # Sort by position for better readability
        channels_list.sort(key=lambda x: x.get('position', 0))

        return {
            "status": "success",
            "guild_id": guild_id,
            "guild_name": guild.name,
            "channels": channels_list,
            "count": len(channels_list),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except ValueError:
        return {"error": f"Invalid guild ID format: {guild_id}."}
    except Exception as e:
        error_message = f"Error listing channels for guild {guild_id}: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}

async def list_tools(cog: commands.Cog) -> Dict[str, Any]:
    """Lists all available tools with their names and descriptions."""
    print("Executing list_tools tool.")
    try:
        # TOOLS is imported from .config
        tool_list = [{"name": tool.name, "description": tool.description} for tool in TOOLS]
        return {
            "status": "success",
            "tools": tool_list,
            "count": len(tool_list),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        error_message = f"Error listing tools: {str(e)}"
        print(error_message); traceback.print_exc()
        return {"error": error_message}


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
    "no_operation": no_operation, # Added no-op tool
    "restart_gurt_bot": restart_gurt_bot, # Tool to restart the Gurt bot
    "run_git_pull": run_git_pull, # Tool to run git pull on the host
    "get_channel_id": get_channel_id, # Tool to get channel id
    # --- Batch 1 Additions ---
    "get_guild_info": get_guild_info,
    "list_guild_members": list_guild_members,
    "get_user_avatar": get_user_avatar,
    "get_bot_uptime": get_bot_uptime,
    "schedule_message": schedule_message,
    # --- End Batch 1 ---
    # --- Batch 2 Additions ---
    "delete_message": delete_message,
    "edit_message": edit_message,
    "get_voice_channel_info": get_voice_channel_info,
    "move_user_to_voice_channel": move_user_to_voice_channel,
    "get_guild_roles": get_guild_roles,
    # --- End Batch 2 ---
    # --- Batch 3 Additions ---
    "assign_role_to_user": assign_role_to_user,
    "remove_role_from_user": remove_role_from_user,
    "fetch_emoji_list": fetch_emoji_list,
    "get_guild_invites": get_guild_invites,
    "purge_messages": purge_messages,
    # --- End Batch 3 ---
    # --- Batch 4 Additions ---
    "get_bot_stats": get_bot_stats,
    "get_weather": get_weather,
    "translate_text": translate_text,
    "remind_user": remind_user,
    "fetch_random_image": fetch_random_image,
    # --- End Batch 4 ---
    # --- Random System/Meme Tools ---
    "read_temps": read_temps,
    "check_disk_space": check_disk_space,
    "fetch_random_joke": fetch_random_joke,
    # --- Guild/Channel Listing Tools ---
    "list_bot_guilds": list_bot_guilds,
    "list_guild_channels": list_guild_channels,
    # --- Tool Listing Tool ---
    "list_tools": list_tools,
    # --- User Profile Tools ---
    "get_user_username": get_user_username,
    "get_user_display_name": get_user_display_name,
    "get_user_avatar_url": get_user_avatar_url,
    "get_user_status": get_user_status,
    "get_user_activity": get_user_activity,
    "get_user_roles": get_user_roles,
    "get_user_profile_info": get_user_profile_info,
    # --- End User Profile Tools ---
}

# --- User Profile Tools ---

async def _get_user_or_member(cog: commands.Cog, user_id_str: str) -> Tuple[Optional[Union[discord.User, discord.Member]], Optional[Dict[str, Any]]]:
    """Helper to fetch a User or Member object, handling errors."""
    try:
        user_id = int(user_id_str)
        user_or_member = cog.bot.get_user(user_id)

        # If in a guild context, try to get the Member object for more info (status, roles, etc.)
        if not user_or_member and cog.current_channel and isinstance(cog.current_channel, discord.abc.GuildChannel):
            guild = cog.current_channel.guild
            if guild:
                print(f"Attempting to fetch member {user_id} from guild {guild.id}")
                try:
                    user_or_member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                except discord.NotFound:
                    print(f"Member {user_id} not found in guild {guild.id}. Falling back to fetch_user.")
                    # Fallback to fetching user if not found as member
                    try: user_or_member = await cog.bot.fetch_user(user_id)
                    except discord.NotFound: pass # Handled below
                except discord.Forbidden:
                     print(f"Forbidden to fetch member {user_id} from guild {guild.id}. Falling back to fetch_user.")
                     try: user_or_member = await cog.bot.fetch_user(user_id)
                     except discord.NotFound: pass # Handled below

        # If still not found, try fetching globally
        if not user_or_member:
            print(f"User/Member {user_id} not in cache or guild, attempting global fetch_user.")
            try:
                user_or_member = await cog.bot.fetch_user(user_id)
            except discord.NotFound:
                print(f"User {user_id} not found globally.")
                return None, {"error": f"User with ID {user_id_str} not found."}
            except discord.HTTPException as e:
                print(f"HTTP error fetching user {user_id}: {e}")
                return None, {"error": f"API error fetching user {user_id_str}: {e}"}

        if not user_or_member: # Should be caught by NotFound above, but double-check
             return None, {"error": f"User with ID {user_id_str} could not be retrieved."}

        return user_or_member, None # Return the user/member object and no error
    except ValueError:
        return None, {"error": f"Invalid user ID format: {user_id_str}."}
    except Exception as e:
        error_message = f"Unexpected error fetching user/member {user_id_str}: {str(e)}"
        print(error_message); traceback.print_exc()
        return None, {"error": error_message}


async def get_user_username(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets the unique Discord username (e.g., username#1234) for a given user ID."""
    print(f"Executing get_user_username for user ID: {user_id}.")
    user_obj, error_resp = await _get_user_or_member(cog, user_id)
    if error_resp: return error_resp
    if not user_obj: return {"error": f"Failed to retrieve user object for ID {user_id}."} # Should not happen if error_resp is None

    return {
        "status": "success",
        "user_id": user_id,
        "username": str(user_obj), # User.__str__() gives username#discriminator
        "timestamp": datetime.datetime.now().isoformat()
    }

async def get_user_display_name(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets the display name for a given user ID (server nickname if in a guild, otherwise global name)."""
    print(f"Executing get_user_display_name for user ID: {user_id}.")
    user_obj, error_resp = await _get_user_or_member(cog, user_id)
    if error_resp: return error_resp
    if not user_obj: return {"error": f"Failed to retrieve user object for ID {user_id}."}

    # user_obj could be User or Member. display_name works for both.
    display_name = user_obj.display_name

    return {
        "status": "success",
        "user_id": user_id,
        "display_name": display_name,
        "timestamp": datetime.datetime.now().isoformat()
    }

async def get_user_avatar_url(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets the URL of the user's current avatar (server-specific if available, otherwise global)."""
    print(f"Executing get_user_avatar_url for user ID: {user_id}.")
    user_obj, error_resp = await _get_user_or_member(cog, user_id)
    if error_resp: return error_resp
    if not user_obj: return {"error": f"Failed to retrieve user object for ID {user_id}."}

    # .display_avatar handles server vs global avatar automatically
    avatar_url = str(user_obj.display_avatar.url)

    return {
        "status": "success",
        "user_id": user_id,
        "avatar_url": avatar_url,
        "timestamp": datetime.datetime.now().isoformat()
    }

async def get_user_status(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets the current status (online, idle, dnd, offline) of a user. Requires guild context."""
    print(f"Executing get_user_status for user ID: {user_id}.")
    user_obj, error_resp = await _get_user_or_member(cog, user_id)
    if error_resp: return error_resp
    if not user_obj: return {"error": f"Failed to retrieve user object for ID {user_id}."}

    if isinstance(user_obj, discord.Member):
        status_str = str(user_obj.status)
        return {
            "status": "success",
            "user_id": user_id,
            "user_status": status_str,
            "guild_id": str(user_obj.guild.id),
            "timestamp": datetime.datetime.now().isoformat()
        }
    else:
        # If we only have a User object, status isn't directly available without presence intent/cache.
        return {"error": f"Cannot determine status for user {user_id} outside of a shared server or without presence intent.", "user_id": user_id}

async def get_user_activity(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets the current activity (e.g., Playing game) of a user. Requires guild context."""
    print(f"Executing get_user_activity for user ID: {user_id}.")
    user_obj, error_resp = await _get_user_or_member(cog, user_id)
    if error_resp: return error_resp
    if not user_obj: return {"error": f"Failed to retrieve user object for ID {user_id}."}

    activity_info = None
    if isinstance(user_obj, discord.Member) and user_obj.activity:
        activity = user_obj.activity
        activity_type_str = str(activity.type).split('.')[-1] # e.g., 'playing', 'streaming', 'listening'
        activity_details = {"type": activity_type_str, "name": activity.name}

        # Add more details based on activity type
        if isinstance(activity, discord.Game):
            if hasattr(activity, 'start'): activity_details["start_time"] = activity.start.isoformat() if activity.start else None
            if hasattr(activity, 'end'): activity_details["end_time"] = activity.end.isoformat() if activity.end else None
        elif isinstance(activity, discord.Streaming):
            activity_details.update({"platform": activity.platform, "url": activity.url, "game": activity.game})
        elif isinstance(activity, discord.Spotify):
            activity_details.update({
                "title": activity.title, "artist": activity.artist, "album": activity.album,
                "album_cover_url": activity.album_cover_url, "track_id": activity.track_id,
                "duration": str(activity.duration),
                "start": activity.start.isoformat() if activity.start else None,
                "end": activity.end.isoformat() if activity.end else None
            })
        elif isinstance(activity, discord.CustomActivity):
             activity_details.update({"custom_text": activity.name, "emoji": str(activity.emoji) if activity.emoji else None})
             activity_details["name"] = activity.name # Override generic name with the custom text
        # Add other activity types if needed (Listening, Watching)

        activity_info = activity_details
        status = "success"
        guild_id = str(user_obj.guild.id)
    elif isinstance(user_obj, discord.Member):
        status = "success" # Found member but they have no activity
        guild_id = str(user_obj.guild.id)
    else:
        return {"error": f"Cannot determine activity for user {user_id} outside of a shared server.", "user_id": user_id}

    return {
        "status": status,
        "user_id": user_id,
        "activity": activity_info, # Will be None if no activity
        "guild_id": guild_id if isinstance(user_obj, discord.Member) else None,
        "timestamp": datetime.datetime.now().isoformat()
    }

async def get_user_roles(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets the list of roles for a user in the current server. Requires guild context."""
    print(f"Executing get_user_roles for user ID: {user_id}.")
    user_obj, error_resp = await _get_user_or_member(cog, user_id)
    if error_resp: return error_resp
    if not user_obj: return {"error": f"Failed to retrieve user object for ID {user_id}."}

    if isinstance(user_obj, discord.Member):
        roles_list = []
        # Sort roles by position (highest first), excluding @everyone
        sorted_roles = sorted(user_obj.roles, key=lambda r: r.position, reverse=True)
        for role in sorted_roles:
            if role.is_default(): continue # Skip @everyone
            roles_list.append({
                "id": str(role.id),
                "name": role.name,
                "color": str(role.color),
                "position": role.position
            })
        return {
            "status": "success",
            "user_id": user_id,
            "roles": roles_list,
            "role_count": len(roles_list),
            "guild_id": str(user_obj.guild.id),
            "timestamp": datetime.datetime.now().isoformat()
        }
    else:
        return {"error": f"Cannot determine roles for user {user_id} outside of a shared server.", "user_id": user_id}

async def get_user_profile_info(cog: commands.Cog, user_id: str) -> Dict[str, Any]:
    """Gets comprehensive profile information for a given user ID."""
    print(f"Executing get_user_profile_info for user ID: {user_id}.")
    user_obj, error_resp = await _get_user_or_member(cog, user_id)
    if error_resp: return error_resp
    if not user_obj: return {"error": f"Failed to retrieve user object for ID {user_id}."}

    profile_info = {
        "user_id": user_id,
        "username": str(user_obj),
        "display_name": user_obj.display_name,
        "avatar_url": str(user_obj.display_avatar.url),
        "is_bot": user_obj.bot,
        "created_at": user_obj.created_at.isoformat() if user_obj.created_at else None,
        # Fields requiring Member object
        "status": None,
        "activity": None,
        "roles": None,
        "role_count": 0,
        "joined_at": None,
        "guild_id": None,
        "nickname": None,
        "voice_state": None,
    }

    if isinstance(user_obj, discord.Member):
        profile_info["status"] = str(user_obj.status)
        profile_info["joined_at"] = user_obj.joined_at.isoformat() if user_obj.joined_at else None
        profile_info["guild_id"] = str(user_obj.guild.id)
        profile_info["nickname"] = user_obj.nick # Store specific nickname

        # Get Activity
        activity_result = await get_user_activity(cog, user_id)
        if activity_result.get("status") == "success":
            profile_info["activity"] = activity_result.get("activity")

        # Get Roles
        roles_result = await get_user_roles(cog, user_id)
        if roles_result.get("status") == "success":
            profile_info["roles"] = roles_result.get("roles")
            profile_info["role_count"] = roles_result.get("role_count", 0)

        # Get Voice State (if connected)
        if user_obj.voice:
            voice = user_obj.voice
            profile_info["voice_state"] = {
                "channel_id": str(voice.channel.id) if voice.channel else None,
                "channel_name": voice.channel.name if voice.channel else None,
                "deaf": voice.deaf, "mute": voice.mute,
                "self_deaf": voice.self_deaf, "self_mute": voice.self_mute,
                "self_stream": voice.self_stream, "self_video": voice.self_video,
                "suppress": voice.suppress, "afk": voice.afk,
                "session_id": voice.session_id
            }

    return {
        "status": "success",
        "profile": profile_info,
        "timestamp": datetime.datetime.now().isoformat()
    }

# --- End User Profile Tools ---


# --- Tool Mapping ---
