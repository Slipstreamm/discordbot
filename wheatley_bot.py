import discord
from discord.ext import commands
import os
import asyncio
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up intents (permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create bot instance with command prefix '%'
bot = commands.Bot(command_prefix='%', intents=intents)
bot.owner_id = int(os.getenv('OWNER_USER_ID'))

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Bot ID: {bot.user.id}')
    # Set the bot's status
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="%ai"))
    print("Bot status set to 'Listening to %ai'")

    # Sync commands
    try:
        print("Starting command sync process...")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Main async function to load the wheatley cog and start the bot."""
    # Check for required environment variables, prioritizing WHEATLEY token
    TOKEN = os.getenv('DISCORD_TOKEN_WHEATLEY')

    # If Wheatley token not found, try GURT token
    if not TOKEN:
        TOKEN = os.getenv('DISCORD_TOKEN_GURT')

    # If neither specific token found, try the main bot token
    if not TOKEN:
        TOKEN = os.getenv('DISCORD_TOKEN')

    if not TOKEN:
        raise ValueError("No Discord token found. Make sure to set DISCORD_TOKEN_WHEATLEY, DISCORD_TOKEN_GURT, or DISCORD_TOKEN in your .env file.")

    # Note: Vertex AI authentication is handled by the library using ADC or GOOGLE_APPLICATION_CREDENTIALS.
    # No explicit API key check is needed here. Ensure GCP_PROJECT_ID and GCP_LOCATION are set in .env

    try:
        async with bot:
            # List of cogs to load - Load WheatleyCog instead of GurtCog
            cogs = ["wheatley.cog", "cogs.profile_updater_cog"] # Assuming profile updater is still desired
            for cog in cogs:
                try:
                    await bot.load_extension(cog)
                    print(f"Successfully loaded {cog}")
                except Exception as e:
                    print(f"Error loading {cog}: {e}")
                    import traceback
                    traceback.print_exc()

            # Start the bot
            await bot.start(TOKEN)
    except Exception as e:
        print(f"Error starting Wheatley Bot: {e}")

# Run the main async function
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Wheatley Bot stopped by user.")
    except Exception as e:
        print(f"An error occurred running Wheatley Bot: {e}")
