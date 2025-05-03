import discord
from discord.ext import commands
import datetime
import random
import logging
from typing import Optional

# Import database functions from the sibling module
from . import database

log = logging.getLogger(__name__)

class GamblingCommands(commands.Cog):
    """Cog containing gambling-related economy commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="coinflip", aliases=["cf"], description="Gamble your money on a coin flip.")
    async def coinflip(self, ctx: commands.Context, amount: int, choice: str):
        """Bets a certain amount on a coin flip (heads or tails)."""
        user_id = ctx.author.id
        command_name = "coinflip" # Cooldown specific to coinflip
        cooldown_duration = datetime.timedelta(seconds=10) # Short cooldown

        choice = choice.lower()
        if choice not in ["heads", "tails", "h", "t"]:
            await ctx.send("Invalid choice. Please choose 'heads' or 'tails'.", ephemeral=True)
            return

        if amount <= 0:
            await ctx.send("Please enter a positive amount to bet.", ephemeral=True)
            return

        # Check cooldown
        last_used = await database.check_cooldown(user_id, command_name)
        if last_used:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=datetime.timezone.utc)

            time_since_last_used = now_utc - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                await ctx.send(f"You're flipping too fast! Try again in **{int(time_left.total_seconds())}s**.", ephemeral=True)
                return

        # Check balance
        user_balance = await database.get_balance(user_id)
        if user_balance < amount:
            await ctx.send(f"You don't have enough money to bet that much! Your balance is **${user_balance:,}**.", ephemeral=True)
            return

        # Set cooldown before proceeding
        await database.set_cooldown(user_id, command_name)

        # Perform the coin flip
        result = random.choice(["heads", "tails"])
        win = (choice.startswith(result[0])) # True if choice matches result

        if win:
            await database.update_balance(user_id, amount) # Win the amount bet
            current_balance = await database.get_balance(user_id)
            await ctx.send(f"🪙 The coin landed on **{result}**! You won **${amount:,}**! Your new balance is **${current_balance:,}**.")
        else:
            await database.update_balance(user_id, -amount) # Lose the amount bet
            current_balance = await database.get_balance(user_id)
            await ctx.send(f"🪙 The coin landed on **{result}**. You lost **${amount:,}**. Your new balance is **${current_balance:,}**.")

# No setup function needed here
