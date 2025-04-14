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

# --- Add this helper function ---
def generate_board_image(board: chess.Board, last_move: Optional[chess.Move] = None, perspective_white: bool = True) -> discord.File:
    """Generates an image representation of the chess board."""
    SQUARE_SIZE = 60
    BOARD_SIZE = 8 * SQUARE_SIZE
    LIGHT_COLOR = (240, 217, 181) # Light wood
    DARK_COLOR = (181, 136, 99)  # Dark wood
    HIGHLIGHT_LIGHT = (205, 210, 106, 180) # Semi-transparent yellow for light squares
    HIGHLIGHT_DARK = (170, 162, 58, 180)   # Semi-transparent yellow for dark squares
    MARGIN = 30  # Add margin for rank and file labels
    TOTAL_SIZE = BOARD_SIZE + 2 * MARGIN
    
    # Create image with margins
    img = Image.new("RGB", (TOTAL_SIZE, TOTAL_SIZE), (50, 50, 50))  # Dark gray background
    draw = ImageDraw.Draw(img, "RGBA") # Use RGBA for transparency support    # Load the bundled DejaVu Sans font
    font = None
    label_font = None
    font_size = int(SQUARE_SIZE * 0.8)
    label_font_size = int(SQUARE_SIZE * 0.4)
    try:
        # Construct path relative to this script file
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        PROJECT_ROOT = os.path.dirname(SCRIPT_DIR) # Go up one level from cogs
        FONT_DIR_NAME = "dejavusans" # Directory specified by user
        FONT_FILE_NAME = "DejaVuSans.ttf"
        font_path = os.path.join(PROJECT_ROOT, FONT_DIR_NAME, FONT_FILE_NAME)

        font = ImageFont.truetype(font_path, font_size)
        label_font = ImageFont.truetype(font_path, label_font_size)
        print(f"[Debug] Loaded font from bundled path: {font_path}")
    except IOError:
        print(f"Warning: Could not load bundled font at '{font_path}'. Using default font. Chess pieces might not render correctly.")
        font = ImageFont.load_default() # Fallback
        label_font = ImageFont.load_default() # Fallback for labels too    # Determine squares to highlight based on the last move
    highlight_squares = set()
    if last_move:
        highlight_squares.add(last_move.from_square)
        highlight_squares.add(last_move.to_square)

    for rank in range(8):
        for file in range(8):
            square = chess.square(file, rank)
            # Flip board if perspective is black
            display_rank = rank if perspective_white else 7 - rank
            display_file = file if perspective_white else 7 - file

            x0 = MARGIN + display_file * SQUARE_SIZE
            y0 = MARGIN + (7 - display_rank) * SQUARE_SIZE # Y is inverted in PIL
            x1 = x0 + SQUARE_SIZE
            y1 = y0 + SQUARE_SIZE

            # Draw square color
            is_light = (rank + file) % 2 != 0
            color = LIGHT_COLOR if is_light else DARK_COLOR
            draw.rectangle([x0, y0, x1, y1], fill=color)

            # Draw highlight if applicable
            if square in highlight_squares:
                 highlight_color = HIGHLIGHT_LIGHT if is_light else HIGHLIGHT_DARK
                 draw.rectangle([x0, y0, x1, y1], fill=highlight_color)

    # Load piece images from the pieces-png directory
    PIECES_DIR = os.path.join(PROJECT_ROOT, "pieces-png")
    piece_images = {}
    for color in ["white", "black"]:
        for piece in ["king", "queen", "rook", "bishop", "knight", "pawn"]:
            piece_key = f"{color}-{piece}"
            piece_path = os.path.join(PIECES_DIR, f"{piece_key}.png")
            try:
                piece_images[piece_key] = Image.open(piece_path).convert("RGBA")
            except IOError:
                print(f"Warning: Could not load image for {piece_key} at {piece_path}.")

    # Draw pieces using PNG images
    for rank in range(8):
        for file in range(8):
            square = chess.square(file, rank)
            # Flip board if perspective is black
            display_rank = rank if perspective_white else 7 - rank
            display_file = file if perspective_white else 7 - file

            x0 = MARGIN + display_file * SQUARE_SIZE
            y0 = MARGIN + (7 - display_rank) * SQUARE_SIZE # Y is inverted in PIL

            # Draw piece
            piece = board.piece_at(square)
            if piece:
                piece_color = "white" if piece.color == chess.WHITE else "black"
                piece_type = piece.piece_type
                piece_name = {
                    chess.KING: "king",
                    chess.QUEEN: "queen",
                    chess.ROOK: "rook",
                    chess.BISHOP: "bishop",
                    chess.KNIGHT: "knight",
                    chess.PAWN: "pawn"
                }.get(piece_type, None)
