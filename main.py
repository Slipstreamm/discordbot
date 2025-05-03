import threading
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import sys
import asyncio
import subprocess
import importlib.util
import argparse
import logging # Add logging
from commands import load_all_cogs, reload_all_cogs
from error_handler import handle_error, patch_discord_methods, store_interaction_content
from utils import reload_script
import settings_manager # Import the settings manager

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

# --- Constants ---
DEFAULT_PREFIX = "!"
CORE_COGS = {'SettingsCog', 'HelpCog'} # Cogs that cannot be disabled

# --- Dynamic Prefix Function ---
async def get_prefix(bot_instance, message):
    """Determines the command prefix based on guild settings or default."""
    if not message.guild:
        # Use default prefix in DMs
        return commands.when_mentioned_or(DEFAULT_PREFIX)(bot_instance, message)

    # Fetch prefix from settings manager (cache first, then DB)
    prefix = await settings_manager.get_guild_prefix(message.guild.id, DEFAULT_PREFIX)
    return commands.when_mentioned_or(prefix)(bot_instance, message)

# --- Bot Setup ---
# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create bot instance with the dynamic prefix function
bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.owner_id = int(os.getenv('OWNER_USER_ID'))
bot.core_cogs = CORE_COGS # Attach core cogs list to bot instance

# --- Logging Setup ---
# Configure logging (adjust level and format as needed)
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__) # Logger for main.py

# --- Events ---
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

# Error handling - Updated to handle custom check failures
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CogDisabledError):
        await ctx.send(str(error), ephemeral=True) # Send the error message from the exception
        log.warning(f"Command '{ctx.command.qualified_name}' blocked for user {ctx.author.id} in guild {ctx.guild.id}: {error}")
    elif isinstance(error, CommandPermissionError):
        await ctx.send(str(error), ephemeral=True) # Send the error message from the exception
        log.warning(f"Command '{ctx.command.qualified_name}' blocked for user {ctx.author.id} in guild {ctx.guild.id}: {error}")
    else:
        # Pass other errors to the original handler
        await handle_error(ctx, error)

@bot.tree.error
async def on_app_command_error(interaction, error):
    await handle_error(interaction, error)

# --- Global Command Checks ---

# Need to import SettingsCog to access CORE_COGS, or define CORE_COGS here.
# Let's import it, assuming it's safe to do so at the top level.
# If it causes circular imports, CORE_COGS needs to be defined elsewhere or passed differently.
try:
    from discordbot.cogs import settings_cog # Import the cog itself
except ImportError:
    log.error("Could not import settings_cog.py for CORE_COGS definition. Cog checks might fail.")
    settings_cog = None # Define as None to avoid NameError later

class CogDisabledError(commands.CheckFailure):
    """Custom exception for disabled cogs."""
    def __init__(self, cog_name):
        self.cog_name = cog_name
        super().__init__(f"The module `{cog_name}` is disabled in this server.")

class CommandPermissionError(commands.CheckFailure):
    """Custom exception for insufficient command permissions based on roles."""
    def __init__(self, command_name):
        self.command_name = command_name
        super().__init__(f"You do not have the required role to use the command `{command_name}`.")

@bot.before_invoke
async def global_command_checks(ctx: commands.Context):
    """Global check run before any command invocation."""
    # Ignore checks for DMs (or apply different logic if needed)
    if not ctx.guild:
        return

    # Ignore checks for the bot owner
    if await bot.is_owner(ctx.author):
        return

    command = ctx.command
    if not command: # Should not happen with prefix commands, but good practice
        return

    cog = command.cog
    cog_name = cog.qualified_name if cog else None
    command_name = command.qualified_name
    guild_id = ctx.guild.id

    # Ensure author is a Member to get roles
    if not isinstance(ctx.author, discord.Member):
        log.warning(f"Could not perform permission check for user {ctx.author.id} (not a Member object). Allowing command '{command_name}'.")
        return # Cannot check roles if not a Member object

    member_roles_ids = [role.id for role in ctx.author.roles]

    # 1. Check if the Cog is enabled
    # Use CORE_COGS attached to the bot instance
    if cog_name and cog_name not in bot.core_cogs: # Don't disable core cogs
        # Assuming default is True if not explicitly set in DB
        is_enabled = await settings_manager.is_cog_enabled(guild_id, cog_name, default_enabled=True)
        if not is_enabled:
            log.warning(f"Command '{command_name}' blocked in guild {guild_id}: Cog '{cog_name}' is disabled.")
            raise CogDisabledError(cog_name)

    # 2. Check command permissions based on roles
    # This check only applies if specific permissions HAVE been set for this command.
    # If no permissions are set in the DB, check_command_permission returns True.
    has_perm = await settings_manager.check_command_permission(guild_id, command_name, member_roles_ids)
    if not has_perm:
        log.warning(f"Command '{command_name}' blocked for user {ctx.author.id} in guild {guild_id}: Insufficient role permissions.")
        raise CommandPermissionError(command_name)

    # If both checks pass, the command proceeds.
    log.debug(f"Command '{command_name}' passed global checks for user {ctx.author.id} in guild {guild_id}.")


