import discord
from discord.ext import commands
import random

async def roll(interaction: discord.Interaction):
    """Rolls a dice and returns a number between 1 and 6."""
    result = random.randint(1, 6)
    await interaction.response.send_message(f"You rolled a **{result}**! 🎲")
