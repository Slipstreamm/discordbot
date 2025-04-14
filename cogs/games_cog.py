import discord
from discord.ext import commands
from discord import app_commands, ui
import discord
from discord.ext import commands
from discord import app_commands, ui
import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import asyncio
from typing import Optional, List, Union # Added Union
import chess
import chess.engine
import platform
import os
from PIL import Image, ImageDraw, ImageFont # Added Pillow imports
import io # Added io import

# --- Add this helper function ---
def generate_board_image(board: chess.Board, last_move: Optional[chess.Move] = None, perspective_white: bool = True) -> discord.File:
    """Generates an image representation of the chess board."""
    SQUARE_SIZE = 60
    BOARD_SIZE = 8 * SQUARE_SIZE
    LIGHT_COLOR = (240, 217, 181) # Light wood
    DARK_COLOR = (181, 136, 99)  # Dark wood
    HIGHLIGHT_LIGHT = (205, 210, 106, 180) # Semi-transparent yellow for light squares
    HIGHLIGHT_DARK = (170, 162, 58, 180)   # Semi-transparent yellow for dark squares

    img = Image.new("RGB", (BOARD_SIZE, BOARD_SIZE), DARK_COLOR)
    draw = ImageDraw.Draw(img, "RGBA") # Use RGBA for transparency support

    # Load a font that supports Unicode chess pieces
    try:
        # Adjust font path and size as needed
        # Ensure you have a font file (like Arial) accessible or specify a full path
        # On Windows: font_path = "C:/Windows/Fonts/arial.ttf"
        # On Linux: font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" (example)
        font_path = "arial.ttf" # Adjust if necessary
        font_size = int(SQUARE_SIZE * 0.8)
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print(f"Warning: Font '{font_path}' not found. Using default font. Chess pieces might not render correctly.")
        font = ImageFont.load_default()

    # Determine squares to highlight based on the last move
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

            x0 = display_file * SQUARE_SIZE
            y0 = (7 - display_rank) * SQUARE_SIZE # Y is inverted in PIL
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

            # Draw piece
            piece = board.piece_at(square)
            if piece:
                piece_symbol = piece.unicode_symbol()
                # Calculate text position to center it using textbbox for modern Pillow
                try:
                    bbox = draw.textbbox((0, 0), piece_symbol, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x0 + (SQUARE_SIZE - text_width) / 2
                    text_y = y0 + (SQUARE_SIZE - text_height) / 2 - (SQUARE_SIZE * 0.05) # Small offset adjustment
                except AttributeError: # Fallback for older Pillow versions using getsize
                     # Note: textsize is deprecated, but included for compatibility
                     try:
                         text_width, text_height = draw.textsize(piece_symbol, font=font)
                     except AttributeError: # Even older Pillow? Unlikely but safe.
                         text_width, text_height = font.getsize(piece_symbol)
                     text_x = x0 + (SQUARE_SIZE - text_width) / 2
                     text_y = y0 + (SQUARE_SIZE - text_height) / 2 - (SQUARE_SIZE * 0.05)

                # Piece color (simple black/white)
                piece_color = (255, 255, 255) if piece.color == chess.WHITE else (0, 0, 0)
                draw.text((text_x, text_y), piece_symbol, fill=piece_color, font=font)

    # Save image to a bytes buffer
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    return discord.File(fp=img_byte_arr, filename="chess_board.png")

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
        super().__init__(style=discord.ButtonStyle.secondary, label='', row=y)
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
        super().__init__(style=discord.ButtonStyle.secondary, label='', row=y)
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

# --- Chess Game (Image + Modal Input) --- START

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
            # Try parsing as SAN first (more user-friendly)
            move = board.parse_san(move_text)
        except ValueError:
            try:
                # Try parsing as UCI if SAN fails (e.g., "e2e4")
                move = board.parse_uci(move_text)
            except ValueError:
                await interaction.response.send_message(
                    f"Invalid move format: '{move_text}'. Use algebraic notation (e.g., Nf3, e4, O-O) or UCI (e.g., e2e4).",
                    ephemeral=True
                )
                return # Stop processing if format is wrong

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
    def __init__(self, white_player: discord.Member, black_player: discord.Member):
        super().__init__(timeout=600.0)  # 10 minute timeout
        self.white_player = white_player
        self.black_player = black_player
        self.current_player = white_player  # White starts
        self.board = chess.Board()
        self.message: Optional[discord.Message] = None
        self.last_move: Optional[chess.Move] = None # Store last move for highlighting

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

        content = f"Chess: {self.white_player.mention} (White) vs {self.black_player.mention} (Black)\n\n{status}"
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
        """Ends the game, disables buttons, and updates the message."""
        await self.disable_all_buttons()
        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.current_player == self.white_player)) # Show final board

        # Use followup if interaction was deferred (likely from modal or resign)
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(content=message_content, attachments=[board_image], view=self)
            else:
                # This case might happen if end_game is called directly without deferral (less likely now)
                await interaction.response.edit_message(content=message_content, attachments=[board_image], view=self)
        except (discord.NotFound, discord.HTTPException) as e:
             print(f"ChessView: Failed to edit message on game end: {e}")
             # Attempt to send a new message if editing failed
             try:
                 await interaction.channel.send(content=message_content, files=[board_image])
             except discord.Forbidden:
                 print("ChessView: Missing permissions to send final game message.")

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

