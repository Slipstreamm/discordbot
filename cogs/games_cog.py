import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import asyncio
from typing import Optional, List, Union, Dict # Added Dict
import chess
import chess.pgn # Import PGN library
import os
from PIL import Image, ImageDraw, ImageFont # Added Pillow imports
import io # Added io import
import ast

# Import chess utilities and views
from .games.chess_utils import generate_board_image, MoveInputModal
from .games.chess_pvp import ChessView
from .games.chess_bot import ChessBotView, get_stockfish_path # Import necessary items

# Note: Other game views (CoinFlip, RPS, TTT) are likely used by commands in simple_games.py or other cogs.

class GamesCog(commands.Cog):
    """Cog for handling chess games (PvP and PvBot)."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store active bot game views to manage engine resources and cleanup
        self.active_chess_bot_views: Dict[int, ChessBotView] = {} # Store by message ID

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
                    fen_row += piece
            if empty_count > 0:
                fen_row += str(empty_count)
            fen_rows.append(fen_row)

        piece_placement = "/".join(fen_rows)
        turn_char = 'w' if turn == chess.WHITE else 'b'
        # Default castling, no en passant, 0 halfmove, 1 fullmove for simplicity from array
        fen = f"{piece_placement} {turn_char} - - 0 1"
        return fen

    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        print("Unloading GamesCog, closing active chess engines...")
        # Create a copy of the dictionary items to avoid runtime errors during iteration
        views_to_stop = list(self.active_chess_bot_views.values())
        for view in views_to_stop:
            # Ensure it's a ChessBotView and has the stop_engine method
            if isinstance(view, ChessBotView) and hasattr(view, 'stop_engine'):
                try:
                    await view.stop_engine()
                except Exception as e:
                    print(f"Error stopping engine for view {view}: {e}")
            # Stop the view itself regardless (handles timeouts etc.)
            if hasattr(view, 'stop'):
                view.stop()
        self.active_chess_bot_views.clear()
        print("GamesCog unloaded.")

    # Hangman game logic removed - should be in simple_games.py

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
        ]
    )
    async def chessbot(self, interaction: discord.Interaction, color: Optional[app_commands.Choice[str]] = None, variant: Optional[app_commands.Choice[str]] = None, skill_level: int = 10, think_time: float = 1.0):
        """Starts a chess game against the Stockfish engine."""
        player = interaction.user
        player_color_str = color.value if color else "white"
        variant_str = variant.value if variant else "standard"
        player_color = chess.WHITE if player_color_str == "white" else chess.BLACK

        # Validate inputs
        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))

        supported_variants = ["standard", "chess960"]
        if variant_str not in supported_variants:
            await interaction.response.send_message(f"Sorry, the variant '{variant_str}' is not currently supported. Choose from: {', '.join(supported_variants)}", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            view = ChessBotView(player, player_color, variant_str, skill_level, think_time)

            # Store interaction temporarily for potential error reporting during init
            view._interaction = interaction
            await view.start_engine()
            if hasattr(view, '_interaction'): del view._interaction # Remove temporary attribute

            if view.engine is None or view.is_finished():
                # Error message should have been sent by start_engine or view stopped itself
                print("ChessBotView: Engine failed to start, stopping command execution.")
                # No need to send another message here, start_engine handles it.
                return # Stop if engine failed

            initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
            initial_message_content = view.get_board_message(initial_status_prefix)
            board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

            message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
            view.message = message
            self.active_chess_bot_views[message.id] = view # Track the view

            asyncio.create_task(view._send_or_update_dm())

            if player_color == chess.BLACK:
                asyncio.create_task(view.make_bot_move())

        except Exception as e:
            print(f"Error during /chessbot command setup: {e}")
            try:
                await interaction.followup.send(f"An error occurred while starting the chess game: {e}", ephemeral=True)
            except discord.HTTPException:
                pass # Ignore if we can't send the error

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
                        color: Optional[app_commands.Choice[str]] = None, # Required for bot games
                        skill_level: int = 10,
                        think_time: float = 1.0):
        """Loads a chess game state (FEN, PGN, Array) and starts a view."""
        await interaction.response.defer()
        initiator = interaction.user
        board = None
        load_error = None
        loaded_pgn_game = None

        # --- Input Validation ---
        if not opponent and not color:
            await interaction.followup.send("The 'color' parameter is required when playing against the bot.", ephemeral=True)
            return

        # --- Parsing Logic ---
        state_trimmed = state.strip()
        try:
            # 1. Try parsing as PGN
            if state_trimmed.startswith("[Event") or ('.' in state_trimmed and ('O-O' in state_trimmed or 'x' in state_trimmed or state_trimmed[0].isdigit())):
                pgn_io = io.StringIO(state_trimmed)
                loaded_pgn_game = chess.pgn.read_game(pgn_io)
                if loaded_pgn_game is None: raise ValueError("Could not parse PGN data.")
                board = loaded_pgn_game.end().board()
                print("[Debug] Parsed as PGN.")
            # 2. Try parsing as FEN
            elif '/' in state_trimmed and (' w ' in state_trimmed or ' b ' in state_trimmed):
                board = chess.Board(fen=state_trimmed)
                print(f"[Debug] Parsed as FEN: {state_trimmed}")
            # 3. Try parsing as Array
            elif state_trimmed.startswith('[') and state_trimmed.endswith(']'):
                if not turn: raise ValueError("The 'turn' parameter is required for array state.")
                board_array = ast.literal_eval(state_trimmed)
                if not isinstance(board_array, list) or len(board_array) != 8 or \
                   not all(isinstance(row, list) and len(row) == 8 for row in board_array):
                    raise ValueError("Invalid array structure. Must be 8x8 list.")
                turn_color = chess.WHITE if turn.value == "white" else chess.BLACK
                fen = self._array_to_fen(board_array, turn_color)
                print(f"[Debug] Converted array to FEN: {fen}")
                board = chess.Board(fen=fen)
            else:
                raise ValueError("Input does not match known PGN, FEN, or Array patterns.")
        except Exception as e:
            load_error = f"Invalid state format. Could not parse input. Error: {e}"
            print(f"[Error] State parsing failed: {e}")

        # --- Final Check and Error Handling ---
        if board is None:
            final_error = load_error or "Failed to load board state from the provided input."
            await interaction.followup.send(final_error, ephemeral=True)
            return

        # --- Game Setup ---
        try:
            if opponent:
                # Player vs Player
                if opponent == initiator: raise ValueError("You cannot challenge yourself!")
                if opponent.bot: raise ValueError("You cannot challenge a bot! Use `/chessbot` or load without opponent.")

                white_player = initiator if board.turn == chess.WHITE else opponent
                black_player = opponent if board.turn == chess.WHITE else initiator

                # Use ChessView imported at the top
                view = ChessView(white_player, black_player, board=board)
                if loaded_pgn_game:
                    view.game_pgn = loaded_pgn_game
                    view.pgn_node = loaded_pgn_game.end()

                current_player_mention = white_player.mention if board.turn == chess.WHITE else black_player.mention
                turn_color_name = "White" if board.turn == chess.WHITE else "Black"
                initial_status = f"Turn: **{current_player_mention}** ({turn_color_name})"
                if board.is_check(): initial_status += " **Check!**"
                initial_message = f"Loaded Chess Game: {white_player.mention} (White) vs {black_player.mention} (Black)\n\n{initial_status}"
                perspective_white = (initiator.id == white_player.id) # Show from initiator's perspective
                board_image = generate_board_image(view.board, perspective_white=perspective_white)

                message = await interaction.followup.send(initial_message, file=board_image, view=view, wait=True)
                view.message = message

                asyncio.create_task(view._send_or_update_dm(view.white_player))
                asyncio.create_task(view._send_or_update_dm(view.black_player))

            else:
                # Player vs Bot
                player = initiator
                player_color = chess.WHITE if color.value == "white" else chess.BLACK
                skill_level = max(0, min(20, skill_level))
                think_time = max(0.1, min(5.0, think_time))
                variant_str = "chess960" if board.chess960 else "standard"

                view = ChessBotView(player, player_color, variant_str, skill_level, think_time, board=board)
                if loaded_pgn_game:
                    view.game_pgn = loaded_pgn_game
                    view.pgn_node = loaded_pgn_game.end()

                view._interaction = interaction # For error reporting during start
                await view.start_engine()
                if hasattr(view, '_interaction'): del view._interaction

                if view.engine is None or view.is_finished():
                    print("ChessBotView (Load): Engine failed to start, stopping command execution.")
                    return # start_engine should have sent error

                status_prefix = "Your turn." if board.turn == player_color else "Bot is thinking..."
                initial_message_content = view.get_board_message(status_prefix)
                board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

                message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
                view.message = message
                self.active_chess_bot_views[message.id] = view

                asyncio.create_task(view._send_or_update_dm())

                if board.turn != player_color:
                    asyncio.create_task(view.make_bot_move())

        except Exception as e:
            print(f"Error during /loadchess game setup: {e}")
            try:
                await interaction.followup.send(f"An error occurred setting up the chess game: {e}", ephemeral=True)
            except discord.HTTPException:
                pass

    # --- Prefix Commands (Legacy Support) ---

    @commands.command(name="chessbot")
    async def chessbot_prefix(self, ctx: commands.Context, color: str = "white", variant: str = "standard", skill_level: int = 10, think_time: float = 1.0):
        """(Prefix) Play chess against the bot. Usage: !chessbot [white|black] [standard|chess960] [skill 0-20] [time 0.1-5.0]"""
        player = ctx.author
        player_color_str = color.lower()
        variant_str = variant.lower()

        if player_color_str not in ["white", "black"]:
            await ctx.send("Invalid color. Please choose 'white' or 'black'.")
            return
        player_color = chess.WHITE if player_color_str == "white" else chess.BLACK

        supported_variants = ["standard", "chess960"]
        if variant_str not in supported_variants:
            await ctx.send(f"Sorry, the variant '{variant_str}' is not currently supported. Choose from: {', '.join(supported_variants)}")
            return

        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))

        thinking_msg = await ctx.send("Initializing chess engine...")

        try:
            view = ChessBotView(player, player_color, variant_str, skill_level, think_time)

            view.message = thinking_msg # Store message early for error reporting
            await view.start_engine()

            if view.engine is None or view.is_finished():
                 print("ChessBotView (Prefix): Engine failed to start, stopping command execution.")
                 # start_engine should have edited the message or logged error
                 return

            initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
            initial_message_content = view.get_board_message(initial_status_prefix)
            board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

            message = await thinking_msg.edit(content=initial_message_content, attachments=[board_image], view=view)
            view.message = message # Update view's message reference
            self.active_chess_bot_views[message.id] = view

            asyncio.create_task(view._send_or_update_dm())

            if player_color == chess.BLACK:
                asyncio.create_task(view.make_bot_move())

        except Exception as e:
            print(f"Error during !chessbot command setup: {e}")
            try:
                await thinking_msg.edit(content=f"An error occurred while starting the chess game: {e}", view=None, attachments=[])
            except discord.HTTPException:
                pass # Ignore if we can't edit the message

    # --- Listeners for Cleanup ---

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Clean up finished chess bot views when interacted with."""
        # Check if the interaction is for a message managed by this cog
        if interaction.message and interaction.message.id in self.active_chess_bot_views:
            view = self.active_chess_bot_views.get(interaction.message.id)
            # If the view associated with the message is finished, remove it from tracking
            if view and view.is_finished():
                # Check again before deleting in case of race conditions
                if interaction.message.id in self.active_chess_bot_views:
                    del self.active_chess_bot_views[interaction.message.id]
                    print(f"Removed finished ChessBotView tracking for message {interaction.message.id}")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Clean up chess bot view if its message is deleted."""
        if message.id in self.active_chess_bot_views:
            print(f"Chess game message {message.id} deleted. Stopping associated view and engine.")
            view = self.active_chess_bot_views.pop(message.id, None) # Use pop to remove and get view
            if view and not view.is_finished():
                # Ensure it's a ChessBotView and has the stop_engine method
                if isinstance(view, ChessBotView) and hasattr(view, 'stop_engine'):
                    try:
                        await view.stop_engine()
                    except Exception as e:
                        print(f"Error stopping engine for deleted message view {view}: {e}")
                # Stop the view itself
                if hasattr(view, 'stop'):
                    view.stop()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listener to potentially handle other message-based game interactions if needed."""
        if message.author.bot:
            return
        # Currently no message content based triggers active for chess
        pass

async def setup(bot: commands.Bot):
    # Ensure necessary libraries are available
    try:
        import chess
        import chess.pgn
        from PIL import Image, ImageDraw, ImageFont
        import io
        import ast
    except ImportError as e:
        print(f"Error loading GamesCog: Missing dependency - {e}. Please install required libraries (python-chess, Pillow).")
        return

    # Check for Stockfish executable using the imported function
    stockfish_available = False
    try:
        get_stockfish_path() # This will raise FileNotFoundError or OSError if not found/configured
        stockfish_available = True
    except (FileNotFoundError, OSError) as e:
        print(f"Warning loading GamesCog: {e}. Chess bot features will be unavailable.")

    # Load the cog
    await bot.add_cog(GamesCog(bot))
    if stockfish_available:
        print("GamesCog loaded successfully with Stockfish available.")
    else:
         print("GamesCog loaded, but Stockfish engine not found or not executable. Chess bot commands will fail.")
