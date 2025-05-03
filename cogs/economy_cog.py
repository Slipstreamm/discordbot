import discord
from discord.ext import commands
import logging
import asyncio

# Import command classes and db functions from submodules
from .economy.database import init_db, close_db # Import close_db
from .economy.earning import EarningCommands
from .economy.gambling import GamblingCommands
from .economy.utility import UtilityCommands
from .economy.risky import RiskyCommands
from .economy.jobs import JobsCommands # Import the new JobsCommands

log = logging.getLogger(__name__)

# --- Main Cog Implementation ---

# Inherit from commands.Cog and all the command classes
class EconomyCog(
    EarningCommands,
    GamblingCommands,
    UtilityCommands,
    RiskyCommands,
    JobsCommands, # Add JobsCommands to the inheritance list
    commands.Cog # Ensure commands.Cog is included
    ):
    """Main cog for the economy system, combining all command groups."""

    def __init__(self, bot: commands.Bot):
        # Initialize all parent cogs (important!)
        super().__init__(bot) # Calls __init__ of the first parent in MRO (EarningCommands)
        # If other parent cogs had complex __init__, we might need to call them explicitly,
        # but in this case, they only store the bot instance, which super() handles.
        self.bot = bot
        log.info("EconomyCog initialized (combined).")

    async def cog_load(self):
        """Called when the cog is loaded, ensures DB is initialized."""
        log.info("Loading EconomyCog (combined)...")
        try:
            await init_db()
            log.info("EconomyCog database initialization complete.")
        except Exception as e:
            log.error(f"EconomyCog failed to initialize database during load: {e}", exc_info=True)
            # Prevent the cog from loading if DB init fails
            raise commands.ExtensionFailed(self.qualified_name, e) from e

    async def cog_unload(self):
        """Called when the cog is unloaded, closes DB connections."""
        log.info("Unloading EconomyCog (combined)...")
        # Schedule the close_db function to run in the bot's event loop
        # Using ensure_future or create_task is generally safer within cogs
        asyncio.ensure_future(close_db())
        log.info("Scheduled database connection closure.")


# --- Setup Function ---

async def setup(bot: commands.Bot):
    """Sets up the combined EconomyCog."""
    await bot.add_cog(EconomyCog(bot))
    log.info("Combined EconomyCog added to bot.")
