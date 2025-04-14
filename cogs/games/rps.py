import discord
from discord.ext import commands
import random
from discord import app_commands

async def rps(interaction: discord.Interaction, choice: app_commands.Choice[str]):
    """Play Rock-Paper-Scissors against the bot."""
    choices = ["Rock", "Paper", "Scissors"]
    bot_choice = random.choice(choices)
    user_choice = choice.value # Get value from choice

    if user_choice == bot_choice:
        result = "It's a tie!"
    elif (user_choice == "Rock" and bot_choice == "Scissors") or \
         (user_choice == "Paper" and bot_choice == "Rock") or \
         (user_choice == "Scissors" and bot_choice == "Paper"):
        result = "You win! 🎉"
    else:
        result = "You lose! 😢"

    emojis = {
        "Rock": "🪨",
        "Paper": "📄",
        "Scissors": "✂️"
    }

    await interaction.response.send_message(
        f"You chose **{user_choice}** {emojis[user_choice]}\n"
        f"I chose **{bot_choice}** {emojis[bot_choice]}\n\n"
        f"{result}"
    )
