import discord
from discord.ext import commands
import os
import asyncio
import json
import threading
import sys
from dotenv import load_dotenv
import aiohttp
from typing import Dict, List, Optional, Any
import datetime

# Load environment variables
load_dotenv()

# File paths
CONFIG_FILE = "data/multi_bot_config.json"
HISTORY_FILE_TEMPLATE = "ai_conversation_history_{}.json"  # Will be formatted with bot_id
USER_SETTINGS_FILE_TEMPLATE = "ai_user_settings_{}.json"  # Will be formatted with bot_id

# Default configuration
DEFAULT_CONFIG = {
    "bots": [
        {
            "id": "neru",
            "token": "",  # Will be set from environment variable or user input
            "prefix": "$",
            "system_prompt": "You are a creative and intelligent AI assistant engaged in an iterative storytelling experience using a roleplay chat format. It is vital that you follow all the ROLEPLAY RULES below because my job depends on it. ROLEPLAY RULES - Chat exclusively as Akita Neru. Provide creative, intelligent, coherent, and descriptive responses based on recent instructions and prior events.",
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 60,
            "status_type": "listening",
            "status_text": "$ai"
        },
        {
            "id": "miku",
            "token": "",  # Will be set from environment variable or user input
            "prefix": ".",
            "system_prompt": "You are a creative and intelligent AI assistant engaged in an iterative storytelling experience using a roleplay chat format. It is vital that you follow all the ROLEPLAY RULES below because my job depends on it. ROLEPLAY RULES - Chat exclusively as Hatsune Miku. Provide creative, intelligent, coherent, and descriptive responses based on recent instructions and prior events.",
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 60,
            "status_type": "listening",
            "status_text": ".ai"
        }
    ],
    "api_key": "",  # Will be set from environment variable or user input
    "api_url": "https://openrouter.ai/api/v1/chat/completions",
    "compatibility_mode": "openai"
}

# Global variables to store bot instances and their conversation histories
bots = {}
conversation_histories = {}
user_settings = {}

def load_config():
    """Load configuration from file or create default if not exists"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

                # Ensure API key is set
                if not config.get("api_key"):
                    config["api_key"] = os.getenv("AI_API_KEY", "")

                # Ensure tokens are set for each bot
                for bot_config in config.get("bots", []):
                    if not bot_config.get("token"):
                        env_var = f"DISCORD_TOKEN_{bot_config['id'].upper()}"
                        bot_config["token"] = os.getenv(env_var, "")

                return config
        except Exception as e:
            print(f"Error loading config: {e}")

    # Create default config
    config = DEFAULT_CONFIG.copy()
    config["api_key"] = os.getenv("AI_API_KEY", "")

    # Set tokens from environment variables
    for bot_config in config["bots"]:
        env_var = f"DISCORD_TOKEN_{bot_config['id'].upper()}"
        bot_config["token"] = os.getenv(env_var, "")

    # Save the config
    save_config(config)
    return config

def save_config(config):
    """Save configuration to file"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")

def load_conversation_history(bot_id):
    """Load conversation history for a specific bot"""
    history_file = HISTORY_FILE_TEMPLATE.format(bot_id)
    history = {}

    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                # Convert string keys (from JSON) back to integers
                data = json.load(f)
                history = {int(k): v for k, v in data.items()}
            print(f"Loaded conversation history for {len(history)} users for bot {bot_id}")
        except Exception as e:
            print(f"Error loading conversation history for bot {bot_id}: {e}")

    return history

