import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import random
import datetime
from typing import Optional

# Import command classes and db functions from submodules
from .economy.database import init_db, close_db, get_balance, update_balance, set_cooldown, check_cooldown
from .economy.database import get_user_job, set_user_job, remove_user_job, get_available_jobs, get_leaderboard
from .economy.earning import EarningCommands
from .economy.gambling import GamblingCommands
from .economy.utility import UtilityCommands
from .economy.risky import RiskyCommands
from .economy.jobs import JobsCommands # Import the new JobsCommands

# Create a database object for function calls
class DatabaseWrapper:
    async def get_balance(self, user_id):
        return await get_balance(user_id)

    async def update_balance(self, user_id, amount):
        return await update_balance(user_id, amount)

    async def set_cooldown(self, user_id, command_name):
        return await set_cooldown(user_id, command_name)

    async def check_cooldown(self, user_id, command_name):
        return await check_cooldown(user_id, command_name)

    async def get_user_job(self, user_id):
        return await get_user_job(user_id)

    async def set_user_job(self, user_id, job_name):
        return await set_user_job(user_id, job_name)

    async def remove_user_job(self, user_id):
        return await remove_user_job(user_id)

    async def get_available_jobs(self):
        return await get_available_jobs()

    async def get_leaderboard(self, limit=10):
        return await get_leaderboard(limit)

