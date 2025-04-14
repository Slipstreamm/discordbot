import discord
from discord.ext import commands
import os
from auto_updater import check_for_updates
from dotenv import load_dotenv
import threading
import sys
import asyncio
from commands import load_all_cogs
from error_handler import handle_error
from utils import listen_for_reload, set_bot_instance, check_and_reload_hook # Import the hook

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
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    bot.loop.create_task(check_for_updates())

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

# Store the bot instance for reloading purposes (before async setup)
set_bot_instance(bot)

# Register the before_invoke hook globally
bot.before_invoke(check_and_reload_hook)

# Start the reload listener in a separate thread
listener_thread = threading.Thread(target=listen_for_reload, daemon=True)
listener_thread.start()

async def main():
    """Main async function to load cogs and start the bot."""
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        raise ValueError("No token found. Make sure to set DISCORD_TOKEN in your .env file.")

    async with bot:
        # Load all cogs from the 'cogs' directory
        await load_all_cogs(bot)
        # Start the bot using start() for async context
        await bot.start(TOKEN)

# Run the main async function
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"An error occurred running the bot: {e}")
