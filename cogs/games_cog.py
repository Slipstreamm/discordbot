import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import asyncio
from typing import Optional, List, Union
import chess
import chess.engine
import chess.pgn
import platform
import os
import io
import ast

# Import game implementations from separate files
from .games.chess_game import (
    generate_board_image, MoveInputModal, ChessView, ChessBotView,
    get_stockfish_path
)
from .games.coinflip_game import CoinFlipView
from .games.tictactoe_game import TicTacToeView, BotTicTacToeView
from .games.rps_game import RockPaperScissorsView
from .games.basic_games import roll_dice, flip_coin, magic8ball_response, play_hangman

class GamesCog(commands.Cog, name="Games"):
    """Cog for game-related commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store active bot game views to manage engine resources
        self.active_chess_bot_views = {} # Store by message ID
        self.ttt_games = {} # Store TicTacToe game instances by user ID

        # Create the main command group for this cog
        self.games_group = app_commands.Group(
            name="fun",
            description="Play various games with the bot or other users"
        )

        # Register commands
        self.register_commands()

        # Add command group to the bot's tree
        self.bot.tree.add_command(self.games_group)

    def _array_to_fen(self, board_array: List[List[str]], turn: chess.Color) -> str:
        """Converts an 8x8 array representation to a basic FEN string."""
        fen_rows = []
        for rank_idx in range(8): # Iterate ranks 0-7 (corresponds to 8-1 in FEN)
            rank_data = board_array[rank_idx]
            fen_row = ""
            empty_count = 0
            for piece in rank_data: # Iterate files a-h
                if piece == ".":
                    empty_count += 1
                else:
                    if empty_count > 0:
                        fen_row += str(empty_count)
                        empty_count = 0
                    # Validate piece character if needed, assume valid for now
                    fen_row += piece
            if empty_count > 0:
                fen_row += str(empty_count)
            fen_rows.append(fen_row)

        piece_placement = "/".join(fen_rows)
        turn_char = 'w' if turn == chess.WHITE else 'b'
        # Default castling, no en passant, 0 halfmove, 1 fullmove for simplicity from array
        fen = f"{piece_placement} {turn_char} - - 0 1"
        return fen

    def register_commands(self):
        """Register all commands for this cog"""

        # --- Dice Commands ---
        # Coinflip command
        coinflip_command = app_commands.Command(
            name="coinflip",
            description="Flip a coin and get Heads or Tails",
            callback=self.games_coinflip_callback,
            parent=self.games_group
        )
        self.games_group.add_command(coinflip_command)

        # Roll command
        roll_command = app_commands.Command(
            name="roll",
            description="Roll a dice and get a number between 1 and 6",
            callback=self.games_roll_callback,
            parent=self.games_group
        )
        self.games_group.add_command(roll_command)

        # Magic 8-ball command
        magic8ball_command = app_commands.Command(
            name="magic8ball",
            description="Ask the magic 8 ball a question",
            callback=self.games_magic8ball_callback,
            parent=self.games_group
        )
        self.games_group.add_command(magic8ball_command)

        # --- RPS Commands ---
        # RPS command
        rps_command = app_commands.Command(
            name="rps",
            description="Play Rock-Paper-Scissors against the bot",
            callback=self.games_rps_callback,
            parent=self.games_group
        )
        self.games_group.add_command(rps_command)

        # RPS Challenge command
        rpschallenge_command = app_commands.Command(
            name="rpschallenge",
            description="Challenge another user to a game of Rock-Paper-Scissors",
            callback=self.games_rpschallenge_callback,
            parent=self.games_group
        )
        self.games_group.add_command(rpschallenge_command)

        # --- Other Game Commands ---
        # Guess command
        guess_command = app_commands.Command(
            name="guess",
            description="Guess the number I'm thinking of (1-100)",
            callback=self.games_guess_callback,
            parent=self.games_group
        )
        self.games_group.add_command(guess_command)

        # Hangman command
        hangman_command = app_commands.Command(
            name="hangman",
            description="Play a game of Hangman",
            callback=self.games_hangman_callback,
            parent=self.games_group
        )
        self.games_group.add_command(hangman_command)

        # --- TicTacToe Commands ---
        # TicTacToe command
        tictactoe_command = app_commands.Command(
            name="tictactoe",
            description="Challenge another user to a game of Tic-Tac-Toe",
            callback=self.games_tictactoe_callback,
            parent=self.games_group
        )
        self.games_group.add_command(tictactoe_command)

        # TicTacToe Bot command
        tictactoebot_command = app_commands.Command(
            name="tictactoebot",
            description="Play a game of Tic-Tac-Toe against the bot",
            callback=self.games_tictactoebot_callback,
            parent=self.games_group
        )
        self.games_group.add_command(tictactoebot_command)

        # --- Chess Commands ---
        # Chess command
        chess_command = app_commands.Command(
            name="chess",
            description="Challenge another user to a game of chess",
            callback=self.games_chess_callback,
            parent=self.games_group
        )
        self.games_group.add_command(chess_command)

        # Chess Bot command
        chessbot_command = app_commands.Command(
            name="chessbot",
            description="Play chess against the bot",
            callback=self.games_chessbot_callback,
            parent=self.games_group
        )
        self.games_group.add_command(chessbot_command)

        # Load Chess command
        loadchess_command = app_commands.Command(
            name="loadchess",
            description="Load a chess game from FEN, PGN, or array representation",
            callback=self.games_loadchess_callback,
            parent=self.games_group
        )
        self.games_group.add_command(loadchess_command)

    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        print("Unloading GamesCog, closing active chess engines...")
        # Create a copy of the dictionary items to avoid runtime errors during iteration
        views_to_stop = list(self.active_chess_bot_views.values())
        for view in views_to_stop:
            await view.stop_engine()
            view.stop() # Stop the view itself
        self.active_chess_bot_views.clear()
        print("GamesCog unloaded.")

    # --- Command Callbacks ---
    # Dice group callbacks
    async def games_coinflip_callback(self, interaction: discord.Interaction):
        """Callback for /games dice coinflip command"""
        result = flip_coin()
        await interaction.response.send_message(f"The coin landed on **{result}**! 🪙")

    async def games_roll_callback(self, interaction: discord.Interaction):
        """Callback for /games dice roll command"""
        result = roll_dice()
        await interaction.response.send_message(f"You rolled a **{result}**! 🎲")

    async def games_magic8ball_callback(self, interaction: discord.Interaction, question: str = None):
        """Callback for /games dice magic8ball command"""
        response = magic8ball_response()
        await interaction.response.send_message(f"🎱 {response}")

    # Games group callbacks
    async def games_rps_callback(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        """Callback for /games rps command"""
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

    async def games_rpschallenge_callback(self, interaction: discord.Interaction, opponent: discord.Member):
        """Callback for /games rpschallenge command"""
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

    async def games_guess_callback(self, interaction: discord.Interaction, guess: int):
        """Callback for /games guess command"""
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

    async def games_hangman_callback(self, interaction: discord.Interaction):
        """Callback for /games hangman command"""
        await play_hangman(self.bot, interaction.channel, interaction.user)

    # TicTacToe group callbacks
    async def games_tictactoe_callback(self, interaction: discord.Interaction, opponent: discord.Member):
        """Callback for /games tictactoe play command"""
        initiator = interaction.user

        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot! Use `/games tictactoe bot` instead.", ephemeral=True)
            return

        view = TicTacToeView(initiator, opponent)
        initial_message = f"Tic Tac Toe: {initiator.mention} (X) vs {opponent.mention} (O)\n\nTurn: **{initiator.mention} (X)**"
        await interaction.response.send_message(initial_message, view=view)
        message = await interaction.original_response()
        view.message = message # Store message for timeout handling

    async def games_tictactoebot_callback(self, interaction: discord.Interaction, difficulty: app_commands.Choice[str] = None):
        """Callback for /games tictactoe bot command"""
        # Use default if no choice is made (discord.py handles default value assignment)
        difficulty_value = difficulty.value if difficulty else "minimax"

        # Ensure tictactoe module is importable
        try:
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.append(parent_dir)
            from tictactoe import TicTacToe # Assuming tictactoe.py is in the parent directory
        except ImportError:
            await interaction.response.send_message("Error: TicTacToe game engine module not found.", ephemeral=True)
            return
        except Exception as e:
             await interaction.response.send_message(f"Error importing TicTacToe module: {e}", ephemeral=True)
             return

        # Create a new game instance
        try:
            game = TicTacToe(ai_player='O', ai_difficulty=difficulty_value)
        except Exception as e:
             await interaction.response.send_message(f"Error initializing TicTacToe game: {e}", ephemeral=True)
             return

        # Create a view for the user interface
        view = BotTicTacToeView(game, interaction.user)
        await interaction.response.send_message(
            f"Tic Tac Toe: {interaction.user.mention} (X) vs Bot (O) - Difficulty: {difficulty_value.capitalize()}\n\nYour turn!",
            view=view
        )
        view.message = await interaction.original_response()

    # Chess group callbacks
    async def games_chess_callback(self, interaction: discord.Interaction, opponent: discord.Member):
        """Callback for /games chess play command"""
        initiator = interaction.user

        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot! Use `/games chess bot` instead.", ephemeral=True)
            return

        # Initiator is white, opponent is black
        view = ChessView(initiator, opponent)
        initial_status = f"Turn: **{initiator.mention}** (White)"
        initial_message = f"Chess: {initiator.mention} (White) vs {opponent.mention} (Black)\n\n{initial_status}"
        board_image = generate_board_image(view.board) # Generate initial board image

        await interaction.response.send_message(initial_message, file=board_image, view=view)
        message = await interaction.original_response()
        view.message = message

        # Send initial DMs
        asyncio.create_task(view._send_or_update_dm(view.white_player))
        asyncio.create_task(view._send_or_update_dm(view.black_player))

    async def games_chessbot_callback(self, interaction: discord.Interaction, color: app_commands.Choice[str] = None, variant: app_commands.Choice[str] = None, skill_level: int = 10, think_time: float = 1.0):
        """Callback for /games chess bot command"""
        player = interaction.user
        player_color_str = color.value if color else "white"
        variant_str = variant.value if variant else "standard"
        player_color = chess.WHITE if player_color_str == "white" else chess.BLACK

        # Validate inputs
        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))

        # Check if variant is supported (currently standard and chess960)
        supported_variants = ["standard", "chess960"]
        if variant_str not in supported_variants:
            await interaction.response.send_message(f"Sorry, the variant '{variant_str}' is not currently supported. Choose from: {', '.join(supported_variants)}", ephemeral=True)
            return

        # Defer response as engine start might take a moment
        await interaction.response.defer()

        view = ChessBotView(player, player_color, variant_str, skill_level, think_time)

        # Start the engine asynchronously
        # Store interaction temporarily for potential error reporting during init
        view._interaction = interaction
        await view.start_engine()
        del view._interaction # Remove temporary attribute

        if view.engine is None or view.is_finished(): # Check if engine failed or view stopped during init
             # Error message should have been sent by start_engine or view stopped itself
             # Ensure we don't try to send another response if already handled
             # No need to send another message here, start_engine handles it.
             print("ChessBotView: Engine failed to start, stopping command execution.")
             return # Stop if engine failed

        # Determine initial message based on who moves first
        initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
        initial_message_content = view.get_board_message(initial_status_prefix)
        board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

        # Send the initial game state using followup
        message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
        view.message = message
        self.active_chess_bot_views[message.id] = view # Track the view

        # Send initial DM to player
        asyncio.create_task(view._send_or_update_dm())

        # If bot moves first (player chose black), trigger its move
        if player_color == chess.BLACK:
            # Don't await this, let it run in the background
            asyncio.create_task(view.make_bot_move())

    async def games_loadchess_callback(self, interaction: discord.Interaction, state: str, turn: Optional[app_commands.Choice[str]] = None, opponent: Optional[discord.Member] = None, color: Optional[app_commands.Choice[str]] = None, skill_level: int = 10, think_time: float = 1.0):
        """Callback for /games chess load command"""
        await interaction.response.defer()
        initiator = interaction.user
        board = None
        load_error = None
        loaded_pgn_game = None # To store the loaded PGN game object if parsed

        # --- Input Validation ---
        if not opponent and not color:
            await interaction.followup.send("The 'color' parameter is required when playing against the bot.", ephemeral=True)
            return

        # --- Parsing Logic ---
        state_trimmed = state.strip()

        # 1. Try parsing as PGN
        if state_trimmed.startswith("[Event") or ('.' in state_trimmed and ('O-O' in state_trimmed or 'x' in state_trimmed or state_trimmed[0].isdigit())):
            try:
                pgn_io = io.StringIO(state_trimmed)
                loaded_pgn_game = chess.pgn.read_game(pgn_io)
                if loaded_pgn_game is None:
                    raise ValueError("Could not parse PGN data.")
                # Get the board state from the end of the main line
                board = loaded_pgn_game.end().board()
                print("[Debug] Parsed as PGN.")
            except Exception as e:
                load_error = f"Could not parse as PGN: {e}. Trying other formats."
                print(f"[Debug] PGN parsing failed: {e}")
                loaded_pgn_game = None # Reset if PGN parsing failed

        # 2. Try parsing as FEN (if not already parsed as PGN)
        if board is None and '/' in state_trimmed and (' w ' in state_trimmed or ' b ' in state_trimmed):
            try:
                board = chess.Board(fen=state_trimmed)
                print(f"[Debug] Parsed as FEN: {state_trimmed}")
            except ValueError as e:
                load_error = f"Invalid FEN string: {e}. Trying array format."
                print(f"[Error] FEN parsing failed: {e}")
            except Exception as e:
                load_error = f"Unexpected FEN parsing error: {e}. Trying array format."
                print(f"[Error] Unexpected FEN parsing error: {e}")

        # 3. Try parsing as Array (if not parsed as PGN or FEN)
        if board is None:
            try:
                # Check if it looks like a list before eval
                if not state_trimmed.startswith('[') or not state_trimmed.endswith(']'):
                     raise ValueError("Input does not look like a list array.")

                board_array = ast.literal_eval(state_trimmed)
                print("[Debug] Attempting to parse as array...")

                if not isinstance(board_array, list) or len(board_array) != 8 or \
                   not all(isinstance(row, list) and len(row) == 8 for row in board_array):
                    raise ValueError("Invalid array structure. Must be 8x8 list.")

                if not turn:
                    load_error = "The 'turn' parameter is required when providing a board array."
                else:
                    turn_color = chess.WHITE if turn.value == "white" else chess.BLACK
                    fen = self._array_to_fen(board_array, turn_color)
                    print(f"[Debug] Converted array to FEN: {fen}")
                    board = chess.Board(fen=fen)

            except (ValueError, SyntaxError, TypeError) as e:
                # If PGN/FEN failed, this is the final error message
                load_error = f"Invalid state format. Could not parse as PGN, FEN, or Python list array. Error: {e}"
                print(f"[Error] Array parsing failed: {e}")
            except Exception as e:
                load_error = f"Error parsing array state: {e}"
                print(f"[Error] Unexpected array parsing error: {e}")

        # --- Final Check and Error Handling ---
        if board is None:
            final_error = load_error or "Failed to load board state from the provided input."
            await interaction.followup.send(final_error, ephemeral=True)
            return

        # --- Game Setup ---
        if opponent:
            # Player vs Player
            if opponent == initiator:
                await interaction.followup.send("You cannot challenge yourself!", ephemeral=True)
                return
            if opponent.bot:
                await interaction.followup.send("You cannot challenge a bot! Use `/games chess bot` or load without opponent.", ephemeral=True)
                return

            white_player = initiator if board.turn == chess.WHITE else opponent
            black_player = opponent if board.turn == chess.WHITE else initiator

            view = ChessView(white_player, black_player, board=board) # Pass loaded board
            # If loaded from PGN, set the game object in the view
            if loaded_pgn_game:
                view.game_pgn = loaded_pgn_game
                view.pgn_node = loaded_pgn_game.end() # Start from the end node

            current_player_mention = white_player.mention if board.turn == chess.WHITE else black_player.mention
            turn_color_name = "White" if board.turn == chess.WHITE else "Black"
            initial_status = f"Turn: **{current_player_mention}** ({turn_color_name})"
            if board.is_check(): initial_status += " **Check!**"
            initial_message = f"Loaded Chess Game: {white_player.mention} (White) vs {black_player.mention} (Black)\n\n{initial_status}"
            perspective_white = (board.turn == chess.WHITE)
            board_image = generate_board_image(view.board, perspective_white=perspective_white)

            message = await interaction.followup.send(initial_message, file=board_image, view=view, wait=True)
            view.message = message

            # Send initial DMs
            asyncio.create_task(view._send_or_update_dm(view.white_player))
            asyncio.create_task(view._send_or_update_dm(view.black_player))

        else:
            # Player vs Bot
            player = initiator
            # Color is now required, checked at the start
            player_color = chess.WHITE if color.value == "white" else chess.BLACK

            skill_level = max(0, min(20, skill_level))
            think_time = max(0.1, min(5.0, think_time))
            variant_str = "chess960" if board.chess960 else "standard"

            view = ChessBotView(player, player_color, variant_str, skill_level, think_time, board=board) # Pass loaded board
            # If loaded from PGN, set the game object in the view
            if loaded_pgn_game:
                view.game_pgn = loaded_pgn_game
                view.pgn_node = loaded_pgn_game.end() # Start from the end node

            view._interaction = interaction # For error reporting during start
            await view.start_engine()
            if hasattr(view, '_interaction'): del view._interaction

    # --- Legacy Commands (kept for backward compatibility) ---
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
        initial_message = f"{initiator.mention} has challenged {opponent.mention} to a coin flip game! {initiator.mention}, choose your side:"

        # Send the initial message and store it in the view
        await interaction.response.send_message(initial_message, view=view)
        message = await interaction.original_response()
        view.message = message

    @app_commands.command(name="rps", description="Play Rock-Paper-Scissors against the bot.")
    @app_commands.describe(choice="Your choice: Rock, Paper, or Scissors.")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock 🪨", value="Rock"),
        app_commands.Choice(name="Paper 📄", value="Paper"),
        app_commands.Choice(name="Scissors ✂️", value="Scissors")
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
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

    @app_commands.command(name="hangman", description="Play a game of Hangman.")
    async def hangman(self, interaction: discord.Interaction):
        """Play a game of Hangman."""
        await play_hangman(self.bot, interaction.channel, interaction.user)

    @app_commands.command(name="tictactoe", description="Challenge another user to a game of Tic-Tac-Toe.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def tictactoe(self, interaction: discord.Interaction, opponent: discord.Member):
        """Starts a Tic-Tac-Toe game with another user."""
        initiator = interaction.user

        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot! Use `/tictactoebot` instead.", ephemeral=True)
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
    async def tictactoebot(self, interaction: discord.Interaction, difficulty: app_commands.Choice[str] = None):
        """Play a game of Tic-Tac-Toe against the bot."""
        # Use default if no choice is made (discord.py handles default value assignment)
        difficulty_value = difficulty.value if difficulty else "minimax"

        # Ensure tictactoe module is importable
        try:
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.append(parent_dir)
            from tictactoe import TicTacToe # Assuming tictactoe.py is in the parent directory
        except ImportError:
            await interaction.response.send_message("Error: TicTacToe game engine module not found.", ephemeral=True)
            return
        except Exception as e:
             await interaction.response.send_message(f"Error importing TicTacToe module: {e}", ephemeral=True)
             return

        # Create a new game instance
        try:
            game = TicTacToe(ai_player='O', ai_difficulty=difficulty_value)
        except Exception as e:
             await interaction.response.send_message(f"Error initializing TicTacToe game: {e}", ephemeral=True)
             return

        # Create a view for the user interface
        view = BotTicTacToeView(game, interaction.user)
        await interaction.response.send_message(
            f"Tic Tac Toe: {interaction.user.mention} (X) vs Bot (O) - Difficulty: {difficulty_value.capitalize()}\n\nYour turn!",
            view=view
        )
        view.message = await interaction.original_response()

    @app_commands.command(name="chess", description="Challenge another user to a game of chess.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def chess(self, interaction: discord.Interaction, opponent: discord.Member):
        """Start a game of chess with another user."""
        initiator = interaction.user

        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot! Use `/chessbot` instead.", ephemeral=True)
            return

        # Initiator is white, opponent is black
        view = ChessView(initiator, opponent)
        initial_status = f"Turn: **{initiator.mention}** (White)"
        initial_message = f"Chess: {initiator.mention} (White) vs {opponent.mention} (Black)\n\n{initial_status}"
        board_image = generate_board_image(view.board) # Generate initial board image

        await interaction.response.send_message(initial_message, file=board_image, view=view)
        message = await interaction.original_response()
        view.message = message

        # Send initial DMs
        asyncio.create_task(view._send_or_update_dm(view.white_player))
        asyncio.create_task(view._send_or_update_dm(view.black_player))

    @app_commands.command(name="chessbot", description="Play chess against the bot.")
    @app_commands.describe(
        color="Choose your color (default: White).",
        variant="Choose the chess variant (default: Standard).",
        skill_level="Bot skill level (0=Easy - 20=Hard, default: 10).",
        think_time="Bot thinking time per move in seconds (0.1 - 5.0, default: 1.0)."
    )
    @app_commands.choices(
        color=[
            app_commands.Choice(name="White", value="white"),
            app_commands.Choice(name="Black", value="black"),
        ],
        variant=[
            app_commands.Choice(name="Standard", value="standard"),
            app_commands.Choice(name="Chess960 (Fischer Random)", value="chess960"),
            # Add more variants here as supported
        ]
    )
    async def chessbot(self, interaction: discord.Interaction, color: app_commands.Choice[str] = None, variant: app_commands.Choice[str] = None, skill_level: int = 10, think_time: float = 1.0):
        """Starts a chess game against the Stockfish engine."""
        player = interaction.user
        player_color_str = color.value if color else "white"
        variant_str = variant.value if variant else "standard"
        player_color = chess.WHITE if player_color_str == "white" else chess.BLACK

        # Validate inputs
        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))

        # Check if variant is supported (currently standard and chess960)
        supported_variants = ["standard", "chess960"]
        if variant_str not in supported_variants:
            await interaction.response.send_message(f"Sorry, the variant '{variant_str}' is not currently supported. Choose from: {', '.join(supported_variants)}", ephemeral=True)
            return

        # Defer response as engine start might take a moment
        await interaction.response.defer()

        view = ChessBotView(player, player_color, variant_str, skill_level, think_time)

        # Start the engine asynchronously
        # Store interaction temporarily for potential error reporting during init
        view._interaction = interaction
        await view.start_engine()
        del view._interaction # Remove temporary attribute

        if view.engine is None or view.is_finished(): # Check if engine failed or view stopped during init
             # Error message should have been sent by start_engine or view stopped itself
             # Ensure we don't try to send another response if already handled
             # No need to send another message here, start_engine handles it.
             print("ChessBotView: Engine failed to start, stopping command execution.")
             return # Stop if engine failed

        # Determine initial message based on who moves first
        initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
        initial_message_content = view.get_board_message(initial_status_prefix)
        board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

        # Send the initial game state using followup
        message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
        view.message = message
        self.active_chess_bot_views[message.id] = view # Track the view

        # Send initial DM to player
        asyncio.create_task(view._send_or_update_dm())

        # If bot moves first (player chose black), trigger its move
        if player_color == chess.BLACK:
            # Don't await this, let it run in the background
            asyncio.create_task(view.make_bot_move())

    @app_commands.command(name="loadchess", description="Load a chess game from FEN, PGN, or array representation.")
    @app_commands.describe(
        state="FEN string, PGN string, or board array (e.g., [['r',...],...]).",
        turn="Whose turn? ('white' or 'black'). Required only for array state.",
        opponent="Challenge a user (optional, defaults to playing the bot).",
        color="Your color vs bot (White/Black). Required if playing vs bot.",
        skill_level="Bot skill level (0-20, default: 10).",
        think_time="Bot think time (0.1-5.0, default: 1.0)."
    )
    @app_commands.choices(
        turn=[app_commands.Choice(name="White", value="white"), app_commands.Choice(name="Black", value="black")],
        color=[app_commands.Choice(name="White", value="white"), app_commands.Choice(name="Black", value="black")]
    )
    async def loadchess(self, interaction: discord.Interaction,
                        state: str,
                        turn: Optional[app_commands.Choice[str]] = None,
                        opponent: Optional[discord.Member] = None,
                        color: Optional[app_commands.Choice[str]] = None, # Now required for bot games
                        skill_level: int = 10,
                        think_time: float = 1.0):
        """Loads a chess game state (FEN, PGN, Array) and starts a view."""
        await interaction.response.defer()
        initiator = interaction.user
        board = None
        load_error = None
        loaded_pgn_game = None # To store the loaded PGN game object if parsed

        # --- Input Validation ---
        if not opponent and not color:
            await interaction.followup.send("The 'color' parameter is required when playing against the bot.", ephemeral=True)
            return

        # --- Parsing Logic ---
        state_trimmed = state.strip()

        # 1. Try parsing as PGN
        if state_trimmed.startswith("[Event") or ('.' in state_trimmed and ('O-O' in state_trimmed or 'x' in state_trimmed or state_trimmed[0].isdigit())):
            try:
                pgn_io = io.StringIO(state_trimmed)
                loaded_pgn_game = chess.pgn.read_game(pgn_io)
                if loaded_pgn_game is None:
                    raise ValueError("Could not parse PGN data.")
                # Get the board state from the end of the main line
                board = loaded_pgn_game.end().board()
                print("[Debug] Parsed as PGN.")
            except Exception as e:
                load_error = f"Could not parse as PGN: {e}. Trying other formats."
                print(f"[Debug] PGN parsing failed: {e}")
                loaded_pgn_game = None # Reset if PGN parsing failed

        # 2. Try parsing as FEN (if not already parsed as PGN)
        if board is None and '/' in state_trimmed and (' w ' in state_trimmed or ' b ' in state_trimmed):
            try:
                board = chess.Board(fen=state_trimmed)
                print(f"[Debug] Parsed as FEN: {state_trimmed}")
            except ValueError as e:
                load_error = f"Invalid FEN string: {e}. Trying array format."
                print(f"[Error] FEN parsing failed: {e}")
            except Exception as e:
                load_error = f"Unexpected FEN parsing error: {e}. Trying array format."
                print(f"[Error] Unexpected FEN parsing error: {e}")

        # 3. Try parsing as Array (if not parsed as PGN or FEN)
        if board is None:
            try:
                # Check if it looks like a list before eval
                if not state_trimmed.startswith('[') or not state_trimmed.endswith(']'):
                     raise ValueError("Input does not look like a list array.")

                board_array = ast.literal_eval(state_trimmed)
                print("[Debug] Attempting to parse as array...")

                if not isinstance(board_array, list) or len(board_array) != 8 or \
                   not all(isinstance(row, list) and len(row) == 8 for row in board_array):
                    raise ValueError("Invalid array structure. Must be 8x8 list.")

                if not turn:
                    load_error = "The 'turn' parameter is required when providing a board array."
                else:
                    turn_color = chess.WHITE if turn.value == "white" else chess.BLACK
                    fen = self._array_to_fen(board_array, turn_color)
                    print(f"[Debug] Converted array to FEN: {fen}")
                    board = chess.Board(fen=fen)

            except (ValueError, SyntaxError, TypeError) as e:
                # If PGN/FEN failed, this is the final error message
                load_error = f"Invalid state format. Could not parse as PGN, FEN, or Python list array. Error: {e}"
                print(f"[Error] Array parsing failed: {e}")
            except Exception as e:
                load_error = f"Error parsing array state: {e}"
                print(f"[Error] Unexpected array parsing error: {e}")

        # --- Final Check and Error Handling ---
        if board is None:
            final_error = load_error or "Failed to load board state from the provided input."
            await interaction.followup.send(final_error, ephemeral=True)
            return

        # --- Game Setup ---
        if opponent:
            # Player vs Player
            if opponent == initiator:
                await interaction.followup.send("You cannot challenge yourself!", ephemeral=True)
                return
            if opponent.bot:
                await interaction.followup.send("You cannot challenge a bot! Use `/chessbot` or load without opponent.", ephemeral=True)
                return

            white_player = initiator if board.turn == chess.WHITE else opponent
            black_player = opponent if board.turn == chess.WHITE else initiator

            view = ChessView(white_player, black_player, board=board) # Pass loaded board
            # If loaded from PGN, set the game object in the view
            if loaded_pgn_game:
                view.game_pgn = loaded_pgn_game
                view.pgn_node = loaded_pgn_game.end() # Start from the end node

            current_player_mention = white_player.mention if board.turn == chess.WHITE else black_player.mention
            turn_color_name = "White" if board.turn == chess.WHITE else "Black"
            initial_status = f"Turn: **{current_player_mention}** ({turn_color_name})"
            if board.is_check(): initial_status += " **Check!**"
            initial_message = f"Loaded Chess Game: {white_player.mention} (White) vs {black_player.mention} (Black)\n\n{initial_status}"
            perspective_white = (board.turn == chess.WHITE)
            board_image = generate_board_image(view.board, perspective_white=perspective_white)

            message = await interaction.followup.send(initial_message, file=board_image, view=view, wait=True)
            view.message = message

            # Send initial DMs
            asyncio.create_task(view._send_or_update_dm(view.white_player))
            asyncio.create_task(view._send_or_update_dm(view.black_player))

        else:
            # Player vs Bot
            player = initiator
            # Color is now required, checked at the start
            player_color = chess.WHITE if color.value == "white" else chess.BLACK

            skill_level = max(0, min(20, skill_level))
            think_time = max(0.1, min(5.0, think_time))
            variant_str = "chess960" if board.chess960 else "standard"

            view = ChessBotView(player, player_color, variant_str, skill_level, think_time, board=board) # Pass loaded board
            # If loaded from PGN, set the game object in the view
            if loaded_pgn_game:
                view.game_pgn = loaded_pgn_game
                view.pgn_node = loaded_pgn_game.end() # Start from the end node

            view._interaction = interaction # For error reporting during start
            await view.start_engine()
            if hasattr(view, '_interaction'): del view._interaction

            if view.engine is None or view.is_finished():
                print("ChessBotView (Load): Engine failed to start, stopping command execution.")
                return

            status_prefix = "Your turn." if board.turn == player_color else "Bot is thinking..."
            initial_message_content = view.get_board_message(status_prefix)
            board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

            message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
            view.message = message
            self.active_chess_bot_views[message.id] = view

            # Send initial DM to player
            asyncio.create_task(view._send_or_update_dm())

            if board.turn != player_color:
                asyncio.create_task(view.make_bot_move())


    # --- Prefix Commands (Legacy Support) ---

    @commands.command(name="coinflipbet", add_to_app_commands=False)
    async def coinflipbet_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Challenge another user to a coin flip game."""
        initiator = ctx.author

        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        view = CoinFlipView(initiator, opponent)
        initial_message = f"{initiator.mention} has challenged {opponent.mention} to a coin flip game! {initiator.mention}, choose your side:"
        message = await ctx.send(initial_message, view=view)
        view.message = message

    @commands.command(name="coinflip", add_to_app_commands=False)
    async def coinflip_prefix(self, ctx: commands.Context):
        """(Prefix) Flip a coin."""
        result = flip_coin()
        await ctx.send(f"The coin landed on **{result}**! 🪙")

    @commands.command(name="roll", add_to_app_commands=False)
    async def roll_prefix(self, ctx: commands.Context):
        """(Prefix) Roll a dice."""
        result = roll_dice()
        await ctx.send(f"You rolled a **{result}**! 🎲")

    @commands.command(name="magic8ball", add_to_app_commands=False)
    async def magic8ball_prefix(self, ctx: commands.Context, *, question: str):
        """(Prefix) Ask the magic 8 ball."""
        response = magic8ball_response()
        await ctx.send(f"🎱 {response}")

    @commands.command(name="tictactoe", add_to_app_commands=False)
    async def tictactoe_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Challenge another user to Tic-Tac-Toe."""
        initiator = ctx.author

        if opponent.bot:
            await ctx.send("You cannot challenge a bot! Use `!tictactoebot` instead.")
            return

        view = TicTacToeView(initiator, opponent)
        initial_message = f"Tic Tac Toe: {initiator.mention} (X) vs {opponent.mention} (O)\n\nTurn: **{initiator.mention} (X)**"
        message = await ctx.send(initial_message, view=view)
        view.message = message

    @commands.command(name="tictactoebot", add_to_app_commands=False)
    async def tictactoebot_prefix(self, ctx: commands.Context, difficulty: str = "minimax"):
        """(Prefix) Play Tic-Tac-Toe against the bot."""
        difficulty_value = difficulty.lower()
        valid_difficulties = ["random", "rule", "minimax"]
        if difficulty_value not in valid_difficulties:
            await ctx.send(f"Invalid difficulty! Choose from: {', '.join(valid_difficulties)}")
            return

        try:
            import sys
            import os
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if parent_dir not in sys.path:
                sys.path.append(parent_dir)
            from tictactoe import TicTacToe
        except ImportError:
            await ctx.send("Error: TicTacToe game engine module not found.")
            return
        except Exception as e:
             await ctx.send(f"Error importing TicTacToe module: {e}")
             return

        try:
            game = TicTacToe(ai_player='O', ai_difficulty=difficulty_value)
        except Exception as e:
             await ctx.send(f"Error initializing TicTacToe game: {e}")
             return

        view = BotTicTacToeView(game, ctx.author)
        message = await ctx.send(
            f"Tic Tac Toe: {ctx.author.mention} (X) vs Bot (O) - Difficulty: {difficulty_value.capitalize()}\n\nYour turn!",
            view=view
        )
        view.message = message

    @commands.command(name="rpschallenge", add_to_app_commands=False)
    async def rpschallenge_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Challenge another user to Rock-Paper-Scissors."""
        initiator = ctx.author

        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        view = RockPaperScissorsView(initiator, opponent)
        initial_message = f"Rock Paper Scissors: {initiator.mention} vs {opponent.mention}\n\nChoose your move!"
        message = await ctx.send(initial_message, view=view)
        view.message = message

    @commands.command(name="rps", add_to_app_commands=False)
    async def rps_prefix(self, ctx: commands.Context, choice: str):
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

    @commands.command(name="chess", add_to_app_commands=False)
    async def chess_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Start a game of chess with another user."""
        initiator = ctx.author

        if opponent.bot:
            await ctx.send("You cannot challenge a bot! Use `!chessbot` instead.")
            return

        view = ChessView(initiator, opponent)
        initial_status = f"Turn: **{initiator.mention}** (White)"
        initial_message = f"Chess: {initiator.mention} (White) vs {opponent.mention} (Black)\n\n{initial_status}"
        board_image = generate_board_image(view.board)

        message = await ctx.send(initial_message, file=board_image, view=view)
        view.message = message

        # Send initial DMs
        asyncio.create_task(view._send_or_update_dm(view.white_player))
        asyncio.create_task(view._send_or_update_dm(view.black_player))

    @commands.command(name="hangman", add_to_app_commands=False)
    async def hangman_prefix(self, ctx: commands.Context):
        """(Prefix) Play a game of Hangman."""
        await play_hangman(self.bot, ctx.channel, ctx.author)

    @commands.command(name="guess", add_to_app_commands=False)
    async def guess_prefix(self, ctx: commands.Context, guess: int):
        """(Prefix) Guess a number between 1 and 100."""
        number_to_guess = random.randint(1, 100)

        if guess < 1 or guess > 100:
            await ctx.send("Please guess a number between 1 and 100.")
            return

        if guess == number_to_guess:
            await ctx.send(f"🎉 Correct! The number was **{number_to_guess}**.")
        elif guess < number_to_guess:
            await ctx.send(f"Too low! The number was {number_to_guess}.")
        else:
            await ctx.send(f"Too high! The number was {number_to_guess}.")

async def setup(bot: commands.Bot):
    """Set up the GamesCog with the bot."""
    print("Setting up GamesCog...")
    cog = GamesCog(bot)
    await bot.add_cog(cog)
    print(f"GamesCog setup complete with command group: {[cmd.name for cmd in bot.tree.get_commands() if cmd.name == 'games']}")
    print(f"Available commands: {[cmd.name for cmd in cog.games_group.walk_commands() if isinstance(cmd, app_commands.Command)]}")
