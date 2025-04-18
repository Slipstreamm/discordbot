import discord
from discord.ext import commands
import json
import os
import asyncio
import random
import math
from typing import Dict, List, Optional, Union, Set

# File paths for JSON data
LEVELS_FILE = "levels_data.json"
LEVEL_ROLES_FILE = "level_roles.json"
RESTRICTED_CHANNELS_FILE = "level_restricted_channels.json"

# Default XP settings
DEFAULT_XP_PER_MESSAGE = 15
DEFAULT_XP_COOLDOWN = 60  # seconds
DEFAULT_LEVEL_MULTIPLIER = 100  # XP needed per level = level * multiplier

class LevelingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_data = {}  # {user_id: {"xp": int, "level": int, "last_message_time": float}}
        self.level_roles = {}  # {guild_id: {level: role_id}}
        self.restricted_channels = set()  # Set of channel IDs where XP gain is disabled
        self.xp_cooldowns = {}  # {user_id: last_xp_time}

        # Load existing data
        self.load_user_data()
        self.load_level_roles()
        self.load_restricted_channels()

    def load_user_data(self):
        """Load user XP and level data from JSON file"""
        if os.path.exists(LEVELS_FILE):
            try:
                with open(LEVELS_FILE, "r") as f:
                    # Convert string keys (from JSON) back to integers
                    data = json.load(f)
                    self.user_data = {int(k): v for k, v in data.items()}
                print(f"Loaded level data for {len(self.user_data)} users")
            except Exception as e:
                print(f"Error loading level data: {e}")

    def save_user_data(self):
        """Save user XP and level data to JSON file"""
        try:
            # Convert int keys to strings for JSON serialization
            serializable_data = {str(k): v for k, v in self.user_data.items()}
            with open(LEVELS_FILE, "w") as f:
                json.dump(serializable_data, f, indent=4)
        except Exception as e:
            print(f"Error saving level data: {e}")

    def load_level_roles(self):
        """Load level role configuration from JSON file"""
        if os.path.exists(LEVEL_ROLES_FILE):
            try:
                with open(LEVEL_ROLES_FILE, "r") as f:
                    # Convert string keys (from JSON) back to integers
                    data = json.load(f)
                    # Convert nested dictionaries with string keys to integers
                    self.level_roles = {}
                    for guild_id_str, roles_dict in data.items():
                        guild_id = int(guild_id_str)
                        self.level_roles[guild_id] = {int(level): int(role_id) for level, role_id in roles_dict.items()}
                print(f"Loaded level roles for {len(self.level_roles)} guilds")
            except Exception as e:
                print(f"Error loading level roles: {e}")

    def save_level_roles(self):
        """Save level role configuration to JSON file"""
        try:
            # Convert int keys to strings for JSON serialization (for both guild_id and level)
            serializable_data = {}
            for guild_id, roles_dict in self.level_roles.items():
                serializable_data[str(guild_id)] = {str(level): str(role_id) for level, role_id in roles_dict.items()}

            with open(LEVEL_ROLES_FILE, "w") as f:
                json.dump(serializable_data, f, indent=4)
        except Exception as e:
            print(f"Error saving level roles: {e}")

    def load_restricted_channels(self):
        """Load restricted channels from JSON file"""
        if os.path.exists(RESTRICTED_CHANNELS_FILE):
            try:
                with open(RESTRICTED_CHANNELS_FILE, "r") as f:
                    data = json.load(f)
                    # Convert list to set of integers
                    self.restricted_channels = set(int(channel_id) for channel_id in data)
                print(f"Loaded {len(self.restricted_channels)} restricted channels")
            except Exception as e:
                print(f"Error loading restricted channels: {e}")

    def save_restricted_channels(self):
        """Save restricted channels to JSON file"""
        try:
            # Convert set to list of strings for JSON serialization
            serializable_data = [str(channel_id) for channel_id in self.restricted_channels]
            with open(RESTRICTED_CHANNELS_FILE, "w") as f:
                json.dump(serializable_data, f, indent=4)
        except Exception as e:
            print(f"Error saving restricted channels: {e}")

    def calculate_level(self, xp: int) -> int:
        """Calculate level based on XP"""
        # Level formula: level = sqrt(xp / multiplier)
        return int(math.sqrt(xp / DEFAULT_LEVEL_MULTIPLIER))

    def calculate_xp_for_level(self, level: int) -> int:
        """Calculate XP required for a specific level"""
        return level * level * DEFAULT_LEVEL_MULTIPLIER

    def get_user_data(self, user_id: int) -> Dict:
        """Get user data with defaults if not set"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {"xp": 0, "level": 0, "last_message_time": 0}
        return self.user_data[user_id]

    async def add_xp(self, user_id: int, guild_id: int, xp_amount: int = DEFAULT_XP_PER_MESSAGE) -> Optional[int]:
        """
        Add XP to a user and return new level if leveled up, otherwise None
        """
        user_data = self.get_user_data(user_id)
        current_level = user_data["level"]

        # Add XP
        user_data["xp"] += xp_amount

        # Calculate new level
        new_level = self.calculate_level(user_data["xp"])
        user_data["level"] = new_level

        # Save changes
        self.save_user_data()

        # Return new level if leveled up, otherwise None
        if new_level > current_level:
            # Check if there's a role to assign for this level in this guild
            await self.assign_level_role(user_id, guild_id, new_level)
            return new_level
        return None

    async def assign_level_role(self, user_id: int, guild_id: int, level: int) -> bool:
        """
        Assign role based on user level
        Returns True if role was assigned, False otherwise
        """
        # Check if guild has level roles configured
        if guild_id not in self.level_roles:
            return False

        # Get the guild object
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False

        # Get the member object
        member = guild.get_member(user_id)
        if not member:
            return False

        # Find the highest role that matches the user's level
        highest_matching_level = 0
        highest_role_id = None

        for role_level, role_id in self.level_roles[guild_id].items():
            if role_level <= level and role_level > highest_matching_level:
                highest_matching_level = role_level
                highest_role_id = role_id

        if highest_role_id:
            # Get the role object
            role = guild.get_role(highest_role_id)
            if role and role not in member.roles:
                try:
                    # Remove any other level roles
                    roles_to_remove = []
                    for role_level, role_id in self.level_roles[guild_id].items():
                        if role_id != highest_role_id:
                            other_role = guild.get_role(role_id)
                            if other_role and other_role in member.roles:
                                roles_to_remove.append(other_role)

                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason="Level role update")

                    # Add the new role
                    await member.add_roles(role, reason=f"Reached level {level}")
                    return True
                except discord.Forbidden:
                    print(f"Missing permissions to assign roles in guild {guild_id}")
                except Exception as e:
                    print(f"Error assigning level role: {e}")

        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Event listener for messages to award XP"""
        # Ignore bot messages
        if message.author.bot:
            return

        # Ignore messages in restricted channels
        if message.channel.id in self.restricted_channels:
            return

        # Check cooldown
        user_id = message.author.id
        current_time = message.created_at.timestamp()

        if user_id in self.xp_cooldowns:
            time_diff = current_time - self.xp_cooldowns[user_id]
            if time_diff < DEFAULT_XP_COOLDOWN:
                return  # Still on cooldown

        # Update cooldown
        self.xp_cooldowns[user_id] = current_time

        # Add XP with random variation (10-20 XP)
        xp_amount = random.randint(10, 20)
        new_level = await self.add_xp(user_id, message.guild.id, xp_amount)

        # If user leveled up, send a message
        if new_level:
            try:
                await message.channel.send(
                    f"🎉 Congratulations {message.author.mention}! You've reached level **{new_level}**!",
                    delete_after=10  # Delete after 10 seconds
                )
            except discord.Forbidden:
                pass  # Ignore if we can't send messages

    @commands.hybrid_command(name="level", description="Check your current level and XP")
    async def level_command(self, ctx: commands.Context, member: discord.Member = None):
        """Check your current level and XP or another member's"""
        target = member or ctx.author
        user_data = self.get_user_data(target.id)

        level = user_data["level"]
        xp = user_data["xp"]

        # Calculate XP needed for next level
        next_level = level + 1
        xp_needed = self.calculate_xp_for_level(next_level)
        xp_current = xp - self.calculate_xp_for_level(level)
        xp_required = xp_needed - self.calculate_xp_for_level(level)

        # Create progress bar (20 characters wide)
        progress = xp_current / xp_required
        progress_bar_length = 20
        filled_length = int(progress_bar_length * progress)
        bar = '█' * filled_length + '░' * (progress_bar_length - filled_length)

        embed = discord.Embed(
            title=f"{target.display_name}'s Level",
            description=f"**Level:** {level}\n**XP:** {xp} / {xp_needed}\n\n**Progress to Level {next_level}:**\n[{bar}] {int(progress * 100)}%",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="Show the server's level leaderboard")
    async def leaderboard_command(self, ctx: commands.Context):
        """Show the server's level leaderboard"""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        # Get all members in the guild
        guild_members = {member.id: member for member in ctx.guild.members}

        # Filter user_data to only include members in this guild
        guild_data = {}
        for user_id, data in self.user_data.items():
            if user_id in guild_members:
                guild_data[user_id] = data

        # Sort by XP (descending)
        sorted_data = sorted(guild_data.items(), key=lambda x: x[1]["xp"], reverse=True)

        # Create embed
        embed = discord.Embed(
            title=f"{ctx.guild.name} Level Leaderboard",
            color=discord.Color.gold()
        )

        # Add top 10 users to embed
        for i, (user_id, data) in enumerate(sorted_data[:10], 1):
            member = guild_members[user_id]
            embed.add_field(
                name=f"{i}. {member.display_name}",
                value=f"Level: {data['level']} | XP: {data['xp']}",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="register_level_role", description="Register a role for a specific level")
    @commands.has_permissions(manage_roles=True)
    async def register_level_role(self, ctx: commands.Context, level: int, role: discord.Role):
        """Register a role to be assigned at a specific level"""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        if level < 1:
            await ctx.send("Level must be at least 1.")
            return

        # Initialize guild in level_roles if not exists
        if ctx.guild.id not in self.level_roles:
            self.level_roles[ctx.guild.id] = {}

        # Register the role
        self.level_roles[ctx.guild.id][level] = role.id
        self.save_level_roles()

        await ctx.send(f"✅ Role {role.mention} will now be assigned at level {level}.")

    @commands.hybrid_command(name="remove_level_role", description="Remove a level role registration")
    @commands.has_permissions(manage_roles=True)
    async def remove_level_role(self, ctx: commands.Context, level: int):
        """Remove a level role registration"""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        if ctx.guild.id not in self.level_roles or level not in self.level_roles[ctx.guild.id]:
            await ctx.send("No role is registered for this level.")
            return

        # Remove the role registration
        del self.level_roles[ctx.guild.id][level]
        self.save_level_roles()

        await ctx.send(f"✅ Level {level} role registration has been removed.")

    @commands.hybrid_command(name="list_level_roles", description="List all registered level roles")
    async def list_level_roles(self, ctx: commands.Context):
        """List all registered level roles for this server"""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        if ctx.guild.id not in self.level_roles or not self.level_roles[ctx.guild.id]:
            await ctx.send("No level roles are registered for this server.")
            return

        embed = discord.Embed(
            title=f"Level Roles for {ctx.guild.name}",
            color=discord.Color.blue()
        )

        # Sort by level
        sorted_roles = sorted(self.level_roles[ctx.guild.id].items())

        for level, role_id in sorted_roles:
            role = ctx.guild.get_role(role_id)
            role_name = role.mention if role else f"Unknown Role (ID: {role_id})"
            embed.add_field(
                name=f"Level {level}",
                value=role_name,
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="restrict_channel", description="Restrict a channel from giving XP")
    @commands.has_permissions(manage_channels=True)
    async def restrict_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Restrict a channel from giving XP"""
        target_channel = channel or ctx.channel

        if target_channel.id in self.restricted_channels:
            await ctx.send(f"{target_channel.mention} is already restricted from giving XP.")
            return

        self.restricted_channels.add(target_channel.id)
        self.save_restricted_channels()
        await ctx.send(f"✅ {target_channel.mention} will no longer give XP for messages.")

    @commands.hybrid_command(name="unrestrict_channel", description="Allow a channel to give XP again")
    @commands.has_permissions(manage_channels=True)
    async def unrestrict_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Allow a channel to give XP again"""
        target_channel = channel or ctx.channel

        if target_channel.id not in self.restricted_channels:
            await ctx.send(f"{target_channel.mention} is not restricted from giving XP.")
            return

        self.restricted_channels.remove(target_channel.id)
        self.save_restricted_channels()
        await ctx.send(f"✅ {target_channel.mention} will now give XP for messages.")

    @commands.hybrid_command(name="process_existing_messages", description="Process existing messages to award XP")
    @commands.is_owner()
    async def process_existing_messages(self, ctx: commands.Context, limit: int = 10000):
        """Process existing messages to award XP (Owner only)"""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        status_message = await ctx.send(f"Processing existing messages (up to {limit} per channel)...")

        total_processed = 0
        total_channels = 0

        # Get all text channels in the guild
        text_channels = [channel for channel in ctx.guild.channels if isinstance(channel, discord.TextChannel)]

        for channel in text_channels:
            # Skip restricted channels
            if channel.id in self.restricted_channels:
                continue

            try:
                processed_in_channel = 0

                # Update status message
                await status_message.edit(content=f"Processing channel {channel.mention}... ({total_processed} messages processed so far)")

                async for message in channel.history(limit=limit):
                    # Skip bot messages
                    if message.author.bot:
                        continue

                    # Add XP (without cooldown)
                    user_id = message.author.id
                    xp_amount = random.randint(10, 20)
                    await self.add_xp(user_id, ctx.guild.id, xp_amount)

                    processed_in_channel += 1
                    total_processed += 1

                    # Update status every 1000 messages
                    if total_processed % 1000 == 0:
                        await status_message.edit(content=f"Processing channel {channel.mention}... ({total_processed} messages processed so far)")

                total_channels += 1

            except discord.Forbidden:
                await ctx.send(f"Missing permissions to read message history in {channel.mention}")
            except Exception as e:
                await ctx.send(f"Error processing messages in {channel.mention}: {e}")

        # Final update
        await status_message.edit(content=f"✅ Finished processing {total_processed} messages across {total_channels} channels.")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    async def cog_unload(self):
        """Save all data when cog is unloaded"""
        self.save_user_data()
        self.save_level_roles()
        self.save_restricted_channels()
        print(f'{self.__class__.__name__} cog has been unloaded and data saved.')

async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))
