import discord
from discord.ext import commands
import logging
import sys
import os

# Add the parent directory to sys.path to ensure settings_manager is accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import settings_manager

log = logging.getLogger(__name__)

class WelcomeCog(commands.Cog):
    """Handles welcome and goodbye messages for guilds."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("WelcomeCog: Initializing and registering event listeners")

        # Check existing event listeners
        print(f"WelcomeCog: Bot event listeners before registration: {self.bot.extra_events}")

        # Register event listeners
        self.bot.add_listener(self.on_member_join, "on_member_join")
        self.bot.add_listener(self.on_member_remove, "on_member_remove")

        # Check if event listeners were registered
        print(f"WelcomeCog: Bot event listeners after registration: {self.bot.extra_events}")
        print("WelcomeCog: Event listeners registered")

    async def on_member_join(self, member: discord.Member):
        """Sends a welcome message when a new member joins."""
        print(f"WelcomeCog: on_member_join event triggered for {member.name}")
        guild = member.guild
        if not guild:
            print(f"WelcomeCog: Guild not found for member {member.name}")
            return

        log.debug(f"Member {member.name} joined guild {guild.name} ({guild.id})")
        print(f"WelcomeCog: Member {member.name} joined guild {guild.name} ({guild.id})")

        # --- Fetch settings ---
        print(f"WelcomeCog: Fetching welcome settings for guild {guild.id}")
        welcome_channel_id_str = await settings_manager.get_setting(guild.id, 'welcome_channel_id')
        welcome_message_template = await settings_manager.get_setting(guild.id, 'welcome_message', default="Welcome {user} to {server}!")
        print(f"WelcomeCog: Retrieved settings - channel_id: {welcome_channel_id_str}, message: {welcome_message_template}")

        # Handle the "__NONE__" marker for potentially unset values
        if not welcome_channel_id_str or welcome_channel_id_str == "__NONE__":
            log.debug(f"Welcome channel not configured for guild {guild.id}")
            print(f"WelcomeCog: Welcome channel not configured for guild {guild.id}")
            return

        try:
            welcome_channel_id = int(welcome_channel_id_str)
            channel = guild.get_channel(welcome_channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                log.warning(f"Welcome channel ID {welcome_channel_id} not found or not text channel in guild {guild.id}")
                # Maybe remove the setting here if the channel is invalid?
                return

            # --- Format and send message ---
            # Basic formatting, can be expanded
            formatted_message = welcome_message_template.format(
                user=member.mention,
                username=member.name,
                server=guild.name
            )

            await channel.send(formatted_message)
            log.info(f"Sent welcome message for {member.name} in guild {guild.id}")

        except ValueError:
            log.error(f"Invalid welcome_channel_id '{welcome_channel_id_str}' configured for guild {guild.id}")
        except discord.Forbidden:
            log.error(f"Missing permissions to send welcome message in channel {welcome_channel_id} for guild {guild.id}")
        except Exception as e:
            log.exception(f"Error sending welcome message for guild {guild.id}: {e}")

    async def on_member_remove(self, member: discord.Member):
        """Sends a goodbye message when a member leaves."""
        print(f"WelcomeCog: on_member_remove event triggered for {member.name}")
        guild = member.guild
        if not guild:
            print(f"WelcomeCog: Guild not found for member {member.name}")
            return

        log.debug(f"Member {member.name} left guild {guild.name} ({guild.id})")
        print(f"WelcomeCog: Member {member.name} left guild {guild.name} ({guild.id})")

        # --- Fetch settings ---
        print(f"WelcomeCog: Fetching goodbye settings for guild {guild.id}")
        goodbye_channel_id_str = await settings_manager.get_setting(guild.id, 'goodbye_channel_id')
        goodbye_message_template = await settings_manager.get_setting(guild.id, 'goodbye_message', default="{username} has left the server.")
        print(f"WelcomeCog: Retrieved settings - channel_id: {goodbye_channel_id_str}, message: {goodbye_message_template}")

        # Handle the "__NONE__" marker
        if not goodbye_channel_id_str or goodbye_channel_id_str == "__NONE__":
            log.debug(f"Goodbye channel not configured for guild {guild.id}")
            print(f"WelcomeCog: Goodbye channel not configured for guild {guild.id}")
            return

        try:
            goodbye_channel_id = int(goodbye_channel_id_str)
            channel = guild.get_channel(goodbye_channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                log.warning(f"Goodbye channel ID {goodbye_channel_id} not found or not text channel in guild {guild.id}")
                return

            # --- Format and send message ---
            formatted_message = goodbye_message_template.format(
                user=member.mention, # Might not be mentionable after leaving
                username=member.name,
                server=guild.name
            )

            await channel.send(formatted_message)
            log.info(f"Sent goodbye message for {member.name} in guild {guild.id}")

        except ValueError:
            log.error(f"Invalid goodbye_channel_id '{goodbye_channel_id_str}' configured for guild {guild.id}")
        except discord.Forbidden:
            log.error(f"Missing permissions to send goodbye message in channel {goodbye_channel_id} for guild {guild.id}")
        except Exception as e:
            log.exception(f"Error sending goodbye message for guild {guild.id}: {e}")


    @commands.command(name='setwelcome', help="Sets the welcome message and channel. Usage: `setwelcome #channel [message template]`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_welcome(self, ctx: commands.Context, channel: discord.TextChannel, *, message_template: str = "Welcome {user} to {server}!"):
        """Sets the channel and template for welcome messages."""
        guild_id = ctx.guild.id
        key_channel = 'welcome_channel_id'
        key_message = 'welcome_message'

        # Use settings_manager.set_setting
        success_channel = await settings_manager.set_setting(guild_id, key_channel, str(channel.id))
        success_message = await settings_manager.set_setting(guild_id, key_message, message_template)

        if success_channel and success_message: # Both need to succeed
            await ctx.send(f"Welcome messages will now be sent to {channel.mention} with the template:\n```\n{message_template}\n```")
            log.info(f"Welcome settings updated for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("Failed to save welcome settings. Check logs.")
            log.error(f"Failed to save welcome settings for guild {guild_id}")

    @commands.command(name='disablewelcome', help="Disables welcome messages for this server.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def disable_welcome(self, ctx: commands.Context):
        """Disables welcome messages by removing the channel setting."""
        guild_id = ctx.guild.id
        key_channel = 'welcome_channel_id'
        key_message = 'welcome_message' # Also clear the message template

        # Use set_setting with None to delete the settings
        success_channel = await settings_manager.set_setting(guild_id, key_channel, None)
        success_message = await settings_manager.set_setting(guild_id, key_message, None)

        if success_channel and success_message: # Both need to succeed
            await ctx.send("Welcome messages have been disabled.")
            log.info(f"Welcome messages disabled for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("Failed to disable welcome messages. Check logs.")
            log.error(f"Failed to disable welcome settings for guild {guild_id}")


    @commands.command(name='setgoodbye', help="Sets the goodbye message and channel. Usage: `setgoodbye #channel [message template]`")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_goodbye(self, ctx: commands.Context, channel: discord.TextChannel, *, message_template: str = "{username} has left the server."):
        """Sets the channel and template for goodbye messages."""
        guild_id = ctx.guild.id
        key_channel = 'goodbye_channel_id'
        key_message = 'goodbye_message'

        # Use settings_manager.set_setting
        success_channel = await settings_manager.set_setting(guild_id, key_channel, str(channel.id))
        success_message = await settings_manager.set_setting(guild_id, key_message, message_template)

        if success_channel and success_message: # Both need to succeed
            await ctx.send(f"Goodbye messages will now be sent to {channel.mention} with the template:\n```\n{message_template}\n```")
            log.info(f"Goodbye settings updated for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("Failed to save goodbye settings. Check logs.")
            log.error(f"Failed to save goodbye settings for guild {guild_id}")

    @commands.command(name='disablegoodbye', help="Disables goodbye messages for this server.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def disable_goodbye(self, ctx: commands.Context):
        """Disables goodbye messages by removing the channel setting."""
        guild_id = ctx.guild.id
        key_channel = 'goodbye_channel_id'
        key_message = 'goodbye_message'

        # Use set_setting with None to delete the settings
        success_channel = await settings_manager.set_setting(guild_id, key_channel, None)
        success_message = await settings_manager.set_setting(guild_id, key_message, None)

        if success_channel and success_message: # Both need to succeed
            await ctx.send("Goodbye messages have been disabled.")
            log.info(f"Goodbye messages disabled for guild {guild_id} by {ctx.author.name}")
        else:
            await ctx.send("Failed to disable goodbye messages. Check logs.")
            log.error(f"Failed to disable goodbye settings for guild {guild_id}")

    # Error Handling for this Cog
    @set_welcome.error
    @disable_welcome.error
    @set_goodbye.error
    @disable_goodbye.error
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
            log.error(f"Unhandled error in WelcomeCog command '{ctx.command.name}': {error}")
            await ctx.send("An unexpected error occurred. Please check the logs.")


async def setup(bot: commands.Bot):
    # Ensure pools are initialized before adding the cog
    print("WelcomeCog setup function called!")
    if settings_manager.pg_pool is None or settings_manager.redis_pool is None:
        log.warning("Settings Manager pools not initialized before loading WelcomeCog. Attempting initialization.")
        print("WelcomeCog: Settings Manager pools not initialized, attempting initialization...")
        try:
            await settings_manager.initialize_pools()
            print("WelcomeCog: Settings Manager pools initialized successfully.")
        except Exception as e:
            log.exception("Failed to initialize Settings Manager pools during WelcomeCog setup. Cog will not load.")
            print(f"WelcomeCog: Failed to initialize Settings Manager pools: {e}")
            return # Prevent loading if pools fail

    welcome_cog = WelcomeCog(bot)
    await bot.add_cog(welcome_cog)
    print(f"WelcomeCog loaded! Event listeners registered: on_member_join, on_member_remove")
    log.info("WelcomeCog loaded.")
