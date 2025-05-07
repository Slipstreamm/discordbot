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

# Define all possible event keys for toggling
# Keep this list updated if new loggable events are added
ALL_EVENT_KEYS = sorted([
    # Direct Events
    "member_join", "member_remove", "member_ban_event", "member_unban", "member_update",
    "role_create_event", "role_delete_event", "role_update_event",
    "channel_create_event", "channel_delete_event", "channel_update_event",
    "message_edit", "message_delete",
    "reaction_add", "reaction_remove", "reaction_clear", "reaction_clear_emoji",
    "voice_state_update",
    "guild_update_event", "emoji_update_event",
    "invite_create_event", "invite_delete_event",
    "command_error", # Potentially noisy
    "thread_create", "thread_delete", "thread_update", "thread_member_join", "thread_member_remove",
    "webhook_update",
    # Audit Log Actions (prefixed with 'audit_')
    "audit_kick", "audit_prune", "audit_ban", "audit_unban",
    "audit_member_role_update", "audit_member_update_timeout", # Specific member_update cases
    "audit_message_delete", "audit_message_bulk_delete",
    "audit_role_create", "audit_role_delete", "audit_role_update",
    "audit_channel_create", "audit_channel_delete", "audit_channel_update",
    "audit_emoji_create", "audit_emoji_delete", "audit_emoji_update",
    "audit_invite_create", "audit_invite_delete",
    "audit_guild_update",
    # Add more audit keys if needed, e.g., "audit_stage_instance_create"
])

