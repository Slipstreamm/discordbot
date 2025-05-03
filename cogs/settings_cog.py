import discord
from discord.ext import commands
import logging
from discordbot import settings_manager # Assuming settings_manager is accessible

log = logging.getLogger(__name__)

# CORE_COGS definition moved to main.py

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

        if cog_name in CORE_COGS:
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

        if cog_name in CORE_COGS:
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
        # Use the CORE_COGS defined at the top of this file
        core_cogs_list = CORE_COGS

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

    # TODO: Add command to list permissions?

    # --- Error Handling for this Cog ---
    @set_prefix.error
    @enable_cog.error
    @disable_cog.error
    @allow_command.error
    @disallow_command.error
    async def on_command_error(self, ctx: commands.Context, error):
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
    if settings_manager.pg_pool is None or settings_manager.redis_pool is None:
        log.warning("Settings Manager pools not initialized before loading SettingsCog. Attempting initialization.")
        try:
            await settings_manager.initialize_pools()
        except Exception as e:
            log.exception("Failed to initialize Settings Manager pools during SettingsCog setup. Cog will not load.")
            return # Prevent loading if pools fail

    await bot.add_cog(SettingsCog(bot))
    log.info("SettingsCog loaded.")
