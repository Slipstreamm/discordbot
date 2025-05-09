import asyncio
# Set the event loop policy to the default asyncio policy BEFORE other asyncio/discord imports
# This is to test if uvloop (if active globally) is causing issues with asyncpg.
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

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
import asyncpg
import redis.asyncio as aioredis
from commands import load_all_cogs, reload_all_cogs
from error_handler import handle_error, patch_discord_methods, store_interaction_content
from utils import reload_script
import settings_manager # Import the settings manager
from db import mod_log_db # Import the new mod log db functions
import command_customization # Import command customization utilities
from global_bot_accessor import set_bot_instance # Import the new accessor

# Import the unified API service runner and the sync API module
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from run_unified_api import start_api_in_thread
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

# --- Custom Bot Class with setup_hook for async initialization ---
class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner_id = int(os.getenv('OWNER_USER_ID'))
        self.core_cogs = CORE_COGS # Attach core cogs list to bot instance
        self.settings_manager = settings_manager # Attach settings manager instance
        self.pg_pool = None # Will be initialized in setup_hook
        self.redis = None   # Will be initialized in setup_hook
        self.ai_cogs_to_skip = [] # For --disable-ai flag

    async def setup_hook(self):
        log.info("Running setup_hook...")

        # Create Postgres pool on this loop
        self.pg_pool = await asyncpg.create_pool(
            dsn=settings_manager.DATABASE_URL, # Use DATABASE_URL from settings_manager
            min_size=1,
            max_size=10,
            loop=self.loop  # Explicitly use the bot's event loop
        )
        log.info("Postgres pool initialized and attached to bot.pg_pool.")

        # Create Redis client on this loop
        self.redis = await aioredis.from_url(
            settings_manager.REDIS_URL, # Use REDIS_URL from settings_manager
            max_connections=10,
            decode_responses=True,
        )
        log.info("Redis client initialized and attached to bot.redis.")

        # Make sure the bot instance is set in the global_bot_accessor
        # This ensures settings_manager can access the pools via get_bot_instance()
        set_bot_instance(self)
        log.info("Bot instance set in global_bot_accessor from setup_hook.")

        # Initialize database schema and run migrations using settings_manager
        if self.pg_pool and self.redis:
            try:
                await settings_manager.initialize_database() # Uses the bot instance via get_bot_instance()
                log.info("Database schema initialization called via settings_manager.")
                await settings_manager.run_migrations() # Uses the bot instance via get_bot_instance()
                log.info("Database migrations called via settings_manager.")
            except Exception as e:
                log.exception("CRITICAL: Failed during settings_manager database setup (init/migrations).")
        else:
            log.error("CRITICAL: pg_pool or redis_client not initialized in setup_hook. Cannot proceed with settings_manager setup.")


        # Setup the moderation log table *after* pool initialization
        if self.pg_pool:
            try:
                await mod_log_db.setup_moderation_log_table(self.pg_pool)
                log.info("Moderation log table setup complete via setup_hook.")
            except Exception as e:
                log.exception("CRITICAL: Failed to setup moderation log table in setup_hook.")
        else:
            log.warning("pg_pool not available in setup_hook, skipping mod_log_db setup.")

        # Load all cogs from the 'cogs' directory, skipping AI if requested
        await load_all_cogs(self, skip_cogs=self.ai_cogs_to_skip)
        log.info(f"Cogs loaded in setup_hook. Skipped: {self.ai_cogs_to_skip or 'None'}")

        # --- Share GurtCog, ModLogCog, and bot instance with the sync API ---
        try:
            gurt_cog = self.get_cog("Gurt")
            if gurt_cog:
                discord_bot_sync_api.gurt_cog_instance = gurt_cog
                log.info("Successfully shared GurtCog instance with discord_bot_sync_api via setup_hook.")
            else:
                log.warning("GurtCog not found after loading cogs in setup_hook.")

            discord_bot_sync_api.bot_instance = self
            log.info("Successfully shared bot instance with discord_bot_sync_api via setup_hook.")

            mod_log_cog = self.get_cog("ModLogCog")
            if mod_log_cog:
                discord_bot_sync_api.mod_log_cog_instance = mod_log_cog
                log.info("Successfully shared ModLogCog instance with discord_bot_sync_api via setup_hook.")
            else:
                log.warning("ModLogCog not found after loading cogs in setup_hook.")
        except Exception as e:
            log.exception(f"Error sharing instances with discord_bot_sync_api in setup_hook: {e}")

        # --- Manually Load FreakTetoCog (only if AI is NOT disabled) ---
        if not self.ai_cogs_to_skip: # Check if list is empty (meaning AI is not disabled)
            try:
                freak_teto_cog_path = "discordbot.freak_teto.cog"
                await self.load_extension(freak_teto_cog_path)
                log.info(f"Successfully loaded FreakTetoCog from {freak_teto_cog_path} in setup_hook.")
            except commands.ExtensionAlreadyLoaded:
                log.info(f"FreakTetoCog ({freak_teto_cog_path}) already loaded (setup_hook).")
            except commands.ExtensionNotFound:
                log.error(f"Error: FreakTetoCog not found at {freak_teto_cog_path} (setup_hook).")
            except Exception as e:
                log.exception(f"Failed to load FreakTetoCog in setup_hook: {e}")
        log.info("setup_hook completed.")