class LoggingCog(commands.Cog):
    """Handles comprehensive server event logging via webhooks with granular toggling."""
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
            # Add User ID to footer if author is present and footer isn't custom
            user_id_str = f" | User ID: {author.id}" if author else ""
            embed.set_footer(text=f"Bot ID: {self.bot.user.id}{user_id_str}")
        return embed

    def _add_id_footer(self, embed: discord.Embed, obj: Union[discord.Member, discord.User, discord.Role, discord.abc.GuildChannel, discord.Message, discord.Invite, None] = None, obj_id: Optional[int] = None, id_name: str = "ID"):
        """Adds an ID to the embed footer if possible."""
        target_id = obj_id or (obj.id if obj else None)
        if target_id:
            existing_footer = embed.footer.text or ""
            separator = " | " if existing_footer else ""
            embed.set_footer(text=f"{existing_footer}{separator}{id_name}: {target_id}")

    async def _check_log_enabled(self, guild_id: int, event_key: str) -> bool:
        """Checks if logging is enabled for a specific event key in a guild."""
        # First, check if the webhook is configured at all
        webhook_url = await settings_manager.get_logging_webhook(guild_id)
        if not webhook_url:
            return False
        # Then, check if the specific event is enabled (defaults to True if not set)
        enabled = await settings_manager.is_log_event_enabled(guild_id, event_key, default_enabled=True)
        # if not enabled:
        #     log.debug(f"Logging disabled for event '{event_key}' in guild {guild_id}")
        return enabled


    # --- Log Command Group ---

    @commands.group(name="log", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def log_group(self, ctx: commands.Context):
        """Manages logging settings. Use subcommands like 'channel', 'toggle', 'status', 'list_keys'."""
        await ctx.send_help(ctx.command)

    @log_group.command(name="channel")
    @commands.has_permissions(administrator=True)
    async def log_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Sets the channel for logging and creates/updates the webhook. (Admin Only)"""
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

    @log_group.command(name="toggle")
    @commands.has_permissions(administrator=True)
    async def log_toggle(self, ctx: commands.Context, event_key: str, enabled_status: Optional[bool] = None):
        """Toggles logging for a specific event type (on/off).

        Use 'log list_keys' to see available event keys.
        If [on|off] is not provided, the current status will be flipped.
        Example: !log toggle message_edit off
        Example: !log toggle audit_kick
        """
        guild_id = ctx.guild.id
        event_key = event_key.lower() # Ensure case-insensitivity

        if event_key not in ALL_EVENT_KEYS:
            await ctx.send(f"❌ Invalid event key: `{event_key}`. Use `{ctx.prefix}log list_keys` to see valid keys.")
            return

        # Determine the new status
        if enabled_status is None:
            # Fetch current status (defaults to True if not explicitly set)
            current_status = await settings_manager.is_log_event_enabled(guild_id, event_key, default_enabled=True)
            new_status = not current_status
        else:
            new_status = enabled_status

        # Save the new status
        success = await settings_manager.set_log_event_enabled(guild_id, event_key, new_status)

        if success:
            status_str = "ENABLED" if new_status else "DISABLED"
            await ctx.send(f"✅ Logging for event `{event_key}` is now **{status_str}**.")
        else:
            await ctx.send(f"❌ Failed to update setting for event `{event_key}`. Please check logs or try again.")

    @log_group.command(name="status")
    @commands.has_permissions(administrator=True)
    async def log_status(self, ctx: commands.Context):
        """Shows the current enabled/disabled status for all loggable events."""
        guild_id = ctx.guild.id
        toggles = await settings_manager.get_all_log_event_toggles(guild_id)

        embed = discord.Embed(title=f"Logging Status for {ctx.guild.name}", color=discord.Color.blue())
        lines = []
        for key in ALL_EVENT_KEYS:
            # Get status, defaulting to True if not explicitly in the DB/cache map
            is_enabled = toggles.get(key, True)
            status_emoji = "✅" if is_enabled else "❌"
            lines.append(f"{status_emoji} `{key}`")

        # Paginate if too long for one embed description
        description = ""
        for line in lines:
            if len(description) + len(line) + 1 > 4000: # Embed description limit (approx)
                embed.description = description
                await ctx.send(embed=embed)
                description = line + "\n" # Start new description
                embed = discord.Embed(color=discord.Color.blue()) # New embed for continuation
            else:
                description += line + "\n"

        if description: # Send the last embed page
             embed.description = description.strip()
             await ctx.send(embed=embed)


    @log_group.command(name="list_keys")
    async def log_list_keys(self, ctx: commands.Context):
        """Lists all valid event keys for use with the 'log toggle' command."""
        embed = discord.Embed(title="Available Logging Event Keys", color=discord.Color.purple())
        keys_text = "\n".join(f"`{key}`" for key in ALL_EVENT_KEYS)

        # Paginate if needed
        if len(keys_text) > 4000:
             parts = []
             current_part = ""
             for key in ALL_EVENT_KEYS:
                 line = f"`{key}`\n"
                 if len(current_part) + len(line) > 4000:
                     parts.append(current_part)
                     current_part = line
                 else:
                     current_part += line
             if current_part:
                 parts.append(current_part)

             embed.description = parts[0]
             await ctx.send(embed=embed)
             for part in parts[1:]:
                 await ctx.send(embed=discord.Embed(description=part, color=discord.Color.purple()))
        else:
             embed.description = keys_text
             await ctx.send(embed=embed)


    # --- Thread Events ---
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        guild = thread.guild
        event_key = "thread_create"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="🧵 Thread Created",
            description=f"Thread {thread.mention} (`{thread.name}`) created in {thread.parent.mention}.",
            color=discord.Color.dark_blue(),
            # Creator might be available via thread.owner_id or audit log
            footer=f"Thread ID: {thread.id} | Parent ID: {thread.parent_id}"
        )
        if thread.owner: # Sometimes owner isn't cached immediately
             embed.set_author(name=str(thread.owner), icon_url=thread.owner.display_avatar.url)
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        guild = thread.guild
        event_key = "thread_delete"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="🗑️ Thread Deleted",
            description=f"Thread `{thread.name}` deleted from {thread.parent.mention}.",
            color=discord.Color.dark_grey(),
            footer=f"Thread ID: {thread.id} | Parent ID: {thread.parent_id}"
        )
        # Audit log needed for deleter
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        guild = after.guild
        event_key = "thread_update"
        if not await self._check_log_enabled(guild.id, event_key): return

        changes = []
        if before.name != after.name: changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.archived != after.archived: changes.append(f"**Archived:** `{before.archived}` → `{after.archived}`")
        if before.locked != after.locked: changes.append(f"**Locked:** `{before.locked}` → `{after.locked}`")
        if before.slowmode_delay != after.slowmode_delay: changes.append(f"**Slowmode:** `{before.slowmode_delay}s` → `{after.slowmode_delay}s`")
        if before.auto_archive_duration != after.auto_archive_duration: changes.append(f"**Auto-Archive:** `{before.auto_archive_duration} mins` → `{after.auto_archive_duration} mins`")

        if changes:
            embed = self._create_log_embed(
                title="📝 Thread Updated",
                description=f"Thread {after.mention} in {after.parent.mention} updated:\n" + "\n".join(changes),
                color=discord.Color.blue(),
                footer=f"Thread ID: {after.id}"
            )
            # Audit log needed for updater
            await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_thread_member_join(self, member: discord.ThreadMember):
        thread = member.thread
        guild = thread.guild
        event_key = "thread_member_join"
        if not await self._check_log_enabled(guild.id, event_key): return

        user = await self.bot.fetch_user(member.id) # Get user object
        embed = self._create_log_embed(
            title="➕ Member Joined Thread",
            description=f"{user.mention} joined thread {thread.mention}.",
            color=discord.Color.dark_green(),
            author=user,
            footer=f"Thread ID: {thread.id} | User ID: {user.id}"
        )
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_thread_member_remove(self, member: discord.ThreadMember):
        thread = member.thread
        guild = thread.guild
        event_key = "thread_member_remove"
        if not await self._check_log_enabled(guild.id, event_key): return

        user = await self.bot.fetch_user(member.id) # Get user object
        embed = self._create_log_embed(
            title="➖ Member Left Thread",
            description=f"{user.mention} left thread {thread.mention}.",
            color=discord.Color.dark_orange(),
            author=user,
            footer=f"Thread ID: {thread.id} | User ID: {user.id}"
        )
        await self._send_log_embed(guild, embed)


    # --- Webhook Events ---
    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        """Logs when webhooks are updated in a channel."""
        guild = channel.guild
        event_key = "webhook_update"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="🎣 Webhooks Updated",
            description=f"Webhooks were updated in channel {channel.mention}.\n*Audit log may contain specific details and updater.*",
            color=discord.Color.greyple(),
            footer=f"Channel ID: {channel.id}"
        )
        await self._send_log_embed(guild, embed)


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
        guild = member.guild
        event_key = "member_join"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="📥 Member Joined",
            description=f"{member.mention} ({member.id}) joined the server.",
            color=discord.Color.green(),
            author=member
            # Footer already includes User ID via _create_log_embed
        )
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, style='F'), inline=False)
        await self._send_log_embed(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        event_key = "member_remove"
        if not await self._check_log_enabled(guild.id, event_key): return

        # This event doesn't tell us if it was a kick or leave. Audit log polling will handle kicks.
        # We log it as a generic "left" event here.
        embed = self._create_log_embed(
            title="📤 Member Left",
            description=f"{member.mention} left the server.",
            color=discord.Color.orange(),
            author=member
        )
        self._add_id_footer(embed, member, id_name="User ID")
        await self._send_log_embed(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]):
        event_key = "member_ban_event"
        if not await self._check_log_enabled(guild.id, event_key): return

        # Note: Ban reason isn't available directly in this event. Audit log might have it.
        embed = self._create_log_embed(
            title="🔨 Member Banned (Event)", # Clarify this is the event, audit log has more details
            description=f"{user.mention} was banned.\n*Audit log may contain moderator and reason.*",
            color=discord.Color.red(),
            author=user # User who was banned
        )
        self._add_id_footer(embed, user, id_name="User ID")
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        event_key = "member_unban"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="🔓 Member Unbanned",
            description=f"{user.mention} was unbanned.",
            color=discord.Color.blurple(),
            author=user # User who was unbanned
        )
        self._add_id_footer(embed, user, id_name="User ID")
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = after.guild
        event_key = "member_update"
        if not await self._check_log_enabled(guild.id, event_key): return

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

        # Add avatar change detection
        if before.display_avatar != after.display_avatar:
             changes.append(f"**Avatar Changed**") # URL is enough, no need to show old/new

        if changes:
            embed = self._create_log_embed(
                title="👤 Member Updated",
                description=f"{after.mention}\n" + "\n".join(changes),
                color=discord.Color.yellow(),
                author=after
            )
            self._add_id_footer(embed, after, id_name="User ID")
            await self._send_log_embed(guild, embed)


    # --- Role Events ---
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        event_key = "role_create_event"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="✨ Role Created (Event)",
            description=f"Role {role.mention} (`{role.name}`) was created.\n*Audit log may contain creator.*",
            color=discord.Color.teal()
        )
        self._add_id_footer(embed, role, id_name="Role ID")
        await self._send_log_embed(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        event_key = "role_delete_event"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="🗑️ Role Deleted (Event)",
            description=f"Role `{role.name}` was deleted.\n*Audit log may contain deleter.*",
            color=discord.Color.dark_teal()
        )
        self._add_id_footer(embed, role, id_name="Role ID")
        await self._send_log_embed(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        guild = after.guild
        event_key = "role_update_event"
        if not await self._check_log_enabled(guild.id, event_key): return

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

        # Add position change
        if before.position != after.position:
             changes.append(f"**Position:** `{before.position}` → `{after.position}`")

        if changes:
            embed = self._create_log_embed(
                title="🔧 Role Updated (Event)",
                description=f"Role {after.mention} updated.\n*Audit log may contain updater and specific permission changes.*\n" + "\n".join(changes),
                color=discord.Color.blue()
            )
            self._add_id_footer(embed, after, id_name="Role ID")
            await self._send_log_embed(guild, embed)


    # --- Channel Events ---
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        event_key = "channel_create_event"
        if not await self._check_log_enabled(guild.id, event_key): return

        ch_type = str(channel.type).capitalize()
        embed = self._create_log_embed(
            title=f"➕ {ch_type} Channel Created (Event)",
            description=f"Channel {channel.mention} (`{channel.name}`) was created.\n*Audit log may contain creator.*",
            color=discord.Color.green()
        )
        self._add_id_footer(embed, channel, id_name="Channel ID")
        await self._send_log_embed(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        event_key = "channel_delete_event"
        if not await self._check_log_enabled(guild.id, event_key): return

        ch_type = str(channel.type).capitalize()
        embed = self._create_log_embed(
            title=f"➖ {ch_type} Channel Deleted (Event)",
            description=f"Channel `{channel.name}` was deleted.\n*Audit log may contain deleter.*",
            color=discord.Color.red()
        )
        self._add_id_footer(embed, channel, id_name="Channel ID")
        await self._send_log_embed(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        guild = after.guild
        event_key = "channel_update_event"
        if not await self._check_log_enabled(guild.id, event_key): return

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
        # Permission overwrites change
        if before.overwrites != after.overwrites:
            # Identify changes without detailing every permission bit
            before_targets = set(before.overwrites.keys())
            after_targets = set(after.overwrites.keys())
            added_targets = after_targets - before_targets
            removed_targets = before_targets - after_targets
            updated_targets = before_targets.intersection(after_targets) # Targets present before and after

            overwrite_changes = []
            if added_targets:
                overwrite_changes.append(f"Added overwrites for: {', '.join([f'<@{t.id}>' if isinstance(t, discord.Member) else f'<@&{t.id}>' for t in added_targets])}")
            if removed_targets:
                 overwrite_changes.append(f"Removed overwrites for: {', '.join([f'<@{t.id}>' if isinstance(t, discord.Member) else f'<@&{t.id}>' for t in removed_targets])}")
            # Check if any *values* changed for targets present both before and after
            if any(before.overwrites[t] != after.overwrites[t] for t in updated_targets):
                 overwrite_changes.append(f"Modified overwrites for: {', '.join([f'<@{t.id}>' if isinstance(t, discord.Member) else f'<@&{t.id}>' for t in updated_targets if before.overwrites[t] != after.overwrites[t]])}")

            if overwrite_changes:
                 changes.append(f"**Permission Overwrites:**\n - " + '\n - '.join(overwrite_changes))
            else:
                 changes.append("**Permission Overwrites Updated** (No specific target changes detected by event)")


        # Add position change
        if before.position != after.position:
             changes.append(f"**Position:** `{before.position}` → `{after.position}`")
        # Add category change
        if before.category != after.category:
             before_cat = before.category.mention if before.category else 'None'
             after_cat = after.category.mention if after.category else 'None'
             changes.append(f"**Category:** {before_cat} → {after_cat}")


        if changes:
            embed = self._create_log_embed(
                title=f"📝 {ch_type} Channel Updated (Event)",
                description=f"Channel {after.mention} updated.\n*Audit log may contain updater and specific permission changes.*\n" + "\n".join(changes),
                color=discord.Color.yellow()
            )
            self._add_id_footer(embed, after, id_name="Channel ID")
            await self._send_log_embed(guild, embed)


    # --- Message Events ---
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Ignore edits from bots or if content is the same (e.g., embed loading)
        if before.author.bot or before.content == after.content:
            return
        guild = after.guild
        if not guild: return # Ignore DMs

        # Check if logging is enabled *after* initial checks
        event_key = "message_edit"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="✏️ Message Edited",
            description=f"Message edited in {after.channel.mention} [Jump to Message]({after.jump_url})",
            color=discord.Color.light_grey(),
            author=after.author
        )
        # Add fields for before and after, handling potential length limits
        embed.add_field(name="Before", value=before.content[:1020] + ('...' if len(before.content) > 1020 else '') or "`Empty Message`", inline=False)
        embed.add_field(name="After", value=after.content[:1020] + ('...' if len(after.content) > 1020 else '') or "`Empty Message`", inline=False)
        self._add_id_footer(embed, after, id_name="Message ID") # Add message ID
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # Ignore deletes from bots or messages without content/embeds/attachments
        if message.author.bot or (not message.content and not message.embeds and not message.attachments):
             # Allow logging bot message deletions if needed, but can be noisy
             # Example: if message.author.id == self.bot.user.id: pass # Log bot's own deletions
             # else: return
             return
        guild = message.guild
        if not guild: return # Ignore DMs

        # Check if logging is enabled *after* initial checks
        event_key = "message_delete"
        if not await self._check_log_enabled(guild.id, event_key): return

        desc = f"Message deleted in {message.channel.mention}"
        # Audit log needed for *who* deleted it, if not the author themselves
        # We can add a placeholder here and update it if the audit log confirms a moderator deletion later

        embed = self._create_log_embed(
            title="🗑️ Message Deleted",
            description=f"{desc}\n*Audit log may contain deleter if not the author.*",
            color=discord.Color.dark_grey(),
            author=message.author
        )
        if message.content:
            embed.add_field(name="Content", value=message.content[:1020] + ('...' if len(message.content) > 1020 else '') or "`Empty Message`", inline=False)
        if message.attachments:
            atts = [f"[{att.filename}]({att.url})" for att in message.attachments]
            embed.add_field(name="Attachments", value=", ".join(atts), inline=False)
        self._add_id_footer(embed, message, id_name="Message ID") # Add message ID
        await self._send_log_embed(guild, embed)


    # --- Reaction Events ---
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        if user.bot: return
        guild = reaction.message.guild
        if not guild: return # Should not happen in guilds but safety check

        # Check if logging is enabled *after* initial checks
        event_key = "reaction_add"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="👍 Reaction Added",
            description=f"{user.mention} added {reaction.emoji} to a message by {reaction.message.author.mention} in {reaction.message.channel.mention} [Jump to Message]({reaction.message.jump_url})",
            color=discord.Color.gold(),
            author=user
        )
        self._add_id_footer(embed, reaction.message, id_name="Message ID")
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        if user.bot: return
        guild = reaction.message.guild
        if not guild: return # Should not happen in guilds but safety check

        # Check if logging is enabled *after* initial checks
        event_key = "reaction_remove"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="👎 Reaction Removed",
            description=f"{user.mention} removed {reaction.emoji} from a message by {reaction.message.author.mention} in {reaction.message.channel.mention} [Jump to Message]({reaction.message.jump_url})",
            color=discord.Color.dark_gold(),
            author=user
        )
        self._add_id_footer(embed, reaction.message, id_name="Message ID")
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_reaction_clear(self, message: discord.Message, _: list[discord.Reaction]):
        guild = message.guild
        if not guild: return # Should not happen in guilds but safety check

        # Check if logging is enabled *after* initial checks
        event_key = "reaction_clear"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="💥 All Reactions Cleared",
            description=f"All reactions were cleared from a message by {message.author.mention} in {message.channel.mention} [Jump to Message]({message.jump_url})\n*Audit log may contain moderator.*",
            color=discord.Color.orange(),
            author=message.author # Usually the author or a mod clears reactions
        )
        self._add_id_footer(embed, message, id_name="Message ID")
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_reaction_clear_emoji(self, reaction: discord.Reaction):
        guild = reaction.message.guild
        if not guild: return # Should not happen in guilds but safety check

        # Check if logging is enabled *after* initial checks
        event_key = "reaction_clear_emoji"
        if not await self._check_log_enabled(guild.id, event_key): return

        embed = self._create_log_embed(
            title="💥 Emoji Reactions Cleared",
            description=f"All {reaction.emoji} reactions were cleared from a message by {reaction.message.author.mention} in {reaction.message.channel.mention} [Jump to Message]({reaction.message.jump_url})\n*Audit log may contain moderator.*",
            color=discord.Color.dark_orange(),
            author=reaction.message.author # Usually the author or a mod clears reactions
        )
        self._add_id_footer(embed, reaction.message, id_name="Message ID")
        await self._send_log_embed(guild, embed)


    # --- Voice State Events ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        event_key = "voice_state_update"
        if not await self._check_log_enabled(guild.id, event_key): return

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
            description=f"{member.mention}\n{details}",
            color=color,
            author=member
        )
        self._add_id_footer(embed, member, id_name="User ID")
        await self._send_log_embed(guild, embed)


    # --- Guild/Server Events ---
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        guild = after # Use 'after' for guild ID check
        event_key = "guild_update_event"
        if not await self._check_log_enabled(guild.id, event_key): return

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
                # title="⚙️ Guild Updated", # Removed duplicate title
                title="⚙️ Guild Updated (Event)",
                description="Server settings were updated.\n*Audit log may contain updater.*\n" + "\n".join(changes),
                color=discord.Color.dark_purple()
            )
            self._add_id_footer(embed, after, id_name="Guild ID")
            await self._send_log_embed(after, embed)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: tuple[discord.Emoji, ...], after: tuple[discord.Emoji, ...]):
        event_key = "emoji_update_event"
        if not await self._check_log_enabled(guild.id, event_key): return

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
                # title="😀 Emojis Updated", # Removed duplicate title
                title="😀 Emojis Updated (Event)",
                description=f"*Audit log may contain updater.*\n{desc.strip()}",
                color=discord.Color.magenta()
            )
            self._add_id_footer(embed, guild, id_name="Guild ID")
            await self._send_log_embed(guild, embed)


    # --- Invite Events ---
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        guild = invite.guild
        if not guild: return

        # Check if logging is enabled *after* initial checks
        event_key = "invite_create_event"
        if not await self._check_log_enabled(guild.id, event_key): return

        inviter = invite.inviter
        channel = invite.channel
        desc = f"Invite `{invite.code}` created for {channel.mention if channel else 'Unknown Channel'}"
        if invite.max_age:
            # Use invite.created_at if available, otherwise fall back to current time
            created_time = invite.created_at if invite.created_at is not None else discord.utils.utcnow()
            expires_at = created_time + datetime.timedelta(seconds=invite.max_age)
            desc += f"\nExpires: {discord.utils.format_dt(expires_at, style='R')}"
        if invite.max_uses:
            desc += f"\nMax Uses: {invite.max_uses}"

        embed = self._create_log_embed(
            # title="✉️ Invite Created", # Removed duplicate title
            title="✉️ Invite Created (Event)",
            description=f"{desc}\n*Audit log may contain creator.*",
            color=discord.Color.dark_magenta(),
            author=inviter # Can be None if invite created through server settings/vanity URL
        )
        self._add_id_footer(embed, invite, obj_id=invite.id, id_name="Invite ID") # Invite object doesn't have ID directly? Use code? No, ID exists.
        await self._send_log_embed(guild, embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        guild = invite.guild
        if not guild: return

        # Check if logging is enabled *after* initial checks
        event_key = "invite_delete_event"
        if not await self._check_log_enabled(guild.id, event_key): return

        channel = invite.channel
        desc = f"Invite `{invite.code}` for {channel.mention if channel else 'Unknown Channel'} was deleted or expired."

        embed = self._create_log_embed(
            # title="🗑️ Invite Deleted", # Removed duplicate title
            title="🗑️ Invite Deleted (Event)",
            description=f"{desc}\n*Audit log may contain deleter.*",
            color=discord.Color.dark_grey()
            # Cannot reliably get inviter after deletion
        )
        # Invite object might not have ID after deletion, use code in footer?
        embed.set_footer(text=f"Invite Code: {invite.code}")
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

        # Check if logging is enabled *after* initial checks
        event_key = "command_error"
        if not await self._check_log_enabled(ctx.guild.id, event_key): return

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
    #     if await self._check_log_enabled(ctx.guild.id, "command_completion"): # Add toggle check if uncommented
    #         await self._send_log_embed(ctx.guild, embed)

    # Note: Duplicate Thread/Webhook listeners removed below this line.
    # The first set of definitions already includes the toggle checks.

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
                discord.AuditLogAction.member_prune,
                discord.AuditLogAction.member_role_update,
                discord.AuditLogAction.message_delete,
                discord.AuditLogAction.message_bulk_delete,
                discord.AuditLogAction.member_update, # Includes timeout
                discord.AuditLogAction.role_create,
                discord.AuditLogAction.role_delete,
                discord.AuditLogAction.role_update,
                discord.AuditLogAction.channel_create,
                discord.AuditLogAction.channel_delete,
                discord.AuditLogAction.channel_update,
                discord.AuditLogAction.emoji_create,
                discord.AuditLogAction.emoji_delete,
                discord.AuditLogAction.emoji_update,
                discord.AuditLogAction.invite_create,
                discord.AuditLogAction.invite_delete,
                discord.AuditLogAction.guild_update,
                discord.AuditLogAction.ban, # Add ban action for reason/moderator
                discord.AuditLogAction.unban, # Add unban action for moderator
            ]

            latest_id_in_batch = last_id
            entries_to_log = []

            try:
                # Fetch entries after the last known ID for this guild
                # The 'actions' parameter is deprecated; filter manually after fetching.
                async for entry in guild.audit_logs(limit=50, after=discord.Object(id=last_id) if last_id else None):
                    # log.debug(f"Processing audit entry {entry.id} for guild {guild_id}") # Debug print
                    # Double check ID comparison just in case the 'after' parameter isn't perfectly reliable across different calls/times
                    if last_id is None or entry.id > last_id:
                         entries_to_log.append(entry)
                         if latest_id_in_batch is None or entry.id > latest_id_in_batch:
                             latest_id_in_batch = entry.id

                # Process entries oldest to newest to maintain order
                for entry in reversed(entries_to_log):
                    # Filter by action *after* fetching
                    if entry.action in relevant_actions:
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
        color = discord.Color.dark_grey()
        title = f"🛡️ Audit Log: {str(entry.action).replace('_', ' ').title()}"

        if not user: # Should generally not happen for manual actions, but safeguard
            return

        # --- Member Events (Ban, Unban, Kick, Prune) ---
        if entry.action == discord.AuditLogAction.ban:
            audit_event_key = "audit_ban"
            if not await self._check_log_enabled(guild.id, audit_event_key): return
            title = "🛡️ Audit Log: Member Banned"
            action_desc = f"{user.mention} banned {target.mention}"
            color = discord.Color.red()
            # self._add_id_footer(embed, target, id_name="Target ID") # Footer set later
        elif entry.action == discord.AuditLogAction.unban:
            audit_event_key = "audit_unban"
            if not await self._check_log_enabled(guild.id, audit_event_key): return
            title = "🛡️ Audit Log: Member Unbanned"
            action_desc = f"{user.mention} unbanned {target.mention}"
            color = discord.Color.blurple()
            # self._add_id_footer(embed, target, id_name="Target ID") # Footer set later
        elif entry.action == discord.AuditLogAction.kick:
            audit_event_key = "audit_kick"
            if not await self._check_log_enabled(guild.id, audit_event_key): return
            title = "🛡️ Audit Log: Member Kicked"
            action_desc = f"{user.mention} kicked {target.mention}"
            color = discord.Color.brand_red()
            # self._add_id_footer(embed, target, id_name="Target ID") # Footer set later
        elif entry.action == discord.AuditLogAction.member_prune:
            audit_event_key = "audit_prune"
            if not await self._check_log_enabled(guild.id, audit_event_key): return
            title = "🛡️ Audit Log: Member Prune"
            days = entry.extra.get('delete_member_days')
            count = entry.extra.get('members_removed')
            action_desc = f"{user.mention} pruned {count} members inactive for {days} days."
            color = discord.Color.dark_red()
            # No specific target ID here

        # --- Member Update (Roles, Timeout) ---
        elif entry.action == discord.AuditLogAction.member_role_update:
            audit_event_key = "audit_member_role_update"
            if not await self._check_log_enabled(guild.id, audit_event_key): return
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

        elif entry.action == discord.AuditLogAction.member_update:
             # Check for timeout changes
             before_timed_out = getattr(entry.before, 'timed_out_until', None)
             after_timed_out = getattr(entry.after, 'timed_out_until', None)
             if before_timed_out != after_timed_out:
                 audit_event_key = "audit_member_update_timeout"
                 if not await self._check_log_enabled(guild.id, audit_event_key): return
                 title = "🛡️ Audit Log: Member Timeout Update"
                 if after_timed_out:
                     timeout_duration = discord.utils.format_dt(after_timed_out, style='R')
                     action_desc = f"{user.mention} timed out {target.mention} ({target.id}) until {timeout_duration}"
                     color = discord.Color.orange()
                 else:
                     action_desc = f"{user.mention} removed timeout from {target.mention} ({target.id})"
                     color = discord.Color.green()
                 # self._add_id_footer(embed, target, id_name="Target ID") # Footer set later
             else:
                 # Could log other member updates here if needed (e.g. nick changes by mods) - requires separate toggle key
                 # log.debug(f"Unhandled member_update audit log entry by {user} on {target}")
                 return # Skip other member updates for now

        # --- Role Events ---
        elif entry.action == discord.AuditLogAction.role_create:
             audit_event_key = "audit_role_create"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Role Created"
             role = target # Target is the role
             action_desc = f"{user.mention} created role {role.mention} (`{role.name}`)"
             color = discord.Color.teal()
             # self._add_id_footer(embed, role, id_name="Role ID") # Footer set later
        elif entry.action == discord.AuditLogAction.role_delete:
             audit_event_key = "audit_role_delete"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Role Deleted"
             # Target is the role ID, before object has role details
             role_name = entry.before.name
             role_id = entry.target.id
             action_desc = f"{user.mention} deleted role `{role_name}` ({role_id})"
             color = discord.Color.dark_teal()
             # self._add_id_footer(embed, obj_id=role_id, id_name="Role ID") # Footer set later
        elif entry.action == discord.AuditLogAction.role_update:
             audit_event_key = "audit_role_update"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Role Updated"
             role = target
             changes = []
             # Simple diffing for common properties
             if hasattr(entry.before, 'name') and hasattr(entry.after, 'name') and entry.before.name != entry.after.name:
                 changes.append(f"Name: `{entry.before.name}` → `{entry.after.name}`")
             if hasattr(entry.before, 'color') and hasattr(entry.after, 'color') and entry.before.color != entry.after.color:
                 changes.append(f"Color: `{entry.before.color}` → `{entry.after.color}`")
             if hasattr(entry.before, 'hoist') and hasattr(entry.after, 'hoist') and entry.before.hoist != entry.after.hoist:
                 changes.append(f"Hoisted: `{entry.before.hoist}` → `{entry.after.hoist}`")
             if hasattr(entry.before, 'mentionable') and hasattr(entry.after, 'mentionable') and entry.before.mentionable != entry.after.mentionable:
                 changes.append(f"Mentionable: `{entry.before.mentionable}` → `{entry.after.mentionable}`")
             if hasattr(entry.before, 'permissions') and hasattr(entry.after, 'permissions') and entry.before.permissions != entry.after.permissions:
                 changes.append("Permissions Updated (See Audit Log for details)") # Permissions are complex
             if changes:
                 action_desc = f"{user.mention} updated role {role.mention} ({role.id}):\n" + "\n".join(f"- {c}" for c in changes)
                 color = discord.Color.blue()
                 # self._add_id_footer(embed, role, id_name="Role ID") # Footer set later
             else:
                 # log.debug(f"Role update detected for {role.id} but no tracked changes found.") # Might still want to log permission changes even if other props are same
                 return # Skip if no changes we track were made

        # --- Channel Events ---
        elif entry.action == discord.AuditLogAction.channel_create:
             audit_event_key = "audit_channel_create"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Channel Created"
             channel = target
             ch_type = str(channel.type).capitalize()
             action_desc = f"{user.mention} created {ch_type} channel {channel.mention} (`{channel.name}`)"
             color = discord.Color.green()
             # self._add_id_footer(embed, channel, id_name="Channel ID") # Footer set later
        elif entry.action == discord.AuditLogAction.channel_delete:
             audit_event_key = "audit_channel_delete"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Channel Deleted"
             # Target is channel ID, before object has details
             channel_name = entry.before.name
             channel_id = entry.target.id
             ch_type = str(entry.before.type).capitalize()
             action_desc = f"{user.mention} deleted {ch_type} channel `{channel_name}` ({channel_id})"
             color = discord.Color.red()
             # self._add_id_footer(embed, obj_id=channel_id, id_name="Channel ID") # Footer set later
        elif entry.action == discord.AuditLogAction.channel_update:
             audit_event_key = "audit_channel_update"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Channel Updated"
             channel = target
             ch_type = str(channel.type).capitalize()
             changes = []
             # Simple diffing
             if hasattr(entry.before, 'name') and hasattr(entry.after, 'name') and entry.before.name != entry.after.name:
                 changes.append(f"Name: `{entry.before.name}` → `{entry.after.name}`")
             if hasattr(entry.before, 'topic') and hasattr(entry.after, 'topic') and entry.before.topic != entry.after.topic:
                 changes.append(f"Topic Changed") # Keep it simple
             if hasattr(entry.before, 'nsfw') and hasattr(entry.after, 'nsfw') and entry.before.nsfw != entry.after.nsfw:
                 changes.append(f"NSFW: `{entry.before.nsfw}` → `{entry.after.nsfw}`")
             if hasattr(entry.before, 'slowmode_delay') and hasattr(entry.after, 'slowmode_delay') and entry.before.slowmode_delay != entry.after.slowmode_delay:
                 changes.append(f"Slowmode: `{entry.before.slowmode_delay}s` → `{entry.after.slowmode_delay}s`")
             if hasattr(entry.before, 'bitrate') and hasattr(entry.after, 'bitrate') and entry.before.bitrate != entry.after.bitrate:
                 changes.append(f"Bitrate: `{entry.before.bitrate}` → `{entry.after.bitrate}`")
             # Process detailed changes from entry.changes
             detailed_changes = []
             for change in entry.changes:
                 attr = change.attribute
                 before_val = change.before
                 after_val = change.after
                 if attr == 'name': detailed_changes.append(f"Name: `{before_val}` → `{after_val}`")
                 elif attr == 'topic': detailed_changes.append(f"Topic: `{before_val or 'None'}` → `{after_val or 'None'}`")
                 elif attr == 'nsfw': detailed_changes.append(f"NSFW: `{before_val}` → `{after_val}`")
                 elif attr == 'slowmode_delay': detailed_changes.append(f"Slowmode: `{before_val}s` → `{after_val}s`")
                 elif attr == 'bitrate': detailed_changes.append(f"Bitrate: `{before_val}` → `{after_val}`")
                 elif attr == 'user_limit': detailed_changes.append(f"User Limit: `{before_val}` → `{after_val}`")
                 elif attr == 'position': detailed_changes.append(f"Position: `{before_val}` → `{after_val}`")
                 elif attr == 'category': detailed_changes.append(f"Category: {getattr(before_val, 'mention', 'None')} → {getattr(after_val, 'mention', 'None')}")
                 elif attr == 'permission_overwrites':
                     # Audit log gives overwrite target ID and type directly in the change object
                     ow_target_id = getattr(change.target, 'id', None) # Target of the overwrite change
                     ow_target_type = getattr(change.target, 'type', None) # 'role' or 'member'
                     if ow_target_id and ow_target_type:
                         target_mention = f"<@&{ow_target_id}>" if ow_target_type == 'role' else f"<@{ow_target_id}>"
                         # Determine if added, removed, or updated (before/after values are PermissionOverwrite objects)
                         if before_val is None and after_val is not None:
                             detailed_changes.append(f"Added overwrite for {target_mention}")
                         elif before_val is not None and after_val is None:
                             detailed_changes.append(f"Removed overwrite for {target_mention}")
                         else:
                             detailed_changes.append(f"Updated overwrite for {target_mention}")
                     else:
                          detailed_changes.append("Permission Overwrites Updated (Target details unavailable)") # Fallback
                 else:
                     # Log other unhandled changes generically
                     detailed_changes.append(f"{attr.replace('_', ' ').title()} changed: `{before_val}` → `{after_val}`")

             if detailed_changes:
                 action_desc = f"{user.mention} updated {ch_type} channel {channel.mention} ({channel.id}):\n" + "\n".join(f"- {c}" for c in detailed_changes)
                 color = discord.Color.yellow()
                 # self._add_id_footer(embed, channel, id_name="Channel ID") # Footer set later
             else:
                 # log.debug(f"Channel update detected for {channel.id} but no tracked changes found.") # Might still want to log permission changes
                 return # Skip if no changes we track were made

        # --- Message Events (Delete, Bulk Delete) ---
        elif entry.action == discord.AuditLogAction.message_delete:
            audit_event_key = "audit_message_delete"
            if not await self._check_log_enabled(guild.id, audit_event_key): return
            title = "🛡️ Audit Log: Message Deleted" # Title adjusted for clarity
            channel = entry.extra.channel
            count = entry.extra.count
            action_desc = f"{user.mention} deleted {count} message(s) by {target.mention} ({target.id}) in {channel.mention}"
            color = discord.Color.dark_grey()

        elif entry.action == discord.AuditLogAction.message_bulk_delete:
             audit_event_key = "audit_message_bulk_delete"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Message Bulk Delete"
             channel = entry.target # Channel is the target here
             count = entry.extra.count
             action_desc = f"{user.mention} bulk deleted {count} messages in {channel.mention}"
             color = discord.Color.dark_grey()
             # self._add_id_footer(embed, channel, id_name="Channel ID") # Footer set later

        # --- Emoji Events ---
        elif entry.action == discord.AuditLogAction.emoji_create:
             audit_event_key = "audit_emoji_create"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Emoji Created"
             emoji = target
             action_desc = f"{user.mention} created emoji {emoji} (`{emoji.name}`)"
             color = discord.Color.magenta()
             # self._add_id_footer(embed, emoji, id_name="Emoji ID") # Footer set later
        elif entry.action == discord.AuditLogAction.emoji_delete:
             audit_event_key = "audit_emoji_delete"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Emoji Deleted"
             emoji_name = entry.before.name
             emoji_id = entry.target.id
             action_desc = f"{user.mention} deleted emoji `{emoji_name}` ({emoji_id})"
             color = discord.Color.dark_magenta()
             # self._add_id_footer(embed, obj_id=emoji_id, id_name="Emoji ID") # Footer set later
        elif entry.action == discord.AuditLogAction.emoji_update:
             audit_event_key = "audit_emoji_update"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Emoji Updated"
             emoji = target
             if hasattr(entry.before, 'name') and hasattr(entry.after, 'name') and entry.before.name != entry.after.name:
                 action_desc = f"{user.mention} renamed emoji `{entry.before.name}` to {emoji} (`{emoji.name}`)"
                 color = discord.Color.magenta()
                 # self._add_id_footer(embed, emoji, id_name="Emoji ID") # Footer set later
             else:
                 # log.debug(f"Emoji update detected for {emoji.id} but no tracked changes found.") # Only log name changes for now
                 return # Only log name changes for now

        # --- Invite Events ---
        elif entry.action == discord.AuditLogAction.invite_create:
             audit_event_key = "audit_invite_create"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Invite Created"
             invite = target # Target is the invite object
             channel = invite.channel
             desc = f"Invite `{invite.code}` created for {channel.mention if channel else 'Unknown Channel'}"
             if invite.max_age:
                 # Use invite.created_at if available, otherwise fall back to current time
                 created_time = invite.created_at if invite.created_at is not None else discord.utils.utcnow()
                 expires_at = created_time + datetime.timedelta(seconds=invite.max_age)
                 desc += f"\nExpires: {discord.utils.format_dt(expires_at, style='R')}"
             if invite.max_uses: desc += f"\nMax Uses: {invite.max_uses}"
             action_desc = f"{user.mention} created an invite:\n{desc}"
             color = discord.Color.dark_green()
             # self._add_id_footer(embed, invite, obj_id=invite.id, id_name="Invite ID") # Footer set later
        elif entry.action == discord.AuditLogAction.invite_delete:
             audit_event_key = "audit_invite_delete"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Invite Deleted"
             # Target is invite ID, before object has details
             invite_code = entry.before.code
             channel_id = entry.before.channel_id
             channel_mention = f"<#{channel_id}>" if channel_id else "Unknown Channel"
             action_desc = f"{user.mention} deleted invite `{invite_code}` for channel {channel_mention}"
             color = discord.Color.dark_red()
             # Cannot get invite ID after deletion easily, use code in footer later

        # --- Guild Update ---
        elif entry.action == discord.AuditLogAction.guild_update:
             audit_event_key = "audit_guild_update"
             if not await self._check_log_enabled(guild.id, audit_event_key): return
             title = "🛡️ Audit Log: Guild Updated"
             changes = []
             # Diffing guild properties - safely check attributes exist before comparing
             if hasattr(entry.before, 'name') and hasattr(entry.after, 'name') and entry.before.name != entry.after.name:
                 changes.append(f"Name: `{entry.before.name}` → `{entry.after.name}`")
             if hasattr(entry.before, 'description') and hasattr(entry.after, 'description') and entry.before.description != entry.after.description:
                 changes.append(f"Description Changed")
             if hasattr(entry.before, 'icon') and hasattr(entry.after, 'icon') and entry.before.icon != entry.after.icon:
                 changes.append(f"Icon Changed")
             if hasattr(entry.before, 'banner') and hasattr(entry.after, 'banner') and entry.before.banner != entry.after.banner:
                 changes.append(f"Banner Changed")
             if hasattr(entry.before, 'owner') and hasattr(entry.after, 'owner') and entry.before.owner != entry.after.owner:
                 changes.append(f"Owner: {entry.before.owner.mention if entry.before.owner else 'None'} → {entry.after.owner.mention if entry.after.owner else 'None'}")
             if hasattr(entry.before, 'verification_level') and hasattr(entry.after, 'verification_level') and entry.before.verification_level != entry.after.verification_level:
                 changes.append(f"Verification Level: `{entry.before.verification_level}` → `{entry.after.verification_level}`")
             if hasattr(entry.before, 'explicit_content_filter') and hasattr(entry.after, 'explicit_content_filter') and entry.before.explicit_content_filter != entry.after.explicit_content_filter:
                 changes.append(f"Explicit Content Filter: `{entry.before.explicit_content_filter}` → `{entry.after.explicit_content_filter}`")
             if hasattr(entry.before, 'system_channel') and hasattr(entry.after, 'system_channel') and entry.before.system_channel != entry.after.system_channel:
                 changes.append(f"System Channel Changed")
             # Add more properties as needed

             if changes:
                 action_desc = f"{user.mention} updated server settings:\n" + "\n".join(f"- {c}" for c in changes)
                 color = discord.Color.dark_purple()
                 # self._add_id_footer(embed, guild, id_name="Guild ID") # Footer set later
             else:
                 # log.debug(f"Guild update detected for {guild.id} but no tracked changes found.") # Might still want to log feature changes etc.
                 return # Skip if no changes we track were made

        else:
            # Action is in relevant_actions but not specifically handled above
            log.warning(f"Audit log action '{entry.action}' is relevant but not explicitly handled in _process_audit_log_entry.")
            # Generic fallback log
            title = f"🛡️ Audit Log: {str(entry.action).replace('_', ' ').title()}"
            # Determine the generic audit key based on the action category if possible
            generic_audit_key = f"audit_{str(entry.action).split('.')[0]}" # e.g., audit_member, audit_channel
            if generic_audit_key in ALL_EVENT_KEYS:
                 if not await self._check_log_enabled(guild.id, generic_audit_key): return
            else:
                 log.warning(f"No specific or generic toggle key found for unhandled audit action '{entry.action}'. Logging anyway.")
                 # Or decide to return here if you only want explicitly toggled events logged

            title = f"🛡️ Audit Log: {str(entry.action).replace('_', ' ').title()}"
            action_desc = f"{user.mention} performed action `{entry.action}`"
            if target:
                target_mention = getattr(target, 'mention', str(target))
                action_desc += f" on {target_mention}"
                # self._add_id_footer(embed, target, id_name="Target ID") # Footer set later
            color = discord.Color.light_grey()


        if not action_desc: # If no description was generated (e.g., skipped update), skip logging
             # log.debug(f"Skipping audit log entry {entry.id} (action: {entry.action}) as no action description was generated.")
             return

        # Create the embed (title is set within the if/elif blocks now)
        embed = self._create_log_embed(
            title=title,
            description=action_desc.strip(),
            color=color,
            author=user # The moderator/actor is the author of the log entry
        )
        if reason:
            embed.add_field(name="Reason", value=reason[:1024], inline=False) # Limit reason length

        # Add relevant IDs to footer (target ID if available, otherwise just mod/entry ID)
        target_id_str = ""
        if target:
            target_id_str = f" | Target ID: {target.id}"
        elif entry.action == discord.AuditLogAction.role_delete:
             target_id_str = f" | Role ID: {entry.target.id}" # Get ID from target even if object deleted
        elif entry.action == discord.AuditLogAction.channel_delete:
             target_id_str = f" | Channel ID: {entry.target.id}"
        elif entry.action == discord.AuditLogAction.emoji_delete:
             target_id_str = f" | Emoji ID: {entry.target.id}"
        elif entry.action == discord.AuditLogAction.invite_delete:
             target_id_str = f" | Invite Code: {entry.before.code}" # Use code for deleted invites

        embed.set_footer(text=f"Audit Log Entry ID: {entry.id} | Moderator ID: {user.id}{target_id_str}")


        await self._send_log_embed(guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
    log.info("LoggingCog added.")
