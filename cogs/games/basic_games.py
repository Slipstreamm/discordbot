import discord
import random
import asyncio
from typing import List

# Simple utility functions for basic games

def roll_dice() -> int:
    """Roll a dice and return a number between 1 and 6."""
    return random.randint(1, 6)

def flip_coin() -> str:
    """Flip a coin and return 'Heads' or 'Tails'."""
    return random.choice(["Heads", "Tails"])

def magic8ball_response() -> str:
    """Return a random Magic 8 Ball response."""
    responses = [
        "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes – definitely.", "You may rely on it.",
        "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."
    ]
    return random.choice(responses)

async def play_hangman(bot, channel, user, words_file_path: str = "words.txt") -> None:
    """
    Play a game of Hangman in the specified channel.
    
    Args:
        bot: The Discord bot instance
        channel: The channel to play in
        user: The user who initiated the game
        words_file_path: Path to the file containing words for the game
    """
    try:
        with open(words_file_path, "r") as file:
            words = [line.strip().lower() for line in file if line.strip() and len(line.strip()) > 3]
        if not words:
            await channel.send("Word list is empty or not found.")
            return
        word = random.choice(words)
    except FileNotFoundError:
        await channel.send(f"`{words_file_path}` not found. Cannot start Hangman.")
        return

    guessed = ["_"] * len(word)
    attempts = 6
    guessed_letters = set()

    def format_hangman_message(attempts_left, current_guessed, letters_tried):
        stages = [ # Hangman stages (simple text version)
            "```\n +---+\n |   |\n O   |\n/|\\  |\n/ \\  |\n     |\n=======\n```", # 0 attempts left
            "```\n +---+\n |   |\n O   |\n/|\\  |\n/    |\n     |\n=======\n```", # 1 attempt left
            "```\n +---+\n |   |\n O   |\n/|\\  |\n     |\n     |\n=======\n```", # 2 attempts left
            "```\n +---+\n |   |\n O   |\n/|   |\n     |\n     |\n=======\n```", # 3 attempts left
            "```\n +---+\n |   |\n O   |\n |   |\n     |\n     |\n=======\n```", # 4 attempts left
            "```\n +---+\n |   |\n O   |\n     |\n     |\n     |\n=======\n```", # 5 attempts left
            "```\n +---+\n |   |\n     |\n     |\n     |\n     |\n=======\n```"  # 6 attempts left
        ]
        stage_index = max(0, min(attempts_left, 6)) # Clamp index
        guessed_str = ' '.join(current_guessed)
        tried_str = ', '.join(sorted(list(letters_tried))) if letters_tried else "None"
        return f"{stages[stage_index]}\nWord: `{guessed_str}`\nAttempts left: {attempts_left}\nGuessed letters: {tried_str}\n\nGuess a letter!"

    initial_msg_content = format_hangman_message(attempts, guessed, guessed_letters)
    game_message = await channel.send(initial_msg_content)

    def check(m):
        # Check if message is from the original user, in the same channel, and is a single letter
        return m.author == user and m.channel == channel and len(m.content) == 1 and m.content.isalpha()

    while attempts > 0 and "_" in guessed:
        try:
            msg = await bot.wait_for("message", check=check, timeout=120.0) # 2 min timeout per guess
            guess = msg.content.lower()

            # Delete the user's guess message for cleaner chat
            try:
                await msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass # Ignore if delete fails

            if guess in guessed_letters:
                feedback = "You already guessed that letter!"
            else:
                guessed_letters.add(guess)
                if guess in word:
                    feedback = "✅ Correct!"
                    for i, letter in enumerate(word):
                        if letter == guess:
                            guessed[i] = guess
                else:
                    attempts -= 1
                    feedback = f"❌ Wrong!"

            # Check for win/loss after processing guess
            if "_" not in guessed:
                final_message = f"🎉 You guessed the word: **{word}**!"
                await game_message.edit(content=final_message)
                return # End game on win
            elif attempts == 0:
                final_message = f"💀 You ran out of attempts! The word was **{word}**."
                await game_message.edit(content=format_hangman_message(0, guessed, guessed_letters) + "\n" + final_message)
                return # End game on loss

            # Update the game message with new state and feedback
            updated_content = format_hangman_message(attempts, guessed, guessed_letters) + f"\n({feedback})"
            await game_message.edit(content=updated_content)

        except asyncio.TimeoutError:
            timeout_message = f"⏰ Time's up! The word was **{word}**."
            await game_message.edit(content=format_hangman_message(attempts, guessed, guessed_letters) + "\n" + timeout_message)
            return # End game on timeout
