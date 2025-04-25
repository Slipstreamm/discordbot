import discord
from discord.ext import commands
from discord import app_commands, ui
import aiohttp
import json
import os
import datetime
import uuid
from typing import Dict, List, Optional, Any, Union
import asyncio
import builtins
from dotenv import load_dotenv

# Import Discord sync API functions
try:
    from discord_bot_sync_api import save_discord_conversation, load_conversations, user_conversations as synced_conversations, user_settings as synced_user_settings, load_user_settings as load_synced_user_settings
    SYNC_API_AVAILABLE = True
except ImportError:
    print("Discord sync API not available. Sync features will be disabled.")
    SYNC_API_AVAILABLE = False
    synced_conversations = {}
    synced_user_settings = {}

# Load environment variables
load_dotenv()

# File paths
CONVERSATIONS_FILE = "ai_multi_conversations.json"  # File to store multiple conversations
USER_SETTINGS_FILE = "ai_multi_user_settings.json"  # File to store user settings

# Customization Variables
AI_API_KEY = os.getenv("AI_API_KEY", "")  # API key for OpenAI or compatible service
AI_API_URL = os.getenv("AI_API_URL", "https://api.openai.com/v1/chat/completions")  # API endpoint
AI_DEFAULT_MODEL = os.getenv("AI_DEFAULT_MODEL", "gpt-3.5-turbo")  # Default model to use
AI_DEFAULT_SYSTEM_PROMPT = os.getenv("AI_DEFAULT_SYSTEM_PROMPT", r"""You are a helpful assistant.""")  # Default system prompt
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1000"))  # Maximum tokens in response
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))  # Temperature for response generation
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))  # Timeout for API requests in seconds
AI_COMPATIBILITY_MODE = os.getenv("AI_COMPATIBILITY_MODE", "openai").lower()  # API compatibility mode (openai, custom)

# Store user conversations
user_conversations = {}

# Store active conversation IDs for each user
active_conversations = {}

