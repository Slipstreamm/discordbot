import discord
from discord.ext import commands
from discord import app_commands

class PingCog(commands.Cog, name="Ping"):
    """Cog for ping-related commands"""

    def __init__(self, bot):
        self.bot = bot

    async def _ping_logic(self):
        """Core logic for the ping command."""
        latency = round(self.bot.latency * 1000)
        return f'Pong! Response time: {latency}ms'

    # --- Prefix Command (for backward compatibility) ---
    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Check the bot's response time."""
        response = await self._ping_logic()
        await ctx.reply(response)

    # --- Slash Command ---
    @app_commands.command(name="ping", description="Check the bot's response time")
    async def ping_slash(self, interaction: discord.Interaction):
        """Slash command for ping."""
        response = await self._ping_logic()
        await interaction.response.send_message(response)

async def setup(bot):
    await bot.add_cog(PingCog(bot))