# ...existing code...
                if piece_name:
                    piece_key = f"{piece_color}-{piece_name}"
                    piece_image = piece_images.get(piece_key)
                    if piece_image:
                        # Use Image.Resampling.LANCZOS instead of Image.ANTIALIAS
                        piece_image_resized = piece_image.resize((SQUARE_SIZE, SQUARE_SIZE), Image.Resampling.LANCZOS)
                        img.paste(piece_image_resized, (x0, y0), piece_image_resized)

    # Draw file labels (a-h) along the bottom
# ...existing code...
    text_color = (220, 220, 220)  # Light gray color for labels
    for file in range(8):
        # Determine the correct file label based on perspective
        display_file = file if perspective_white else 7 - file
        file_label = chr(97 + display_file)  # 97 is ASCII for 'a'
        
        # Position for the file label (bottom)
        x = MARGIN + file * SQUARE_SIZE + SQUARE_SIZE // 2
        y = MARGIN + 8 * SQUARE_SIZE + MARGIN // 2
        
        # Calculate text position for centering
        try:
            bbox = draw.textbbox((0, 0), file_label, font=label_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x - text_width // 2
            text_y = y - text_height // 2
        except AttributeError:
            # Fallback for older Pillow versions
            try:
                text_width, text_height = draw.textsize(file_label, font=label_font)
            except:
                text_width, text_height = label_font.getsize(file_label)
            text_x = x - text_width // 2
            text_y = y - text_height // 2
        
        draw.text((text_x, text_y), file_label, fill=text_color, font=label_font)
        
    # Draw rank labels (1-8) along the side
    for rank in range(8):
        # Determine the correct rank label based on perspective
        display_rank = rank if perspective_white else 7 - rank
        rank_label = str(8 - display_rank)  # Ranks go from 8 to 1
        
        # Position for the rank label (left side)
        x = MARGIN // 2
        y = MARGIN + display_rank * SQUARE_SIZE + SQUARE_SIZE // 2
        
        # Calculate text position for centering
        try:
            bbox = draw.textbbox((0, 0), rank_label, font=label_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x - text_width // 2
            text_y = y - text_height // 2
        except AttributeError:
            # Fallback for older Pillow versions
            try:
                text_width, text_height = draw.textsize(rank_label, font=label_font)
            except:
                text_width, text_height = label_font.getsize(rank_label)
            text_x = x - text_width // 2
            text_y = y - text_height // 2
        
        draw.text((text_x, text_y), rank_label, fill=text_color, font=label_font)

    # Save image to a bytes buffer
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    return discord.File(fp=img_byte_arr, filename="chess_board.png")

class MoveInputModal(ui.Modal, title='Enter Your Move'):
    move_input = ui.TextInput(
        label='Move (e.g., e4, Nf3, O-O)',
        placeholder='Enter move in algebraic notation (SAN or UCI)',
        required=True,
        style=discord.TextStyle.short,
        max_length=10 # e.g., e8=Q# is 5, allow some buffer
    )

    def __init__(self, game_view: Union['ChessView', 'ChessBotView']):
        super().__init__(timeout=120.0) # 2 minute timeout for modal
        self.game_view = game_view

    async def on_submit(self, interaction: discord.Interaction):
        move_text = self.move_input.value.strip()
        board = self.game_view.board
        move = None

        try:
            move = board.parse_san(move_text)
            if not board.is_legal(move):
                await interaction.response.send_message(
                    f"Illegal move: '{move_text}' is not valid in the current position.",
                    ephemeral=True
                )
                return
        except ValueError:
            try:
                move = board.parse_uci(move_text)
                if not board.is_legal(move):
                    await interaction.response.send_message(
                        f"Illegal move: '{move_text}' is not valid in the current position.",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    f"Invalid move format or illegal move: '{move_text}'. Use algebraic notation (e.g., Nf3, e4, O-O) or UCI (e.g., e2e4).",
                    ephemeral=True
                )
                return

        # Check if the parsed move is legal
        if move not in board.legal_moves:
            # Try to provide the SAN representation of the attempted move for clarity
            try:
                move_san = board.san(move)
            except ValueError: # If the move itself was fundamentally invalid (e.g., piece doesn't exist)
                move_san = move_text # Fallback to user input
            await interaction.response.send_message(
                f"Illegal move: '{move_san}' is not legal in the current position.",
                ephemeral=True
            )
            return

        # Defer interaction here as move processing might take time (esp. for bot game)
        await interaction.response.defer() # Acknowledge modal submission

        # Process the valid move in the respective view
        if isinstance(self.game_view, ChessView):
            await self.game_view.handle_move(interaction, move)
        elif isinstance(self.game_view, ChessBotView):
            await self.game_view.handle_player_move(interaction, move)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Error in MoveInputModal: {error}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send("An error occurred submitting your move.", ephemeral=True)
            else:
                await interaction.response.send_message("An error occurred submitting your move.", ephemeral=True)
        except Exception as e:
            print(f"Failed to send error response in MoveInputModal: {e}")

# Removed ChessButton class (No longer used with image-based board)

class ChessView(ui.View):
    def __init__(self, white_player: discord.Member, black_player: discord.Member, board: Optional[chess.Board] = None):
        super().__init__(timeout=600.0)  # 10 minute timeout
        self.white_player = white_player
        self.black_player = black_player
        self.board = board if board else chess.Board() # Use provided board or create new
        # Determine current player based on board state
        self.current_player = self.white_player if self.board.turn == chess.WHITE else self.black_player
        self.message: Optional[discord.Message] = None
        self.last_move: Optional[chess.Move] = None # Store last move for highlighting
        self.white_dm_message: Optional[discord.Message] = None # DM message for white player
        self.black_dm_message: Optional[discord.Message] = None # DM message for black player
        self.game_pgn = chess.pgn.Game() # Initialize PGN game object
        self.game_pgn.headers["Event"] = "Discord Chess Game"
        self.game_pgn.headers["Site"] = "Discord"
        self.game_pgn.headers["White"] = self.white_player.display_name
        self.game_pgn.headers["Black"] = self.black_player.display_name
        # If starting from a non-standard position, set FEN header and setup board
        if board:
             self.game_pgn.setup(board) # Setup PGN from the board state
        else: # Standard starting position
             # Setup with the initial board state even if it's standard, ensures node exists
             self.game_pgn.setup(self.board)
        self.pgn_node = self.game_pgn # Track the current node for adding moves

        # Add control buttons
        self.add_item(self.MakeMoveButton())
        self.add_item(self.ResignButton())

    # --- Button Definitions ---

    class MakeMoveButton(ui.Button):
        def __init__(self):
            super().__init__(label="Make Move", style=discord.ButtonStyle.primary, custom_id="chess_make_move")

        async def callback(self, interaction: discord.Interaction):
            view: 'ChessView' = self.view
            # Check if it's the correct player's turn before showing modal
            if interaction.user != view.current_player:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            # Open the modal for move input
            await interaction.response.send_modal(MoveInputModal(game_view=view))

    class ResignButton(ui.Button):
        def __init__(self):
            super().__init__(label="Resign", style=discord.ButtonStyle.danger, custom_id="chess_resign")

        async def callback(self, interaction: discord.Interaction):
            view: 'ChessView' = self.view
            resigning_player = interaction.user
            # Check if the resigner is part of the game
            if resigning_player.id not in [view.white_player.id, view.black_player.id]:
                 await interaction.response.send_message("You are not part of this game.", ephemeral=True)
                 return
            winner = view.black_player if resigning_player == view.white_player else view.white_player
            await view.end_game(interaction, f"{resigning_player.mention} resigned. {winner.mention} wins! 🏳️")

    # --- Helper Methods ---

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Checks are now mostly handled within button callbacks for clarity."""
        # Basic check: is the user part of the game?
        if interaction.user.id not in [self.white_player.id, self.black_player.id]:
            await interaction.response.send_message("You are not part of this game.", ephemeral=True)
            return False
        # Specific turn checks are done in MakeMoveButton callback and MoveInputModal submission
        return True

    async def _get_dm_content(self, player_perspective: discord.Member, result: Optional[str] = None) -> str:
        """Generates the FEN and PGN content for the DM from a specific player's perspective."""
        fen = self.board.fen()
        opponent = self.black_player if player_perspective == self.white_player else self.white_player
        opponent_color_str = "Black" if player_perspective == self.white_player else "White"

        # Update PGN headers if result is provided and game is over
        if result:
            pgn_result_code = "*" # Default for ongoing or unknown
            if result in ["1-0", "0-1", "1/2-1/2"]:
                pgn_result_code = result
            elif "wins" in result:
                if self.white_player.mention in result: pgn_result_code = "1-0"
                elif self.black_player.mention in result: pgn_result_code = "0-1"
            elif "draw" in result:
                pgn_result_code = "1/2-1/2"
            # Only update if not already set or if changing from '*'
            if "Result" not in self.game_pgn.headers or self.game_pgn.headers["Result"] == "*":
                 self.game_pgn.headers["Result"] = pgn_result_code

        # Use an exporter for cleaner PGN output
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        pgn_string = self.game_pgn.accept(exporter)
        # Limit PGN length in DM preview
        pgn_preview = pgn_string[:1500] + "..." if len(pgn_string) > 1500 else pgn_string

        content = f"Use `/loadchess` to restore this game from FEN or PGN.\n\n" \
              f"**Game vs {opponent.display_name}** ({opponent_color_str})\n\n" \
              f"**FEN:**\n`{fen}`\n\n" \
              f"**PGN:**\n```pgn\n{pgn_preview}\n```"

        if result:
            content += f"\n\n**Status:** {result}" # Always show the descriptive status message

        return content

    async def _send_or_update_dm(self, player: discord.Member, result: Optional[str] = None):
        """Sends or updates the DM with FEN and PGN for a specific player."""
        is_white = (player == self.white_player)
        dm_message_attr = "white_dm_message" if is_white else "black_dm_message"
        dm_message: Optional[discord.Message] = getattr(self, dm_message_attr, None)

        try:
            content = await self._get_dm_content(player_perspective=player, result=result)
            dm_channel = player.dm_channel or await player.create_dm()

            if dm_message:
                try:
                    await dm_message.edit(content=content)
                    # print(f"Successfully edited DM for {player.display_name}") # Debug
                    return # Edited successfully
                except discord.NotFound:
                    print(f"DM message for {player.display_name} not found, will send a new one.")
                    setattr(self, dm_message_attr, None)
                    dm_message = None
                except discord.Forbidden:
                    print(f"Cannot edit DM for {player.display_name} (Forbidden). DMs might be closed or message deleted.")
                    setattr(self, dm_message_attr, None)
                    dm_message = None
                except discord.HTTPException as e:
                    print(f"HTTP error editing DM for {player.display_name}: {e}. Will try sending.")
                    setattr(self, dm_message_attr, None)
                    dm_message = None

            if dm_message is None:
                new_dm_message = await dm_channel.send(content=content)
                setattr(self, dm_message_attr, new_dm_message)
                # print(f"Successfully sent new DM to {player.display_name}") # Debug

        except discord.Forbidden:
            print(f"Cannot send DM to {player.display_name} (Forbidden). User likely has DMs disabled.")
            setattr(self, dm_message_attr, None)
        except discord.HTTPException as e:
            print(f"Failed to send/edit DM for {player.display_name}: {e}")
            setattr(self, dm_message_attr, None)
        except Exception as e:
            print(f"Unexpected error sending/updating DM for {player.display_name}: {e}")
            setattr(self, dm_message_attr, None)

    async def handle_move(self, interaction: discord.Interaction, move: chess.Move):
        """Handles a validated legal move submitted via the modal."""
        self.board.push(move)
        self.last_move = move # Store for highlighting

        # Switch turns
        self.current_player = self.black_player if self.current_player == self.white_player else self.white_player

        # Check for game end
        outcome = self.board.outcome()
        if outcome:
            await self.end_game(interaction, self.get_game_over_message(outcome))
            return

        # Update the message with the new board state
        await self.update_message(interaction)

    async def update_message(self, interaction_or_message: Union[discord.Interaction, discord.Message], status_prefix: str = ""):
        """Updates the game message with the current board image and status."""
        turn_color = "White" if self.board.turn == chess.WHITE else "Black"
        status = f"{status_prefix}Turn: **{self.current_player.mention}** ({turn_color})"
        if self.board.is_check():
            status += " **Check!**"

        fen_string = self.board.fen()
        content = f"Chess: {self.white_player.mention} (White) vs {self.black_player.mention} (Black)\n\n{status}\nFEN: `{fen_string}`"
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.current_player == self.white_player))

        # Determine how to edit the message
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
            print(f"ChessView: Failed to update message: {e}")
            # Handle potential errors like message deleted or permissions lost

    def get_game_over_message(self, outcome: chess.Outcome) -> str:
        """Generates the game over message based on the outcome."""
        if outcome.winner == chess.WHITE:
            winner_mention = self.white_player.mention
            loser_mention = self.black_player.mention
        elif outcome.winner == chess.BLACK:
            winner_mention = self.black_player.mention
            loser_mention = self.white_player.mention
        else: # Draw
            winner_mention = "Nobody" # Or maybe mention both?

        termination_reason = outcome.termination.name.replace("_", " ").title()

        if outcome.winner is not None:
            message = f"Game Over! **{winner_mention}** ({'White' if outcome.winner == chess.WHITE else 'Black'}) wins by {termination_reason}! 🎉"
        else: # Draw
            message = f"Game Over! It's a draw by {termination_reason}! 🤝"

        return message

    async def end_game(self, interaction: discord.Interaction, message_content: str):
        """Ends the game, disables buttons, stops the engine, and updates the message."""
        """Ends the game, disables buttons, stops the engine, and updates the message."""
        # --- This method belongs to ChessView, not ChessBotView ---
        # --- The search block matched the wrong end_game method ---
        # --- Reverting this specific change ---
        await self.disable_all_buttons()
        # await self.stop_engine() # No engine in ChessView

        # Update DMs with the final result
        dm_update_tasks = [
            self._send_or_update_dm(self.white_player, result=message_content),
            self._send_or_update_dm(self.black_player, result=message_content)
        ]
        await asyncio.gather(*dm_update_tasks)

        board_image = generate_board_image(self.board, self.last_move, perspective_white=True) # Final board perspective

        try:
            if interaction.response.is_done():
                # If interaction was already responded to, use followup
                await interaction.followup.send(content=message_content, file=board_image)
            else:
                # Edit the interaction response if still valid
                await interaction.response.edit_message(content=message_content, attachments=[board_image], view=self)
        except discord.NotFound:
            # If the original message is gone, send a new message
            if interaction.channel:
                await interaction.channel.send(content=message_content, file=board_image)
        except Exception as e:
            print(f"ChessBotView: Failed to edit or send game end message: {e}")

        self.stop()

    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        # Don't edit the message here, let end_game or on_timeout handle the final update

    async def on_timeout(self):
        if self.message and not self.is_finished():
            await self.disable_all_buttons()
            timeout_msg = f"Chess game between {self.white_player.mention} and {self.black_player.mention} timed out."
            board_image = generate_board_image(self.board, self.last_move, perspective_white=True) # Default perspective on timeout
            try:
                await self.message.edit(content=timeout_msg, attachments=[board_image], view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass # Ignore if message is gone or cannot be edited
        self.stop()