# --- Chess Game --- END

# --- Chess Bot Game --- START

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

    def __init__(self, player: discord.Member, player_color: chess.Color, variant: str = "standard", skill_level: int = 10, think_time: float = 1.0):
        super().__init__(timeout=900.0)  # 15 minute timeout
        self.player = player
        self.player_color = player_color
        self.bot_color = not player_color
        self.variant = variant.lower()
        self.message: Optional[discord.Message] = None
        self.protocol: Optional[chess.engine.UciProtocol] = None # Renamed from engine
        self.transport: Optional[chess.engine.BaseTransport] = None
        self.skill_level = max(0, min(20, skill_level)) # Clamp skill level
        self.think_time = max(0.1, min(5.0, think_time)) # Clamp think time
        self.is_thinking = False # Flag to prevent interaction during bot's turn
        self.last_move: Optional[chess.Move] = None # Store last move for highlighting

        # Initialize board based on variant
        if self.variant == "chess960":
            self.board = chess.Board(chess960=True)
            # Stockfish needs the FEN for Chess960 setup
            self.initial_fen = self.board.fen()
        else: # Standard chess
            self.board = chess.Board()
            self.initial_fen = None # Not needed for standard

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
        """Initializes the Stockfish engine using SimpleEngine."""
        try:
            stockfish_path = get_stockfish_path()
            print(f"Attempting to start Stockfish from: {stockfish_path}")

            # Use the async popen_uci to get transport and protocol
            self.transport, self.protocol = await chess.engine.popen_uci(stockfish_path)
            print(f"Stockfish process opened via popen_uci. Transport: {self.transport}, Protocol Type: {type(self.protocol)}")

            # Initialize the engine via UCI commands (This performs the handshake)
            await self.protocol.initialize()
            print("Stockfish initialized via UCI.")

            # Configure Stockfish options
            print("Configuring Stockfish...")
            options = {"Skill Level": self.skill_level}
            if self.variant == "chess960":
                options["UCI_Chess960"] = "true"
            await self.protocol.configure(options)

            # Set position (handles standard and Chess960)
            await self.protocol.position(self.board)

            print(f"Stockfish protocol configured for {self.variant} with skill level {self.skill_level}.")
        except (FileNotFoundError, OSError, chess.engine.EngineError, Exception) as e:
            print(f"Failed to start Stockfish engine/protocol: {e}")
            self.protocol = None # Ensure protocol is None if failed
            # Optionally notify the user in the channel if the message exists
            if self.message:
                try:
                    await self.message.channel.send(f"Error: Could not start the chess engine. {e}")
                except discord.Forbidden:
                    pass # Can't send message
            self.stop() # Stop the view if engine fails

    async def handle_player_move(self, interaction: discord.Interaction, move: chess.Move):
        """Handles the player's validated legal move."""
        self.board.push(move)
        self.last_move = move

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
        """Lets the Stockfish engine make a move."""
        if self.engine is None or self.board.turn != self.bot_color or self.is_thinking or self.is_finished():
            return # Engine not ready, not bot's turn, already thinking, or game ended

        self.is_thinking = True
        try:
            # Ensure the engine has the latest board state
            await self.engine.position(self.board)

            # Use asyncio.to_thread for the blocking engine call
            result = await asyncio.to_thread(
                self.engine.play,
                self.board,
                chess.engine.Limit(time=self.think_time)
            )

            # Check if the view is still active before proceeding
            if self.is_finished():
                print("ChessBotView: Game ended while bot was thinking.")
                return

            if result.move:
                self.board.push(result.move)
                self.last_move = result.move

                # Check game state *after* bot's move
                outcome = self.board.outcome()
                if outcome:
                    # Need a way to update the message; use self.message if available
                    if self.message:
                         await self.end_game(self.message, self.get_game_over_message(outcome))
                    else: # Should not happen if game started correctly
                         print("ChessBotView Error: Cannot end game after bot move, self.message is None.")
                    return

                # Update message for player's turn
                if self.message:
                    await self.update_message(self.message, status_prefix="Your turn.")
            else:
                 print("ChessBotView: Engine returned no bestmove.")
                 if self.message:
                     await self.update_message(self.message, status_prefix="Bot failed to find a move. Your turn?")

        except (chess.engine.EngineError, Exception) as e:
            print(f"Error during bot move analysis: {e}")
            if self.message:
                 try:
                     # Try to inform the user about the error
                     await self.update_message(self.message, status_prefix=f"Error during bot move: {e}. Your turn.")
                 except: pass # Ignore errors editing message here
        finally:
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
        await self.stop_engine() # Ensure engine is closed

        board_image = generate_board_image(self.board, self.last_move, perspective_white=(self.player_color == chess.WHITE)) # Show final board

        try:
            if isinstance(interaction_or_message, discord.Interaction):
                if interaction_or_message.response.is_done():
                    await interaction_or_message.edit_original_response(content=message_content, attachments=[board_image], view=self)
                else:
                    await interaction_or_message.response.edit_message(content=message_content, attachments=[board_image], view=self)
            elif isinstance(interaction_or_message, discord.Message):
                 await interaction_or_message.edit(content=message_content, attachments=[board_image], view=self)
        except (discord.NotFound, discord.HTTPException) as e:
             print(f"ChessBotView: Failed to edit message on game end: {e}")
             # Attempt to send a new message if editing failed and we have a channel context
             channel = None
             if isinstance(interaction_or_message, discord.Interaction):
                 channel = interaction_or_message.channel
             elif isinstance(interaction_or_message, discord.Message):
                 channel = interaction_or_message.channel

             if channel:
                 try:
                     await channel.send(content=message_content, files=[board_image])
                 except discord.Forbidden:
                     print("ChessBotView: Missing permissions to send final game message.")

        self.stop() # Stop the view itself

    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        # Don't edit the message here, let end_game or on_timeout handle the final update

    async def stop_engine(self):
        """Safely quits the chess engine protocol and closes the transport."""
        # First, try to quit the engine via UCI protocol
        if self.protocol:
            protocol_to_stop = self.protocol
            self.protocol = None # Set to None immediately to prevent further use
            try:
                await protocol_to_stop.quit()
                print("Stockfish protocol quit command sent successfully.")
            except (chess.engine.EngineError, BrokenPipeError, Exception) as e:
                # BrokenPipeError can happen if engine process already terminated
                if not isinstance(e, BrokenPipeError):
                     print(f"Error sending quit command to Stockfish protocol: {e}")

        # Regardless of protocol quit success, close the transport
        if self.transport:
            transport_to_close = self.transport
            self.transport = None # Set to None immediately
            try:
                transport_to_close.close()
                print("Stockfish transport closed successfully.")
            except Exception as e:
                print(f"Error closing Stockfish transport: {e}")

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

