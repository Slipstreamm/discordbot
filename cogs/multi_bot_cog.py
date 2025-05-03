import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import subprocess
import sys
import threading
import asyncio
import psutil
from typing import Dict, List, Optional, Literal

# Import the multi_bot module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import multi_bot

# Configuration file path
CONFIG_FILE = "data/multi_bot_config.json"

# Bot IDs
NERU_BOT_ID = "neru"
MIKU_BOT_ID = "miku"

class MultiBotCog(commands.Cog, name="Multi Bot"):
    """Cog for managing multiple bot instances"""

    def __init__(self, bot):
        self.bot = bot
        self.bot_processes = {}  # Store subprocess objects
        self.bot_threads = {}    # Store thread objects

        # Create the main command group for this cog
        self.multibot_group = app_commands.Group(
            name="multibot",
            description="Manage multiple bot instances"
        )

        # Create subgroups
        self.config_group = app_commands.Group(
            name="config",
            description="Configure bot settings",
            parent=self.multibot_group
        )

        self.status_group = app_commands.Group(
            name="status",
            description="Manage bot status",
            parent=self.multibot_group
        )

        self.manage_group = app_commands.Group(
            name="manage",
            description="Add or remove bots",
            parent=self.multibot_group
        )

        # Register all commands
        self.register_commands()

        # Add command groups to the bot's tree
        self.bot.tree.add_command(self.multibot_group)

    def cog_unload(self):
        """Stop all bots when the cog is unloaded"""
        self.stop_all_bots()

    # --- Legacy prefix commands (kept for backward compatibility) ---
    @commands.command(name="startbot")
    @commands.is_owner()
    async def start_bot(self, ctx, bot_id: str):
        """Start a specific bot (Owner only)"""
        result = await self._start_bot_logic(bot_id)
        await ctx.send(result)

    # --- Main multibot commands ---
    async def multibot_start_callback(self, interaction: discord.Interaction, bot_id: str):
        """Start a specific bot (Owner only)"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command can only be used by the bot owner.", ephemeral=True)
            return

        result = await self._start_bot_logic(bot_id)
        await interaction.response.send_message(result, ephemeral=True)

    async def multibot_stop_callback(self, interaction: discord.Interaction, bot_id: str):
        """Stop a specific bot (Owner only)"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command can only be used by the bot owner.", ephemeral=True)
            return

        result = await self._stop_bot_logic(bot_id)
        await interaction.response.send_message(result, ephemeral=True)

    async def multibot_startall_callback(self, interaction: discord.Interaction):
        """Start all configured bots (Owner only)"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command can only be used by the bot owner.", ephemeral=True)
            return

        result = await self._startall_bots_logic()
        await interaction.response.send_message(result, ephemeral=True)

    async def multibot_stopall_callback(self, interaction: discord.Interaction):
        """Stop all running bots (Owner only)"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command can only be used by the bot owner.", ephemeral=True)
            return

        result = await self._stopall_bots_logic()
        await interaction.response.send_message(result, ephemeral=True)

    async def multibot_list_callback(self, interaction: discord.Interaction):
        """List all configured bots and their status (Owner only)"""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command can only be used by the bot owner.", ephemeral=True)
            return

        embed = await self._list_bots_logic()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Register commands in __init__
    def register_commands(self):
        """Register all commands for this cog"""
        # Start command
        start_command = app_commands.Command(
            name="start",
            description="Start a specific bot",
            callback=self.multibot_start_callback,
            parent=self.multibot_group
        )
        self.multibot_group.add_command(start_command)

        # Stop command
        stop_command = app_commands.Command(
            name="stop",
            description="Stop a specific bot",
            callback=self.multibot_stop_callback,
            parent=self.multibot_group
        )
        self.multibot_group.add_command(stop_command)

        # Start all command
        startall_command = app_commands.Command(
            name="startall",
            description="Start all configured bots",
            callback=self.multibot_startall_callback,
            parent=self.multibot_group
        )
        self.multibot_group.add_command(startall_command)

        # Stop all command
        stopall_command = app_commands.Command(
            name="stopall",
            description="Stop all running bots",
            callback=self.multibot_stopall_callback,
            parent=self.multibot_group
        )
        self.multibot_group.add_command(stopall_command)

        # List command
        list_command = app_commands.Command(
            name="list",
            description="List all configured bots and their status",
            callback=self.multibot_list_callback,
            parent=self.multibot_group
        )
        self.multibot_group.add_command(list_command)

    async def _start_bot_logic(self, bot_id: str) -> str:
        """Common logic for starting a bot"""
        # Check if the bot is already running
        if bot_id in self.bot_processes and self.bot_processes[bot_id].poll() is None:
            return f"Bot {bot_id} is already running."

        if bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive():
            return f"Bot {bot_id} is already running in a thread."

        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            return f"Configuration file not found: {CONFIG_FILE}"

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Find the bot configuration
            bot_config = None
            for bc in config.get("bots", []):
                if bc.get("id") == bot_id:
                    bot_config = bc
                    break

            if not bot_config:
                return f"Bot {bot_id} not found in configuration."

            # Check if the token is set
            if not bot_config.get("token"):
                return f"Token for bot {bot_id} is not set in the configuration."

            # Start the bot in a separate thread
            thread = multi_bot.run_bot_in_thread(bot_id)
            self.bot_threads[bot_id] = thread

            return f"Bot {bot_id} started successfully."

        except Exception as e:
            return f"Error starting bot {bot_id}: {e}"

    @commands.command(name="stopbot")
    @commands.is_owner()
    async def stop_bot(self, ctx, bot_id: str):
        """Stop a specific bot (Owner only)"""
        result = await self._stop_bot_logic(bot_id)
        await ctx.send(result)

    async def _stop_bot_logic(self, bot_id: str) -> str:
        """Common logic for stopping a bot"""
        # Check if the bot is running as a process
        if bot_id in self.bot_processes:
            process = self.bot_processes[bot_id]
            if process.poll() is None:  # Process is still running
                try:
                    # Try to terminate gracefully
                    process.terminate()
                    # Wait a bit for it to terminate
                    await asyncio.sleep(2)
                    # If still running, kill it
                    if process.poll() is None:
                        process.kill()

                    del self.bot_processes[bot_id]
                    return f"Bot {bot_id} stopped."
                except Exception as e:
                    return f"Error stopping bot {bot_id}: {e}"

        # Check if the bot is running in a thread
        if bot_id in self.bot_threads:
            # We can't directly stop a thread in Python, but we can try to find and kill the process
            thread = self.bot_threads[bot_id]
            if thread.is_alive():
                try:
                    # Find and kill the process by looking for Python processes with multi_bot.py
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            cmdline = proc.info['cmdline']
                            if cmdline and 'python' in cmdline[0].lower() and any('multi_bot.py' in arg for arg in cmdline if arg):
                                # This is likely our bot process
                                proc.terminate()
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            pass

                    # Remove from our tracking
                    del self.bot_threads[bot_id]

                    # Note: The thread itself might still be alive but will eventually notice the process is gone
                    return f"Bot {bot_id} stopped."
                except Exception as e:
                    return f"Error stopping bot {bot_id}: {e}"

        return f"Bot {bot_id} is not running."

    @commands.command(name="startallbots")
    @commands.is_owner()
    async def start_all_bots(self, ctx):
        """Start all configured bots (Owner only)"""
        result = await self._startall_bots_logic()
        await ctx.send(result)

    async def _startall_bots_logic(self) -> str:
        """Common logic for starting all bots"""
        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            return f"Configuration file not found: {CONFIG_FILE}"

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            started_count = 0
            failed_count = 0
            already_running = 0

            for bot_config in config.get("bots", []):
                bot_id = bot_config.get("id")
                if not bot_id:
                    continue

                # Check if already running
                if (bot_id in self.bot_processes and self.bot_processes[bot_id].poll() is None) or \
                   (bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive()):
                    already_running += 1
                    continue

                # Check if token is set
                if not bot_config.get("token"):
                    failed_count += 1
                    continue

                try:
                    # Start the bot in a separate thread
                    thread = multi_bot.run_bot_in_thread(bot_id)
                    self.bot_threads[bot_id] = thread
                    started_count += 1
                except Exception as e:
                    failed_count += 1

            status_message = f"Started {started_count} bots."
            if already_running > 0:
                status_message += f" {already_running} bots were already running."
            if failed_count > 0:
                status_message += f" Failed to start {failed_count} bots."

            return status_message

        except Exception as e:
            return f"Error starting bots: {e}"

    @commands.command(name="stopallbots")
    @commands.is_owner()
    async def stop_all_bots(self, ctx):
        """Stop all running bots (Owner only)"""
        result = await self._stopall_bots_logic()
        await ctx.send(result)

    async def _stopall_bots_logic(self) -> str:
        """Common logic for stopping all bots"""
        stopped_count = 0
        failed_count = 0

        # Stop process-based bots
        for bot_id, process in list(self.bot_processes.items()):
            if process.poll() is None:  # Process is still running
                try:
                    # Try to terminate gracefully
                    process.terminate()
                    # Wait a bit for it to terminate
                    await asyncio.sleep(1)
                    # If still running, kill it
                    if process.poll() is None:
                        process.kill()

                    del self.bot_processes[bot_id]
                    stopped_count += 1
                except Exception as e:
                    failed_count += 1

        # Stop thread-based bots
        for bot_id, thread in list(self.bot_threads.items()):
            if thread.is_alive():
                try:
                    # Find and kill the process
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            cmdline = proc.info['cmdline']
                            if cmdline and 'python' in cmdline[0].lower() and any('multi_bot.py' in arg for arg in cmdline if arg):
                                # This is likely our bot process
                                proc.terminate()
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            pass

                    del self.bot_threads[bot_id]
                    stopped_count += 1
                except Exception as e:
                    failed_count += 1

        status_message = f"Stopped {stopped_count} bots."
        if failed_count > 0:
            status_message += f" Failed to stop {failed_count} bots."

        return status_message

    def stop_all_bots(self):
        """Stop all running bots (internal method)"""
        # Stop process-based bots
        for bot_id, process in list(self.bot_processes.items()):
            if process.poll() is None:  # Process is still running
                try:
                    # Try to terminate gracefully
                    process.terminate()
                    # Wait a bit for it to terminate
                    import time
                    time.sleep(1)
                    # If still running, kill it
                    if process.poll() is None:
                        process.kill()
                except Exception as e:
                    print(f"Error stopping bot {bot_id}: {e}")

        # Stop thread-based bots
        for bot_id, thread in list(self.bot_threads.items()):
            if thread.is_alive():
                try:
                    # Find and kill the process
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            cmdline = proc.info['cmdline']
                            if cmdline and 'python' in cmdline[0].lower() and any('multi_bot.py' in arg for arg in cmdline if arg):
                                # This is likely our bot process
                                proc.terminate()
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            pass
                except Exception as e:
                    print(f"Error stopping bot {bot_id}: {e}")

    @commands.command(name="listbots")
    @commands.is_owner()
    async def list_bots(self, ctx):
        """List all configured bots and their status (Owner only)"""
        embed = await self._list_bots_logic()
        await ctx.send(embed=embed)

    async def _list_bots_logic(self) -> discord.Embed:
        """Common logic for listing all bots"""
        # Create an embed to display the bot list
        embed = discord.Embed(
            title="Configured Bots",
            description="List of all configured bots and their status",
            color=discord.Color.blue()
        )

        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            embed.description = f"Configuration file not found: {CONFIG_FILE}"
            return embed

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            bot_list = []

            for bot_config in config.get("bots", []):
                bot_id = bot_config.get("id")
                if not bot_id:
                    continue

                # Check if running
                is_running = False
                run_type = ""

                if bot_id in self.bot_processes and self.bot_processes[bot_id].poll() is None:
                    is_running = True
                    run_type = "process"
                elif bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive():
                    is_running = True
                    run_type = "thread"

                # Get other info
                prefix = bot_config.get("prefix", "!")
                system_prompt = bot_config.get("system_prompt", "Default system prompt")
                if len(system_prompt) > 50:
                    system_prompt = system_prompt[:47] + "..."

                # Get status settings
                status_type = bot_config.get("status_type", "listening")
                status_text = bot_config.get("status_text", f"{prefix}ai")

                run_status = f"Running ({run_type})" if is_running else "Stopped"

                bot_list.append(f"**Bot ID**: {bot_id}\n**Status**: {run_status}\n**Prefix**: {prefix}\n**Activity**: {status_type.capitalize()} {status_text}\n**System Prompt**: {system_prompt}\n")

            if not bot_list:
                embed.description = "No bots configured."
                return embed

            for i, bot_info in enumerate(bot_list):
                embed.add_field(
                    name=f"Bot {i+1}",
                    value=bot_info,
                    inline=False
                )

            return embed

        except Exception as e:
            embed.description = f"Error listing bots: {e}"
            return embed

    @commands.command(name="setbottoken")
    @commands.is_owner()
    async def set_bot_token(self, ctx, bot_id: str, *, token: str):
        """Set the token for a bot (Owner only)"""
        # Delete the message to protect the token
        try:
            await ctx.message.delete()
        except:
            pass

        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Find the bot configuration
            found = False
            for bot_config in config.get("bots", []):
                if bot_config.get("id") == bot_id:
                    bot_config["token"] = token
                    found = True
                    break

            if not found:
                await ctx.send(f"Bot {bot_id} not found in configuration.")
                return

            # Save the updated configuration
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            await ctx.send(f"Token for bot {bot_id} has been updated. The message with your token has been deleted for security.")

        except Exception as e:
            await ctx.send(f"Error setting bot token: {e}")

    @commands.command(name="setbotprompt")
    @commands.is_owner()
    async def set_bot_prompt(self, ctx, bot_id: str, *, system_prompt: str):
        """Set the system prompt for a bot (Owner only)"""
        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Find the bot configuration
            found = False
            for bot_config in config.get("bots", []):
                if bot_config.get("id") == bot_id:
                    bot_config["system_prompt"] = system_prompt
                    found = True
                    break

            if not found:
                await ctx.send(f"Bot {bot_id} not found in configuration.")
                return

            # Save the updated configuration
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            await ctx.send(f"System prompt for bot {bot_id} has been updated.")

        except Exception as e:
            await ctx.send(f"Error setting bot system prompt: {e}")

    @commands.command(name="setbotprefix")
    @commands.is_owner()
    async def set_bot_prefix(self, ctx, bot_id: str, prefix: str):
        """Set the command prefix for a bot (Owner only)"""
        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Find the bot configuration
            found = False
            for bot_config in config.get("bots", []):
                if bot_config.get("id") == bot_id:
                    bot_config["prefix"] = prefix
                    found = True
                    break

            if not found:
                await ctx.send(f"Bot {bot_id} not found in configuration.")
                return

            # Save the updated configuration
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            await ctx.send(f"Command prefix for bot {bot_id} has been updated to '{prefix}'.")

            # Notify that the bot needs to be restarted for the change to take effect
            await ctx.send("Note: You need to restart the bot for this change to take effect.")

        except Exception as e:
            await ctx.send(f"Error setting bot prefix: {e}")

    @commands.command(name="setapikey")
    @commands.is_owner()
    async def set_api_key(self, ctx, *, api_key: str):
        """Set the API key for all bots (Owner only)"""
        # Delete the message to protect the API key
        try:
            await ctx.message.delete()
        except:
            pass

        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Update the API key
            config["api_key"] = api_key

            # Save the updated configuration
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            await ctx.send("API key has been updated. The message with your API key has been deleted for security.")

        except Exception as e:
            await ctx.send(f"Error setting API key: {e}")

    @commands.command(name="setapiurl")
    @commands.is_owner()
    async def set_api_url(self, ctx, *, api_url: str):
        """Set the API URL for all bots (Owner only)"""
        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Update the API URL
            config["api_url"] = api_url

            # Save the updated configuration
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            await ctx.send(f"API URL has been updated to '{api_url}'.")

        except Exception as e:
            await ctx.send(f"Error setting API URL: {e}")

    @commands.command(name="setbotstatus")
    @commands.is_owner()
    async def set_bot_status(self, ctx, bot_id: str, status_type: str, *, status_text: str):
        """Set the status for a bot (Owner only)

        Status types:
        - playing: "Playing {status_text}"
        - listening: "Listening to {status_text}"
        - watching: "Watching {status_text}"
        - streaming: "Streaming {status_text}"
        - competing: "Competing in {status_text}"
        """
        # Validate status type
        valid_status_types = ["playing", "listening", "watching", "streaming", "competing"]
        status_type = status_type.lower()

        if status_type not in valid_status_types:
            await ctx.send(f"Invalid status type: '{status_type}'. Valid types are: {', '.join(valid_status_types)}")
            return

        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)

            # Find the bot configuration
            found = False
            for bot_config in config.get("bots", []):
                if bot_config.get("id") == bot_id:
                    bot_config["status_type"] = status_type
                    bot_config["status_text"] = status_text
                    found = True
                    break

            if not found:
                await ctx.send(f"Bot {bot_id} not found in configuration.")
                return

            # Save the updated configuration
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

            await ctx.send(f"Status for bot {bot_id} has been updated to '{status_type.capitalize()} {status_text}'.")

            # Check if the bot is running and update its status
            if bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive():
                # We can't directly update the status of a bot running in a thread
                await ctx.send("Note: You need to restart the bot for this change to take effect.")

        except Exception as e:
            await ctx.send(f"Error setting bot status: {e}")

    @commands.command(name="setallbotstatus")
    @commands.is_owner()
    async def set_all_bots_status(self, ctx, status_type: str, *, status_text: str):
        """Set the status for all bots (Owner only)

        Status types:
        - playing: "Playing {status_text}"
        - listening: "Listening to {status_text}"
        - watching: "Watching {status_text}"
        - streaming: "Streaming {status_text}"
        - competing: "Competing in {status_text}"
        """
        # Validate status type
        valid_status_types = ["playing", "listening", "watching", "streaming", "competing"]
        status_type = status_type.lower()

        if status_type not in valid_status_types:
            await ctx.send(f"Invalid status type: '{status_type}'. Valid types are: {', '.join(valid_status_types)}")
            return

        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)

            # Update all bot configurations
            updated_count = 0
            for bot_config in config.get("bots", []):
                bot_config["status_type"] = status_type
                bot_config["status_text"] = status_text
                updated_count += 1

            if updated_count == 0:
                await ctx.send("No bots found in configuration.")
                return

            # Save the updated configuration
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

            await ctx.send(f"Status for all {updated_count} bots has been updated to '{status_type.capitalize()} {status_text}'.")

            # Check if any bots are running
            running_bots = [bot_id for bot_id, thread in self.bot_threads.items() if thread.is_alive()]
            if running_bots:
                await ctx.send(f"Note: You need to restart the following bots for this change to take effect: {', '.join(running_bots)}")

        except Exception as e:
            await ctx.send(f"Error setting all bot statuses: {e}")

    @commands.command(name="addbot")
    @commands.is_owner()
    async def add_bot(self, ctx, bot_id: str, prefix: str = "!"):
        """Add a new bot configuration (Owner only)"""
        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)

            # Check if bot_id already exists
            for bot_config in config.get("bots", []):
                if bot_config.get("id") == bot_id:
                    await ctx.send(f"Bot with ID '{bot_id}' already exists.")
                    return

            # Create new bot configuration
            new_bot = {
                "id": bot_id,
                "token": "",
                "prefix": prefix,
                "system_prompt": "You are a helpful assistant.",
                "model": "deepseek/deepseek-chat-v3-0324:free",
                "max_tokens": 1000,
                "temperature": 0.7,
                "timeout": 60,
                "status_type": "listening",
                "status_text": f"{prefix}ai"
            }

            # Add to the configuration
            if "bots" not in config:
                config["bots"] = []

            config["bots"].append(new_bot)

            # Save the updated configuration
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

            await ctx.send(f"Bot '{bot_id}' added to configuration with prefix '{prefix}'.")
            await ctx.send("Note: You need to set a token for this bot using the `!setbottoken` command before starting it.")

        except Exception as e:
            await ctx.send(f"Error adding bot: {e}")

    @commands.command(name="removebot")
    @commands.is_owner()
    async def remove_bot(self, ctx, bot_id: str):
        """Remove a bot configuration (Owner only)"""
        # Load the configuration
        if not os.path.exists(CONFIG_FILE):
            await ctx.send(f"Configuration file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)

            # Check if the bot is running and stop it
            if (bot_id in self.bot_processes and self.bot_processes[bot_id].poll() is None) or \
               (bot_id in self.bot_threads and self.bot_threads[bot_id].is_alive()):
                await self.stop_bot(ctx, bot_id)

            # Find and remove the bot configuration
            found = False
            if "bots" in config:
                config["bots"] = [bc for bc in config["bots"] if bc.get("id") != bot_id]
                found = True

            if not found:
                await ctx.send(f"Bot '{bot_id}' not found in configuration.")
                return

            # Save the updated configuration
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

            await ctx.send(f"Bot '{bot_id}' removed from configuration.")

        except Exception as e:
            await ctx.send(f"Error removing bot: {e}")

async def setup(bot):
    await bot.add_cog(MultiBotCog(bot))
