import discord
from discord import ui
import chess
import chess.engine
import chess.pgn
import platform
import os
from PIL import Image, ImageDraw, ImageFont
import io
import asyncio
from typing import Optional, List, Union

# --- Chess board image generation function ---
def generate_board_image(board: chess.Board, last_move: Optional[chess.Move] = None, perspective_white: bool = True, valid_moves: Optional[List[chess.Move]] = None) -> discord.File:
    """Generates an image representation of the chess board.
    
    Args:
        board: The chess board to render
        last_move: The last move made, to highlight source and destination squares
        perspective_white: Whether to show the board from white's perspective
        valid_moves: Optional list of valid moves to highlight with dots
    """
    SQUARE_SIZE = 60
    BOARD_SIZE = 8 * SQUARE_SIZE
    LIGHT_COLOR = (240, 217, 181) # Light wood
    DARK_COLOR = (181, 136, 99)  # Dark wood
    HIGHLIGHT_LIGHT = (205, 210, 106, 180) # Semi-transparent yellow for light squares
    HIGHLIGHT_DARK = (170, 162, 58, 180)   # Semi-transparent yellow for dark squares
    VALID_MOVE_COLOR = (100, 100, 100, 180) # Semi-transparent dark gray for valid move dots
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
        PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR)) # Go up two levels from games dir
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
                if piece_name:
                    piece_key = f"{piece_color}-{piece_name}"
                    piece_image = piece_images.get(piece_key)
                    if piece_image:
                        # Use Image.Resampling.LANCZOS instead of Image.ANTIALIAS
                        piece_image_resized = piece_image.resize((SQUARE_SIZE, SQUARE_SIZE), Image.Resampling.LANCZOS)
                        img.paste(piece_image_resized, (x0, y0), piece_image_resized)

    # Draw valid move dots if provided
    if valid_moves:
        valid_dest_squares = set()
        for move in valid_moves:
            valid_dest_squares.add(move.to_square)
        
        for square in valid_dest_squares:
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            
            # Flip coordinates if perspective is black
            display_rank = rank if perspective_white else 7 - rank
            display_file = file if perspective_white else 7 - file
            
            # Calculate center of square for dot
            center_x = MARGIN + display_file * SQUARE_SIZE + SQUARE_SIZE // 2
            center_y = MARGIN + (7 - display_rank) * SQUARE_SIZE + SQUARE_SIZE // 2
            
            # Draw a circle (dot) to indicate valid move
            dot_radius = SQUARE_SIZE // 6
            draw.ellipse(
                [(center_x - dot_radius, center_y - dot_radius), 
                 (center_x + dot_radius, center_y + dot_radius)], 
                fill=VALID_MOVE_COLOR
            )
    
    # Draw file labels (a-h) along the bottom
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

# --- Chess Game Modal for Move Input ---
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

