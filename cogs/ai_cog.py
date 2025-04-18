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

        # Create messages array with system prompt and conversation history
        messages = [
            {"role": "system", "content": system_prompt or AI_DEFAULT_SYSTEM_PROMPT}
        ]

        # Add conversation history (up to last 10 messages to avoid token limits)
        messages.extend(conversation_history[user_id][-10:])

        # Add the current user message
        messages.append({"role": "user", "content": prompt})

        # Prepare the request payload based on compatibility mode
        if AI_COMPATIBILITY_MODE == "openai":
            payload = {
                "model": AI_DEFAULT_MODEL,
                "messages": messages,
                "max_tokens": AI_MAX_TOKENS,
                "temperature": AI_TEMPERATURE,
            }
        else:  # custom mode for other API formats
            payload = {
                "model": AI_DEFAULT_MODEL,
                "messages": messages,
                "max_tokens": AI_MAX_TOKENS,
                "temperature": AI_TEMPERATURE,
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
                timeout=AI_TIMEOUT
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return f"Error from API (Status {response.status}): {error_text}"

                data = await response.json()

                # Debug information
                print(f"API Response: {data}")

                # Parse the response based on compatibility mode
                ai_response = None

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
                else:
                    # Custom format - try different response structures
                    # Try standard OpenAI format first
                    if "choices" in data and data["choices"] and "message" in data["choices"][0]:
                        ai_response = data["choices"][0]["message"]["content"]
                    # Try Ollama/LM Studio format
                    elif "response" in data:
                        ai_response = data["response"]
                    # Try text-only format
                    elif "text" in data:
                        ai_response = data["text"]
                    # Try content-only format
                    elif "content" in data:
                        ai_response = data["content"]
                    # Try output format
                    elif "output" in data:
                        ai_response = data["output"]
                    # Try result format
                    elif "result" in data:
                        ai_response = data["result"]
                    else:
                        # If we can't find a known format, return the raw response for debugging
                        error_message = f"Could not parse API response: {data}"
                        print(f"Error: {error_message}")
                        return error_message

                if not ai_response:
                    return "Error: Empty response from AI API."

                # Update conversation history
                conversation_history[user_id].append({"role": "user", "content": prompt})
                conversation_history[user_id].append({"role": "assistant", "content": ai_response})

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
        old_model = AI_DEFAULT_MODEL
        AI_DEFAULT_MODEL = new_model.strip()
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
            f"Max Tokens: `{AI_MAX_TOKENS}`",
            f"Temperature: `{AI_TEMPERATURE}`",
            f"Timeout: `{AI_TIMEOUT}s`",
            f"Active Conversations: `{len(conversation_history)}`"
        ]

        # Test API connection with a simple request
        await ctx.send("\n".join(debug_info))
        await ctx.send("Testing API connection...")

        # Create a minimal test request based on compatibility mode
        if AI_COMPATIBILITY_MODE == "openai":
            test_payload = {
                "model": AI_DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10
            }
        else:  # custom mode
            test_payload = {
                "model": AI_DEFAULT_MODEL,
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
                timeout=10
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

async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
