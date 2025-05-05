import discord
from discord.ext import commands
from discord import app_commands
import datetime
import logging
from typing import Optional, Union, List

# Configure logging
logger = logging.getLogger(__name__)

class ModerationCog(commands.Cog):
    """Real moderation commands that perform actual moderation actions."""

    def __init__(self, bot):
        self.bot = bot

        # Create the main command group for this cog
        self.moderate_group = app_commands.Group(
            name="moderate",
            description="Moderation commands for server management"
        )

        # Register commands
        self.register_commands()

        # Add command group to the bot's tree
        self.bot.tree.add_command(self.moderate_group)

    def register_commands(self):
        """Register all commands for this cog"""

        # --- Ban Command ---
        ban_command = app_commands.Command(
            name="ban",
            description="Ban a member from the server",
            callback=self.moderate_ban_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            member="The member to ban",
            reason="The reason for the ban",
            delete_days="Number of days of messages to delete (0-7)"
        )(ban_command)
        self.moderate_group.add_command(ban_command)

        # --- Unban Command ---
        unban_command = app_commands.Command(
            name="unban",
            description="Unban a user from the server",
            callback=self.moderate_unban_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            user_id="The ID of the user to unban",
            reason="The reason for the unban"
        )(unban_command)
        self.moderate_group.add_command(unban_command)

        # --- Kick Command ---
        kick_command = app_commands.Command(
            name="kick",
            description="Kick a member from the server",
            callback=self.moderate_kick_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            member="The member to kick",
            reason="The reason for the kick"
        )(kick_command)
        self.moderate_group.add_command(kick_command)

        # --- Timeout Command ---
        timeout_command = app_commands.Command(
            name="timeout",
            description="Timeout a member in the server",
            callback=self.moderate_timeout_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            member="The member to timeout",
            duration="The duration of the timeout (e.g., '1d', '2h', '30m', '60s')",
            reason="The reason for the timeout"
        )(timeout_command)
        self.moderate_group.add_command(timeout_command)

        # --- Remove Timeout Command ---
        remove_timeout_command = app_commands.Command(
            name="removetimeout",
            description="Remove a timeout from a member",
            callback=self.moderate_remove_timeout_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            member="The member to remove timeout from",
            reason="The reason for removing the timeout"
        )(remove_timeout_command)
        self.moderate_group.add_command(remove_timeout_command)

        # --- Purge Command ---
        purge_command = app_commands.Command(
            name="purge",
            description="Delete a specified number of messages from a channel",
            callback=self.moderate_purge_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            amount="Number of messages to delete (1-100)",
            user="Optional: Only delete messages from this user"
        )(purge_command)
        self.moderate_group.add_command(purge_command)

        # --- Warn Command ---
        warn_command = app_commands.Command(
            name="warn",
            description="Warn a member in the server",
            callback=self.moderate_warn_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            member="The member to warn",
            reason="The reason for the warning"
        )(warn_command)
        self.moderate_group.add_command(warn_command)

        # --- DM Banned User Command ---
        dm_banned_command = app_commands.Command(
            name="dmbanned",
            description="Send a DM to a banned user",
            callback=self.moderate_dm_banned_callback,
            parent=self.moderate_group
        )
        app_commands.describe(
            user_id="The ID of the banned user to DM",
            message="The message to send to the banned user"
        )(dm_banned_command)
        self.moderate_group.add_command(dm_banned_command)

    # Helper method for parsing duration strings
    def _parse_duration(self, duration_str: str) -> Optional[datetime.timedelta]:
        """Parse a duration string like '1d', '2h', '30m' into a timedelta."""
        if not duration_str:
            return None

        try:
            # Extract the number and unit
            amount = int(''.join(filter(str.isdigit, duration_str)))
            unit = ''.join(filter(str.isalpha, duration_str)).lower()

            if unit == 'd' or unit == 'day' or unit == 'days':
                return datetime.timedelta(days=amount)
            elif unit == 'h' or unit == 'hour' or unit == 'hours':
                return datetime.timedelta(hours=amount)
            elif unit == 'm' or unit == 'min' or unit == 'minute' or unit == 'minutes':
                return datetime.timedelta(minutes=amount)
            elif unit == 's' or unit == 'sec' or unit == 'second' or unit == 'seconds':
                return datetime.timedelta(seconds=amount)
            else:
                return None
        except (ValueError, TypeError):
            return None

    # --- Command Callbacks ---

    async def moderate_ban_callback(self, interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_days: int = 0):
        """Ban a member from the server."""
        # Check if the user has permission to ban members
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ You don't have permission to ban members.", ephemeral=True)
            return

        # Check if the bot has permission to ban members
        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message("❌ I don't have permission to ban members.", ephemeral=True)
            return

        # Check if the user is trying to ban themselves
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot ban yourself.", ephemeral=True)
            return

        # Check if the user is trying to ban the bot
        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ I cannot ban myself.", ephemeral=True)
            return

        # Check if the user is trying to ban someone with a higher role
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot ban someone with a higher or equal role.", ephemeral=True)
            return

        # Check if the bot can ban the member (role hierarchy)
        if interaction.guild.me.top_role <= member.top_role:
            await interaction.response.send_message("❌ I cannot ban someone with a higher or equal role than me.", ephemeral=True)
            return

        # Ensure delete_days is within valid range (0-7)
        delete_days = max(0, min(7, delete_days))

        # Try to send a DM to the user before banning them
        dm_sent = False
        try:
            embed = discord.Embed(
                title="Ban Notice",
                description=f"You have been banned from **{interaction.guild.name}**",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Moderator", value=interaction.user.name, inline=False)
            embed.set_footer(text=f"Server ID: {interaction.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await member.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            # User has DMs closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending ban DM to {member} (ID: {member.id}): {e}")

        # Perform the ban
        try:
            await member.ban(reason=reason, delete_message_days=delete_days)

            # Log the action
            logger.info(f"User {member} (ID: {member.id}) was banned from {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}). Reason: {reason}")

            # Send confirmation message with DM status
            dm_status = "✅ DM notification sent" if dm_sent else "❌ Could not send DM notification (user may have DMs disabled)"
            await interaction.response.send_message(f"🔨 **Banned {member.mention}**! Reason: {reason or 'No reason provided'}\n{dm_status}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while banning the member: {e}", ephemeral=True)

    async def moderate_unban_callback(self, interaction: discord.Interaction, user_id: str, reason: str = None):
        """Unban a user from the server."""
        # Check if the user has permission to ban members (which includes unbanning)
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ You don't have permission to unban users.", ephemeral=True)
            return

        # Check if the bot has permission to ban members (which includes unbanning)
        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message("❌ I don't have permission to unban users.", ephemeral=True)
            return

        # Validate user ID
        try:
            user_id_int = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID. Please provide a valid user ID.", ephemeral=True)
            return

        # Check if the user is banned
        try:
            ban_entry = await interaction.guild.fetch_ban(discord.Object(id=user_id_int))
            banned_user = ban_entry.user
        except discord.NotFound:
            await interaction.response.send_message("❌ This user is not banned.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to view the ban list.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while checking the ban list: {e}", ephemeral=True)
            return

        # Perform the unban
        try:
            await interaction.guild.unban(banned_user, reason=reason)

            # Log the action
            logger.info(f"User {banned_user} (ID: {banned_user.id}) was unbanned from {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}). Reason: {reason}")

            # Send confirmation message
            await interaction.response.send_message(f"🔓 **Unbanned {banned_user}**! Reason: {reason or 'No reason provided'}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to unban this user.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while unbanning the user: {e}", ephemeral=True)

    async def moderate_kick_callback(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Kick a member from the server."""
        # Check if the user has permission to kick members
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ You don't have permission to kick members.", ephemeral=True)
            return

        # Check if the bot has permission to kick members
        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message("❌ I don't have permission to kick members.", ephemeral=True)
            return

        # Check if the user is trying to kick themselves
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot kick yourself.", ephemeral=True)
            return

        # Check if the user is trying to kick the bot
        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ I cannot kick myself.", ephemeral=True)
            return

        # Check if the user is trying to kick someone with a higher role
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot kick someone with a higher or equal role.", ephemeral=True)
            return

        # Check if the bot can kick the member (role hierarchy)
        if interaction.guild.me.top_role <= member.top_role:
            await interaction.response.send_message("❌ I cannot kick someone with a higher or equal role than me.", ephemeral=True)
            return

        # Try to send a DM to the user before kicking them
        dm_sent = False
        try:
            embed = discord.Embed(
                title="Kick Notice",
                description=f"You have been kicked from **{interaction.guild.name}**",
                color=discord.Color.orange()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Moderator", value=interaction.user.name, inline=False)
            embed.set_footer(text=f"Server ID: {interaction.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await member.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            # User has DMs closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending kick DM to {member} (ID: {member.id}): {e}")

        # Perform the kick
        try:
            await member.kick(reason=reason)

            # Log the action
            logger.info(f"User {member} (ID: {member.id}) was kicked from {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}). Reason: {reason}")

            # Send confirmation message with DM status
            dm_status = "✅ DM notification sent" if dm_sent else "❌ Could not send DM notification (user may have DMs disabled)"
            await interaction.response.send_message(f"👢 **Kicked {member.mention}**! Reason: {reason or 'No reason provided'}\n{dm_status}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while kicking the member: {e}", ephemeral=True)

    async def moderate_timeout_callback(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
        """Timeout a member in the server."""
        # Check if the user has permission to moderate members
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ You don't have permission to timeout members.", ephemeral=True)
            return

        # Check if the bot has permission to moderate members
        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ I don't have permission to timeout members.", ephemeral=True)
            return

        # Check if the user is trying to timeout themselves
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot timeout yourself.", ephemeral=True)
            return

        # Check if the user is trying to timeout the bot
        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ I cannot timeout myself.", ephemeral=True)
            return

        # Check if the user is trying to timeout someone with a higher role
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot timeout someone with a higher or equal role.", ephemeral=True)
            return

        # Check if the bot can timeout the member (role hierarchy)
        if interaction.guild.me.top_role <= member.top_role:
            await interaction.response.send_message("❌ I cannot timeout someone with a higher or equal role than me.", ephemeral=True)
            return

        # Parse the duration
        delta = self._parse_duration(duration)
        if not delta:
            await interaction.response.send_message("❌ Invalid duration format. Please use formats like '1d', '2h', '30m', or '60s'.", ephemeral=True)
            return

        # Check if the duration is within Discord's limits (max 28 days)
        max_timeout = datetime.timedelta(days=28)
        if delta > max_timeout:
            await interaction.response.send_message("❌ Timeout duration cannot exceed 28 days.", ephemeral=True)
            return

        # Calculate the end time
        until = discord.utils.utcnow() + delta

        # Try to send a DM to the user before timing them out
        dm_sent = False
        try:
            embed = discord.Embed(
                title="Timeout Notice",
                description=f"You have been timed out in **{interaction.guild.name}** for {duration}",
                color=discord.Color.gold()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Moderator", value=interaction.user.name, inline=False)
            embed.add_field(name="Duration", value=duration, inline=False)
            embed.add_field(name="Expires", value=f"<t:{int(until.timestamp())}:F>", inline=False)
            embed.set_footer(text=f"Server ID: {interaction.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await member.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            # User has DMs closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending timeout DM to {member} (ID: {member.id}): {e}")

        # Perform the timeout
        try:
            await member.timeout(until, reason=reason)

            # Log the action
            logger.info(f"User {member} (ID: {member.id}) was timed out in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}) for {duration}. Reason: {reason}")

            # Send confirmation message with DM status
            dm_status = "✅ DM notification sent" if dm_sent else "❌ Could not send DM notification (user may have DMs disabled)"
            await interaction.response.send_message(f"⏰ **Timed out {member.mention}** for {duration}! Reason: {reason or 'No reason provided'}\n{dm_status}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to timeout this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while timing out the member: {e}", ephemeral=True)

    async def moderate_remove_timeout_callback(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Remove a timeout from a member."""
        # Check if the user has permission to moderate members
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ You don't have permission to remove timeouts.", ephemeral=True)
            return

        # Check if the bot has permission to moderate members
        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ I don't have permission to remove timeouts.", ephemeral=True)
            return

        # Check if the member is timed out
        if not member.timed_out_until:
            await interaction.response.send_message("❌ This member is not timed out.", ephemeral=True)
            return

        # Try to send a DM to the user about the timeout removal
        dm_sent = False
        try:
            embed = discord.Embed(
                title="Timeout Removed",
                description=f"Your timeout in **{interaction.guild.name}** has been removed",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Moderator", value=interaction.user.name, inline=False)
            embed.set_footer(text=f"Server ID: {interaction.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await member.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            # User has DMs closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending timeout removal DM to {member} (ID: {member.id}): {e}")

        # Perform the timeout removal
        try:
            await member.timeout(None, reason=reason)

            # Log the action
            logger.info(f"Timeout was removed from user {member} (ID: {member.id}) in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}). Reason: {reason}")

            # Send confirmation message with DM status
            dm_status = "✅ DM notification sent" if dm_sent else "❌ Could not send DM notification (user may have DMs disabled)"
            await interaction.response.send_message(f"⏰ **Removed timeout from {member.mention}**! Reason: {reason or 'No reason provided'}\n{dm_status}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to remove the timeout from this member.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while removing the timeout: {e}", ephemeral=True)

    async def moderate_purge_callback(self, interaction: discord.Interaction, amount: int, user: Optional[discord.Member] = None):
        """Delete a specified number of messages from a channel."""
        # Check if the user has permission to manage messages
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to purge messages.", ephemeral=True)
            return

        # Check if the bot has permission to manage messages
        if not interaction.guild.me.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ I don't have permission to purge messages.", ephemeral=True)
            return

        # Validate the amount
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ You can only purge between 1 and 100 messages at a time.", ephemeral=True)
            return

        # Defer the response since this might take a moment
        await interaction.response.defer(ephemeral=True)

        # Perform the purge
        try:
            if user:
                # Delete messages from a specific user
                def check(message):
                    return message.author.id == user.id

                deleted = await interaction.channel.purge(limit=amount, check=check)

                # Log the action
                logger.info(f"{len(deleted)} messages from user {user} (ID: {user.id}) were purged from channel {interaction.channel.name} (ID: {interaction.channel.id}) in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}).")

                # Send confirmation message
                await interaction.followup.send(f"🧹 **Purged {len(deleted)} messages** from {user.mention}!", ephemeral=True)
            else:
                # Delete messages from anyone
                deleted = await interaction.channel.purge(limit=amount)

                # Log the action
                logger.info(f"{len(deleted)} messages were purged from channel {interaction.channel.name} (ID: {interaction.channel.id}) in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}).")

                # Send confirmation message
                await interaction.followup.send(f"🧹 **Purged {len(deleted)} messages**!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages in this channel.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ An error occurred while purging messages: {e}", ephemeral=True)

    async def moderate_warn_callback(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        """Warn a member in the server."""
        # Check if the user has permission to kick members (using kick permission as a baseline for warning)
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ You don't have permission to warn members.", ephemeral=True)
            return

        # Check if the user is trying to warn themselves
        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot warn yourself.", ephemeral=True)
            return

        # Check if the user is trying to warn the bot
        if member.id == self.bot.user.id:
            await interaction.response.send_message("❌ I cannot warn myself.", ephemeral=True)
            return

        # Check if the user is trying to warn someone with a higher role
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot warn someone with a higher or equal role.", ephemeral=True)
            return

        # Log the warning
        logger.info(f"User {member} (ID: {member.id}) was warned in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}). Reason: {reason}")

        # Send warning message in the channel
        await interaction.response.send_message(f"⚠️ **{member.mention} has been warned**! Reason: {reason}")

        # Try to DM the user about the warning
        try:
            embed = discord.Embed(
                title="Warning Notice",
                description=f"You have been warned in **{interaction.guild.name}**",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=interaction.user.name, inline=False)
            embed.set_footer(text=f"Server ID: {interaction.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await member.send(embed=embed)
        except discord.Forbidden:
            # User has DMs closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending warning DM to {member} (ID: {member.id}): {e}")

    async def moderate_dm_banned_callback(self, interaction: discord.Interaction, user_id: str, message: str):
        """Send a DM to a banned user."""
        # Check if the user has permission to ban members
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ You don't have permission to DM banned users.", ephemeral=True)
            return

        # Validate user ID
        try:
            user_id_int = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID. Please provide a valid user ID.", ephemeral=True)
            return

        # Check if the user is banned
        try:
            ban_entry = await interaction.guild.fetch_ban(discord.Object(id=user_id_int))
            banned_user = ban_entry.user
        except discord.NotFound:
            await interaction.response.send_message("❌ This user is not banned.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to view the ban list.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while checking the ban list: {e}", ephemeral=True)
            return

        # Try to send a DM to the banned user
        try:
            # Create an embed with the message
            embed = discord.Embed(
                title=f"Message from {interaction.guild.name}",
                description=message,
                color=discord.Color.red()
            )
            embed.add_field(name="Sent by", value=interaction.user.name, inline=False)
            embed.set_footer(text=f"Server ID: {interaction.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            # Send the DM
            await banned_user.send(embed=embed)

            # Log the action
            logger.info(f"DM sent to banned user {banned_user} (ID: {banned_user.id}) in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.user} (ID: {interaction.user.id}).")

            # Send confirmation message
            await interaction.response.send_message(f"✅ **DM sent to banned user {banned_user}**!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I couldn't send a DM to this user. They may have DMs disabled or have blocked the bot.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ An error occurred while sending the DM: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error sending DM to banned user {banned_user} (ID: {banned_user.id}): {e}")
            await interaction.response.send_message(f"❌ An unexpected error occurred: {e}", ephemeral=True)

    # --- Legacy Command Handlers (for prefix commands) ---

    @commands.command(name="timeout")
    async def timeout(self, ctx: commands.Context, member: discord.Member = None, duration: str = None, *, reason: str = None):
        """Timeout a member in the server. Can be used by replying to a message."""
        # Check if this is a reply to a message and no member was specified
        if not member and ctx.message.reference:
            # Get the message being replied to
            replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            member = replied_msg.author

            # Don't allow timing out the bot itself
            if member.id == self.bot.user.id:
                await ctx.reply("❌ I cannot timeout myself.")
                return
        elif not member:
            await ctx.reply("❌ Please specify a member to timeout or reply to their message.")
            return

        # If duration wasn't specified but we're in a reply, check if it's the first argument
        if not duration and ctx.message.reference and len(ctx.message.content.split()) > 1:
            # Try to extract duration from the first argument
            potential_duration = ctx.message.content.split()[1]
            # Simple check if it looks like a duration (contains numbers and letters)
            if any(c.isdigit() for c in potential_duration) and any(c.isalpha() for c in potential_duration):
                duration = potential_duration
                # If there's more content, it's the reason
                if len(ctx.message.content.split()) > 2:
                    reason = ' '.join(ctx.message.content.split()[2:])

        # Check if duration is specified
        if not duration:
            await ctx.reply("❌ Please specify a duration for the timeout (e.g., '1d', '2h', '30m', '60s').")
            return

        # Check if the user has permission to moderate members
        if not ctx.author.guild_permissions.moderate_members:
            await ctx.reply("❌ You don't have permission to timeout members.")
            return

        # Check if the bot has permission to moderate members
        if not ctx.guild.me.guild_permissions.moderate_members:
            await ctx.reply("❌ I don't have permission to timeout members.")
            return

        # Check if the user is trying to timeout themselves
        if member.id == ctx.author.id:
            await ctx.reply("❌ You cannot timeout yourself.")
            return

        # Check if the user is trying to timeout someone with a higher role
        if ctx.author.top_role <= member.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.reply("❌ You cannot timeout someone with a higher or equal role.")
            return

        # Check if the bot can timeout the member (role hierarchy)
        if ctx.guild.me.top_role <= member.top_role:
            await ctx.reply("❌ I cannot timeout someone with a higher or equal role than me.")
            return

        # Parse the duration
        delta = self._parse_duration(duration)
        if not delta:
            await ctx.reply("❌ Invalid duration format. Please use formats like '1d', '2h', '30m', or '60s'.")
            return

        # Check if the duration is within Discord's limits (max 28 days)
        max_timeout = datetime.timedelta(days=28)
        if delta > max_timeout:
            await ctx.reply("❌ Timeout duration cannot exceed 28 days.")
            return

        # Calculate the end time
        until = discord.utils.utcnow() + delta

        # Try to send a DM to the user before timing them out
        dm_sent = False
        try:
            embed = discord.Embed(
                title="Timeout Notice",
                description=f"You have been timed out in **{ctx.guild.name}** for {duration}",
                color=discord.Color.gold()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Moderator", value=ctx.author.name, inline=False)
            embed.add_field(name="Duration", value=duration, inline=False)
            embed.add_field(name="Expires", value=f"<t:{int(until.timestamp())}:F>", inline=False)
            embed.set_footer(text=f"Server ID: {ctx.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await member.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            # User has DMs closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending timeout DM to {member} (ID: {member.id}): {e}")

        # Perform the timeout
        try:
            await member.timeout(until, reason=reason)

            # Log the action
            logger.info(f"User {member} (ID: {member.id}) was timed out in {ctx.guild.name} (ID: {ctx.guild.id}) by {ctx.author} (ID: {ctx.author.id}) for {duration}. Reason: {reason}")

            # Send confirmation message with DM status
            dm_status = "✅ DM notification sent" if dm_sent else "❌ Could not send DM notification (user may have DMs disabled)"
            await ctx.reply(f"⏰ **Timed out {member.mention}** for {duration}! Reason: {reason or 'No reason provided'}\n{dm_status}")
        except discord.Forbidden:
            await ctx.reply("❌ I don't have permission to timeout this member.")
        except discord.HTTPException as e:
            await ctx.reply(f"❌ An error occurred while timing out the member: {e}")

    @commands.command(name="removetimeout")
    async def removetimeout(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        """Remove a timeout from a member. Can be used by replying to a message."""
        # Check if this is a reply to a message and no member was specified
        if not member and ctx.message.reference:
            # Get the message being replied to
            replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            member = replied_msg.author

            # Don't allow removing timeout from the bot itself
            if member.id == self.bot.user.id:
                await ctx.reply("❌ I cannot remove a timeout from myself.")
                return
        elif not member:
            await ctx.reply("❌ Please specify a member to remove timeout from or reply to their message.")
            return

        # Check if the user has permission to moderate members
        if not ctx.author.guild_permissions.moderate_members:
            await ctx.reply("❌ You don't have permission to remove timeouts.")
            return

        # Check if the bot has permission to moderate members
        if not ctx.guild.me.guild_permissions.moderate_members:
            await ctx.reply("❌ I don't have permission to remove timeouts.")
            return

        # Check if the member is timed out
        if not member.timed_out_until:
            await ctx.reply("❌ This member is not timed out.")
            return

        # Try to send a DM to the user about the timeout removal
        dm_sent = False
        try:
            embed = discord.Embed(
                title="Timeout Removed",
                description=f"Your timeout in **{ctx.guild.name}** has been removed",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Moderator", value=ctx.author.name, inline=False)
            embed.set_footer(text=f"Server ID: {ctx.guild.id} • {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await member.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            # User has DMs closed, ignore
            pass
        except Exception as e:
            logger.error(f"Error sending timeout removal DM to {member} (ID: {member.id}): {e}")

        # Perform the timeout removal
        try:
            await member.timeout(None, reason=reason)

            # Log the action
            logger.info(f"Timeout was removed from user {member} (ID: {member.id}) in {ctx.guild.name} (ID: {ctx.guild.id}) by {ctx.author} (ID: {ctx.author.id}). Reason: {reason}")

            # Send confirmation message with DM status
            dm_status = "✅ DM notification sent" if dm_sent else "❌ Could not send DM notification (user may have DMs disabled)"
            await ctx.reply(f"⏰ **Removed timeout from {member.mention}**! Reason: {reason or 'No reason provided'}\n{dm_status}")
        except discord.Forbidden:
            await ctx.reply("❌ I don't have permission to remove the timeout from this member.")
        except discord.HTTPException as e:
            await ctx.reply(f"❌ An error occurred while removing the timeout: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
