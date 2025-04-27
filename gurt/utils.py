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
    sorted_mentions = sorted(message.mentions, key=lambda m: len(str(m.id)), reverse=True)

    for member in sorted_mentions:
        processed_content = processed_content.replace(f'<@{member.id}>', member.display_name)
        processed_content = processed_content.replace(f'<@!{member.id}>', member.display_name)
    return processed_content

def format_message(cog: 'GurtCog', message: discord.Message) -> Dict[str, Any]:
    """Helper function to format a discord.Message object into a dictionary."""
    processed_content = replace_mentions_with_names(cog, message.content, message) # Pass cog
    mentioned_users_details = [
        {"id": str(m.id), "name": m.name, "display_name": m.display_name}
        for m in message.mentions
    ]

    formatted_msg = {
        "id": str(message.id),
        "author": {
            "id": str(message.author.id), "name": message.author.name,
            "display_name": message.author.display_name, "bot": message.author.bot
        },
        "content": processed_content,
        "created_at": message.created_at.isoformat(),
        "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
        "embeds": len(message.embeds) > 0,
        "mentions": [{"id": str(m.id), "name": m.name} for m in message.mentions], # Keep original simple list too
        "mentioned_users_details": mentioned_users_details,
        "replied_to_message_id": None, "replied_to_author_id": None,
        "replied_to_author_name": None, "replied_to_content": None,
        "is_reply": False
    }

    if message.reference and message.reference.message_id:
        formatted_msg["replied_to_message_id"] = str(message.reference.message_id)
        formatted_msg["is_reply"] = True
        # Try to get resolved details (might be None if message not cached/fetched)
        ref_msg = message.reference.resolved
        if isinstance(ref_msg, discord.Message): # Check if resolved is a Message
            formatted_msg["replied_to_author_id"] = str(ref_msg.author.id)
            formatted_msg["replied_to_author_name"] = ref_msg.author.display_name
            formatted_msg["replied_to_content"] = ref_msg.content
        # else: print(f"Referenced message {message.reference.message_id} not resolved.") # Optional debug

    return formatted_msg

def update_relationship(cog: 'GurtCog', user_id_1: str, user_id_2: str, change: float):
    """Updates the relationship score between two users."""
    if user_id_1 > user_id_2: user_id_1, user_id_2 = user_id_2, user_id_1
    if user_id_1 not in cog.user_relationships: cog.user_relationships[user_id_1] = {}

    current_score = cog.user_relationships[user_id_1].get(user_id_2, 0.0)
    new_score = max(0.0, min(current_score + change, 100.0)) # Clamp 0-100
    cog.user_relationships[user_id_1][user_id_2] = new_score
    # print(f"Updated relationship {user_id_1}-{user_id_2}: {current_score:.1f} -> {new_score:.1f} ({change:+.1f})") # Debug log

async def simulate_human_typing(cog: 'GurtCog', channel, text: str):
    """Simulates realistic human typing behavior."""
    base_char_delay = random.uniform(0.05, 0.12)
    channel_id = channel.id

    # Adjust speed based on channel dynamics if available
    if hasattr(cog, 'channel_response_timing') and channel_id in cog.channel_response_timing:
        response_factor = cog.channel_response_timing[channel_id]
        base_char_delay *= response_factor * random.uniform(0.85, 1.15)
        # print(f"Adjusting typing speed (factor: {response_factor:.2f})") # Debug

    # Adjust speed based on mood
    if cog.current_mood in ["excited", "slightly hyper"]: base_char_delay *= 0.7
    elif cog.current_mood in ["tired", "a bit bored"]: base_char_delay *= 1.3

    # Typo probability (needs personality traits from cog)
    # Fetch current traits - might be slightly inefficient to fetch each time
    persistent_traits = await cog.memory_manager.get_all_personality_traits()
    randomness = persistent_traits.get('randomness', 0.5) # Default if fetch fails
    typo_probability = 0.02 * (0.5 + randomness)

    nearby_keys = { # Simplified for example
        'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx', 'e': 'wrsdf', 'f': 'drtgvc',
        'g': 'ftyhbv', 'h': 'gyujnb', 'i': 'uojkl', 'j': 'huikmn', 'k': 'jiolm', 'l': 'kop;',
        'm': 'njk,', 'n': 'bhjm', 'o': 'iklp', 'p': 'ol;[', 'q': 'asw', 'r': 'edft',
        's': 'awedxz', 't': 'rfgy', 'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc',
        'y': 'tghu', 'z': 'asx'
    }

    total_time = 0; max_time = 10.0
    async with channel.typing():
        i = 0
        while i < len(text) and total_time < max_time:
            char_delay = base_char_delay
            if text[i] in ['.', '!', '?', ',']: char_delay *= random.uniform(1.5, 2.5)
            elif text[i] == ' ': char_delay *= random.uniform(1.0, 1.8)

            if random.random() < 0.03 and text[i] in [' ', ',']:
                thinking_pause = random.uniform(0.5, 1.5)
                await asyncio.sleep(thinking_pause); total_time += thinking_pause

            make_typo = random.random() < typo_probability and text[i].lower() in nearby_keys
            if make_typo:
                await asyncio.sleep(char_delay); total_time += char_delay # Wait before typo
                if random.random() < 0.8: # Correct typo
                    notice_delay = random.uniform(0.2, 0.8)
                    await asyncio.sleep(notice_delay); total_time += notice_delay
                    correction_delay = random.uniform(0.1, 0.3) # Simulate backspace+correct
                    await asyncio.sleep(correction_delay); total_time += correction_delay
                # else: pass # Don't correct
            else:
                await asyncio.sleep(char_delay); total_time += char_delay

            i += 1
            # Simulate burst typing
            if random.random() < 0.1 and i < len(text) - 3:
                next_few_chars = text[i:i+min(5, len(text)-i)]
                if ' ' not in next_few_chars:
                    burst_length = min(len(next_few_chars), random.randint(2, 4))
                    burst_delay = base_char_delay * 0.4 * burst_length
                    await asyncio.sleep(burst_delay); total_time += burst_delay
                    i += burst_length - 1

        min_typing_time = min(1.0, len(text) * 0.03)
        if total_time < min_typing_time: await asyncio.sleep(min_typing_time - total_time)

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

        with open(log_file, "a", encoding="utf-8") as f: f.write(log_entry)
    except Exception as log_e: print(f"!!! Failed to write to internal API log file {log_file}: {log_e}")

# Note: _create_human_like_mistake was removed as it wasn't used in the final on_message logic provided.
# If needed, it can be added back here, ensuring it takes 'cog' if it needs personality traits.
