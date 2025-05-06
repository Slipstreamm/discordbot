import discord
from discord.ext import commands
from discord import app_commands
import random

class FakeModerationCog(commands.Cog):
    """Fake moderation commands that don't actually perform any actions."""

    def __init__(self, bot):
        self.bot = bot

        # Create the main command group for this cog
        self.fakemod_group = app_commands.Group(
            name="fakemod",
            description="Fake moderation commands that don't actually perform any actions"
        )

        # Register commands
        self.register_commands()

        # Add command group to the bot's tree
        self.bot.tree.add_command(self.fakemod_group)

    # Helper method for generating responses
    async def _fake_moderation_response(self, action, target, reason=None, duration=None):
        """Generate a fake moderation response."""
        responses = {
            "ban": [
                f"🔨 **Banned {target}**{f' for {duration}' if duration else ''}! Reason: {reason or 'No reason provided'}",
                f"👋 {target} has been banned from the server{f' for {duration}' if duration else ''}. Reason: {reason or 'No reason provided'}",
                f"🚫 {target} is now banned{f' for {duration}' if duration else ''}. Reason: {reason or 'No reason provided'}"
            ],
            "kick": [
                f"👢 **Kicked {target}**! Reason: {reason or 'No reason provided'}",
                f"👋 {target} has been kicked from the server. Reason: {reason or 'No reason provided'}",
                f"🚪 {target} has been shown the door. Reason: {reason or 'No reason provided'}"
            ],
            "mute": [
                f"🔇 **Muted {target}**{f' for {duration}' if duration else ''}! Reason: {reason or 'No reason provided'}",
                f"🤐 {target} has been muted{f' for {duration}' if duration else ''}. Reason: {reason or 'No reason provided'}",
                f"📵 {target} can no longer speak{f' for {duration}' if duration else ''}. Reason: {reason or 'No reason provided'}"
            ],
            "timeout": [
                f"⏰ **Timed out {target}** for {duration or 'some time'}! Reason: {reason or 'No reason provided'}",
                f"⏳ {target} has been put in timeout for {duration or 'some time'}. Reason: {reason or 'No reason provided'}",
                f"🕒 {target} is now in timeout for {duration or 'some time'}. Reason: {reason or 'No reason provided'}"
            ],
            "warn": [
                f"⚠️ **Warned {target}**! Reason: {reason or 'No reason provided'}",
                f"📝 {target} has been warned. Reason: {reason or 'No reason provided'}",
                f"🚨 Warning issued to {target}. Reason: {reason or 'No reason provided'}"
            ],
            "unban": [
                f"🔓 **Unbanned {target}**! Reason: {reason or 'No reason provided'}",
                f"🎊 {target} has been unbanned. Reason: {reason or 'No reason provided'}",
                f"🔄 {target} is now allowed back in the server. Reason: {reason or 'No reason provided'}"
            ],
            "unmute": [
                f"🔊 **Unmuted {target}**! Reason: {reason or 'No reason provided'}",
                f"🗣️ {target} can speak again. Reason: {reason or 'No reason provided'}",
                f"📢 {target} has been unmuted. Reason: {reason or 'No reason provided'}"
            ]
        }

        return random.choice(responses.get(action, [f"Action performed on {target}"]))

    def register_commands(self):
        """Register all commands for this cog"""

        # --- Ban Command ---
        ban_command = app_commands.Command(
            name="ban",
            description="Pretends to ban a member from the server",
            callback=self.fakemod_ban_callback,
            parent=self.fakemod_group
        )
        app_commands.describe(
            member="The member to pretend to ban",
            duration="The fake duration of the ban (e.g., '1d', '7d')",
            reason="The fake reason for the ban"
        )(ban_command)
        self.fakemod_group.add_command(ban_command)

        # --- Unban Command ---
        unban_command = app_commands.Command(
            name="unban",
            description="Pretends to unban a user from the server",
            callback=self.fakemod_unban_callback,
            parent=self.fakemod_group
        )
        app_commands.describe(
            user="The user to pretend to unban (username or ID)",
            reason="The fake reason for the unban"
        )(unban_command)
        self.fakemod_group.add_command(unban_command)

        # --- Kick Command ---
        kick_command = app_commands.Command(
            name="kick",
            description="Pretends to kick a member from the server",
            callback=self.fakemod_kick_callback,
            parent=self.fakemod_group
        )
        app_commands.describe(
            member="The member to pretend to kick",
            reason="The fake reason for the kick"
        )(kick_command)
        self.fakemod_group.add_command(kick_command)

        # --- Mute Command ---
        mute_command = app_commands.Command(
            name="mute",
            description="Pretends to mute a member in the server",
            callback=self.fakemod_mute_callback,
            parent=self.fakemod_group
        )
        app_commands.describe(
            member="The member to pretend to mute",
            duration="The fake duration of the mute (e.g., '1h', '30m')",
            reason="The fake reason for the mute"
        )(mute_command)
        self.fakemod_group.add_command(mute_command)

        # --- Unmute Command ---
        unmute_command = app_commands.Command(
            name="unmute",
            description="Pretends to unmute a member in the server",
            callback=self.fakemod_unmute_callback,
            parent=self.fakemod_group
        )
        app_commands.describe(
            member="The member to pretend to unmute",
            reason="The fake reason for the unmute"
        )(unmute_command)
        self.fakemod_group.add_command(unmute_command)

        # --- Timeout Command ---
        timeout_command = app_commands.Command(
            name="timeout",
            description="Pretends to timeout a member in the server",
            callback=self.fakemod_timeout_callback,
            parent=self.fakemod_group
        )
        app_commands.describe(
            member="The member to pretend to timeout",
            duration="The fake duration of the timeout (e.g., '1h', '30m')",
            reason="The fake reason for the timeout"
        )(timeout_command)
        self.fakemod_group.add_command(timeout_command)

        # --- Warn Command ---
        warn_command = app_commands.Command(
            name="warn",
            description="Pretends to warn a member in the server",
            callback=self.fakemod_warn_callback,
            parent=self.fakemod_group
        )
        app_commands.describe(
            member="The member to pretend to warn",
            reason="The fake reason for the warning"
        )(warn_command)
        self.fakemod_group.add_command(warn_command)

    # --- Command Callbacks ---

    async def fakemod_ban_callback(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        """Pretends to ban a member from the server."""
        response = await self._fake_moderation_response("ban", member.mention, reason, duration)
        await interaction.response.send_message(response)

    async def fakemod_unban_callback(self, interaction: discord.Interaction, user: str, reason: str = None):
        """Pretends to unban a user from the server."""
        response = await self._fake_moderation_response("unban", user, reason)
        await interaction.response.send_message(response)

    async def fakemod_kick_callback(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Pretends to kick a member from the server."""
        response = await self._fake_moderation_response("kick", member.mention, reason)
        await interaction.response.send_message(response)

    async def fakemod_mute_callback(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        """Pretends to mute a member in the server."""
        response = await self._fake_moderation_response("mute", member.mention, reason, duration)
        await interaction.response.send_message(response)

    async def fakemod_unmute_callback(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Pretends to unmute a member in the server."""
        response = await self._fake_moderation_response("unmute", member.mention, reason)
        await interaction.response.send_message(response)

    async def fakemod_timeout_callback(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        """Pretends to timeout a member in the server."""
        response = await self._fake_moderation_response("timeout", member.mention, reason, duration)
        await interaction.response.send_message(response)

    async def fakemod_warn_callback(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Pretends to warn a member in the server."""
        response = await self._fake_moderation_response("warn", member.mention, reason)
        await interaction.response.send_message(response)

    # --- Legacy Command Handlers (for prefix commands) ---

    @commands.command(name="ban")
    async def ban(self, ctx: commands.Context, member: discord.Member = None, duration: str = None, *, reason: str = None):
        """Pretends to ban a member from the server."""
        if not member:
            await ctx.reply("Please specify a member to ban.")
            return

        response = await self._fake_moderation_response("ban", member.mention, reason, duration)
        await ctx.reply(response)

    @commands.command(name="kick")
    async def kick(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        """Pretends to kick a member from the server."""
        if not member:
            await ctx.reply("Please specify a member to kick.")
            return

        response = await self._fake_moderation_response("kick", member.mention, reason)
        await ctx.reply(response)

    @commands.command(name="mute")
    async def mute(self, ctx: commands.Context, member: discord.Member = None, duration: str = None, *, reason: str = None):
        """Pretends to mute a member in the server. Can be used by replying to a message."""
        # Check if this is a reply to a message and no member was specified
        if not member and ctx.message.reference:
            # Get the message being replied to
            replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            member = replied_msg.author

            # Don't allow muting the bot itself
            if member.id == self.bot.user.id:
                await ctx.reply("❌ I cannot mute myself.")
                return
        elif not member:
            await ctx.reply("Please specify a member to mute or reply to their message.")
            return

        response = await self._fake_moderation_response("mute", member.mention, reason, duration)
        await ctx.reply(response)

    @commands.command(name="faketimeout", aliases=["fto"]) # Renamed command and added alias
    async def fake_timeout(self, ctx: commands.Context, member: discord.Member = None, duration: str = None, *, reason: str = None): # Renamed function
        """Pretends to timeout a member in the server. Can be used by replying to a message."""
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
            await ctx.reply("Please specify a member to timeout or reply to their message.")
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

        response = await self._fake_moderation_response("timeout", member.mention, reason, duration)
        await ctx.reply(response)

    @commands.command(name="warn")
    async def warn(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        """Pretends to warn a member in the server."""
        if not member:
            await ctx.reply("Please specify a member to warn.")
            return

        response = await self._fake_moderation_response("warn", member.mention, reason)
        await ctx.reply(response)

    @commands.command(name="unban")
    async def unban(self, ctx: commands.Context, user: str = None, *, reason: str = None):
        """Pretends to unban a user from the server."""
        if not user:
            await ctx.reply("Please specify a user to unban.")
            return

        # Since we can't mention unbanned users, we'll just use the name
        response = await self._fake_moderation_response("unban", user, reason)
        await ctx.reply(response)

    @commands.command(name="unmute")
    async def unmute(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        """Pretends to unmute a member in the server."""
        if not member:
            await ctx.reply("Please specify a member to unmute.")
            return

        response = await self._fake_moderation_response("unmute", member.mention, reason)
        await ctx.reply(response)

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

async def setup(bot: commands.Bot):
    await bot.add_cog(FakeModerationCog(bot))
