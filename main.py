import threading
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import sys
import asyncio
from commands import load_all_cogs
from error_handler import handle_error
from utils import reload_script
import hmac
import hashlib
from flask import Flask, request, abort

# Load environment variables from .env file
load_dotenv()

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

GITHUB_SECRET = os.getenv("GITHUB_SECRET").encode()
app = Flask(__name__)

def verify_signature(payload, signature):
    mac = hmac.new(GITHUB_SECRET, payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route("/github-webhook-123", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature or not verify_signature(request.data, signature):
        abort(403)

    reload_script()
    return "OK"

def run_flask():
    app.run(host="127.0.0.1", port=5000)

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
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"An error occurred running the bot: {e}")