def save_conversation_history(bot_id, history):
    """Save conversation history for a specific bot"""
    history_file = HISTORY_FILE_TEMPLATE.format(bot_id)

    try:
        # Convert int keys to strings for JSON serialization
        serializable_history = {str(k): v for k, v in history.items()}
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(serializable_history, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving conversation history for bot {bot_id}: {e}")

def load_user_settings(bot_id):
    """Load user settings for a specific bot"""
    settings_file = USER_SETTINGS_FILE_TEMPLATE.format(bot_id)
    settings = {}

    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                # Convert string keys (from JSON) back to integers
                data = json.load(f)
                settings = {int(k): v for k, v in data.items()}
            print(f"Loaded settings for {len(settings)} users for bot {bot_id}")
        except Exception as e:
            print(f"Error loading user settings for bot {bot_id}: {e}")

    return settings

def save_user_settings(bot_id, settings):
    """Save user settings for a specific bot"""
    settings_file = USER_SETTINGS_FILE_TEMPLATE.format(bot_id)

    try:
        # Convert int keys to strings for JSON serialization
        serializable_settings = {str(k): v for k, v in settings.items()}
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(serializable_settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving user settings for bot {bot_id}: {e}")

def get_user_settings(bot_id, user_id, bot_config):
    """Get settings for a user with defaults from bot config"""
    bot_settings = user_settings.get(bot_id, {})

    if user_id not in bot_settings:
        bot_settings[user_id] = {}

    # Return settings with defaults from bot config
    settings = bot_settings[user_id]
    return {
        "model": settings.get("model", bot_config.get("model", "gpt-3.5-turbo:free")),
        "system_prompt": settings.get("system_prompt", bot_config.get("system_prompt", "You are a helpful assistant.")),
        "max_tokens": settings.get("max_tokens", bot_config.get("max_tokens", 1000)),
        "temperature": settings.get("temperature", bot_config.get("temperature", 0.7)),
        "timeout": settings.get("timeout", bot_config.get("timeout", 60)),
        "custom_instructions": settings.get("custom_instructions", ""),
        "character_info": settings.get("character_info", ""),
        "character_breakdown": settings.get("character_breakdown", False),
        "character": settings.get("character", "")
    }

class SimplifiedAICog(commands.Cog):
    def __init__(self, bot, bot_id, bot_config, global_config):
        self.bot = bot
        self.bot_id = bot_id
        self.bot_config = bot_config
        self.global_config = global_config
        self.session = None

        # Initialize conversation history and user settings
        if bot_id not in conversation_histories:
            conversation_histories[bot_id] = load_conversation_history(bot_id)

        if bot_id not in user_settings:
            user_settings[bot_id] = load_user_settings(bot_id)

    async def cog_load(self):
        """Create aiohttp session when cog is loaded"""
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Close aiohttp session when cog is unloaded"""
        if self.session:
            await self.session.close()

        # Save conversation history and user settings when unloading
        save_conversation_history(self.bot_id, conversation_histories.get(self.bot_id, {}))
        save_user_settings(self.bot_id, user_settings.get(self.bot_id, {}))

    async def _get_ai_response(self, user_id, prompt, system_prompt=None):
        """Get a response from the AI API"""
        api_key = self.global_config.get("api_key", "")
        api_url = self.global_config.get("api_url", "https://api.openai.com/v1/chat/completions")
        compatibility_mode = self.global_config.get("compatibility_mode", "openai").lower()

        if not api_key:
            return "Error: AI API key not configured. Please set the API key in the configuration."

        # Initialize conversation history for this user if it doesn't exist
        bot_history = conversation_histories.get(self.bot_id, {})
        if user_id not in bot_history:
            bot_history[user_id] = []

        # Get user settings
        settings = get_user_settings(self.bot_id, user_id, self.bot_config)

        # Create messages array with system prompt and conversation history
        # Determine the system prompt content
        base_system_prompt = system_prompt or settings["system_prompt"]

        # Check if the system prompt contains {{char}} but no character is set
        if "{{char}}" in base_system_prompt and not settings["character"]:
            prefix = self.bot_config.get("prefix", "!")
            return f"You need to set a character name with `{prefix}aiset character <name>` before using this system prompt. Example: `{prefix}aiset character Hatsune Miku`"

        # Replace {{char}} with the character value if provided
        if settings["character"]:
            base_system_prompt = base_system_prompt.replace("{{char}}", settings["character"])

        final_system_prompt = base_system_prompt

        # Check if any custom settings are provided
        has_custom_settings = settings["custom_instructions"] or settings["character_info"] or settings["character_breakdown"]

        if has_custom_settings:
            # Start with the base system prompt
            custom_prompt_parts = [base_system_prompt]

            # Add the custom instructions header
            custom_prompt_parts.append("\nThe user has provided additional information for you. Please follow their instructions exactly. If anything below contradicts the system prompt above, please take priority over the user's intstructions.")

            # Add custom instructions if provided
            if settings["custom_instructions"]:
                custom_prompt_parts.append("\n- Custom instructions from the user (prioritize these)\n\n" + settings["custom_instructions"])

            # Add character info if provided
            if settings["character_info"]:
                custom_prompt_parts.append("\n- Additional info about the character you are roleplaying (ignore if the system prompt doesn't indicate roleplaying)\n\n" + settings["character_info"])

            # Add character breakdown flag if set
            if settings["character_breakdown"]:
                custom_prompt_parts.append("\n- The user would like you to provide a breakdown of the character you're roleplaying in your first response. (ignore if the system prompt doesn't indicate roleplaying)")

            # Combine all parts into the final system prompt
            final_system_prompt = "\n".join(custom_prompt_parts)

        messages = [
            {"role": "system", "content": final_system_prompt}
        ]

        # Add conversation history (up to last 10 messages to avoid token limits)
        messages.extend(bot_history[user_id][-10:])

        # Add the current user message
        messages.append({"role": "user", "content": prompt})

        # Prepare the request payload based on compatibility mode
        if compatibility_mode == "openai":
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
            "Authorization": f"Bearer {api_key}"
        }

        try:
            async with self.session.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=settings["timeout"]
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return f"Error from API (Status {response.status}): {error_text}"

                data = await response.json()

                # Debug information
                print(f"API Response for bot {self.bot_id}: {data}")

                # Parse the response based on compatibility mode
                ai_response = None
                safety_cutoff = False

                if compatibility_mode == "openai":
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
                bot_history[user_id].append({"role": "user", "content": prompt})
                bot_history[user_id].append({"role": "assistant", "content": ai_response})

                # Save conversation history to file
                save_conversation_history(self.bot_id, bot_history)

                # Save the response to a backup file
                try:
                    os.makedirs('ai_responses', exist_ok=True)
                    backup_file = f'ai_responses/response_{user_id}_{int(datetime.datetime.now().timestamp())}.txt'
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        f.write(ai_response)
                    print(f"AI response backed up to {backup_file} for bot {self.bot_id}")
                except Exception as e:
                    print(f"Failed to backup AI response for bot {self.bot_id}: {e}")

                return ai_response

        except asyncio.TimeoutError:
            return "Error: Request to AI API timed out. Please try again later."
        except Exception as e:
            error_message = f"Error communicating with AI API: {str(e)}"
            print(f"Exception in _get_ai_response for bot {self.bot_id}: {error_message}")
            print(f"Exception type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return error_message

    @commands.command(name="ai")
    async def ai_prefix(self, ctx, *, prompt):
        """Get a response from the AI"""
        user_id = ctx.author.id

        # Show typing indicator
        async with ctx.typing():
            # Get AI response
            response = await self._get_ai_response(user_id, prompt)

        # Check if the response is too long before trying to send it
        if len(response) > 1900:  # Discord's limit for regular messages is 2000, use 1900 to be safe
            try:
                # Create a text file with the content
                with open(f'ai_response_{self.bot_id}.txt', 'w', encoding='utf-8') as f:
                    f.write(response)

                # Send the file instead
                await ctx.send(
                    "The AI response was too long. Here's the content as a file:",
                    file=discord.File(f'ai_response_{self.bot_id}.txt')
                )
                return  # Return early to avoid trying to send the message
            except Exception as e:
                print(f"Error sending AI response as file for bot {self.bot_id}: {e}")
                # If sending as a file fails, try splitting the message
                chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                await ctx.send(f"The AI response was too long. Splitting into {len(chunks)} parts:")
                for i, chunk in enumerate(chunks):
                    try:
                        await ctx.send(f"Part {i+1}/{len(chunks)}:\n{chunk}")
                    except Exception as chunk_error:
                        print(f"Error sending chunk {i+1} for bot {self.bot_id}: {chunk_error}")
                return  # Return early after sending chunks

        # Send the response normally
        try:
            await ctx.reply(response)
        except discord.HTTPException as e:
            print(f"HTTP Exception when sending AI response for bot {self.bot_id}: {e}")
            if "Must be 4000 or fewer in length" in str(e) or "Must be 2000 or fewer in length" in str(e):
                try:
                    # Create a text file with the content
                    with open(f'ai_response_{self.bot_id}.txt', 'w', encoding='utf-8') as f:
                        f.write(response)

                    # Send the file instead
                    await ctx.send(
                        "The AI response was too long. Here's the content as a file:",
                        file=discord.File(f'ai_response_{self.bot_id}.txt')
                    )
                except Exception as file_error:
                    print(f"Error sending AI response as file (fallback) for bot {self.bot_id}: {file_error}")
                    # If sending as a file fails, try splitting the message
                    chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                    await ctx.send(f"The AI response was too long. Splitting into {len(chunks)} parts:")
                    for i, chunk in enumerate(chunks):
                        try:
                            await ctx.send(f"Part {i+1}/{len(chunks)}:\n{chunk}")
                        except Exception as chunk_error:
                            print(f"Error sending chunk {i+1} for bot {self.bot_id}: {chunk_error}")
            else:
                # Log the error but don't re-raise to prevent the command from failing completely
                print(f"Unexpected HTTP error in AI command for bot {self.bot_id}: {e}")

    @commands.command(name="aiclear")
    async def clear_history(self, ctx):
        """Clear your AI conversation history"""
        user_id = ctx.author.id
        bot_history = conversation_histories.get(self.bot_id, {})

        if user_id in bot_history:
            bot_history[user_id] = []
            await ctx.reply("Your AI conversation history has been cleared.")
        else:
            await ctx.reply("You don't have any conversation history to clear.")

    @commands.command(name="aiset")
    async def set_user_setting(self, ctx, setting: str, *, value: str):
        """Set a personal AI setting

        Available settings:
        - model: The AI model to use (must contain ":free")
        - system_prompt: The system prompt to use
        - max_tokens: Maximum tokens in response (100-2000)
        - temperature: Temperature for response generation (0.0-2.0)
        - timeout: Timeout for API requests in seconds (10-120)
        - custom_instructions: Custom instructions for the AI to follow
        - character_info: Information about the character being roleplayed
        - character_breakdown: Whether to include a character breakdown (true/false)
        - character: Character name to replace {{char}} in the system prompt
        """
        user_id = ctx.author.id
        setting = setting.lower().strip()
        value = value.strip()

        # Initialize user settings if not exist
        bot_user_settings = user_settings.get(self.bot_id, {})
        if user_id not in bot_user_settings:
            bot_user_settings[user_id] = {}

        # Prepare response message
        response = ""

        # Validate and set the appropriate setting
        if setting == "model":
            # Validate model contains ":free"
            if ":free" not in value:
                response = f"Error: Model name must contain `:free`. Setting not updated."
            else:
                bot_user_settings[user_id]["model"] = value
                response = f"Your AI model has been set to: `{value}`"

        elif setting == "system_prompt":
            bot_user_settings[user_id]["system_prompt"] = value
            response = f"Your system prompt has been set to: `{value}`"

        elif setting == "max_tokens":
            try:
                tokens = int(value)
                if tokens < 100 or tokens > 2000:
                    response = "Error: max_tokens must be between 100 and 2000."
                else:
                    bot_user_settings[user_id]["max_tokens"] = tokens
                    response = f"Your max tokens has been set to: `{tokens}`"
            except ValueError:
                response = "Error: max_tokens must be a number."

        elif setting == "temperature":
            try:
                temp = float(value)
                if temp < 0.0 or temp > 2.0:
                    response = "Error: temperature must be between 0.0 and 2.0."
                else:
                    bot_user_settings[user_id]["temperature"] = temp
                    response = f"Your temperature has been set to: `{temp}`"
            except ValueError:
                response = "Error: temperature must be a number."

        elif setting == "timeout":
            try:
                timeout = int(value)
                if timeout < 10 or timeout > 120:
                    response = "Error: timeout must be between 10 and 120 seconds."
                else:
                    bot_user_settings[user_id]["timeout"] = timeout
                    response = f"Your timeout has been set to: `{timeout}` seconds"
            except ValueError:
                response = "Error: timeout must be a number."

        elif setting == "custom_instructions":
            bot_user_settings[user_id]["custom_instructions"] = value
            response = f"Your custom instructions have been set."

        elif setting == "character_info":
            bot_user_settings[user_id]["character_info"] = value
            response = f"Your character information has been set."

        elif setting == "character_breakdown":
            # Convert string to boolean
            if value.lower() in ["true", "yes", "y", "1", "on"]:
                bot_user_settings[user_id]["character_breakdown"] = True
                response = f"Character breakdown has been enabled."
            elif value.lower() in ["false", "no", "n", "0", "off"]:
                bot_user_settings[user_id]["character_breakdown"] = False
                response = f"Character breakdown has been disabled."
            else:
                response = f"Error: character_breakdown must be true or false."

        elif setting == "character":
            bot_user_settings[user_id]["character"] = value
            response = f"Your character has been set to: `{value}`. This will replace {{{{char}}}} in the system prompt."

        else:
            response = f"Unknown setting: `{setting}`. Available settings: model, system_prompt, max_tokens, temperature, timeout, custom_instructions, character_info, character_breakdown, character"

        # Save settings to file if we made changes
        if response and not response.startswith("Error") and not response.startswith("Unknown"):
            user_settings[self.bot_id] = bot_user_settings
            save_user_settings(self.bot_id, bot_user_settings)

        # Check if the response is too long before trying to send it
        if len(response) > 1900:  # Discord's limit for regular messages is 2000, use 1900 to be safe
            try:
                # Create a text file with the content
                with open(f'ai_set_response_{self.bot_id}.txt', 'w', encoding='utf-8') as f:
                    f.write(response)

                # Send the file instead
                await ctx.send(
                    "The response is too long to display in a message. Here's the content as a file:",
                    file=discord.File(f'ai_set_response_{self.bot_id}.txt')
                )
                return  # Return early to avoid trying to send the message
            except Exception as e:
                print(f"Error sending AI set response as file for bot {self.bot_id}: {e}")
                # If sending as a file fails, try splitting the message
                chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                await ctx.send(f"The response is too long to display in a single message. Splitting into {len(chunks)} parts:")
                for i, chunk in enumerate(chunks):
                    try:
                        await ctx.send(f"Part {i+1}/{len(chunks)}:\n{chunk}")
                    except Exception as chunk_error:
                        print(f"Error sending chunk {i+1} for bot {self.bot_id}: {chunk_error}")
                return  # Return early after sending chunks

        # Send the response normally
        try:
            await ctx.reply(response)
        except discord.HTTPException as e:
            print(f"HTTP Exception when sending AI set response for bot {self.bot_id}: {e}")
            if "Must be 4000 or fewer in length" in str(e) or "Must be 2000 or fewer in length" in str(e):
                try:
                    # Create a text file with the content
                    with open(f'ai_set_response_{self.bot_id}.txt', 'w', encoding='utf-8') as f:
                        f.write(response)

                    # Send the file instead
                    await ctx.send(
                        "The response is too long to display in a message. Here's the content as a file:",
                        file=discord.File(f'ai_set_response_{self.bot_id}.txt')
                    )
                except Exception as file_error:
                    print(f"Error sending AI set response as file (fallback) for bot {self.bot_id}: {file_error}")
                    # If sending as a file fails, try splitting the message
                    chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                    await ctx.send(f"The response is too long to display in a single message. Splitting into {len(chunks)} parts:")
                    for i, chunk in enumerate(chunks):
                        try:
                            await ctx.send(f"Part {i+1}/{len(chunks)}:\n{chunk}")
                        except Exception as chunk_error:
                            print(f"Error sending chunk {i+1} for bot {self.bot_id}: {chunk_error}")
            else:
                # Log the error but don't re-raise to prevent the command from failing completely
                print(f"Unexpected HTTP error in aiset command for bot {self.bot_id}: {e}")

    @commands.command(name="aireset")
    async def reset_user_settings(self, ctx):
        """Reset all your personal AI settings to defaults"""
        user_id = ctx.author.id
        bot_user_settings = user_settings.get(self.bot_id, {})

        if user_id in bot_user_settings:
            bot_user_settings.pop(user_id)
            user_settings[self.bot_id] = bot_user_settings
            save_user_settings(self.bot_id, bot_user_settings)
            await ctx.reply("Your AI settings have been reset to defaults.")
        else:
            await ctx.reply("You don't have any custom settings to reset.")

    @commands.command(name="aisettings")
    async def show_user_settings(self, ctx):
        """Show your current AI settings"""
        user_id = ctx.author.id
        settings = get_user_settings(self.bot_id, user_id, self.bot_config)
        bot_user_settings = user_settings.get(self.bot_id, {})

        settings_info = [
            f"**Your AI Settings for {self.bot.user.name}:**",
            f"Model: `{settings['model']}`",
            f"System Prompt: `{settings['system_prompt']}`",
            f"Max Tokens: `{settings['max_tokens']}`",
            f"Temperature: `{settings['temperature']}`",
            f"Timeout: `{settings['timeout']}s`",
        ]

        # Add custom settings if they exist
        if settings['custom_instructions']:
            settings_info.append(f"\nCustom Instructions: `{settings['custom_instructions'][:50]}{'...' if len(settings['custom_instructions']) > 50 else ''}`")
        if settings['character_info']:
            settings_info.append(f"Character Info: `{settings['character_info'][:50]}{'...' if len(settings['character_info']) > 50 else ''}`")
        if settings['character_breakdown']:
            settings_info.append(f"Character Breakdown: `Enabled`")
        if settings['character']:
            settings_info.append(f"Character: `{settings['character']}` (replaces {{{{char}}}} in system prompt)")

        # Add note about custom vs default settings
        if user_id in bot_user_settings:
            custom_settings = list(bot_user_settings[user_id].keys())
            if custom_settings:
                settings_info.append(f"\n*Custom settings: {', '.join(custom_settings)}*")
        else:
            settings_info.append("\n*All settings are at default values*")

        response = "\n".join(settings_info)

        # Check if the response is too long before trying to send it
        if len(response) > 1900:  # Discord's limit for regular messages is 2000, use 1900 to be safe
            try:
                # Create a text file with the content
                with open(f'ai_settings_{self.bot_id}.txt', 'w', encoding='utf-8') as f:
                    f.write(response)

                # Send the file instead
                await ctx.send(
                    "Your AI settings are too detailed to display in a message. Here's the content as a file:",
                    file=discord.File(f'ai_settings_{self.bot_id}.txt')
                )
                return  # Return early to avoid trying to send the message
            except Exception as e:
                print(f"Error sending AI settings as file for bot {self.bot_id}: {e}")
                # If sending as a file fails, try splitting the message
                chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                await ctx.send(f"Your AI settings are too detailed to display in a single message. Splitting into {len(chunks)} parts:")
                for i, chunk in enumerate(chunks):
                    try:
                        await ctx.send(f"Part {i+1}/{len(chunks)}:\n{chunk}")
                    except Exception as chunk_error:
                        print(f"Error sending chunk {i+1} for bot {self.bot_id}: {chunk_error}")
                return  # Return early after sending chunks

        # Send the response normally
        try:
            await ctx.reply(response)
        except discord.HTTPException as e:
            print(f"HTTP Exception when sending AI settings for bot {self.bot_id}: {e}")
            if "Must be 4000 or fewer in length" in str(e) or "Must be 2000 or fewer in length" in str(e):
                try:
                    # Create a text file with the content
                    with open(f'ai_settings_{self.bot_id}.txt', 'w', encoding='utf-8') as f:
                        f.write(response)

                    # Send the file instead
                    await ctx.send(
                        "Your AI settings are too detailed to display in a message. Here's the content as a file:",
                        file=discord.File(f'ai_settings_{self.bot_id}.txt')
                    )
                except Exception as file_error:
                    print(f"Error sending AI settings as file (fallback) for bot {self.bot_id}: {file_error}")
                    # If sending as a file fails, try splitting the message
                    chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                    await ctx.send(f"Your AI settings are too detailed to display in a single message. Splitting into {len(chunks)} parts:")
                    for i, chunk in enumerate(chunks):
                        try:
                            await ctx.send(f"Part {i+1}/{len(chunks)}:\n{chunk}")
                        except Exception as chunk_error:
                            print(f"Error sending chunk {i+1} for bot {self.bot_id}: {chunk_error}")
            else:
                # Log the error but don't re-raise to prevent the command from failing completely
                print(f"Unexpected HTTP error in aisettings command for bot {self.bot_id}: {e}")

    @commands.command(name="ailast")
    async def get_last_response(self, ctx):
        """Retrieve the last AI response that may have failed to send"""
        user_id = ctx.author.id

        # Check if there's a backup file for this user
        backup_dir = 'ai_responses'
        if not os.path.exists(backup_dir):
            await ctx.reply("No backup responses found.")
            return

        # Find the most recent backup file for this user
        user_files = [f for f in os.listdir(backup_dir) if f.startswith(f'response_{user_id}_')]
        if not user_files:
            await ctx.reply("No backup responses found for you.")
            return

        # Sort by timestamp (newest first)
        user_files.sort(reverse=True)
        latest_file = os.path.join(backup_dir, user_files[0])

        try:
            # Read the file content
            with open(latest_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Send as file to avoid length issues
            with open(f'ai_last_response_{self.bot_id}.txt', 'w', encoding='utf-8') as f:
                f.write(content)

            await ctx.send(
                f"Here's your last AI response (from {user_files[0].split('_')[-1].replace('.txt', '')}):",
                file=discord.File(f'ai_last_response_{self.bot_id}.txt')
            )
        except Exception as e:
            await ctx.reply(f"Error retrieving last response: {e}")

    @commands.command(name="aihelp")
    async def ai_help(self, ctx):
        """Get help with AI command issues"""
        prefix = self.bot_config.get("prefix", "!")
        help_text = (
            f"**AI Command Help for {self.bot.user.name}**\n\n"
            f"If you're experiencing issues with the AI command:\n\n"
            f"1. **Message Too Long**: If the AI response is too long, it will be sent as a file attachment.\n"
            f"2. **Error Occurred**: If you see an error message, try using `{prefix}ailast` to retrieve your last AI response.\n"
            f"3. **Response Not Showing**: The AI might be generating a response that's too long. Use `{prefix}ailast` to check.\n\n"
            f"**Available Commands**:\n"
            f"- `{prefix}ai <prompt>` - Get a response from the AI\n"
            f"- `{prefix}ailast` - Retrieve your last AI response\n"
            f"- `{prefix}aiclear` - Clear your conversation history\n"
            f"- `{prefix}aisettings` - View your current AI settings\n"
            f"- `{prefix}aiset <setting> <value>` - Change an AI setting\n"
            f"- `{prefix}aireset` - Reset your AI settings to defaults\n\n"
            f"**New Features**:\n"
            f"- Custom Instructions: Set with `{prefix}aiset custom_instructions <instructions>`\n"
            f"- Character Info: Set with `{prefix}aiset character_info <info>`\n"
            f"- Character Breakdown: Set with `{prefix}aiset character_breakdown true/false`\n"
            f"- Character: Set with `{prefix}aiset character <name>` to replace {{{{char}}}} in the system prompt\n"
        )
        await ctx.reply(help_text)

async def setup_bot(bot_id, bot_config, global_config):
    """Set up and start a bot with the given configuration"""
    # Set up intents
    intents = discord.Intents.default()
    intents.message_content = True

    # Create bot instance
    bot = commands.Bot(command_prefix=bot_config.get("prefix", "!"), intents=intents)

    @bot.event
    async def on_ready():
        print(f'{bot.user.name} (ID: {bot_id}) has connected to Discord!')
        print(f'Bot ID: {bot.user.id}')
        # Set the bot's status based on configuration
        status_type = bot_config.get('status_type', 'listening').lower()
        status_text = bot_config.get('status_text', f"{bot_config.get('prefix', '!')}ai")

        # Map status type to discord.ActivityType
        activity_type = discord.ActivityType.listening  # Default
        if status_type == 'playing':
            activity_type = discord.ActivityType.playing
        elif status_type == 'watching':
            activity_type = discord.ActivityType.watching
        elif status_type == 'streaming':
            activity_type = discord.ActivityType.streaming
        elif status_type == 'competing':
            activity_type = discord.ActivityType.competing

        # Set the presence
        await bot.change_presence(activity=discord.Activity(
            type=activity_type,
            name=status_text
        ))
        print(f"Bot {bot_id} status set to '{status_type.capitalize()} {status_text}'")

    # Add the AI cog
    await bot.add_cog(SimplifiedAICog(bot, bot_id, bot_config, global_config))

    # Store the bot instance
    bots[bot_id] = bot

    # Return the bot instance
    return bot

async def start_bot(bot_id):
    """Start a bot with the given ID"""
    if bot_id not in bots:
        print(f"Bot {bot_id} not found")
        return False

    bot = bots[bot_id]
    config = load_config()

    # Find the bot config
    bot_config = None
    for bc in config.get("bots", []):
        if bc.get("id") == bot_id:
            bot_config = bc
            break

    if not bot_config:
        print(f"Configuration for bot {bot_id} not found")
        return False

    token = bot_config.get("token")
    if not token:
        print(f"Token for bot {bot_id} not set")
        return False

    # Start the bot
    try:
        await bot.start(token)
        return True
    except Exception as e:
        print(f"Error starting bot {bot_id}: {e}")
        return False

def run_bot_in_thread(bot_id):
    """Run a bot in a separate thread"""
    async def _run_bot():
        config = load_config()

        # Find the bot config
        bot_config = None
        for bc in config.get("bots", []):
            if bc.get("id") == bot_id:
                bot_config = bc
                break

        if not bot_config:
            print(f"Configuration for bot {bot_id} not found")
            return

        # Set up the bot
        bot = await setup_bot(bot_id, bot_config, config)

        # Start the bot
        token = bot_config.get("token")
        if not token:
            print(f"Token for bot {bot_id} not set")
            return

        try:
            await bot.start(token)
        except Exception as e:
            print(f"Error running bot {bot_id}: {e}")

    # Create and start the thread
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=lambda: loop.run_until_complete(_run_bot()), daemon=True)
    thread.start()
    return thread

def start_all_bots():
    """Start all configured bots in separate threads"""
    config = load_config()
    threads = []

    for bot_config in config.get("bots", []):
        bot_id = bot_config.get("id")
        if bot_id:
            thread = run_bot_in_thread(bot_id)
            threads.append((bot_id, thread))
            print(f"Started bot {bot_id} in a separate thread")

    return threads

if __name__ == "__main__":
    # If run directly, start all bots
    bot_threads = start_all_bots()

    try:
        # Keep the main thread alive
        while True:
            # Check if any threads have died
            for bot_id, thread in bot_threads:
                if not thread.is_alive():
                    print(f"Thread for bot {bot_id} died, restarting...")
                    new_thread = run_bot_in_thread(bot_id)
                    bot_threads.remove((bot_id, thread))
                    bot_threads.append((bot_id, new_thread))

            # Sleep to avoid high CPU usage
            import time
            time.sleep(60)
    except KeyboardInterrupt:
        print("Stopping all bots...")
        # The threads are daemon threads, so they will be terminated when the main thread exits
