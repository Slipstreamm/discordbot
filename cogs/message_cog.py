import discord
from discord.ext import commands
from discord import app_commands

class MessageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Hardcoded message with {target} placeholder
        self.message_template = """
        {target} - Your legs are pulled apart from behind, the sudden movement causing you to stumble forward. As your balance falters, a hand shoots out to grab your hips, holding you in place.

With your body restrained, a finger begins to dance along the waistband of your pants, teasing and taunting until it finally hooks into the elasticized seam. The fabric is slowly peeled back, exposing your bare skin to the cool night air.

As the hand continues its downward journey, your breath catches in your throat. You try to move, but the grip on your hips is too tight, holding you firmly in place.

Your pants are slowly and deliberately removed, leaving you feeling exposed and vulnerable. The sensation is both thrilling and terrifying as a presence looms over you, the only sound being the faint rustling of fabric as your clothes are discarded.
        """

    # Helper method for the message logic
    async def _message_logic(self, target):
        """Core logic for the message command."""
        # Replace {target} with the mentioned user
        return self.message_template.format(target=target)

    # --- Prefix Command ---
    @commands.command(name="molest")
    async def molest(self, ctx: commands.Context, member: discord.Member):
        """Send a hardcoded message to the mentioned user."""
        response = await self._message_logic(member.mention)
        await ctx.reply(response)

    # --- Slash Command ---
    @app_commands.command(name="molest", description="Send a hardcoded message to the mentioned user")
    @app_commands.describe(
        member="The user to send the message to"
    )
    async def molest_slash(self, interaction: discord.Interaction, member: discord.Member):
        """Slash command version of message."""
        response = await self._message_logic(member.mention)
        await interaction.response.send_message(response)

async def setup(bot: commands.Bot):
    await bot.add_cog(MessageCog(bot))
