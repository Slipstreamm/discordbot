import discord
from discord.ext import commands
from discord import app_commands, Interaction, Embed, Color, User, Member, Object
import asyncpg
import logging
from typing import Optional, Union, Dict, Any
import datetime

# Use absolute imports from the discordbot package root
from discordbot.db import mod_log_db
from discordbot import settings_manager as sm # Use module functions directly

log = logging.getLogger(__name__)

class ModLogCog(commands.Cog):
    """Cog for handling integrated moderation logging and related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Settings manager functions are used directly from the imported module
        self.pool: asyncpg.Pool = bot.pool # Assuming pool is attached to bot

        # Create the main command group for this cog
        self.modlog_group = app_commands.Group(
            name="modlog",
            description="Commands for viewing and managing moderation logs"
        )

        # Register commands within the group
        self.register_commands()

        # Add command group to the bot's tree
        self.bot.tree.add_command(self.modlog_group)

    def register_commands(self):
        """Register all commands for this cog"""

        # --- View Command ---
        view_command = app_commands.Command(
            name="view",
            description="View moderation logs for a user or the server",
            callback=self.modlog_view_callback,
            parent=self.modlog_group
        )
        app_commands.describe(
            user="Optional: The user whose logs you want to view"
        )(view_command)
        self.modlog_group.add_command(view_command)

        # --- Case Command ---
        case_command = app_commands.Command(
            name="case",
            description="View details for a specific moderation case ID",
            callback=self.modlog_case_callback,
            parent=self.modlog_group
        )
        app_commands.describe(
            case_id="The ID of the moderation case to view"
        )(case_command)
        self.modlog_group.add_command(case_command)

        # --- Reason Command ---
        reason_command = app_commands.Command(
            name="reason",
            description="Update the reason for a specific moderation case ID",
            callback=self.modlog_reason_callback,
            parent=self.modlog_group
        )
        app_commands.describe(
            case_id="The ID of the moderation case to update",
            new_reason="The new reason for the moderation action"
        )(reason_command)
        self.modlog_group.add_command(reason_command)

    # --- Core Logging Function ---

    async def log_action(
        self,
        guild: discord.Guild,
        moderator: Union[User, Member], # For bot actions
        target: Union[User, Member, Object], # Can be user, member, or just an ID object
        action_type: str,
        reason: Optional[str],
        duration: Optional[datetime.timedelta] = None,
        source: str = "BOT", # Default source is the bot itself
        ai_details: Optional[Dict[str, Any]] = None, # Details from AI API
        moderator_id_override: Optional[int] = None # Allow overriding moderator ID for AI source
    ):
        """Logs a moderation action to the database and configured channel."""
        if not guild:
            log.warning("Attempted to log action without guild context.")
            return

        guild_id = guild.id
        # Use override if provided (for AI source), otherwise use moderator object ID
        moderator_id = moderator_id_override if moderator_id_override is not None else moderator.id
        target_user_id = target.id
        duration_seconds = int(duration.total_seconds()) if duration else None

        # 1. Add initial log entry to DB
        case_id = await mod_log_db.add_mod_log(
            self.pool, guild_id, moderator_id, target_user_id,
            action_type, reason, duration_seconds
        )

        if not case_id:
            log.error(f"Failed to get case_id when logging action {action_type} in guild {guild_id}")
            return # Don't proceed if we couldn't save the initial log

        # 2. Check settings and send log message
        try:
            # Use functions from settings_manager module
            log_enabled = await sm.is_mod_log_enabled(guild_id, default=False)
            log_channel_id = await sm.get_mod_log_channel_id(guild_id)

            if not log_enabled or not log_channel_id:
                log.debug(f"Mod logging disabled or channel not set for guild {guild_id}. Skipping Discord log message.")
                return

            log_channel = guild.get_channel(log_channel_id)
            if not log_channel or not isinstance(log_channel, discord.TextChannel):
                log.warning(f"Mod log channel {log_channel_id} not found or not a text channel in guild {guild_id}.")
                # Optionally update DB to remove channel ID? Or just leave it.
                return

            # 3. Format and send embed
            embed = self._format_log_embed(
                case_id=case_id,
                moderator=moderator, # Pass the object for display formatting
                target=target,
                action_type=action_type,
                reason=reason,
                duration=duration,
                guild=guild,
                source=source,
                ai_details=ai_details,
                moderator_id_override=moderator_id_override # Pass override for formatting
            )
            log_message = await log_channel.send(embed=embed)

            # 4. Update DB with message details
            await mod_log_db.update_mod_log_message_details(self.pool, case_id, log_message.id, log_channel.id)

        except Exception as e:
            log.exception(f"Error during Discord mod log message sending/updating for case {case_id} in guild {guild_id}: {e}")

    def _format_log_embed(
        self,
        case_id: int,
        moderator: Union[User, Member],
        target: Union[User, Member, Object],
        action_type: str,
        reason: Optional[str],
        duration: Optional[datetime.timedelta],
        guild: discord.Guild,
        source: str = "BOT",
        ai_details: Optional[Dict[str, Any]] = None,
        moderator_id_override: Optional[int] = None
    ) -> Embed:
        """Helper function to create the standard log embed."""
        color_map = {
            "BAN": Color.red(),
            "UNBAN": Color.green(),
            "KICK": Color.orange(),
            "TIMEOUT": Color.gold(),
            "REMOVE_TIMEOUT": Color.blue(),
            "WARN": Color.yellow(),
            "AI_ALERT": Color.purple(),
            "AI_DELETE_REQUESTED": Color.dark_grey(),
        }
        embed_color = color_map.get(action_type.upper(), Color.greyple())
        action_title_prefix = "AI Moderation Action" if source == "AI_API" else action_type.replace("_", " ").title()
        action_title = f"{action_title_prefix} | Case #{case_id}"

        embed = Embed(
            title=action_title,
            color=embed_color,
            timestamp=discord.utils.utcnow()
        )

        target_display = f"{getattr(target, 'mention', target.id)} ({target.id})"

        # Determine moderator display based on source
        if source == "AI_API":
            moderator_display = f"AI System (ID: {moderator_id_override or 'Unknown'})"
        else:
            moderator_display = f"{moderator.mention} ({moderator.id})"


        embed.add_field(name="User", value=target_display, inline=True)
        embed.add_field(name="Moderator", value=moderator_display, inline=True)

        # Add AI-specific details if available
        if ai_details:
            if 'rule_violated' in ai_details:
                embed.add_field(name="Rule Violated", value=ai_details['rule_violated'], inline=True)
            if 'reasoning' in ai_details:
                 # Use AI reasoning as the main reason field if bot reason is empty
                 reason_to_display = reason or ai_details['reasoning']
                 embed.add_field(name="Reason / AI Reasoning", value=reason_to_display or "No reason provided.", inline=False)
                 # Optionally add bot reason separately if both exist and differ
                 if reason and reason != ai_details['reasoning']:
                     embed.add_field(name="Original Bot Reason", value=reason, inline=False)
            else:
                 embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        else:
            embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)

        if duration:
            # Format duration nicely (e.g., "1 day", "2 hours 30 minutes")
            # This is a simple version, could be made more robust
            total_seconds = int(duration.total_seconds())
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = ""
            if days > 0: duration_str += f"{days}d "
            if hours > 0: duration_str += f"{hours}h "
            if minutes > 0: duration_str += f"{minutes}m "
            if seconds > 0 or not duration_str: duration_str += f"{seconds}s"
            duration_str = duration_str.strip()

            embed.add_field(name="Duration", value=duration_str, inline=True)
            # Add expiration timestamp if applicable (e.g., for timeouts)
            if action_type.upper() == "TIMEOUT":
                 expires_at = discord.utils.utcnow() + duration
                 embed.add_field(name="Expires", value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)


        embed.set_footer(text=f"Guild: {guild.name} ({guild.id})")

        return embed

    # --- Command Callbacks ---

    @app_commands.checks.has_permissions(moderate_members=True) # Adjust permissions as needed
    async def modlog_view_callback(self, interaction: Interaction, user: Optional[discord.User] = None):
        """Callback for the /modlog view command."""
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id

        if not guild_id:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        records = []
        if user:
            records = await mod_log_db.get_user_mod_logs(self.pool, guild_id, user.id)
            title = f"Moderation Logs for {user.name} ({user.id})"
        else:
            records = await mod_log_db.get_guild_mod_logs(self.pool, guild_id)
            title = f"Recent Moderation Logs for {interaction.guild.name}"

        if not records:
            await interaction.followup.send("No moderation logs found matching your criteria.", ephemeral=True)
            return

        # Format the logs into an embed or text response
        # For simplicity, sending as text for now. Can enhance with pagination/embeds later.
        response_lines = [f"**{title}**"]
        for record in records:
            timestamp_str = record['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            reason_str = record['reason'] or "N/A"
            duration_str = f" ({record['duration_seconds']}s)" if record['duration_seconds'] else ""
            response_lines.append(
                f"`Case #{record['case_id']}` [{timestamp_str}] **{record['action_type']}** "
                f"Target: <@{record['target_user_id']}> Mod: <@{record['moderator_id']}> "
                f"Reason: {reason_str}{duration_str}"
            )

        # Handle potential message length limits
        full_response = "\n".join(response_lines)
        if len(full_response) > 2000:
            full_response = full_response[:1990] + "\n... (truncated)"

        await interaction.followup.send(full_response, ephemeral=True)


    @app_commands.checks.has_permissions(moderate_members=True) # Adjust permissions as needed
    async def modlog_case_callback(self, interaction: Interaction, case_id: int):
        """Callback for the /modlog case command."""
        await interaction.response.defer(ephemeral=True)
        record = await mod_log_db.get_mod_log(self.pool, case_id)

        if not record:
            await interaction.followup.send(f"❌ Case ID #{case_id} not found.", ephemeral=True)
            return

        # Ensure the case belongs to the current guild for security/privacy
        if record['guild_id'] != interaction.guild_id:
             await interaction.followup.send(f"❌ Case ID #{case_id} does not belong to this server.", ephemeral=True)
             return

        # Fetch user objects if possible to show names
        moderator = await self.bot.fetch_user(record['moderator_id'])
        target = await self.bot.fetch_user(record['target_user_id'])
        duration = datetime.timedelta(seconds=record['duration_seconds']) if record['duration_seconds'] else None

        embed = self._format_log_embed(
            case_id,
            moderator or Object(id=record['moderator_id']), # Fallback to Object if user not found
            target or Object(id=record['target_user_id']), # Fallback to Object if user not found
            record['action_type'],
            record['reason'],
            duration,
            interaction.guild
        )

        # Add log message link if available
        if record['log_message_id'] and record['log_channel_id']:
            link = f"https://discord.com/channels/{record['guild_id']}/{record['log_channel_id']}/{record['log_message_id']}"
            embed.add_field(name="Log Message", value=f"[Jump to Log]({link})", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


    @app_commands.checks.has_permissions(manage_guild=True) # Higher permission for editing reasons
    async def modlog_reason_callback(self, interaction: Interaction, case_id: int, new_reason: str):
        """Callback for the /modlog reason command."""
        await interaction.response.defer(ephemeral=True)

        # 1. Get the original record to verify guild and existence
        original_record = await mod_log_db.get_mod_log(self.pool, case_id)
        if not original_record:
            await interaction.followup.send(f"❌ Case ID #{case_id} not found.", ephemeral=True)
            return
        if original_record['guild_id'] != interaction.guild_id:
             await interaction.followup.send(f"❌ Case ID #{case_id} does not belong to this server.", ephemeral=True)
             return

        # 2. Update the reason in the database
        success = await mod_log_db.update_mod_log_reason(self.pool, case_id, new_reason)

        if not success:
            await interaction.followup.send(f"❌ Failed to update reason for Case ID #{case_id}. Please check logs.", ephemeral=True)
            return

        await interaction.followup.send(f"✅ Updated reason for Case ID #{case_id}.", ephemeral=True)

        # 3. (Optional but recommended) Update the original log message embed
        if original_record['log_message_id'] and original_record['log_channel_id']:
            try:
                log_channel = interaction.guild.get_channel(original_record['log_channel_id'])
                if log_channel and isinstance(log_channel, discord.TextChannel):
                    log_message = await log_channel.fetch_message(original_record['log_message_id'])
                    if log_message and log_message.author == self.bot.user and log_message.embeds:
                        # Re-fetch users/duration to reconstruct embed accurately
                        moderator = await self.bot.fetch_user(original_record['moderator_id'])
                        target = await self.bot.fetch_user(original_record['target_user_id'])
                        duration = datetime.timedelta(seconds=original_record['duration_seconds']) if original_record['duration_seconds'] else None

                        new_embed = self._format_log_embed(
                            case_id,
                            moderator or Object(id=original_record['moderator_id']),
                            target or Object(id=original_record['target_user_id']),
                            original_record['action_type'],
                            new_reason, # Use the new reason here
                            duration,
                            interaction.guild
                        )
                        # Add log message link again
                        link = f"https://discord.com/channels/{original_record['guild_id']}/{original_record['log_channel_id']}/{original_record['log_message_id']}"
                        new_embed.add_field(name="Log Message", value=f"[Jump to Log]({link})", inline=False)
                        new_embed.add_field(name="Updated Reason By", value=f"{interaction.user.mention}", inline=False) # Indicate update

                        await log_message.edit(embed=new_embed)
                        log.info(f"Successfully updated log message embed for case {case_id}")
            except discord.NotFound:
                log.warning(f"Original log message or channel not found for case {case_id} when updating reason.")
            except discord.Forbidden:
                log.warning(f"Missing permissions to edit original log message for case {case_id}.")
            except Exception as e:
                log.exception(f"Error updating original log message embed for case {case_id}: {e}")


    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure the pool and settings_manager are available
        if not hasattr(self.bot, 'pool') or not self.bot.pool:
            log.error("Database pool not found on bot object. ModLogCog requires bot.pool.")
            # Consider preventing the cog from loading fully or raising an error
        # Settings manager is imported directly, no need to check on bot object

        print(f'{self.__class__.__name__} cog has been loaded.')


async def setup(bot: commands.Bot):
    # Ensure dependencies (pool) are ready before adding cog
    # Settings manager is imported directly within the cog
    if hasattr(bot, 'pool'):
        await bot.add_cog(ModLogCog(bot))
    else:
        log.error("Failed to load ModLogCog: bot.pool not initialized.")
