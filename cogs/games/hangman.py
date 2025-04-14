import discord
from discord.ext import commands
import random
import asyncio

async def hangman(interaction: discord.Interaction):
    """Play a game of Hangman."""
    # Basic implementation - needs improvement for multi-player or persistent state
    try:
        with open("words.txt", "r") as file:
            words = [line.strip().lower() for line in file if line.strip() and len(line.strip()) > 3] # Ensure words are lowercase and reasonable length
        if not words:
             await interaction.response.send_message("Word list is empty or not found.", ephemeral=True)
             return
        word = random.choice(words)
    except FileNotFoundError:
         await interaction.response.send_message("`words.txt` not found. Cannot start Hangman.", ephemeral=True)
         return

    guessed = ["_"] * len(word)
    attempts = 6
    guessed_letters = set()
    user = interaction.user

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
    await interaction.response.send_message(initial_msg_content)
    game_message = await interaction.original_response()

    def check(m):
        # Check if message is from the original user, in the same channel, and is a single letter
        return m.author == user and m.channel == interaction.channel and len(m.content) == 1 and m.content.isalpha()

    while attempts > 0 and "_" in guessed:
        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=120.0) # 2 min timeout per guess
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
                await game_message.edit(content=final_message, view=None) # Remove buttons if any were planned
                return # End game on win
            elif attempts == 0:
                final_message = f"💀 You ran out of attempts! The word was **{word}**."
                await game_message.edit(content=format_hangman_message(0, guessed, guessed_letters) + "\n" + final_message, view=None)
                return # End game on loss

            # Update the game message with new state and feedback
            updated_content = format_hangman_message(attempts, guessed, guessed_letters) + f"\n({feedback})"
            await game_message.edit(content=updated_content)

        except asyncio.TimeoutError:
            timeout_message = f"⏰ Time's up! The word was **{word}**."
            await game_message.edit(content=format_hangman_message(attempts, guessed, guessed_letters) + "\n" + timeout_message, view=None)
            return # End game on timeout
