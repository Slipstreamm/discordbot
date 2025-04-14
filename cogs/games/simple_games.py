import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import os

# --- Simple Games ---

# --- Roll ---
@app_commands.command(name="roll", description="Roll a dice and get a number between 1 and 6.")
async def roll_slash(interaction: discord.Interaction):
    """Rolls a dice and returns a number between 1 and 6."""
    result = random.randint(1, 6)
    await interaction.response.send_message(f"You rolled a **{result}**! 🎲")

@commands.command(name="roll")
async def roll_prefix(ctx: commands.Context):
    """(Prefix) Roll a dice."""
    result = random.randint(1, 6)
    await ctx.send(f"You rolled a **{result}**! 🎲")

# --- Magic 8 Ball ---
@app_commands.command(name="magic8ball", description="Ask the magic 8 ball a question.")
@app_commands.describe(
    question="The question you want to ask the magic 8 ball."
)
async def magic8ball_slash(interaction: discord.Interaction, question: str):
    """Provides a random response to a yes/no question."""
    responses = [
        "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes – definitely.", "You may rely on it.",
        "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."
    ]
    response = random.choice(responses)
    await interaction.response.send_message(f"🎱 {response}")

@commands.command(name="magic8ball")
async def magic8ball_prefix(ctx: commands.Context, *, question: str):
    """(Prefix) Ask the magic 8 ball."""
    responses = [
        "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes – definitely.", "You may rely on it.",
        "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."
    ]
    response = random.choice(responses)
    await ctx.send(f"🎱 {response}")

# --- Guess the Number ---
@app_commands.command(name="guess", description="Guess the number I'm thinking of (1-100).")
@app_commands.describe(guess="Your guess (1-100).")
async def guess_slash(interaction: discord.Interaction, guess: int):
    """Guess the number the bot is thinking of."""
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

# No prefix command for guess was present in the original code.

# --- Hangman ---
# Note: Hangman requires the bot instance (`self.bot`) for `wait_for`.
# It's better implemented as a method within the Cog or requires passing the bot instance.
# For simplicity in separation, we'll define the command structure here,
# but the implementation will need adjustment in the main cog file.

@app_commands.command(name="hangman", description="Play a game of Hangman.")
async def hangman_slash(interaction: discord.Interaction):
    """Play a game of Hangman."""
    # Implementation will be handled in the main GamesCog class
    # This is just a placeholder registration
    cog = interaction.client.get_cog('GamesCog')
    if cog:
        await cog.hangman_game(interaction) # Delegate to cog method
    else:
        await interaction.response.send_message("Error: GamesCog not found.", ephemeral=True)

# No prefix command for hangman was present in the original code.


# --- Setup Function ---
async def setup(bot: commands.Bot, cog: commands.Cog):
    tree = bot.tree
    # Add slash commands
    tree.add_command(roll_slash, guild=cog.guild)
    tree.add_command(magic8ball_slash, guild=cog.guild)
    tree.add_command(guess_slash, guild=cog.guild)
    tree.add_command(hangman_slash, guild=cog.guild)

    # Add prefix commands
    bot.add_command(roll_prefix)
    bot.add_command(magic8ball_prefix)
    # No prefix commands for guess or hangman in original
