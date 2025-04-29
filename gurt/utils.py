import discord
import re
import random
import asyncio
import time
import datetime
import json
import os
from typing import TYPE_CHECKING, Optional, Tuple, Dict, Any

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting

# --- Utility Functions ---
# Note: Functions needing cog state (like personality traits for mistakes)
#       will need the 'cog' instance passed in.

def replace_mentions_with_names(cog: 'GurtCog', content: str, message: discord.Message) -> str:
    """Replaces user mentions (<@id> or <@!id>) with their display names."""
    if not message.mentions:
        return content

    processed_content = content
    # Sort by length of ID to handle potential overlaps correctly (longer IDs first)
    # Although Discord IDs are fixed length, this is safer if formats change
    sorted_mentions = sorted(message.mentions, key=lambda m: len(str(m.id)), reverse=True)

    for member in sorted_mentions:
        # Use display_name for better readability
        processed_content = processed_content.replace(f'<@{member.id}>', member.display_name)
        processed_content = processed_content.replace(f'<@!{member.id}>', member.display_name) # Handle nickname mention format
    return processed_content

def _format_attachment_size(size_bytes: int) -> str:
    """Formats attachment size into KB or MB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def format_message(cog: 'GurtCog', message: discord.Message) -> Dict[str, Any]:
    """
    Helper function to format a discord.Message object into a dictionary,
    including detailed reply info and attachment descriptions.
    """
    # Process content first to replace mentions
    processed_content = replace_mentions_with_names(cog, message.content, message) # Pass cog

    # --- Attachment Processing ---
    attachment_descriptions = []
    for a in message.attachments:
        size_str = _format_attachment_size(a.size)
        file_type = "Image" if a.content_type and a.content_type.startswith("image/") else "File"
        description = f"[{file_type}: {a.filename} ({a.content_type or 'unknown type'}, {size_str})]"
        attachment_descriptions.append({
            "description": description,
            "filename": a.filename,
            "content_type": a.content_type,
            "size": a.size,
            "url": a.url # Keep URL for potential future use (e.g., vision model)
        })
    # --- End Attachment Processing ---

    # Basic message structure
    formatted_msg = {
        "id": str(message.id),
        "author": {
            "id": str(message.author.id),
            "name": message.author.name,
            "display_name": message.author.display_name,
            "bot": message.author.bot
        },
        "content": processed_content, # Use processed content
        "created_at": message.created_at.isoformat(),
        "attachment_descriptions": attachment_descriptions, # Use new descriptions list
        # "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments], # REMOVED old field
        "embeds": len(message.embeds) > 0,
        "mentions": [{"id": str(m.id), "name": m.name, "display_name": m.display_name} for m in message.mentions], # Keep detailed mentions
        # Reply fields initialized
        "replied_to_message_id": None,
        "replied_to_author_id": None,
        "replied_to_author_name": None,
        "replied_to_content_snippet": None, # Changed field name for clarity
        "is_reply": False
    }

    # --- Reply Processing ---
    if message.reference and message.reference.message_id:
        formatted_msg["replied_to_message_id"] = str(message.reference.message_id)
        formatted_msg["is_reply"] = True
        # Try to get resolved details (might be None if message not cached/fetched)
        ref_msg = message.reference.resolved
        if isinstance(ref_msg, discord.Message): # Check if resolved is a Message
            formatted_msg["replied_to_author_id"] = str(ref_msg.author.id)
            formatted_msg["replied_to_author_name"] = ref_msg.author.display_name
            # Create a snippet of the replied-to content
            snippet = ref_msg.content
            if len(snippet) > 80: # Truncate long replies
                snippet = snippet[:77] + "..."
            formatted_msg["replied_to_content_snippet"] = snippet
        # else: print(f"Referenced message {message.reference.message_id} not resolved.") # Optional debug
    # --- End Reply Processing ---

    return formatted_msg

def update_relationship(cog: 'GurtCog', user_id_1: str, user_id_2: str, change: float):
    """Updates the relationship score between two users."""
    # Ensure consistent key order
    if user_id_1 > user_id_2: user_id_1, user_id_2 = user_id_2, user_id_1
    # Initialize user_id_1's dict if not present
    if user_id_1 not in cog.user_relationships: cog.user_relationships[user_id_1] = {}

    current_score = cog.user_relationships[user_id_1].get(user_id_2, 0.0)
    new_score = max(0.0, min(current_score + change, 100.0)) # Clamp 0-100
    cog.user_relationships[user_id_1][user_id_2] = new_score
    # print(f"Updated relationship {user_id_1}-{user_id_2}: {current_score:.1f} -> {new_score:.1f} ({change:+.1f})") # Debug log

async def simulate_human_typing(cog: 'GurtCog', channel, text: str):
    """Shows typing indicator without significant delay."""
    # Minimal delay to ensure the typing indicator shows up reliably
    # but doesn't add noticeable latency to the response.
    # The actual sending of the message happens immediately after this.
    # Check if the bot has permissions to send messages and type
    perms = channel.permissions_for(channel.guild.me) if isinstance(channel, discord.TextChannel) else None
    if perms is None or (perms.send_messages and perms.send_tts_messages): # send_tts_messages often implies typing allowed
        try:
            async with channel.typing():
                await asyncio.sleep(0.1) # Very short sleep, just to ensure typing shows
        except discord.Forbidden:
            print(f"Warning: Missing permissions to type in channel {channel.id}")
        except Exception as e:
            print(f"Warning: Error during typing simulation in {channel.id}: {e}")
    # else: print(f"Skipping typing simulation in {channel.id} due to missing permissions.") # Optional debug

async def log_internal_api_call(cog: 'GurtCog', task_description: str, payload: Dict[str, Any], response_data: Optional[Dict[str, Any]], error: Optional[Exception] = None):
    """Helper function to log internal API calls to a file."""
    log_dir = "data"
    log_file = os.path.join(log_dir, "internal_api_calls.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.datetime.now().isoformat()
        log_entry = f"--- Log Entry: {timestamp} ---\n"
        log_entry += f"Task: {task_description}\n"
        log_entry += f"Model: {payload.get('model', 'N/A')}\n"

        # Sanitize payload for logging (avoid large base64 images)
        payload_to_log = payload.copy()
        if 'messages' in payload_to_log:
            sanitized_messages = []
            for msg in payload_to_log['messages']:
                if isinstance(msg.get('content'), list): # Multimodal message
                    new_content = []
                    for part in msg['content']:
                        if part.get('type') == 'image_url' and part.get('image_url', {}).get('url', '').startswith('data:image'):
                            new_content.append({'type': 'image_url', 'image_url': {'url': 'data:image/...[truncated]'}})
                        else:
                            new_content.append(part)
                    sanitized_messages.append({**msg, 'content': new_content})
                else:
                    sanitized_messages.append(msg)
            payload_to_log['messages'] = sanitized_messages

        log_entry += f"Request Payload:\n{json.dumps(payload_to_log, indent=2)}\n"
        if response_data: log_entry += f"Response Data:\n{json.dumps(response_data, indent=2)}\n"
        if error: log_entry += f"Error: {str(error)}\n"
        log_entry += "---\n\n"

        # Use async file writing if in async context, but this helper might be called from sync code?
        # Sticking to sync file I/O for simplicity here, assuming logging isn't performance critical path.
        with open(log_file, "a", encoding="utf-8") as f: f.write(log_entry)
    except Exception as log_e: print(f"!!! Failed to write to internal API log file {log_file}: {log_e}")

# Note: _create_human_like_mistake was removed as it wasn't used in the final on_message logic provided.
# If needed, it can be added back here, ensuring it takes 'cog' if it needs personality traits.
