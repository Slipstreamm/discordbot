import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import datetime
import asyncio
from typing import Dict, List, Optional, Any, Union

# Import the API integration
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api_integration import (
    init_api_client,
    set_token,
    get_user_conversations,
    save_discord_conversation,
    get_user_settings,
    update_user_settings,
    convert_discord_settings_to_api,
    convert_api_settings_to_discord
)

# Constants
HISTORY_FILE = "conversation_history.json"
USER_SETTINGS_FILE = "user_settings.json"
ACTIVE_CONVOS_FILE = "active_convos.json" # New file for active convo IDs
API_URL = os.getenv("API_URL", "https://slipstreamm.dev/api")

# Initialize the API client
api_client = init_api_client(API_URL)

class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conversation_history = {}
        self.user_settings = {}
        self.active_conversation_ids = {} # New dict to track active convo ID per user

        # Load conversation history, user settings, and active convo IDs
        self.load_conversation_history()
        self.load_user_settings()
        self.load_active_conversation_ids()

    def load_conversation_history(self):
        """Load conversation history from JSON file"""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    # Convert string keys (from JSON) back to integers
                    data = json.load(f)
                    self.conversation_history = {int(k): v for k, v in data.items()}
                print(f"Loaded conversation history for {len(self.conversation_history)} users")
            except Exception as e:
                print(f"Error loading conversation history: {e}")

    def save_conversation_history(self):
        """Save conversation history to JSON file"""
        try:
            # Convert int keys to strings for JSON serialization
            serializable_history = {str(k): v for k, v in self.conversation_history.items()}
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable_history, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving conversation history: {e}")

    def load_user_settings(self):
        """Load user settings from JSON file"""
        if os.path.exists(USER_SETTINGS_FILE):
            try:
                with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    # Convert string keys (from JSON) back to integers
                    data = json.load(f)
                    self.user_settings = {int(k): v for k, v in data.items()}
                print(f"Loaded settings for {len(self.user_settings)} users")
            except Exception as e:
                print(f"Error loading user settings: {e}")

    def save_user_settings(self):
        """Save user settings to JSON file"""
        try:
            # Convert int keys to strings for JSON serialization
            serializable_settings = {str(k): v for k, v in self.user_settings.items()}
            with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable_settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving user settings: {e}")

    def load_active_conversation_ids(self):
        """Load active conversation IDs from JSON file"""
        if os.path.exists(ACTIVE_CONVOS_FILE):
            try:
                with open(ACTIVE_CONVOS_FILE, "r", encoding="utf-8") as f:
                    # Convert string keys (from JSON) back to integers
                    data = json.load(f)
                    self.active_conversation_ids = {int(k): v for k, v in data.items()}
                print(f"Loaded active conversation IDs for {len(self.active_conversation_ids)} users")
            except Exception as e:
                print(f"Error loading active conversation IDs: {e}")

    def save_active_conversation_ids(self):
        """Save active conversation IDs to JSON file"""
        try:
            # Convert int keys to strings for JSON serialization
            serializable_ids = {str(k): v for k, v in self.active_conversation_ids.items()}
            with open(ACTIVE_CONVOS_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable_ids, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving active conversation IDs: {e}")

    def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Get settings for a user with defaults"""
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {
                "model": "openai/gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 1000,
                "show_reasoning": False,
                "reasoning_effort": "medium",
                "web_search_enabled": False,
                "system_prompt": None,
                "character": None,
                "character_info": None,
                "character_breakdown": False,
                "custom_instructions": None
            }

        return self.user_settings[user_id]

    async def sync_settings_with_api(self, user_id: int, token: str):
        """Sync user settings with the API"""
        try:
            # Get current settings
            discord_settings = self.get_user_settings(user_id)

            # Convert to API format
            api_settings = convert_discord_settings_to_api(discord_settings)

            # Update settings in the API
            updated_settings = await update_user_settings(str(user_id), token, api_settings)

            if updated_settings:
                print(f"Successfully synced settings for user {user_id} with API")
                return True
            else:
                print(f"Failed to sync settings for user {user_id} with API")
                return False
        except Exception as e:
            print(f"Error syncing settings for user {user_id} with API: {e}")
            return False

    async def fetch_settings_from_api(self, user_id: int, token: str):
        """Fetch user settings from the API"""
        try:
            # Get settings from the API
            api_settings = await get_user_settings(str(user_id), token)

            if api_settings:
                # Convert to Discord format
                discord_settings = convert_api_settings_to_discord(api_settings)

                # Update local settings
                self.user_settings[user_id] = discord_settings

                # Save to file
                self.save_user_settings()

                print(f"Successfully fetched settings for user {user_id} from API")
                return True
            else:
                print(f"Failed to fetch settings for user {user_id} from API")
                return False
        except Exception as e:
            print(f"Error fetching settings for user {user_id} from API: {e}")
            return False

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.__class__.__name__} Cog ready")

        # Try to fetch settings from the API for all users
        await self.fetch_all_settings_from_api()

    # Helper method to fetch settings from the API for all users
    async def fetch_all_settings_from_api(self):
        """Fetch settings from the API for all users"""
        print("Attempting to fetch settings from API for all users...")

        # Get all user IDs from the user_settings dictionary
        user_ids = list(self.user_settings.keys())

        if not user_ids:
            print("No users found in local settings")
            return

        print(f"Found {len(user_ids)} users in local settings")

        # Try to fetch settings for each user
        for user_id in user_ids:
            try:
                # Try to get the user's Discord token for API authentication
                token = await self.get_discord_token(user_id)

                if token:
                    # Try to fetch settings from the API
                    success = await self.fetch_settings_from_api(user_id, token)
                    if success:
                        print(f"Successfully fetched settings from API for user {user_id}")
                    else:
                        print(f"Failed to fetch settings from API for user {user_id}")
                else:
                    print(f"No token available for user {user_id}")
            except Exception as e:
                print(f"Error fetching settings from API for user {user_id}: {e}")

    # Helper method to get Discord token for API authentication
    async def get_discord_token(self, user_id: int) -> Optional[str]:
        """Get the Discord token for a user"""
        # Import the OAuth module
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import discord_oauth

        # Try to get the token from the OAuth system
        token = await discord_oauth.get_token(str(user_id))
        if token:
            print(f"Using OAuth token for user {user_id}")
            return token

        # For backward compatibility, check environment variables
        user_token_var = f"DISCORD_TOKEN_{user_id}"
        user_token = os.getenv(user_token_var)
        if user_token:
            print(f"Using user-specific token from environment for user {user_id}")
            return user_token

        # Then check if we have a general test token
        test_token = os.getenv("DISCORD_TEST_TOKEN")
        if test_token:
            print(f"Using general test token for user {user_id}")
            return test_token

        # Try to load from a token file if it exists (legacy method)
        token_file = os.path.join(os.path.dirname(__file__), "..", "tokens", f"{user_id}.token")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    token = f.read().strip()
                    if token:
                        print(f"Loaded token from legacy file for user {user_id}")
                        return token
            except Exception as e:
                print(f"Error loading token from legacy file for user {user_id}: {e}")

        # No token found
        print(f"No token found for user {user_id}")
        return None

    @commands.command(name="aiset")
    async def set_ai_settings(self, ctx, setting: str = None, *, value: str = None):
        """Set AI settings for the user"""
        user_id = ctx.author.id

        # Try to get the user's Discord token for API authentication
        token = await self.get_discord_token(user_id)

        # Try to fetch the latest settings from the API if we have a token
        api_settings_fetched = False
        if token:
            try:
                print(f"Fetching settings from API for user {user_id}")
                api_settings_fetched = await self.fetch_settings_from_api(user_id, token)
                if api_settings_fetched:
                    print(f"Successfully fetched settings from API for user {user_id}")
                else:
                    print(f"Failed to fetch settings from API for user {user_id}, using local settings")
            except Exception as e:
                print(f"Error fetching settings from API: {e}")

        # Get the settings (either from API or local storage)
        settings = self.get_user_settings(user_id)

        if setting is None:
            # Display current settings
            settings_str = "Current AI settings:\n"
            settings_str += f"Model: `{settings.get('model', 'openai/gpt-3.5-turbo')}`\n"
            settings_str += f"Temperature: `{settings.get('temperature', 0.7)}`\n"
            settings_str += f"Max Tokens: `{settings.get('max_tokens', 1000)}`\n"
            settings_str += f"Show Reasoning: `{settings.get('show_reasoning', False)}`\n"
            settings_str += f"Reasoning Effort: `{settings.get('reasoning_effort', 'medium')}`\n"
            settings_str += f"Web Search: `{settings.get('web_search_enabled', False)}`\n"

            # Character settings
            character = settings.get('character')
            character_info = settings.get('character_info')
            character_breakdown = settings.get('character_breakdown', False)
            custom_instructions = settings.get('custom_instructions')

            if character:
                settings_str += f"Character: `{character}`\n"
            if character_info:
                settings_str += f"Character Info: `{character_info[:50]}...`\n"
            settings_str += f"Character Breakdown: `{character_breakdown}`\n"
            if custom_instructions:
                settings_str += f"Custom Instructions: `{custom_instructions[:50]}...`\n"

            # System prompt
            system_prompt = settings.get('system_prompt')
            if system_prompt:
                settings_str += f"System Prompt: `{system_prompt[:50]}...`\n"

            # Add information about API sync status
            if api_settings_fetched:
                settings_str += "\n*Settings were synced with the API*\n"
            elif token:
                settings_str += "\n*Warning: Failed to sync settings with the API*\n"
            else:
                settings_str += "\n*Warning: No Discord token available for API sync*\n"

            await ctx.send(settings_str)
            return

        # Update the specified setting
        setting = setting.lower()

        if setting == "model":
            if value:
                settings["model"] = value
                await ctx.send(f"Model set to `{value}`")
            else:
                await ctx.send(f"Current model: `{settings.get('model', 'openai/gpt-3.5-turbo')}`")

        elif setting == "temperature":
            if value:
                try:
                    temp = float(value)
                    if 0 <= temp <= 2:
                        settings["temperature"] = temp
                        await ctx.send(f"Temperature set to `{temp}`")
                    else:
                        await ctx.send("Temperature must be between 0 and 2")
                except ValueError:
                    await ctx.send("Temperature must be a number")
            else:
                await ctx.send(f"Current temperature: `{settings.get('temperature', 0.7)}`")

        elif setting == "max_tokens" or setting == "maxtokens":
            if value:
                try:
                    tokens = int(value)
                    if tokens > 0:
                        settings["max_tokens"] = tokens
                        await ctx.send(f"Max tokens set to `{tokens}`")
                    else:
                        await ctx.send("Max tokens must be greater than 0")
                except ValueError:
                    await ctx.send("Max tokens must be a number")
            else:
                await ctx.send(f"Current max tokens: `{settings.get('max_tokens', 1000)}`")

        elif setting == "reasoning" or setting == "show_reasoning":
            if value and value.lower() in ("true", "yes", "on", "1"):
                settings["show_reasoning"] = True
                await ctx.send("Reasoning enabled")
            elif value and value.lower() in ("false", "no", "off", "0"):
                settings["show_reasoning"] = False
                await ctx.send("Reasoning disabled")
            else:
                await ctx.send(f"Current reasoning setting: `{settings.get('show_reasoning', False)}`")

        elif setting == "reasoning_effort":
            if value and value.lower() in ("low", "medium", "high"):
                settings["reasoning_effort"] = value.lower()
                await ctx.send(f"Reasoning effort set to `{value.lower()}`")
            else:
                await ctx.send(f"Current reasoning effort: `{settings.get('reasoning_effort', 'medium')}`")

        elif setting == "websearch" or setting == "web_search":
            if value and value.lower() in ("true", "yes", "on", "1"):
                settings["web_search_enabled"] = True
                await ctx.send("Web search enabled")
            elif value and value.lower() in ("false", "no", "off", "0"):
                settings["web_search_enabled"] = False
                await ctx.send("Web search disabled")
            else:
                await ctx.send(f"Current web search setting: `{settings.get('web_search_enabled', False)}`")

        elif setting == "system" or setting == "system_prompt":
            if value:
                settings["system_prompt"] = value
                await ctx.send(f"System prompt set to: `{value[:50]}...`")
            else:
                system_prompt = settings.get('system_prompt')
                if system_prompt:
                    await ctx.send(f"Current system prompt: `{system_prompt[:50]}...`")
                else:
                    await ctx.send("No system prompt set")

        elif setting == "character":
            if value:
                settings["character"] = value
                await ctx.send(f"Character set to: `{value}`")
            else:
                character = settings.get('character')
                if character:
                    await ctx.send(f"Current character: `{character}`")
                else:
                    await ctx.send("No character set")

        elif setting == "character_info":
            if value:
                settings["character_info"] = value
                await ctx.send(f"Character info set to: `{value[:50]}...`")
            else:
                character_info = settings.get('character_info')
                if character_info:
                    await ctx.send(f"Current character info: `{character_info[:50]}...`")
                else:
                    await ctx.send("No character info set")

        elif setting == "character_breakdown":
            if value and value.lower() in ("true", "yes", "on", "1"):
                settings["character_breakdown"] = True
                await ctx.send("Character breakdown enabled")
            elif value and value.lower() in ("false", "no", "off", "0"):
                settings["character_breakdown"] = False
                await ctx.send("Character breakdown disabled")
            else:
                await ctx.send(f"Current character breakdown setting: `{settings.get('character_breakdown', False)}`")

        elif setting == "custom_instructions":
            if value:
                settings["custom_instructions"] = value
                await ctx.send(f"Custom instructions set to: `{value[:50]}...`")
            else:
                custom_instructions = settings.get('custom_instructions')
                if custom_instructions:
                    await ctx.send(f"Current custom instructions: `{custom_instructions[:50]}...`")
                else:
                    await ctx.send("No custom instructions set")

        else:
            await ctx.send(f"Unknown setting: {setting}")
            return

        # Save the updated settings
        self.save_user_settings()

        # Sync settings with the API if the user has a token
        token = await self.get_discord_token(user_id)
        if token:
            try:
                # Convert to API format
                api_settings = convert_discord_settings_to_api(settings)

                # Update settings in the API
                updated_settings = await update_user_settings(str(user_id), token, api_settings)

                if updated_settings:
                    print(f"Successfully synced updated settings for user {user_id} with API")
                    await ctx.send("*Settings updated and synced with the API*")
                else:
                    print(f"Failed to sync updated settings for user {user_id} with API")
                    await ctx.send("*Settings updated locally but failed to sync with the API*")
            except Exception as e:
                print(f"Error syncing updated settings for user {user_id} with API: {e}")
                await ctx.send("*Settings updated locally but an error occurred during API sync*")
        else:
            print(f"Settings updated for user {user_id}, but no token available for API sync")
            await ctx.send("*Settings updated locally. No Discord token available for API sync*")

    @commands.command(name="ai")
    async def ai_command(self, ctx, *, prompt: str = None):
        """Interact with the AI"""
        user_id = ctx.author.id

        # Initialize conversation history for this user if it doesn't exist
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []

        # Try to get the user's Discord token for API authentication
        token = await self.get_discord_token(user_id)

        # Try to fetch the latest settings from the API if we have a token
        if token:
            try:
                await self.fetch_settings_from_api(user_id, token)
            except Exception as e:
                print(f"Error fetching settings from API before AI command: {e}")

        # Get user settings
        settings = self.get_user_settings(user_id)

        if prompt is None:
            await ctx.send("Please provide a prompt for the AI")
            return

        # Add user message to conversation history
        self.conversation_history[user_id].append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.datetime.now().isoformat()
        })

        # In a real implementation, you would call your AI service here
        # For this example, we'll just echo the prompt
        response = f"{prompt}"

        # Add AI response to conversation history
        self.conversation_history[user_id].append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.datetime.now().isoformat()
        })

        # Save conversation history
        self.save_conversation_history()

        # Send the response
        await ctx.send(response)

        # Sync conversation with the API if the user has a token
        token = await self.get_discord_token(user_id)
        if token:
            try:
                # Convert messages to API format
                messages = self.conversation_history[user_id]

                # Get settings for the conversation
                settings = self.get_user_settings(user_id)
                # Get the current active conversation ID for this user
                current_conversation_id = self.active_conversation_ids.get(user_id)

                # Save the conversation to the API, passing the current ID
                saved_conversation = await save_discord_conversation( # Assign return value
                    user_id=str(user_id),
                    token=token,
                    conversation_id=current_conversation_id, # Pass the current ID
                    messages=messages,
                    model_id=settings.get("model", "openai/gpt-3.5-turbo"),
                    temperature=settings.get("temperature", 0.7),
                    max_tokens=settings.get("max_tokens", 1000),
                    reasoning_enabled=settings.get("show_reasoning", False),
                    reasoning_effort=settings.get("reasoning_effort", "medium"),
                    web_search_enabled=settings.get("web_search_enabled", False),
                    system_message=settings.get("system_prompt")
                )

                # Check the result of the API call
                if saved_conversation:
                    # Use the ID from the returned object if available
                    conv_id = getattr(saved_conversation, 'id', None)
                    print(f"Successfully synced conversation {conv_id} for user {user_id} with API")
                    # Update the active conversation ID if we got one back
                    if conv_id:
                        self.active_conversation_ids[user_id] = conv_id
                        self.save_active_conversation_ids() # Save the updated ID
                else:
                    # Error message is already printed within save_discord_conversation
                    print(f"Failed to sync conversation for user {user_id} with API.")
                    # Optionally send a message to the user/channel?
                    # await ctx.send("⚠️ Failed to sync this conversation with the central server.")
            except Exception as e:
                print(f"Error during conversation sync process for user {user_id}: {e}")
        else:
            print(f"Conversation updated locally for user {user_id}, but no token available for API sync")

    @commands.command(name="aiclear")
    async def clear_history(self, ctx):
        """Clear conversation history for the user"""
        user_id = ctx.author.id

        if user_id in self.conversation_history or user_id in self.active_conversation_ids:
            # Clear local history
            if user_id in self.conversation_history:
                self.conversation_history[user_id] = []
                self.save_conversation_history()
            # Clear active conversation ID
            if user_id in self.active_conversation_ids:
                removed_id = self.active_conversation_ids.pop(user_id, None)
                self.save_active_conversation_ids()
                print(f"Cleared active conversation ID {removed_id} for user {user_id}")

            await ctx.send("Conversation history and active session cleared")
            # TODO: Optionally call API to delete conversation by ID if needed
        else:
            await ctx.send("No conversation history or active session to clear")

    @commands.command(name="aisyncsettings")
    async def sync_settings_command(self, ctx):
        """Force sync settings with the API"""
        user_id = ctx.author.id

        # Try to get the user's Discord token for API authentication
        token = await self.get_discord_token(user_id)

        if not token:
            await ctx.send("❌ No Discord token available for API sync. Please log in to the Flutter app first or use !aisavetoken.")
            return

        # Send a message to indicate we're syncing
        message = await ctx.send("⏳ Syncing settings with the API...")

        try:
            # First try to fetch settings from the API
            api_settings_fetched = await self.fetch_settings_from_api(user_id, token)

            if api_settings_fetched:
                await message.edit(content="✅ Successfully fetched settings from the API")

                # Display the current settings
                settings = self.get_user_settings(user_id)
                settings_str = "Current AI settings after sync:\n"
                settings_str += f"Model: `{settings.get('model', 'openai/gpt-3.5-turbo')}`\n"
                settings_str += f"Temperature: `{settings.get('temperature', 0.7)}`\n"
                settings_str += f"Max Tokens: `{settings.get('max_tokens', 1000)}`\n"

                # Character settings
                character = settings.get('character')
                if character:
                    settings_str += f"Character: `{character}`\n"

                await ctx.send(settings_str)
            else:
                # If fetching failed, try pushing local settings to the API
                await message.edit(content="⚠️ Failed to fetch settings from the API. Trying to push local settings...")

                # Get current settings
                settings = self.get_user_settings(user_id)

                # Convert to API format
                api_settings = convert_discord_settings_to_api(settings)

                # Update settings in the API
                updated_settings = await update_user_settings(str(user_id), token, api_settings)

                if updated_settings:
                    await message.edit(content="✅ Successfully pushed local settings to the API")
                else:
                    await message.edit(content="❌ Failed to sync settings with the API")
        except Exception as e:
            await message.edit(content=f"❌ Error syncing settings with the API: {str(e)}")
            print(f"Error syncing settings for user {user_id} with API: {e}")

    @commands.command(name="aisavetoken")
    async def save_token_command(self, ctx, token: str = None):
        """Save a Discord token for API authentication (for testing only)"""
        # This command should only be used by the bot owner or for testing
        if ctx.author.id != self.bot.owner_id and not await self.bot.is_owner(ctx.author):
            await ctx.send("❌ This command can only be used by the bot owner.")
            return

        # Delete the user's message to prevent token leakage
        try:
            await ctx.message.delete()
        except:
            pass

        if not token:
            await ctx.send("Please provide a token to save. Usage: `!aisavetoken <token>`")
            return

        user_id = ctx.author.id

        # Import the OAuth module
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import discord_oauth

        try:
            # Validate the token
            is_valid, discord_user_id = await discord_oauth.validate_token(token)

            if not is_valid:
                await ctx.send("❌ The token is invalid. Please provide a valid Discord token.")
                return

            # Create a mock token data structure
            token_data = {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 604800,  # 1 week
                "refresh_token": None,
                "scope": "identify"
            }

            # Save the token using the OAuth system
            discord_oauth.save_token(str(user_id), token_data)

            await ctx.send("✅ Token saved successfully. You can now use !aisyncsettings to sync with the API.")
        except Exception as e:
            await ctx.send(f"❌ Error saving token: {str(e)}")
            print(f"Error saving token for user {user_id}: {e}")

    @commands.command(name="aiapicheck")
    async def api_check_command(self, ctx):
        """Check the API connection status"""
        user_id = ctx.author.id

        # Send a message to indicate we're checking
        message = await ctx.send("⏳ Checking API connection...")

        # Check if the API client is initialized
        if not api_client:
            await message.edit(content="❌ API client not initialized. Please check your API_URL environment variable.")
            return

        # Try to get the user's Discord token for API authentication
        token = await self.get_discord_token(user_id)

        if not token:
            await message.edit(content="⚠️ No Discord token available. Will check API without authentication.")

        try:
            # Try to make a simple request to the API
            import aiohttp
            async with aiohttp.ClientSession() as session:
                api_url = os.getenv("API_URL", "https://slipstreamm.dev/api")
                async with session.get(f"{api_url}/") as response:
                    if response.status == 200:
                        await message.edit(content=f"✅ API connection successful! Status: {response.status}")
                    else:
                        await message.edit(content=f"⚠️ API responded with status code: {response.status}")

                    # Try to get the response body
                    try:
                        response_json = await response.json()
                        await ctx.send(f"API response: ```json\n{response_json}\n```")
                    except:
                        response_text = await response.text()
                        await ctx.send(f"API response: ```\n{response_text[:1000]}\n```")
        except Exception as e:
            await message.edit(content=f"❌ Error connecting to API: {str(e)}")
            print(f"Error checking API connection: {e}")

    @commands.command(name="aitokencheck")
    async def token_check_command(self, ctx):
        """Check if you have a valid Discord token for API authentication"""
        user_id = ctx.author.id

        # Try to get the user's Discord token for API authentication
        token = await self.get_discord_token(user_id)

        if not token:
            await ctx.send("❌ No Discord token available. Please log in to the Flutter app first or use !aisavetoken.")
            return

        # Send a message to indicate we're checking
        message = await ctx.send("⏳ Checking token validity...")

        try:
            # Try to make an authenticated request to the API
            import aiohttp
            async with aiohttp.ClientSession() as session:
                api_url = os.getenv("API_URL", "https://slipstreamm.dev/api")
                headers = {"Authorization": f"Bearer {token}"}

                # Try to get user settings (requires authentication)
                async with session.get(f"{api_url}/settings", headers=headers) as response:
                    if response.status == 200:
                        await message.edit(content=f"✅ Token is valid! Successfully authenticated with the API.")

                        # Try to get the response body to show some settings
                        try:
                            response_json = await response.json()
                            # Extract some basic settings to display
                            settings = response_json.get("settings", {})
                            if settings:
                                model = settings.get("model_id", "Unknown")
                                temp = settings.get("temperature", "Unknown")
                                await ctx.send(f"API settings preview: Model: `{model}`, Temperature: `{temp}`")
                        except Exception as e:
                            print(f"Error parsing settings response: {e}")
                    elif response.status == 401:
                        await message.edit(content=f"❌ Token is invalid or expired. Please log in to the Flutter app again or use !aisavetoken with a new token.")
                    else:
                        await message.edit(content=f"⚠️ API responded with status code: {response.status}")
                        response_text = await response.text()
                        await ctx.send(f"API response: ```\n{response_text[:500]}\n```")
        except Exception as e:
            await message.edit(content=f"❌ Error checking token: {str(e)}")
            print(f"Error checking token: {e}")

    @commands.command(name="aihelp")
    async def ai_help_command(self, ctx):
        """Show help for AI commands"""
        help_embed = discord.Embed(
            title="AI Commands Help",
            description="Here are all the available AI commands and their descriptions.",
            color=discord.Color.blue()
        )

        # Basic commands
        help_embed.add_field(
            name="Basic Commands",
            value=(
                "`!ai <prompt>` - Chat with the AI\n"
                "`!aiclear` - Clear your conversation history\n"
                "`!aihelp` - Show this help message"
            ),
            inline=False
        )

        # Settings commands
        help_embed.add_field(
            name="Settings Commands",
            value=(
                "`!aiset` - View current AI settings\n"
                "`!aiset model <model_id>` - Set the AI model\n"
                "`!aiset temperature <value>` - Set the temperature (0.0-2.0)\n"
                "`!aiset max_tokens <value>` - Set the maximum tokens\n"
                "`!aiset reasoning <true/false>` - Enable/disable reasoning\n"
                "`!aiset reasoning_effort <low/medium/high>` - Set reasoning effort\n"
                "`!aiset websearch <true/false>` - Enable/disable web search\n"
                "`!aiset system <prompt>` - Set the system prompt\n"
                "`!aiset character <name>` - Set the character name\n"
                "`!aiset character_info <info>` - Set character information\n"
                "`!aiset character_breakdown <true/false>` - Enable/disable character breakdown\n"
                "`!aiset custom_instructions <instructions>` - Set custom instructions"
            ),
            inline=False
        )

        # Sync commands
        help_embed.add_field(
            name="Sync Commands",
            value=(
                "`!aisyncsettings` - Force sync settings with the API\n"
                "`!aiapicheck` - Check the API connection status\n"
                "`!aitokencheck` - Check if you have a valid Discord token for API\n"
                "`!aisavetoken <token>` - Save a Discord token for API authentication (owner only)"
            ),
            inline=False
        )

        # Authentication commands
        help_embed.add_field(
            name="Authentication Commands",
            value=(
                "`!auth` - Authenticate with Discord to allow the bot to access the API\n"
                "`!deauth` - Revoke the bot's access to your Discord account\n"
                "`!authstatus` - Check your authentication status\n"
                "`!authhelp` - Get help with authentication commands"
            ),
            inline=False
        )

        # Troubleshooting
        help_embed.add_field(
            name="Troubleshooting",
            value=(
                "If your settings aren't syncing properly between the Discord bot and Flutter app:\n"
                "1. Use `!auth` to authenticate with Discord\n"
                "2. Use `!authstatus` to verify your authentication status\n"
                "3. Use `!aiapicheck` to verify the API is accessible\n"
                "4. Use `!aisyncsettings` to force a sync with the API\n"
                "5. Make sure you're logged in to the Flutter app with the same Discord account"
            ),
            inline=False
        )

        await ctx.send(embed=help_embed)

async def setup(bot):
    await bot.add_cog(AICog(bot))
