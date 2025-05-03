import discord
from discord.ext import commands
import datetime
import logging
from typing import Optional

# Import database functions from the sibling module
from . import database

log = logging.getLogger(__name__)

class UtilityCommands(commands.Cog):
    """Cog containing utility-related economy commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="balance", description="Check your or another user's balance.")
    @commands.cooldown(1, 5, commands.BucketType.user) # Basic discord.py cooldown
    async def balance(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Displays the economy balance for a user."""
        target_user = user or ctx.author
        balance_amount = await database.get_balance(target_user.id)
        await ctx.send(f"{target_user.display_name} has a balance of **${balance_amount:,}**.", ephemeral=True)

    @commands.hybrid_command(name="leaderboard", aliases=["lb", "top"], description="Show the richest users.")
    @commands.cooldown(1, 30, commands.BucketType.user) # Prevent spam
    async def leaderboard(self, ctx: commands.Context, count: int = 10):
        """Displays the top users by balance."""
        if not 1 <= count <= 25:
            await ctx.send("Please provide a count between 1 and 25.", ephemeral=True)
            return

        results = await database.get_leaderboard(count)

        if not results:
            await ctx.send("The leaderboard is empty!", ephemeral=True)
            return

        embed = discord.Embed(title="💰 Economy Leaderboard", color=discord.Color.gold())
        description = ""
        rank = 1
        for user_id, balance in results:
            user = self.bot.get_user(user_id) # Try to get user object for display name
            # Fetch user if not in cache - might be slow for large leaderboards
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    user = None # User might have left all shared servers
                except discord.HTTPException:
                    user = None # Other Discord API error
                    log.warning(f"Failed to fetch user {user_id} for leaderboard.")

            user_name = user.display_name if user else f"User ID: {user_id}"
            description += f"{rank}. {user_name} - **${balance:,}**\n"
            rank += 1

        embed.description = description
        await ctx.send(embed=embed)


    @commands.hybrid_command(name="pay", description="Transfer money to another user.")
    async def pay(self, ctx: commands.Context, recipient: discord.User, amount: int):
        """Transfers currency from the command author to another user."""
        sender_id = ctx.author.id
        recipient_id = recipient.id

        if sender_id == recipient_id:
            await ctx.send("You cannot pay yourself!", ephemeral=True)
            return

        if amount <= 0:
            await ctx.send("Please enter a positive amount to pay.", ephemeral=True)
            return

        sender_balance = await database.get_balance(sender_id)

        if sender_balance < amount:
            await ctx.send(f"You don't have enough money! Your balance is **${sender_balance:,}**.", ephemeral=True)
            return

        # Perform the transfer
        await database.update_balance(sender_id, -amount) # Decrease sender's balance
        await database.update_balance(recipient_id, amount) # Increase recipient's balance

        current_sender_balance = await database.get_balance(sender_id)
        await ctx.send(f"💸 You successfully paid **${amount:,}** to {recipient.mention}. Your new balance is **${current_sender_balance:,}**.")
        try:
            # Optionally DM the recipient
            await recipient.send(f"💸 You received a payment of **${amount:,}** from {ctx.author.mention}!")
        except discord.Forbidden:
            log.warning(f"Could not DM recipient {recipient_id} about payment.") # User might have DMs closed

# No setup function needed here
