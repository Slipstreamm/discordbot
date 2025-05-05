import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging
import sys

# Add the parent directory to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the starboard cog and settings manager
from discordbot.cogs.starboard_cog import StarboardCog
import discordbot.settings_manager as settings_manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__)

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    log.info(f'{bot.user.name} has connected to Discord!')
    log.info(f'Bot ID: {bot.user.id}')

    # Load the starboard cog
    try:
        await bot.add_cog(StarboardCog(bot))
        log.info("StarboardCog loaded successfully!")
    except Exception as e:
        log.error(f"Error loading StarboardCog: {e}")

async def main():
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        raise ValueError("No token found. Make sure to set DISCORD_TOKEN in your .env file.")

    try:
        await bot.start(TOKEN)
    except Exception as e:
        log.exception(f"Error starting bot: {e}")

if __name__ == "__main__":
    asyncio.run(main())
