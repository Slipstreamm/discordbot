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
                print(f"Unexpected error deleting container {container.id[:12]}: {delete_exc}") # <--- Corrected indentation
        # Ensure the client connection is closed
        if client:
            await client.close()

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
    "extract_web_content": extract_web_content
}
