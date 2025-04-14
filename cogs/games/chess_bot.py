import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import asyncio
from typing import Optional, List, Union
import chess
import chess.pgn
import chess.engine # Ensure this import exists
import platform
import os
from PIL import Image, ImageDraw, ImageFont
import io
import ast

# Import shared utilities
from .chess_utils import generate_board_image, MoveInputModal
# Import PvP view for loadchess command type hint
from .chess_pvp import ChessView


# --- Chess Bot Game --- START

# Define paths relative to the script location for better portability
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR)) # Go up two levels (cogs/games -> cogs -> root)

STOCKFISH_PATH_WINDOWS = os.path.join(PROJECT_ROOT, "stockfish-windows-x86-64-avx2", "stockfish", "stockfish-windows-x86-64-avx2.exe")
STOCKFISH_PATH_LINUX = os.path.join(PROJECT_ROOT, "stockfish-ubuntu-x86-64-avx2", "stockfish", "stockfish-ubuntu-x86-64-avx2")

def get_stockfish_path():
    """Returns the appropriate Stockfish path based on the OS."""
    system = platform.system()
    if system == "Windows":
        if not os.path.exists(STOCKFISH_PATH_WINDOWS):
            raise FileNotFoundError(f"Stockfish not found at expected Windows path: {STOCKFISH_PATH_WINDOWS}")
        return STOCKFISH_PATH_WINDOWS
    elif system == "Linux":
        # Check for execute permissions on Linux
        if not os.path.exists(STOCKFISH_PATH_LINUX):
            raise FileNotFoundError(f"Stockfish not found at expected Linux path: {STOCKFISH_PATH_LINUX}")
        if not os.access(STOCKFISH_PATH_LINUX, os.X_OK):
             print(f"Warning: Stockfish at {STOCKFISH_PATH_LINUX} does not have execute permissions. Attempting to set...")
             try:
                 os.chmod(STOCKFISH_PATH_LINUX, 0o755) # Add execute permissions
                 if not os.access(STOCKFISH_PATH_LINUX, os.X_OK): # Check again
                     raise OSError(f"Failed to set execute permissions for Stockfish at {STOCKFISH_PATH_LINUX}")
             except Exception as e:
                 raise OSError(f"Error setting execute permissions for Stockfish: {e}")
        return STOCKFISH_PATH_LINUX
    else:
        raise OSError(f"Unsupported operating system '{system}' for Stockfish.")

# This button class seems unused now that image boards are implemented, but kept for completeness
class ChessBotButton(ui.Button['ChessBotView']):
    def __init__(self, x: int, y: int, piece_symbol: Optional[str] = None):
        # Unicode chess pieces
        self.pieces = {
            'r': '♜', 'n': '♞', 'b': '♝', 'q': '♛', 'k': '♚', 'p': '♟',
            'R': '♖', 'N': '♘', 'B': '♗', 'Q': '♕', 'K': '♔', 'P': '♙',
            None: ' ' # Use a space for empty squares
        }
        self.x = x
        self.y = y
        self.piece_symbol = piece_symbol

        # Set button style and label based on square color
        is_dark = (x + y) % 2 != 0
        style = discord.ButtonStyle.secondary if is_dark else discord.ButtonStyle.primary
        label = self.pieces.get(piece_symbol, ' ') # Get piece representation or space
        super().__init__(style=style, label=label if label != ' ' else '') # Use em-space for empty squares

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: ChessBotView = self.view

        # Check if it's the player's turn and the engine is ready
        if interaction.user != view.player:
             await interaction.response.send_message("This is not your game!", ephemeral=True)
             return
        if view.board.turn != view.player_color:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
        if view.engine is None or view.is_thinking:
            await interaction.response.send_message("Please wait for the bot to finish thinking or start.", ephemeral=True)
            return

        # Process the move (This part needs a handler in the view, e.g., handle_square_click)
        # Assuming a handle_square_click method exists in ChessBotView
        if hasattr(view, 'handle_square_click'):
            await view.handle_square_click(interaction, self.x, self.y)
        else:
            print("Error: ChessBotButton callback cannot find handle_square_click in view.")
            await interaction.response.send_message("Error processing button click.", ephemeral=True)


