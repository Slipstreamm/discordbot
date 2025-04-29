# Import the MemoryManager from the parent directory
# Use a direct import path that doesn't rely on package structure
import os
import importlib.util
from typing import TYPE_CHECKING, List, Sequence, Dict, Any # Import TYPE_CHECKING and other types
import collections # Import collections for deque

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
# Import specific message types needed
from langchain_core.messages import (
    BaseMessage, AIMessage, HumanMessage, SystemMessage, ToolMessage
)

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
        """Retrieve messages from the cache and reconstruct LangChain messages."""
        # Access the cache via the cog instance
        # Ensure the cache is initialized as a deque
        channel_cache = self.cog.message_cache['by_channel'].setdefault(
            self.channel_id, collections.deque(maxlen=CONTEXT_WINDOW_SIZE * 2) # Use a larger maxlen for safety?
        )
        cached_messages_data = list(channel_cache) # Get a list copy

        items: List[BaseMessage] = []
        # Apply context window limit (consider if the limit should apply differently to LC messages vs formatted)
        # For now, apply simple limit to the combined list
        relevant_messages_data = cached_messages_data[-(CONTEXT_WINDOW_SIZE * 2):] # Use the potentially larger limit

        for msg_data in relevant_messages_data:
            if isinstance(msg_data, dict) and msg_data.get('_is_lc_message_'):
                # Reconstruct LangChain message from serialized dict
                lc_type = msg_data.get('lc_type')
                content = msg_data.get('content', '')
                additional_kwargs = msg_data.get('additional_kwargs', {})
                tool_calls = msg_data.get('tool_calls') # For AIMessage
                tool_call_id = msg_data.get('tool_call_id') # For ToolMessage

                try:
                    if lc_type == 'HumanMessage':
                        items.append(HumanMessage(content=content, additional_kwargs=additional_kwargs))
                    elif lc_type == 'AIMessage':
                        # Reconstruct AIMessage, potentially with tool_calls
                        ai_msg = AIMessage(content=content, additional_kwargs=additional_kwargs)
                        if tool_calls:
                            # Ensure tool_calls are in the correct format if needed (e.g., list of dicts)
                            # Assuming they were stored correctly from message.dict()
                            ai_msg.tool_calls = tool_calls
                        items.append(ai_msg)
                    elif lc_type == 'ToolMessage':
                        # ToolMessage needs content and tool_call_id
                        if tool_call_id:
                            items.append(ToolMessage(content=content, tool_call_id=tool_call_id, additional_kwargs=additional_kwargs))
                        else:
                            logger.warning(f"Skipping ToolMessage reconstruction, missing tool_call_id: {msg_data}")
                    elif lc_type == 'SystemMessage': # Should not happen via add_message, but handle defensively
                        items.append(SystemMessage(content=content, additional_kwargs=additional_kwargs))
                    # Add other types if needed (FunctionMessage?)
                    else:
                        logger.warning(f"Unhandled LangChain message type '{lc_type}' during reconstruction.")

                except Exception as recon_e:
                    logger.error(f"Error reconstructing LangChain message type '{lc_type}': {recon_e}\nData: {msg_data}", exc_info=True)

            elif isinstance(msg_data, dict) and not msg_data.get('_is_lc_message_'):
                # Existing logic for reconstructing from formatted user/bot messages
                # This assumes the agent doesn't add Human/AI messages that overlap with these
                role = "ai" if msg_data.get('author', {}).get('id') == str(self.cog.bot.user.id) else "human"
                # Reconstruct content similar to original logic (simplified)
                content_parts = []
                author_name = msg_data.get('author', {}).get('display_name', 'Unknown')

                # Basic content reconstruction
                content = msg_data.get('content', '')
                attachments = msg_data.get("attachment_descriptions", [])
                if attachments:
                    attachment_str = " ".join([att['description'] for att in attachments])
                    content += f" [Attachments: {attachment_str}]" # Append attachment info

                # Combine author and content for the LangChain message
                # NOTE: This might differ from how the agent expects input if it relies on raw content.
                # Consider if just the content string is better here.
                # Let's stick to the previous format for now.
                full_content = f"{author_name}: {content}"

                if role == "human":
                    items.append(HumanMessage(content=full_content))
                elif role == "ai":
                    # This should only be the *final* AI response text, without tool calls
                    items.append(AIMessage(content=full_content))
                else:
                    logger.warning(f"Unhandled message role '{role}' in GurtMessageCacheHistory (formatted msg) for channel {self.channel_id}")
            else:
                logger.warning(f"Skipping unrecognized item in message cache: {type(msg_data)}")

        return items

    def add_message(self, message: BaseMessage) -> None:
        """Add a LangChain BaseMessage to the history cache."""
        try:
            # Serialize the message object to a dictionary using pydantic's dict()
            message_dict = message.dict()
            # Explicitly store the LangChain class name for reconstruction
            message_dict['lc_type'] = message.__class__.__name__
            # Add our flag to distinguish it during retrieval
            message_dict['_is_lc_message_'] = True

            # Ensure tool_calls and tool_call_id are preserved if they exist
            # (message.dict() should handle this, but double-check if issues arise)
            # Example explicit checks (might be redundant):
            # if isinstance(message, AIMessage) and hasattr(message, 'tool_calls') and message.tool_calls:
            #     message_dict['tool_calls'] = message.tool_calls
            # elif isinstance(message, ToolMessage) and hasattr(message, 'tool_call_id'):
            #     message_dict['tool_call_id'] = message.tool_call_id

            # Access the cache via the cog instance, ensuring it's a deque
            channel_cache = self.cog.message_cache['by_channel'].setdefault(
                self.channel_id, collections.deque(maxlen=CONTEXT_WINDOW_SIZE * 2) # Use consistent maxlen
            )
            channel_cache.append(message_dict)
            logger.debug(f"Added LangChain message ({message.__class__.__name__}) to cache for channel {self.channel_id}")

        except Exception as e:
            logger.error(f"Error adding LangChain message to cache for channel {self.channel_id}: {e}", exc_info=True)


    # Optional: Implement add_user_message, add_ai_message if needed (BaseChatMessageHistory provides defaults)

    def clear(self) -> None:
        """Clear history from the cache for this channel."""
        logger.warning(f"GurtMessageCacheHistory.clear() called for channel {self.channel_id}. Clearing cache deque.")
        if self.channel_id in self.cog.message_cache['by_channel']:
            # Clear the deque instead of deleting the key, to keep the deque object
            self.cog.message_cache['by_channel'][self.channel_id].clear()
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