# Create bot instance using the custom class
bot = MyBot(command_prefix=get_prefix, intents=intents)

# --- Logging Setup ---
# Configure logging (adjust level and format as needed)
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__) # Logger for main.py

# --- Events ---
@bot.event
async def on_ready():
    log.info(f'{bot.user.name} has connected to Discord!')
    log.info(f'Bot ID: {bot.user.id}')
    # Set the bot's status
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!help"))
    log.info("Bot status set to 'Listening to !help'")

    # --- Add current guilds to DB ---
    if bot.pg_pool:
        log.info("Syncing guilds with database...")
        try:
            async with bot.pg_pool.acquire() as conn:
                # Get guilds bot is currently in
                current_guild_ids = {guild.id for guild in bot.guilds}
                log.debug(f"Bot is currently in {len(current_guild_ids)} guilds.")

                # Get guilds currently in DB
                db_records = await conn.fetch("SELECT guild_id FROM guilds")
                db_guild_ids = {record['guild_id'] for record in db_records}
                log.debug(f"Found {len(db_guild_ids)} guilds in database.")

                # Add guilds bot joined while offline
                guilds_to_add = current_guild_ids - db_guild_ids
                if guilds_to_add:
                    log.info(f"Adding {len(guilds_to_add)} new guilds to database: {guilds_to_add}")
                    await conn.executemany("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING;",
                                           [(guild_id,) for guild_id in guilds_to_add])

                # Remove guilds bot left while offline
                guilds_to_remove = db_guild_ids - current_guild_ids
                if guilds_to_remove:
                    log.info(f"Removing {len(guilds_to_remove)} guilds from database: {guilds_to_remove}")
                    await conn.execute("DELETE FROM guilds WHERE guild_id = ANY($1::bigint[])", list(guilds_to_remove))

            log.info("Guild sync with database complete.")
        except Exception as e:
            log.exception("Error syncing guilds with database on ready.")
    else:
        log.warning("Bot Postgres pool not initialized, skipping guild sync.")
    # -----------------------------

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

        # Skip global command sync to avoid duplication
        print("Skipping global command sync to avoid command duplication...")

        # Only sync guild-specific commands with customizations
        print("Syncing guild-specific command customizations...")
        guild_syncs = await command_customization.register_all_guild_commands(bot)

        total_guild_syncs = sum(len(cmds) for cmds in guild_syncs.values())
        print(f"Synced commands for {len(guild_syncs)} guilds with a total of {total_guild_syncs} customized commands")

        # List commands after sync
        commands_after = [cmd.name for cmd in bot.tree.get_commands()]
        print(f"Commands registered in command tree: {commands_after}")

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

@bot.event
async def on_guild_join(guild: discord.Guild):
    """Adds guild to database when bot joins and syncs commands."""
    log.info(f"Joined guild: {guild.name} ({guild.id})")
    if bot.pg_pool:
        try:
            async with bot.pg_pool.acquire() as conn:
                 await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING;", guild.id)
            log.info(f"Added guild {guild.id} to database.")

            # Sync commands for the new guild
            try:
                log.info(f"Syncing commands for new guild: {guild.name} ({guild.id})")
                synced = await command_customization.register_guild_commands(bot, guild)
                log.info(f"Synced {len(synced)} commands for guild {guild.id}")
            except Exception as e:
                log.exception(f"Failed to sync commands for new guild {guild.id}: {e}")
        except Exception as e:
            log.exception(f"Failed to add guild {guild.id} to database on join.")
    else:
        log.warning("Bot Postgres pool not initialized, cannot add guild on join.")