class ChessBotView(ui.View):
    # Maps skill level (0-20) to typical ELO ratings for context
    SKILL_ELO_MAP = {
        0: 800, 1: 900, 2: 1000, 3: 1100, 4: 1200, 5: 1300, 6: 1400, 7: 1500, 8: 1600, 9: 1700,
        10: 1800, 11: 1900, 12: 2000, 13: 2100, 14: 2200, 15: 2300, 16: 2400, 17: 2500, 18: 2600,
        19: 2700, 20: 2800
    }

    def __init__(self, player: discord.Member, player_color: chess.Color, variant: str = "standard", skill_level: int = 10, think_time: float = 1.0, board: Optional[chess.Board] = None, cog: Optional[commands.Cog] = None):
        super().__init__(timeout=900.0)  # 15 minute timeout
        self.player = player
        self.player_color = player_color # The color the human player chose to play as
        self.bot_color = not player_color
        self.variant = variant.lower()
        self.message: Optional[discord.Message] = None
        self.engine: Optional[chess.engine.SimpleEngine] = None # Use SimpleEngine for async
        self._engine_transport: Optional[asyncio.SubprocessTransport] = None # Store transport for closing
        self.skill_level = max(0, min(20, skill_level)) # Clamp skill level
        self.think_time = max(0.1, min(5.0, think_time)) # Clamp think time
        self.is_thinking = False # Flag to prevent interaction during bot's turn
        self.last_move: Optional[chess.Move] = None # Store last move for highlighting
        self.player_dm_message: Optional[discord.Message] = None # DM message for the player
        self.cog = cog # Store reference to the main cog for cleanup

        # Initialize board - Use provided board or create new based on variant
        if board:
            self.board = board
            # Infer variant from loaded board if possible
            self.variant = "chess960" if self.board.chess960 else "standard"
        else:
            self.variant = variant.lower()
            if self.variant == "chess960":
                self.board = chess.Board(chess960=True)
            else: # Standard chess
                self.board = chess.Board()

        # Initialize PGN tracking
        self.game_pgn = chess.pgn.Game()
        self.game_pgn.headers["Event"] = f"Discord Chess Bot Game (Skill {self.skill_level})"
        self.game_pgn.headers["Site"] = "Discord"
        self.game_pgn.headers["White"] = player.display_name if player_color == chess.WHITE else f"Bot (Skill {self.skill_level})"
        self.game_pgn.headers["Black"] = player.display_name if player_color == chess.BLACK else f"Bot (Skill {self.skill_level})"
        # If starting from a non-standard position (loaded board), set up PGN
        self.game_pgn.setup(self.board) # Setup PGN from the board state
        self.pgn_node = self.game_pgn # Start at the root node

        # Add control buttons
        self.add_item(self.MakeMoveButton())
        self.add_item(self.ResignButton())

    # --- Button Definitions ---

    class MakeMoveButton(ui.Button):
        def __init__(self):
            super().__init__(label="Make Move", style=discord.ButtonStyle.primary, custom_id="chessbot_make_move")

        async def callback(self, interaction: discord.Interaction):
            view: 'ChessBotView' = self.view
            # Check turn and thinking state
            if interaction.user != view.player:
                 await interaction.response.send_message("This is not your game!", ephemeral=True)
                 return
            if view.board.turn != view.player_color:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            if view.is_thinking:
                await interaction.response.send_message("The bot is thinking, please wait.", ephemeral=True)
                return
            if view.engine is None:
                 await interaction.response.send_message("The engine is not running or failed to start.", ephemeral=True)
                 return

            # Open the modal for move input
            await interaction.response.send_modal(MoveInputModal(game_view=view))

    class ResignButton(ui.Button):
        def __init__(self):
            super().__init__(label="Resign", style=discord.ButtonStyle.danger, custom_id="chessbot_resign")

        async def callback(self, interaction: discord.Interaction):
            view: 'ChessBotView' = self.view
            if interaction.user != view.player:
                 await interaction.response.send_message("This is not your game!", ephemeral=True)
                 return
            # Bot wins on player resignation
            await view.end_game(interaction, f"{view.player.mention} resigned. Bot wins! 🏳️")

    # --- Engine and Game Logic ---

    async def start_engine(self):
        """Initializes the Stockfish engine using the async SimpleEngine."""
        if self.engine: # Avoid starting multiple engines
            return
        try:
            stockfish_path = get_stockfish_path()
            print(f"[Debug] OS: {platform.system()}, Path used: {stockfish_path}")

            # Use the async open_uci
            print("[Debug] Awaiting chess.engine.open_uci...")
            # --- Debugging Removed ---
            self.engine = await chess.engine.open_uci(stockfish_path)
            print(f"[Debug] open_uci successful. Engine type: {type(self.engine)}")

            # Configure Stockfish options
            print("[Debug] Configuring engine...")
            options_to_set = {"Skill Level": self.skill_level}
            if self.variant == "chess960":
                options_to_set["UCI_Chess960"] = True
            await self.engine.configure(options_to_set)
            print("[Debug] Configuration successful.")

            print(f"Stockfish engine configured for {self.variant} with skill level {self.skill_level}.")

        except (FileNotFoundError, OSError, chess.engine.EngineError, Exception) as e:
             print(f"[Error] Failed to start or configure Stockfish engine: {e}")
             self.engine = None # Ensure engine is None on failure
             # Try to notify the user if possible
             if hasattr(self, '_interaction') and self._interaction: # Check if interaction context exists
                 try:
                     await self._interaction.followup.send(f"Error: Could not start the chess engine: {e}", ephemeral=True)
                 except Exception as notify_error:
                     print(f"Failed to notify user about engine start error: {notify_error}")
             elif self.message: # Fallback to using the message channel
                 try:
                     await self.message.channel.send(f"Error: Could not start the chess engine: {e}")
                 except Exception as notify_error:
                     print(f"Failed to notify user via channel about engine start error: {notify_error}")
             # Stop the view if engine fails to start
             if not self.is_finished():
                 self.stop()


    async def handle_player_move(self, interaction: discord.Interaction, move: chess.Move):
        """Handles the player's validated legal move."""
        if self.is_thinking:
            await interaction.followup.send("The bot is still thinking!", ephemeral=True)
            return
        if self.engine is None:
             await interaction.followup.send("The chess engine is not available.", ephemeral=True)
             return

        # Add move to PGN
        try:
            self.pgn_node = self.pgn_node.add_variation(move)
        except Exception as e:
            print(f"Error adding player move to PGN: {e}")

        self.board.push(move)
        self.last_move = move

        # Update player's DM
        asyncio.create_task(self._send_or_update_dm())

        # Check game state *after* player's move
        outcome = self.board.outcome()
        if outcome:
            await self.end_game(interaction, self.get_game_over_message(outcome))
            return

        # Update message to show player's move and indicate bot's turn
        # Use followup.edit_message as the interaction was deferred in the modal
        await self.update_message(interaction, status_prefix="Bot is thinking...")

        # Trigger bot's move asynchronously
        asyncio.create_task(self.make_bot_move(interaction)) # Pass interaction for potential error reporting

    async def make_bot_move(self, original_interaction: Optional[discord.Interaction] = None):
        """Lets the Stockfish engine make a move using the async protocol."""
        if self.engine is None or self.board.turn != self.bot_color or self.is_thinking or self.is_finished():
            return

        self.is_thinking = True
        bot_move = None
        try:
            # Use the engine's play method (ASYNC)
            print("[Debug] Awaiting engine.play...")
            # Ensure the board is passed correctly
            result = await self.engine.play(self.board, chess.engine.Limit(time=self.think_time))
            print(f"[Debug] engine.play completed. Result: {result}")
            bot_move = result.move

            # Check if the view is still active before proceeding
            if self.is_finished():
                print("ChessBotView: Game ended while bot was thinking.")
                return

            if bot_move:
                # Add bot's move to PGN
                try:
                    self.pgn_node = self.pgn_node.add_variation(bot_move)
                except Exception as e:
                    print(f"Error adding bot move to PGN: {e}")

                self.board.push(bot_move)
                self.last_move = bot_move

                # Update player's DM
                asyncio.create_task(self._send_or_update_dm())

                # Check game state *after* bot's move
                outcome = self.board.outcome()
                if outcome:
                    # Use self.message if available to end the game
                    if self.message:
                         await self.end_game(self.message, self.get_game_over_message(outcome))
                    else:
                         print("ChessBotView Error: Cannot end game after bot move, self.message is None.")
                    return # Important: return after ending the game

                # Update message for player's turn
                if self.message and not self.is_finished():
                    await self.update_message(self.message, status_prefix="Your turn.")
            else:
                 print("ChessBotView: Engine returned no best move (result.move is None).")
                 if self.message and not self.is_finished():
                     await self.update_message(self.message, status_prefix="Bot failed to find a move. Your turn?")

        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, Exception) as e:
            print(f"Error during bot move analysis: {e}")
            # Try to inform the user via the original interaction if possible
            error_message = f"An error occurred during the bot's move: {e}. Stopping game."
            if original_interaction and original_interaction.response.is_done():
                try: await original_interaction.followup.send(error_message, ephemeral=True)
                except: pass # Ignore errors sending followup
            elif self.message:
                 try: await self.message.channel.send(error_message)
                 except: pass # Ignore errors sending to channel
            # Stop the game if the engine has issues
            await self.end_game(self.message or original_interaction, f"Game stopped due to engine error: {e}")
        finally:
            self.is_thinking = False

    # --- Message and State Management ---

    async def update_message(self, interaction_or_message: Union[discord.Interaction, discord.Message], status_prefix: str = ""):
        """Updates the game message with the current board image and status."""
        if self.is_finished(): return # Don't update if view stopped

        content = self.get_board_message(status_prefix)
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE))

        try:
            if isinstance(interaction_or_message, discord.Interaction):
                # Use followup.edit_message if interaction was deferred
                if interaction_or_message.response.is_done():
                     await interaction_or_message.edit_original_response(content=content, attachments=[board_image], view=self)
                else: # Should not happen often here, but handle just in case
                     await interaction_or_message.response.edit_message(content=content, attachments=[board_image], view=self)
            elif isinstance(interaction_or_message, discord.Message):
                 await interaction_or_message.edit(content=content, attachments=[board_image], view=self)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"ChessBotView: Failed to update message: {e}")
            # If message update fails, stop the game to prevent inconsistent state
            await self.stop_engine()
            if not self.is_finished(): self.stop()

    def get_board_message(self, status_prefix: str) -> str:
        """Generates the message content including status and whose turn it is."""
        turn_color_name = "White" if self.board.turn == chess.WHITE else "Black"
        player_mention = self.player.mention
        elo = self.SKILL_ELO_MAP.get(self.skill_level, "Unknown")
        variant_name = "Chess960" if self.variant == "chess960" else "Standard Chess"

        title = f"{variant_name}: {player_mention} ({'White' if self.player_color == chess.WHITE else 'Black'}) vs Bot (Skill: {self.skill_level}/20, ~{elo} ELO)"

        # Determine turn indicator string
        if self.board.turn == self.player_color:
            turn_indicator = f"Turn: **Your ({turn_color_name})**"
        else:
            turn_indicator = f"Turn: **Bot ({turn_color_name})**"

        # Add check indicator
        check_indicator = ""
        if self.board.is_check():
            check_indicator = " **Check!**"

        return f"{title}\n\n{status_prefix}{check_indicator}\n{turn_indicator}"

    def get_game_over_message(self, outcome: chess.Outcome) -> str:
        """Generates the game over message based on the outcome."""
        winner_text = "It's a draw!"
        if outcome.winner == self.player_color:
            winner_text = f"{self.player.mention} ({'White' if self.player_color == chess.WHITE else 'Black'}) wins!"
        elif outcome.winner == self.bot_color:
            winner_text = f"Bot ({'White' if self.bot_color == chess.WHITE else 'Black'}) wins!"

        termination_reason = outcome.termination.name.replace("_", " ").title()
        return f"Game Over! **{winner_text} by {termination_reason}**"

    async def end_game(self, interaction_or_message: Union[discord.Interaction, discord.Message, None], message_content: str):
        """Ends the game, disables buttons, stops the engine, and updates the message."""
        if self.is_finished(): return # Avoid double execution

        print(f"Ending ChessBot game. Reason: {message_content}")
        await self.disable_all_buttons()
        await self.stop_engine() # Ensure engine is closed

        # Update DM with final result
        await self._send_or_update_dm(result=message_content)

        # Remove view from active tracking in the cog
        if self.cog and self.message:
            self.cog.active_chess_bot_views.pop(self.message.id, None)
            print(f"Removed ChessBotView tracking for message {self.message.id}")

        # Generate final board image
        final_board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE))

        # Update the message
        target_message = self.message
        interaction = None
        if isinstance(interaction_or_message, discord.Interaction):
            interaction = interaction_or_message
            if not target_message: # Try to get message from interaction if not set
                try: target_message = await interaction.original_response()
                except: pass

        try:
            if interaction and interaction.response.is_done():
                 await interaction.edit_original_response(content=message_content, attachments=[final_board_image], view=self)
            elif interaction and not interaction.response.is_done():
                 await interaction.response.edit_message(content=message_content, attachments=[final_board_image], view=self)
            elif target_message:
                 await target_message.edit(content=message_content, attachments=[final_board_image], view=self)
            else:
                 print("ChessBotView: Could not determine message/interaction to edit for game end.")
        except (discord.NotFound, discord.HTTPException) as e:
             print(f"ChessBotView: Failed to edit message on game end: {e}")
             # Attempt to send a new message if editing failed
             channel = target_message.channel if target_message else (interaction.channel if interaction else None)
             if channel:
                 try: await channel.send(content=message_content, files=[final_board_image])
                 except: pass # Ignore further errors

        self.stop() # Stop the view itself

    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        # Edit the message immediately to show disabled buttons if possible
        if self.message and not self.is_finished():
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass # Ignore if message is already gone or cannot be edited

    async def stop_engine(self):
        """Safely quits the chess engine."""
        if self.engine:
            try:
                await self.engine.quit()
                print("Stockfish engine quit command sent successfully.")
            except (chess.engine.EngineError, chess.engine.EngineTerminatedError, Exception) as e:
                print(f"Error quitting Stockfish engine: {e}")
            finally:
                self.engine = None

    async def on_timeout(self):
        if not self.is_finished():
            timeout_msg = f"Chess game for {self.player.mention} timed out."
            await self.end_game(self.message, timeout_msg) # Use end_game for cleanup

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print(f"Error in ChessBotView interaction (item: {item}): {error}")
        # Try to send an ephemeral message about the error
        try:
            error_msg = f"An error occurred: {error}"
            if interaction.response.is_done():
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)
        except Exception as e:
            print(f"ChessBotView: Failed to send error response: {e}")

        # Stop the game on error to be safe
        await self.end_game(interaction, f"An error occurred, stopping the game: {error}")

    # --- DM Helper Methods --- (Identical to ChessView, could be further abstracted)
    async def _get_dm_content(self, result: Optional[str] = None) -> str:
        """Generates the FEN and PGN content for the player's DM."""
        fen = self.board.fen()
        opponent_name = f"Bot (Skill {self.skill_level})"
        opponent_color_str = "Black" if self.player_color == chess.WHITE else "White"

        # Update PGN headers if result is provided and game is over
        if result:
            pgn_result_code = "*" # Default
            if "wins" in result:
                if self.player.mention in result: # Player won
                    pgn_result_code = "1-0" if self.player_color == chess.WHITE else "0-1"
                else: # Bot won
                    pgn_result_code = "0-1" if self.player_color == chess.WHITE else "1-0"
            elif "draw" in result:
                pgn_result_code = "1/2-1/2"
            elif "resigned" in result: # Player resigned, bot wins
                 pgn_result_code = "0-1" if self.player_color == chess.WHITE else "1-0"
            # Only update if not already set or if changing from '*'
            if "Result" not in self.game_pgn.headers or self.game_pgn.headers["Result"] == "*":
                 self.game_pgn.headers["Result"] = pgn_result_code

        # Use an exporter for cleaner PGN output
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        pgn_string = self.game_pgn.accept(exporter)
        pgn_preview = pgn_string[:1500] + "..." if len(pgn_string) > 1500 else pgn_string

        content = f"**Game vs {opponent_name}** ({opponent_color_str})\n\n" \
                  f"**FEN:**\n`{fen}`\n\n" \
                  f"**PGN:**\n```pgn\n{pgn_preview}\n```"

        if result:
            content += f"\n\n**Status:** {result}"

        return content

    async def _send_or_update_dm(self, result: Optional[str] = None):
        """Sends or updates the DM with FEN and PGN for the human player."""
        player = self.player
        dm_message = self.player_dm_message

        try:
            content = await self._get_dm_content(result=result)
            dm_channel = player.dm_channel or await player.create_dm()

            if dm_message:
                try:
                    await dm_message.edit(content=content)
                    return # Edited successfully
                except discord.NotFound:
                    print(f"DM message for {player.display_name} not found, will send a new one.")
                    self.player_dm_message = None
                    dm_message = None
                except discord.Forbidden:
                    print(f"Cannot edit DM for {player.display_name} (Forbidden).")
                    self.player_dm_message = None
                    dm_message = None
                except discord.HTTPException as e:
                    print(f"HTTP error editing DM for {player.display_name}: {e}. Will try sending.")
                    self.player_dm_message = None
                    dm_message = None

            if dm_message is None:
                new_dm_message = await dm_channel.send(content=content)
                self.player_dm_message = new_dm_message

        except discord.Forbidden:
            print(f"Cannot send DM to {player.display_name} (Forbidden). User likely has DMs disabled.")
            self.player_dm_message = None
        except discord.HTTPException as e:
            print(f"Failed to send/edit DM for {player.display_name}: {e}")
            self.player_dm_message = None
        except Exception as e:
            print(f"Unexpected error sending/updating DM for {player.display_name}: {e}")
            self.player_dm_message = None

