import discord
from discord.ext import commands
import datetime
import random
import logging
from typing import Optional

# Import database functions from the sibling module
from . import database

log = logging.getLogger(__name__)

class EarningCommands(commands.Cog):
    """Cog containing currency earning commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="daily", description="Claim your daily reward.")
    async def daily(self, ctx: commands.Context):
        """Allows users to claim a daily currency reward."""
        user_id = ctx.author.id
        command_name = "daily"
        cooldown_duration = datetime.timedelta(hours=24)
        reward_amount = 100 # Example daily reward

        last_used = await database.check_cooldown(user_id, command_name)

        if last_used:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            # Ensure last_used is timezone-aware for comparison
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=datetime.timezone.utc)

            time_since_last_used = now_utc - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                embed = discord.Embed(description=f"🕒 You've already claimed your daily reward. Try again in **{hours}h {minutes}m {seconds}s**.", color=discord.Color.orange())
                await ctx.send(embed=embed, ephemeral=True)
                return

        # Not on cooldown or cooldown expired
        await database.update_balance(user_id, reward_amount)
        await database.set_cooldown(user_id, command_name)
        current_balance = await database.get_balance(user_id)
        embed = discord.Embed(
            title="Daily Reward Claimed!",
            description=f"🎉 You claimed your daily reward of **${reward_amount:,}**!",
            color=discord.Color.green()
        )
        embed.add_field(name="New Balance", value=f"${current_balance:,}", inline=False)
        await ctx.send(embed=embed)


    @commands.command(name="beg", description="Beg for some spare change.")
    async def beg(self, ctx: commands.Context):
        """Allows users to beg for a small amount of currency with a chance of success."""
        user_id = ctx.author.id
        command_name = "beg"
        cooldown_duration = datetime.timedelta(minutes=5) # 5-minute cooldown
        success_chance = 0.4 # 40% chance of success
        min_reward = 1
        max_reward = 20

        last_used = await database.check_cooldown(user_id, command_name)

        if last_used:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=datetime.timezone.utc)

            time_since_last_used = now_utc - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                minutes, seconds = divmod(int(time_left.total_seconds()), 60)
                embed = discord.Embed(description=f"🕒 You can't beg again so soon. Try again in **{minutes}m {seconds}s**.", color=discord.Color.orange())
                await ctx.send(embed=embed, ephemeral=True)
                return

        # Set cooldown regardless of success/failure
        await database.set_cooldown(user_id, command_name)

        # Determine success
        if random.random() < success_chance:
            reward_amount = random.randint(min_reward, max_reward)
            await database.update_balance(user_id, reward_amount)
            current_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="Begging Successful!",
                description=f"🙏 Someone took pity on you! You received **${reward_amount:,}**.",
                color=discord.Color.green()
            )
            embed.add_field(name="New Balance", value=f"${current_balance:,}", inline=False)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="Begging Failed",
                description="🤷 Nobody gave you anything. Better luck next time!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="work", description="Do some work for a guaranteed reward.")
    async def work(self, ctx: commands.Context):
        """Allows users to perform work for a small, guaranteed reward."""
        user_id = ctx.author.id
        command_name = "work"
        cooldown_duration = datetime.timedelta(hours=1) # 1-hour cooldown
        reward_amount = random.randint(15, 35) # Small reward range - This is now fallback if no job

        # --- Check if user has a job ---
        job_info = await database.get_user_job(user_id)
        if job_info and job_info.get("name"):
            job_key = job_info["name"]
            # Dynamically get job details if possible (assuming JOB_DEFINITIONS might be accessible or refactored)
            # For simplicity here, just use the job key. A better approach might involve a shared config or helper.
            # from .jobs import JOB_DEFINITIONS # Avoid circular import if possible
            # job_details = JOB_DEFINITIONS.get(job_key)
            # command_to_use = job_details['command'] if job_details else f"your job command (`/{job_key}`)" # Fallback
            command_to_use = f"`/{job_key}`" # Simple fallback
            embed = discord.Embed(description=f"💼 You have a job! Use {command_to_use} instead of the generic `/work` command.", color=discord.Color.blue())
            await ctx.send(embed=embed, ephemeral=True)
            return
        # --- End Job Check ---


        # Proceed with generic /work only if no job
        last_used = await database.check_cooldown(user_id, command_name)

        if last_used:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=datetime.timezone.utc)

            time_since_last_used = now_utc - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                embed = discord.Embed(description=f"🕒 You need to rest after working. Try again in **{hours}h {minutes}m {seconds}s**.", color=discord.Color.orange())
                await ctx.send(embed=embed, ephemeral=True)
                return

        # Set cooldown and give reward
        await database.set_cooldown(user_id, command_name)
        await database.update_balance(user_id, reward_amount)
        # Add some flavor text
        work_messages = [
            f"You worked hard and earned **${reward_amount:,}**!",
            f"After a solid hour of work, you got **${reward_amount:,}**.",
            f"Your efforts paid off! You received **${reward_amount:,}**.",
        ]
        current_balance = await database.get_balance(user_id)
        embed = discord.Embed(
            title="Work Complete!",
            description=random.choice(work_messages),
            color=discord.Color.green()
        )
        embed.add_field(name="New Balance", value=f"${current_balance:,}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="scavenge", description="Scavenge around for some spare change.") # Renamed to avoid conflict
    async def scavenge(self, ctx: commands.Context): # Renamed function
        """Allows users to scavenge for a small chance of finding money."""
        user_id = ctx.author.id
        command_name = "scavenge" # Update command name for cooldown tracking
        cooldown_duration = datetime.timedelta(minutes=30) # 30-minute cooldown
        success_chance = 0.25 # 25% chance to find something
        min_reward = 1
        max_reward = 10

        last_used = await database.check_cooldown(user_id, command_name)

        if last_used:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=datetime.timezone.utc)

            time_since_last_used = now_utc - last_used
            if time_since_last_used < cooldown_duration:
                time_left = cooldown_duration - time_since_last_used
                minutes, seconds = divmod(int(time_left.total_seconds()), 60)
                embed = discord.Embed(description=f"🕒 You've searched recently. Try again in **{minutes}m {seconds}s**.", color=discord.Color.orange())
                await ctx.send(embed=embed, ephemeral=True)
                return

        # Set cooldown regardless of success
        await database.set_cooldown(user_id, command_name)

        # Flavor text for scavenging
        scavenge_locations = [ # Renamed variable for clarity
            "under the sofa cushions", "in an old coat pocket", "behind the dumpster",
            "in a dusty corner", "on the sidewalk", "in a forgotten drawer"
        ]
        location = random.choice(scavenge_locations)

        if random.random() < success_chance:
            reward_amount = random.randint(min_reward, max_reward)
            await database.update_balance(user_id, reward_amount)
            current_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="Scavenging Successful!",
                description=f"🔍 You scavenged {location} and found **${reward_amount:,}**!",
                color=discord.Color.green()
            )
            embed.add_field(name="New Balance", value=f"${current_balance:,}", inline=False)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="Scavenging Failed",
                description=f"🔍 You scavenged {location} but found nothing but lint.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

# No setup function needed here, it will be in __init__.py
