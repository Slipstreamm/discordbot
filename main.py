import threading
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import sys
import asyncio
import subprocess
import importlib.util
from commands import load_all_cogs, reload_all_cogs
from error_handler import handle_error, patch_discord_methods, store_interaction_content
from utils import reload_script

# Import the unified API service runner and the sync API module
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from discordbot.run_unified_api import start_api_in_thread
import discord_bot_sync_api # Import the module to set the cog instance

# Check if API dependencies are available
try:
    import uvicorn
    API_AVAILABLE = True
except ImportError:
    print("uvicorn not available. API service will not be available.")
    API_AVAILABLE = False

# Load environment variables from .env file
load_dotenv()

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create bot instance with command prefix '!' and enable the application commands
bot = commands.Bot(command_prefix='!', intents=intents)
bot.owner_id = int(os.getenv('OWNER_USER_ID'))

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Bot ID: {bot.user.id}')
    # Set the bot's status
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!help"))
    print("Bot status set to 'Listening to !help'")

    # Patch Discord methods to store message content
    try:
        patch_discord_methods()
        print("Discord methods patched to store message content for error handling")

        # Make the store_interaction_content function available globally
        import builtins
        builtins.store_interaction_content = store_interaction_content
        print("Made store_interaction_content available globally")
    except Exception as e:
        print(f"Warning: Failed to patch Discord methods: {e}")
        import traceback
        traceback.print_exc()
    try:
        print("Starting command sync process...")
        # List commands before sync
        commands_before = [cmd.name for cmd in bot.tree.get_commands()]
        print(f"Commands before sync: {commands_before}")

        # Perform sync
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

        # List commands after sync
        commands_after = [cmd.name for cmd in bot.tree.get_commands()]
        print(f"Commands after sync: {commands_after}")

    except Exception as e:
        print(f"Failed to sync commands: {e}")
        import traceback
        traceback.print_exc()

@bot.event
async def on_shard_disconnect(shard_id):
    print(f"Shard {shard_id} disconnected. Attempting to reconnect...")
    try:
        await bot.connect(reconnect=True)
        print(f"Shard {shard_id} reconnected successfully.")
    except Exception as e:
        print(f"Failed to reconnect shard {shard_id}: {e}")

# Error handling
@bot.event
async def on_command_error(ctx, error):
    await handle_error(ctx, error)

@bot.tree.error
async def on_app_command_error(interaction, error):
    await handle_error(interaction, error)

@commands.command(name="restart", help="Restarts the bot. Owner only.")
@commands.is_owner()
async def restart(ctx):
    """Restarts the bot. (Owner Only)"""
    await ctx.send("Restarting the bot...")
    await bot.close()  # Gracefully close the bot
    os.execv(sys.executable, [sys.executable] + sys.argv)  # Restart the bot process

bot.add_command(restart)