# --- Chess Bot Game --- END

# --- Helper for loadchess ---
def _array_to_fen(board_array: List[List[str]], turn: chess.Color) -> str:
    """Converts an 8x8 array representation to a basic FEN string."""
    fen_rows = []
    for rank_idx in range(8): # Iterate ranks 0-7 (corresponds to 8-1 in FEN)
        rank_data = board_array[rank_idx]
        fen_row = ""
        empty_count = 0
        for piece in rank_data: # Iterate files a-h
            if piece == ".": # Assuming '.' represents empty squares
                empty_count += 1
            else:
                if empty_count > 0:
                    fen_row += str(empty_count)
                    empty_count = 0
                # Basic validation (optional, assumes input is mostly correct)
                if piece.lower() not in 'prnbqk' or (piece.islower() and turn == chess.WHITE) or (piece.isupper() and turn == chess.BLACK):
                     # This basic check might be too strict depending on array source
                     # For now, just append the character
                     pass
                fen_row += piece
        if empty_count > 0:
            fen_row += str(empty_count)
        fen_rows.append(fen_row)

    piece_placement = "/".join(fen_rows)
    turn_char = 'w' if turn == chess.WHITE else 'b'
    # Default castling, no en passant, 0 halfmove, 1 fullmove for simplicity from array
    fen = f"{piece_placement} {turn_char} - - 0 1"
    return fen

