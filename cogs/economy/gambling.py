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

    @commands.hybrid_command(name="moneyflip", aliases=["mf"], description="Gamble your money on a coin flip.") # Renamed to avoid conflict
    async def moneyflip(self, ctx: commands.Context, amount: int, choice: str): # Renamed function
        """Bets a certain amount on a coin flip (heads or tails)."""
        user_id = ctx.author.id
        command_name = "moneyflip" # Update command name for cooldown tracking
        cooldown_duration = datetime.timedelta(seconds=10) # Short cooldown

        choice = choice.lower()
        if choice not in ["heads", "tails", "h", "t"]:
            embed = discord.Embed(description="❌ Invalid choice. Please choose 'heads' or 'tails'.", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        if amount <= 0:
            embed = discord.Embed(description="❌ Please enter a positive amount to bet.", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
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
                embed = discord.Embed(description=f"🕒 You're flipping too fast! Try again in **{int(time_left.total_seconds())}s**.", color=discord.Color.orange())
                await ctx.send(embed=embed, ephemeral=True)
                return

        # Check balance
        user_balance = await database.get_balance(user_id)
        if user_balance < amount:
            embed = discord.Embed(description=f"❌ You don't have enough money to bet that much! Your balance is **${user_balance:,}**.", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Set cooldown before proceeding
        await database.set_cooldown(user_id, command_name)

        # Perform the coin flip
        result = random.choice(["heads", "tails"])
        win = (choice.startswith(result[0])) # True if choice matches result

        if win:
            await database.update_balance(user_id, amount) # Win the amount bet
            current_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="Coin Flip: Win!",
                description=f"🪙 The coin landed on **{result}**! You won **${amount:,}**!",
                color=discord.Color.green()
            )
            embed.add_field(name="New Balance", value=f"${current_balance:,}", inline=False)
            await ctx.send(embed=embed)
        else:
            await database.update_balance(user_id, -amount) # Lose the amount bet
            current_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="Coin Flip: Loss!",
                description=f"🪙 The coin landed on **{result}**. You lost **${amount:,}**.",
                color=discord.Color.red()
            )
            embed.add_field(name="New Balance", value=f"${current_balance:,}", inline=False)
            await ctx.send(embed=embed)

# No setup function needed here
