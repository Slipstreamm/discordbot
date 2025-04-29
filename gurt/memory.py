# Import the MemoryManager from the parent directory
# Use a direct import path that doesn't rely on package structure
import os
import importlib.util
from typing import TYPE_CHECKING # Import TYPE_CHECKING

if TYPE_CHECKING:
    from .cog import GurtCog # Use relative import for type hinting

# Get the absolute path to gurt_memory.py
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gurt_memory_path = os.path.join(parent_dir, 'gurt_memory.py')

# Load the module dynamically
spec = importlib.util.spec_from_file_location('gurt_memory', gurt_memory_path)
gurt_memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gurt_memory)

# Import the MemoryManager class from the loaded module
MemoryManager = gurt_memory.MemoryManager

import logging
from typing import List, Sequence

# LangChain imports for Chat History
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage

# Relative imports
from .config import CONTEXT_WINDOW_SIZE # Import context window size

# Configure logging if not already done elsewhere
logger = logging.getLogger(__name__)

# --- LangChain Chat History Implementation ---

class GurtMessageCacheHistory(BaseChatMessageHistory):
    """Chat message history that reads from and potentially writes to GurtCog's message cache."""

    def __init__(self, cog: 'GurtCog', channel_id: int):
        # Use relative import for type checking within the function scope if needed,
        # or rely solely on the TYPE_CHECKING block if sufficient.
        # For runtime check, a local relative import is safer.
        from .cog import GurtCog # Use relative import here
        if not isinstance(cog, GurtCog):
             raise TypeError("GurtMessageCacheHistory requires a GurtCog instance.")
        self.cog = cog
        self.channel_id = channel_id
        self.key = f"channel:{channel_id}" # Example key structure

    @property
    def messages(self) -> List[BaseMessage]:  # type: ignore
        """Retrieve messages from the cache and format them."""
        # Access the cache via the cog instance
        cached_messages_data = list(self.cog.message_cache['by_channel'].get(self.channel_id, []))

        # Apply context window limit
        items: List[BaseMessage] = []
        # Take the last N messages based on CONTEXT_WINDOW_SIZE
        relevant_messages_data = cached_messages_data[-CONTEXT_WINDOW_SIZE:]

        for msg_data in relevant_messages_data:
            role = "ai" if msg_data['author']['id'] == str(self.cog.bot.user.id) else "human"
            # Reconstruct content similar to gather_conversation_context
            content_parts = []
            author_name = msg_data['author']['display_name']

            if msg_data.get("is_reply"):
                reply_author = msg_data.get('replied_to_author_name', 'Unknown User')
                reply_snippet = msg_data.get('replied_to_content_snippet')
                reply_snippet_short = '...'
                if isinstance(reply_snippet, str):
                    reply_snippet_short = (reply_snippet[:25] + '...') if len(reply_snippet) > 28 else reply_snippet
                content_parts.append(f"{author_name} (replying to {reply_author} '{reply_snippet_short}'):")
            else:
                content_parts.append(f"{author_name}:")

            if msg_data.get('content'):
                content_parts.append(msg_data['content'])

            attachments = msg_data.get("attachment_descriptions", [])
            if attachments:
                attachment_str = " ".join([att['description'] for att in attachments])
                content_parts.append(f"[Attachments: {attachment_str}]") # Clearly label attachments

            content = " ".join(content_parts).strip()

            if role == "human":
                items.append(HumanMessage(content=content))
            elif role == "ai":
                items.append(AIMessage(content=content))
            else:
                # Handle other roles if necessary, or raise an error
                logger.warning(f"Unhandled message role '{role}' in GurtMessageCacheHistory for channel {self.channel_id}")

        return items

    def add_message(self, message: BaseMessage) -> None:
        """
        Add a message to the history.

        Note: This implementation assumes the GurtCog's message listeners
        are already populating the cache. This method might just log
        or could potentially duplicate additions if not careful.
        For now, we make it a no-op and rely on the cog's caching.
        """
        logger.debug(f"GurtMessageCacheHistory.add_message called for channel {self.channel_id}, but is currently a no-op. Cache is populated by GurtCog listeners.")
        # If we needed to write back:
        # self._add_message_to_cache(message)
        pass

    # Optional: Implement add_user_message, add_ai_message if needed

    def clear(self) -> None:
        """Clear history from the cache for this channel."""
        logger.warning(f"GurtMessageCacheHistory.clear() called for channel {self.channel_id}. Clearing cache entry.")
        if self.channel_id in self.cog.message_cache['by_channel']:
            del self.cog.message_cache['by_channel'][self.channel_id]
            # Potentially clear other related caches if necessary

# Factory function for LangchainAgent
def get_gurt_session_history(session_id: str, cog: 'GurtCog') -> BaseChatMessageHistory:
    """
    Factory function to get a chat history instance for a given session ID.
    The session_id is expected to be the Discord channel ID.
    """
    try:
        channel_id = int(session_id)
        return GurtMessageCacheHistory(cog=cog, channel_id=channel_id)
    except ValueError:
        logger.error(f"Invalid session_id for Gurt chat history: '{session_id}'. Expected integer channel ID.")
        # Return an in-memory history as a fallback? Or raise error?
        # from langchain_community.chat_message_histories import ChatMessageHistory
        # return ChatMessageHistory() # Fallback to basic in-memory
        raise ValueError(f"Invalid session_id: {session_id}")
    except TypeError as e:
        logger.error(f"TypeError creating GurtMessageCacheHistory: {e}. Ensure 'cog' is passed correctly.")
        raise

# Re-export the MemoryManager class AND the history components
__all__ = ['MemoryManager', 'GurtMessageCacheHistory', 'get_gurt_session_history']