# --- Slash Commands ---

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
async def chessbot_slash(interaction: discord.Interaction, color: Optional[app_commands.Choice[str]] = None, variant: Optional[app_commands.Choice[str]] = None, skill_level: int = 10, think_time: float = 1.0):
    """Starts a chess game against the Stockfish engine."""
    # Get cog instance to pass to the view for cleanup tracking
    cog = interaction.client.get_cog('GamesCog') # Assumes the main cog is named 'GamesCog'
    if not cog:
        await interaction.response.send_message("Error: GamesCog not found.", ephemeral=True)
        return

    player = interaction.user
    player_color_str = color.value if color else "white"
    variant_str = variant.value if variant else "standard"
    player_color = chess.WHITE if player_color_str == "white" else chess.BLACK

    # Validate inputs
    skill_level = max(0, min(20, skill_level))
    think_time = max(0.1, min(5.0, think_time))

    supported_variants = ["standard", "chess960"]
    if variant_str not in supported_variants:
        await interaction.response.send_message(f"Sorry, the variant '{variant_str}' is not currently supported.", ephemeral=True)
        return

    await interaction.response.defer()

    view = ChessBotView(player, player_color, variant_str, skill_level, think_time, cog=cog)

    # Store interaction temporarily for potential error reporting during engine start
    view._interaction = interaction
    await view.start_engine()
    if hasattr(view, '_interaction'): del view._interaction # Clean up temporary attribute

    if view.engine is None or view.is_finished():
         print("ChessBotView: Engine failed to start or view stopped during init.")
         # Error message should have been sent by start_engine or view stopped itself
         return

    initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
    initial_message_content = view.get_board_message(initial_status_prefix)
    board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

    message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
    view.message = message
    cog.active_chess_bot_views[message.id] = view # Track the view in the main cog

    # Send initial DM to player
    asyncio.create_task(view._send_or_update_dm())

    if player_color == chess.BLACK:
        asyncio.create_task(view.make_bot_move(interaction))


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
async def loadchess_slash(interaction: discord.Interaction,
                    state: str,
                    turn: Optional[app_commands.Choice[str]] = None,
                    opponent: Optional[discord.Member] = None,
                    color: Optional[app_commands.Choice[str]] = None,
                    skill_level: int = 10,
                    think_time: float = 1.0):
    """Loads a chess game state (FEN, PGN, Array) and starts a view."""
    # Get cog instance
    cog = interaction.client.get_cog('GamesCog')
    if not cog:
        await interaction.response.send_message("Error: GamesCog not found.", ephemeral=True)
        return

    await interaction.response.defer()
    initiator = interaction.user
    board = None
    load_error = None
    loaded_pgn_game = None

    # --- Input Validation ---
    if opponent and opponent == initiator:
        await interaction.followup.send("You cannot challenge yourself!", ephemeral=True)
        return
    if opponent and opponent.bot:
        await interaction.followup.send("You cannot challenge a bot directly with loadchess. Load against the bot by omitting the opponent.", ephemeral=True)
        return
    if not opponent and not color:
        await interaction.followup.send("The 'color' parameter (your color) is required when loading a game against the bot.", ephemeral=True)
        return

    # --- Parsing Logic ---
    state_trimmed = state.strip()
    # (Parsing logic remains the same as in the original cog)
    # 1. Try parsing as PGN
    if state_trimmed.startswith("[Event") or ('.' in state_trimmed and ('O-O' in state_trimmed or 'x' in state_trimmed or state_trimmed[0].isdigit())):
        try:
            pgn_io = io.StringIO(state_trimmed)
            loaded_pgn_game = chess.pgn.read_game(pgn_io)
            if loaded_pgn_game is None: raise ValueError("Could not parse PGN data.")
            board = loaded_pgn_game.end().board()
            print("[Debug] Parsed as PGN.")
        except Exception as e:
            load_error = f"Could not parse as PGN: {e}. Trying other formats."
            loaded_pgn_game = None
    # 2. Try parsing as FEN
    if board is None and '/' in state_trimmed and (' w ' in state_trimmed or ' b ' in state_trimmed):
        try:
            board = chess.Board(fen=state_trimmed)
            print(f"[Debug] Parsed as FEN: {state_trimmed}")
        except Exception as e:
            load_error = f"Invalid FEN string: {e}. Trying array format."
    # 3. Try parsing as Array
    if board is None:
        try:
            if not state_trimmed.startswith('[') or not state_trimmed.endswith(']'): raise ValueError("Input does not look like a list array.")
            board_array = ast.literal_eval(state_trimmed)
            if not isinstance(board_array, list) or len(board_array) != 8 or not all(isinstance(row, list) and len(row) == 8 for row in board_array): raise ValueError("Invalid array structure. Must be 8x8 list.")
            if not turn: raise ValueError("The 'turn' parameter is required when providing a board array.")
            turn_color = chess.WHITE if turn.value == "white" else chess.BLACK
            fen = _array_to_fen(board_array, turn_color) # Use the helper function
            board = chess.Board(fen=fen)
            print(f"[Debug] Parsed as array, converted to FEN: {fen}")
        except Exception as e:
            load_error = f"Invalid state format. Could not parse as PGN, FEN, or Python list array. Error: {e}"

    # --- Final Check ---
    if board is None:
        final_error = load_error or "Failed to load board state from the provided input."
        await interaction.followup.send(final_error, ephemeral=True)
        return

    # --- Game Setup ---
    if opponent:
        # Player vs Player
        white_player = initiator if board.turn == chess.WHITE else opponent
        black_player = opponent if board.turn == chess.WHITE else initiator
        view = ChessView(white_player, black_player, board=board)
        if loaded_pgn_game:
            view.game_pgn = loaded_pgn_game
            view.pgn_node = loaded_pgn_game.end()

        current_player_mention = white_player.mention if board.turn == chess.WHITE else black_player.mention
        turn_color_name = "White" if board.turn == chess.WHITE else "Black"
        initial_status = f"Turn: **{current_player_mention}** ({turn_color_name})"
        if board.is_check(): initial_status += " **Check!**"
        initial_message = f"Loaded Chess Game: {white_player.mention} (White) vs {black_player.mention} (Black)\n\n{initial_status}"
        perspective_white = (board.turn == chess.WHITE) # Show board from current player's perspective
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

        view = ChessBotView(player, player_color, variant_str, skill_level, think_time, board=board, cog=cog)
        if loaded_pgn_game:
            view.game_pgn = loaded_pgn_game
            view.pgn_node = loaded_pgn_game.end()

        view._interaction = interaction # For error reporting during start
        await view.start_engine()
        if hasattr(view, '_interaction'): del view._interaction

        if view.engine is None or view.is_finished():
            print("ChessBotView (Load): Engine failed to start or view stopped during init.")
            return

        status_prefix = "Your turn." if board.turn == player_color else "Bot is thinking..."
        initial_message_content = view.get_board_message(status_prefix)
        board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

        message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
        view.message = message
        cog.active_chess_bot_views[message.id] = view # Track view

        asyncio.create_task(view._send_or_update_dm())
        if board.turn != player_color:
            asyncio.create_task(view.make_bot_move(interaction))