# --- Chess Game (Player vs Player) ---
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
        
        # Button-driven move selection state
        self.move_selection_mode = False  # Whether we're in button-driven move selection mode
        self.selected_file = None  # Selected file (0-7) during move selection
        self.selected_rank = None  # Selected rank (0-7) during move selection
        self.selected_square = None  # Selected square (0-63) during move selection
        self.valid_moves = []  # List of valid moves from the selected square
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
        self.add_item(self.SelectMoveButton())
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

    class SelectMoveButton(ui.Button):
        """Button to start the button-driven move selection process."""
        def __init__(self):
            super().__init__(label="Select Move", style=discord.ButtonStyle.primary, custom_id="chess_select_move")
            
        async def callback(self, interaction: discord.Interaction):
            view: 'ChessView' = self.view
            # Check if it's the correct player's turn
            if interaction.user != view.current_player:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
                
            # Start the move selection process
            view.move_selection_mode = True
            view.selected_file = None
            view.selected_rank = None
            view.selected_square = None
            view.valid_moves = []
            
            # Show file selection buttons
            await view.show_file_selection(interaction)
    
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

    # --- Button Classes for Move Selection ---
    
    class FileButton(ui.Button):
        """Button for selecting a file (A-H) in the first phase of move selection."""
        def __init__(self, file_idx: int):
            self.file_idx = file_idx
            file_label = chr(65 + file_idx)  # 65 is ASCII for 'A'
            super().__init__(label=file_label, style=discord.ButtonStyle.primary)
            
        async def callback(self, interaction: discord.Interaction):
            view: 'ChessView' = self.view
            
            # Basic checks
            if interaction.user != view.current_player:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
                
            # Store the selected file and show rank buttons
            view.selected_file = self.file_idx
            view.selected_rank = None
            view.selected_square = None
            
            # Show rank selection buttons
            await view.show_rank_selection(interaction)
    
    class RankButton(ui.Button):
        """Button for selecting a rank (1-8) in the first phase of move selection."""
        def __init__(self, rank_idx: int):
            self.rank_idx = rank_idx
            rank_label = str(8 - rank_idx)  # Ranks are displayed as 8 to 1
            super().__init__(label=rank_label, style=discord.ButtonStyle.primary)
            
        async def callback(self, interaction: discord.Interaction):
            view: 'ChessView' = self.view
            
            # Basic checks
            if interaction.user != view.current_player:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
                
            # Calculate the square index
            file_idx = view.selected_file
            rank_idx = self.rank_idx
            square = chess.square(file_idx, 7 - rank_idx)  # Convert to chess.py square index
            
            # Check if the square has a piece of the current player's color
            piece = view.board.piece_at(square)
            if piece is None or piece.color != view.board.turn:
                await interaction.response.send_message("You must select a square with one of your pieces.", ephemeral=True)
                # Go back to file selection
                await view.show_file_selection(interaction)
                return
                
            # Find valid moves from this square
            valid_moves = [move for move in view.board.legal_moves if move.from_square == square]
            if not valid_moves:
                await interaction.response.send_message("This piece has no legal moves.", ephemeral=True)
                # Go back to file selection
                await view.show_file_selection(interaction)
                return
                
            # Store the selected square and valid moves
            view.selected_square = square
            view.valid_moves = valid_moves
            
            # Show valid move buttons
            await view.show_valid_moves(interaction)
    
    class MoveButton(ui.Button):
        """Button for selecting a destination square in the second phase of move selection."""
        def __init__(self, move: chess.Move):
            self.move = move
            # Get the destination square coordinates
            file_idx = chess.square_file(move.to_square)
            rank_idx = chess.square_rank(move.to_square)
            # Create label in algebraic notation (e.g., "e4")
            label = f"{chr(97 + file_idx)}{rank_idx + 1}"
            super().__init__(label=label, style=discord.ButtonStyle.success)
            
        async def callback(self, interaction: discord.Interaction):
            view: 'ChessView' = self.view
            
            # Basic checks
            if interaction.user != view.current_player:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
                
            # Execute the move
            await interaction.response.defer()  # Acknowledge the interaction
            await view.handle_move(interaction, self.move)
    
    # --- Button-Driven Move Selection Methods ---
    
    async def show_file_selection(self, interaction: discord.Interaction):
        """Shows buttons for selecting a file (A-H)."""
        # Clear existing buttons
        self.clear_items()
        
        # Add file selection buttons (A-H)
        for file_idx in range(8):
            self.add_item(self.FileButton(file_idx))
            
        # Add a cancel button to return to normal view
        cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_move_selection")
        cancel_button.callback = self._cancel_move_selection_callback
        self.add_item(cancel_button)
        
        # Update the message
        turn_color = "White" if self.board.turn == chess.WHITE else "Black"
        content = f"Chess: {self.white_player.mention} (White) vs {self.black_player.mention} (Black)\n\nSelect a file (A-H) to choose a piece.\nTurn: **{self.current_player.mention}** ({turn_color})"
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.current_player == self.white_player))
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, attachments=[board_image], view=self)
        else:
            await interaction.response.edit_message(content=content, attachments=[board_image], view=self)
    
    async def show_rank_selection(self, interaction: discord.Interaction):
        """Shows buttons for selecting a rank (1-8)."""
        # Clear existing buttons
        self.clear_items()
        
        # Add rank selection buttons (1-8)
        for rank_idx in range(8):
            self.add_item(self.RankButton(rank_idx))
            
        # Add a back button to return to file selection
        back_button = ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="back_to_file_selection")
        back_button.callback = self._back_to_file_selection_callback
        self.add_item(back_button)
        
        # Add a cancel button to return to normal view
        cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_move_selection")
        cancel_button.callback = self._cancel_move_selection_callback
        self.add_item(cancel_button)
        
        # Update the message
        turn_color = "White" if self.board.turn == chess.WHITE else "Black"
        file_letter = chr(65 + self.selected_file)  # Convert to A-H
        content = f"Chess: {self.white_player.mention} (White) vs {self.black_player.mention} (Black)\n\nSelected file {file_letter}. Now select a rank (1-8).\nTurn: **{self.current_player.mention}** ({turn_color})"
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.current_player == self.white_player))
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, attachments=[board_image], view=self)
        else:
            await interaction.response.edit_message(content=content, attachments=[board_image], view=self)
    
    async def show_valid_moves(self, interaction: discord.Interaction):
        """Shows buttons for selecting a destination square from valid moves."""
        # Clear existing buttons
        self.clear_items()
        
        # Add buttons for each valid move
        for move in self.valid_moves:
            self.add_item(self.MoveButton(move))
            
        # Add a back button to return to file selection
        back_button = ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="back_to_file_selection")
        back_button.callback = self._back_to_file_selection_callback
        self.add_item(back_button)
        
        # Add a cancel button to return to normal view
        cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_move_selection")
        cancel_button.callback = self._cancel_move_selection_callback
        self.add_item(cancel_button)
        
        # Update the message with valid move dots
        turn_color = "White" if self.board.turn == chess.WHITE else "Black"
        file_letter = chr(65 + self.selected_file)  # Convert to A-H
        rank_number = 8 - chess.square_rank(self.selected_square)  # Convert to 1-8
        content = f"Chess: {self.white_player.mention} (White) vs {self.black_player.mention} (Black)\n\nSelected piece at {file_letter}{rank_number}. Choose a destination square.\nTurn: **{self.current_player.mention}** ({turn_color})"
        board_image = generate_board_image(
            self.board, 
            self.last_move, 
            perspective_white=(self.current_player == self.white_player),
            valid_moves=self.valid_moves
        )
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, attachments=[board_image], view=self)
        else:
            await interaction.response.edit_message(content=content, attachments=[board_image], view=self)
    
    async def _back_to_file_selection_callback(self, interaction: discord.Interaction):
        """Callback for the 'Back' button to return to file selection."""
        if interaction.user != self.current_player:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
        await self.show_file_selection(interaction)
    
    async def _cancel_move_selection_callback(self, interaction: discord.Interaction):
        """Callback for the 'Cancel' button to exit move selection mode."""
        if interaction.user != self.current_player:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
            
        # Reset move selection state
        self.move_selection_mode = False
        self.selected_file = None
        self.selected_rank = None
        self.selected_square = None
        self.valid_moves = []
        
        # Restore normal view
        self.clear_items()
        self.add_item(self.MakeMoveButton())
        self.add_item(self.SelectMoveButton())
        self.add_item(self.ResignButton())
        
        # Update the message
        await self.update_message(interaction, "Move selection cancelled. ")
    
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
            
        # Restore default buttons before updating message
        self.clear_items()
        self.add_item(self.MakeMoveButton())
        self.add_item(self.SelectMoveButton())
        self.add_item(self.ResignButton())

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
        await self.disable_all_buttons()

        # Update DMs with the final result
        dm_update_tasks = [
            self._send_or_update_dm(self.white_player, result=message_content),
            self._send_or_update_dm(self.black_player, result=message_content)
        ]
        await asyncio.gather(*dm_update_tasks)

        # Generate the final board image - ensure it's properly created
        board_image = generate_board_image(self.board, self.last_move, perspective_white=True) # Final board perspective

        try:
            if interaction.response.is_done():
                # If interaction was already responded to, use followup
                try:
                    await interaction.followup.send(content=message_content, file=board_image)
                except discord.HTTPException as e:
                    print(f"Failed to send followup: {e}")
                    # Fallback to channel send if followup fails
                    if interaction.channel:
                        await interaction.channel.send(content=message_content, file=board_image)
            else:
                # Edit the interaction response if still valid
                try:
                    await interaction.response.edit_message(content=message_content, attachments=[board_image], view=self)
                except discord.HTTPException as e:
                    print(f"Failed to edit message: {e}")
                    # Fallback to sending a new message
                    if interaction.channel:
                        await interaction.channel.send(content=message_content, file=board_image)
        except discord.NotFound:
            # If the original message is gone, send a new message
            if interaction.channel:
                await interaction.channel.send(content=message_content, file=board_image)
        except Exception as e:
            print(f"ChessView: Failed to edit or send game end message: {e}")
            # Last resort fallback - try to send a message to the channel if we can access it
            try:
                if interaction.channel:
                    await interaction.channel.send(content=message_content, file=board_image)
                elif self.message and self.message.channel:
                    await self.message.channel.send(content=message_content, file=board_image)
            except Exception as inner_e:
                print(f"Final fallback also failed: {inner_e}")

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

