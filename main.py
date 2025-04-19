import threading
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import sys
import asyncio
import subprocess
from commands import load_all_cogs
from error_handler import handle_error
from utils import reload_script

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

        # Check for specific commands
        for cmd in bot.tree.get_commands():
            if cmd.name == "webdrivertorso":
                print(f"Found webdrivertorso command with {len(cmd.parameters)} parameters")
                for param in cmd.parameters:
                    print(f"  - Parameter: {param.name}, Type: {type(param.type).__name__}")
                    if hasattr(param, 'choices') and param.choices:
                        print(f"    Choices: {[choice.name for choice in param.choices]}")
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

async def main():
    """Main async function to load cogs and start the bot."""
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        raise ValueError("No token found. Make sure to set DISCORD_TOKEN in your .env file.")

    # Start Flask server as a separate process
    flask_process = subprocess.Popen([sys.executable, "flask_server.py"], cwd=os.path.dirname(__file__))

    try:
        async with bot:
            # Load all cogs from the 'cogs' directory
            await load_all_cogs(bot)
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