# --- Prefix Commands ---

@commands.command(name="chessbot")
async def chessbot_prefix(ctx: commands.Context, color: str = "white", variant: str = "standard", skill_level: int = 10, think_time: float = 1.0):
    """(Prefix) Play chess against the bot. Usage: !chessbot [white|black] [standard|chess960] [skill 0-20] [time 0.1-5.0]"""
    cog = ctx.bot.get_cog('GamesCog')
    if not cog:
        await ctx.send("Error: GamesCog not found.")
        return

    player = ctx.author
    player_color_str = color.lower()
    variant_str = variant.lower()

    if player_color_str not in ["white", "black"]:
        await ctx.send("Invalid color choice. Please choose 'white' or 'black'.")
        return
    player_color = chess.WHITE if player_color_str == "white" else chess.BLACK

    skill_level = max(0, min(20, skill_level))
    think_time = max(0.1, min(5.0, think_time))

    supported_variants = ["standard", "chess960"]
    if variant_str not in supported_variants:
        await ctx.send(f"Sorry, the variant '{variant_str}' is not currently supported.")
        return

    thinking_msg = await ctx.send("Initializing chess engine...")

    view = ChessBotView(player, player_color, variant_str, skill_level, think_time, cog=cog)
    view.message = thinking_msg # Store message early for potential error reporting

    await view.start_engine()

    if view.engine is None or view.is_finished():
         print("ChessBotView (Prefix): Engine failed to start or view stopped during init.")
         # Attempt to edit the thinking message if possible
         try: await thinking_msg.edit(content="Failed to start chess engine.")
         except: pass
         return

    initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
    initial_message_content = view.get_board_message(initial_status_prefix)
    board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

    message = await thinking_msg.edit(content=initial_message_content, attachments=[board_image], view=view)
    view.message = message # Update view's message reference
    cog.active_chess_bot_views[message.id] = view # Track view

    asyncio.create_task(view._send_or_update_dm())
    if player_color == chess.BLACK:
        asyncio.create_task(view.make_bot_move())


