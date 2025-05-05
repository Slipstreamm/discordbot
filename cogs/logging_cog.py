import discord
from discord.ext import commands, tasks
import datetime
import asyncio
import aiohttp # Added for webhook sending
import logging # Use logging instead of print
from typing import Optional, Union

# Import settings manager
try:
    from .. import settings_manager # Relative import if cogs are in a subfolder
except ImportError:
    import settings_manager # Fallback for direct execution? Adjust as needed.


log = logging.getLogger(__name__) # Setup logger for this cog

class LoggingCog(commands.Cog):
    """Handles comprehensive server event logging via webhooks."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None # Session for webhooks
        self.last_audit_log_ids: dict[int, Optional[int]] = {} # Store last ID per guild
        # Start the audit log poller task if the bot is ready, otherwise wait
        if bot.is_ready():
            asyncio.create_task(self.initialize_cog()) # Use async init helper
        else:
            asyncio.create_task(self.start_audit_log_poller_when_ready()) # Keep this for initial start

    async def initialize_cog(self):
        """Asynchronous initialization tasks."""
        log.info("Initializing LoggingCog...")
        self.session = aiohttp.ClientSession()
        log.info("aiohttp ClientSession created for LoggingCog.")
        await self.initialize_audit_log_ids()
        if not self.poll_audit_log.is_running():
            self.poll_audit_log.start()
            log.info("Audit log poller started during initialization.")

    async def initialize_audit_log_ids(self):
        """Fetch the latest audit log ID for each guild the bot is in."""
        log.info("Initializing last audit log IDs for guilds...")
        for guild in self.bot.guilds:
            if guild.id not in self.last_audit_log_ids: # Only initialize if not already set
                try:
                    if guild.me.guild_permissions.view_audit_log:
                        async for entry in guild.audit_logs(limit=1):
                            self.last_audit_log_ids[guild.id] = entry.id
                            log.debug(f"Initialized last_audit_log_id for guild {guild.id} to {entry.id}")
                            break # Only need the latest one
                    else:
                        log.warning(f"Missing 'View Audit Log' permission in guild {guild.id}. Cannot initialize audit log ID.")
                        self.last_audit_log_ids[guild.id] = None # Mark as unable to fetch
                except discord.Forbidden:
                     log.warning(f"Forbidden error fetching initial audit log ID for guild {guild.id}.")
                     self.last_audit_log_ids[guild.id] = None
                except discord.HTTPException as e:
                     log.error(f"HTTP error fetching initial audit log ID for guild {guild.id}: {e}")
                     self.last_audit_log_ids[guild.id] = None
                except Exception as e:
                    log.exception(f"Unexpected error fetching initial audit log ID for guild {guild.id}: {e}")
                    self.last_audit_log_ids[guild.id] = None # Mark as unable on other errors
        log.info("Finished initializing audit log IDs.")


    async def start_audit_log_poller_when_ready(self):
        """Waits until bot is ready, then initializes and starts the poller."""
        await self.bot.wait_until_ready()
        await self.initialize_cog() # Call the main init helper

    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.poll_audit_log.cancel()
        log.info("Audit log poller stopped.")
        if self.session and not self.session.closed:
            await self.session.close()
            log.info("aiohttp ClientSession closed for LoggingCog.")

    async def _send_log_embed(self, guild: discord.Guild, embed: discord.Embed):
        """Sends the log embed via the configured webhook for the guild."""
        if not self.session or self.session.closed:
            log.error(f"aiohttp session not available or closed in LoggingCog for guild {guild.id}. Cannot send log.")
            return

        webhook_url = await settings_manager.get_logging_webhook(guild.id)

        if not webhook_url:
            # log.debug(f"Logging webhook not configured for guild {guild.id}. Skipping log.") # Can be noisy
            return

        try:
            webhook = discord.Webhook.from_url(webhook_url, session=self.session)
            await webhook.send(
                embed=embed,
                username=f"{self.bot.user.name} Logs", # Optional: Customize webhook appearance
                avatar_url=self.bot.user.display_avatar.url # Optional: Use bot's avatar
            )
            # log.debug(f"Sent log embed via webhook for guild {guild.id}") # Can be noisy
        except ValueError:
            log.error(f"Invalid logging webhook URL configured for guild {guild.id}.")
            # Consider notifying an admin or disabling logging for this guild temporarily
            # await settings_manager.set_logging_webhook(guild.id, None) # Example: Auto-disable on invalid URL
        except (discord.Forbidden, discord.NotFound):
            log.error(f"Webhook permissions error or webhook not found for guild {guild.id}. URL: {webhook_url}")
            # Consider notifying an admin or disabling logging for this guild temporarily
            # await settings_manager.set_logging_webhook(guild.id, None) # Example: Auto-disable on error
        except discord.HTTPException as e:
            log.error(f"HTTP error sending log via webhook for guild {guild.id}: {e}")
        except aiohttp.ClientError as e:
             log.error(f"aiohttp client error sending log via webhook for guild {guild.id}: {e}")
        except Exception as e:
            log.exception(f"Unexpected error sending log via webhook for guild {guild.id}: {e}")


    def _create_log_embed(self, title: str, description: str = "", color: discord.Color = discord.Color.blue(), author: Optional[Union[discord.User, discord.Member]] = None, footer: Optional[str] = None) -> discord.Embed:
        """Creates a standardized log embed."""
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if author:
            embed.set_author(name=str(author), icon_url=author.display_avatar.url)
        if footer:
            embed.set_footer(text=footer)
        else:
            embed.set_footer(text=f"Bot ID: {self.bot.user.id}")
        return embed

    # --- Setup Command ---
    @commands.command(name="setup_logging")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def setup_logging(self, ctx: commands.Context, channel: discord.TextChannel):
        """Sets up the logging webhook for the server. (Admin Only)

        Usage: !setup_logging #your-log-channel
        """
        guild = ctx.guild
        me = guild.me

        # 1. Check bot permissions
        if not channel.permissions_for(me).manage_webhooks:
            await ctx.send(f"❌ I don't have the 'Manage Webhooks' permission in {channel.mention}. Please grant it and try again.")
            return
        if not channel.permissions_for(me).send_messages:
             await ctx.send(f"❌ I don't have the 'Send Messages' permission in {channel.mention}. Please grant it and try again (needed for webhook creation confirmation).")
             return

        # 2. Check existing webhook setting
        existing_url = await settings_manager.get_logging_webhook(guild.id)
        if existing_url:
             # Try to fetch the existing webhook to see if it's still valid and in the right channel
             try:
                 if not self.session or self.session.closed: self.session = aiohttp.ClientSession() # Ensure session exists
                 existing_webhook = await discord.Webhook.from_url(existing_url, session=self.session).fetch()
                 if existing_webhook.channel_id == channel.id:
                     await ctx.send(f"✅ Logging is already configured for {channel.mention} using webhook `{existing_webhook.name}`.")
                     return
                 else:
                     await ctx.send(f"⚠️ Logging webhook is currently set for a different channel (<#{existing_webhook.channel_id}>). I will create a new one for {channel.mention}.")
             except (discord.NotFound, discord.Forbidden, ValueError, aiohttp.ClientError):
                 await ctx.send(f"⚠️ Could not verify the existing webhook URL. It might be invalid or deleted. I will create a new one for {channel.mention}.")
             except Exception as e:
                 log.exception(f"Error fetching existing webhook during setup for guild {guild.id}")
                 await ctx.send(f"⚠️ An error occurred while checking the existing webhook. Proceeding to create a new one for {channel.mention}.")


        # 3. Create new webhook
        try:
            webhook_name = f"{self.bot.user.name} Logger"
            # Use bot's avatar if possible
            avatar_bytes = None
            try:
                avatar_bytes = await self.bot.user.display_avatar.read()
            except Exception:
                 log.warning(f"Could not read bot avatar for webhook creation in guild {guild.id}.")

            new_webhook = await channel.create_webhook(name=webhook_name, avatar=avatar_bytes, reason=f"Logging setup by {ctx.author} ({ctx.author.id})")
            log.info(f"Created logging webhook '{webhook_name}' in channel {channel.id} for guild {guild.id}")
        except discord.HTTPException as e:
            log.error(f"Failed to create webhook in {channel.mention} for guild {guild.id}: {e}")
            await ctx.send(f"❌ Failed to create webhook. Error: {e}. This could be due to hitting the channel webhook limit (15).")
            return
        except Exception as e:
            log.exception(f"Unexpected error creating webhook in {channel.mention} for guild {guild.id}")
            await ctx.send("❌ An unexpected error occurred while creating the webhook.")
            return

        # 4. Save webhook URL
        success = await settings_manager.set_logging_webhook(guild.id, new_webhook.url)
        if success:
            await ctx.send(f"✅ Successfully configured logging to send messages to {channel.mention} via the new webhook `{new_webhook.name}`.")
            # Test send (optional)
            try:
                 test_embed = self._create_log_embed("✅ Logging Setup Complete", f"Logs will now be sent to this channel via the webhook `{new_webhook.name}`.", color=discord.Color.green())
                 await new_webhook.send(embed=test_embed, username=webhook_name, avatar_url=self.bot.user.display_avatar.url)
            except Exception as e:
                 log.error(f"Failed to send test message via new webhook for guild {guild.id}: {e}")
                 await ctx.send("⚠️ Could not send a test message via the new webhook, but the URL has been saved.")
        else:
            log.error(f"Failed to save webhook URL {new_webhook.url} to database for guild {guild.id}")
            await ctx.send("❌ Successfully created the webhook, but failed to save its URL to my settings. Please try again or contact support.")
            # Attempt to delete the created webhook to avoid orphans
            try:
                await new_webhook.delete(reason="Failed to save URL to settings")
                log.info(f"Deleted orphaned webhook '{new_webhook.name}' for guild {guild.id}")
            except Exception as del_e:
                log.error(f"Failed to delete orphaned webhook '{new_webhook.name}' for guild {guild.id}: {del_e}")


    # --- Event Listeners ---

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize when the cog is ready (called after bot on_ready)."""
        log.info(f'{self.__class__.__name__} cog is ready.')
        # Initialization is now handled by initialize_cog called from __init__ or start_audit_log_poller_when_ready
        # Ensure the poller is running if it wasn't started earlier
        if self.bot.is_ready() and not self.poll_audit_log.is_running():
             log.warning("Poll audit log task was not running after on_ready, attempting to start.")
             await self.initialize_cog() # Re-initialize just in case

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Initialize audit log ID when joining a new guild."""
        log.info(f"Joined guild {guild.id}. Initializing audit log ID.")
        if guild.id not in self.last_audit_log_ids:
            try:
                if guild.me.guild_permissions.view_audit_log:
                    async for entry in guild.audit_logs(limit=1):
                        self.last_audit_log_ids[guild.id] = entry.id
                        log.debug(f"Initialized last_audit_log_id for new guild {guild.id} to {entry.id}")
                        break
                else:
                     log.warning(f"Missing 'View Audit Log' permission in new guild {guild.id}.")
                     self.last_audit_log_ids[guild.id] = None
            except Exception as e:
                log.exception(f"Error fetching initial audit log ID for new guild {guild.id}: {e}")
                self.last_audit_log_ids[guild.id] = None

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Remove guild data when leaving."""
        log.info(f"Left guild {guild.id}. Removing audit log ID.")
        self.last_audit_log_ids.pop(guild.id, None)
        # Note: Webhook URL is stored in DB and should ideally be cleaned up there too,
        # but the guild_settings table uses ON DELETE CASCADE, so it *should* be handled automatically
        # when the guild is removed from the guilds table in main.py's on_guild_remove.


    # --- Member Events --- (Keep existing event handlers, they now use _send_log_embed)
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = self._create_log_embed(
            title="📥 Member Joined",
            description=f"{member.mention} ({member.id}) joined the server.",
            color=discord.Color.green(),
            author=member,
            footer=f"Account Created: {discord.utils.format_dt(member.created_at, style='R')}"
        )
        await self._send_log_embed(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # This event doesn't tell us if it was a kick or leave. Audit log polling will handle kicks.
        # We log it as a generic "left" event here.
        embed = self._create_log_embed(
            title="📤 Member Left",
            description=f"{member.mention} ({member.id}) left the server.",
            color=discord.Color.orange(),
            author=member
        )
        await self._send_log_embed(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]):
        # Note: Ban reason isn't available directly in this event. Audit log might have it.
        embed = self._create_log_embed(
            title="🔨 Member Banned",
            description=f"{user.mention} ({user.id}) was banned.",
            color=discord.Color.red(),
            author=user # User who was banned
        )
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = self._create_log_embed(
            title="🔓 Member Unbanned",
            description=f"{user.mention} ({user.id}) was unbanned.",
            color=discord.Color.blurple(),
            author=user # User who was unbanned
        )
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = after.guild
        changes = []
        # Nickname change
        if before.nick != after.nick:
            changes.append(f"**Nickname:** `{before.nick or 'None'}` → `{after.nick or 'None'}`")
        # Role changes (handled more reliably by audit log for who did it)
        if before.roles != after.roles:
            added_roles = [r.mention for r in after.roles if r not in before.roles]
            removed_roles = [r.mention for r in before.roles if r not in after.roles]
            if added_roles:
                changes.append(f"**Roles Added:** {', '.join(added_roles)}")
            if removed_roles:
                changes.append(f"**Roles Removed:** {', '.join(removed_roles)}")
        # Timeout change
        if before.timed_out_until != after.timed_out_until:
             if after.timed_out_until:
                 timeout_duration = discord.utils.format_dt(after.timed_out_until, style='R')
                 changes.append(f"**Timed Out Until:** {timeout_duration}")
             else:
                 changes.append("**Timeout Removed**")

        # TODO: Add other trackable changes like status if needed

        if changes:
            embed = self._create_log_embed(
                title="👤 Member Updated",
                description=f"{after.mention} ({after.id})\n" + "\n".join(changes),
                color=discord.Color.yellow(),
                author=after
            )
            await self._send_log_embed(guild, embed)


    # --- Role Events ---
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = self._create_log_embed(
            title="✨ Role Created",
            description=f"Role {role.mention} (`{role.name}`, ID: {role.id}) was created.",
            color=discord.Color.teal()
        )
        # Audit log needed to see *who* created it
        await self._send_log_embed(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = self._create_log_embed(
            title="🗑️ Role Deleted",
            description=f"Role `{role.name}` (ID: {role.id}) was deleted.",
            color=discord.Color.dark_teal()
        )
        # Audit log needed to see *who* deleted it
        await self._send_log_embed(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        guild = after.guild
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` → `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"**Hoisted:** `{before.hoist}` → `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable:** `{before.mentionable}` → `{after.mentionable}`")
        if before.permissions != after.permissions:
            # Comparing permissions can be complex, just note that they changed.
            # Audit log provides specifics on permission changes.
            changes.append("**Permissions Updated**")
            # You could compare p.name for p in before.permissions if p.value and not getattr(after.permissions, p.name) etc.
            # but it gets verbose quickly.

        if changes:
            embed = self._create_log_embed(
                title="🔧 Role Updated",
                description=f"Role {after.mention} ({after.id})\n" + "\n".join(changes),
                color=discord.Color.blue()
            )
            # Audit log needed to see *who* updated it
            await self._send_log_embed(guild, embed)


    # --- Channel Events ---
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        ch_type = str(channel.type).capitalize()
        embed = self._create_log_embed(
            title=f"➕ {ch_type} Channel Created",
            description=f"Channel {channel.mention} (`{channel.name}`, ID: {channel.id}) was created.",
            color=discord.Color.green()
        )
        # Audit log needed for creator
        await self._send_log_embed(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        ch_type = str(channel.type).capitalize()
        embed = self._create_log_embed(
            title=f"➖ {ch_type} Channel Deleted",
            description=f"Channel `{channel.name}` (ID: {channel.id}) was deleted.",
            color=discord.Color.red()
        )
        # Audit log needed for deleter
        await self._send_log_embed(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        guild = after.guild
        changes = []
        ch_type = str(after.type).capitalize()

        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if isinstance(before, discord.TextChannel) and isinstance(after, discord.TextChannel):
            if before.topic != after.topic:
                changes.append(f"**Topic:** `{before.topic or 'None'}` → `{after.topic or 'None'}`")
            if before.slowmode_delay != after.slowmode_delay:
                 changes.append(f"**Slowmode:** `{before.slowmode_delay}s` → `{after.slowmode_delay}s`")
            if before.nsfw != after.nsfw:
                 changes.append(f"**NSFW:** `{before.nsfw}` → `{after.nsfw}`")
        if isinstance(before, discord.VoiceChannel) and isinstance(after, discord.VoiceChannel):
             if before.bitrate != after.bitrate:
                 changes.append(f"**Bitrate:** `{before.bitrate}` → `{after.bitrate}`")
             if before.user_limit != after.user_limit:
                 changes.append(f"**User Limit:** `{before.user_limit}` → `{after.user_limit}`")
        # Permission overwrites change (complex, audit log is better)
        if before.overwrites != after.overwrites:
            changes.append("**Permissions Overwrites Updated**") # Audit log better for details

        if changes:
            embed = self._create_log_embed(
                title=f"📝 {ch_type} Channel Updated",
                description=f"Channel {after.mention} ({after.id})\n" + "\n".join(changes),
                color=discord.Color.yellow()
            )
            # Audit log needed for updater
            await self._send_log_embed(guild, embed)


    # --- Message Events ---
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Ignore edits from bots or if content is the same (e.g., embed loading)
        if before.author.bot or before.content == after.content:
            return
        # Ignore messages if webhook isn't configured for the guild
        guild = after.guild
        if not guild or not await settings_manager.get_logging_webhook(guild.id):
             return
        # No need to check channel name anymore as we use webhooks

        if not guild: return # Ignore DMs

        embed = self._create_log_embed(
            title="✏️ Message Edited",
            description=f"Message edited in {after.channel.mention} [Jump to Message]({after.jump_url})",
            color=discord.Color.light_grey(),
            author=after.author
        )
        # Add fields for before and after, handling potential length limits
        embed.add_field(name="Before", value=before.content[:1020] + ('...' if len(before.content) > 1020 else ''), inline=False)
        embed.add_field(name="After", value=after.content[:1020] + ('...' if len(after.content) > 1020 else ''), inline=False)
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # Ignore deletes from bots or messages without content/embeds/attachments
        if message.author.bot or (not message.content and not message.embeds and not message.attachments):
             # Allow logging bot message deletions if needed, but can be noisy
             # Example: if message.author.id == self.bot.user.id: pass # Log bot's own deletions
             # else: return
             return
        # Ignore messages if webhook isn't configured for the guild
        guild = message.guild
        if not guild or not await settings_manager.get_logging_webhook(guild.id):
             return
        # No need to check channel name anymore

        if not guild: return # Ignore DMs

        desc = f"Message deleted in {message.channel.mention}"
        # Audit log needed for *who* deleted it, if not the author themselves
        # We can add a placeholder here and update it if the audit log confirms a moderator deletion later

        embed = self._create_log_embed(
            title="🗑️ Message Deleted",
            description=desc,
            color=discord.Color.dark_grey(),
            author=message.author
        )
        if message.content:
            embed.add_field(name="Content", value=message.content[:1020] + ('...' if len(message.content) > 1020 else ''), inline=False)
        if message.attachments:
            embed.add_field(name="Attachments", value=", ".join([att.filename for att in message.attachments]), inline=False)

        await self._send_log_embed(guild, embed)


    # --- Reaction Events ---
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        if user.bot: return
        guild = reaction.message.guild
        # Ignore reactions if webhook isn't configured for the guild
        if not guild or not await settings_manager.get_logging_webhook(guild.id):
             return
        # No need to check channel name anymore

        embed = self._create_log_embed(
            title="👍 Reaction Added",
            description=f"{user.mention} added {reaction.emoji} to a message in {reaction.message.channel.mention} [Jump to Message]({reaction.message.jump_url})",
            color=discord.Color.gold(),
            author=user
        )
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        if user.bot: return
        guild = reaction.message.guild
        # Ignore reactions if webhook isn't configured for the guild
        if not guild or not await settings_manager.get_logging_webhook(guild.id):
             return
        # No need to check channel name anymore

        embed = self._create_log_embed(
            title="👎 Reaction Removed",
            description=f"{user.mention} removed {reaction.emoji} from a message in {reaction.message.channel.mention} [Jump to Message]({reaction.message.jump_url})",
            color=discord.Color.dark_gold(),
            author=user
        )
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_reaction_clear(self, message: discord.Message, reactions: list[discord.Reaction]):
        guild = message.guild
        # Ignore reactions if webhook isn't configured for the guild
        if not guild or not await settings_manager.get_logging_webhook(guild.id):
             return
        # No need to check channel name anymore

        embed = self._create_log_embed(
            title="💥 All Reactions Cleared",
            description=f"All reactions were cleared from a message in {message.channel.mention} [Jump to Message]({message.jump_url})",
            color=discord.Color.orange(),
            author=message.author # Usually the author or a mod clears reactions
        )
        # Audit log needed for *who* cleared them
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_reaction_clear_emoji(self, reaction: discord.Reaction):
        guild = reaction.message.guild
        # Ignore reactions if webhook isn't configured for the guild
        if not guild or not await settings_manager.get_logging_webhook(guild.id):
             return
        # No need to check channel name anymore

        embed = self._create_log_embed(
            title="💥 Emoji Reactions Cleared",
            description=f"All {reaction.emoji} reactions were cleared from a message in {reaction.message.channel.mention} [Jump to Message]({reaction.message.jump_url})",
            color=discord.Color.dark_orange(),
            author=reaction.message.author # Usually the author or a mod clears reactions
        )
        # Audit log needed for *who* cleared them
        await self._send_log_embed(guild, embed)


    # --- Voice State Events ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        action = ""
        details = ""
        color = discord.Color.purple()

        # Join VC
        if before.channel is None and after.channel is not None:
            action = "🔊 Joined Voice Channel"
            details = f"Joined {after.channel.mention}"
            color = discord.Color.green()
        # Leave VC
        elif before.channel is not None and after.channel is None:
            action = "🔇 Left Voice Channel"
            details = f"Left {before.channel.mention}"
            color = discord.Color.orange()
        # Move VC
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            action = "🔄 Moved Voice Channel"
            details = f"Moved from {before.channel.mention} to {after.channel.mention}"
            color = discord.Color.blue()
        # Server Mute/Deafen Update
        elif before.mute != after.mute:
            action = "🎙️ Server Mute Update"
            details = f"Server Muted: `{after.mute}`"
            color = discord.Color.red() if after.mute else discord.Color.green()
        elif before.deaf != after.deaf:
            action = "🎧 Server Deafen Update"
            details = f"Server Deafened: `{after.deaf}`"
            color = discord.Color.red() if after.deaf else discord.Color.green()
        # Self Mute/Deafen Update (Can be noisy)
        # elif before.self_mute != after.self_mute:
        #     action = "🎙️ Self Mute Update"
        #     details = f"Self Muted: `{after.self_mute}`"
        # elif before.self_deaf != after.self_deaf:
        #     action = "🎧 Self Deafen Update"
        #     details = f"Self Deafened: `{after.self_deaf}`"
        # Stream Update (Can be noisy)
        # elif before.self_stream != after.self_stream:
        #     action = "📹 Streaming Update"
        #     details = f"Streaming: `{after.self_stream}`"
        # Video Update (Can be noisy)
        # elif before.self_video != after.self_video:
        #     action = " Webcam Update"
        #     details = f"Webcam On: `{after.self_video}`"
        else:
            return # No relevant change detected

        embed = self._create_log_embed(
            title=action,
            description=f"{member.mention} ({member.id})\n{details}",
            color=color,
            author=member
        )
        await self._send_log_embed(guild, embed)


    # --- Guild/Server Events ---
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.description != after.description:
            changes.append(f"**Description:** `{before.description or 'None'}` → `{after.description or 'None'}`")
        if before.icon != after.icon:
            changes.append(f"**Icon Changed**") # URL comparison can be tricky
        if before.banner != after.banner:
            changes.append(f"**Banner Changed**")
        if before.owner != after.owner:
            changes.append(f"**Owner:** {before.owner.mention if before.owner else 'None'} → {after.owner.mention if after.owner else 'None'}")
        # Add other relevant changes: region, verification_level, explicit_content_filter, etc.
        if before.verification_level != after.verification_level:
             changes.append(f"**Verification Level:** `{before.verification_level}` → `{after.verification_level}`")
        if before.explicit_content_filter != after.explicit_content_filter:
             changes.append(f"**Explicit Content Filter:** `{before.explicit_content_filter}` → `{after.explicit_content_filter}`")
        if before.system_channel != after.system_channel:
             changes.append(f"**System Channel:** {before.system_channel.mention if before.system_channel else 'None'} → {after.system_channel.mention if after.system_channel else 'None'}")


        if changes:
            embed = self._create_log_embed(
                title="⚙️ Guild Updated",
                description="Server settings were updated:\n" + "\n".join(changes),
                color=discord.Color.dark_purple()
            )
            # Audit log needed for *who* updated it
            await self._send_log_embed(after, embed)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: tuple[discord.Emoji, ...], after: tuple[discord.Emoji, ...]):
        added = [e for e in after if e not in before]
        removed = [e for e in before if e not in after]
        # Renamed detection is harder, requires comparing by ID
        renamed_before = []
        renamed_after = []
        before_map = {e.id: e for e in before}
        after_map = {e.id: e for e in after}
        for e_id, e_after in after_map.items():
            if e_id in before_map and before_map[e_id].name != e_after.name:
                 renamed_before.append(before_map[e_id])
                 renamed_after.append(e_after)


        desc = ""
        if added:
            desc += f"**Added:** {', '.join([str(e) for e in added])}\n"
        if removed:
            desc += f"**Removed:** {', '.join([f'`{e.name}`' for e in removed])}\n" # Can't display removed emoji easily
        if renamed_before:
             desc += "**Renamed:**\n" + "\n".join([f"`{b.name}` → {a}" for b, a in zip(renamed_before, renamed_after)])


        if desc:
            embed = self._create_log_embed(
                title="😀 Emojis Updated",
                description=desc.strip(),
                color=discord.Color.magenta()
            )
            # Audit log needed for *who* updated them
            await self._send_log_embed(guild, embed)


    # --- Invite Events ---
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        guild = invite.guild
        if not guild: return

        inviter = invite.inviter
        channel = invite.channel
        desc = f"Invite `{invite.code}` created for {channel.mention if channel else 'Unknown Channel'}"
        if invite.max_age:
            expires_at = invite.created_at + datetime.timedelta(seconds=invite.max_age)
            desc += f"\nExpires: {discord.utils.format_dt(expires_at, style='R')}"
        if invite.max_uses:
            desc += f"\nMax Uses: {invite.max_uses}"

        embed = self._create_log_embed(
            title="✉️ Invite Created",
            description=desc,
            color=discord.Color.dark_magenta(),
            author=inviter # Can be None if invite created through server settings/vanity URL
        )
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        guild = invite.guild
        if not guild: return

        channel = invite.channel
        desc = f"Invite `{invite.code}` for {channel.mention if channel else 'Unknown Channel'} was deleted or expired."

        embed = self._create_log_embed(
            title="🗑️ Invite Deleted",
            description=desc,
            color=discord.Color.dark_grey()
            # Cannot reliably get inviter after deletion
        )
        # Audit log might show who deleted it if done manually
        await self._send_log_embed(guild, embed)


    # --- Bot/Command Events ---
    # Note: These might be noisy depending on bot usage. Consider enabling selectively.
    # @commands.Cog.listener()
    # async def on_command(self, ctx: commands.Context):
    #     if not ctx.guild: return # Ignore DMs
    #     embed = self._create_log_embed(
    #         title="▶️ Command Used",
    #         description=f"`{ctx.command.qualified_name}` used by {ctx.author.mention} in {ctx.channel.mention}",
    #         color=discord.Color.lighter_grey(),
    #         author=ctx.author
    #     )
    #     await self._send_log_embed(ctx.guild, embed)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Log only significant errors, ignore things like CommandNotFound or CheckFailure if desired
        ignored = (commands.CommandNotFound, commands.CheckFailure, commands.UserInputError, commands.DisabledCommand, commands.CommandOnCooldown)
        if isinstance(error, ignored):
            return
        if not ctx.guild: return # Ignore DMs

        embed = self._create_log_embed(
            title="❌ Command Error",
            description=f"Error in command `{ctx.command.qualified_name if ctx.command else 'Unknown'}` used by {ctx.author.mention} in {ctx.channel.mention}",
            color=discord.Color.brand_red(),
            author=ctx.author
        )
        # Get traceback if available (might need error handling specific to your bot's setup)
        import traceback
        tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        embed.add_field(name="Error Details", value=f"```py\n{tb[:1000]}\n...```" if len(tb) > 1000 else f"```py\n{tb}```", inline=False)

        await self._send_log_embed(ctx.guild, embed)

    # @commands.Cog.listener()
    # async def on_command_completion(self, ctx: commands.Context):
    #     if not ctx.guild: return # Ignore DMs
    #     embed = self._create_log_embed(
    #         title="✅ Command Completed",
    #         description=f"`{ctx.command.qualified_name}` completed successfully for {ctx.author.mention} in {ctx.channel.mention}",
    #         color=discord.Color.dark_green(),
    #         author=ctx.author
    #     )
    #     await self._send_log_embed(ctx.guild, embed)


    # --- Audit Log Polling Task ---
    @tasks.loop(seconds=30) # Poll every 30 seconds
    async def poll_audit_log(self):
        # This loop starts only after the bot is ready and initialized
        if not self.bot.is_ready() or self.session is None or self.session.closed:
            # log.debug("Audit log poll skipped: Bot not ready or session not initialized.")
            return # Wait until ready and session is available

        # log.debug("Polling audit logs for all guilds...") # Can be noisy
        for guild in self.bot.guilds:
            guild_id = guild.id
            # Skip polling if webhook isn't configured for this guild
            if not await settings_manager.get_logging_webhook(guild_id):
                # log.debug(f"Skipping audit log poll for guild {guild_id}: Logging webhook not configured.")
                continue

            # Check permissions and last known ID for this specific guild
            if not guild.me.guild_permissions.view_audit_log:
                if self.last_audit_log_ids.get(guild_id) is not None: # Log only once when perms are lost
                     log.warning(f"Missing 'View Audit Log' permission in guild {guild_id}. Cannot poll audit log.")
                     self.last_audit_log_ids[guild_id] = None # Mark as unable to poll
                continue # Skip this guild

            # If we previously couldn't poll due to permissions, try re-initializing the ID
            if self.last_audit_log_ids.get(guild_id) is None and guild.me.guild_permissions.view_audit_log:
                 log.info(f"Re-initializing audit log ID for guild {guild_id} after gaining permissions.")
                 try:
                     async for entry in guild.audit_logs(limit=1):
                         self.last_audit_log_ids[guild_id] = entry.id
                         log.debug(f"Re-initialized last_audit_log_id for guild {guild.id} to {entry.id}")
                         break
                 except Exception as e:
                     log.exception(f"Error re-initializing audit log ID for guild {guild.id}: {e}")
                     continue # Skip this cycle if re-init fails

            last_id = self.last_audit_log_ids.get(guild_id)
            # log.debug(f"Polling audit log for guild {guild_id} after ID: {last_id}") # Can be noisy

            relevant_actions = [
                discord.AuditLogAction.kick,
                discord.AuditLogAction.member_prune, # User removed via prune
                discord.AuditLogAction.member_role_update, # Manual role changes
                discord.AuditLogAction.message_delete, # Moderator message delete
                discord.AuditLogAction.message_bulk_delete, # Moderator bulk delete
                discord.AuditLogAction.member_update, # e.g. Timeout applied by mod
                # Add other actions as needed: channel updates by mods, role updates by mods, etc.
            ]

            latest_id_in_batch = last_id
            entries_to_log = []

            try:
                # Fetch entries after the last known ID for this guild
                async for entry in guild.audit_logs(limit=50, after=discord.Object(id=last_id) if last_id else None, actions=relevant_actions):
                    # log.debug(f"Processing audit entry {entry.id} for guild {guild_id}") # Debug print
                    # Double check ID comparison just in case the 'after' parameter isn't perfectly reliable across different calls/times
                    if last_id is None or entry.id > last_id:
                         entries_to_log.append(entry)
                         if latest_id_in_batch is None or entry.id > latest_id_in_batch:
                             latest_id_in_batch = entry.id

                # Process entries oldest to newest to maintain order
                for entry in reversed(entries_to_log):
                    await self._process_audit_log_entry(guild, entry)

                # Update the last seen ID for this guild *after* processing the batch
                if latest_id_in_batch is not None and latest_id_in_batch != last_id:
                    self.last_audit_log_ids[guild_id] = latest_id_in_batch
                    # log.debug(f"Updated last_audit_log_id for guild {guild_id} to {latest_id_in_batch}") # Debug print

            except discord.Forbidden:
                log.warning(f"Missing permissions (likely View Audit Log) in guild {guild.id} during poll. Marking as unable.")
                self.last_audit_log_ids[guild_id] = None # Mark as unable to poll
            except discord.HTTPException as e:
                log.error(f"HTTP error fetching audit logs for guild {guild.id}: {e}. Retrying next cycle.")
                # Consider adding backoff logic here if errors persist
            except Exception as e:
                log.exception(f"Unexpected error in poll_audit_log for guild {guild.id}: {e}")
                # Don't update last_audit_log_id on unexpected error, retry next time


    async def _process_audit_log_entry(self, guild: discord.Guild, entry: discord.AuditLogEntry):
        """Processes a single relevant audit log entry and sends an embed."""
        user = entry.user # Moderator/Actor
        target = entry.target # User/Channel/Role/Message affected
        reason = entry.reason
        action_desc = ""
        target_desc = ""
        color = discord.Color.dark_grey()
        title = f"🛡️ Audit Log: {str(entry.action).replace('_', ' ').title()}"

        if not user: # Should generally not happen for manual actions, but safeguard
            return

        # --- Kick / Prune ---
        if entry.action == discord.AuditLogAction.kick:
            action_desc = f"{user.mention} kicked {target.mention} ({target.id})"
            color = discord.Color.brand_red()
        elif entry.action == discord.AuditLogAction.member_prune:
            # Target isn't available here, 'extra' has details
            days = entry.extra.get('delete_member_days')
            count = entry.extra.get('members_removed')
            action_desc = f"{user.mention} pruned {count} members inactive for {days} days."
            color = discord.Color.dark_red()

        # --- Member Role Update ---
        elif entry.action == discord.AuditLogAction.member_role_update:
            # entry.before.roles / entry.after.roles contains the role changes
            before_roles = entry.before.roles
            after_roles = entry.after.roles
            added = [r.mention for r in after_roles if r not in before_roles]
            removed = [r.mention for r in before_roles if r not in after_roles]
            if added or removed: # Only log if roles actually changed
                action_desc = f"{user.mention} updated roles for {target.mention} ({target.id}):"
                if added: action_desc += f"\n**Added:** {', '.join(added)}"
                if removed: action_desc += f"\n**Removed:** {', '.join(removed)}"
                color = discord.Color.blue()
            else: return # Skip if no role change detected

        # --- Member Update (e.g. Timeout) ---
        elif entry.action == discord.AuditLogAction.member_update:
             # Check specifically for timeout changes
             before_timed_out = entry.before.timed_out_until
             after_timed_out = entry.after.timed_out_until
             if before_timed_out != after_timed_out:
                 if after_timed_out:
                     timeout_duration = discord.utils.format_dt(after_timed_out, style='R')
                     action_desc = f"{user.mention} timed out {target.mention} ({target.id}) until {timeout_duration}"
                     color = discord.Color.orange()
                 else:
                     action_desc = f"{user.mention} removed timeout from {target.mention} ({target.id})"
                     color = discord.Color.green()
             else: return # Skip other member updates for now unless needed

        # --- Message Delete ---
        elif entry.action == discord.AuditLogAction.message_delete:
            channel = entry.extra.channel
            count = entry.extra.count
            action_desc = f"{user.mention} deleted {count} message(s) by {target.mention} ({target.id}) in {channel.mention}"
            color = discord.Color.dark_grey()

        # --- Message Bulk Delete ---
        elif entry.action == discord.AuditLogAction.message_bulk_delete:
             channel = entry.target # Channel is the target here
             count = entry.extra.count
             action_desc = f"{user.mention} bulk deleted {count} messages in {channel.mention}"
             color = discord.Color.dark_grey()

        # --- Add other relevant actions here ---
        # e.g., channel create/delete/update by mod, role create/delete/update by mod

        else:
            # Action is relevant but not specifically handled yet
            action_desc = f"{user.mention} performed action `{entry.action}`"
            if target: action_desc += f" on {target.mention if hasattr(target, 'mention') else target}"


        if not action_desc: # If no description was generated, skip logging
             return

        embed = self._create_log_embed(
            title=title,
            description=action_desc,
            color=color,
            author=user # The moderator/actor
        )
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Audit Log Entry ID: {entry.id}")

        await self._send_log_embed(guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
    log.info("LoggingCog added.")