@commands.command(name="gitpull_restart", help="Pulls latest code from git and restarts the bot. Owner only.")
@commands.is_owner()
async def gitpull_restart(ctx):
    """Pulls latest code from git and restarts the bot. (Owner Only)"""
    await ctx.send("Pulling latest code from git...")
    proc = await asyncio.create_subprocess_exec(
        "git", "pull",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode().strip() + "\n" + stderr.decode().strip()
    if "unstaged changes" in output or "Please commit your changes" in output:
        await ctx.send("Unstaged changes detected. Committing changes before pulling...")
        commit_proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-am", "Git pull and restart command",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        commit_stdout, commit_stderr = await commit_proc.communicate()
        commit_output = commit_stdout.decode().strip() + "\n" + commit_stderr.decode().strip()
        await ctx.send(f"Committed changes:\n```\n{commit_output}\n```Trying git pull again...")
        proc = await asyncio.create_subprocess_exec(
            "git", "pull",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip() + "\n" + stderr.decode().strip()
    if proc.returncode == 0:
        await ctx.send(f"Git pull successful:\n```\n{output}\n```Restarting the bot...")
        await bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    else:
        await ctx.send(f"Git pull failed:\n```\n{output}\n```")

bot.add_command(gitpull_restart)

@commands.command(name="reload_cogs", help="Reloads all cogs. Owner only.")
@commands.is_owner()
async def reload_cogs(ctx):
    """Reloads all cogs. (Owner Only)"""
    await ctx.send("Reloading all cogs...")
    reloaded_cogs, failed_reload = await reload_all_cogs(bot)
    if reloaded_cogs:
        await ctx.send(f"Successfully reloaded cogs: {', '.join(reloaded_cogs)}")
    if failed_reload:
        await ctx.send(f"Failed to reload cogs: {', '.join(failed_reload)}")

bot.add_command(reload_cogs)

@commands.command(name="gitpull_reload", help="Pulls latest code from git and reloads all cogs. Owner only.")
@commands.is_owner()
async def gitpull_reload(ctx):
    """Pulls latest code from git and reloads all cogs. (Owner Only)"""
    await ctx.send("Pulling latest code from git...")
    proc = await asyncio.create_subprocess_exec(
        "git", "pull",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode().strip() + "\n" + stderr.decode().strip()
    if "unstaged changes" in output or "Please commit your changes" in output:
        await ctx.send("Unstaged changes detected. Committing changes before pulling...")
        commit_proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-am", "Git pull and reload command",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        commit_stdout, commit_stderr = await commit_proc.communicate()
        commit_output = commit_stdout.decode().strip() + "\n" + commit_stderr.decode().strip()
        await ctx.send(f"Committed changes:\n```\n{commit_output}\n```Trying git pull again...")
        proc = await asyncio.create_subprocess_exec(
            "git", "pull",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip() + "\n" + stderr.decode().strip()
    if proc.returncode == 0:
        await ctx.send(f"Git pull successful:\n```\n{output}\n```Reloading all cogs...")
        reloaded_cogs, failed_reload = await reload_all_cogs(bot)
        if reloaded_cogs:
            await ctx.send(f"Successfully reloaded cogs: {', '.join(reloaded_cogs)}")
        if failed_reload:
            await ctx.send(f"Failed to reload cogs: {', '.join(failed_reload)}")
    else:
        await ctx.send(f"Git pull failed:\n```\n{output}\n```")

bot.add_command(gitpull_reload)




# The unified API service is now handled by run_unified_api.py

async def main():
    """Main async function to load cogs and start the bot."""
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        raise ValueError("No token found. Make sure to set DISCORD_TOKEN in your .env file.")

    # Start Flask server as a separate process
    flask_process = subprocess.Popen([sys.executable, "flask_server.py"], cwd=os.path.dirname(__file__))

    # Start the unified API service in a separate thread if available
    api_thread = None
    if API_AVAILABLE:
        print("Starting unified API service...")
        try:
            # Start the API in a separate thread
            api_thread = start_api_in_thread()
            print("Unified API service started successfully")
        except Exception as e:
            print(f"Failed to start unified API service: {e}")

    # Configure OAuth settings from environment variables
    oauth_host = os.getenv("OAUTH_HOST", "0.0.0.0")
    oauth_port = int(os.getenv("OAUTH_PORT", "8080"))
    oauth_redirect_uri = os.getenv("DISCORD_REDIRECT_URI", f"http://{oauth_host}:{oauth_port}/oauth/callback")

    # Update the OAuth redirect URI in the environment
    os.environ["DISCORD_REDIRECT_URI"] = oauth_redirect_uri
    print(f"OAuth redirect URI set to: {oauth_redirect_uri}")

    try:
        async with bot:
            # Load all cogs from the 'cogs' directory
            await load_all_cogs(bot)

            # --- Share GurtCog instance with the sync API ---
            try:
                gurt_cog = bot.get_cog("Gurt") # Get the loaded GurtCog instance
                if gurt_cog:
                    discord_bot_sync_api.gurt_cog_instance = gurt_cog
                    print("Successfully shared GurtCog instance with discord_bot_sync_api.")
                else:
                    print("Warning: GurtCog not found after loading cogs. Stats API might not work.")
            except Exception as e:
                print(f"Error sharing GurtCog instance: {e}")
            # ------------------------------------------------

            # Start the bot using start() for async context
            await bot.start(TOKEN)
    finally:
        # Terminate the Flask server process when the bot stops
        flask_process.terminate()
        print("Flask server process terminated.")

# Run the main async function
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"An error occurred running the bot: {e}")
