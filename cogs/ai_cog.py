import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import os
from typing import Dict, List, Optional, Any
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# File paths
HISTORY_FILE = "ai_conversation_history.json"  # File to store conversation history
USER_SETTINGS_FILE = "ai_user_settings.json"  # File to store user settings

# Customization Variables
# These can be modified to change the behavior of the AI
AI_API_KEY = os.getenv("AI_API_KEY", "")  # API key for OpenAI or compatible service
AI_API_URL = os.getenv("AI_API_URL", "https://api.openai.com/v1/chat/completions")  # API endpoint
AI_DEFAULT_MODEL = os.getenv("AI_DEFAULT_MODEL", "gpt-3.5-turbo")  # Default model to use
AI_DEFAULT_SYSTEM_PROMPT = os.getenv("AI_DEFAULT_SYSTEM_PROMPT", "You are a helpful assistant.")  # Default system prompt
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1000"))  # Maximum tokens in response
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))  # Temperature for response generation
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "60"))  # Timeout for API requests in seconds
AI_COMPATIBILITY_MODE = os.getenv("AI_COMPATIBILITY_MODE", "openai").lower()  # API compatibility mode (openai, custom)

# Store conversation history per user
conversation_history = {}

# Store user settings
user_settings = {}

# Load conversation history from JSON file
def load_conversation_history():
    """Load conversation history from JSON file"""
    global conversation_history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                # Convert string keys (from JSON) back to integers
                data = json.load(f)
                conversation_history = {int(k): v for k, v in data.items()}
            print(f"Loaded conversation history for {len(conversation_history)} users")
        except Exception as e:
            print(f"Error loading conversation history: {e}")

# Save conversation history to JSON file
def save_conversation_history():
    """Save conversation history to JSON file"""
    try:
        # Convert int keys to strings for JSON serialization
        serializable_history = {str(k): v for k, v in conversation_history.items()}
        with open(HISTORY_FILE, "w") as f:
            json.dump(serializable_history, f, indent=4)
    except Exception as e:
        print(f"Error saving conversation history: {e}")

# Load user settings from JSON file
def load_user_settings():
    """Load user settings from JSON file"""
    global user_settings
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r") as f:
                # Convert string keys (from JSON) back to integers
                data = json.load(f)
                user_settings = {int(k): v for k, v in data.items()}
            print(f"Loaded settings for {len(user_settings)} users")
        except Exception as e:
            print(f"Error loading user settings: {e}")

# Save user settings to JSON file
def save_user_settings():
    """Save user settings to JSON file"""
    try:
        # Convert int keys to strings for JSON serialization
        serializable_settings = {str(k): v for k, v in user_settings.items()}
        with open(USER_SETTINGS_FILE, "w") as f:
            json.dump(serializable_settings, f, indent=4)
    except Exception as e:
        print(f"Error saving user settings: {e}")

