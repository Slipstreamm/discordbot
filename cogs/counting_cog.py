import discord
from discord.ext import commands
from discord import app_commands
import logging
import re
import asyncio
from typing import Optional, Union

# Import settings manager for storing guild-specific settings
import settings_manager

# Set up logging
log = logging.getLogger(__name__)

class CountingCog(commands.Cog):
    """A cog that manages a counting channel where users can only post sequential numbers."""
    
    def __init__(self, bot):
        self.bot = bot
        self.counting_channels = {}  # Cache for counting channels {guild_id: channel_id}
        self.current_counts = {}     # Cache for current counts {guild_id: current_number}
        self.last_user = {}          # Cache to track the last user who sent a number {guild_id: user_id}
        
        # Register commands
        self.counting_group = app_commands.Group(
            name="counting",
            description="Commands for managing the counting channel",
            guild_only=True
        )
        self.register_commands()
        
        log.info("CountingCog initialized")
    
    def register_commands(self):
        """Register all commands for this cog"""
        
        # Set counting channel command
        set_channel_command = app_commands.Command(
            name="setchannel",
            description="Set the current channel as the counting channel",
            callback=self.counting_set_channel_callback,
            parent=self.counting_group
        )
        self.counting_group.add_command(set_channel_command)
        
        # Disable counting command
        disable_command = app_commands.Command(
            name="disable",
            description="Disable the counting feature for this server",
            callback=self.counting_disable_callback,
            parent=self.counting_group
        )
        self.counting_group.add_command(disable_command)
        
        # Reset count command
        reset_command = app_commands.Command(
            name="reset",
            description="Reset the count to 0",
            callback=self.counting_reset_callback,
            parent=self.counting_group
        )
        self.counting_group.add_command(reset_command)
        
        # Get current count command
        status_command = app_commands.Command(
            name="status",
            description="Show the current count and counting channel",
            callback=self.counting_status_callback,
            parent=self.counting_group
        )
        self.counting_group.add_command(status_command)
    
    async def cog_load(self):
        """Called when the cog is loaded."""
        log.info("Loading CountingCog")
        # Add the command group to the bot
        self.bot.tree.add_command(self.counting_group)
    
    async def cog_unload(self):
        """Called when the cog is unloaded."""
        log.info("Unloading CountingCog")
        # Remove the command group from the bot
        self.bot.tree.remove_command(self.counting_group.name, type=self.counting_group.type)
    
    async def load_counting_data(self, guild_id: int):
        """Load counting channel and current count from database."""
        channel_id_str = await settings_manager.get_setting(guild_id, 'counting_channel_id')
        current_count_str = await settings_manager.get_setting(guild_id, 'counting_current_number', default='0')
        
        if channel_id_str:
            self.counting_channels[guild_id] = int(channel_id_str)
            self.current_counts[guild_id] = int(current_count_str)
            last_user_str = await settings_manager.get_setting(guild_id, 'counting_last_user', default=None)
            if last_user_str:
                self.last_user[guild_id] = int(last_user_str)
            return True
        return False
    
    # Command callbacks
    async def counting_set_channel_callback(self, interaction: discord.Interaction):
        """Set the current channel as the counting channel."""
        # Check if user has manage channels permission
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You need the 'Manage Channels' permission to use this command.", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        
        # Save to database
        await settings_manager.set_setting(guild_id, 'counting_channel_id', str(channel_id))
        await settings_manager.set_setting(guild_id, 'counting_current_number', '0')
        
        # Update cache
        self.counting_channels[guild_id] = channel_id
        self.current_counts[guild_id] = 0
        if guild_id in self.last_user:
            del self.last_user[guild_id]
        
        await interaction.response.send_message(f"✅ This channel has been set as the counting channel! The count starts at 1.", ephemeral=False)
    
    async def counting_disable_callback(self, interaction: discord.Interaction):
        """Disable the counting feature for this server."""
        # Check if user has manage channels permission
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You need the 'Manage Channels' permission to use this command.", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        
        # Remove from database
        await settings_manager.set_setting(guild_id, 'counting_channel_id', None)
        await settings_manager.set_setting(guild_id, 'counting_current_number', None)
        await settings_manager.set_setting(guild_id, 'counting_last_user', None)
        
        # Update cache
        if guild_id in self.counting_channels:
            del self.counting_channels[guild_id]
        if guild_id in self.current_counts:
            del self.current_counts[guild_id]
        if guild_id in self.last_user:
            del self.last_user[guild_id]
        
        await interaction.response.send_message("✅ Counting feature has been disabled for this server.", ephemeral=True)
    
    async def counting_reset_callback(self, interaction: discord.Interaction):
        """Reset the count to 0."""
        # Check if user has manage channels permission
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ You need the 'Manage Channels' permission to use this command.", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        
        # Check if counting is enabled
        if guild_id not in self.counting_channels:
            await self.load_counting_data(guild_id)
            if guild_id not in self.counting_channels:
                await interaction.response.send_message("❌ Counting is not enabled for this server. Use `/counting setchannel` first.", ephemeral=True)
                return
        
        # Reset count in database
        await settings_manager.set_setting(guild_id, 'counting_current_number', '0')
        
        # Update cache
        self.current_counts[guild_id] = 0
        if guild_id in self.last_user:
            del self.last_user[guild_id]
        
        await interaction.response.send_message("✅ The count has been reset to 0. The next number is 1.", ephemeral=False)
    
    async def counting_status_callback(self, interaction: discord.Interaction):
        """Show the current count and counting channel."""
        guild_id = interaction.guild.id
        
        # Check if counting is enabled
        if guild_id not in self.counting_channels:
            await self.load_counting_data(guild_id)
            if guild_id not in self.counting_channels:
                await interaction.response.send_message("❌ Counting is not enabled for this server. Use `/counting setchannel` first.", ephemeral=True)
                return
        
        channel_id = self.counting_channels[guild_id]
        current_count = self.current_counts[guild_id]
        channel = self.bot.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message("❌ The counting channel could not be found. It may have been deleted.", ephemeral=True)
            return
        
        await interaction.response.send_message(f"📊 **Counting Status**\n"
                                               f"Channel: {channel.mention}\n"
                                               f"Current count: {current_count}\n"
                                               f"Next number: {current_count + 1}", ephemeral=False)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Check if message is in counting channel and validate the number."""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Ignore DMs
        if not message.guild:
            return
        
        guild_id = message.guild.id
        
        # Check if this is a counting channel
        if guild_id not in self.counting_channels:
            # Try to load from database
            channel_exists = await self.load_counting_data(guild_id)
            if not channel_exists:
                return
        
        # Check if this message is in the counting channel
        if message.channel.id != self.counting_channels[guild_id]:
            return
        
        # Get current count
        current_count = self.current_counts[guild_id]
        expected_number = current_count + 1
        
        # Check if the message is just the next number
        # Strip whitespace and check if it's a number
        content = message.content.strip()
        
        # Use regex to check if the message contains only the number (allowing for whitespace)
        if not re.match(r'^\s*' + str(expected_number) + r'\s*$', content):
            # Not the expected number, delete the message
            try:
                await message.delete()
                # Optionally send a DM to the user explaining why their message was deleted
                try:
                    await message.author.send(f"Your message in the counting channel was deleted because it wasn't the next number in the sequence. The next number should be {expected_number}.")
                except discord.Forbidden:
                    # Can't send DM, ignore
                    pass
            except discord.Forbidden:
                # Bot doesn't have permission to delete messages
                log.warning(f"Cannot delete message in counting channel {message.channel.id} - missing permissions")
            except Exception as e:
                log.error(f"Error deleting message in counting channel: {e}")
            return
        
        # Check if the same user is posting twice in a row
        if guild_id in self.last_user and self.last_user[guild_id] == message.author.id:
            try:
                await message.delete()
                try:
                    await message.author.send(f"Your message in the counting channel was deleted because you cannot post two numbers in a row. Let someone else continue the count.")
                except discord.Forbidden:
                    pass
            except Exception as e:
                log.error(f"Error deleting message from same user: {e}")
            return
        
        # Valid number, update the count
        self.current_counts[guild_id] = expected_number
        self.last_user[guild_id] = message.author.id
        
        # Save to database
        await settings_manager.set_setting(guild_id, 'counting_current_number', str(expected_number))
        await settings_manager.set_setting(guild_id, 'counting_last_user', str(message.author.id))
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready."""
        log.info("CountingCog is ready")

async def setup(bot: commands.Bot):
    """Set up the CountingCog with the bot."""
    await bot.add_cog(CountingCog(bot))
    log.info("CountingCog has been added to the bot")
