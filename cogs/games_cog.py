import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import asyncio
from typing import Optional, List

class CoinFlipView(ui.View):
    def __init__(self, initiator: discord.Member, opponent: discord.Member):
        super().__init__(timeout=180.0)  # 3-minute timeout
        self.initiator = initiator
        self.opponent = opponent
        self.initiator_choice: Optional[str] = None
        self.opponent_choice: Optional[str] = None
        self.result: Optional[str] = None
        self.winner: Optional[discord.Member] = None
        self.message: Optional[discord.Message] = None # To store the message for editing

        # Initial state: Initiator chooses side
        self.add_item(self.HeadsButton())
        self.add_item(self.TailsButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check who is interacting at which stage."""
        # Stage 1: Initiator chooses Heads/Tails
        if self.initiator_choice is None:
            if interaction.user.id != self.initiator.id:
                await interaction.response.send_message("Only the initiator can choose their side.", ephemeral=True)
                return False
            return True
        # Stage 2: Opponent Accepts/Declines
        else:
            if interaction.user.id != self.opponent.id:
                await interaction.response.send_message("Only the opponent can accept or decline the game.", ephemeral=True)
                return False
            return True

    async def update_view_state(self, interaction: discord.Interaction):
        """Updates the view items based on the current state."""
        self.clear_items()
        if self.initiator_choice is None: # Should not happen if called correctly, but for safety
            self.add_item(self.HeadsButton())
            self.add_item(self.TailsButton())
        elif self.result is None: # Opponent needs to accept/decline
            self.add_item(self.AcceptButton())
            self.add_item(self.DeclineButton())
        else: # Game finished, disable all (handled by disabling in callbacks)
            pass # No items needed, or keep disabled ones

        # Edit the original message
        if self.message:
            try:
                # Use interaction response to edit if available, otherwise use message.edit
                # This handles the case where the interaction is the one causing the edit
                if interaction and interaction.message and interaction.message.id == self.message.id:
                     await interaction.response.edit_message(view=self)
                else:
                     await self.message.edit(view=self)
            except discord.NotFound:
                print("CoinFlipView: Failed to edit message, likely deleted.")
            except discord.Forbidden:
                print("CoinFlipView: Missing permissions to edit message.")
            except discord.InteractionResponded:
                 # If interaction already responded (e.g. initial choice), use followup or webhook
                 try:
                     await interaction.edit_original_response(view=self)
                 except discord.HTTPException:
                     print("CoinFlipView: Failed to edit original response after InteractionResponded.")


    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound: pass # Ignore if message is gone
            except discord.Forbidden: pass # Ignore if permissions lost

    async def on_timeout(self):
        if self.message and not self.is_finished(): # Check if not already stopped
            await self.disable_all_buttons()
            timeout_msg = f"Coin flip game between {self.initiator.mention} and {self.opponent.mention} timed out."
            try:
                await self.message.edit(content=timeout_msg, view=self)
            except discord.NotFound: pass
            except discord.Forbidden: pass
        self.stop()

    # --- Button Definitions ---

    class HeadsButton(ui.Button):
        def __init__(self):
            super().__init__(label="Heads", style=discord.ButtonStyle.primary, custom_id="cf_heads")

        async def callback(self, interaction: discord.Interaction):
            view: 'CoinFlipView' = self.view
            view.initiator_choice = "Heads"
            view.opponent_choice = "Tails"
            # Update message and view for opponent
            await view.update_view_state(interaction) # Switches to Accept/Decline
            await interaction.edit_original_response( # Edit the message content *after* updating state
                content=f"{view.opponent.mention}, {view.initiator.mention} has chosen **Heads**! You get **Tails**. Do you accept?"
            )


    class TailsButton(ui.Button):
        def __init__(self):
            super().__init__(label="Tails", style=discord.ButtonStyle.primary, custom_id="cf_tails")

        async def callback(self, interaction: discord.Interaction):
            view: 'CoinFlipView' = self.view
            view.initiator_choice = "Tails"
            view.opponent_choice = "Heads"
            # Update message and view for opponent
            await view.update_view_state(interaction) # Switches to Accept/Decline
            await interaction.edit_original_response( # Edit the message content *after* updating state
                content=f"{view.opponent.mention}, {view.initiator.mention} has chosen **Tails**! You get **Heads**. Do you accept?"
            )


    class AcceptButton(ui.Button):
        def __init__(self):
            super().__init__(label="Accept", style=discord.ButtonStyle.success, custom_id="cf_accept")

        async def callback(self, interaction: discord.Interaction):
            view: 'CoinFlipView' = self.view
            # Perform the coin flip
            view.result = random.choice(["Heads", "Tails"])

            # Determine winner
            if view.result == view.initiator_choice:
                view.winner = view.initiator
            else:
                view.winner = view.opponent

            # Construct result message
            result_message = (
                f"Coin flip game between {view.initiator.mention} ({view.initiator_choice}) and {view.opponent.mention} ({view.opponent_choice}).\n\n"
                f"Flipping the coin... **{view.result}**!\n\n"
                f"🎉 **{view.winner.mention} wins!** 🎉"
            )

            await view.disable_all_buttons()
            await interaction.response.edit_message(content=result_message, view=view)
            view.stop()

    class DeclineButton(ui.Button):
        def __init__(self):
            super().__init__(label="Decline", style=discord.ButtonStyle.danger, custom_id="cf_decline")

        async def callback(self, interaction: discord.Interaction):
            view: 'CoinFlipView' = self.view
            decline_message = f"{view.opponent.mention} has declined the coin flip game from {view.initiator.mention}."
            await view.disable_all_buttons()
            await interaction.response.edit_message(content=decline_message, view=view)
            view.stop()


# --- Tic Tac Toe --- START

class TicTacToeButton(ui.Button['TicTacToeView']):
    def __init__(self, x: int, y: int):
        # Use a blank character for the initial label to avoid large buttons
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: TicTacToeView = self.view

        # Check if it's the correct player's turn
        if interaction.user != view.current_player:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return

        # Check if the spot is already taken
        if view.board[self.y][self.x] is not None:
            await interaction.response.send_message("This spot is already taken!", ephemeral=True)
            return

        # Update board state and button appearance
        view.board[self.y][self.x] = view.current_symbol
        self.label = view.current_symbol
        self.style = discord.ButtonStyle.success if view.current_symbol == 'X' else discord.ButtonStyle.danger
        self.disabled = True

        # Check for win/draw
        if view.check_win():
            view.winner = view.current_player
            await view.end_game(interaction, f"🎉 {view.winner.mention} ({view.current_symbol}) wins! 🎉")
            return
        elif view.check_draw():
            await view.end_game(interaction, "🤝 It's a draw! 🤝")
            return

        # Switch turns
        view.switch_player()
        await view.update_board_message(interaction)

class TicTacToeView(ui.View):
    def __init__(self, initiator: discord.Member, opponent: discord.Member):
        super().__init__(timeout=300.0) # 5 minute timeout
        self.initiator = initiator
        self.opponent = opponent
        self.current_player = initiator # Initiator starts as X
        self.current_symbol = 'X'
        self.board: List[List[Optional[str]]] = [[None for _ in range(3)] for _ in range(3)]
        self.winner: Optional[discord.Member] = None
        self.message: Optional[discord.Message] = None

        # Add buttons to the view
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def switch_player(self):
        if self.current_player == self.initiator:
            self.current_player = self.opponent
            self.current_symbol = 'O'
        else:
            self.current_player = self.initiator
            self.current_symbol = 'X'

    def check_win(self) -> bool:
        s = self.current_symbol
        b = self.board
        # Rows
        for row in b:
            if all(cell == s for cell in row):
                return True
        # Columns
        for col in range(3):
            if all(b[row][col] == s for row in range(3)):
                return True
        # Diagonals
        if all(b[i][i] == s for i in range(3)):
            return True
        if all(b[i][2 - i] == s for i in range(3)):
            return True
        return False

    def check_draw(self) -> bool:
        return all(cell is not None for row in self.board for cell in row)

    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    async def update_board_message(self, interaction: discord.Interaction):
        content = f"Tic Tac Toe: {self.initiator.mention} (X) vs {self.opponent.mention} (O)\n\nTurn: **{self.current_player.mention} ({self.current_symbol})**"
        # Use response.edit_message for button interactions
        await interaction.response.edit_message(content=content, view=self)

    async def end_game(self, interaction: discord.Interaction, message_content: str):
        await self.disable_all_buttons()
        # Use response.edit_message as this follows a button click
        await interaction.response.edit_message(content=message_content, view=self)
        self.stop()

    async def on_timeout(self):
        if self.message and not self.is_finished():
            await self.disable_all_buttons()
            timeout_msg = f"Tic Tac Toe game between {self.initiator.mention} and {self.opponent.mention} timed out."
            try:
                await self.message.edit(content=timeout_msg, view=self)
            except discord.NotFound: pass
            except discord.Forbidden: pass
        self.stop()

# --- Tic Tac Toe --- END

# ---Tic Tac Toe Bot View--- START

class BotTicTacToeButton(ui.Button['BotTicTacToeView']):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y
        self.position = y * 3 + x  # Convert to position index (0-8) for the TicTacToe engine

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: BotTicTacToeView = self.view
        
        # Check if it's the player's turn
        if interaction.user != view.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
            
        # Try to make the move in the game engine
        try:
            view.game.play_turn(self.position)
            self.label = 'X'  # Player is always X
            self.style = discord.ButtonStyle.success
            self.disabled = True
              # Check if game is over after player's move
            if view.game.is_game_over():
                await view.end_game(interaction)
                return
                
            # Now it's the bot's turn - defer without thinking message
            await interaction.response.defer()
            await asyncio.sleep(1)  # Brief pause to simulate bot "thinking"
            
            # Bot makes its move
            bot_move = view.game.play_turn()  # AI will automatically choose its move
            
            # Update the button for the bot's move
            bot_y, bot_x = divmod(bot_move, 3)
            for child in view.children:
                if isinstance(child, BotTicTacToeButton) and child.x == bot_x and child.y == bot_y:
                    child.label = 'O'  # Bot is always O
                    child.style = discord.ButtonStyle.danger
                    child.disabled = True
                    break
                    
            # Check if game is over after bot's move
            if view.game.is_game_over():
                await view.end_game(interaction)
                return
                
            # Update the game board for the next player's turn
            await interaction.followup.edit_message(
                message_id=view.message.id,
                content=f"Tic Tac Toe: {view.player.mention} (X) vs Bot (O) - Difficulty: {view.game.ai_difficulty.capitalize()}\n\nYour turn!",
                view=view
            )
            
        except ValueError as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class BotTicTacToeView(ui.View):
    def __init__(self, game, player: discord.Member):
        super().__init__(timeout=300.0)  # 5 minute timeout
        self.game = game  # Instance of the TicTacToe engine
        self.player = player
        self.message = None

        # Add buttons to the view (3x3 grid)
        for y in range(3):
            for x in range(3):
                self.add_item(BotTicTacToeButton(x, y))
                
    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
                
    async def end_game(self, interaction: discord.Interaction):
        await self.disable_all_buttons()
        
        winner = self.game.get_winner()
        if winner:
            if winner == 'X':  # Player wins
                content = f"🎉 {self.player.mention} wins! 🎉"
            else:  # Bot wins
                content = f"The bot ({self.game.ai_difficulty.capitalize()}) wins! Better luck next time."
        else:
            content = "It's a tie! 🤝"
            
        # Convert the board to a visually appealing format
        board_display = self.format_board()
        
        # Update the message
        try:
            await interaction.followup.edit_message(
                message_id=self.message.id,
                content=f"{content}\n\n{board_display}",
                view=self
            )
        except (discord.NotFound, discord.HTTPException):
            # Fallback for interaction timeouts
            if self.message:
                try:
                    await self.message.edit(content=f"{content}\n\n{board_display}", view=self)
                except: pass
        self.stop()
        def format_board(self) -> str:
            """Format the game board into a string representation."""
            board = self.game.get_board()
            rows = []
            for i in range(0, 9, 3):
                row = board[i:i+3]
                # Replace spaces with emoji equivalents for better visualization
                row = [cell if cell != ' ' else '⬜' for cell in row]
                row = [cell.replace('X', '❌').replace('O', '⭕') for cell in row]
                rows.append(' '.join(row))
            return '\n'.join(rows)
    
    async def on_timeout(self):
        if self.message:
            await self.disable_all_buttons()
            try:
                await self.message.edit(
                    content=f"Tic Tac Toe game for {self.player.mention} timed out.",
                    view=self
                )
            except discord.NotFound: pass
            except discord.Forbidden: pass
        self.stop()

# ---Tic Tac Toe Bot View--- END

# --- Rock Paper Scissors Challenge --- START

class RockPaperScissorsView(ui.View):
    def __init__(self, initiator: discord.Member, opponent: discord.Member):
        super().__init__(timeout=180.0)  # 3-minute timeout
        self.initiator = initiator
        self.opponent = opponent
        self.initiator_choice: Optional[str] = None
        self.opponent_choice: Optional[str] = None
        self.message: Optional[discord.Message] = None
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the person interacting is part of the game."""
        if interaction.user.id not in [self.initiator.id, self.opponent.id]:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return False
        return True
            
    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound: pass
            except discord.Forbidden: pass
    
    async def on_timeout(self):
        if self.message:
            await self.disable_all_buttons()
            timeout_msg = f"Rock Paper Scissors game between {self.initiator.mention} and {self.opponent.mention} timed out."
            try:
                await self.message.edit(content=timeout_msg, view=self)
            except discord.NotFound: pass
            except discord.Forbidden: pass
        self.stop()
    
    # Determine winner between two choices
    def get_winner(self, choice1: str, choice2: str) -> Optional[str]:
        if choice1 == choice2:
            return None  # Tie
        if (choice1 == "Rock" and choice2 == "Scissors") or \
           (choice1 == "Paper" and choice2 == "Rock") or \
           (choice1 == "Scissors" and choice2 == "Paper"):
            return "player1"
        else:
            return "player2"
    
    @ui.button(label="Rock", style=discord.ButtonStyle.primary)
    async def rock_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Rock")
    
    @ui.button(label="Paper", style=discord.ButtonStyle.success)
    async def paper_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Paper")
    
    @ui.button(label="Scissors", style=discord.ButtonStyle.danger)
    async def scissors_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Scissors")
    
    async def make_choice(self, interaction: discord.Interaction, choice: str):
        player = interaction.user
        
        # Record the choice for the appropriate player
        if player.id == self.initiator.id:
            self.initiator_choice = choice
            await interaction.response.send_message(f"You chose **{choice}**!", ephemeral=True)
        else:  # opponent
            self.opponent_choice = choice
            await interaction.response.send_message(f"You chose **{choice}**!", ephemeral=True)
        
        # Check if both players have made their choices
        if self.initiator_choice and self.opponent_choice:
            # Determine the winner
            winner_id = self.get_winner(self.initiator_choice, self.opponent_choice)
            
            if winner_id is None:
                result = "It's a tie! 🤝"
            elif winner_id == "player1":
                result = f"**{self.initiator.mention}** wins! 🎉"
            else:
                result = f"**{self.opponent.mention}** wins! 🎉"
            
            # Update the message with the results
            result_message = (
                f"**Rock Paper Scissors Results**\n"
                f"{self.initiator.mention} chose **{self.initiator_choice}**\n"
                f"{self.opponent.mention} chose **{self.opponent_choice}**\n\n"
                f"{result}"
            )
            
            await self.disable_all_buttons()
            await self.message.edit(content=result_message, view=self)
            self.stop()

# --- Rock Paper Scissors Challenge --- END

class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store instances of bot Tic-Tac-Toe games
        self.ttt_games = {}

    @app_commands.command(name="coinflipbet", description="Challenge another user to a coin flip game.")
    @app_commands.describe(
        opponent="The user you want to challenge."
    )
    async def coinflipbet(self, interaction: discord.Interaction, opponent: discord.Member):
        """Initiates a coin flip game against another user."""

        initiator = interaction.user

        # --- Input Validation ---
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot!", ephemeral=True)
            return

        # --- Start the Game ---
        view = CoinFlipView(initiator, opponent)
        initial_message = f"{initiator.mention} has challenged {opponent.mention} to a coin flip game! Choose your side:"

        # Send the initial message and store it in the view
        await interaction.response.send_message(initial_message, view=view)
        message = await interaction.original_response()
        view.message = message

    @app_commands.command(name="coinflip", description="Flip a coin and get Heads or Tails.")
    async def coinflip(self, interaction: discord.Interaction):
        """Flips a coin and returns Heads or Tails."""
        result = random.choice(["Heads", "Tails"])
        await interaction.response.send_message(f"The coin landed on **{result}**! 🪙")

    @app_commands.command(name="roll", description="Roll a dice and get a number between 1 and 6.")
    async def roll(self, interaction: discord.Interaction):
        """Rolls a dice and returns a number between 1 and 6."""
        result = random.randint(1, 6)
        await interaction.response.send_message(f"You rolled a **{result}**! 🎲")

    @app_commands.command(name="magic8ball", description="Ask the magic 8 ball a question.")
    @app_commands.describe(
        question="The question you want to ask the magic 8 ball."
    )
    async def magic8ball(self, interaction: discord.Interaction, question: str):
        """Provides a random response to a yes/no question."""
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes – definitely.", "You may rely on it.",
            "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."
        ]
        response = random.choice(responses)
        await interaction.response.send_message(f"🎱 {response}")    @app_commands.command(name="rps", description="Play Rock-Paper-Scissors against the bot.")
    @app_commands.describe(choice="Your choice: Rock, Paper, or Scissors.")
    async def rps(self, interaction: discord.Interaction, choice: str):
        """Play Rock-Paper-Scissors against the bot."""
        choices = ["Rock", "Paper", "Scissors"]
        bot_choice = random.choice(choices)
        user_choice = choice.capitalize()

        if user_choice not in choices:
            await interaction.response.send_message("Invalid choice! Please choose Rock, Paper, or Scissors.", ephemeral=True)
            return

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

        if result == "You win! 🎉":
            await interaction.response.send_message(f"{emojis[user_choice]}🤜{emojis[bot_choice]}\nYou chose **{user_choice}**, and I chose **{bot_choice}**. {result}")
        elif result == "You lose! 😢":
            await interaction.response.send_message(f"{emojis[bot_choice]}🤜{emojis[user_choice]}\nYou chose **{user_choice}**, and I chose **{bot_choice}**. {result}")
        else:
            await interaction.response.send_message(f"{emojis[user_choice]}🤝{emojis[bot_choice]}\nYou chose **{user_choice}**, and I chose **{bot_choice}**. {result}")

    @app_commands.command(name="rpschallenge", description="Challenge another user to a game of Rock-Paper-Scissors.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def rpschallenge(self, interaction: discord.Interaction, opponent: discord.Member):
        """Starts a Rock-Paper-Scissors game with another user."""
        initiator = interaction.user

        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot!", ephemeral=True)
            return

        view = RockPaperScissorsView(initiator, opponent)
        initial_message = f"Rock Paper Scissors: {initiator.mention} vs {opponent.mention}\n\nChoose your move!"
        await interaction.response.send_message(initial_message, view=view)
        message = await interaction.original_response()
        view.message = message

    @app_commands.command(name="guess", description="Guess the number I'm thinking of (1-100).")
    @app_commands.describe(guess="Your guess (1-100).")
    async def guess(self, interaction: discord.Interaction, guess: int):
        """Guess the number the bot is thinking of."""
        if not hasattr(self, "_number_to_guess"):
            self._number_to_guess = random.randint(1, 100)

        if guess < 1 or guess > 100:
            await interaction.response.send_message("Please guess a number between 1 and 100.", ephemeral=True)
            return

        if guess == self._number_to_guess:
            await interaction.response.send_message(f"🎉 Correct! The number was **{self._number_to_guess}**.")
            self._number_to_guess = random.randint(1, 100)  # Reset for the next game
        elif guess < self._number_to_guess:
            await interaction.response.send_message("Too low! Try again.")
        else:
            await interaction.response.send_message("Too high! Try again.")

    @app_commands.command(name="hangman", description="Play a game of Hangman.")
    async def hangman(self, interaction: discord.Interaction):
        """Play a game of Hangman."""
        with open("words.txt", "r") as file:
            words = [line.strip() for line in file if line.strip()] 
        word = random.choice(words)
        guessed = ["_"] * len(word)
        attempts = 6
        guessed_letters = []

        await interaction.response.send_message(f"🎮 Hangman: {' '.join(guessed)}\nAttempts left: {attempts}")

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and len(m.content) == 1

        while attempts > 0 and "_" in guessed:
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=60.0)
                guess = msg.content.lower()

                if guess in guessed_letters:
                    await msg.reply("You've already guessed that letter!")
                    continue

                guessed_letters.append(guess)

                if guess in word:
                    for i, letter in enumerate(word):
                        if letter == guess:
                            guessed[i] = guess
                    await msg.reply(f"✅ Correct! {' '.join(guessed)}")
                else:
                    attempts -= 1
                    await msg.reply(f"❌ Wrong! Attempts left: {attempts}")

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Time's up! Game over.")
                return

        if "_" not in guessed:
            await interaction.followup.send(f"🎉 You guessed the word: **{word}**!")
        else:
            await interaction.followup.send(f"💀 You ran out of attempts! The word was **{word}**.")

    @app_commands.command(name="tictactoe", description="Challenge another user to a game of Tic-Tac-Toe.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def tictactoe(self, interaction: discord.Interaction, opponent: discord.Member):
        """Starts a Tic-Tac-Toe game with another user."""
        initiator = interaction.user

        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot!", ephemeral=True)
            return

        view = TicTacToeView(initiator, opponent)
        initial_message = f"Tic Tac Toe: {initiator.mention} (X) vs {opponent.mention} (O)\n\nTurn: **{initiator.mention} (X)**"
        await interaction.response.send_message(initial_message, view=view)
        message = await interaction.original_response()
        view.message = message # Store message for timeout handling

    @app_commands.command(name="tictactoebot", description="Play a game of Tic-Tac-Toe against the bot.")
    @app_commands.describe(difficulty="Bot difficulty: random, rule, or minimax (default: minimax)")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="Random (Easy)", value="random"),
        app_commands.Choice(name="Rule-based (Medium)", value="rule"),
        app_commands.Choice(name="Minimax (Hard)", value="minimax")
    ])
    async def tictactoebot(self, interaction: discord.Interaction, difficulty: str = "minimax"):
        """Play a game of Tic-Tac-Toe against the bot."""
        import sys
        import os
        
        # Add the parent directory to sys.path if needed to import tictactoe
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent_dir not in sys.path:
            sys.path.append(parent_dir)
            
        from tictactoe import TicTacToe
        
        # Validate difficulty
        valid_difficulties = ["random", "rule", "minimax"]
        if difficulty not in valid_difficulties:
            await interaction.response.send_message(
                f"Invalid difficulty! Please choose from: {', '.join(valid_difficulties)}",
                ephemeral=True
            )
            return
        
        # Create a new game instance
        user_id = interaction.user.id
        game = TicTacToe(ai_player='O', ai_difficulty=difficulty)
        self.ttt_games[user_id] = game
        
        # Create a view for the user interface
        view = BotTicTacToeView(game, interaction.user)
        await interaction.response.send_message(
            f"Tic Tac Toe: {interaction.user.mention} (X) vs Bot (O) - Difficulty: {difficulty.capitalize()}\n\nYour turn!",
            view=view
        )
        view.message = await interaction.original_response()

    @commands.command(name="coinflipbet")
    async def coinflipbet_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """Initiates a coin flip game against another user."""
        initiator = ctx.author

        # --- Input Validation ---
        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        # --- Start the Game ---
        view = CoinFlipView(initiator, opponent)
        initial_message = f"{initiator.mention} has challenged {opponent.mention} to a coin flip game! Choose your side:"

        # Send the initial message and store it in the view
        message = await ctx.send(initial_message, view=view)
        view.message = message

    @commands.command(name="coinflip")
    async def coinflip_prefix(self, ctx: commands.Context):
        """Flips a coin and returns Heads or Tails."""
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"The coin landed on **{result}**! 🪙")

    @commands.command(name="roll")
    async def roll_prefix(self, ctx: commands.Context):
        """Rolls a dice and returns a number between 1 and 6."""
        result = random.randint(1, 6)
        await ctx.send(f"You rolled a **{result}**! 🎲")

    @commands.command(name="magic8ball")
    async def magic8ball_prefix(self, ctx: commands.Context, *, question: str):
        """Provides a random response to a yes/no question."""
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes - definitely.", "You may rely on it.",
            "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."
        ]
        response = random.choice(responses)
        await ctx.send(f"🎱 {response}")

    @commands.command(name="tictactoe")
    async def tictactoe_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """Starts a Tic-Tac-Toe game with another user."""
        initiator = ctx.author

        if opponent == initiator:
            await ctx.send("You cannot challenge yourself!")
            return
        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        view = TicTacToeView(initiator, opponent)
        initial_message = f"Tic Tac Toe: {initiator.mention} (X) vs {opponent.mention} (O)\n\nTurn: **{initiator.mention} (X)**"
        message = await ctx.send(initial_message, view=view)
        view.message = message # Store message for timeout handling

    @commands.command(name="tictactoebot")
    async def tictactoebot_prefix(self, ctx: commands.Context, difficulty: str = "minimax"):
        """Play a game of Tic-Tac-Toe against the bot."""
        valid_difficulties = ["random", "rule", "minimax"]
        if difficulty.lower() not in valid_difficulties:
            await ctx.send(f"Invalid difficulty! Please choose from: {', '.join(valid_difficulties)}")
            return
            
        import sys
        import os
        
        # Add the parent directory to sys.path if needed to import tictactoe
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent_dir not in sys.path:
            sys.path.append(parent_dir)
            
        from tictactoe import TicTacToe
        
        # Create a new game instance
        user_id = ctx.author.id
        game = TicTacToe(ai_player='O', ai_difficulty=difficulty.lower())
        self.ttt_games[user_id] = game
        
        # Create a view for the user interface
        view = BotTicTacToeView(game, ctx.author)
        message = await ctx.send(
            f"Tic Tac Toe: {ctx.author.mention} (X) vs Bot (O) - Difficulty: {difficulty.capitalize()}\n\nYour turn!",
            view=view
        )
        view.message = message

    @commands.command(name="rpschallenge")
    async def rpschallenge_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """Challenge another user to a game of Rock-Paper-Scissors."""
        initiator = ctx.author

        if opponent == initiator:
            await ctx.send("You cannot challenge yourself!")
            return
        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        view = RockPaperScissorsView(initiator, opponent)
        initial_message = f"Rock Paper Scissors: {initiator.mention} vs {opponent.mention}\n\nChoose your move!"
        message = await ctx.send(initial_message, view=view)
        view.message = message
    
    @commands.command(name="rps")
    async def rps_prefix(self, ctx: commands.Context, choice: str):
        """Play Rock-Paper-Scissors against the bot."""
        choices = ["Rock", "Paper", "Scissors"]
        bot_choice = random.choice(choices)
        user_choice = choice.capitalize()

        if user_choice not in choices:
            await ctx.send("Invalid choice! Please choose Rock, Paper, or Scissors.")
            return

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

        if result == "You win! 🎉":
            await ctx.send(f"{emojis[user_choice]}🤜{emojis[bot_choice]}\nYou chose **{user_choice}**, and I chose **{bot_choice}**. {result}")
        elif result == "You lose! 😢":
            await ctx.send(f"{emojis[bot_choice]}🤜{emojis[user_choice]}\nYou chose **{user_choice}**, and I chose **{bot_choice}**. {result}")
        else:
            await ctx.send(f"{emojis[user_choice]}🤝{emojis[bot_choice]}\nYou chose **{user_choice}**, and I chose **{bot_choice}**. {result}")

async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))
    print("GamesCog loaded successfully.")
