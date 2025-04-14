import discord
from discord.ext import commands
import random

async def guess(interaction: discord.Interaction, guess: int):
    """Guess the number I'm thinking of (1-100)."""
    # Simple implementation: generate number per guess (no state needed)
    number_to_guess = random.randint(1, 100)

    if guess < 1 or guess > 100:
        await interaction.response.send_message("Please guess a number between 1 and 100.", ephemeral=True)
        return

    if guess == number_to_guess:
        await interaction.response.send_message(f"🎉 Correct! The number was **{number_to_guess}**.")
    elif guess < number_to_guess:
        await interaction.response.send_message(f"Too low! The number was {number_to_guess}.")
    else:
        await interaction.response.send_message(f"Too high! The number was {number_to_guess}.")
