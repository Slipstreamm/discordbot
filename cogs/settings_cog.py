import discord
from discord.ext import commands
import logging
import settings_manager # Assuming settings_manager is accessible
import command_customization # Import command customization utilities
from typing import Optional

log = logging.getLogger(__name__)

# Get CORE_COGS from bot instance
def get_core_cogs(bot):
    return getattr(bot, 'core_cogs', {'SettingsCog', 'HelpCog'})

class SettingsCog(commands.Cog, name="Settings"):
    """Commands for server administrators to configure the bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Prefix Management ---
    @commands.command(name='setprefix', help="Sets the command prefix for this server. Usage: `setprefix <new_prefix>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_prefix(self, ctx: commands.Context, new_prefix: str):
        """Sets the command prefix for the current guild."""
        if not new_prefix:
            await ctx.send("Prefix cannot be empty.")
            return
        if len(new_prefix) > 10: # Arbitrary limit
             await ctx.send("Prefix cannot be longer than 10 characters.")
             return
        if new_prefix.isspace():
             await ctx.send("Prefix cannot be just whitespace.")
             return

        guild_id = ctx.guild.id
        success = await settings_manager.set_guild_prefix(guild_id, new_prefix)

        if success:
            await ctx.send(f"Command prefix for this server has been set to: `{new_prefix}`")
            log.info(f"Prefix updated for guild {guild_id} to '{new_prefix}' by {ctx.author.name}")
        else:
            await ctx.send("Failed to set the prefix. Please check the logs.")
            log.error(f"Failed to save prefix for guild {guild_id}")

    @commands.command(name='showprefix', help="Shows the current command prefix for this server.")
    @commands.guild_only()
    async def show_prefix(self, ctx: commands.Context):
        """Shows the current command prefix."""
        # We need the bot's default prefix as a fallback
        # This might need access to the bot instance's initial config or a constant
        default_prefix = self.bot.command_prefix # This might not work if command_prefix is the callable
        # Use the constant defined in main.py if possible, or keep a local fallback
        default_prefix_fallback = "!" # TODO: Get default prefix reliably if needed elsewhere

        guild_id = ctx.guild.id
        current_prefix = await settings_manager.get_guild_prefix(guild_id, default_prefix_fallback)
        await ctx.send(f"The current command prefix for this server is: `{current_prefix}`")


    # --- Cog Management ---
    @commands.command(name='enablecog', help="Enables a specific module (cog) for this server. Usage: `enablecog <CogName>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def enable_cog(self, ctx: commands.Context, cog_name: str):
        """Enables a cog for the current guild."""
        # Validate if cog exists
        if cog_name not in self.bot.cogs:
            await ctx.send(f"Error: Cog `{cog_name}` not found.")
            return

        core_cogs = get_core_cogs(self.bot)
        if cog_name in core_cogs:
             await ctx.send(f"Error: Core cog `{cog_name}` cannot be disabled/enabled.")
             return

        guild_id = ctx.guild.id
        success = await settings_manager.set_cog_enabled(guild_id, cog_name, enabled=True)

        if success:
            await ctx.send(f"Module `{cog_name}` has been enabled for this server.")
            log.info(f"Cog '{cog_name}' enabled for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to enable module `{cog_name}`. Check logs.")
            log.error(f"Failed to enable cog '{cog_name}' for guild {guild_id}")

    @commands.command(name='disablecog', help="Disables a specific module (cog) for this server. Usage: `disablecog <CogName>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def disable_cog(self, ctx: commands.Context, cog_name: str):
        """Disables a cog for the current guild."""
        if cog_name not in self.bot.cogs:
            await ctx.send(f"Error: Cog `{cog_name}` not found.")
            return

        core_cogs = get_core_cogs(self.bot)
        if cog_name in core_cogs:
             await ctx.send(f"Error: Core cog `{cog_name}` cannot be disabled.")
             return

        guild_id = ctx.guild.id
        success = await settings_manager.set_cog_enabled(guild_id, cog_name, enabled=False)

        if success:
            await ctx.send(f"Module `{cog_name}` has been disabled for this server.")
            log.info(f"Cog '{cog_name}' disabled for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to disable module `{cog_name}`. Check logs.")
            log.error(f"Failed to disable cog '{cog_name}' for guild {guild_id}")

    @commands.command(name='listcogs', help="Lists all available modules (cogs) and their status for this server.")
    @commands.guild_only()
    async def list_cogs(self, ctx: commands.Context):
        """Lists available cogs and their enabled/disabled status."""
        guild_id = ctx.guild.id
        # Note: Default enabled status might need adjustment based on desired behavior
        # If a cog has no entry in the DB, should it be considered enabled or disabled by default?
        # Let's assume default_enabled=True for now.
        default_behavior = True

        embed = discord.Embed(title="Available Modules (Cogs)", color=discord.Color.blue())
        lines = []
        # Get core cogs from bot instance
        core_cogs_list = get_core_cogs(self.bot)

        for cog_name in sorted(self.bot.cogs.keys()):
            is_enabled = await settings_manager.is_cog_enabled(guild_id, cog_name, default_enabled=default_behavior)
            status = "✅ Enabled" if is_enabled else "❌ Disabled"
            if cog_name in core_cogs_list:
                status += " (Core)"
            lines.append(f"`{cog_name}`: {status}")

        embed.description = "\n".join(lines) if lines else "No cogs found."
        await ctx.send(embed=embed)


    # --- Command Permission Management (Basic Role-Based) ---
    @commands.command(name='allowcmd', help="Allows a role to use a specific command. Usage: `allowcmd <command_name> <@Role>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def allow_command(self, ctx: commands.Context, command_name: str, role: discord.Role):
        """Allows a specific role to use a command."""
        command = self.bot.get_command(command_name)
        if not command:
            await ctx.send(f"Error: Command `{command_name}` not found.")
            return

        guild_id = ctx.guild.id
        role_id = role.id
        success = await settings_manager.add_command_permission(guild_id, command_name, role_id)

        if success:
            await ctx.send(f"Role `{role.name}` is now allowed to use command `{command_name}`.")
            log.info(f"Permission added for command '{command_name}', role '{role.name}' ({role_id}) in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to add permission for command `{command_name}`. Check logs.")
            log.error(f"Failed to add permission for command '{command_name}', role {role_id} in guild {guild_id}")


    @commands.command(name='disallowcmd', help="Disallows a role from using a specific command. Usage: `disallowcmd <command_name> <@Role>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def disallow_command(self, ctx: commands.Context, command_name: str, role: discord.Role):
        """Disallows a specific role from using a command."""
        command = self.bot.get_command(command_name)
        if not command:
            await ctx.send(f"Error: Command `{command_name}` not found.")
            return

        guild_id = ctx.guild.id
        role_id = role.id
        success = await settings_manager.remove_command_permission(guild_id, command_name, role_id)

        if success:
            await ctx.send(f"Role `{role.name}` is no longer allowed to use command `{command_name}`.")
            log.info(f"Permission removed for command '{command_name}', role '{role.name}' ({role_id}) in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to remove permission for command `{command_name}`. Check logs.")
            log.error(f"Failed to remove permission for command '{command_name}', role {role_id} in guild {guild_id}")

    # --- Command Customization Management ---
    @commands.command(name='setcmdname', help="Sets a custom name for a slash command in this server. Usage: `setcmdname <original_name> <custom_name>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_command_name(self, ctx: commands.Context, original_name: str, custom_name: str):
        """Sets a custom name for a slash command in the current guild."""
        # Validate the original command exists
        command_found = False
        for cmd in self.bot.tree.get_commands():
            if cmd.name == original_name:
                command_found = True
                break

        if not command_found:
            await ctx.send(f"Error: Slash command `{original_name}` not found.")
            return

        # Validate custom name format (Discord has restrictions on command names)
        if not custom_name.islower() or not custom_name.replace('_', '').isalnum():
            await ctx.send("Error: Custom command names must be lowercase and contain only letters, numbers, and underscores.")
            return

        if len(custom_name) < 1 or len(custom_name) > 32:
            await ctx.send("Error: Custom command names must be between 1 and 32 characters long.")
            return

        guild_id = ctx.guild.id
        success = await settings_manager.set_custom_command_name(guild_id, original_name, custom_name)

        if success:
            await ctx.send(f"Command `{original_name}` will now appear as `{custom_name}` in this server.\n"
                          f"Note: You'll need to restart the bot or use `/sync` for changes to take effect.")
            log.info(f"Custom command name set for '{original_name}' to '{custom_name}' in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to set custom command name. Check logs.")
            log.error(f"Failed to set custom command name for '{original_name}' in guild {guild_id}")

    @commands.command(name='resetcmdname', help="Resets a slash command to its original name. Usage: `resetcmdname <original_name>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def reset_command_name(self, ctx: commands.Context, original_name: str):
        """Resets a slash command to its original name in the current guild."""
        guild_id = ctx.guild.id
        success = await settings_manager.set_custom_command_name(guild_id, original_name, None)

        if success:
            await ctx.send(f"Command `{original_name}` has been reset to its original name in this server.\n"
                          f"Note: You'll need to restart the bot or use `/sync` for changes to take effect.")
            log.info(f"Custom command name reset for '{original_name}' in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to reset command name. Check logs.")
            log.error(f"Failed to reset command name for '{original_name}' in guild {guild_id}")

    @commands.command(name='setgroupname', help="Sets a custom name for a command group. Usage: `setgroupname <original_name> <custom_name>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_group_name(self, ctx: commands.Context, original_name: str, custom_name: str):
        """Sets a custom name for a command group in the current guild."""
        # Validate the original group exists
        group_found = False
        for cmd in self.bot.tree.get_commands():
            if hasattr(cmd, 'parent') and cmd.parent and cmd.parent.name == original_name:
                group_found = True
                break

        if not group_found:
            await ctx.send(f"Error: Command group `{original_name}` not found.")
            return

        # Validate custom name format (Discord has restrictions on command names)
        if not custom_name.islower() or not custom_name.replace('_', '').isalnum():
            await ctx.send("Error: Custom group names must be lowercase and contain only letters, numbers, and underscores.")
            return

        if len(custom_name) < 1 or len(custom_name) > 32:
            await ctx.send("Error: Custom group names must be between 1 and 32 characters long.")
            return

        guild_id = ctx.guild.id
        success = await settings_manager.set_custom_group_name(guild_id, original_name, custom_name)

        if success:
            await ctx.send(f"Command group `{original_name}` will now appear as `{custom_name}` in this server.\n"
                          f"Note: You'll need to restart the bot or use `/sync` for changes to take effect.")
            log.info(f"Custom group name set for '{original_name}' to '{custom_name}' in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to set custom group name. Check logs.")
            log.error(f"Failed to set custom group name for '{original_name}' in guild {guild_id}")

    @commands.command(name='resetgroupname', help="Resets a command group to its original name. Usage: `resetgroupname <original_name>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def reset_group_name(self, ctx: commands.Context, original_name: str):
        """Resets a command group to its original name in the current guild."""
        guild_id = ctx.guild.id
        success = await settings_manager.set_custom_group_name(guild_id, original_name, None)

        if success:
            await ctx.send(f"Command group `{original_name}` has been reset to its original name in this server.\n"
                          f"Note: You'll need to restart the bot or use `/sync` for changes to take effect.")
            log.info(f"Custom group name reset for '{original_name}' in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to reset group name. Check logs.")
            log.error(f"Failed to reset group name for '{original_name}' in guild {guild_id}")

    @commands.command(name='addcmdalias', help="Adds an alias for a command. Usage: `addcmdalias <original_name> <alias_name>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def add_command_alias(self, ctx: commands.Context, original_name: str, alias_name: str):
        """Adds an alias for a command in the current guild."""
        # Validate the original command exists
        command = self.bot.get_command(original_name)
        if not command:
            await ctx.send(f"Error: Command `{original_name}` not found.")
            return

        # Validate alias format
        if not alias_name.islower() or not alias_name.replace('_', '').isalnum():
            await ctx.send("Error: Aliases must be lowercase and contain only letters, numbers, and underscores.")
            return

        if len(alias_name) < 1 or len(alias_name) > 32:
            await ctx.send("Error: Aliases must be between 1 and 32 characters long.")
            return

        guild_id = ctx.guild.id
        success = await settings_manager.add_command_alias(guild_id, original_name, alias_name)

        if success:
            await ctx.send(f"Added alias `{alias_name}` for command `{original_name}` in this server.")
            log.info(f"Command alias added for '{original_name}': '{alias_name}' in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to add command alias. Check logs.")
            log.error(f"Failed to add command alias for '{original_name}' in guild {guild_id}")

    @commands.command(name='removecmdalias', help="Removes an alias for a command. Usage: `removecmdalias <original_name> <alias_name>`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def remove_command_alias(self, ctx: commands.Context, original_name: str, alias_name: str):
        """Removes an alias for a command in the current guild."""
        guild_id = ctx.guild.id
        success = await settings_manager.remove_command_alias(guild_id, original_name, alias_name)

        if success:
            await ctx.send(f"Removed alias `{alias_name}` for command `{original_name}` in this server.")
            log.info(f"Command alias removed for '{original_name}': '{alias_name}' in guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send(f"Failed to remove command alias. Check logs.")
            log.error(f"Failed to remove command alias for '{original_name}' in guild {guild_id}")

    @commands.command(name='listcmdaliases', help="Lists all command aliases for this server.")
    @commands.guild_only()
    async def list_command_aliases(self, ctx: commands.Context):
        """Lists all command aliases for the current guild."""
        guild_id = ctx.guild.id
        aliases_dict = await settings_manager.get_all_command_aliases(guild_id)

        if aliases_dict is None:
            await ctx.send("Failed to retrieve command aliases. Check logs.")
            return

        if not aliases_dict:
            await ctx.send("No command aliases are set for this server.")
            return

        embed = discord.Embed(title="Command Aliases", color=discord.Color.blue())
        for cmd_name, aliases in aliases_dict.items():
            embed.add_field(name=f"Command: {cmd_name}", value=", ".join([f"`{alias}`" for alias in aliases]), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='listcustomcmds', help="Lists all custom command names for this server.")
    @commands.guild_only()
    async def list_custom_commands(self, ctx: commands.Context):
        """Lists all custom command names for the current guild."""
        guild_id = ctx.guild.id
        cmd_customizations = await settings_manager.get_all_command_customizations(guild_id)
        group_customizations = await settings_manager.get_all_group_customizations(guild_id)

        if cmd_customizations is None or group_customizations is None:
            await ctx.send("Failed to retrieve command customizations. Check logs.")
            return

        if not cmd_customizations and not group_customizations:
            await ctx.send("No command customizations are set for this server.")
            return

        embed = discord.Embed(title="Command Customizations", color=discord.Color.blue())

        if cmd_customizations:
            cmd_text = "\n".join([f"`{orig}` → `{custom}`" for orig, custom in cmd_customizations.items()])
            embed.add_field(name="Custom Command Names", value=cmd_text, inline=False)

        if group_customizations:
            group_text = "\n".join([f"`{orig}` → `{custom}`" for orig, custom in group_customizations.items()])
            embed.add_field(name="Custom Group Names", value=group_text, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='synccmds', help="Syncs slash commands with Discord to apply customizations.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def sync_commands(self, ctx: commands.Context):
        """Syncs slash commands with Discord to apply customizations."""
        try:
            guild = ctx.guild
            await ctx.send("Syncing commands with Discord... This may take a moment.")

            # Use the command_customization module to sync commands with customizations
            try:
                synced = await command_customization.register_guild_commands(self.bot, guild)

                await ctx.send(f"Successfully synced {len(synced)} commands for this server with customizations.")
                log.info(f"Commands synced with customizations for guild {guild.id} by {ctx.author.name}")
            except Exception as e:
                log.error(f"Failed to sync commands with customizations: {e}")
                # Don't fall back to regular sync to avoid command duplication
                await ctx.send(f"Failed to apply customizations. Please check the logs and try again.")
                log.info(f"Command sync with customizations failed for guild {guild.id}")
        except Exception as e:
            await ctx.send(f"Failed to sync commands: {str(e)}")
            log.error(f"Failed to sync commands for guild {ctx.guild.id}: {e}")

    # TODO: Add command to list permissions?


    # --- Moderation Logging Settings ---
    @commands.group(name='modlogconfig', help="Configure the integrated moderation logging.", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def modlog_config_group(self, ctx: commands.Context):
        """Base command for moderation log configuration. Shows current settings."""
        guild_id = ctx.guild.id
        enabled = await settings_manager.is_mod_log_enabled(guild_id)
        channel_id = await settings_manager.get_mod_log_channel_id(guild_id)
        channel = ctx.guild.get_channel(channel_id) if channel_id else None

        status = "✅ Enabled" if enabled else "❌ Disabled"
        channel_status = channel.mention if channel else ("Not Set" if channel_id else "Not Set")

        embed = discord.Embed(title="Moderation Logging Configuration", color=discord.Color.teal())
        embed.add_field(name="Status", value=status, inline=False)
        embed.add_field(name="Log Channel", value=channel_status, inline=False)
        await ctx.send(embed=embed)

    @modlog_config_group.command(name='enable', help="Enables the integrated moderation logging.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def modlog_enable(self, ctx: commands.Context):
        """Enables the integrated moderation logging for this server."""
        guild_id = ctx.guild.id
        success = await settings_manager.set_mod_log_enabled(guild_id, True)
        if success:
            await ctx.send("✅ Integrated moderation logging has been enabled.")
            log.info(f"Moderation logging enabled for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("❌ Failed to enable moderation logging. Please check logs.")
            log.error(f"Failed to enable moderation logging for guild {guild_id}")

    @modlog_config_group.command(name='disable', help="Disables the integrated moderation logging.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def modlog_disable(self, ctx: commands.Context):
        """Disables the integrated moderation logging for this server."""
        guild_id = ctx.guild.id
        success = await settings_manager.set_mod_log_enabled(guild_id, False)
        if success:
            await ctx.send("❌ Integrated moderation logging has been disabled.")
            log.info(f"Moderation logging disabled for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("❌ Failed to disable moderation logging. Please check logs.")
            log.error(f"Failed to disable moderation logging for guild {guild_id}")

    @modlog_config_group.command(name='setchannel', help="Sets the channel where moderation logs will be sent. Usage: `setchannel #channel`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def modlog_setchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Sets the channel for integrated moderation logs."""
        guild_id = ctx.guild.id
        # Basic check for bot permissions in the target channel
        if not channel.permissions_for(ctx.guild.me).send_messages or not channel.permissions_for(ctx.guild.me).embed_links:
             await ctx.send(f"❌ I need 'Send Messages' and 'Embed Links' permissions in {channel.mention} to send logs there.")
             return

        success = await settings_manager.set_mod_log_channel_id(guild_id, channel.id)
        if success:
            await ctx.send(f"✅ Moderation logs will now be sent to {channel.mention}.")
            log.info(f"Moderation log channel set to {channel.id} for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("❌ Failed to set the moderation log channel. Please check logs.")
            log.error(f"Failed to set moderation log channel for guild {guild_id}")

    @modlog_config_group.command(name='unsetchannel', help="Unsets the moderation log channel (disables sending logs).")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def modlog_unsetchannel(self, ctx: commands.Context):
        """Unsets the channel for integrated moderation logs."""
        guild_id = ctx.guild.id
        success = await settings_manager.set_mod_log_channel_id(guild_id, None)
        if success:
            await ctx.send("✅ Moderation log channel has been unset. Logs will not be sent to a channel.")
            log.info(f"Moderation log channel unset for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("❌ Failed to unset the moderation log channel. Please check logs.")
            log.error(f"Failed to unset moderation log channel for guild {guild_id}")


    # --- Error Handling for this Cog ---
    @set_prefix.error
    @enable_cog.error
    @disable_cog.error
    @allow_command.error
    @disallow_command.error
    @set_command_name.error
    @reset_command_name.error
    @set_group_name.error
    @reset_group_name.error
    @add_command_alias.error
    @remove_command_alias.error
    @sync_commands.error
    @modlog_config_group.error # Add error handler for the group
    @modlog_enable.error
    @modlog_disable.error
    @modlog_setchannel.error
    @modlog_unsetchannel.error
    async def on_command_error(self, ctx: commands.Context, error):
        # Check if the error originates from the modlogconfig group or its subcommands
        if ctx.command and (ctx.command.name == 'modlogconfig' or (ctx.command.parent and ctx.command.parent.name == 'modlogconfig')):
            if isinstance(error, commands.MissingPermissions):
                await ctx.send("You need Administrator permissions to configure moderation logging.")
                return # Handled
            elif isinstance(error, commands.BadArgument):
                 await ctx.send(f"Invalid argument. Usage: `{ctx.prefix}help {ctx.command.qualified_name}`")
                 return # Handled
            elif isinstance(error, commands.MissingRequiredArgument):
                 await ctx.send(f"Missing argument. Usage: `{ctx.prefix}help {ctx.command.qualified_name}`")
                 return # Handled
            elif isinstance(error, commands.NoPrivateMessage):
                 await ctx.send("This command can only be used in a server.")
                 return # Handled
            # Let other errors fall through to the generic handler below

        # Generic handlers for other commands in this cog
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need Administrator permissions to use this command.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid argument provided. Check the command help: `{ctx.prefix}help {ctx.command.name}`")
        elif isinstance(error, commands.MissingRequiredArgument):
             await ctx.send(f"Missing required argument. Check the command help: `{ctx.prefix}help {ctx.command.name}`")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in private messages.")
        else:
            log.error(f"Unhandled error in SettingsCog command '{ctx.command.name}': {error}")
            await ctx.send("An unexpected error occurred. Please check the logs.")


async def setup(bot: commands.Bot):
    # Ensure pools are initialized before adding the cog
    if getattr(bot, "pg_pool", None) is None or getattr(bot, "redis", None) is None:
        log.warning("Bot pools not initialized before loading SettingsCog. Cog will not load.")
        return # Prevent loading if pools are missing

    await bot.add_cog(SettingsCog(bot))
    log.info("SettingsCog loaded.")
