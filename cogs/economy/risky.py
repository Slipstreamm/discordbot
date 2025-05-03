import discord
from discord.ext import commands
import datetime
import random
import logging
from typing import Optional

# Import database functions from the sibling module
from . import database

log = logging.getLogger(__name__)

class RiskyCommands(commands.Cog):
    """Cog containing risky economy commands like robbing."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="rob", description="Attempt to rob another user (risky!).")
    async def rob(self, ctx: commands.Context, target: discord.User):
        """Attempts to steal money from another user."""
        robber_id = ctx.author.id
        target_id = target.id
        command_name = "rob"
        cooldown_duration = datetime.timedelta(hours=6) # 6-hour cooldown
        success_chance = 0.30 # 30% base chance of success
        min_target_balance = 100 # Target must have at least this much to be robbed
        fine_multiplier = 0.5 # Fine is 50% of what you tried to steal if caught
        steal_percentage_min = 0.05 # Steal between 5%
        steal_percentage_max = 0.20 # and 20% of target's balance

        if robber_id == target_id:
            embed = discord.Embed(description="❌ You can't rob yourself!", color=discord.Color.red())
            await ctx.send(embed=embed, ephemeral=True)
            return

        # Check cooldown
        last_used = await database.check_cooldown(robber_id, command_name)
        if last_used:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=datetime.timezone.utc)

            time_since_last_used = now_utc - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                embed = discord.Embed(description=f"🕒 You need to lay low after your last attempt. Try again in **{hours}h {minutes}m {seconds}s**.", color=discord.Color.orange())
                await ctx.send(embed=embed, ephemeral=True)
                return

        # Check target balance
        target_balance = await database.get_balance(target_id)
        if target_balance < min_target_balance:
            embed = discord.Embed(description=f"❌ {target.display_name} doesn't have enough money to be worth robbing (minimum ${min_target_balance:,}).", color=discord.Color.orange())
            await ctx.send(embed=embed, ephemeral=True)
            # Don't apply cooldown if target wasn't viable
            return

        # Set cooldown now that a valid attempt is being made
        await database.set_cooldown(robber_id, command_name)

        # Check robber balance (needed for potential fine)
        robber_balance = await database.get_balance(robber_id)

        # Determine success
        if random.random() < success_chance:
            # Success!
            steal_percentage = random.uniform(steal_percentage_min, steal_percentage_max)
            stolen_amount = int(target_balance * steal_percentage)

            if stolen_amount <= 0: # Ensure at least 1 is stolen if percentage is too low
                stolen_amount = 1

            await database.update_balance(robber_id, stolen_amount)
            await database.update_balance(target_id, -stolen_amount)
            current_robber_balance = await database.get_balance(robber_id)
            embed_success = discord.Embed(
                title="Robbery Successful!",
                description=f"🚨 Success! You skillfully robbed **${stolen_amount:,}** from {target.mention}!",
                color=discord.Color.green()
            )
            embed_success.add_field(name="Your New Balance", value=f"${current_robber_balance:,}", inline=False)
            await ctx.send(embed=embed_success)
            try:
                embed_target = discord.Embed(
                    title="You've Been Robbed!",
                    description=f"🚨 Oh no! {ctx.author.mention} robbed you for **${stolen_amount:,}**!",
                    color=discord.Color.red()
                )
                await target.send(embed=embed_target)
            except discord.Forbidden:
                pass # Ignore if DMs are closed
        else:
            # Failure! Calculate potential fine
            # Fine based on what they *could* have stolen (using average percentage for calculation)
            potential_steal_amount = int(target_balance * ((steal_percentage_min + steal_percentage_max) / 2))
            if potential_steal_amount <= 0: potential_steal_amount = 1
            fine_amount = int(potential_steal_amount * fine_multiplier)

            # Ensure fine doesn't exceed robber's balance
            fine_amount = min(fine_amount, robber_balance)

            if fine_amount > 0:
                await database.update_balance(robber_id, -fine_amount)
                # Optional: Give the fine to the target? Or just remove it? Let's remove it.
                # await database.update_balance(target_id, fine_amount)
                current_robber_balance = await database.get_balance(robber_id)
                embed_fail = discord.Embed(
                    title="Robbery Failed!",
                    description=f"👮‍♂️ You were caught trying to rob {target.mention}! You paid a fine of **${fine_amount:,}**.",
                    color=discord.Color.red()
                )
                embed_fail.add_field(name="Your New Balance", value=f"${current_robber_balance:,}", inline=False)
                await ctx.send(embed=embed_fail)
            else:
                # Robber is broke, can't pay fine
                 embed_fail_broke = discord.Embed(
                     title="Robbery Failed!",
                     description=f"👮‍♂️ You were caught trying to rob {target.mention}, but you're too broke to pay the fine!",
                     color=discord.Color.red()
                 )
                 await ctx.send(embed=embed_fail_broke)

# No setup function needed here