# Get user settings with defaults
def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Get settings for a user, with defaults if not set"""
    if user_id not in user_settings:
        user_settings[user_id] = {}

    # Return settings with defaults for missing values
    settings = user_settings[user_id]
    return {
        "model": settings.get("model", AI_DEFAULT_MODEL),
        "system_prompt": settings.get("system_prompt", AI_DEFAULT_SYSTEM_PROMPT),
        "max_tokens": settings.get("max_tokens", AI_MAX_TOKENS),
        "temperature": settings.get("temperature", AI_TEMPERATURE),
        "timeout": settings.get("timeout", AI_TIMEOUT)
    }

# Initialize by loading saved data
load_conversation_history()
load_user_settings()

class AICog(commands.Cog):
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

        # Save conversation history and user settings when unloading
        save_conversation_history()
        save_user_settings()

    async def _get_ai_response(self, user_id: int, prompt: str, system_prompt: str = None) -> str:
        """
        Get a response from the AI API

        Args:
            user_id: Discord user ID for conversation history
            prompt: User's message
            system_prompt: Optional system prompt to override default

        Returns:
            The AI's response as a string
        """
        if not AI_API_KEY:
            return "Error: AI API key not configured. Please set the AI_API_KEY environment variable."

        # Initialize conversation history for this user if it doesn't exist
        if user_id not in conversation_history:
            conversation_history[user_id] = []

        # Get user settings
        settings = get_user_settings(user_id)

        # Create messages array with system prompt and conversation history
        messages = [
            {"role": "system", "content": system_prompt or settings["system_prompt"]}
        ]

        # Add conversation history (up to last 10 messages to avoid token limits)
        messages.extend(conversation_history[user_id][-10:])

        # Add the current user message
        messages.append({"role": "user", "content": prompt})

        # Prepare the request payload based on compatibility mode
        if AI_COMPATIBILITY_MODE == "openai":
            payload = {
                "model": settings["model"],
                "messages": messages,
                "max_tokens": settings["max_tokens"],
                "temperature": settings["temperature"],
            }
        else:  # custom mode for other API formats
            payload = {
                "model": settings["model"],
                "messages": messages,
                "max_tokens": settings["max_tokens"],
                "temperature": settings["temperature"],
                "stream": False
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_API_KEY}"
        }

        try:
            async with self.session.post(
                AI_API_URL,
                headers=headers,
                json=payload,
                timeout=settings["timeout"]
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return f"Error from API (Status {response.status}): {error_text}"

                data = await response.json()

                # Debug information
                print(f"API Response: {data}")

                # Parse the response based on compatibility mode
                ai_response = None
                safety_cutoff = False

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

                    # Check for safety cutoff in OpenAI format
                    if "finish_reason" in data["choices"][0] and data["choices"][0]["finish_reason"] == "content_filter":
                        safety_cutoff = True
                    # Check for native_finish_reason: SAFETY
                    if "native_finish_reason" in data["choices"][0] and data["choices"][0]["native_finish_reason"] == "SAFETY":
                        safety_cutoff = True
                else:
                    # Custom format - try different response structures
                    # Try standard OpenAI format first
                    if "choices" in data and data["choices"] and "message" in data["choices"][0]:
                        ai_response = data["choices"][0]["message"]["content"]
                        # Check for safety cutoff in OpenAI format
                        if "finish_reason" in data["choices"][0] and data["choices"][0]["finish_reason"] == "content_filter":
                            safety_cutoff = True
                        # Check for native_finish_reason: SAFETY
                        if "native_finish_reason" in data["choices"][0] and data["choices"][0]["native_finish_reason"] == "SAFETY":
                            safety_cutoff = True
                    # Try Ollama/LM Studio format
                    elif "response" in data:
                        ai_response = data["response"]
                        # Check for safety cutoff in response metadata
                        if "native_finish_reason" in data and data["native_finish_reason"] == "SAFETY":
                            safety_cutoff = True
                    # Try text-only format
                    elif "text" in data:
                        ai_response = data["text"]
                        # Check for safety cutoff in response metadata
                        if "native_finish_reason" in data and data["native_finish_reason"] == "SAFETY":
                            safety_cutoff = True
                    # Try content-only format
                    elif "content" in data:
                        ai_response = data["content"]
                        # Check for safety cutoff in response metadata
                        if "native_finish_reason" in data and data["native_finish_reason"] == "SAFETY":
                            safety_cutoff = True
                    # Try output format
                    elif "output" in data:
                        ai_response = data["output"]
                        # Check for safety cutoff in response metadata
                        if "native_finish_reason" in data and data["native_finish_reason"] == "SAFETY":
                            safety_cutoff = True
                    # Try result format
                    elif "result" in data:
                        ai_response = data["result"]
                        # Check for safety cutoff in response metadata
                        if "native_finish_reason" in data and data["native_finish_reason"] == "SAFETY":
                            safety_cutoff = True
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

                # Update conversation history
                conversation_history[user_id].append({"role": "user", "content": prompt})
                conversation_history[user_id].append({"role": "assistant", "content": ai_response})

                # Save conversation history to file
                save_conversation_history()

                return ai_response

        except asyncio.TimeoutError:
            return "Error: Request to AI API timed out. Please try again later."
        except Exception as e:
            error_message = f"Error communicating with AI API: {str(e)}"
            print(f"Exception in _get_ai_response: {error_message}")
            print(f"Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return error_message

    @app_commands.command(name="ai", description="Get a response from the AI")
    @app_commands.describe(
        prompt="Your message to the AI",
        system_prompt="Optional system prompt to override the default",
        clear_history="Clear your conversation history before sending this message"
    )
    async def ai_slash(
        self,
        interaction: discord.Interaction,
        prompt: str,
        system_prompt: Optional[str] = None,
        clear_history: bool = False
    ):
        """Slash command to get a response from the AI"""
        user_id = interaction.user.id

        # Clear history if requested
        if clear_history and user_id in conversation_history:
            conversation_history[user_id] = []

        # Defer the response since API calls can take time
        await interaction.response.defer(thinking=True)

        # Get AI response
        response = await self._get_ai_response(user_id, prompt, system_prompt)

        # Send the response
        await interaction.followup.send(response)

    @commands.command(name="ai")
    async def ai_prefix(self, ctx: commands.Context, *, prompt: str):
        """Prefix command to get a response from the AI"""
        user_id = ctx.author.id

        # Show typing indicator
        async with ctx.typing():
            # Get AI response
            response = await self._get_ai_response(user_id, prompt)

        # Send the response
        await ctx.reply(response)

    @commands.command(name="aiclear")
    async def clear_history(self, ctx: commands.Context):
        """Clear your AI conversation history"""
        user_id = ctx.author.id

        if user_id in conversation_history:
            conversation_history[user_id] = []
            await ctx.reply("Your AI conversation history has been cleared.")
        else:
            await ctx.reply("You don't have any conversation history to clear.")

    @app_commands.command(name="aiclear", description="Clear your AI conversation history")
    async def clear_history_slash(self, interaction: discord.Interaction):
        """Slash command to clear AI conversation history"""
        user_id = interaction.user.id

        if user_id in conversation_history:
            conversation_history[user_id] = []
            await interaction.response.send_message("Your AI conversation history has been cleared.")
        else:
            await interaction.response.send_message("You don't have any conversation history to clear.")

    @commands.command(name="aiseturl")
    @commands.is_owner()
    async def set_api_url(self, ctx: commands.Context, *, new_url: str):
        """Set a new API URL for the AI service (Owner only)"""
        global AI_API_URL
        old_url = AI_API_URL
        AI_API_URL = new_url.strip()
        await ctx.send(f"API URL updated:\nOld: `{old_url}`\nNew: `{AI_API_URL}`")

    @commands.command(name="aisetkey")
    @commands.is_owner()
    async def set_api_key(self, ctx: commands.Context, *, new_key: str):
        """Set a new API key for the AI service (Owner only)"""
        global AI_API_KEY
        AI_API_KEY = new_key.strip()
        # Delete the user's message to protect the API key
        try:
            await ctx.message.delete()
        except:
            pass
        await ctx.send("API key updated. The message with your key has been deleted for security.")

    @commands.command(name="aisetmodel")
    @commands.is_owner()
    async def set_model(self, ctx: commands.Context, *, new_model: str):
        """Set a new model for the AI service (Owner only)"""
        global AI_DEFAULT_MODEL
        new_model = new_model.strip()

        # Validate that the model contains ":free" if it's being changed
        if ":free" not in new_model:
            await ctx.send(f"Error: Model name must contain `:free`. Model not updated.")
            return

        old_model = AI_DEFAULT_MODEL
        AI_DEFAULT_MODEL = new_model
        await ctx.send(f"AI model updated:\nOld: `{old_model}`\nNew: `{AI_DEFAULT_MODEL}`")

    @commands.command(name="aisetmode")
    @commands.is_owner()
    async def set_compatibility_mode(self, ctx: commands.Context, *, mode: str):
        """Set the API compatibility mode (Owner only)

        Valid modes:
        - openai: Standard OpenAI API format
        - custom: Try multiple response formats (for local LLMs)
        """
        global AI_COMPATIBILITY_MODE
        mode = mode.strip().lower()

        if mode not in ["openai", "custom"]:
            await ctx.send(f"Invalid mode: `{mode}`. Valid options are: `openai`, `custom`")
            return

        old_mode = AI_COMPATIBILITY_MODE
        AI_COMPATIBILITY_MODE = mode
        await ctx.send(f"AI compatibility mode updated:\nOld: `{old_mode}`\nNew: `{AI_COMPATIBILITY_MODE}`")

    @commands.command(name="aidebug")
    @commands.is_owner()
    async def ai_debug(self, ctx: commands.Context):
        """Debug command to check AI API configuration (Owner only)"""
        debug_info = [
            "**AI Configuration Debug Info:**",
            f"API URL: `{AI_API_URL}`",
            f"API Key Set: `{'Yes' if AI_API_KEY else 'No'}`",
            f"Default Model: `{AI_DEFAULT_MODEL}`",
            f"Compatibility Mode: `{AI_COMPATIBILITY_MODE}`",
            f"Default Max Tokens: `{AI_MAX_TOKENS}`",
            f"Default Temperature: `{AI_TEMPERATURE}`",
            f"Default Timeout: `{AI_TIMEOUT}s`",
            f"Active Conversations: `{len(conversation_history)}`",
            f"Users with Custom Settings: `{len(user_settings)}`"
        ]

        # Add user's personal settings if they have any
        user_id = ctx.author.id
        if user_id in user_settings:
            debug_info.append("\n**Your Personal Settings:**")
            settings = get_user_settings(user_id)
            debug_info.append(f"Model: `{settings['model']}`")
            debug_info.append(f"System Prompt: `{settings['system_prompt']}`")
            debug_info.append(f"Max Tokens: `{settings['max_tokens']}`")
            debug_info.append(f"Temperature: `{settings['temperature']}`")
            debug_info.append(f"Timeout: `{settings['timeout']}s`")

        # Test API connection with a simple request
        await ctx.send("\n".join(debug_info))
        await ctx.send("Testing API connection...")

        # Get user settings for the test
        user_id = ctx.author.id
        settings = get_user_settings(user_id)

        # Create a minimal test request based on compatibility mode
        if AI_COMPATIBILITY_MODE == "openai":
            test_payload = {
                "model": settings["model"],
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10
            }
        else:  # custom mode
            test_payload = {
                "model": settings["model"],
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10,
                "stream": False
            }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AI_API_KEY}"
        }

        try:
            async with self.session.post(
                AI_API_URL,
                headers=headers,
                json=test_payload,
                timeout=settings["timeout"]
            ) as response:
                status = response.status
                response_text = await response.text()

                await ctx.send(f"API Response Status: `{status}`")

                # Truncate response if too long
                if len(response_text) > 1900:
                    response_text = response_text[:1900] + "..."

                await ctx.send(f"API Response:\n```json\n{response_text}\n```")

        except Exception as e:
            await ctx.send(f"Error testing API: {str(e)}")

    @commands.command(name="aiset")
    async def set_user_setting(self, ctx: commands.Context, setting: str, *, value: str):
        """Set a personal AI setting

        Available settings:
        - model: The AI model to use (must contain ":free")
        - system_prompt: The system prompt to use
        - max_tokens: Maximum tokens in response (100-2000)
        - temperature: Temperature for response generation (0.0-2.0)
        - timeout: Timeout for API requests in seconds (10-120)
        """
        user_id = ctx.author.id
        setting = setting.lower().strip()
        value = value.strip()

        # Initialize user settings if not exist
        if user_id not in user_settings:
            user_settings[user_id] = {}

        # Validate and set the appropriate setting
        if setting == "model":
            # Validate model contains ":free"
            if ":free" not in value:
                await ctx.reply(f"Error: Model name must contain `:free`. Setting not updated.")
                return
            user_settings[user_id]["model"] = value
            await ctx.reply(f"Your AI model has been set to: `{value}`")

        elif setting == "system_prompt":
            user_settings[user_id]["system_prompt"] = value
            await ctx.reply(f"Your system prompt has been set to: `{value}`")

        elif setting == "max_tokens":
            try:
                tokens = int(value)
                if tokens < 100 or tokens > 2000:
                    await ctx.reply("Error: max_tokens must be between 100 and 2000.")
                    return
                user_settings[user_id]["max_tokens"] = tokens
                await ctx.reply(f"Your max tokens has been set to: `{tokens}`")
            except ValueError:
                await ctx.reply("Error: max_tokens must be a number.")

        elif setting == "temperature":
            try:
                temp = float(value)
                if temp < 0.0 or temp > 2.0:
                    await ctx.reply("Error: temperature must be between 0.0 and 2.0.")
                    return
                user_settings[user_id]["temperature"] = temp
                await ctx.reply(f"Your temperature has been set to: `{temp}`")
            except ValueError:
                await ctx.reply("Error: temperature must be a number.")

        elif setting == "timeout":
            try:
                timeout = int(value)
                if timeout < 10 or timeout > 120:
                    await ctx.reply("Error: timeout must be between 10 and 120 seconds.")
                    return
                user_settings[user_id]["timeout"] = timeout
                await ctx.reply(f"Your timeout has been set to: `{timeout}` seconds")
            except ValueError:
                await ctx.reply("Error: timeout must be a number.")

        else:
            await ctx.reply(f"Unknown setting: `{setting}`. Available settings: model, system_prompt, max_tokens, temperature, timeout")
            return

        # Save settings to file
        save_user_settings()

    @app_commands.command(name="aiset", description="Set a personal AI setting")
    @app_commands.describe(
        setting="The setting to change",
        value="The new value for the setting"
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="model", value="model"),
        app_commands.Choice(name="system_prompt", value="system_prompt"),
        app_commands.Choice(name="max_tokens", value="max_tokens"),
        app_commands.Choice(name="temperature", value="temperature"),
        app_commands.Choice(name="timeout", value="timeout")
    ])
    async def set_user_setting_slash(self, interaction: discord.Interaction, setting: app_commands.Choice[str], value: str):
        """Slash command to set a personal AI setting"""
        user_id = interaction.user.id
        setting_name = setting.value
        value = value.strip()

        # Initialize user settings if not exist
        if user_id not in user_settings:
            user_settings[user_id] = {}

        # Validate and set the appropriate setting
        if setting_name == "model":
            # Validate model contains ":free"
            if ":free" not in value:
                await interaction.response.send_message(f"Error: Model name must contain `:free`. Setting not updated.")
                return
            user_settings[user_id]["model"] = value
            await interaction.response.send_message(f"Your AI model has been set to: `{value}`")

        elif setting_name == "system_prompt":
            user_settings[user_id]["system_prompt"] = value
            await interaction.response.send_message(f"Your system prompt has been set to: `{value}`")

        elif setting_name == "max_tokens":
            try:
                tokens = int(value)
                if tokens < 100 or tokens > 2000:
                    await interaction.response.send_message("Error: max_tokens must be between 100 and 2000.")
                    return
                user_settings[user_id]["max_tokens"] = tokens
                await interaction.response.send_message(f"Your max tokens has been set to: `{tokens}`")
            except ValueError:
                await interaction.response.send_message("Error: max_tokens must be a number.")

        elif setting_name == "temperature":
            try:
                temp = float(value)
                if temp < 0.0 or temp > 2.0:
                    await interaction.response.send_message("Error: temperature must be between 0.0 and 2.0.")
                    return
                user_settings[user_id]["temperature"] = temp
                await interaction.response.send_message(f"Your temperature has been set to: `{temp}`")
            except ValueError:
                await interaction.response.send_message("Error: temperature must be a number.")

        elif setting_name == "timeout":
            try:
                timeout = int(value)
                if timeout < 10 or timeout > 120:
                    await interaction.response.send_message("Error: timeout must be between 10 and 120 seconds.")
                    return
                user_settings[user_id]["timeout"] = timeout
                await interaction.response.send_message(f"Your timeout has been set to: `{timeout}` seconds")
            except ValueError:
                await interaction.response.send_message("Error: timeout must be a number.")

        # Save settings to file
        save_user_settings()

    @commands.command(name="aireset")
    async def reset_user_settings(self, ctx: commands.Context):
        """Reset all your personal AI settings to defaults"""
        user_id = ctx.author.id

        if user_id in user_settings:
            user_settings.pop(user_id)
            save_user_settings()
            await ctx.reply("Your AI settings have been reset to defaults.")
        else:
            await ctx.reply("You don't have any custom settings to reset.")

    @app_commands.command(name="aireset", description="Reset all your personal AI settings to defaults")
    async def reset_user_settings_slash(self, interaction: discord.Interaction):
        """Slash command to reset all personal AI settings"""
        user_id = interaction.user.id

        if user_id in user_settings:
            user_settings.pop(user_id)
            save_user_settings()
            await interaction.response.send_message("Your AI settings have been reset to defaults.")
        else:
            await interaction.response.send_message("You don't have any custom settings to reset.")

    @commands.command(name="aisettings")
    async def show_user_settings(self, ctx: commands.Context):
        """Show your current AI settings"""
        user_id = ctx.author.id
        settings = get_user_settings(user_id)

        settings_info = [
            "**Your AI Settings:**",
            f"Model: `{settings['model']}`",
            f"System Prompt: `{settings['system_prompt']}`",
            f"Max Tokens: `{settings['max_tokens']}`",
            f"Temperature: `{settings['temperature']}`",
            f"Timeout: `{settings['timeout']}s`",
        ]

        # Add note about custom vs default settings
        if user_id in user_settings:
            custom_settings = list(user_settings[user_id].keys())
            if custom_settings:
                settings_info.append(f"\n*Custom settings: {', '.join(custom_settings)}*")
        else:
            settings_info.append("\n*All settings are at default values*")

        await ctx.reply("\n".join(settings_info))

    @app_commands.command(name="aisettings", description="Show your current AI settings")
    async def show_user_settings_slash(self, interaction: discord.Interaction):
        """Slash command to show current AI settings"""
        user_id = interaction.user.id
        settings = get_user_settings(user_id)

        settings_info = [
            "**Your AI Settings:**",
            f"Model: `{settings['model']}`",
            f"System Prompt: `{settings['system_prompt']}`",
            f"Max Tokens: `{settings['max_tokens']}`",
            f"Temperature: `{settings['temperature']}`",
            f"Timeout: `{settings['timeout']}s`",
        ]

        # Add note about custom vs default settings
        if user_id in user_settings:
            custom_settings = list(user_settings[user_id].keys())
            if custom_settings:
                settings_info.append(f"\n*Custom settings: {', '.join(custom_settings)}*")
        else:
            settings_info.append("\n*All settings are at default values*")

        await interaction.response.send_message("\n".join(settings_info))

async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