# Create an instance of the wrapper
database = DatabaseWrapper()

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

        # Create the main command group for this cog
        self.econ_group = app_commands.Group(
            name="econ",
            description="Economy system commands"
        )

        # Register commands
        self.register_commands()

        # Add command group to the bot's tree
        self.bot.tree.add_command(self.econ_group)

        log.info("EconomyCog initialized with econ command group.")

    def register_commands(self):
        """Register all commands for this cog"""

        # --- Earning Commands ---
        # Daily command
        daily_command = app_commands.Command(
            name="daily",
            description="Claim your daily reward",
            callback=self.economy_daily_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(daily_command)

        # Beg command
        beg_command = app_commands.Command(
            name="beg",
            description="Beg for some spare change",
            callback=self.economy_beg_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(beg_command)

        # Work command
        work_command = app_commands.Command(
            name="work",
            description="Do some work for a guaranteed reward",
            callback=self.economy_work_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(work_command)

        # Scavenge command
        scavenge_command = app_commands.Command(
            name="scavenge",
            description="Scavenge around for some spare change",
            callback=self.economy_scavenge_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(scavenge_command)

        # --- Gambling Commands ---
        # Coinflip command
        coinflip_command = app_commands.Command(
            name="coinflip",
            description="Bet on a coin flip",
            callback=self.economy_coinflip_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(coinflip_command)

        # Slots command
        slots_command = app_commands.Command(
            name="slots",
            description="Play the slot machine",
            callback=self.economy_slots_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(slots_command)

        # --- Utility Commands ---
        # Balance command
        balance_command = app_commands.Command(
            name="balance",
            description="Check your balance",
            callback=self.economy_balance_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(balance_command)

        # Transfer command
        transfer_command = app_commands.Command(
            name="transfer",
            description="Transfer money to another user",
            callback=self.economy_transfer_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(transfer_command)

        # Leaderboard command
        leaderboard_command = app_commands.Command(
            name="leaderboard",
            description="View the economy leaderboard",
            callback=self.economy_leaderboard_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(leaderboard_command)

        # --- Risky Commands ---
        # Rob command
        rob_command = app_commands.Command(
            name="rob",
            description="Attempt to rob another user",
            callback=self.economy_rob_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(rob_command)

        # --- Jobs Commands ---
        # Apply command
        apply_command = app_commands.Command(
            name="apply",
            description="Apply for a job",
            callback=self.economy_apply_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(apply_command)

        # Quit command
        quit_command = app_commands.Command(
            name="quit",
            description="Quit your current job",
            callback=self.economy_quit_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(quit_command)

        # List command
        joblist_command = app_commands.Command(
            name="joblist",
            description="List available jobs",
            callback=self.economy_joblist_callback,
            parent=self.econ_group
        )
        self.econ_group.add_command(joblist_command)

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

    # --- Command Callbacks ---
    # Earning group callbacks
    async def economy_daily_callback(self, interaction: discord.Interaction):
        """Callback for /economy earning daily command"""
        user_id = interaction.user.id
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
                await interaction.response.send_message(embed=embed, ephemeral=True)
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
        await interaction.response.send_message(embed=embed)

    async def economy_beg_callback(self, interaction: discord.Interaction):
        """Callback for /economy earning beg command"""
        user_id = interaction.user.id
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
                await interaction.response.send_message(embed=embed, ephemeral=True)
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
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="Begging Failed",
                description="🤷 Nobody gave you anything. Better luck next time!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)

    async def economy_work_callback(self, interaction: discord.Interaction):
        """Callback for /economy earning work command"""
        user_id = interaction.user.id
        command_name = "work"
        cooldown_duration = datetime.timedelta(hours=1) # 1-hour cooldown
        reward_amount = random.randint(15, 35) # Small reward range - This is now fallback if no job

        # --- Check if user has a job ---
        job_info = await database.get_user_job(user_id)
        if job_info and job_info.get("name"):
            job_key = job_info["name"]
            command_to_use = f"`/economy jobs {job_key}`" # Updated command path
            embed = discord.Embed(description=f"💼 You have a job! Use {command_to_use} instead of the generic work command.", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        # --- End Job Check ---

        # Proceed with generic work only if no job
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
                await interaction.response.send_message(embed=embed, ephemeral=True)
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
        await interaction.response.send_message(embed=embed)

    async def economy_scavenge_callback(self, interaction: discord.Interaction):
        """Callback for /economy earning scavenge command"""
        user_id = interaction.user.id
        command_name = "scavenge"
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
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        # Set cooldown regardless of success
        await database.set_cooldown(user_id, command_name)

        # Flavor text for scavenging
        scavenge_locations = [
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
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="Scavenging Failed",
                description=f"🔍 You scavenged {location} but found nothing but lint.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)

    # Gambling group callbacks
    async def economy_coinflip_callback(self, interaction: discord.Interaction, bet: int, choice: app_commands.Choice[str]):
        """Callback for /economy gambling coinflip command"""
        user_id = interaction.user.id

        # Validate bet amount
        if bet <= 0:
            await interaction.response.send_message("❌ Your bet must be greater than 0.", ephemeral=True)
            return

        # Check if user has enough money
        balance = await database.get_balance(user_id)
        if bet > balance:
            await interaction.response.send_message(f"❌ You don't have enough money. Your balance: ${balance:,}", ephemeral=True)
            return

        # Process the bet
        result = "Heads" if random.random() < 0.5 else "Tails"
        user_choice = choice.value

        # Determine outcome
        if result == user_choice:
            # Win - double the bet
            winnings = bet
            await database.update_balance(user_id, winnings)
            new_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="Coinflip Win!",
                description=f"The coin landed on **{result}**! You won **${winnings:,}**!",
                color=discord.Color.green()
            )
            embed.add_field(name="New Balance", value=f"${new_balance:,}", inline=False)
        else:
            # Lose - subtract the bet
            await database.update_balance(user_id, -bet)
            new_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="Coinflip Loss",
                description=f"The coin landed on **{result}**. You lost **${bet:,}**.",
                color=discord.Color.red()
            )
            embed.add_field(name="New Balance", value=f"${new_balance:,}", inline=False)

        await interaction.response.send_message(embed=embed)

    async def economy_slots_callback(self, interaction: discord.Interaction, bet: int):
        """Callback for /economy gambling slots command"""
        user_id = interaction.user.id

        # Validate bet amount
        if bet <= 0:
            await interaction.response.send_message("❌ Your bet must be greater than 0.", ephemeral=True)
            return

        # Check if user has enough money
        balance = await database.get_balance(user_id)
        if bet > balance:
            await interaction.response.send_message(f"❌ You don't have enough money. Your balance: ${balance:,}", ephemeral=True)
            return

        # Define slot symbols and their payouts
        symbols = ["🍒", "🍊", "🍋", "🍇", "🍉", "💎", "7️⃣"]
        payouts = {
            "🍒🍒🍒": 2,    # 2x bet
            "🍊🍊🍊": 3,    # 3x bet
            "🍋🍋🍋": 4,    # 4x bet
            "🍇🍇🍇": 5,    # 5x bet
            "🍉🍉🍉": 8,    # 8x bet
            "💎💎💎": 10,   # 10x bet
            "7️⃣7️⃣7️⃣": 20,   # 20x bet
        }

        # Spin the slots
        result = [random.choice(symbols) for _ in range(3)]
        result_str = "".join(result)

        # Check for win
        win_multiplier = payouts.get(result_str, 0)

        if win_multiplier > 0:
            # Win
            winnings = bet * win_multiplier
            await database.update_balance(user_id, winnings - bet)  # Subtract bet, add winnings
            new_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="🎰 Slots Win!",
                description=f"[ {result[0]} | {result[1]} | {result[2]} ]\n\nYou won **${winnings:,}**! ({win_multiplier}x)",
                color=discord.Color.green()
            )
            embed.add_field(name="New Balance", value=f"${new_balance:,}", inline=False)
        else:
            # Lose
            await database.update_balance(user_id, -bet)
            new_balance = await database.get_balance(user_id)
            embed = discord.Embed(
                title="🎰 Slots Loss",
                description=f"[ {result[0]} | {result[1]} | {result[2]} ]\n\nYou lost **${bet:,}**.",
                color=discord.Color.red()
            )
            embed.add_field(name="New Balance", value=f"${new_balance:,}", inline=False)

        await interaction.response.send_message(embed=embed)

    # Utility group callbacks
    async def economy_balance_callback(self, interaction: discord.Interaction, user: discord.Member = None):
        """Callback for /economy utility balance command"""
        target_user = user or interaction.user
        user_id = target_user.id

        balance = await database.get_balance(user_id)

        if target_user == interaction.user:
            embed = discord.Embed(
                title="Your Balance",
                description=f"💰 You have **${balance:,}**",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title=f"{target_user.display_name}'s Balance",
                description=f"💰 {target_user.mention} has **${balance:,}**",
                color=discord.Color.blue()
            )

        await interaction.response.send_message(embed=embed)

    async def economy_transfer_callback(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Callback for /economy utility transfer command"""
        sender_id = interaction.user.id
        receiver_id = user.id

        # Validate transfer
        if sender_id == receiver_id:
            await interaction.response.send_message("❌ You can't transfer money to yourself.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Transfer amount must be greater than 0.", ephemeral=True)
            return

        # Check if sender has enough money
        sender_balance = await database.get_balance(sender_id)
        if amount > sender_balance:
            await interaction.response.send_message(f"❌ You don't have enough money. Your balance: ${sender_balance:,}", ephemeral=True)
            return

        # Process transfer
        await database.update_balance(sender_id, -amount)
        await database.update_balance(receiver_id, amount)

        # Get updated balances
        new_sender_balance = await database.get_balance(sender_id)

        embed = discord.Embed(
            title="Transfer Complete",
            description=f"💸 You sent **${amount:,}** to {user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Your New Balance", value=f"${new_sender_balance:,}", inline=False)

        await interaction.response.send_message(embed=embed)

    async def economy_leaderboard_callback(self, interaction: discord.Interaction):
        """Callback for /economy utility leaderboard command"""
        # Get top 10 users by balance
        leaderboard_data = await database.get_leaderboard(limit=10)

        if not leaderboard_data:
            await interaction.response.send_message("No users found in the economy system yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Economy Leaderboard",
            description="Top 10 richest users",
            color=discord.Color.gold()
        )

        for i, (user_id, balance) in enumerate(leaderboard_data):
            try:
                user = await self.bot.fetch_user(user_id)
                username = user.display_name
            except:
                username = f"User {user_id}"

            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            embed.add_field(
                name=f"{medal} {username}",
                value=f"${balance:,}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    # Risky group callbacks
    async def economy_rob_callback(self, interaction: discord.Interaction, user: discord.Member):
        """Callback for /economy risky rob command"""
        robber_id = interaction.user.id
        victim_id = user.id

        # Validate rob attempt
        if robber_id == victim_id:
            await interaction.response.send_message("❌ You can't rob yourself.", ephemeral=True)
            return

        # Check cooldown
        command_name = "rob"
        cooldown_duration = datetime.timedelta(hours=1)
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
                embed = discord.Embed(description=f"🕒 You can't rob again so soon. Try again in **{hours}h {minutes}m {seconds}s**.", color=discord.Color.orange())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        # Set cooldown regardless of outcome
        await database.set_cooldown(robber_id, command_name)

        # Get balances
        robber_balance = await database.get_balance(robber_id)
        victim_balance = await database.get_balance(victim_id)

        # Minimum balance requirements
        min_robber_balance = 50
        min_victim_balance = 100

        if robber_balance < min_robber_balance:
            embed = discord.Embed(
                title="Rob Failed",
                description=f"❌ You need at least **${min_robber_balance}** to attempt a robbery.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        if victim_balance < min_victim_balance:
            embed = discord.Embed(
                title="Rob Failed",
                description=f"❌ {user.mention} doesn't have enough money to be worth robbing.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            return

        # Determine success (30% chance)
        success_chance = 0.3
        if random.random() < success_chance:
            # Success - steal 10-30% of victim's balance
            steal_percent = random.uniform(0.1, 0.3)
            steal_amount = int(victim_balance * steal_percent)

            # Update balances
            await database.update_balance(robber_id, steal_amount)
            await database.update_balance(victim_id, -steal_amount)

            # Get updated balance
            new_robber_balance = await database.get_balance(robber_id)

            embed = discord.Embed(
                title="Rob Successful!",
                description=f"💰 You successfully robbed {user.mention} and got away with **${steal_amount:,}**!",
                color=discord.Color.green()
            )
            embed.add_field(name="Your New Balance", value=f"${new_robber_balance:,}", inline=False)
        else:
            # Failure - lose 10-20% of your balance as a fine
            fine_percent = random.uniform(0.1, 0.2)
            fine_amount = int(robber_balance * fine_percent)

            # Update balance
            await database.update_balance(robber_id, -fine_amount)

            # Get updated balance
            new_robber_balance = await database.get_balance(robber_id)

            embed = discord.Embed(
                title="Rob Failed",
                description=f"🚔 You were caught trying to rob {user.mention} and had to pay a fine of **${fine_amount:,}**!",
                color=discord.Color.red()
            )
            embed.add_field(name="Your New Balance", value=f"${new_robber_balance:,}", inline=False)

        await interaction.response.send_message(embed=embed)

    # Jobs group callbacks
    async def economy_apply_callback(self, interaction: discord.Interaction, job: app_commands.Choice[str]):
        """Callback for /economy jobs apply command"""
        user_id = interaction.user.id
        job_name = job.value

        # Check if user already has a job
        current_job = await database.get_user_job(user_id)
        if current_job and current_job.get("name"):
            embed = discord.Embed(
                description=f"❌ You already have a job as a {current_job['name']}. You must quit first before applying for a new job.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Apply for the job
        success = await database.set_user_job(user_id, job_name)

        if success:
            embed = discord.Embed(
                title="Job Application Successful!",
                description=f"🎉 Congratulations! You are now employed as a **{job_name}**.",
                color=discord.Color.green()
            )
            embed.add_field(name="Next Steps", value=f"Use `/economy jobs {job_name}` to work at your new job!", inline=False)
        else:
            embed = discord.Embed(
                title="Job Application Failed",
                description="❌ There was an error processing your job application. Please try again later.",
                color=discord.Color.red()
            )

        await interaction.response.send_message(embed=embed)

    async def economy_quit_callback(self, interaction: discord.Interaction):
        """Callback for /economy jobs quit command"""
        user_id = interaction.user.id

        # Check if user has a job
        current_job = await database.get_user_job(user_id)
        if not current_job or not current_job.get("name"):
            embed = discord.Embed(
                description="❌ You don't currently have a job to quit.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        job_name = current_job.get("name")

        # Quit the job
        success = await database.remove_user_job(user_id)

        if success:
            embed = discord.Embed(
                title="Job Resignation",
                description=f"✅ You have successfully quit your job as a **{job_name}**.",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="Error",
                description="❌ There was an error processing your resignation. Please try again later.",
                color=discord.Color.red()
            )

        await interaction.response.send_message(embed=embed)

    async def economy_joblist_callback(self, interaction: discord.Interaction):
        """Callback for /economy jobs list command"""
        # Get list of available jobs
        jobs = await database.get_available_jobs()

        if not jobs:
            await interaction.response.send_message("No jobs are currently available.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Available Jobs",
            description="Here are the jobs you can apply for:",
            color=discord.Color.blue()
        )

        for job in jobs:
            embed.add_field(
                name=f"{job['name']} - ${job['base_pay']} per shift",
                value=job['description'],
                inline=False
            )

        embed.set_footer(text="Apply for a job with /economy jobs apply")
        await interaction.response.send_message(embed=embed)

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
    print("Setting up EconomyCog...")
    cog = EconomyCog(bot)
    await bot.add_cog(cog)
    log.info("Combined EconomyCog added to bot with econ command group.")
    print(f"EconomyCog setup complete with command group: {[cmd.name for cmd in bot.tree.get_commands() if cmd.name == 'econ']}")
    print(f"Available commands: {[cmd.name for cmd in cog.econ_group.walk_commands() if isinstance(cmd, app_commands.Command)]}")
