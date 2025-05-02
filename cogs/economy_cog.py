import discord
from discord.ext import commands, tasks
import aiosqlite
import os
import datetime
import logging
import random
from typing import Optional

# Configure logging
log = logging.getLogger(__name__)

# Database path (within the discordbot/data directory)
DB_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DB_DIR, 'economy.db')

# Ensure the data directory exists
os.makedirs(DB_DIR, exist_ok=True)

# --- Database Setup ---

async def init_db():
    """Initializes the database and creates tables if they don't exist."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Create economy table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0
                )
            """)
            log.info("Checked/created 'economy' table.")

            # Create command_cooldowns table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS command_cooldowns (
                    user_id INTEGER NOT NULL,
                    command_name TEXT NOT NULL,
                    last_used TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, command_name)
                )
            """)
            log.info("Checked/created 'command_cooldowns' table.")

            await db.commit()
            log.info(f"Database initialized successfully at {DB_PATH}")
    except Exception as e:
        log.error(f"Failed to initialize economy database at {DB_PATH}: {e}", exc_info=True)
        raise # Re-raise the exception to prevent the cog from loading incorrectly

# --- Cog Implementation ---

class EconomyCog(commands.Cog):
    """Cog for handling economy commands like balance, daily, and beg."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.info("EconomyCog initialized.")

    async def cog_load(self):
        """Called when the cog is loaded, ensures DB is initialized."""
        log.info("Loading EconomyCog...")
        await init_db()
        log.info("EconomyCog database initialization complete.")

    # --- Database Helper Methods ---

    async def _get_balance(self, user_id: int) -> int:
        """Gets the balance for a user, creating an entry if needed."""
        async with aiosqlite.connect(DB_PATH) as db:
            # Try to fetch existing balance
            async with db.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result[0]
                else:
                    # User doesn't exist, create entry and return default balance (0)
                    try:
                        await db.execute("INSERT INTO economy (user_id, balance) VALUES (?, ?)", (user_id, 0))
                        await db.commit()
                        log.info(f"Created new economy entry for user_id: {user_id}")
                        return 0
                    except aiosqlite.IntegrityError:
                        # Handle rare race condition where another process inserted the user just now
                        log.warning(f"Race condition handled for user_id: {user_id} during balance fetch.")
                        async with db.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,)) as cursor_retry:
                            result_retry = await cursor_retry.fetchone()
                            return result_retry[0] if result_retry else 0 # Should exist now

    async def _update_balance(self, user_id: int, amount: int):
        """Updates a user's balance by adding the specified amount (can be negative)."""
        async with aiosqlite.connect(DB_PATH) as db:
            # Ensure user exists first
            await self._get_balance(user_id)
            # Update balance
            await db.execute("UPDATE economy SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            await db.commit()
            log.debug(f"Updated balance for user_id {user_id} by {amount}.")

    async def _check_cooldown(self, user_id: int, command_name: str) -> Optional[datetime.datetime]:
        """Checks if a command is on cooldown for a user. Returns the last used time if on cooldown, else None."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_used FROM command_cooldowns WHERE user_id = ? AND command_name = ?", (user_id, command_name)) as cursor:
                result = await cursor.fetchone()
                if result:
                    # Parse the timestamp string back into a datetime object
                    # Assuming timestamps are stored in ISO 8601 format (YYYY-MM-DD HH:MM:SS.ffffff)
                    try:
                        last_used_dt = datetime.datetime.fromisoformat(result[0])
                        return last_used_dt
                    except ValueError:
                        log.error(f"Could not parse timestamp '{result[0]}' for user {user_id}, command {command_name}")
                        # Fallback: treat as if not on cooldown or handle error appropriately
                        return None
                else:
                    return None # Not on cooldown

    async def _set_cooldown(self, user_id: int, command_name: str):
        """Sets or updates the cooldown timestamp for a command."""
        now = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now.isoformat() # Store in ISO format for consistency
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO command_cooldowns (user_id, command_name, last_used)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, command_name) DO UPDATE SET last_used = excluded.last_used
            """, (user_id, command_name, now_iso))
            await db.commit()
            log.debug(f"Set cooldown for user_id {user_id}, command {command_name} to {now_iso}")


    # --- Commands ---

    @commands.hybrid_command(name="balance", description="Check your or another user's balance.")
    @commands.cooldown(1, 5, commands.BucketType.user) # Basic discord.py cooldown to prevent spamming the check itself
    async def balance(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Displays the economy balance for a user."""
        target_user = user or ctx.author
        balance_amount = await self._get_balance(target_user.id)
        await ctx.send(f"{target_user.display_name} has a balance of **${balance_amount:,}**.", ephemeral=True)

    @commands.hybrid_command(name="daily", description="Claim your daily reward.")
    async def daily(self, ctx: commands.Context):
        """Allows users to claim a daily currency reward."""
        user_id = ctx.author.id
        command_name = "daily"
        cooldown_duration = datetime.timedelta(hours=24)
        reward_amount = 100 # Example daily reward

        last_used = await self._check_cooldown(user_id, command_name)

        if last_used:
            time_since_last_used = datetime.datetime.now(datetime.timezone.utc) - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                # Format timedelta nicely
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                await ctx.send(f"You've already claimed your daily reward. Try again in **{hours}h {minutes}m {seconds}s**.", ephemeral=True)
                return
            else:
                 # Cooldown expired but entry exists, proceed to claim
                 pass

        # Not on cooldown or cooldown expired
        await self._update_balance(user_id, reward_amount)
        await self._set_cooldown(user_id, command_name)
        await ctx.send(f"🎉 You claimed your daily reward of **${reward_amount:,}**! Your new balance is **${await self._get_balance(user_id):,}**.")


    @commands.hybrid_command(name="beg", description="Beg for some spare change.")
    async def beg(self, ctx: commands.Context):
        """Allows users to beg for a small amount of currency with a chance of success."""
        user_id = ctx.author.id
        command_name = "beg"
        cooldown_duration = datetime.timedelta(minutes=5) # 5-minute cooldown
        success_chance = 0.4 # 40% chance of success
        min_reward = 1
        max_reward = 20

        last_used = await self._check_cooldown(user_id, command_name)

        if last_used:
            time_since_last_used = datetime.datetime.now(datetime.timezone.utc) - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                minutes, seconds = divmod(int(time_left.total_seconds()), 60)
                await ctx.send(f"You can't beg again so soon. Try again in **{minutes}m {seconds}s**.", ephemeral=True)
                return
            else:
                # Cooldown expired
                pass

        # Set cooldown regardless of success/failure
        await self._set_cooldown(user_id, command_name)

        # Determine success
        if random.random() < success_chance:
            reward_amount = random.randint(min_reward, max_reward)
            await self._update_balance(user_id, reward_amount)
            await ctx.send(f"🙏 Someone took pity on you! You received **${reward_amount:,}**. Your new balance is **${await self._get_balance(user_id):,}**.")
        else:
            await ctx.send("🤷 Nobody gave you anything. Better luck next time!")


async def setup(bot: commands.Bot):
    """Sets up the EconomyCog."""
    await bot.add_cog(EconomyCog(bot))
    log.info("EconomyCog added to bot.")
