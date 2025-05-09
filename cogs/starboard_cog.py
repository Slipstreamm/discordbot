import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re
import datetime
from typing import Optional, Union, Dict, List, Tuple
import logging
import sys
import os

# Add the parent directory to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import settings manager for database operations
import settings_manager as settings_manager
from global_bot_accessor import get_bot_instance

# Set up logging
log = logging.getLogger(__name__)

class StarboardCog(commands.Cog):
    """A cog that implements a starboard feature for highlighting popular messages."""

    def __init__(self, bot):
        self.bot = bot
        self.emoji_pattern = re.compile(r'<a?:.+?:\d+>|[\U00010000-\U0010ffff]')
        self.pending_updates = {}  # Store message IDs that are being processed to prevent race conditions
        self.lock = asyncio.Lock()  # Global lock for database operations

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Event listener for when a reaction is added to a message."""
        # Skip if the reaction is from a bot
        if payload.member.bot:
            return

        # Get guild and check if it exists
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Get starboard settings for this guild
        settings = await settings_manager.get_starboard_settings(guild.id)
        if not settings or not settings.get('enabled') or not settings.get('starboard_channel_id'):
            return

        # Check if the emoji matches the configured star emoji
        emoji_str = str(payload.emoji)
        if emoji_str != settings.get('star_emoji', '⭐'):
            return

        # Process the star reaction
        await self._process_star_reaction(payload, settings, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Event listener for when a reaction is removed from a message."""
        # Get guild and check if it exists
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Get user who removed the reaction
        user = await self.bot.fetch_user(payload.user_id)
        if not user or user.bot:
            return

        # Get starboard settings for this guild
        settings = await settings_manager.get_starboard_settings(guild.id)
        if not settings or not settings.get('enabled') or not settings.get('starboard_channel_id'):
            return

        # Check if the emoji matches the configured star emoji
        emoji_str = str(payload.emoji)
        if emoji_str != settings.get('star_emoji', '⭐'):
            return

        # Process the star reaction removal
        await self._process_star_reaction(payload, settings, is_add=False)

    async def _process_star_reaction(self, payload, settings, is_add: bool):
        """Process a star reaction being added or removed."""
        # Get the channels
        guild = self.bot.get_guild(payload.guild_id)
        source_channel = guild.get_channel(payload.channel_id)
        starboard_channel = guild.get_channel(settings.get('starboard_channel_id'))

        if not source_channel or not starboard_channel:
            return

        # Check if the source channel is the starboard channel (prevent stars on starboard posts)
        if source_channel.id == starboard_channel.id:
            return

        # Acquire lock for this message to prevent race conditions
        message_key = f"{payload.guild_id}:{payload.message_id}"
        if message_key in self.pending_updates:
            log.debug(f"Skipping concurrent update for message {payload.message_id} in guild {payload.guild_id}")
            return

        self.pending_updates[message_key] = True
        try:
            # Get the message with retry logic
            message = None
            retry_attempts = 3
            for attempt in range(retry_attempts):
                try:
                    message = await source_channel.fetch_message(payload.message_id)
                    break
                except discord.NotFound:
                    log.warning(f"Message {payload.message_id} not found in channel {source_channel.id}")
                    return
                except discord.HTTPException as e:
                    if attempt < retry_attempts - 1:
                        log.warning(f"Error fetching message {payload.message_id}, attempt {attempt+1}/{retry_attempts}: {e}")
                        await asyncio.sleep(1)  # Wait before retrying
                    else:
                        log.error(f"Failed to fetch message {payload.message_id} after {retry_attempts} attempts: {e}")
                        return

            if not message:
                log.error(f"Could not retrieve message {payload.message_id} after multiple attempts")
                return

            # Check if message is from a bot and if we should ignore bot messages
            if message.author.bot and settings.get('ignore_bots', True):
                log.debug(f"Ignoring bot message {message.id} from {message.author.name}")
                return

            # Check if the user is starring their own message and if that's allowed
            if is_add and payload.user_id == message.author.id and not settings.get('self_star', False):
                log.debug(f"User {payload.user_id} attempted to star their own message {message.id}, but self-starring is disabled")
                return

            # Update the reaction in the database with retry logic
            star_count = None
            retry_attempts = 3
            for attempt in range(retry_attempts):
                try:
                    if is_add:
                        star_count = await settings_manager.add_starboard_reaction(
                            guild.id, message.id, payload.user_id
                        )
                    else:
                        star_count = await settings_manager.remove_starboard_reaction(
                            guild.id, message.id, payload.user_id
                        )

                    # If we got a valid count, break out of the retry loop
                    if isinstance(star_count, int):
                        break

                    # If we couldn't get a valid count, try to fetch it directly
                    star_count = await settings_manager.get_starboard_reaction_count(guild.id, message.id)
                    if isinstance(star_count, int):
                        break

                except Exception as e:
                    if attempt < retry_attempts - 1:
                        log.warning(f"Error updating reaction for message {message.id}, attempt {attempt+1}/{retry_attempts}: {e}")
                        await asyncio.sleep(1)  # Wait before retrying
                    else:
                        log.error(f"Failed to update reaction for message {message.id} after {retry_attempts} attempts: {e}")
                        return

            if not isinstance(star_count, int):
                log.error(f"Could not get valid star count for message {message.id}")
                return

            log.info(f"Message {message.id} in guild {guild.id} now has {star_count} stars (action: {'add' if is_add else 'remove'})")

            # Get the threshold from settings
            threshold = settings.get('threshold', 3)

            # Check if this message is already in the starboard
            entry = None
            retry_attempts = 3
            for attempt in range(retry_attempts):
                try:
                    entry = await settings_manager.get_starboard_entry(guild.id, message.id)
                    break
                except Exception as e:
                    if attempt < retry_attempts - 1:
                        log.warning(f"Error getting starboard entry for message {message.id}, attempt {attempt+1}/{retry_attempts}: {e}")
                        await asyncio.sleep(1)  # Wait before retrying
                    else:
                        log.error(f"Failed to get starboard entry for message {message.id} after {retry_attempts} attempts: {e}")
                        # Continue with entry=None, which will create a new entry if needed

            if star_count >= threshold:
                # Message should be in starboard
                if entry:
                    # Update existing entry
                    try:
                        starboard_message = await starboard_channel.fetch_message(entry.get('starboard_message_id'))
                        await self._update_starboard_message(starboard_message, message, star_count)
                        await settings_manager.update_starboard_entry(guild.id, message.id, star_count)
                        log.info(f"Updated starboard message {starboard_message.id} for original message {message.id}")
                    except discord.NotFound:
                        # Starboard message was deleted, create a new one
                        log.warning(f"Starboard message {entry.get('starboard_message_id')} was deleted, creating a new one")
                        starboard_message = await self._create_starboard_message(starboard_channel, message, star_count)
                        if starboard_message:
                            await settings_manager.create_starboard_entry(
                                guild.id, message.id, source_channel.id,
                                starboard_message.id, message.author.id, star_count
                            )
                            log.info(f"Created new starboard message {starboard_message.id} for original message {message.id}")
                    except discord.HTTPException as e:
                        log.error(f"Error updating starboard message for {message.id}: {e}")
                else:
                    # Create new entry
                    log.info(f"Creating new starboard entry for message {message.id} with {star_count} stars")
                    starboard_message = await self._create_starboard_message(starboard_channel, message, star_count)
                    if starboard_message:
                        await settings_manager.create_starboard_entry(
                            guild.id, message.id, source_channel.id,
                            starboard_message.id, message.author.id, star_count
                        )
                        log.info(f"Created starboard message {starboard_message.id} for original message {message.id}")
            elif entry:
                # Message is below threshold but exists in starboard
                log.info(f"Message {message.id} now has {star_count} stars, below threshold of {threshold}. Removing from starboard.")
                try:
                    # Delete the starboard message if it exists
                    starboard_message = await starboard_channel.fetch_message(entry.get('starboard_message_id'))
                    await starboard_message.delete()
                    log.info(f"Deleted starboard message {entry.get('starboard_message_id')}")
                except discord.NotFound:
                    log.warning(f"Starboard message {entry.get('starboard_message_id')} already deleted")
                except discord.HTTPException as e:
                    log.error(f"Error deleting starboard message {entry.get('starboard_message_id')}: {e}")

                # Delete the entry from the database
                await settings_manager.delete_starboard_entry(guild.id, message.id)
        except Exception as e:
            log.exception(f"Unexpected error processing star reaction for message {payload.message_id}: {e}")
        finally:
            # Release the lock
            self.pending_updates.pop(message_key, None)
            log.debug(f"Released lock for message {payload.message_id} in guild {payload.guild_id}")

    async def _create_starboard_message(self, starboard_channel, message, star_count):
        """Create a new message in the starboard channel."""
        try:
            embed = self._create_starboard_embed(message, star_count)

            # Add jump link to the original message
            content = f"{self._get_star_emoji(star_count)} **{star_count}** | {message.channel.mention} | [Jump to Message]({message.jump_url})"

            # Send the message to the starboard channel
            return await starboard_channel.send(content=content, embed=embed)
        except discord.HTTPException as e:
            log.error(f"Error creating starboard message: {e}")
            return None

    async def _update_starboard_message(self, starboard_message, original_message, star_count):
        """Update an existing message in the starboard channel."""
        try:
            embed = self._create_starboard_embed(original_message, star_count)

            # Update the star count in the message content
            content = f"{self._get_star_emoji(star_count)} **{star_count}** | {original_message.channel.mention} | [Jump to Message]({original_message.jump_url})"

            # Edit the message
            await starboard_message.edit(content=content, embed=embed)
            return starboard_message
        except discord.HTTPException as e:
            log.error(f"Error updating starboard message: {e}")
            return None

    def _create_starboard_embed(self, message, star_count):
        """Create an embed for the starboard message."""
        # We're not using star_count in the embed directly, but it's passed for potential future use
        # such as changing embed color based on star count
        embed = discord.Embed(
            description=message.content,
            color=0xFFAC33,  # Gold color for stars
            timestamp=message.created_at
        )

        # Set author information
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.display_avatar.url
        )

        # Add footer with message ID for reference
        embed.set_footer(text=f"ID: {message.id}")

        # Add attachments if any
        if message.attachments:
            # If it's an image, add it to the embed
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    embed.set_image(url=attachment.url)
                    break

            # Add a field listing all attachments
            if len(message.attachments) > 1:
                attachment_list = "\n".join([f"[{a.filename}]({a.url})" for a in message.attachments])
                embed.add_field(name="Attachments", value=attachment_list, inline=False)

        return embed

    def _get_star_emoji(self, count):
        """Get the appropriate star emoji based on the count."""
        if count >= 15:
            return "🌟"  # Glowing star for 15+
        elif count >= 10:
            return "✨"  # Sparkles for 10+
        elif count >= 5:
            return "⭐"  # Star for 5+
        else:
            return "⭐"  # Regular star for < 5

    # --- Starboard Commands ---

    @commands.hybrid_group(name="starboard", description="Manage the starboard settings")
    @commands.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def starboard_group(self, ctx):
        """Commands for managing the starboard feature."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand. Use `help starboard` for more information.")

    @starboard_group.command(name="enable", description="Enable or disable the starboard")
    @app_commands.describe(enabled="Whether to enable or disable the starboard")
    async def starboard_enable(self, ctx, enabled: bool):
        """Enable or disable the starboard feature."""
        success = await settings_manager.update_starboard_settings(ctx.guild.id, enabled=enabled)

        if success:
            status = "enabled" if enabled else "disabled"
            await ctx.send(f"✅ Starboard has been {status}.")
        else:
            await ctx.send("❌ Failed to update starboard settings.")

    @starboard_group.command(name="channel", description="Set the channel for starboard posts")
    @app_commands.describe(channel="The channel to use for starboard posts")
    async def starboard_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel where starboard messages will be posted."""
        success = await settings_manager.update_starboard_settings(ctx.guild.id, starboard_channel_id=channel.id)

        if success:
            await ctx.send(f"✅ Starboard channel set to {channel.mention}.")
        else:
            await ctx.send("❌ Failed to update starboard channel.")

    @starboard_group.command(name="threshold", description="Set the minimum number of stars needed")
    @app_commands.describe(threshold="The minimum number of stars needed (1-25)")
    async def starboard_threshold(self, ctx, threshold: int):
        """Set the minimum number of stars needed for a message to appear on the starboard."""
        if threshold < 1 or threshold > 25:
            await ctx.send("❌ Threshold must be between 1 and 25.")
            return

        success = await settings_manager.update_starboard_settings(ctx.guild.id, threshold=threshold)

        if success:
            await ctx.send(f"✅ Starboard threshold set to {threshold} stars.")
        else:
            await ctx.send("❌ Failed to update starboard threshold.")

    @starboard_group.command(name="emoji", description="Set the emoji used for starring messages")
    @app_commands.describe(emoji="The emoji to use for starring messages")
    async def starboard_emoji(self, ctx, emoji: str):
        """Set the emoji that will be used for starring messages."""
        # Validate that the input is a single emoji
        if not self.emoji_pattern.fullmatch(emoji):
            await ctx.send("❌ Please provide a valid emoji.")
            return

        success = await settings_manager.update_starboard_settings(ctx.guild.id, star_emoji=emoji)

        if success:
            await ctx.send(f"✅ Starboard emoji set to {emoji}.")
        else:
            await ctx.send("❌ Failed to update starboard emoji.")

    @starboard_group.command(name="ignorebots", description="Set whether to ignore bot messages")
    @app_commands.describe(ignore="Whether to ignore messages from bots")
    async def starboard_ignorebots(self, ctx, ignore: bool):
        """Set whether messages from bots should be ignored for the starboard."""
        success = await settings_manager.update_starboard_settings(ctx.guild.id, ignore_bots=ignore)

        if success:
            status = "will be ignored" if ignore else "will be included"
            await ctx.send(f"✅ Bot messages {status} in the starboard.")
        else:
            await ctx.send("❌ Failed to update bot message handling.")

    @starboard_group.command(name="selfstar", description="Allow or disallow users to star their own messages")
    @app_commands.describe(allow="Whether to allow users to star their own messages")
    async def starboard_selfstar(self, ctx, allow: bool):
        """Set whether users can star their own messages."""
        success = await settings_manager.update_starboard_settings(ctx.guild.id, self_star=allow)

        if success:
            status = "can" if allow else "cannot"
            await ctx.send(f"✅ Users {status} star their own messages.")
        else:
            await ctx.send("❌ Failed to update self-starring setting.")

    @starboard_group.command(name="settings", description="Show current starboard settings")
    async def starboard_settings(self, ctx):
        """Display the current starboard settings."""
        settings = await settings_manager.get_starboard_settings(ctx.guild.id)

        if not settings:
            await ctx.send("❌ Failed to retrieve starboard settings.")
            return

        # Create an embed to display the settings
        embed = discord.Embed(
            title="Starboard Settings",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now()
        )

        # Add fields for each setting
        embed.add_field(name="Status", value="Enabled" if settings.get('enabled') else "Disabled", inline=True)

        channel_id = settings.get('starboard_channel_id')
        channel_mention = f"<#{channel_id}>" if channel_id else "Not set"
        embed.add_field(name="Channel", value=channel_mention, inline=True)

        embed.add_field(name="Threshold", value=str(settings.get('threshold', 3)), inline=True)
        embed.add_field(name="Emoji", value=settings.get('star_emoji', '⭐'), inline=True)
        embed.add_field(name="Ignore Bots", value="Yes" if settings.get('ignore_bots', True) else "No", inline=True)
        embed.add_field(name="Self-starring", value="Allowed" if settings.get('self_star', False) else "Not allowed", inline=True)

        await ctx.send(embed=embed)

    @starboard_group.command(name="clear", description="Clear all starboard entries")
    @commands.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def starboard_clear(self, ctx):
        """Clear all entries from the starboard."""
        # Ask for confirmation
        await ctx.send("⚠️ **Warning**: This will delete all starboard entries for this server. Are you sure? (yes/no)")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]

        try:
            # Wait for confirmation
            response = await self.bot.wait_for("message", check=check, timeout=30.0)

            if response.content.lower() != "yes":
                await ctx.send("❌ Operation cancelled.")
                return

            # Get the starboard channel
            settings = await settings_manager.get_starboard_settings(ctx.guild.id)
            if not settings or not settings.get('starboard_channel_id'):
                await ctx.send("❌ Starboard channel not set.")
                return

            starboard_channel = ctx.guild.get_channel(settings.get('starboard_channel_id'))
            if not starboard_channel:
                await ctx.send("❌ Starboard channel not found.")
                return

            # Get all entries
            entries = await settings_manager.clear_starboard_entries(ctx.guild.id)

            if not entries:
                await ctx.send("✅ Starboard cleared. No entries were found.")
                return

            # Delete all messages from the starboard channel
            status_message = await ctx.send(f"🔄 Clearing {len(entries)} entries from the starboard...")

            deleted_count = 0
            failed_count = 0

            # Convert entries to a list of dictionaries
            entries_list = [dict(entry) for entry in entries]

            # Delete messages in batches to avoid rate limits
            for entry in entries_list:
                try:
                    try:
                        message = await starboard_channel.fetch_message(entry['starboard_message_id'])
                        await message.delete()
                        deleted_count += 1
                    except discord.NotFound:
                        # Message already deleted
                        deleted_count += 1
                    except discord.HTTPException as e:
                        log.error(f"Error deleting starboard message {entry['starboard_message_id']}: {e}")
                        failed_count += 1
                except Exception as e:
                    log.error(f"Unexpected error deleting starboard message: {e}")
                    failed_count += 1

            await status_message.edit(content=f"✅ Starboard cleared. Deleted {deleted_count} messages. Failed to delete {failed_count} messages.")

        except asyncio.TimeoutError:
            await ctx.send("❌ Confirmation timed out. Operation cancelled.")
        except Exception as e:
            log.exception(f"Error clearing starboard: {e}")
            await ctx.send(f"❌ An error occurred while clearing the starboard: {str(e)}")

    @starboard_group.command(name="stats", description="Show starboard statistics")
    async def starboard_stats(self, ctx):
        """Display statistics about the starboard."""
        try:
            # Get the starboard settings
            settings = await settings_manager.get_starboard_settings(ctx.guild.id)
            if not settings:
                await ctx.send("❌ Failed to retrieve starboard settings.")
                return

            # Get the bot instance and its pg_pool
            bot_instance = get_bot_instance()
            if not bot_instance or not bot_instance.pg_pool:
                await ctx.send("❌ Database connection not available.")
                return

            # Get a connection to the database
            conn = await asyncio.wait_for(bot_instance.pg_pool.acquire(), timeout=5.0)
            try:
                # Get the total number of entries
                total_entries = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM starboard_entries
                    WHERE guild_id = $1
                    """,
                    ctx.guild.id
                )

                # Get the total number of reactions
                total_reactions = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM starboard_reactions
                    WHERE guild_id = $1
                    """,
                    ctx.guild.id
                )

                # Get the most starred message
                most_starred = await conn.fetchrow(
                    """
                    SELECT * FROM starboard_entries
                    WHERE guild_id = $1
                    ORDER BY star_count DESC
                    LIMIT 1
                    """,
                    ctx.guild.id
                )

                # Create an embed to display the statistics
                embed = discord.Embed(
                    title="Starboard Statistics",
                    color=discord.Color.gold(),
                    timestamp=datetime.datetime.now()
                )

                embed.add_field(name="Total Entries", value=str(total_entries), inline=True)
                embed.add_field(name="Total Reactions", value=str(total_reactions), inline=True)

                if most_starred:
                    most_starred_dict = dict(most_starred)
                    embed.add_field(
                        name="Most Starred Message",
                        value=f"[Jump to Message](https://discord.com/channels/{ctx.guild.id}/{most_starred_dict['original_channel_id']}/{most_starred_dict['original_message_id']})\n{most_starred_dict['star_count']} stars",
                        inline=False
                    )

                await ctx.send(embed=embed)
            finally:
                # Release the connection
                await bot_instance.pg_pool.release(conn)
        except Exception as e:
            log.exception(f"Error getting starboard statistics: {e}")
            await ctx.send(f"❌ An error occurred while getting starboard statistics: {str(e)}")

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(StarboardCog(bot))
