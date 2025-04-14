import discord
from discord.ext import commands
from discord import app_commands
import random

# --- Rock Paper Scissors (vs Bot) --- START

@app_commands.command(name="rps", description="Play Rock-Paper-Scissors against the bot.")
@app_commands.describe(choice="Your choice: Rock, Paper, or Scissors.")
@app_commands.choices(choice=[
    app_commands.Choice(name="Rock 🪨", value="Rock"),
    app_commands.Choice(name="Paper 📄", value="Paper"),
    app_commands.Choice(name="Scissors ✂️", value="Scissors")
])
async def rps_slash(interaction: discord.Interaction, choice: app_commands.Choice[str]):
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

@commands.command(name="rps")
async def rps_prefix(ctx: commands.Context, choice: str):
    """(Prefix) Play Rock-Paper-Scissors against the bot."""
    choices = ["Rock", "Paper", "Scissors"]
    bot_choice = random.choice(choices)
    user_choice = choice.capitalize()

    if user_choice not in choices:
        await ctx.send("Invalid choice! Please choose Rock, Paper, or Scissors.")
        return

    # Identical logic to slash command, just using ctx.send
    if user_choice == bot_choice:
        result = "It's a tie!"
    elif (user_choice == "Rock" and bot_choice == "Scissors") or \
         (user_choice == "Paper" and bot_choice == "Rock") or \
         (user_choice == "Scissors" and bot_choice == "Paper"):
        result = "You win! 🎉"
    else:
        result = "You lose! 😢"

    emojis = { "Rock": "🪨", "Paper": "📄", "Scissors": "✂️" }
    await ctx.send(
        f"You chose **{user_choice}** {emojis[user_choice]}\n"
        f"I chose **{bot_choice}** {emojis[bot_choice]}\n\n"
        f"{result}"
    )

# --- Rock Paper Scissors (vs Bot) --- END

# --- Setup Function ---
async def setup(bot: commands.Bot, cog: commands.Cog):
    tree = bot.tree
    tree.add_command(rps_slash, guild=cog.guild)
    bot.add_command(rps_prefix)
