import discord
from discord.ext import commands
from discord import app_commands
import random

class ModerationCog(commands.Cog):
    """Fake moderation commands that don't actually perform any actions."""

    def __init__(self, bot):
        self.bot = bot

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

    # --- Ban Commands ---
    @commands.command(name="ban")
    async def ban(self, ctx: commands.Context, member: discord.Member = None, duration: str = None, *, reason: str = None):
        """Pretends to ban a member from the server."""
        if not member:
            await ctx.reply("Please specify a member to ban.")
            return

        response = await self._fake_moderation_response("ban", member.mention, reason, duration)
        await ctx.reply(response)

    @app_commands.command(name="ban", description="Pretends to ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        duration="The duration of the ban (e.g., '1d', '7d')",
        reason="The reason for the ban"
    )
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        """Slash command version of ban."""
        response = await self._fake_moderation_response("ban", member.mention, reason, duration)
        await interaction.response.send_message(response)

    # --- Kick Commands ---
    @commands.command(name="kick")
    async def kick(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        """Pretends to kick a member from the server."""
        if not member:
            await ctx.reply("Please specify a member to kick.")
            return

        response = await self._fake_moderation_response("kick", member.mention, reason)
        await ctx.reply(response)

    @app_commands.command(name="kick", description="Pretends to kick a member from the server")
    @app_commands.describe(
        member="The member to kick",
        reason="The reason for the kick"
    )
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Slash command version of kick."""
        response = await self._fake_moderation_response("kick", member.mention, reason)
        await interaction.response.send_message(response)

    # --- Mute Commands ---
    @commands.command(name="mute")
    async def mute(self, ctx: commands.Context, member: discord.Member = None, duration: str = None, *, reason: str = None):
        """Pretends to mute a member in the server."""
        if not member:
            await ctx.reply("Please specify a member to mute.")
            return

        response = await self._fake_moderation_response("mute", member.mention, reason, duration)
        await ctx.reply(response)

    @app_commands.command(name="mute", description="Pretends to mute a member in the server")
    @app_commands.describe(
        member="The member to mute",
        duration="The duration of the mute (e.g., '1h', '30m')",
        reason="The reason for the mute"
    )
    async def mute_slash(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        """Slash command version of mute."""
        response = await self._fake_moderation_response("mute", member.mention, reason, duration)
        await interaction.response.send_message(response)

    # --- Timeout Commands ---
    @commands.command(name="timeout")
    async def timeout(self, ctx: commands.Context, member: discord.Member = None, duration: str = None, *, reason: str = None):
        """Pretends to timeout a member in the server."""
        if not member:
            await ctx.reply("Please specify a member to timeout.")
            return

        response = await self._fake_moderation_response("timeout", member.mention, reason, duration)
        await ctx.reply(response)

    @app_commands.command(name="timeout", description="Pretends to timeout a member in the server")
    @app_commands.describe(
        member="The member to timeout",
        duration="The duration of the timeout (e.g., '1h', '30m')",
        reason="The reason for the timeout"
    )
    async def timeout_slash(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        """Slash command version of timeout."""
        response = await self._fake_moderation_response("timeout", member.mention, reason, duration)
        await interaction.response.send_message(response)

    # --- Warn Commands ---
    @commands.command(name="warn")
    async def warn(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        """Pretends to warn a member in the server."""
        if not member:
            await ctx.reply("Please specify a member to warn.")
            return

        response = await self._fake_moderation_response("warn", member.mention, reason)
        await ctx.reply(response)

    @app_commands.command(name="warn", description="Pretends to warn a member in the server")
    @app_commands.describe(
        member="The member to warn",
        reason="The reason for the warning"
    )
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Slash command version of warn."""
        response = await self._fake_moderation_response("warn", member.mention, reason)
        await interaction.response.send_message(response)

    # --- Unban Commands ---
    @commands.command(name="unban")
    async def unban(self, ctx: commands.Context, user: str = None, *, reason: str = None):
        """Pretends to unban a user from the server."""
        if not user:
            await ctx.reply("Please specify a user to unban.")
            return

        # Since we can't mention unbanned users, we'll just use the name
        response = await self._fake_moderation_response("unban", user, reason)
        await ctx.reply(response)

    @app_commands.command(name="unban", description="Pretends to unban a user from the server")
    @app_commands.describe(
        user="The user to unban (username or ID)",
        reason="The reason for the unban"
    )
    async def unban_slash(self, interaction: discord.Interaction, user: str, reason: str = None):
        """Slash command version of unban."""
        response = await self._fake_moderation_response("unban", user, reason)
        await interaction.response.send_message(response)

    # --- Unmute Commands ---
    @commands.command(name="unmute")
    async def unmute(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        """Pretends to unmute a member in the server."""
        if not member:
            await ctx.reply("Please specify a member to unmute.")
            return

        response = await self._fake_moderation_response("unmute", member.mention, reason)
        await ctx.reply(response)

    @app_commands.command(name="unmute", description="Pretends to unmute a member in the server")
    @app_commands.describe(
        member="The member to unmute",
        reason="The reason for the unmute"
    )
    async def unmute_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Slash command version of unmute."""
        response = await self._fake_moderation_response("unmute", member.mention, reason)
        await interaction.response.send_message(response)

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
