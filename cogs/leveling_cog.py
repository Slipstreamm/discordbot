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
LEVEL_CONFIG_FILE = "level_config.json"

# Default XP settings
DEFAULT_XP_PER_MESSAGE = 15
DEFAULT_XP_PER_REACTION = 5
DEFAULT_XP_COOLDOWN = 30  # seconds
DEFAULT_REACTION_COOLDOWN = 30  # seconds
DEFAULT_LEVEL_MULTIPLIER = 35  # XP needed per level = level * multiplier

class LevelingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_data = {}  # {user_id: {"xp": int, "level": int, "last_message_time": float}}
        self.level_roles = {}  # {guild_id: {level: role_id}}
        self.restricted_channels = set()  # Set of channel IDs where XP gain is disabled
        self.xp_cooldowns = {}  # {user_id: last_xp_time}
        self.reaction_cooldowns = {}  # {user_id: last_reaction_time}

        # Configuration settings
        self.config = {
            "xp_per_message": DEFAULT_XP_PER_MESSAGE,
            "xp_per_reaction": DEFAULT_XP_PER_REACTION,
            "message_cooldown": DEFAULT_XP_COOLDOWN,
            "reaction_cooldown": DEFAULT_REACTION_COOLDOWN,
            "reaction_xp_enabled": True
        }

        # Load existing data
        self.load_user_data()
        self.load_level_roles()
        self.load_restricted_channels()
        self.load_config()

    def load_user_data(self):
        """Load user XP and level data from JSON file"""
        if os.path.exists(LEVELS_FILE):
            try:
                with open(LEVELS_FILE, "r", encoding="utf-8") as f:
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
            with open(LEVELS_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving level data: {e}")

    def load_level_roles(self):
        """Load level role configuration from JSON file"""
        if os.path.exists(LEVEL_ROLES_FILE):
            try:
                with open(LEVEL_ROLES_FILE, "r", encoding="utf-8") as f:
                    # Convert string keys (from JSON) back to integers
                    data = json.load(f)
                    # Convert nested dictionaries with string keys to integers
                    self.level_roles = {}
                    for guild_id_str, roles_dict in data.items():
                        guild_id = int(guild_id_str)
                        self.level_roles[guild_id] = {}

                        # Process each level's role data
                        for level_str, role_data in roles_dict.items():
                            level = int(level_str)

                            # Check if this is a gendered role entry
                            if isinstance(role_data, dict):
                                # Handle gendered roles
                                self.level_roles[guild_id][level] = {}
                                for gender, role_id_str in role_data.items():
                                    self.level_roles[guild_id][level][gender] = int(role_id_str)
                            else:
                                # Handle regular roles
                                self.level_roles[guild_id][level] = int(role_data)

                print(f"Loaded level roles for {len(self.level_roles)} guilds")
            except Exception as e:
                print(f"Error loading level roles: {e}")

    def save_level_roles(self):
        """Save level role configuration to JSON file"""
        try:
            # Convert int keys to strings for JSON serialization (for both guild_id and level)
            serializable_data = {}
            for guild_id, roles_dict in self.level_roles.items():
                serializable_data[str(guild_id)] = {}

                # Handle both regular and gendered roles
                for level, role_data in roles_dict.items():
                    if isinstance(role_data, dict):
                        # Handle gendered roles
                        serializable_data[str(guild_id)][str(level)] = {
                            gender: str(role_id) for gender, role_id in role_data.items()
                        }
                    else:
                        # Handle regular roles
                        serializable_data[str(guild_id)][str(level)] = str(role_data)

            with open(LEVEL_ROLES_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving level roles: {e}")

    def load_restricted_channels(self):
        """Load restricted channels from JSON file"""
        if os.path.exists(RESTRICTED_CHANNELS_FILE):
            try:
                with open(RESTRICTED_CHANNELS_FILE, "r", encoding="utf-8") as f:
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
            with open(RESTRICTED_CHANNELS_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving restricted channels: {e}")

    def load_config(self):
        """Load leveling configuration from JSON file"""
        if os.path.exists(LEVEL_CONFIG_FILE):
            try:
                with open(LEVEL_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Update config with saved values, keeping defaults for missing keys
                    for key, value in data.items():
                        if key in self.config:
                            self.config[key] = value
                print(f"Loaded leveling configuration")
            except Exception as e:
                print(f"Error loading leveling configuration: {e}")

    def save_config(self):
        """Save leveling configuration to JSON file"""
        try:
            with open(LEVEL_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving leveling configuration: {e}")

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

        # Check if we need to handle gendered roles
        gender = None

        # Check if the user has pronoun roles
        for role in member.roles:
            role_name_lower = role.name.lower()
            if "he/him" in role_name_lower:
                gender = "male"
                break
            elif "she/her" in role_name_lower:
                gender = "female"
                break

        # Process level roles
        for role_level, role_data in self.level_roles[guild_id].items():
            if role_level <= level and role_level > highest_matching_level:
                highest_matching_level = role_level

                # Handle gendered roles if available
                if isinstance(role_data, dict) and gender in role_data:
                    highest_role_id = role_data[gender]
                elif isinstance(role_data, dict) and "male" in role_data and "female" in role_data:
                    # If we have gendered roles but no gender preference, use male as default
                    highest_role_id = role_data["male"]
                else:
                    # Regular role ID
                    highest_role_id = role_data

        if highest_role_id:
            # Get the role object
            role = guild.get_role(highest_role_id)
            if role and role not in member.roles:
                try:
                    # Remove any other level roles
                    roles_to_remove = []

                    for role_level, role_data in self.level_roles[guild_id].items():
                        # Handle both regular and gendered roles
                        if isinstance(role_data, dict):
                            # For gendered roles, check all gender variants
                            for gender_role_id in role_data.values():
                                if gender_role_id != highest_role_id:
                                    other_role = guild.get_role(gender_role_id)
                                    if other_role and other_role in member.roles:
                                        roles_to_remove.append(other_role)
                        elif role_data != highest_role_id:
                            other_role = guild.get_role(role_data)
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
            if time_diff < self.config["message_cooldown"]:
                return  # Still on cooldown

        # Update cooldown
        self.xp_cooldowns[user_id] = current_time

        # Add XP with random variation (base ±5 XP)
        base_xp = self.config["xp_per_message"]
        xp_amount = random.randint(max(1, base_xp - 5), base_xp + 5)
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
    async def on_raw_reaction_add(self, payload):
        """Event listener for reactions to award XP"""
        # Check if reaction XP is enabled
        if not self.config["reaction_xp_enabled"]:
            return

        # Ignore bot reactions
        if payload.member and payload.member.bot:
            return

        # Get the channel
        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        # Ignore reactions in restricted channels
        if channel.id in self.restricted_channels:
            return

        # Check cooldown
        user_id = payload.user_id
        current_time = discord.utils.utcnow().timestamp()

        if user_id in self.reaction_cooldowns:
            time_diff = current_time - self.reaction_cooldowns[user_id]
            if time_diff < self.config["reaction_cooldown"]:
                return  # Still on cooldown

        # Update cooldown
        self.reaction_cooldowns[user_id] = current_time

        # Add XP with small random variation (base ±2 XP)
        base_xp = self.config["xp_per_reaction"]
        xp_amount = random.randint(max(1, base_xp - 2), base_xp + 2)
        new_level = await self.add_xp(user_id, payload.guild_id, xp_amount)

        # If user leveled up, send a DM to avoid channel spam
        if new_level:
            try:
                member = channel.guild.get_member(user_id)
                if member:
                    await member.send(f"🎉 Congratulations! You've reached level **{new_level}**!")
            except discord.Forbidden:
                pass  # Ignore if we can't send DMs

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    async def cog_unload(self):
        """Save all data when cog is unloaded"""
        self.save_user_data()
        self.save_level_roles()
        self.save_restricted_channels()
        self.save_config()
        print(f'{self.__class__.__name__} cog has been unloaded and data saved.')

    @commands.hybrid_command(name="xp_config", description="Configure XP settings")
    @commands.has_permissions(administrator=True)
    async def xp_config(self, ctx: commands.Context, setting: str = None, value: str = None):
        """Configure XP settings for the leveling system"""
        if not setting:
            # Display current settings
            embed = discord.Embed(
                title="XP Configuration Settings",
                description="Current XP settings for the leveling system:",
                color=discord.Color.blue()
            )

            embed.add_field(name="XP Per Message", value=str(self.config["xp_per_message"]), inline=True)
            embed.add_field(name="XP Per Reaction", value=str(self.config["xp_per_reaction"]), inline=True)
            embed.add_field(name="Message Cooldown", value=f"{self.config['message_cooldown']} seconds", inline=True)
            embed.add_field(name="Reaction Cooldown", value=f"{self.config['reaction_cooldown']} seconds", inline=True)
            embed.add_field(name="Reaction XP Enabled", value="Yes" if self.config["reaction_xp_enabled"] else "No", inline=True)

            embed.set_footer(text="Use !xp_config <setting> <value> to change a setting")
            await ctx.send(embed=embed)
            return

        if not value:
            await ctx.send("Please provide a value for the setting.")
            return

        setting = setting.lower()

        if setting == "xp_per_message":
            try:
                xp = int(value)
                if xp < 1 or xp > 100:
                    await ctx.send("XP per message must be between 1 and 100.")
                    return
                self.config["xp_per_message"] = xp
                await ctx.send(f"✅ XP per message set to {xp}.")
            except ValueError:
                await ctx.send("Value must be a number.")

        elif setting == "xp_per_reaction":
            try:
                xp = int(value)
                if xp < 1 or xp > 50:
                    await ctx.send("XP per reaction must be between 1 and 50.")
                    return
                self.config["xp_per_reaction"] = xp
                await ctx.send(f"✅ XP per reaction set to {xp}.")
            except ValueError:
                await ctx.send("Value must be a number.")

        elif setting == "message_cooldown":
            try:
                cooldown = int(value)
                if cooldown < 0 or cooldown > 3600:
                    await ctx.send("Message cooldown must be between 0 and 3600 seconds.")
                    return
                self.config["message_cooldown"] = cooldown
                await ctx.send(f"✅ Message cooldown set to {cooldown} seconds.")
            except ValueError:
                await ctx.send("Value must be a number.")

        elif setting == "reaction_cooldown":
            try:
                cooldown = int(value)
                if cooldown < 0 or cooldown > 3600:
                    await ctx.send("Reaction cooldown must be between 0 and 3600 seconds.")
                    return
                self.config["reaction_cooldown"] = cooldown
                await ctx.send(f"✅ Reaction cooldown set to {cooldown} seconds.")
            except ValueError:
                await ctx.send("Value must be a number.")

        elif setting == "reaction_xp_enabled":
            value = value.lower()
            if value in ["true", "yes", "on", "1", "enable", "enabled"]:
                self.config["reaction_xp_enabled"] = True
                await ctx.send("✅ Reaction XP has been enabled.")
            elif value in ["false", "no", "off", "0", "disable", "disabled"]:
                self.config["reaction_xp_enabled"] = False
                await ctx.send("✅ Reaction XP has been disabled.")
            else:
                await ctx.send("Value must be 'true' or 'false'.")

        else:
            await ctx.send(f"Unknown setting: {setting}. Available settings: xp_per_message, xp_per_reaction, message_cooldown, reaction_cooldown, reaction_xp_enabled")
            return

        # Save the updated configuration
        self.save_config()

    @commands.hybrid_command(name="setup_medieval_roles", description="Set up medieval-themed level roles")
    @commands.has_permissions(manage_roles=True)
    async def setup_medieval_roles(self, ctx: commands.Context):
        """Automatically set up medieval-themed level roles with gender customization"""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        # Define the medieval role structure with levels and titles
        medieval_roles = {
            1: {"default": "Peasant", "male": "Peasant", "female": "Peasant"},
            5: {"default": "Squire", "male": "Squire", "female": "Squire"},
            10: {"default": "Knight", "male": "Knight", "female": "Dame"},
            20: {"default": "Baron/Baroness", "male": "Baron", "female": "Baroness"},
            30: {"default": "Count/Countess", "male": "Count", "female": "Countess"},
            50: {"default": "Duke/Duchess", "male": "Duke", "female": "Duchess"},
            75: {"default": "Prince/Princess", "male": "Prince", "female": "Princess"},
            100: {"default": "King/Queen", "male": "King", "female": "Queen"}
        }

        # Colors for the roles (gradient from gray to gold)
        colors = {
            1: discord.Color.from_rgb(128, 128, 128),  # Gray
            5: discord.Color.from_rgb(153, 153, 153),  # Light Gray
            10: discord.Color.from_rgb(170, 170, 170), # Silver
            20: discord.Color.from_rgb(218, 165, 32),  # Goldenrod
            30: discord.Color.from_rgb(255, 215, 0),   # Gold
            50: discord.Color.from_rgb(255, 223, 0),   # Bright Gold
            75: discord.Color.from_rgb(255, 235, 0),   # Royal Gold
            100: discord.Color.from_rgb(255, 255, 0)   # Yellow/Gold
        }

        # Initialize guild in level_roles if not exists
        if ctx.guild.id not in self.level_roles:
            self.level_roles[ctx.guild.id] = {}

        status_message = await ctx.send("Creating medieval-themed level roles...")
        created_roles = []
        updated_roles = []

        # Check if the server has pronoun roles
        pronoun_roles = {}
        for role in ctx.guild.roles:
            role_name_lower = role.name.lower()
            if "he/him" in role_name_lower:
                pronoun_roles["male"] = role
            elif "she/her" in role_name_lower:
                pronoun_roles["female"] = role

        has_pronoun_roles = len(pronoun_roles) > 0

        # Create or update roles for each level
        for level, titles in medieval_roles.items():
            # For servers without pronoun roles, use the default title
            if not has_pronoun_roles:
                role_name = f"Level {level} - {titles['default']}"

                # Check if role already exists
                existing_role = discord.utils.get(ctx.guild.roles, name=role_name)

                if existing_role:
                    # Update existing role
                    try:
                        await existing_role.edit(color=colors[level], reason="Updating medieval level role")
                        updated_roles.append(role_name)
                    except discord.Forbidden:
                        await ctx.send(f"Missing permissions to edit role: {role_name}")
                    except Exception as e:
                        await ctx.send(f"Error updating role {role_name}: {e}")
                else:
                    # Create new role
                    try:
                        role = await ctx.guild.create_role(
                            name=role_name,
                            color=colors[level],
                            reason="Creating medieval level role"
                        )
                        created_roles.append(role_name)
                    except discord.Forbidden:
                        await ctx.send(f"Missing permissions to create role: {role_name}")
                    except Exception as e:
                        await ctx.send(f"Error creating role {role_name}: {e}")
                        continue

                # Register the role for this level
                role_id = existing_role.id if existing_role else role.id
                self.level_roles[ctx.guild.id][level] = role_id

            # For servers with pronoun roles, create separate male and female roles
            else:
                # Create male role
                male_role_name = f"Level {level} - {titles['male']}"
                male_role = discord.utils.get(ctx.guild.roles, name=male_role_name)

                if male_role:
                    try:
                        await male_role.edit(color=colors[level], reason="Updating medieval level role")
                        updated_roles.append(male_role_name)
                    except discord.Forbidden:
                        await ctx.send(f"Missing permissions to edit role: {male_role_name}")
                    except Exception as e:
                        await ctx.send(f"Error updating role {male_role_name}: {e}")
                else:
                    try:
                        male_role = await ctx.guild.create_role(
                            name=male_role_name,
                            color=colors[level],
                            reason="Creating medieval level role"
                        )
                        created_roles.append(male_role_name)
                    except discord.Forbidden:
                        await ctx.send(f"Missing permissions to create role: {male_role_name}")
                    except Exception as e:
                        await ctx.send(f"Error creating role {male_role_name}: {e}")
                        male_role = None

                # Create female role
                female_role_name = f"Level {level} - {titles['female']}"
                female_role = discord.utils.get(ctx.guild.roles, name=female_role_name)

                if female_role:
                    try:
                        await female_role.edit(color=colors[level], reason="Updating medieval level role")
                        updated_roles.append(female_role_name)
                    except discord.Forbidden:
                        await ctx.send(f"Missing permissions to edit role: {female_role_name}")
                    except Exception as e:
                        await ctx.send(f"Error updating role {female_role_name}: {e}")
                else:
                    try:
                        female_role = await ctx.guild.create_role(
                            name=female_role_name,
                            color=colors[level],
                            reason="Creating medieval level role"
                        )
                        created_roles.append(female_role_name)
                    except discord.Forbidden:
                        await ctx.send(f"Missing permissions to create role: {female_role_name}")
                    except Exception as e:
                        await ctx.send(f"Error creating role {female_role_name}: {e}")
                        female_role = None

                # Create a special entry for gendered roles
                if level not in self.level_roles[ctx.guild.id]:
                    self.level_roles[ctx.guild.id][level] = {}

                # Store the role IDs with gender information
                if male_role:
                    self.level_roles[ctx.guild.id][level]["male"] = male_role.id
                if female_role:
                    self.level_roles[ctx.guild.id][level]["female"] = female_role.id

        # Save the updated level roles
        self.save_level_roles()

        # Update status message
        created_str = "\n".join(created_roles) if created_roles else "None"
        updated_str = "\n".join(updated_roles) if updated_roles else "None"

        embed = discord.Embed(
            title="Medieval Level Roles Setup",
            description="The following roles have been set up for the medieval leveling system:",
            color=discord.Color.gold()
        )

        if created_roles:
            embed.add_field(name="Created Roles", value=created_str, inline=False)
        if updated_roles:
            embed.add_field(name="Updated Roles", value=updated_str, inline=False)

        embed.add_field(
            name="Gender Detection",
            value="Gender-specific roles will be assigned based on pronoun roles." if has_pronoun_roles else "No pronoun roles detected. Using default titles.",
            inline=False
        )

        await status_message.edit(content=None, embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))
