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
        embed = discord.Embed(
            title=f"{target_user.display_name}'s Balance",
            description=f"💰 **${balance_amount:,}**",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="moneylb", aliases=["mlb", "mtop"], description="Show the richest users by money.") # Renamed to avoid conflict
    @commands.cooldown(1, 30, commands.BucketType.user) # Prevent spam
    async def moneylb(self, ctx: commands.Context, count: int = 10): # Renamed function
        """Displays the top users by balance."""
        if not 1 <= count <= 25:
            embed = discord.Embed(description="❌ Please provide a count between 1 and 25.", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        results = await database.get_leaderboard(count)

        if not results:
            embed = discord.Embed(description="📊 The leaderboard is empty!", color=discord.Color.orange())
            await ctx.send(embed=embed, ephemeral=True)
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
            embed = discord.Embed(description="❌ You cannot pay yourself!", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        if amount <= 0:
            embed = discord.Embed(description="❌ Please enter a positive amount to pay.", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        sender_balance = await database.get_balance(sender_id)

        if sender_balance < amount:
            embed = discord.Embed(description=f"❌ You don't have enough money! Your balance is **${sender_balance:,}**.", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Perform the transfer
        await database.update_balance(sender_id, -amount) # Decrease sender's balance
        await database.update_balance(recipient_id, amount) # Increase recipient's balance

        current_sender_balance = await database.get_balance(sender_id)
        embed_sender = discord.Embed(
            title="Payment Successful!",
            description=f"💸 You successfully paid **${amount:,}** to {recipient.mention}.",
            color=discord.Color.green()
        )
        embed_sender.add_field(name="Your New Balance", value=f"${current_sender_balance:,}", inline=False)
        await ctx.send(embed=embed_sender)
        try:
            # Optionally DM the recipient
            embed_recipient = discord.Embed(
                title="You Received a Payment!",
                description=f"💸 You received **${amount:,}** from {ctx.author.mention}!",
                color=discord.Color.green()
            )
            await recipient.send(embed=embed_recipient)
        except discord.Forbidden:
            log.warning(f"Could not DM recipient {recipient_id} about payment.") # User might have DMs closed

# No setup function needed here
