import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import asyncio
from typing import Optional, List, Union # Added Union
import chess
import chess.engine
import chess.pgn # Import PGN library
import platform
import os
from PIL import Image, ImageDraw, ImageFont # Added Pillow imports
import io # Added io import
import ast

# Define paths relative to the script location for better portability
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR) # Assumes cogs folder is one level down from root

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
        # REMOVED row=y parameter
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

        # Process the move
        await view.handle_square_click(interaction, self.x, self.y)

class ChessBotView(ui.View):
    # Maps skill level (0-20) to typical ELO ratings for context
    SKILL_ELO_MAP = {
        0: 800, 1: 900, 2: 1000, 3: 1100, 4: 1200, 5: 1300, 6: 1400, 7: 1500, 8: 1600, 9: 1700,
        10: 1800, 11: 1900, 12: 2000, 13: 2100, 14: 2200, 15: 2300, 16: 2400, 17: 2500, 18: 2600,
        19: 2700, 20: 2800
    }

    def __init__(self, player: discord.Member, player_color: chess.Color, variant: str = "standard", skill_level: int = 10, think_time: float = 1.0, board: Optional[chess.Board] = None):
        super().__init__(timeout=900.0)  # 15 minute timeout
        self.player = player
        self.player_color = player_color # The color the human player chose to play as
        self.bot_color = not player_color
        self.variant = variant.lower()
        self.message: Optional[discord.Message] = None
        self.engine: Optional[chess.engine.UciProtocol] = None # Use the async UciProtocol
        self._engine_transport: Optional[asyncio.SubprocessTransport] = None # Store transport for closing
        self.skill_level = max(0, min(20, skill_level)) # Clamp skill level
        self.think_time = max(0.1, min(5.0, think_time)) # Clamp think time
        self.is_thinking = False # Flag to prevent interaction during bot's turn
        self.last_move: Optional[chess.Move] = None # Store last move for highlighting
        self.player_dm_message: Optional[discord.Message] = None # DM message for the player

        # Initialize board - Use provided board or create new based on variant
        if board:
            self.board = board
            # Infer variant from loaded board
            self.variant = "chess960" if self.board.chess960 else "standard"
            self.initial_fen = self.board.fen() if self.variant == "chess960" else None
        else:
            self.variant = variant.lower()
            if self.variant == "chess960":
                self.board = chess.Board(chess960=True)
                self.initial_fen = self.board.fen()
            else: # Standard chess
                self.board = chess.Board()
                self.initial_fen = None

        # Initialize PGN tracking
        self.game_pgn = chess.pgn.Game()
        self.game_pgn.headers["Event"] = f"Discord Chess Bot Game (Skill {self.skill_level})"
        self.game_pgn.headers["Site"] = "Discord"
        self.game_pgn.headers["White"] = player.display_name if player_color == chess.WHITE else f"Bot (Skill {self.skill_level})"
        self.game_pgn.headers["Black"] = player.display_name if player_color == chess.BLACK else f"Bot (Skill {self.skill_level})"
        # If starting from a non-standard position (loaded board), set up PGN
        if board:
            self.game_pgn.setup(board)
        else:
            self.game_pgn.setup(self.board) # Setup even for standard start
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
                 await interaction.response.send_message("The engine is not running.", ephemeral=True)
                 return
            if view.is_thinking: # Added check here as well
                await interaction.response.send_message("The bot is thinking, please wait.", ephemeral=True)
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
        """Initializes the Stockfish engine using the async UCI protocol."""
        engine_protocol = None
        transport = None
        try:
            stockfish_path = get_stockfish_path()
            print(f"[Debug] OS: {platform.system()}, Path used: {stockfish_path}")

            # Use the async popen_uci
            print("[Debug] Awaiting chess.engine.popen_uci...")
            transport, engine_protocol = await chess.engine.popen_uci(stockfish_path)
            print(f"[Debug] popen_uci successful. Protocol type: {type(engine_protocol)}")
            self.engine = engine_protocol # This is the UciProtocol object
            self._engine_transport = transport

            # Configure Stockfish options using the configure method (corrected approach)
            # NOTE: The user feedback mentioned using configure on the 'engine object'.
            # However, in this code, self.engine IS the UciProtocol object returned by popen_uci.
            # If UciProtocol doesn't have configure, this might still fail.
            # Let's try the user's suggestion directly first.
            print("[Debug] Configuring engine using configure (async)...")
            options_to_set = {"Skill Level": self.skill_level}
            if self.variant == "chess960":
                # UCI_Chess960 option typically expects a boolean or string "true"/"false".
                # Assuming configure handles this conversion or expects boolean.
                options_to_set["UCI_Chess960"] = True
            await self.engine.configure(options_to_set) # Use configure as suggested
            print("[Debug] Configuration successful.")

            # Position is set implicitly when calling play/analyse or explicitly via send_command
            # No explicit position call needed here.
            print("[Debug] Engine configured. Position will be set on first play/analyse call.")

            print(f"Stockfish engine configured for {self.variant} with skill level {self.skill_level}.")

        except FileNotFoundError as e:
             print(f"[Error] Stockfish executable not found: {e}")
             self.engine = None
             # Notify the user in the channel if the message exists
             if self.message:
                 # ... (rest of existing error handling for this block)
                 try:
                     if hasattr(self, '_interaction') and self._interaction and not self._interaction.response.is_done():
                          await self._interaction.followup.send(f"Error: Could not start the chess engine: {e}", ephemeral=True)
                     else:
                          await self.message.channel.send(f"Error: Could not start the chess engine: {e}")
                 except (discord.Forbidden, discord.HTTPException):
                     pass
             if not self.is_finished(): self.stop()
        except OSError as e:
             print(f"[Error] OS error during engine start: {e}")
             self.engine = None
             # Notify the user in the channel if the message exists
             if self.message:
                 # ... (rest of existing error handling for this block)
                 try:
                     if hasattr(self, '_interaction') and self._interaction and not self._interaction.response.is_done():
                          await self._interaction.followup.send(f"Error: Could not start the chess engine: {e}", ephemeral=True)
                     else:
                          await self.message.channel.send(f"Error: Could not start the chess engine: {e}")
                 except (discord.Forbidden, discord.HTTPException):
                     pass
             if not self.is_finished(): self.stop()
        except chess.engine.EngineError as e:
             print(f"[Error] Chess engine error during start/config: {e}")
             if engine_protocol:
                 try: await engine_protocol.quit()
                 except: pass
             if transport:
                 transport.close()
             self.engine = None
             self._engine_transport = None
             # Notify the user in the channel if the message exists
             if self.message:
                 # ... (rest of existing error handling for this block)
                 try:
                     if hasattr(self, '_interaction') and self._interaction and not self._interaction.response.is_done():
                          await self._interaction.followup.send(f"Error: Could not start the chess engine: {e}", ephemeral=True)
                     else:
                          await self.message.channel.send(f"Error: Could not start the chess engine: {e}")
                 except (discord.Forbidden, discord.HTTPException):
                     pass
             if not self.is_finished(): self.stop()
        except Exception as e:
            # Catch the specific error if possible, otherwise print generic
            print(f"[Error] Unexpected error during engine start: {e}")
            print(f"[Debug] Type of error: {type(e)}") # Print the type of the exception
            if "can't be used in 'await' expression" in str(e):
                 print("[Debug] Caught the specific 'await' expression error.")
            if engine_protocol:
                 try: await engine_protocol.quit()
                 except: pass
            if transport:
                 transport.close()
            self.engine = None
            self._engine_transport = None
            # Notify the user in the channel if the message exists
            if self.message:
                try:
                    # Use followup if interaction is available and not done
                    if hasattr(self, '_interaction') and self._interaction and not self._interaction.response.is_done():
                         await self._interaction.followup.send(f"Error: Could not start the chess engine: {e}", ephemeral=True)
                    else:
                         await self.message.channel.send(f"Error: Could not start the chess engine: {e}")
                except (discord.Forbidden, discord.HTTPException):
                    pass # Can't send message
            if not self.is_finished():
                self.stop() # Stop the view if engine fails and view hasn't already stopped

    async def handle_player_move(self, interaction: discord.Interaction, move: chess.Move):
        """Handles the player's validated legal move."""
        # Add move to PGN
        self.pgn_node = self.pgn_node.add_variation(move)

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
        await self.update_message(interaction, status_prefix="Bot is thinking...")

        # Trigger bot's move asynchronously
        # We don't await this directly, as it can take time.
        # The update_message above gives immediate feedback.
        asyncio.create_task(self.make_bot_move())

    async def make_bot_move(self):
        """Lets the Stockfish engine make a move using the async protocol."""
        if self.engine is None or self.board.turn != self.bot_color or self.is_thinking or self.is_finished():
            return # Engine not ready, not bot's turn, already thinking, or game ended

        self.is_thinking = True
        try:
            # Position is set implicitly by the play method when passed the board
            # No explicit position call needed here.

            # Use the protocol's play method (ASYNC)
            print("[Debug] Awaiting engine.play...")
            result = await self.engine.play(self.board, chess.engine.Limit(time=self.think_time))
            print(f"[Debug] engine.play completed. Result: {result}")

            # Check if the view is still active before proceeding
            if self.is_finished():
                print("ChessBotView: Game ended while bot was thinking.")
                return

            if result.move:
                # Add bot's move to PGN
                self.pgn_node = self.pgn_node.add_variation(result.move)

                self.board.push(result.move)
                self.last_move = result.move

                # Update player's DM
                asyncio.create_task(self._send_or_update_dm())

                # Check game state *after* bot's move
                outcome = self.board.outcome()
                if outcome:
                    # Need a way to update the message; use self.message if available
                    if self.message:
                         # Pass the message object directly to end_game
                         await self.end_game(self.message, self.get_game_over_message(outcome))
                    else: # Should not happen if game started correctly
                         print("ChessBotView Error: Cannot end game after bot move, self.message is None.")
                    return # Important: return after ending the game

                # Update message for player's turn
                if self.message and not self.is_finished(): # Check if view is still active
                    await self.update_message(self.message, status_prefix="Your turn.")
            else:
                 print("ChessBotView: Engine returned no best move (result.move is None).")
                 if self.message and not self.is_finished():
                     await self.update_message(self.message, status_prefix="Bot failed to find a move. Your turn?")

        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, Exception) as e:
            print(f"Error during bot move analysis: {e}")
            if self.message and not self.is_finished():
                 try:
                     # Try to inform the user about the error
                     await self.update_message(self.message, status_prefix=f"Error during bot move: {e}. Your turn?")
                 except: pass # Ignore errors editing message here
            # Consider stopping the game if the engine has issues
            await self.stop_engine()
            if not self.is_finished():
                self.stop() # Stop the view as well
        finally:
            # Ensure is_thinking is reset even if errors occur or game ends mid-thought
            self.is_thinking = False

    # --- Message and State Management ---

    async def update_message(self, interaction_or_message: Union[discord.Interaction, discord.Message], status_prefix: str = ""):
        """Updates the game message with the current board image and status."""
        content = self.get_board_message(status_prefix)
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE))

        try:
            if isinstance(interaction_or_message, discord.Interaction):
                # If interaction hasn't been responded to (e.g., initial send)
                if not interaction_or_message.response.is_done():
                     await interaction_or_message.response.edit_message(content=content, attachments=[board_image], view=self)
                # If interaction was deferred (e.g., after modal submit)
                else:
                     await interaction_or_message.edit_original_response(content=content, attachments=[board_image], view=self)
            elif isinstance(interaction_or_message, discord.Message):
                 await interaction_or_message.edit(content=content, attachments=[board_image], view=self)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"ChessBotView: Failed to update message: {e}")
            # If message update fails, stop the game to prevent inconsistent state
            await self.stop_engine()
            self.stop()

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
        winner_text = ""
        if outcome.winner == self.player_color:
            winner_text = f"{self.player.mention} ({'White' if self.player_color == chess.WHITE else 'Black'}) wins!"
        elif outcome.winner == self.bot_color:
            winner_text = f"Bot ({'White' if self.bot_color == chess.WHITE else 'Black'}) wins!"
        else:
            winner_text = "It's a draw!"

        termination_reason = outcome.termination.name.replace("_", " ").title()
        return f"Game Over! **{winner_text} by {termination_reason}**"

    async def end_game(self, interaction_or_message: Union[discord.Interaction, discord.Message], message_content: str):
        """Ends the game, disables buttons, stops the engine, and updates the message."""
        if self.is_finished(): return # Avoid double execution

        await self.disable_all_buttons()
        await self.disable_all_buttons()
        await self.stop_engine() # Ensure engine is closed before stopping view

        # Update DM with final result
        await self._send_or_update_dm(result=message_content)

        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE)) # Show final board

        # Use a consistent way to get the interaction or message object
        target_message = None
        interaction = None
        if isinstance(interaction_or_message, discord.Interaction):
            interaction = interaction_or_message
            # Try to get the original message if possible, otherwise use interaction context
            try:
                target_message = await interaction.original_response()
            except discord.NotFound:
                 target_message = None # Fallback below
        elif isinstance(interaction_or_message, discord.Message):
            target_message = interaction_or_message

        try:
            if interaction and interaction.response.is_done():
                 # If interaction was deferred or responded to, edit original response
                 await interaction.edit_original_response(content=message_content, attachments=[board_image], view=self)
            elif interaction and not interaction.response.is_done():
                 # If interaction is fresh (e.g., resign button directly), edit its message
                 await interaction.response.edit_message(content=message_content, attachments=[board_image], view=self)
            elif target_message:
                 # If we only have the message object (e.g., bot move leads to game end)
                 await target_message.edit(content=message_content, attachments=[board_image], view=self)
            else:
                 print("ChessBotView: Could not determine message/interaction to edit for game end.")

        except (discord.NotFound, discord.HTTPException) as e:
             print(f"ChessBotView: Failed to edit message on game end: {e}")
             # Attempt to send a new message if editing failed
             channel = target_message.channel if target_message else (interaction.channel if interaction else None)
             if channel:
                 try:
                     await channel.send(content=message_content, files=[board_image])
                 except discord.Forbidden:
                     print("ChessBotView: Missing permissions to send final game message.")

        self.stop() # Stop the view itself AFTER attempting message update

    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        # Don't edit the message here, let end_game or on_timeout handle the final update

    async def stop_engine(self):
        """Safely quits the chess engine using the async protocol and transport."""
        engine_protocol = self.engine
        transport = self._engine_transport
        self.engine = None # Set to None immediately
        self._engine_transport = None # Clear transport reference

        if engine_protocol:
            try:
                # protocol.quit() is ASYNC
                print("[Debug] Awaiting engine.quit()...")
                await engine_protocol.quit()
                print("Stockfish engine quit command sent successfully.")
            except (chess.engine.EngineError, chess.engine.EngineTerminatedError, Exception) as e:
                print(f"Error sending quit command to Stockfish engine: {e}")

        if transport:
            try:
                print("[Debug] Closing engine transport...")
                transport.close()
                print("Engine transport closed.")
            except Exception as e:
                print(f"Error closing engine transport: {e}")


    async def on_timeout(self):
        if not self.is_finished(): # Only act if not already stopped
            timeout_msg = f"Chess game for {self.player.mention} timed out."
        await self.end_game(self.message, timeout_msg) # Use end_game to handle cleanup and message update

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print(f"Error in ChessBotView interaction (item: {item}): {error}")
        # Try to send an ephemeral message about the error
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        except Exception as e:
            print(f"ChessBotView: Failed to send error response: {e}")

        # Stop the game on error to be safe
        await self.end_game(interaction, f"An error occurred, stopping the game: {error}")

    # --- DM Helper Methods (Adapted for Bot Game) ---

    async def _get_dm_content(self, result: Optional[str] = None) -> str:
        """Generates the FEN and PGN content for the player's DM."""
        fen = self.board.fen()
        opponent_name = f"Bot (Skill {self.skill_level})"
        opponent_color_str = "Black" if self.player_color == chess.WHITE else "White"

        # Update PGN headers if result is provided and game is over
        if result:
            pgn_result_code = "*" # Default
            if result in ["1-0", "0-1", "1/2-1/2"]:
                pgn_result_code = result
            elif "wins" in result:
                if (self.player_color == chess.WHITE and "White" in result) or \
                   (self.player_color == chess.BLACK and "Black" in result):
                    pgn_result_code = "1-0" if self.player_color == chess.WHITE else "0-1" # Player won
                else:
                    pgn_result_code = "0-1" if self.player_color == chess.WHITE else "1-0" # Bot won
            elif "draw" in result:
                pgn_result_code = "1/2-1/2"
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