@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Removes guild from database when bot leaves."""
    log.info(f"Left guild: {guild.name} ({guild.id})")
    if bot.pg_pool:
        try:
            async with bot.pg_pool.acquire() as conn:
                # Note: Cascading deletes should handle related settings in other tables
                await conn.execute("DELETE FROM guilds WHERE guild_id = $1", guild.id)
            log.info(f"Removed guild {guild.id} from database.")
        except Exception as e:
            log.exception(f"Failed to remove guild {guild.id} from database on leave.")
    else:
        log.warning("Bot Postgres pool not initialized, cannot remove guild on leave.")


# Error handling - Updated to handle custom check failures
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CogDisabledError):
        await ctx.send(str(error), ephemeral=True) # Send the error message from the exception
        log.warning(f"Command '{ctx.command.qualified_name}' blocked for user {ctx.author.id} in guild {ctx.guild.id}: {error}")
    elif isinstance(error, CommandPermissionError):
        await ctx.send(str(error), ephemeral=True) # Send the error message from the exception
        log.warning(f"Command '{ctx.command.qualified_name}' blocked for user {ctx.author.id} in guild {ctx.guild.id}: {error}")
    elif isinstance(error, CommandDisabledError):
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
# If it causes circular imports, CORE_COGS needs to be defined elsewhere or passed differently
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

class CommandDisabledError(commands.CheckFailure):
    """Custom exception for disabled commands."""
    def __init__(self, command_name):
        self.command_name = command_name
        super().__init__(f"The command `{command_name}` is disabled in this server.")

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

    # 2. Check if the Command is enabled
    # This only applies if the command has been explicitly disabled
    is_cmd_enabled = await settings_manager.is_command_enabled(guild_id, command_name, default_enabled=True)
    if not is_cmd_enabled:
        log.warning(f"Command '{command_name}' blocked in guild {guild_id}: Command is disabled.")
        raise CommandDisabledError(command_name)

    # 3. Check command permissions based on roles
    # This check only applies if specific permissions HAVE been set for this command.
    # If no permissions are set in the DB, check_command_permission returns True.
    has_perm = await settings_manager.check_command_permission(guild_id, command_name, member_roles_ids)
    if not has_perm:
        log.warning(f"Command '{command_name}' blocked for user {ctx.author.id} in guild {guild_id}: Insufficient role permissions.")
        raise CommandPermissionError(command_name)

    # If all checks pass, the command proceeds.
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
        # This is now done on the bot instance directly in the MyBot class
        bot.ai_cogs_to_skip = ai_cogs_to_skip
    else:
        bot.ai_cogs_to_skip = [] # Ensure it exists even if empty

    set_bot_instance(bot) # Set the global bot instance
    log.info(f"Global bot instance set in global_bot_accessor. Bot ID: {id(bot)}")

    # Pool initialization and cog loading are now handled in MyBot.setup_hook()

    try:
        # The bot will call setup_hook internally after login but before on_ready.
        await bot.start(TOKEN)
    except Exception as e:
        log.exception(f"An error occurred during bot.start(): {e}")
    finally:
        # Terminate the Flask server process when the bot stops
        if flask_process and flask_process.poll() is None: # Check if process exists and is running
            flask_process.terminate()
            log.info("Flask server process terminated.")
        else:
            log.info("Flask server process was not running or already terminated.")

        # Close database/cache pools if they were initialized
        if bot.pg_pool:
            log.info("Closing Postgres pool in main finally block...")
            await bot.pg_pool.close()
        if bot.redis:
            log.info("Closing Redis pool in main finally block...")
            await bot.redis.close()
        if not bot.pg_pool and not bot.redis:
            log.info("Pools were not initialized or already closed, skipping close_pools in main.")

# Run the main async function
import signal

def handle_sighup(signum, frame):
    import subprocess
    import sys
    import os
    try:
        print("Received SIGHUP: pulling latest code from /home/git/discordbot.git (branch master)...")
        result = subprocess.run(
            ["git", "--git-dir=/home/git/discordbot.git", "--work-tree=.", "pull", "origin", "master"],
            capture_output=True, text=True
        )
        print(result.stdout)
        print(result.stderr)
        print("Restarting process after SIGHUP...")
    except Exception as e:
        print(f"Error during SIGHUP git pull: {e}")
    os.execv(sys.executable, [sys.executable] + sys.argv)

if __name__ == '__main__':
    # Write PID to .pid file for git hook usage
    try:
        with open(".pid", "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        print(f"Failed to write .pid file: {e}")

    # Register SIGHUP handler (Linux only)
    try:
        signal.signal(signal.SIGHUP, handle_sighup)
    except AttributeError:
        print("SIGHUP not available on this platform.")

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
