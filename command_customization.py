"""
Command customization utilities for Discord bot.
Handles guild-specific command names and groups.
"""
import discord
from discord import app_commands
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable, Awaitable
import asyncio
from . import settings_manager

log = logging.getLogger(__name__)

class GuildCommandTransformer(app_commands.Transformer):
    """
    A transformer that customizes command names based on guild settings.
    This is used to transform command names when they are displayed to users.
    """
    async def transform(self, interaction: discord.Interaction, value: str) -> str:
        """Transform the command name based on guild settings."""
        if not interaction.guild:
            return value  # No customization in DMs
        
        guild_id = interaction.guild.id
        custom_name = await settings_manager.get_custom_command_name(guild_id, value)
        return custom_name if custom_name else value


class GuildCommandSyncer:
    """
    Handles syncing commands with guild-specific customizations.
    """
    def __init__(self, bot):
        self.bot = bot
        self._command_cache = {}  # Cache of original commands
        self._customized_commands = {}  # Guild ID -> {original_name: custom_command}
    
    async def load_guild_customizations(self, guild_id: int) -> Dict[str, str]:
        """
        Load command customizations for a specific guild.
        Returns a dictionary mapping original command names to custom names.
        """
        cmd_customizations = await settings_manager.get_all_command_customizations(guild_id)
        group_customizations = await settings_manager.get_all_group_customizations(guild_id)
        
        if cmd_customizations is None or group_customizations is None:
            log.error(f"Failed to load command customizations for guild {guild_id}")
            return {}
        
        # Combine command and group customizations
        customizations = {**cmd_customizations, **group_customizations}
        log.info(f"Loaded {len(customizations)} command customizations for guild {guild_id}")
        return customizations
    
    async def prepare_guild_commands(self, guild_id: int) -> List[app_commands.Command]:
        """
        Prepare guild-specific commands with customized names.
        Returns a list of commands with guild-specific customizations applied.
        """
        # Get all global commands
        global_commands = self.bot.tree.get_commands()
        
        # Cache original commands if not already cached
        if not self._command_cache:
            self._command_cache = {cmd.name: cmd for cmd in global_commands}
        
        # Load customizations for this guild
        customizations = await self.load_guild_customizations(guild_id)
        if not customizations:
            return global_commands  # No customizations, use global commands
        
        # Create guild-specific commands with custom names
        guild_commands = []
        for cmd in global_commands:
            if cmd.name in customizations:
                # Create a copy of the command with the custom name
                custom_name = customizations[cmd.name]
                custom_cmd = self._create_custom_command(cmd, custom_name)
                guild_commands.append(custom_cmd)
            else:
                # Use the original command
                guild_commands.append(cmd)
        
        # Store customized commands for this guild
        self._customized_commands[guild_id] = {
            cmd.name: custom_cmd for cmd, custom_cmd in zip(global_commands, guild_commands)
            if cmd.name in customizations
        }
        
        return guild_commands
    
    def _create_custom_command(self, original_cmd: app_commands.Command, custom_name: str) -> app_commands.Command:
        """
        Create a copy of a command with a custom name.
        This is a simplified version - in practice, you'd need to handle all command attributes.
        """
        # For simplicity, we're just creating a basic copy with the custom name
        # In a real implementation, you'd need to handle all command attributes and options
        custom_cmd = app_commands.Command(
            name=custom_name,
            description=original_cmd.description,
            callback=original_cmd.callback
        )
        
        # Copy options, if any
        if hasattr(original_cmd, 'options'):
            custom_cmd._params = original_cmd._params.copy()
        
        return custom_cmd
    
    async def sync_guild_commands(self, guild: discord.Guild) -> List[app_commands.Command]:
        """
        Sync commands for a specific guild with customizations.
        Returns the list of synced commands.
        """
        try:
            # Prepare guild-specific commands
            guild_commands = await self.prepare_guild_commands(guild.id)
            
            # Sync commands with Discord
            synced = await self.bot.tree.sync(guild=guild)
            
            log.info(f"Synced {len(synced)} commands for guild {guild.id}")
            return synced
        except Exception as e:
            log.error(f"Failed to sync commands for guild {guild.id}: {e}")
            raise


# Command registration decorator with guild customization support
def guild_command(name: str, description: str, **kwargs):
    """
    Decorator for registering commands with guild-specific name customization.
    Usage:
    
    @guild_command(name="mycommand", description="My command description")
    async def my_command(interaction: discord.Interaction):
        ...
    """
    def decorator(func: Callable[[discord.Interaction, ...], Awaitable[Any]]):
        # Create the app command
        @app_commands.command(name=name, description=description, **kwargs)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            return await func(interaction, *args, **kwargs)
        
        # Store the original name for reference
        wrapper.__original_name__ = name
        
        return wrapper
    
    return decorator


# Command group with guild customization support
class GuildCommandGroup(app_commands.Group):
    """
    A command group that supports guild-specific name customization.
    Usage:
    
    my_group = GuildCommandGroup(name="mygroup", description="My group description")
    
    @my_group.command(name="subcommand", description="Subcommand description")
    async def my_subcommand(interaction: discord.Interaction):
        ...
    """
    def __init__(self, name: str, description: str, **kwargs):
        super().__init__(name=name, description=description, **kwargs)
        self.__original_name__ = name
    
    async def get_guild_name(self, guild_id: int) -> str:
        """Get the guild-specific name for this group."""
        custom_name = await settings_manager.get_custom_group_name(guild_id, self.__original_name__)
        return custom_name if custom_name else self.__original_name__


# Utility functions for command registration
async def register_guild_commands(bot, guild: discord.Guild) -> List[app_commands.Command]:
    """
    Register commands for a specific guild with customizations.
    Returns the list of registered commands.
    """
    syncer = GuildCommandSyncer(bot)
    return await syncer.sync_guild_commands(guild)


async def register_all_guild_commands(bot) -> Dict[int, List[app_commands.Command]]:
    """
    Register commands for all guilds with customizations.
    Returns a dictionary mapping guild IDs to lists of registered commands.
    """
    syncer = GuildCommandSyncer(bot)
    results = {}
    
    for guild in bot.guilds:
        try:
            results[guild.id] = await syncer.sync_guild_commands(guild)
        except Exception as e:
            log.error(f"Failed to sync commands for guild {guild.id}: {e}")
            results[guild.id] = []
    
    return results