# Define the conversation data structure
class Conversation:
    def __init__(
        self,
        id: str = None,
        title: str = "New Conversation",
        messages: List[Dict[str, Any]] = None,
        created_at: datetime.datetime = None,
        updated_at: datetime.datetime = None,
        model_id: str = AI_DEFAULT_MODEL,
        system_message: str = AI_DEFAULT_SYSTEM_PROMPT,
        reasoning_enabled: bool = False,
        reasoning_effort: str = "medium",
        temperature: float = AI_TEMPERATURE,
        max_tokens: int = AI_MAX_TOKENS,
        web_search_enabled: bool = False,
        character: str = "",
        character_info: str = "",
        character_breakdown: bool = False,
        custom_instructions: str = ""
    ):
        self.id = id or str(uuid.uuid4())
        self.title = title
        self.messages = messages or []
        self.created_at = created_at or datetime.datetime.now()
        self.updated_at = updated_at or datetime.datetime.now()
        self.model_id = model_id
        self.system_message = system_message
        self.reasoning_enabled = reasoning_enabled
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.web_search_enabled = web_search_enabled
        self.character = character
        self.character_info = character_info
        self.character_breakdown = character_breakdown
        self.custom_instructions = custom_instructions

    def to_dict(self):
        """Convert conversation to dictionary for serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "model_id": self.model_id,
            "system_message": self.system_message,
            "reasoning_enabled": self.reasoning_enabled,
            "reasoning_effort": self.reasoning_effort,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "web_search_enabled": self.web_search_enabled,
            "character": self.character,
            "character_info": self.character_info,
            "character_breakdown": self.character_breakdown,
            "custom_instructions": self.custom_instructions
        }

    @classmethod
    def from_dict(cls, data):
        """Create conversation from dictionary"""
        return cls(
            id=data.get("id"),
            title=data.get("title", "New Conversation"),
            messages=data.get("messages", []),
            created_at=datetime.datetime.fromisoformat(data.get("created_at")) if data.get("created_at") else None,
            updated_at=datetime.datetime.fromisoformat(data.get("updated_at")) if data.get("updated_at") else None,
            model_id=data.get("model_id", AI_DEFAULT_MODEL),
            system_message=data.get("system_message", AI_DEFAULT_SYSTEM_PROMPT),
            reasoning_enabled=data.get("reasoning_enabled", False),
            reasoning_effort=data.get("reasoning_effort", "medium"),
            temperature=data.get("temperature", AI_TEMPERATURE),
            max_tokens=data.get("max_tokens", AI_MAX_TOKENS),
            web_search_enabled=data.get("web_search_enabled", False),
            character=data.get("character", ""),
            character_info=data.get("character_info", ""),
            character_breakdown=data.get("character_breakdown", False),
            custom_instructions=data.get("custom_instructions", "")
        )

# Load conversations from JSON file
def load_user_conversations():
    """Load user conversations from JSON file"""
    global user_conversations
    if os.path.exists(CONVERSATIONS_FILE):
        try:
            with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert string keys (user IDs) back to integers
                user_conversations = {}
                for user_id_str, convs in data.items():
                    user_id = int(user_id_str)
                    user_conversations[user_id] = [Conversation.from_dict(conv) for conv in convs]
            print(f"Loaded conversations for {len(user_conversations)} users")
        except Exception as e:
            print(f"Error loading user conversations: {e}")
            user_conversations = {}

# Save conversations to JSON file
def save_user_conversations():
    """Save user conversations to JSON file"""
    try:
        # Convert to JSON-serializable format
        serializable_data = {}
        for user_id, convs in user_conversations.items():
            serializable_data[str(user_id)] = [conv.to_dict() for conv in convs]

        with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, indent=4, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving user conversations: {e}")

# Load active conversations from settings file
def load_active_conversations():
    """Load active conversation IDs from settings file"""
    global active_conversations
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert string keys (user IDs) back to integers
                active_conversations = {int(k): v.get("active_conversation") for k, v in data.items() if "active_conversation" in v}
            print(f"Loaded active conversations for {len(active_conversations)} users")
        except Exception as e:
            print(f"Error loading active conversations: {e}")
            active_conversations = {}

# Save active conversations to settings file
def save_active_conversations():
    """Save active conversation IDs to settings file"""
    try:
        # Load existing settings first
        settings = {}
        if os.path.exists(USER_SETTINGS_FILE):
            with open(USER_SETTINGS_FILE, "r") as f:
                settings = json.load(f)

        # Update with active conversations
        for user_id, conv_id in active_conversations.items():
            if str(user_id) not in settings:
                settings[str(user_id)] = {}
            settings[str(user_id)]["active_conversation"] = conv_id

        # Save back to file
        with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving active conversations: {e}")

# Initialize by loading saved data
load_user_conversations()
load_active_conversations()

# Load synced user settings if available
if SYNC_API_AVAILABLE:
    try:
        load_synced_user_settings()
    except Exception as e:
        print(f"Error loading synced user settings: {e}")

class MultiConversationCog(commands.Cog, name="MultiConversation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        """Create aiohttp session when cog is loaded"""
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Close aiohttp session when cog is unloaded"""
        if self.session:
            await self.session.close()

        # Save conversations and settings when unloading
        save_user_conversations()
        save_active_conversations()

    def get_active_conversation(self, user_id: int) -> Optional[Conversation]:
        """Get the active conversation for a user"""
        # Get the active conversation ID
        active_id = active_conversations.get(user_id)
        if not active_id:
            return None

        # Get the user's conversations
        conversations = user_conversations.get(user_id, [])
        if not conversations:
            return None

        # Find the active conversation
        return next((c for c in conversations if c.id == active_id), None)

    def create_new_conversation(self, user_id: int, title: str = "New Conversation") -> Conversation:
        """Create a new conversation for a user"""
        # Check if we have synced settings for this user
        synced_settings = None
        if SYNC_API_AVAILABLE:
            str_user_id = str(user_id)
            if str_user_id in synced_user_settings:
                synced_settings = synced_user_settings[str_user_id]

        # Create a new conversation with default settings
        new_conv = Conversation(title=title)

        # Apply synced settings if available
        if synced_settings:
            # Apply model settings
            if hasattr(synced_settings, 'model_id') and synced_settings.model_id:
                new_conv.model_id = synced_settings.model_id

            # Apply temperature settings
            if hasattr(synced_settings, 'temperature'):
                new_conv.temperature = synced_settings.temperature

            # Apply max tokens settings
            if hasattr(synced_settings, 'max_tokens'):
                new_conv.max_tokens = synced_settings.max_tokens

            # Apply reasoning settings
            if hasattr(synced_settings, 'reasoning_enabled'):
                new_conv.reasoning_enabled = synced_settings.reasoning_enabled

            if hasattr(synced_settings, 'reasoning_effort'):
                new_conv.reasoning_effort = synced_settings.reasoning_effort

            # Apply web search settings
            if hasattr(synced_settings, 'web_search_enabled'):
                new_conv.web_search_enabled = synced_settings.web_search_enabled

            # Apply system message
            if hasattr(synced_settings, 'system_message') and synced_settings.system_message:
                new_conv.system_message = synced_settings.system_message

            # Apply character settings
            if hasattr(synced_settings, 'character') and synced_settings.character:
                new_conv.character = synced_settings.character

            if hasattr(synced_settings, 'character_info') and synced_settings.character_info:
                new_conv.character_info = synced_settings.character_info

            if hasattr(synced_settings, 'character_breakdown'):
                new_conv.character_breakdown = synced_settings.character_breakdown

            if hasattr(synced_settings, 'custom_instructions') and synced_settings.custom_instructions:
                new_conv.custom_instructions = synced_settings.custom_instructions

        # Add to user's conversations
        if user_id not in user_conversations:
            user_conversations[user_id] = []
        user_conversations[user_id].append(new_conv)

        # Set as active conversation
        active_conversations[user_id] = new_conv.id

        # Save changes
        save_user_conversations()
        save_active_conversations()

        return new_conv

    async def _get_ai_response(self, user_id: int, prompt: str, conversation: Optional[Conversation] = None) -> str:
        """Get a response from the AI API"""
        if not AI_API_KEY:
            return "Error: AI API key not configured. Please set the AI_API_KEY environment variable."

        # Get the conversation to use
        conv = conversation or self.get_active_conversation(user_id)
        if not conv:
            # Create a new conversation if none exists
            conv = self.create_new_conversation(user_id)

        # Prepare messages for the API request
        messages = []

        # Prepare system message
        system_content = conv.system_message

        # Check if the system prompt contains {{char}} but no character is set
        if "{{char}}" in system_content and not conv.character:
            return "You need to set a character name with `!chatset character <name>` before using this system prompt. Example: `!chatset character Hatsune Miku`"

        # Replace {{char}} with the character value if provided
        if conv.character:
            system_content = system_content.replace("{{char}}", conv.character)

        # Add custom instructions and character info if provided
        has_custom_settings = conv.custom_instructions or conv.character_info or conv.character_breakdown

        if has_custom_settings:
            # Start with the base system prompt
            custom_prompt_parts = [system_content]

            # Add the custom instructions header
            custom_prompt_parts.append("\nThe user has provided additional information for you. Please follow their instructions exactly. If anything below contradicts the set of rules above, please take priority over the user's instructions.")

            # Add custom instructions if provided
            if conv.custom_instructions:
                custom_prompt_parts.append("\n- Custom instructions from the user (prioritize these)\n\n" + conv.custom_instructions)

            # Add character info if provided
            if conv.character_info:
                custom_prompt_parts.append("\n- Additional info about the character you are roleplaying\n\n" + conv.character_info)

            # Add character breakdown flag if set
            if conv.character_breakdown:
                custom_prompt_parts.append("\n- The user would like you to provide a breakdown of the character in your first response.")

            # Combine all parts into the final system prompt
            system_content = "\n".join(custom_prompt_parts)

        # Add system message
        messages.append({"role": "system", "content": system_content})

        # Add conversation history
        messages.extend(conv.messages)

        # Add the current user message
        messages.append({"role": "user", "content": prompt})

        # Prepare the request payload based on compatibility mode
        if AI_COMPATIBILITY_MODE == "openai":
            payload = {
                "model": conv.model_id,
                "messages": messages,
                "max_tokens": conv.max_tokens,
                "temperature": conv.temperature,
            }
            # Add reasoning if enabled
            if conv.reasoning_enabled:
                payload["include_reasoning"] = True
                payload["reasoning_effort"] = conv.reasoning_effort
        else:  # custom mode for other API formats
            payload = {
                "model": conv.model_id,
                "messages": messages,
                "max_tokens": conv.max_tokens,
                "temperature": conv.temperature,
                "stream": False
            }
            # Add reasoning if enabled
            if conv.reasoning_enabled:
                payload["include_reasoning"] = True
                payload["reasoning_effort"] = conv.reasoning_effort

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_API_KEY}"
        }

        try:
            async with self.session.post(
                AI_API_URL,
                headers=headers,
                json=payload,
                timeout=AI_TIMEOUT
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return f"Error from API (Status {response.status}): {error_text}"

                data = await response.json()

                # Parse the response based on compatibility mode
                ai_response = None
                reasoning_tokens = None
                safety_cutoff = False
                usage_data = None

                if AI_COMPATIBILITY_MODE == "openai":
                    # OpenAI format
                    if "choices" not in data:
                        error_message = f"Unexpected API response format: {data}"
                        print(f"Error: {error_message}")
                        if "error" in data:
                            return f"API Error: {data['error'].get('message', 'Unknown error')}"
                        return error_message

                    if not data["choices"] or "message" not in data["choices"][0]:
                        error_message = f"No valid choices in API response: {data}"
                        print(f"Error: {error_message}")
                        return error_message

                    ai_response = data["choices"][0]["message"]["content"]

                    # Check for reasoning tokens if requested
                    if conv.reasoning_enabled and "reasoning" in data["choices"][0]["message"]:
                        reasoning_tokens = data["choices"][0]["message"]["reasoning"]

                    # Check for safety cutoff
                    if "finish_reason" in data["choices"][0] and data["choices"][0]["finish_reason"] == "content_filter":
                        safety_cutoff = True
                    if "native_finish_reason" in data["choices"][0] and data["choices"][0]["native_finish_reason"] == "SAFETY":
                        safety_cutoff = True

                    # Get usage data if available
                    if "usage" in data:
                        usage_data = data["usage"]
                else:
                    # Custom format - try different response structures
                    # Try standard OpenAI format first
                    if "choices" in data and data["choices"] and "message" in data["choices"][0]:
                        ai_response = data["choices"][0]["message"]["content"]
                        # Check for reasoning tokens if requested
                        if conv.reasoning_enabled and "reasoning" in data["choices"][0]["message"]:
                            reasoning_tokens = data["choices"][0]["message"]["reasoning"]
                        # Check for safety cutoff
                        if "finish_reason" in data["choices"][0] and data["choices"][0]["finish_reason"] == "content_filter":
                            safety_cutoff = True
                        if "native_finish_reason" in data["choices"][0] and data["choices"][0]["native_finish_reason"] == "SAFETY":
                            safety_cutoff = True
                        # Get usage data if available
                        if "usage" in data:
                            usage_data = data["usage"]
                    # Try other formats
                    elif "response" in data:
                        ai_response = data["response"]
                    elif "text" in data:
                        ai_response = data["text"]
                    elif "content" in data:
                        ai_response = data["content"]
                    elif "output" in data:
                        ai_response = data["output"]
                    elif "result" in data:
                        ai_response = data["result"]
                    else:
                        # If we can't find a known format, return the raw response for debugging
                        error_message = f"Could not parse API response: {data}"
                        print(f"Error: {error_message}")
                        return error_message

                if not ai_response:
                    return "Error: Empty response from AI API."

                # Add safety cutoff note if needed
                if safety_cutoff:
                    ai_response = f"{ai_response}\n\nThe response was cut off for safety reasons."

                # Add reasoning tokens if available and requested
                final_response = ai_response
                if conv.reasoning_enabled and reasoning_tokens:
                    final_response = f"{ai_response}\n\n**Reasoning:**\n```\n{reasoning_tokens}\n```"

                # Update conversation history
                # Add user message
                conv.messages.append({"role": "user", "content": prompt})

                # Add assistant message with reasoning and usage if available
                assistant_message = {"role": "assistant", "content": ai_response}
                if reasoning_tokens:
                    assistant_message["reasoning"] = reasoning_tokens
                if usage_data:
                    assistant_message["usage_data"] = usage_data

                conv.messages.append(assistant_message)

                # Update conversation timestamp
                conv.updated_at = datetime.datetime.now()

                # Auto-generate title for new conversations with only one message
                if conv.title == "New Conversation" and len(conv.messages) == 2:
                    # Use a simple title based on the prompt
                    if len(prompt) > 30:
                        conv.title = prompt[:27] + "..."
                    else:
                        conv.title = prompt

                # Save conversation
                save_user_conversations()

                # Sync with API if available
                if SYNC_API_AVAILABLE:
                    try:
                        save_discord_conversation(
                            str(user_id),
                            conv.messages,
                            conv.model_id,
                            conv.id,
                            conv.title,
                            conv.reasoning_enabled,
                            conv.reasoning_effort,
                            conv.temperature,
                            conv.max_tokens,
                            conv.web_search_enabled,
                            conv.system_message,
                            conv.character,
                            conv.character_info,
                            conv.character_breakdown,
                            conv.custom_instructions
                        )
                        print(f"Synced conversation {conv.id} for user {user_id}")
                    except Exception as e:
                        print(f"Error syncing conversation: {e}")

                return final_response

        except asyncio.TimeoutError:
            return "Error: Request to AI API timed out. Please try again later."
        except Exception as e:
            error_message = f"Error communicating with AI API: {str(e)}"
            print(f"Exception in _get_ai_response: {error_message}")
            print(f"Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return error_message

    @commands.command(name="convs")
    async def ai_conversations(self, ctx: commands.Context):
        """Manage your AI conversations"""
        user_id = ctx.author.id

        # Get user's conversations
        conversations = user_conversations.get(user_id, [])

        if not conversations:
            # No conversations, create a new one
            new_conv = self.create_new_conversation(user_id)
            await ctx.reply(f"Created your first conversation: {new_conv.title}", view=ConversationManagementView(user_id))
        else:
            # Show conversation management UI
            await ctx.reply("Here are your conversations:", view=ConversationManagementView(user_id))

    @commands.command(name="chat")
    async def ai_command(self, ctx: commands.Context, *, prompt: str):
        """Get a response from the AI using your active conversation"""
        user_id = ctx.author.id

        # Get active conversation
        conv = self.get_active_conversation(user_id)
        if not conv:
            # No active conversation, create a new one
            conv = self.create_new_conversation(user_id)
            await ctx.reply(f"Created a new conversation: {conv.title}")

        # Show typing indicator
        async with ctx.typing():
            # Get AI response
            response = await self._get_ai_response(user_id, prompt, conv)

        # Check if the response is too long
        if len(response) > 1900:
            # Split into chunks or send as file
            try:
                # Create a text file with the content
                file_name = f'ai_response_{ctx.author.id}_{int(datetime.datetime.now().timestamp())}.txt'
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(response)

                # Send the file
                await ctx.reply(
                    f"Response for conversation '{conv.title}' (too long for Discord):",
                    file=discord.File(file_name)
                )

                # Clean up the file
                try:
                    os.remove(file_name)
                except:
                    pass
            except Exception as e:
                print(f"Error sending file: {e}")
                # Fall back to splitting the message
                chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                await ctx.reply(f"Response for conversation '{conv.title}' (split into {len(chunks)} parts):")
                for i, chunk in enumerate(chunks):
                    await ctx.send(f"**Part {i+1}/{len(chunks)}**\n{chunk}")
        else:
            # Send the response directly
            await ctx.reply(response)

    @commands.command(name="chatset")
    async def ai_settings(self, ctx: commands.Context, setting: str = None, *, value: str = None):
        """Update settings for your active conversation

        Examples:
        !chatset - Show current settings
        !chatset temperature 0.8 - Set temperature to 0.8
        !chatset reasoning on - Enable reasoning
        !chatset web_search on - Enable web search
        !chatset system <message> - Set system message
        !chatset character <name> - Set character name
        !chatset character_info <info> - Set character information
        !chatset character_breakdown on - Enable character breakdown
        !chatset custom_instructions <text> - Set custom instructions
        """
        user_id = ctx.author.id

        # Get active conversation
        conv = self.get_active_conversation(user_id)
        if not conv:
            # No active conversation, create a new one
            conv = self.create_new_conversation(user_id)
            await ctx.reply(f"Created a new conversation: {conv.title}")

        if setting is None:
            # Show current settings
            embed = discord.Embed(
                title=f"Settings for: {conv.title}",
                description="Current settings for your active conversation",
                color=discord.Color.blue()
            )

            # Add fields for each setting
            embed.add_field(name="Model", value=conv.model_id, inline=True)
            embed.add_field(name="Temperature", value=str(conv.temperature), inline=True)
            embed.add_field(name="Max Tokens", value=str(conv.max_tokens), inline=True)
            embed.add_field(name="Reasoning", value="Enabled" if conv.reasoning_enabled else "Disabled", inline=True)
            embed.add_field(name="Reasoning Effort", value=conv.reasoning_effort.capitalize(), inline=True)
            embed.add_field(name="Web Search", value="Enabled" if conv.web_search_enabled else "Disabled", inline=True)

            # Add character settings
            embed.add_field(name="Character", value=conv.character or "None", inline=True)
            embed.add_field(name="Character Breakdown", value="Enabled" if conv.character_breakdown else "Disabled", inline=True)

            # Show system message (truncated if too long)
            system_msg = conv.system_message
            if len(system_msg) > 1000:
                system_msg = system_msg[:997] + "..."
            embed.add_field(name="System Message", value=system_msg, inline=False)

            # Show character info if available (truncated if too long)
            if conv.character_info:
                char_info = conv.character_info
                if len(char_info) > 1000:
                    char_info = char_info[:997] + "..."
                embed.add_field(name="Character Info", value=char_info, inline=False)

            # Show custom instructions if available (truncated if too long)
            if conv.custom_instructions:
                custom_instr = conv.custom_instructions
                if len(custom_instr) > 1000:
                    custom_instr = custom_instr[:997] + "..."
                embed.add_field(name="Custom Instructions", value=custom_instr, inline=False)

            await ctx.reply(embed=embed)
            return

        # Update the specified setting
        setting = setting.lower()

        if setting == "temperature" or setting == "temp":
            if not value:
                await ctx.reply(f"Current temperature: {conv.temperature}")
                return

            try:
                temp = float(value)
                if 0 <= temp <= 2:
                    conv.temperature = temp
                    await ctx.reply(f"Temperature set to {temp}")
                else:
                    await ctx.reply("Temperature must be between 0 and 2")
            except ValueError:
                await ctx.reply("Temperature must be a number")

        elif setting == "max_tokens" or setting == "tokens":
            if not value:
                await ctx.reply(f"Current max tokens: {conv.max_tokens}")
                return

            try:
                tokens = int(value)
                if 100 <= tokens <= 4000:
                    conv.max_tokens = tokens
                    await ctx.reply(f"Max tokens set to {tokens}")
                else:
                    await ctx.reply("Max tokens must be between 100 and 4000")
            except ValueError:
                await ctx.reply("Max tokens must be a number")

        elif setting == "reasoning":
            if not value:
                await ctx.reply(f"Reasoning is currently {'enabled' if conv.reasoning_enabled else 'disabled'}")
                return

            if value.lower() in ["on", "true", "yes", "enable", "enabled"]:
                conv.reasoning_enabled = True
                await ctx.reply("Reasoning enabled")
            elif value.lower() in ["off", "false", "no", "disable", "disabled"]:
                conv.reasoning_enabled = False
                await ctx.reply("Reasoning disabled")
            else:
                await ctx.reply("Value must be 'on' or 'off'")

        elif setting == "reasoning_effort" or setting == "effort":
            if not value:
                await ctx.reply(f"Current reasoning effort: {conv.reasoning_effort}")
                return

            if value.lower() in ["low", "medium", "high"]:
                conv.reasoning_effort = value.lower()
                await ctx.reply(f"Reasoning effort set to {value.lower()}")
            else:
                await ctx.reply("Reasoning effort must be 'low', 'medium', or 'high'")

        elif setting == "web_search" or setting == "search":
            if not value:
                await ctx.reply(f"Web search is currently {'enabled' if conv.web_search_enabled else 'disabled'}")
                return

            if value.lower() in ["on", "true", "yes", "enable", "enabled"]:
                conv.web_search_enabled = True
                await ctx.reply("Web search enabled")
            elif value.lower() in ["off", "false", "no", "disable", "disabled"]:
                conv.web_search_enabled = False
                await ctx.reply("Web search disabled")
            else:
                await ctx.reply("Value must be 'on' or 'off'")

        elif setting == "model":
            if not value:
                await ctx.reply(f"Current model: {conv.model_id}")
                return

            conv.model_id = value
            await ctx.reply(f"Model set to {value}")

        elif setting == "system" or setting == "system_message":
            if not value:
                # Show current system message
                system_msg = conv.system_message
                if len(system_msg) > 1900:
                    # Send as file if too long
                    file_name = f'system_message_{ctx.author.id}.txt'
                    with open(file_name, 'w', encoding='utf-8') as f:
                        f.write(system_msg)

                    await ctx.reply("Current system message (too long for Discord):", file=discord.File(file_name))

                    # Clean up the file
                    try:
                        os.remove(file_name)
                    except:
                        pass
                else:
                    await ctx.reply(f"Current system message:\n```\n{system_msg}\n```")
                return

            # Update system message
            conv.system_message = value
            await ctx.reply(f"System message updated")

        elif setting == "character":
            if not value:
                await ctx.reply(f"Current character: {conv.character or 'None'}")
                return

            # Update character
            conv.character = value
            await ctx.reply(f"Character set to: {value}")

        elif setting == "character_info" or setting == "charinfo":
            if not value:
                # Show current character info
                if not conv.character_info:
                    await ctx.reply("No character info set.")
                    return

                char_info = conv.character_info
                if len(char_info) > 1900:
                    # Send as file if too long
                    file_name = f'character_info_{ctx.author.id}.txt'
                    with open(file_name, 'w', encoding='utf-8') as f:
                        f.write(char_info)

                    await ctx.reply("Current character info (too long for Discord):", file=discord.File(file_name))

                    # Clean up the file
                    try:
                        os.remove(file_name)
                    except:
                        pass
                else:
                    await ctx.reply(f"Current character info:\n```\n{char_info}\n```")
                return

            # Update character info
            conv.character_info = value
            await ctx.reply(f"Character info updated")

        elif setting == "character_breakdown" or setting == "breakdown":
            if not value:
                await ctx.reply(f"Character breakdown is currently {'enabled' if conv.character_breakdown else 'disabled'}")
                return

            if value.lower() in ["on", "true", "yes", "enable", "enabled"]:
                conv.character_breakdown = True
                await ctx.reply("Character breakdown enabled")
            elif value.lower() in ["off", "false", "no", "disable", "disabled"]:
                conv.character_breakdown = False
                await ctx.reply("Character breakdown disabled")
            else:
                await ctx.reply("Value must be 'on' or 'off'")

        elif setting == "custom_instructions" or setting == "instructions":
            if not value:
                # Show current custom instructions
                if not conv.custom_instructions:
                    await ctx.reply("No custom instructions set.")
                    return

                custom_instr = conv.custom_instructions
                if len(custom_instr) > 1900:
                    # Send as file if too long
                    file_name = f'custom_instructions_{ctx.author.id}.txt'
                    with open(file_name, 'w', encoding='utf-8') as f:
                        f.write(custom_instr)

                    await ctx.reply("Current custom instructions (too long for Discord):", file=discord.File(file_name))

                    # Clean up the file
                    try:
                        os.remove(file_name)
                    except:
                        pass
                else:
                    await ctx.reply(f"Current custom instructions:\n```\n{custom_instr}\n```")
                return

            # Update custom instructions
            conv.custom_instructions = value
            await ctx.reply(f"Custom instructions updated")

        elif setting == "title":
            if not value:
                await ctx.reply(f"Current title: {conv.title}")
                return

            # Update title
            conv.title = value
            await ctx.reply(f"Conversation title set to: {value}")

        else:
            await ctx.reply(f"Unknown setting: {setting}\nAvailable settings: temperature, max_tokens, reasoning, reasoning_effort, web_search, model, system, title")
            return

        # Update conversation timestamp
        conv.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        # Sync with API if available
        if SYNC_API_AVAILABLE:
            try:
                save_discord_conversation(
                    str(user_id),
                    conv.messages,
                    conv.model_id,
                    conv.id,
                    conv.title,
                    conv.reasoning_enabled,
                    conv.reasoning_effort,
                    conv.temperature,
                    conv.max_tokens,
                    conv.web_search_enabled,
                    conv.system_message,
                    conv.character,
                    conv.character_info,
                    conv.character_breakdown,
                    conv.custom_instructions
                )
                print(f"Synced conversation {conv.id} for user {user_id} after settings update")
            except Exception as e:
                print(f"Error syncing conversation after settings update: {e}")

    @commands.command(name="chatimport")
    async def ai_import(self, ctx: commands.Context):
        """Import conversations from the sync API"""
        if not SYNC_API_AVAILABLE:
            await ctx.reply("Discord sync API is not available. Sync features are disabled.")
            return

        user_id = ctx.author.id
        user_id_str = str(user_id)

        # Check if user has any synced conversations
        if user_id_str not in synced_conversations or not synced_conversations[user_id_str]:
            await ctx.reply("You don't have any synced conversations to import.")
            return

        # Count how many conversations will be imported
        synced_count = len(synced_conversations[user_id_str])

        # Create a confirmation message
        await ctx.reply(
            f"Found {synced_count} synced conversations. Do you want to import them?",
            view=ImportConfirmationView(self, user_id)
        )

    async def import_conversations(self, user_id: int):
        """Import conversations from the sync API for a user"""
        user_id_str = str(user_id)

        if user_id_str not in synced_conversations or not synced_conversations[user_id_str]:
            return "No synced conversations found."

        # Get existing conversations
        if user_id not in user_conversations:
            user_conversations[user_id] = []

        # Track imported conversations
        imported_count = 0
        updated_count = 0

        # Import each synced conversation
        for synced_conv in synced_conversations[user_id_str]:
            # Check if this conversation already exists
            existing_conv = next((c for c in user_conversations[user_id] if c.id == synced_conv.id), None)

            if existing_conv:
                # Update existing conversation if synced one is newer
                if synced_conv.updated_at > existing_conv.updated_at:
                    # Convert messages to the right format
                    messages = []
                    for msg in synced_conv.messages:
                        message = {
                            "role": msg.role,
                            "content": msg.content
                        }
                        if msg.reasoning:
                            message["reasoning"] = msg.reasoning
                        if msg.usage_data:
                            message["usage_data"] = msg.usage_data
                        messages.append(message)

                    # Update the conversation
                    existing_conv.messages = messages
                    existing_conv.title = synced_conv.title
                    existing_conv.model_id = synced_conv.model_id
                    existing_conv.updated_at = synced_conv.updated_at
                    existing_conv.reasoning_enabled = synced_conv.reasoning_enabled
                    existing_conv.reasoning_effort = synced_conv.reasoning_effort
                    existing_conv.temperature = synced_conv.temperature
                    existing_conv.max_tokens = synced_conv.max_tokens
                    existing_conv.web_search_enabled = synced_conv.web_search_enabled
                    existing_conv.system_message = synced_conv.system_message or AI_DEFAULT_SYSTEM_PROMPT

                    updated_count += 1
            else:
                # Create a new conversation
                # Convert messages to the right format
                messages = []
                for msg in synced_conv.messages:
                    message = {
                        "role": msg.role,
                        "content": msg.content
                    }
                    if msg.reasoning:
                        message["reasoning"] = msg.reasoning
                    if msg.usage_data:
                        message["usage_data"] = msg.usage_data
                    messages.append(message)

                # Create the conversation
                new_conv = Conversation(
                    id=synced_conv.id,
                    title=synced_conv.title,
                    messages=messages,
                    created_at=synced_conv.created_at,
                    updated_at=synced_conv.updated_at,
                    model_id=synced_conv.model_id,
                    system_message=synced_conv.system_message or AI_DEFAULT_SYSTEM_PROMPT,
                    reasoning_enabled=synced_conv.reasoning_enabled,
                    reasoning_effort=synced_conv.reasoning_effort,
                    temperature=synced_conv.temperature,
                    max_tokens=synced_conv.max_tokens,
                    web_search_enabled=synced_conv.web_search_enabled
                )

                # Add to user's conversations
                user_conversations[user_id].append(new_conv)
                imported_count += 1

        # Save changes
        save_user_conversations()

        # Set active conversation if user doesn't have one
        if user_id not in active_conversations or not active_conversations[user_id]:
            if user_conversations[user_id]:
                active_conversations[user_id] = user_conversations[user_id][0].id
                save_active_conversations()

        return f"Imported {imported_count} new conversations and updated {updated_count} existing conversations."

    @app_commands.command(name="chat", description="Get a response from the AI using your active conversation")
    @app_commands.describe(prompt="Your message to the AI")
    async def ai_slash(self, interaction: discord.Interaction, prompt: str):
        """Slash command to get a response from the AI"""
        user_id = interaction.user.id

        # Get active conversation
        conv = self.get_active_conversation(user_id)
        if not conv:
            # No active conversation, create a new one
            conv = self.create_new_conversation(user_id)

        # Defer the response since API calls can take time
        await interaction.response.defer(thinking=True)

        # Get AI response
        response = await self._get_ai_response(user_id, prompt, conv)

        # Check if the response is too long
        if len(response) > 3900:  # Discord's limit for interactions is 4000, use 3900 to be safe
            try:
                # Create a text file with the content
                file_name = f'ai_response_{interaction.user.id}_{int(datetime.datetime.now().timestamp())}.txt'
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(response)

                # Send the file
                await interaction.followup.send(
                    f"Response for conversation '{conv.title}' (too long for Discord):",
                    file=discord.File(file_name)
                )

                # Clean up the file
                try:
                    os.remove(file_name)
                except:
                    pass
            except Exception as e:
                print(f"Error sending file: {e}")
                # Fall back to splitting the message
                chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                await interaction.followup.send(f"Response for conversation '{conv.title}' (split into {len(chunks)} parts):")
                for i, chunk in enumerate(chunks):
                    await interaction.followup.send(f"**Part {i+1}/{len(chunks)}**\n{chunk}")
        else:
            # Send the response directly
            await interaction.followup.send(response)

async def setup(bot):
    await bot.add_cog(MultiConversationCog(bot))

# UI Components for conversation management
class ConversationSelectMenu(ui.Select):
    def __init__(self, user_id: int, conversations: List[Conversation], current_id: str = None):
        self.user_id = user_id
        self.conversations = conversations

        # Create options for each conversation
        options = []
        for conv in conversations:
            # Truncate title if too long
            title = conv.title
            if len(title) > 100:
                title = title[:97] + "..."

            # Create option
            option = discord.SelectOption(
                label=title,
                value=conv.id,
                description=f"Created: {conv.created_at.strftime('%Y-%m-%d')}",
                default=(conv.id == current_id)
            )
            options.append(option)

        # Add option to create new conversation
        options.append(discord.SelectOption(
            label="➕ New Conversation",
            value="new",
            description="Start a new conversation"
        ))

        super().__init__(placeholder="Select a conversation", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        # Get the selected value
        selected_id = self.values[0]

        if selected_id == "new":
            # Get the MultiConversationCog instance
            cog = None
            for c in interaction.client.cogs.values():
                if isinstance(c, MultiConversationCog):
                    cog = c
                    break

            if cog:
                # Use the cog's method to create a new conversation with user settings
                new_conv = cog.create_new_conversation(self.user_id, "New Conversation")
            else:
                # Fallback to creating a conversation directly
                # Check if we have synced settings for this user
                synced_settings = None
                if SYNC_API_AVAILABLE:
                    str_user_id = str(self.user_id)
                    if str_user_id in synced_user_settings:
                        synced_settings = synced_user_settings[str_user_id]

                # Create a new conversation with default settings
                new_conv = Conversation(title="New Conversation")

                # Apply synced settings if available
                if synced_settings:
                    # Apply model settings
                    if hasattr(synced_settings, 'model_id') and synced_settings.model_id:
                        new_conv.model_id = synced_settings.model_id

                    # Apply temperature settings
                    if hasattr(synced_settings, 'temperature'):
                        new_conv.temperature = synced_settings.temperature

                    # Apply max tokens settings
                    if hasattr(synced_settings, 'max_tokens'):
                        new_conv.max_tokens = synced_settings.max_tokens

                    # Apply reasoning settings
                    if hasattr(synced_settings, 'reasoning_enabled'):
                        new_conv.reasoning_enabled = synced_settings.reasoning_enabled

                    if hasattr(synced_settings, 'reasoning_effort'):
                        new_conv.reasoning_effort = synced_settings.reasoning_effort

                    # Apply web search settings
                    if hasattr(synced_settings, 'web_search_enabled'):
                        new_conv.web_search_enabled = synced_settings.web_search_enabled

                    # Apply system message
                    if hasattr(synced_settings, 'system_message') and synced_settings.system_message:
                        new_conv.system_message = synced_settings.system_message

                    # Apply character settings
                    if hasattr(synced_settings, 'character') and synced_settings.character:
                        new_conv.character = synced_settings.character

                    if hasattr(synced_settings, 'character_info') and synced_settings.character_info:
                        new_conv.character_info = synced_settings.character_info

                    if hasattr(synced_settings, 'character_breakdown'):
                        new_conv.character_breakdown = synced_settings.character_breakdown

                    if hasattr(synced_settings, 'custom_instructions') and synced_settings.custom_instructions:
                        new_conv.custom_instructions = synced_settings.custom_instructions

                # Add to user's conversations
                if self.user_id not in user_conversations:
                    user_conversations[self.user_id] = []
                user_conversations[self.user_id].append(new_conv)

                # Set as active conversation
                active_conversations[self.user_id] = new_conv.id

                # Save changes
                save_user_conversations()
                save_active_conversations()

            await interaction.response.edit_message(
                content=f"Created new conversation: {new_conv.title}",
                view=ConversationManagementView(self.user_id)
            )
        else:
            # Set the selected conversation as active
            active_conversations[self.user_id] = selected_id
            save_active_conversations()

            # Find the selected conversation
            selected_conv = next((c for c in self.conversations if c.id == selected_id), None)
            if selected_conv:
                await interaction.response.edit_message(
                    content=f"Switched to conversation: {selected_conv.title}",
                    view=ConversationManagementView(self.user_id)
                )
            else:
                await interaction.response.edit_message(content="Error: Conversation not found")

class ConversationManagementView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id

        # Get user's conversations
        conversations = user_conversations.get(user_id, [])

        # Get active conversation ID
        active_id = active_conversations.get(user_id)

        # Add conversation select menu
        self.add_item(ConversationSelectMenu(user_id, conversations, active_id))

    @ui.button(label="Settings", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def settings_button(self, interaction: discord.Interaction, button: ui.Button):
        # Get active conversation
        active_id = active_conversations.get(self.user_id)
        if not active_id:
            await interaction.response.send_message("No active conversation. Please select or create one first.", ephemeral=True)
            return

        # Find the active conversation
        conversations = user_conversations.get(self.user_id, [])
        active_conv = next((c for c in conversations if c.id == active_id), None)

        if not active_conv:
            await interaction.response.send_message("Error: Active conversation not found", ephemeral=True)
            return

        # Show settings for the active conversation
        embed = discord.Embed(
            title=f"Settings for: {active_conv.title}",
            description="Adjust settings for this conversation",
            color=discord.Color.blue()
        )

        # Add fields for each setting
        embed.add_field(name="Model", value=active_conv.model_id, inline=True)
        embed.add_field(name="Temperature", value=str(active_conv.temperature), inline=True)
        embed.add_field(name="Max Tokens", value=str(active_conv.max_tokens), inline=True)
        embed.add_field(name="Reasoning", value="Enabled" if active_conv.reasoning_enabled else "Disabled", inline=True)
        embed.add_field(name="Reasoning Effort", value=active_conv.reasoning_effort.capitalize(), inline=True)
        embed.add_field(name="Web Search", value="Enabled" if active_conv.web_search_enabled else "Disabled", inline=True)

        # Add character settings
        embed.add_field(name="Character", value=active_conv.character or "None", inline=True)
        embed.add_field(name="Character Breakdown", value="Enabled" if active_conv.character_breakdown else "Disabled", inline=True)

        # Show system message (truncated if too long)
        system_msg = active_conv.system_message
        if len(system_msg) > 1000:
            system_msg = system_msg[:997] + "..."
        embed.add_field(name="System Message", value=system_msg, inline=False)

        # Show character info if available (truncated if too long)
        if active_conv.character_info:
            char_info = active_conv.character_info
            if len(char_info) > 1000:
                char_info = char_info[:997] + "..."
            embed.add_field(name="Character Info", value=char_info, inline=False)

        # Show custom instructions if available (truncated if too long)
        if active_conv.custom_instructions:
            custom_instr = active_conv.custom_instructions
            if len(custom_instr) > 1000:
                custom_instr = custom_instr[:997] + "..."
            embed.add_field(name="Custom Instructions", value=custom_instr, inline=False)

        await interaction.response.send_message(embed=embed, view=ConversationSettingsView(self.user_id, active_id), ephemeral=True)

    @ui.button(label="Rename", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def rename_button(self, interaction: discord.Interaction, button: ui.Button):
        # Get active conversation
        active_id = active_conversations.get(self.user_id)
        if not active_id:
            await interaction.response.send_message("No active conversation. Please select or create one first.", ephemeral=True)
            return

        # Show rename modal
        await interaction.response.send_modal(RenameConversationModal(self.user_id, active_id))

    @ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: ui.Button):
        # Get active conversation
        active_id = active_conversations.get(self.user_id)
        if not active_id:
            await interaction.response.send_message("No active conversation. Please select or create one first.", ephemeral=True)
            return

        # Find the active conversation
        conversations = user_conversations.get(self.user_id, [])
        active_conv = next((c for c in conversations if c.id == active_id), None)

        if not active_conv:
            await interaction.response.send_message("Error: Active conversation not found", ephemeral=True)
            return

        # Confirm deletion
        await interaction.response.send_message(
            f"Are you sure you want to delete the conversation '{active_conv.title}'?",
            view=DeleteConfirmationView(self.user_id, active_id),
            ephemeral=True
        )

class RenameConversationModal(ui.Modal, title="Rename Conversation"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add title input
        self.title_input = ui.TextInput(
            label="New Title",
            placeholder="Enter a new title for this conversation",
            default=self.conversation.title if self.conversation else "",
            required=True,
            max_length=100
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Update the conversation title
        self.conversation.title = self.title_input.value
        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        await interaction.response.send_message(
            f"Renamed conversation to: {self.conversation.title}",
            view=ConversationManagementView(self.user_id),
            ephemeral=True
        )

class DeleteConfirmationView(ui.View):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__(timeout=60)  # 1 minute timeout
        self.user_id = user_id
        self.conversation_id = conversation_id

    @ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        # Get user's conversations
        conversations = user_conversations.get(self.user_id, [])

        # Find the conversation to delete
        conversation = next((c for c in conversations if c.id == self.conversation_id), None)
        if not conversation:
            await interaction.response.edit_message(content="Error: Conversation not found", view=None)
            return

        # Remove the conversation
        user_conversations[self.user_id] = [c for c in conversations if c.id != self.conversation_id]

        # If this was the active conversation, set a new active conversation
        if active_conversations.get(self.user_id) == self.conversation_id:
            if user_conversations[self.user_id]:
                # Set the first remaining conversation as active
                active_conversations[self.user_id] = user_conversations[self.user_id][0].id
            else:
                # No conversations left, remove active conversation
                if self.user_id in active_conversations:
                    del active_conversations[self.user_id]

        # Save changes
        save_user_conversations()
        save_active_conversations()

        await interaction.response.edit_message(
            content=f"Deleted conversation: {conversation.title}",
            view=ConversationManagementView(self.user_id) if user_conversations.get(self.user_id) else None
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Deletion cancelled", view=None)

class ConversationSettingsView(ui.View):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

    @ui.button(label="Edit System Message", style=discord.ButtonStyle.primary, row=0)
    async def system_message_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Show system message modal
        await interaction.response.send_modal(SystemMessageModal(self.user_id, self.conversation_id))

    @ui.button(label="Set Character", style=discord.ButtonStyle.primary, row=0)
    async def character_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Show character modal
        await interaction.response.send_modal(CharacterModal(self.user_id, self.conversation_id))

    @ui.button(label="Character Info", style=discord.ButtonStyle.primary, row=0)
    async def character_info_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Show character info modal
        await interaction.response.send_modal(CharacterInfoModal(self.user_id, self.conversation_id))

    @ui.button(label="Custom Instructions", style=discord.ButtonStyle.primary, row=1)
    async def custom_instructions_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Show custom instructions modal
        await interaction.response.send_modal(CustomInstructionsModal(self.user_id, self.conversation_id))

    @ui.button(label="Toggle Reasoning", style=discord.ButtonStyle.secondary, row=0)
    async def reasoning_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Toggle reasoning
        self.conversation.reasoning_enabled = not self.conversation.reasoning_enabled
        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        await interaction.response.send_message(
            f"Reasoning {'enabled' if self.conversation.reasoning_enabled else 'disabled'} for this conversation",
            ephemeral=True
        )

    @ui.button(label="Toggle Web Search", style=discord.ButtonStyle.secondary, row=0)
    async def web_search_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Toggle web search
        self.conversation.web_search_enabled = not self.conversation.web_search_enabled
        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        await interaction.response.send_message(
            f"Web search {'enabled' if self.conversation.web_search_enabled else 'disabled'} for this conversation",
            ephemeral=True
        )

    @ui.button(label="Set Temperature", style=discord.ButtonStyle.secondary, row=1)
    async def temperature_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Show temperature modal
        await interaction.response.send_modal(TemperatureModal(self.user_id, self.conversation_id))

    @ui.button(label="Set Max Tokens", style=discord.ButtonStyle.secondary, row=1)
    async def max_tokens_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Show max tokens modal
        await interaction.response.send_modal(MaxTokensModal(self.user_id, self.conversation_id))

    @ui.button(label="Set Model", style=discord.ButtonStyle.secondary, row=1)
    async def model_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Show model modal
        await interaction.response.send_modal(ModelModal(self.user_id, self.conversation_id))

class SystemMessageModal(ui.Modal, title="Edit System Message"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add system message input
        self.system_message_input = ui.TextInput(
            label="System Message",
            placeholder="Enter a system message for this conversation",
            default=self.conversation.system_message if self.conversation else AI_DEFAULT_SYSTEM_PROMPT,
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=4000
        )
        self.add_item(self.system_message_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Update the conversation system message
        self.conversation.system_message = self.system_message_input.value
        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        await interaction.response.send_message(
            "System message updated",
            ephemeral=True
        )

class TemperatureModal(ui.Modal, title="Set Temperature"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add temperature input
        self.temperature_input = ui.TextInput(
            label="Temperature (0.0 - 2.0)",
            placeholder="Enter a value between 0.0 and 2.0",
            default=str(self.conversation.temperature) if self.conversation else str(AI_TEMPERATURE),
            required=True,
            max_length=4
        )
        self.add_item(self.temperature_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        try:
            # Parse and validate temperature
            temperature = float(self.temperature_input.value)
            if temperature < 0.0 or temperature > 2.0:
                await interaction.response.send_message("Temperature must be between 0.0 and 2.0", ephemeral=True)
                return

            # Update the conversation temperature
            self.conversation.temperature = temperature
            self.conversation.updated_at = datetime.datetime.now()

            # Save changes
            save_user_conversations()

            await interaction.response.send_message(
                f"Temperature set to {temperature}",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message("Invalid temperature value. Please enter a number between 0.0 and 2.0", ephemeral=True)

class MaxTokensModal(ui.Modal, title="Set Max Tokens"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add max tokens input
        self.max_tokens_input = ui.TextInput(
            label="Max Tokens (100 - 4000)",
            placeholder="Enter a value between 100 and 4000",
            default=str(self.conversation.max_tokens) if self.conversation else str(AI_MAX_TOKENS),
            required=True,
            max_length=4
        )
        self.add_item(self.max_tokens_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        try:
            # Parse and validate max tokens
            max_tokens = int(self.max_tokens_input.value)
            if max_tokens < 100 or max_tokens > 4000:
                await interaction.response.send_message("Max tokens must be between 100 and 4000", ephemeral=True)
                return

            # Update the conversation max tokens
            self.conversation.max_tokens = max_tokens
            self.conversation.updated_at = datetime.datetime.now()

            # Save changes
            save_user_conversations()

            await interaction.response.send_message(
                f"Max tokens set to {max_tokens}",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message("Invalid max tokens value. Please enter a number between 100 and 4000", ephemeral=True)

class ModelModal(ui.Modal, title="Set Model"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add model input
        self.model_input = ui.TextInput(
            label="Model",
            placeholder="Enter a model name (e.g., gpt-3.5-turbo, gpt-4)",
            default=self.conversation.model_id if self.conversation else AI_DEFAULT_MODEL,
            required=True,
            max_length=50
        )
        self.add_item(self.model_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Update the conversation model
        self.conversation.model_id = self.model_input.value
        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        await interaction.response.send_message(
            f"Model set to {self.conversation.model_id}",
            ephemeral=True
        )

class CharacterModal(ui.Modal, title="Set Character"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add character input
        self.character_input = ui.TextInput(
            label="Character Name",
            placeholder="Enter a character name (e.g., Hatsune Miku)",
            default=self.conversation.character if self.conversation else "",
            required=False,
            max_length=100
        )
        self.add_item(self.character_input)

        # Add character breakdown toggle
        self.breakdown_input = ui.TextInput(
            label="Character Breakdown",
            placeholder="Type 'yes' to enable, 'no' to disable",
            default="yes" if self.conversation and self.conversation.character_breakdown else "no",
            required=False,
            max_length=3
        )
        self.add_item(self.breakdown_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Update the conversation character
        self.conversation.character = self.character_input.value

        # Update character breakdown setting
        breakdown_value = self.breakdown_input.value.lower()
        if breakdown_value in ["yes", "y", "true", "on", "1"]:
            self.conversation.character_breakdown = True
        elif breakdown_value in ["no", "n", "false", "off", "0"]:
            self.conversation.character_breakdown = False

        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        # Prepare response message
        if self.conversation.character:
            message = f"Character set to: {self.conversation.character}\n"
        else:
            message = "Character cleared.\n"

        message += f"Character breakdown: {'Enabled' if self.conversation.character_breakdown else 'Disabled'}"

        await interaction.response.send_message(message, ephemeral=True)

class CharacterInfoModal(ui.Modal, title="Character Information"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add character info input
        self.character_info_input = ui.TextInput(
            label="Character Information",
            placeholder="Enter information about the character being roleplayed",
            default=self.conversation.character_info if self.conversation else "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=4000
        )
        self.add_item(self.character_info_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Update the conversation character info
        self.conversation.character_info = self.character_info_input.value
        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        await interaction.response.send_message("Character information updated.", ephemeral=True)

class CustomInstructionsModal(ui.Modal, title="Custom Instructions"):
    def __init__(self, user_id: int, conversation_id: str):
        super().__init__()
        self.user_id = user_id
        self.conversation_id = conversation_id

        # Find the conversation
        conversations = user_conversations.get(user_id, [])
        self.conversation = next((c for c in conversations if c.id == conversation_id), None)

        # Add custom instructions input
        self.custom_instructions_input = ui.TextInput(
            label="Custom Instructions",
            placeholder="Enter custom instructions for the AI to follow",
            default=self.conversation.custom_instructions if self.conversation else "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=4000
        )
        self.add_item(self.custom_instructions_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.conversation:
            await interaction.response.send_message("Error: Conversation not found", ephemeral=True)
            return

        # Update the conversation custom instructions
        self.conversation.custom_instructions = self.custom_instructions_input.value
        self.conversation.updated_at = datetime.datetime.now()

        # Save changes
        save_user_conversations()

        await interaction.response.send_message("Custom instructions updated.", ephemeral=True)

class ImportConfirmationView(ui.View):
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=60)  # 1 minute timeout
        self.cog = cog
        self.user_id = user_id

    @ui.button(label="Yes, Import", style=discord.ButtonStyle.primary)
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        # Defer response since this might take a while
        await interaction.response.defer(thinking=True)

        # Import conversations
        result = await self.cog.import_conversations(self.user_id)

        # Send result
        await interaction.followup.send(result)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Import cancelled", view=None)
