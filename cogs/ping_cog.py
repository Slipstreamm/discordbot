import discord
from discord.ext import commands
from discord import app_commands

class PingCog(commands.Cog, name="Ping"):
    """Cog for ping-related commands"""

    def __init__(self, bot):
        self.bot = bot

        # Create the main command group for this cog
        self.ping_group = app_commands.Group(
            name="ping",
            description="Check the bot's response time"
        )

        # Register commands
        self.register_commands()

        # Add command group to the bot's tree
        self.bot.tree.add_command(self.ping_group)

    def register_commands(self):
        """Register all commands for this cog"""
        # Check command
        check_command = app_commands.Command(
            name="check",
            description="Check the bot's response time",
            callback=self.ping_check_callback,
            parent=self.ping_group
        )
        self.ping_group.add_command(check_command)

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

    # --- Slash Command Callbacks ---
    async def ping_check_callback(self, interaction: discord.Interaction):
        """Callback for /ping check command"""
        response = await self._ping_logic()
        await interaction.response.send_message(response)

async def setup(bot):
    await bot.add_cog(PingCog(bot))
