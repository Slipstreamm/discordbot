import typing
import discord
from discord import ui
from typing import Optional, Union
import chess
import chess.pgn # Import PGN library
from PIL import Image, ImageDraw, ImageFont # Added Pillow imports
import io # Added io import
import os

# Forward declare the view classes used in MoveInputModal type hint
# This avoids circular imports if utils are imported by the views
if typing.TYPE_CHECKING:
    from .chess_pvp import ChessView
    from .chess_bot import ChessBotView

# --- Board Image Generation ---
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
    draw = ImageDraw.Draw(img, "RGBA") # Use RGBA for transparency support

    # Load the bundled DejaVu Sans font
    font = None
    label_font = None
    font_size = int(SQUARE_SIZE * 0.8) # Piece font size (not used for images)
    label_font_size = int(SQUARE_SIZE * 0.4) # Rank/File label font size
    try:
        # Construct path relative to this script file
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR)) # Go up two levels (cogs/games -> cogs -> root)
        FONT_DIR_NAME = "dejavusans" # Directory specified by user
        FONT_FILE_NAME = "DejaVuSans.ttf"
        font_path = os.path.join(PROJECT_ROOT, FONT_DIR_NAME, FONT_FILE_NAME)

        # Only load label_font, piece font is not needed for image-based pieces
        label_font = ImageFont.truetype(font_path, label_font_size)
        print(f"[Debug] Loaded label font from bundled path: {font_path}")
    except IOError:
        print(f"Warning: Could not load bundled font at '{font_path}'. Using default font for labels.")
        label_font = ImageFont.load_default() # Fallback for labels

    # Determine squares to highlight based on the last move
    highlight_squares = set()
    if last_move:
        highlight_squares.add(last_move.from_square)
        highlight_squares.add(last_move.to_square)

    # Draw squares and highlights
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

    # Load piece images from the pieces-png directory (relative to project root)
    PIECES_DIR = os.path.join(PROJECT_ROOT, "pieces-png")
    piece_images = {}
    for color_name in ["white", "black"]:
        for piece_name in ["king", "queen", "rook", "bishop", "knight", "pawn"]:
            piece_key = f"{color_name}-{piece_name}"
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
                piece_color_name = "white" if piece.color == chess.WHITE else "black"
                piece_type_name = chess.piece_name(piece.piece_type) # e.g., 'knight'
                piece_key = f"{piece_color_name}-{piece_type_name}"
                piece_image = piece_images.get(piece_key)
                if piece_image:
                    # Use Image.Resampling.LANCZOS for high-quality resizing
                    piece_image_resized = piece_image.resize((SQUARE_SIZE, SQUARE_SIZE), Image.Resampling.LANCZOS)
                    # Paste piece onto the board image, using alpha channel for transparency
                    img.paste(piece_image_resized, (x0, y0), piece_image_resized)

    # Draw file labels (a-h) along the bottom
    text_color = (220, 220, 220)  # Light gray color for labels
    for file_idx in range(8):
        display_file_idx = file_idx if perspective_white else 7 - file_idx
        file_label = chr(ord('a') + display_file_idx)

        x = MARGIN + file_idx * SQUARE_SIZE + SQUARE_SIZE // 2
        y = MARGIN + BOARD_SIZE + MARGIN // 2 # Position below the board

        # Calculate text position for centering
        try:
            bbox = draw.textbbox((0, 0), file_label, font=label_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x - text_width // 2
            text_y = y - text_height // 2
        except AttributeError: # Fallback for older Pillow versions
            try: text_width, text_height = draw.textsize(file_label, font=label_font)
            except: text_width, text_height = label_font.getsize(file_label) # Older PIL
            text_x = x - text_width // 2
            text_y = y - text_height // 2

        draw.text((text_x, text_y), file_label, fill=text_color, font=label_font)

    # Draw rank labels (1-8) along the left side
    for rank_idx in range(8):
        display_rank_idx = rank_idx if perspective_white else 7 - rank_idx
        rank_label = str(8 - display_rank_idx) # Chess ranks are 1-8 from bottom up

        x = MARGIN // 2 # Position left of the board
        y = MARGIN + rank_idx * SQUARE_SIZE + SQUARE_SIZE // 2

        # Calculate text position for centering
        try:
            bbox = draw.textbbox((0, 0), rank_label, font=label_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x - text_width // 2
            text_y = y - text_height // 2
        except AttributeError: # Fallback for older Pillow versions
            try: text_width, text_height = draw.textsize(rank_label, font=label_font)
            except: text_width, text_height = label_font.getsize(rank_label) # Older PIL
            text_x = x - text_width // 2
            text_y = y - text_height // 2

        draw.text((text_x, text_y), rank_label, fill=text_color, font=label_font)

    # Save image to a bytes buffer
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    return discord.File(fp=img_byte_arr, filename="chess_board.png")


# --- Move Input Modal ---

class MoveInputModal(ui.Modal, title='Enter Your Move'):
    move_input = ui.TextInput(
        label='Move (e.g., e4, Nf3, O-O)',
        placeholder='Enter move in algebraic notation (SAN or UCI)',
        required=True,
        style=discord.TextStyle.short,
        max_length=10 # e.g., e8=Q# is 5, allow some buffer
    )

    # Use forward references in type hint to avoid circular import
    def __init__(self, game_view: Union['ChessView', 'ChessBotView']):
        super().__init__(timeout=120.0) # 2 minute timeout for modal
        self.game_view = game_view

    async def on_submit(self, interaction: discord.Interaction):
        move_text = self.move_input.value.strip()
        board = self.game_view.board
        move = None

        # Try parsing as SAN first, then UCI
        try:
            move = board.parse_san(move_text)
        except ValueError:
            try:
                move = board.parse_uci(move_text)
            except ValueError:
                await interaction.response.send_message(
                    f"Invalid move format: '{move_text}'. Use algebraic notation (e.g., Nf3, e4, O-O) or UCI (e.g., e2e4).",
                    ephemeral=True
                )
                return

        # Check if the parsed move is legal in the current position
        if move not in board.legal_moves:
            # Try to provide the SAN representation for clarity if possible
            try:
                move_san = board.san(move)
            except ValueError: # If the move itself was fundamentally invalid
                move_san = move_text # Fallback to user input
            await interaction.response.send_message(
                f"Illegal move: '{move_san}' is not legal in the current position.",
                ephemeral=True
            )
            return

        # Defer interaction here as move processing might take time (esp. for bot game)
        await interaction.response.defer() # Acknowledge modal submission

        # Process the valid move in the respective view's handler method
        # We rely on the game_view having a method like handle_move or handle_player_move
        if hasattr(self.game_view, 'handle_player_move') and callable(getattr(self.game_view, 'handle_player_move')):
             # Specifically for ChessBotView or similar views with this method
             await self.game_view.handle_player_move(interaction, move)
        elif hasattr(self.game_view, 'handle_move') and callable(getattr(self.game_view, 'handle_move')):
             # For ChessView or other views using this method name
             await self.game_view.handle_move(interaction, move)
        else:
             # Fallback or error if the view doesn't have a known move handler
             print(f"Error: MoveInputModal's game_view (type: {type(self.game_view)}) has no known move handler method.")
             await interaction.followup.send("Error processing move: Could not find handler in the game view.", ephemeral=True)


    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Error in MoveInputModal: {error}")
        try:
            # Use followup if already deferred/responded, otherwise use response
            if interaction.response.is_done():
                await interaction.followup.send("An error occurred submitting your move.", ephemeral=True)
            else:
                await interaction.response.send_message("An error occurred submitting your move.", ephemeral=True)
        except Exception as e:
            print(f"Failed to send error response in MoveInputModal: {e}")