@commands.command(name="loadchess")
async def loadchess_prefix(ctx: commands.Context, state: str, turn: Optional[str] = None, opponent: Optional[discord.Member] = None, color: Optional[str] = None, skill_level: int = 10, think_time: float = 1.0):
    """(Prefix) Load chess game. Usage: !loadchess "<FEN/PGN/Array>" [turn] [opponent] [color] [skill] [time]"""
    cog = ctx.bot.get_cog('GamesCog')
    if not cog:
        await ctx.send("Error: GamesCog not found.")
        return

    initiator = ctx.author
    board = None
    load_error = None
    loaded_pgn_game = None

    # --- Input Validation ---
    if opponent and opponent == initiator:
        await ctx.send("You cannot challenge yourself!")
        return
    if opponent and opponent.bot:
        await ctx.send("You cannot challenge a bot directly with loadchess. Load against the bot by omitting the opponent.")
        return
    if not opponent and not color:
        await ctx.send("The 'color' parameter (your color: white/black) is required when loading a game against the bot.")
        return
    if color and color.lower() not in ["white", "black"]:
         await ctx.send("Invalid 'color' parameter. Use 'white' or 'black'.")
         return

    # --- Parsing Logic ---
    state_trimmed = state.strip()
    # (Parsing logic remains the same)
    # 1. Try parsing as PGN
    if state_trimmed.startswith("[Event") or ('.' in state_trimmed and ('O-O' in state_trimmed or 'x' in state_trimmed or state_trimmed[0].isdigit())):
        try:
            pgn_io = io.StringIO(state_trimmed)
            loaded_pgn_game = chess.pgn.read_game(pgn_io)
            if loaded_pgn_game is None: raise ValueError("Could not parse PGN data.")
            board = loaded_pgn_game.end().board()
        except Exception as e:
            load_error = f"Could not parse as PGN: {e}."
            loaded_pgn_game = None
    # 2. Try parsing as FEN
    if board is None and '/' in state_trimmed and (' w ' in state_trimmed or ' b ' in state_trimmed):
        try: board = chess.Board(fen=state_trimmed)
        except Exception as e: load_error = f"Invalid FEN string: {e}."
    # 3. Try parsing as Array
    if board is None:
        try:
            if not state_trimmed.startswith('[') or not state_trimmed.endswith(']'): raise ValueError("Input does not look like a list array.")
            board_array = ast.literal_eval(state_trimmed)
            if not isinstance(board_array, list) or len(board_array) != 8 or not all(isinstance(row, list) and len(row) == 8 for row in board_array): raise ValueError("Invalid array structure.")
            if not turn or turn.lower() not in ["white", "black"]: raise ValueError("The 'turn' parameter (white/black) is required for array state.")
            turn_color = chess.WHITE if turn.lower() == "white" else chess.BLACK
            fen = _array_to_fen(board_array, turn_color)
            board = chess.Board(fen=fen)
        except Exception as e: load_error = f"Invalid state format (PGN/FEN/Array). Error: {e}"

    # --- Final Check ---
    if board is None:
        final_error = load_error or "Failed to load board state."
        await ctx.send(final_error)
        return

    # --- Game Setup ---
    if opponent:
        # Player vs Player
        white_player = initiator if board.turn == chess.WHITE else opponent
        black_player = opponent if board.turn == chess.WHITE else initiator
        view = ChessView(white_player, black_player, board=board)
        if loaded_pgn_game:
            view.game_pgn = loaded_pgn_game
            view.pgn_node = loaded_pgn_game.end()

        current_player_mention = white_player.mention if board.turn == chess.WHITE else black_player.mention
        turn_color_name = "White" if board.turn == chess.WHITE else "Black"
        initial_status = f"Turn: **{current_player_mention}** ({turn_color_name})"
        if board.is_check(): initial_status += " **Check!**"
        initial_message = f"Loaded Chess Game: {white_player.mention} (White) vs {black_player.mention} (Black)\n\n{initial_status}"
        perspective_white = (board.turn == chess.WHITE)
        board_image = generate_board_image(view.board, perspective_white=perspective_white)

        message = await ctx.send(initial_message, file=board_image, view=view)
        view.message = message
        asyncio.create_task(view._send_or_update_dm(view.white_player))
        asyncio.create_task(view._send_or_update_dm(view.black_player))
    else:
        # Player vs Bot
        player = initiator
        player_color = chess.WHITE if color.lower() == "white" else chess.BLACK
        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))
        variant_str = "chess960" if board.chess960 else "standard"

        thinking_msg = await ctx.send("Initializing chess engine...")
        view = ChessBotView(player, player_color, variant_str, skill_level, think_time, board=board, cog=cog)
        view.message = thinking_msg # Store for potential error editing
        if loaded_pgn_game:
            view.game_pgn = loaded_pgn_game
            view.pgn_node = loaded_pgn_game.end()

        await view.start_engine()
        if view.engine is None or view.is_finished():
            print("ChessBotView (Prefix Load): Engine failed to start.")
            try: await thinking_msg.edit(content="Failed to start chess engine.")
            except: pass
            return

        status_prefix = "Your turn." if board.turn == player_color else "Bot is thinking..."
        initial_message_content = view.get_board_message(status_prefix)
        board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

        message = await thinking_msg.edit(content=initial_message_content, attachments=[board_image], view=view)
        view.message = message # Update view's message reference
        cog.active_chess_bot_views[message.id] = view # Track view

        asyncio.create_task(view._send_or_update_dm())
        if board.turn != player_color:
            asyncio.create_task(view.make_bot_move())


# --- Setup Function ---
async def setup(bot: commands.Bot, cog: commands.Cog):
    # Add slash commands
    tree = bot.tree
    tree.add_command(chessbot_slash, guild=cog.guild)
    tree.add_command(loadchess_slash, guild=cog.guild)

    # Add prefix commands
    bot.add_command(chessbot_prefix)
    bot.add_command(loadchess_prefix)

    # Add the helper function to the cog instance if needed elsewhere,
    # otherwise it's just used locally within loadchess_prefix
    # setattr(cog, '_array_to_fen', _array_to_fen) # Example if needed on cog
