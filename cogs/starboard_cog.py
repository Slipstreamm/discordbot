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
import discordbot.settings_manager as settings_manager

# Set up logging
log = logging.getLogger(__name__)

class StarboardCog(commands.Cog):
    """A cog that implements a starboard feature for highlighting popular messages."""

    def __init__(self, bot):
        self.bot = bot
        self.emoji_pattern = re.compile(r'<a?:.+?:\d+>|[\U00010000-\U0010ffff]')
        self.pending_updates = {}  # Store message IDs that are being processed to prevent race conditions

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
            return

        self.pending_updates[message_key] = True
        try:
            # Get the message
            try:
                message = await source_channel.fetch_message(payload.message_id)
            except discord.NotFound:
                return
            except discord.HTTPException as e:
                log.error(f"Error fetching message {payload.message_id}: {e}")
                return

            # Check if message is from a bot and if we should ignore bot messages
            if message.author.bot and settings.get('ignore_bots', True):
                return

            # Check if the user is starring their own message and if that's allowed
            if is_add and payload.user_id == message.author.id and not settings.get('self_star', False):
                return

            # Update the reaction in the database
            if is_add:
                star_count = await settings_manager.add_starboard_reaction(
                    guild.id, message.id, payload.user_id
                )
            else:
                star_count = await settings_manager.remove_starboard_reaction(
                    guild.id, message.id, payload.user_id
                )

            # If we couldn't get a valid count, fetch it directly
            if not isinstance(star_count, int):
                star_count = await settings_manager.get_starboard_reaction_count(guild.id, message.id)

            # Get the threshold from settings
            threshold = settings.get('threshold', 3)

            # Check if this message is already in the starboard
            entry = await settings_manager.get_starboard_entry(guild.id, message.id)

            if star_count >= threshold:
                # Message should be in starboard
                if entry:
                    # Update existing entry
                    try:
                        starboard_message = await starboard_channel.fetch_message(entry.get('starboard_message_id'))
                        await self._update_starboard_message(starboard_message, message, star_count)
                        await settings_manager.update_starboard_entry(guild.id, message.id, star_count)
                    except discord.NotFound:
                        # Starboard message was deleted, create a new one
                        starboard_message = await self._create_starboard_message(starboard_channel, message, star_count)
                        if starboard_message:
                            await settings_manager.create_starboard_entry(
                                guild.id, message.id, source_channel.id,
                                starboard_message.id, message.author.id, star_count
                            )
                    except discord.HTTPException as e:
                        log.error(f"Error updating starboard message: {e}")
                else:
                    # Create new entry
                    starboard_message = await self._create_starboard_message(starboard_channel, message, star_count)
                    if starboard_message:
                        await settings_manager.create_starboard_entry(
                            guild.id, message.id, source_channel.id,
                            starboard_message.id, message.author.id, star_count
                        )
            elif entry:
                # Message is below threshold but exists in starboard
                try:
                    # Delete the starboard message if it exists
                    starboard_message = await starboard_channel.fetch_message(entry.get('starboard_message_id'))
                    await starboard_message.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass  # Message already deleted or couldn't be deleted

                # Delete the entry from the database
                # Note: We don't have a dedicated function for this yet, but we could add one
                # For now, we'll just update the star count
                await settings_manager.update_starboard_entry(guild.id, message.id, star_count)
        finally:
            # Release the lock
            self.pending_updates.pop(message_key, None)

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

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(StarboardCog(bot))