# --- Chess Bot Game --- END

class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store active bot game views to manage engine resources
        self.active_chess_bot_views = {} # Store by message ID
        self.ttt_games = {} # Store TicTacToe game instances by user ID

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

    @app_commands.command(name="coinflipbet", description="Challenge another user to a coin flip game.")
    @app_commands.describe(
        opponent="The user you want to challenge."
    )
    async def coinflipbet(self, interaction: discord.Interaction, opponent: discord.Member):
        """Initiates a coin flip game against another user."""

        initiator = interaction.user

        # --- Input Validation ---
        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
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
        await interaction.response.send_message(f"🎱 {response}")

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
                msg = await self.bot.wait_for("message", check=check, timeout=120.0) # 2 min timeout per guess
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
        await view.start_engine()
        if view.engine is None or view.is_finished(): # Check if engine failed or view stopped during init
             # Error message should have been sent by start_engine or view stopped itself
             # Ensure we don't try to send another response if already handled
             if not interaction.is_done():
                 await interaction.followup.send("Failed to initialize the chess engine. Cannot start game.", ephemeral=True)
             return # Stop if engine failed

        # Determine initial message based on who moves first
        initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
        initial_message_content = view.get_board_message(initial_status_prefix)
        board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

        # Send the initial game state using followup
        message = await interaction.followup.send(initial_message_content, file=board_image, view=view, wait=True)
        view.message = message
        self.active_chess_bot_views[message.id] = view # Track the view

        # If bot moves first (player chose black), trigger its move
        if player_color == chess.BLACK:
            # Don't await this, let it run in the background
            asyncio.create_task(view.make_bot_move())

    # --- Prefix Commands (Legacy Support) ---

    @commands.command(name="coinflipbet")
    async def coinflipbet_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Challenge another user to a coin flip game."""
        initiator = ctx.author

        if opponent == initiator:
            await ctx.send("You cannot challenge yourself!")
            return
        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        view = CoinFlipView(initiator, opponent)
        initial_message = f"{initiator.mention} has challenged {opponent.mention} to a coin flip game! {initiator.mention}, choose your side:"
        message = await ctx.send(initial_message, view=view)
        view.message = message

    @commands.command(name="coinflip")
    async def coinflip_prefix(self, ctx: commands.Context):
        """(Prefix) Flip a coin."""
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"The coin landed on **{result}**! 🪙")

    @commands.command(name="roll")
    async def roll_prefix(self, ctx: commands.Context):
        """(Prefix) Roll a dice."""
        result = random.randint(1, 6)
        await ctx.send(f"You rolled a **{result}**! 🎲")

    @commands.command(name="magic8ball")
    async def magic8ball_prefix(self, ctx: commands.Context, *, question: str):
        """(Prefix) Ask the magic 8 ball."""
        # Identical logic to slash command, just using ctx.send
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes – definitely.", "You may rely on it.",
            "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."
        ]
        response = random.choice(responses)
        await ctx.send(f"🎱 {response}")

    @commands.command(name="tictactoe")
    async def tictactoe_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Challenge another user to Tic-Tac-Toe."""
        initiator = ctx.author

        if opponent == initiator:
            await ctx.send("You cannot challenge yourself!")
            return
        if opponent.bot:
            await ctx.send("You cannot challenge a bot! Use `!tictactoebot` instead.")
            return

        view = TicTacToeView(initiator, opponent)
        initial_message = f"Tic Tac Toe: {initiator.mention} (X) vs {opponent.mention} (O)\n\nTurn: **{initiator.mention} (X)**"
        message = await ctx.send(initial_message, view=view)
        view.message = message

    @commands.command(name="tictactoebot")
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

    @commands.command(name="rpschallenge")
    async def rpschallenge_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Challenge another user to Rock-Paper-Scissors."""
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

    @commands.command(name="chess")
    async def chess_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """(Prefix) Start a game of chess with another user."""
        initiator = ctx.author

        if opponent == initiator:
            await ctx.send("You cannot challenge yourself!")
            return
        if opponent.bot:
            await ctx.send("You cannot challenge a bot! Use `!chessbot` instead.")
            return

        view = ChessView(initiator, opponent)
        initial_status = f"Turn: **{initiator.mention}** (White)"
        initial_message = f"Chess: {initiator.mention} (White) vs {opponent.mention} (Black)\n\n{initial_status}"
        board_image = generate_board_image(view.board)

        message = await ctx.send(initial_message, file=board_image, view=view)
        view.message = message

    @commands.command(name="chessbot")
    async def chessbot_prefix(self, ctx: commands.Context, color: str = "white", variant: str = "standard", skill_level: int = 10, think_time: float = 1.0):
        """(Prefix) Play chess against the bot. Usage: !chessbot [white|black] [standard|chess960] [skill 0-20] [time 0.1-5.0]"""
        player = ctx.author
        player_color_str = color.lower()
        variant_str = variant.lower()
        player_color = chess.WHITE if player_color_str == "white" else chess.BLACK

        # Validate inputs
        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))

        supported_variants = ["standard", "chess960"]
        if variant_str not in supported_variants:
            await ctx.send(f"Sorry, the variant '{variant_str}' is not currently supported. Choose from: {', '.join(supported_variants)}")
            return

        # Send a thinking message first
        thinking_msg = await ctx.send("Initializing chess engine...")

        view = ChessBotView(player, player_color, variant_str, skill_level, think_time)

        await view.start_engine()
        if view.engine is None or view.is_finished():
             await thinking_msg.edit(content="Failed to initialize the chess engine. Cannot start game.")
             return

        initial_status_prefix = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
        initial_message_content = view.get_board_message(initial_status_prefix)
        board_image = generate_board_image(view.board, perspective_white=(player_color == chess.WHITE))

        # Edit the thinking message to the actual game message
        message = await thinking_msg.edit(content=initial_message_content, attachments=[board_image], view=view)
        view.message = message
        self.active_chess_bot_views[message.id] = view

        if player_color == chess.BLACK:
            asyncio.create_task(view.make_bot_move())

    # --- Listeners for Cleanup ---

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # Clean up finished chess bot views
        if interaction.message and interaction.message.id in self.active_chess_bot_views:
            view = self.active_chess_bot_views.get(interaction.message.id)
            # Check if the view object exists and is finished
            if view and view.is_finished():
                # No need to stop engine here, end_game/on_timeout should handle it
                if interaction.message.id in self.active_chess_bot_views: # Check again in case of race condition
                    del self.active_chess_bot_views[interaction.message.id]
                    print(f"Removed finished ChessBotView tracking for message {interaction.message.id}")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # Clean up chess bot view if its message is deleted
        if message.id in self.active_chess_bot_views:
            print(f"Chess game message {message.id} deleted. Stopping associated view and engine.")
            view = self.active_chess_bot_views.pop(message.id, None) # Use pop with default None
            if view and not view.is_finished():
                await view.stop_engine()
                view.stop()

async def setup(bot: commands.Bot):
    # Ensure necessary libraries are available
    try:
        import chess
        import chess.engine
        from PIL import Image, ImageDraw, ImageFont
        import io
    except ImportError as e:
        print(f"Error loading GamesCog: Missing dependency - {e}. Please install required libraries (python-chess, Pillow).")
        return # Prevent loading cog if dependencies missing

    # Check for Stockfish executable before adding cog
    stockfish_available = False
    try:
        get_stockfish_path() # This will raise FileNotFoundError or OSError if not found/configured
        stockfish_available = True
    except (FileNotFoundError, OSError) as e:
        print(f"Warning loading GamesCog: {e}. Chess bot features will be unavailable.")

    # Load the cog
    await bot.add_cog(GamesCog(bot))
    if stockfish_available:
        print("GamesCog loaded successfully with Stockfish.")
    else:
         print("GamesCog loaded, but Stockfish engine not found or not executable. Chess bot commands will fail.")

    # Note: The `chessbot` commands already handle the `view.protocol is None` case gracefully.
