import discord
from discord.ext import commands
from discord import app_commands

class RoleplayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("RoleplayCog initialized!")

    async def _backshots_logic(self, sender_mention, recipient_mention):
        """Core logic for the backshots command."""
        # Format the message with sender and recipient mentions
        message = f"*{sender_mention} giving {recipient_mention} BACKSHOTS*\n{recipient_mention}: w-wait.. not in front of people-!\n{sender_mention}: \"shhh, it's okay, let them watch... 𝐥𝐞𝐭 𝐭𝐡𝐞𝐦 𝐤𝐧𝐨𝐰 𝐲𝐨𝐮'𝐫𝐞 𝐦𝐢𝐧𝐞...\""
        return message

    # --- Prefix Command ---
    @commands.command(name="backshots")
    async def backshots(self, ctx: commands.Context, sender: discord.Member, recipient: discord.Member):
        """Send a roleplay message about giving backshots between two mentioned users."""
        response = await self._backshots_logic(sender.mention, recipient.mention)
        await ctx.send(response)

    # --- Slash Command ---
    @app_commands.command(name="backshots", description="Send a roleplay message about giving backshots between two mentioned users")
    @app_commands.describe(
        sender="The user giving backshots",
        recipient="The user receiving backshots"
    )
    async def backshots_slash(self, interaction: discord.Interaction, sender: discord.Member, recipient: discord.Member):
        """Slash command version of backshots."""
        response = await self._backshots_logic(sender.mention, recipient.mention)
        await interaction.response.send_message(response)

async def setup(bot: commands.Bot):
    await bot.add_cog(RoleplayCog(bot))