# --- Bot Commands ---

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
    # Access the disable_ai flag from the bot instance or re-parse args if needed
    # For simplicity, assume disable_ai is accessible; otherwise, need a way to pass it.
    # Let's add it to the bot object for easier access later.
    skip_list = getattr(bot, 'ai_cogs_to_skip', [])
    await ctx.send(f"Reloading all cogs... (Skipping: {', '.join(skip_list) or 'None'})")
    reloaded_cogs, failed_reload = await reload_all_cogs(bot, skip_cogs=skip_list)
    if reloaded_cogs:
        await ctx.send(f"Successfully reloaded cogs: {', '.join(reloaded_cogs)}")
    if failed_reload:
        await ctx.send(f"Failed to reload cogs: {', '.join(failed_reload)}")

bot.add_command(reload_cogs)

@commands.command(name="gitpull_reload", help="Pulls latest code from git and reloads all cogs. Owner only.")
@commands.is_owner()
async def gitpull_reload(ctx):
    """Pulls latest code from git and reloads all cogs. (Owner Only)"""
    # Access the disable_ai flag from the bot instance or re-parse args if needed
    skip_list = getattr(bot, 'ai_cogs_to_skip', [])
    await ctx.send(f"Pulling latest code from git... (Will skip reloading: {', '.join(skip_list) or 'None'})")
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
        reloaded_cogs, failed_reload = await reload_all_cogs(bot, skip_cogs=skip_list)
        if reloaded_cogs:
            await ctx.send(f"Successfully reloaded cogs: {', '.join(reloaded_cogs)}")
        if failed_reload:
            await ctx.send(f"Failed to reload cogs: {', '.join(failed_reload)}")
    else:
        await ctx.send(f"Git pull failed:\n```\n{output}\n```")

bot.add_command(gitpull_reload)




# The unified API service is now handled by run_unified_api.py

async def main(args): # Pass parsed args
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

    # --- Define AI cogs to potentially skip ---
    ai_cogs_to_skip = []
    if args.disable_ai:
        print("AI functionality disabled via command line flag.")
        ai_cogs_to_skip = [
            "cogs.ai_cog",
            "cogs.multi_conversation_ai_cog",
            # Add any other AI-related cogs from the 'cogs' folder here
        ]
        # Store the skip list on the bot object for reload commands
        bot.ai_cogs_to_skip = ai_cogs_to_skip
    else:
        bot.ai_cogs_to_skip = [] # Ensure it exists even if empty

    # Initialize pools before starting the bot logic
    await settings_manager.initialize_pools()

    try:
        async with bot:
            # Load all cogs from the 'cogs' directory, skipping AI if requested
            # This should now include WelcomeCog and SettingsCog if they are in the cogs dir
            await load_all_cogs(bot, skip_cogs=ai_cogs_to_skip)

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

            # --- Manually Load FreakTetoCog (only if AI is NOT disabled) ---
            if not args.disable_ai:
                try:
                    freak_teto_cog_path = "discordbot.freak_teto.cog"
                    await bot.load_extension(freak_teto_cog_path)
                    print(f"Successfully loaded FreakTetoCog from {freak_teto_cog_path}")
                    # Optional: Share FreakTetoCog instance if needed later
                    # freak_teto_cog_instance = bot.get_cog("FreakTetoCog")
                    # if freak_teto_cog_instance:
                    #     print("Successfully shared FreakTetoCog instance.")
                    # else:
                    #     print("Warning: FreakTetoCog not found after loading.")
                except commands.ExtensionAlreadyLoaded:
                    print(f"FreakTetoCog ({freak_teto_cog_path}) already loaded.")
                except commands.ExtensionNotFound:
                    print(f"Error: FreakTetoCog not found at {freak_teto_cog_path}")
                except Exception as e:
                    print(f"Failed to load FreakTetoCog: {e}")
                    import traceback
                    traceback.print_exc()
            # ------------------------------------

            # Start the bot using start() for async context
            await bot.start(TOKEN)
    finally:
        # Terminate the Flask server process when the bot stops
        flask_process.terminate()
        log.info("Flask server process terminated.")
        # Close database/cache pools
        await settings_manager.close_pools()

# Run the main async function
if __name__ == '__main__':
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Run the Discord Bot")
    parser.add_argument(
        "--disable-ai",
        action="store_true",
        help="Disable AI-related cogs and functionality."
    )
    args = parser.parse_args()
    # ------------------------

    try:
        asyncio.run(main(args)) # Pass parsed args to main
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
    except Exception as e:
        log.exception(f"An error occurred running the bot: {e}")
    # The finally block with pool closing is now correctly inside the main() function