# --- Chess Bot Game ---

# Define paths relative to the script location for better portability
def get_stockfish_path():
    """Returns the appropriate Stockfish path based on the OS."""
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR)) # Go up two levels from games dir
    
    STOCKFISH_PATH_WINDOWS = os.path.join(PROJECT_ROOT, "stockfish-windows-x86-64-avx2", "stockfish", "stockfish-windows-x86-64-avx2.exe")
    STOCKFISH_PATH_LINUX = os.path.join(PROJECT_ROOT, "stockfish-ubuntu-x86-64-avx2", "stockfish", "stockfish-ubuntu-x86-64-avx2")
    
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
        
        # Button-driven move selection state
        self.move_selection_mode = False  # Whether we're in button-driven move selection mode
        self.selected_file = None  # Selected file (0-7) during move selection
        self.selected_rank = None  # Selected rank (0-7) during move selection
        self.selected_square = None  # Selected square (0-63) during move selection
        self.valid_moves = []  # List of valid moves from the selected square

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
        self.add_item(self.SelectMoveButton())
        self.add_item(self.ResignButton())

    # --- Button Definitions ---
    
    class FileButton(ui.Button):
        """Button for selecting a file (A-H) in the first phase of move selection."""
        def __init__(self, file_idx: int):
            self.file_idx = file_idx
            file_label = chr(65 + file_idx)  # 65 is ASCII for 'A'
            super().__init__(label=file_label, style=discord.ButtonStyle.primary)
            
        async def callback(self, interaction: discord.Interaction):
            view: 'ChessBotView' = self.view
            
            # Basic checks
            if interaction.user != view.player:
                await interaction.response.send_message("This is not your game!", ephemeral=True)
                return
            if view.board.turn != view.player_color:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            if view.is_thinking:
                await interaction.response.send_message("The bot is thinking, please wait.", ephemeral=True)
                return
                
            # Store the selected file and show rank buttons
            view.selected_file = self.file_idx
            view.selected_rank = None
            view.selected_square = None
            
            # Show rank selection buttons
            await view.show_rank_selection(interaction)
    
    class RankButton(ui.Button):
        """Button for selecting a rank (1-8) in the first phase of move selection."""
        def __init__(self, rank_idx: int):
            self.rank_idx = rank_idx
            rank_label = str(8 - rank_idx)  # Ranks are displayed as 8 to 1
            super().__init__(label=rank_label, style=discord.ButtonStyle.primary)
            
        async def callback(self, interaction: discord.Interaction):
            view: 'ChessBotView' = self.view
            
            # Basic checks
            if interaction.user != view.player:
                await interaction.response.send_message("This is not your game!", ephemeral=True)
                return
            if view.board.turn != view.player_color:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            if view.is_thinking:
                await interaction.response.send_message("The bot is thinking, please wait.", ephemeral=True)
                return
                
            # Calculate the square index
            file_idx = view.selected_file
            rank_idx = self.rank_idx
            square = chess.square(file_idx, 7 - rank_idx)  # Convert to chess.py square index
            
            # Check if the square has a piece of the player's color
            piece = view.board.piece_at(square)
            if piece is None or piece.color != view.player_color:
                await interaction.response.send_message("You must select a square with one of your pieces.", ephemeral=True)
                # Go back to file selection
                await view.show_file_selection(interaction)
                return
                
            # Find valid moves from this square
            valid_moves = [move for move in view.board.legal_moves if move.from_square == square]
            if not valid_moves:
                await interaction.response.send_message("This piece has no legal moves.", ephemeral=True)
                # Go back to file selection
                await view.show_file_selection(interaction)
                return
                
            # Store the selected square and valid moves
            view.selected_square = square
            view.valid_moves = valid_moves
            
            # Show valid move buttons
            await view.show_valid_moves(interaction)
    
    class MoveButton(ui.Button):
        """Button for selecting a destination square in the second phase of move selection."""
        def __init__(self, move: chess.Move):
            self.move = move
            # Get the destination square coordinates
            file_idx = chess.square_file(move.to_square)
            rank_idx = chess.square_rank(move.to_square)
            # Create label in algebraic notation (e.g., "e4")
            label = f"{chr(97 + file_idx)}{rank_idx + 1}"
            super().__init__(label=label, style=discord.ButtonStyle.success)
            
        async def callback(self, interaction: discord.Interaction):
            view: 'ChessBotView' = self.view
            
            # Basic checks
            if interaction.user != view.player:
                await interaction.response.send_message("This is not your game!", ephemeral=True)
                return
            if view.board.turn != view.player_color:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return
            if view.is_thinking:
                await interaction.response.send_message("The bot is thinking, please wait.", ephemeral=True)
                return
                
            # Execute the move
            await interaction.response.defer()  # Acknowledge the interaction
            await view.handle_player_move(interaction, self.move)
    
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
            
    class SelectMoveButton(ui.Button):
        """Button to start the button-driven move selection process."""
        def __init__(self):
            super().__init__(label="Select Move", style=discord.ButtonStyle.primary, custom_id="chessbot_select_move")
            
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
                
            # Start the move selection process
            view.move_selection_mode = True
            view.selected_file = None
            view.selected_rank = None
            view.selected_square = None
            view.valid_moves = []
            
            # Show file selection buttons
            await view.show_file_selection(interaction)

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

        # Reset selection mode state before updating message
        self.move_selection_mode = False
        self.selected_file = None
        self.selected_rank = None
        self.selected_square = None
        self.valid_moves = []
        
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

                # Restore default buttons for player's turn
                if self.message and not self.is_finished(): # Check if view is still active
                    self.clear_items()
                    self.add_item(self.MakeMoveButton())
                    self.add_item(self.SelectMoveButton())
                    self.add_item(self.ResignButton())
                    # Now update the message
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
        
        # Determine if we need to show valid move dots (only when showing valid move buttons)
        show_valid_move_dots = self.move_selection_mode and self.selected_square is not None and self.valid_moves
        
        board_image = generate_board_image(
            self.board, 
            self.last_move, 
            perspective_white=(self.player_color == chess.WHITE),
            valid_moves=self.valid_moves if show_valid_move_dots else None
        )

        # NOTE: Button setup is now handled by the calling function (e.g., handle_player_move, make_bot_move, _cancel_move_selection_callback)
        # This method only updates content and attachments.

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
        await self.stop_engine() # Ensure engine is closed before stopping view

        # Update DM with final result
        await self._send_or_update_dm(result=message_content)

        # Ensure a valid board image is generated
        try:
            board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE)) # Show final board
        except Exception as img_error:
            print(f"Error generating final board image: {img_error}")
            # Create a fallback message if image generation fails
            message_content += "\n\n*Note: Could not generate final board image.*"
            board_image = None

        # Use a consistent way to get the interaction or message object
        target_message = None
        interaction = None
        channel = None

        if isinstance(interaction_or_message, discord.Interaction):
            interaction = interaction_or_message
            channel = interaction.channel
            # Try to get the original message if possible
            try:
                if interaction.response.is_done():
                    target_message = await interaction.original_response()
            except (discord.NotFound, discord.HTTPException) as e:
                print(f"Could not get original response: {e}")
                target_message = None
        elif isinstance(interaction_or_message, discord.Message):
            target_message = interaction_or_message
            channel = target_message.channel

        # If we still don't have a channel but have a message stored, use that
        if not channel and self.message:
            channel = self.message.channel
            if not target_message:
                target_message = self.message

        # Try multiple approaches to send the final game state
        success = False

        # 1. Try using the interaction if available
        if interaction and not success:
            try:
                if interaction.response.is_done():
                    # If interaction was deferred or responded to, try to edit original response
                    try:
                        if board_image:
                            await interaction.edit_original_response(content=message_content, attachments=[board_image], view=self)
                        else:
                            await interaction.edit_original_response(content=message_content, view=self)
                        success = True
                    except (discord.NotFound, discord.HTTPException) as e:
                        print(f"Failed to edit original response: {e}")
                else:
                    # If interaction is fresh, edit its message
                    try:
                        if board_image:
                            await interaction.response.edit_message(content=message_content, attachments=[board_image], view=self)
                        else:
                            await interaction.response.edit_message(content=message_content, view=self)
                        success = True
                    except (discord.NotFound, discord.HTTPException) as e:
                        print(f"Failed to edit message via response: {e}")
                        # Try to send a followup if editing fails
                        try:
                            if board_image:
                                await interaction.followup.send(content=message_content, file=board_image)
                            else:
                                await interaction.followup.send(content=message_content)
                            success = True
                        except (discord.NotFound, discord.HTTPException) as followup_e:
                            print(f"Failed to send followup: {followup_e}")
            except Exception as e:
                print(f"Error using interaction for end game: {e}")

        # 2. Try using the target message if available
        if target_message and not success:
            try:
                if board_image:
                    await target_message.edit(content=message_content, attachments=[board_image], view=self)
                else:
                    await target_message.edit(content=message_content, view=self)
                success = True
            except (discord.NotFound, discord.HTTPException) as e:
                print(f"Failed to edit target message: {e}")

        # 3. Last resort: send a new message to the channel
        if channel and not success:
            try:
                if board_image:
                    await channel.send(content=message_content, file=board_image)
                else:
                    await channel.send(content=message_content)
                success = True
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"Failed to send new message to channel: {e}")

        if not success:
            print("ChessBotView: All attempts to send game end message failed")

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

    # --- Button-Driven Move Selection Methods ---
    
    async def show_file_selection(self, interaction: discord.Interaction):
        """Shows buttons for selecting a file (A-H)."""
        # Clear existing buttons
        self.clear_items()
        
        # Add file selection buttons (A-H)
        for file_idx in range(8):
            self.add_item(self.FileButton(file_idx))
            
        # Add a cancel button to return to normal view
        cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_move_selection")
        cancel_button.callback = self._cancel_move_selection_callback
        self.add_item(cancel_button)
        
        # Update the message
        content = self.get_board_message("Select a file (A-H) to choose a piece. ")
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE))
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, attachments=[board_image], view=self)
        else:
            await interaction.response.edit_message(content=content, attachments=[board_image], view=self)
    
    async def show_rank_selection(self, interaction: discord.Interaction):
        """Shows buttons for selecting a rank (1-8)."""
        # Clear existing buttons
        self.clear_items()
        
        # Add rank selection buttons (1-8)
        for rank_idx in range(8):
            self.add_item(self.RankButton(rank_idx))
            
        # Add a back button to return to file selection
        back_button = ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="back_to_file_selection")
        back_button.callback = self._back_to_file_selection_callback
        self.add_item(back_button)
        
        # Add a cancel button to return to normal view
        cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_move_selection")
        cancel_button.callback = self._cancel_move_selection_callback
        self.add_item(cancel_button)
        
        # Update the message
        file_letter = chr(65 + self.selected_file)  # Convert to A-H
        content = self.get_board_message(f"Selected file {file_letter}. Now select a rank (1-8). ")
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE))
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, attachments=[board_image], view=self)
        else:
            await interaction.response.edit_message(content=content, attachments=[board_image], view=self)
    
    async def show_valid_moves(self, interaction: discord.Interaction):
        """Shows buttons for selecting a destination square from valid moves."""
        # Clear existing buttons
        self.clear_items()
        
        # Add buttons for each valid move
        for move in self.valid_moves:
            self.add_item(self.MoveButton(move))
            
        # Add a back button to return to file selection
        back_button = ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="back_to_file_selection")
        back_button.callback = self._back_to_file_selection_callback
        self.add_item(back_button)
        
        # Add a cancel button to return to normal view
        cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_move_selection")
        cancel_button.callback = self._cancel_move_selection_callback
        self.add_item(cancel_button)
        
        # Update the message with valid move dots
        file_letter = chr(65 + self.selected_file)  # Convert to A-H
        rank_number = 8 - chess.square_rank(self.selected_square)  # Convert to 1-8
        content = self.get_board_message(f"Selected piece at {file_letter}{rank_number}. Choose a destination square. ")
        board_image = generate_board_image(
            self.board, 
            self.last_move, 
            perspective_white=(self.player_color == chess.WHITE),
            valid_moves=self.valid_moves
        )
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, attachments=[board_image], view=self)
        else:
            await interaction.response.edit_message(content=content, attachments=[board_image], view=self)
    
    async def _back_to_file_selection_callback(self, interaction: discord.Interaction):
        """Callback for the 'Back' button to return to file selection."""
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        await self.show_file_selection(interaction)
    
    async def _cancel_move_selection_callback(self, interaction: discord.Interaction):
        """Callback for the 'Cancel' button to exit move selection mode."""
        if interaction.user != self.player:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
            
        # Reset move selection state
        self.move_selection_mode = False
        self.selected_file = None
        self.selected_rank = None
        self.selected_square = None
        self.valid_moves = []
        
        # Restore normal view
        self.clear_items()
        self.add_item(self.MakeMoveButton())
        self.add_item(self.SelectMoveButton())
        self.add_item(self.ResignButton())
        
        # Update the message
        content = self.get_board_message("Move selection cancelled. ")
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE))
        
        if interaction.response.is_done():
            await interaction.edit_original_response(content=content, attachments=[board_image], view=self)
        else:
            await interaction.response.edit_message(content=content, attachments=[board_image], view=self)
    
    async def handle_square_click(self, interaction: discord.Interaction, x: int, y: int):
        """Legacy method for handling square clicks from ChessBotButton."""
        # This method is kept for backward compatibility
        await interaction.response.send_message(
            "Please use the 'Select Move' button for the new button-driven move selection interface.",
            ephemeral=True
        )
    
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
