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

# --- Chess Game --- START

class ChessButton(ui.Button['ChessView']):
    def __init__(self, x: int, y: int, piece: str = None):
        # Unicode chess pieces
        self.pieces = {
            'r': '♜', 'n': '♞', 'b': '♝', 'q': '♛', 'k': '♚', 'p': '♟',
            'R': '♖', 'N': '♘', 'B': '♗', 'Q': '♕', 'K': '♔', 'P': '♙',
            None: ' '
        }
        self.x = x
        self.y = y
        self.piece = piece
        
        # Set button style and label based on square color
        is_dark = (x + y) % 2 != 0
        style = discord.ButtonStyle.secondary if is_dark else discord.ButtonStyle.primary
        # REMOVED row=y parameter
        super().__init__(style=style, label=self.pieces.get(piece, ' '))

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: ChessView = self.view
        
        # Check if it's the correct player's turn
        if interaction.user != view.current_player:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
        
        # Process the move
        await view.handle_square_click(interaction, self.x, self.y)


class ChessView(ui.View):
    def __init__(self, white_player: discord.Member, black_player: discord.Member):
        super().__init__(timeout=600.0)  # 10 minute timeout
        self.white_player = white_player
        self.black_player = black_player
        self.current_player = white_player  # White starts
        self.board = chess.Board()
        self.message = None
        
        # For move input (selected square)
        self.selected_square = None
        
        # Initialize the chess board with buttons
        self.update_board_buttons()
    
    def update_board_buttons(self):
        """Recreate all buttons based on current board state"""
        self.clear_items()  # Clear all buttons
        
        # Create buttons for each square
        for y in range(8):
            for x in range(8):
                # Convert to chess coordinates
                square = chess.square(x, 7-y)
                piece = self.board.piece_at(square)
                piece_symbol = piece.symbol() if piece else None
                self.add_item(ChessButton(x, y, piece_symbol))
    
    async def handle_square_click(self, interaction: discord.Interaction, x: int, y: int):
        """Handle when a user clicks a square on the board"""
        # Convert UI coordinates to chess coordinates
        square = chess.square(x, 7-y)  # Chess board is 0,0 at bottom-left, our UI is 0,0 at top-left
        
        if self.selected_square is None:
            # No square selected yet - select this one if it has a piece of the right color
            piece = self.board.piece_at(square)
            if piece is None:
                await interaction.response.send_message("No piece at this square.", ephemeral=True)
                return
            
            # Check correct color
            is_white_piece = piece.color == chess.WHITE
            is_white_turn = self.board.turn == chess.WHITE
            if is_white_piece != is_white_turn:
                await interaction.response.send_message("You can only move your own pieces.", ephemeral=True)
                return
            
            # Select this square
            self.selected_square = square
            await interaction.response.send_message(f"Selected {chess.square_name(square)}.", ephemeral=True)
        
        else:
            # Already have a square selected - try to make a move
            move = chess.Move(self.selected_square, square)
            
            # Check for promotion
            if self.is_pawn_promotion(self.selected_square, square):
                move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)
            
            # Try to make the move
            if move in self.board.legal_moves:
                self.board.push(move)
                self.selected_square = None
                
                # Update board and switch turns
                self.update_board_buttons()
                self.current_player = self.black_player if self.current_player == self.white_player else self.white_player
                
                # Check for game end
                status_message = ""
                if self.board.is_checkmate():
                    winner = self.white_player if not self.board.turn else self.black_player
                    status_message = f"Checkmate! {winner.mention} wins! 🎉"
                    self.stop()
                elif self.board.is_stalemate():
                    status_message = "Stalemate! The game is a draw. 🤝"
                    self.stop()
                elif self.board.is_check():
                    status_message = "Check! "
                
                # Update the message
                turn_color = "White" if self.board.turn == chess.WHITE else "Black"
                content = f"Chess: {self.white_player.mention} (White) vs {self.black_player.mention} (Black)\n\n"
                content += f"{status_message}Turn: **{self.current_player.mention}** ({turn_color})"
                
                await interaction.response.edit_message(content=content, view=self)
            else:
                # Invalid move
                self.selected_square = None
                await interaction.response.send_message("Invalid move. Try again.", ephemeral=True)
    
    def is_pawn_promotion(self, from_square: int, to_square: int) -> bool:
        """Check if a move is a pawn promotion"""
        piece = self.board.piece_at(from_square)
        if piece is None or piece.piece_type != chess.PAWN:
            return False
            
        # Check if move is to the last rank
        to_rank = chess.square_rank(to_square)
        return (piece.color == chess.WHITE and to_rank == 7) or \
               (piece.color == chess.BLACK and to_rank == 0)
    
    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
                
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass
    
    async def on_timeout(self):
        if self.message:
            await self.disable_all_buttons()
            timeout_msg = f"Chess game between {self.white_player.mention} and {self.black_player.mention} timed out."
            try:
                await self.message.edit(content=timeout_msg, view=self)
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass
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
        self.engine: Optional[chess.engine.SimpleEngine] = None
        self.skill_level = max(0, min(20, skill_level)) # Clamp skill level
        self.think_time = max(0.1, min(5.0, think_time)) # Clamp think time
        self.is_thinking = False # Flag to prevent interaction during bot's turn

        # Initialize board based on variant
        if self.variant == "chess960":
            self.board = chess.Board(chess960=True)
            # Stockfish needs the FEN for Chess960 setup
            self.initial_fen = self.board.fen()
        else: # Standard chess
            self.board = chess.Board()
            self.initial_fen = None # Not needed for standard

        # For move input (selected square)
        self.selected_square: Optional[int] = None

        # Initialize the chess board with buttons
        self.update_board_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Allow only the player to interact
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return False
        # Prevent interaction while bot is thinking
        if self.is_thinking:
            await interaction.response.send_message("The bot is thinking, please wait.", ephemeral=True)
            return False
        return True

    async def start_engine(self):
        """Initializes the Stockfish engine."""
        try:
            stockfish_path = get_stockfish_path()
            self.engine = await chess.engine.popen_uci(stockfish_path)

            # Configure Stockfish
            options = {"Skill Level": self.skill_level}
            if self.variant == "chess960":
                options["UCI_Chess960"] = "true"
            await self.engine.configure(options)

            # Set position if Chess960
            if self.initial_fen:
                await self.engine.position(self.board) # Use position method which takes a board

            print(f"Stockfish engine started for {self.variant} with skill level {self.skill_level}.")
        except (FileNotFoundError, OSError, chess.engine.EngineError, Exception) as e:
            print(f"Failed to start Stockfish engine: {e}")
            self.engine = None # Ensure engine is None if failed
            # Optionally notify the user in the channel if the message exists
            if self.message:
                try:
                    await self.message.channel.send(f"Error: Could not start the chess engine. {e}")
                except discord.Forbidden:
                    pass # Can't send message
            self.stop() # Stop the view if engine fails

    def update_board_buttons(self):
        """Recreate all buttons based on current board state"""
        self.clear_items()  # Clear all buttons

        # Create buttons for each square
        for y in range(8):
            for x in range(8):
                # Convert to chess coordinates (0=a1, 63=h8)
                square = chess.square(x, 7 - y) # UI y=0 is rank 8, y=7 is rank 1
                piece = self.board.piece_at(square)
                piece_symbol = piece.symbol() if piece else None
                self.add_item(ChessBotButton(x, y, piece_symbol))

    async def handle_square_click(self, interaction: discord.Interaction, x: int, y: int):
        """Handle when a user clicks a square on the board"""
        # Convert UI coordinates to chess coordinates
        square = chess.square(x, 7 - y)

        if self.selected_square is None:
            # No square selected yet - select this one if it has a piece of the right color
            piece = self.board.piece_at(square)
            if piece is None:
                await interaction.response.send_message("Select a square with your piece first.", ephemeral=True)
                return

            # Check correct color
            if piece.color != self.player_color:
                await interaction.response.send_message("You can only move your own pieces.", ephemeral=True)
                return

            # Select this square
            self.selected_square = square
            await interaction.response.send_message(f"Selected {chess.square_name(square)}. Now select the destination square.", ephemeral=True)

        else:
            # Already have a square selected - try to make a move
            move = chess.Move(self.selected_square, square)

            # Check for promotion - always promote to Queen for simplicity in this context
            piece = self.board.piece_at(self.selected_square)
            if piece and piece.piece_type == chess.PAWN:
                to_rank = chess.square_rank(square)
                if (piece.color == chess.WHITE and to_rank == 7) or \
                   (piece.color == chess.BLACK and to_rank == 0):
                    move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)

            # Try to make the move
            if move in self.board.legal_moves:
                self.board.push(move)
                self.selected_square = None # Reset selection

                # Update board visually
                self.update_board_buttons()

                # Check game state *after* player's move
                if await self.check_game_over(interaction):
                    return # Game ended

                # Edit message to show player's move and indicate bot's turn
                await interaction.response.edit_message(content=self.get_board_message("Bot is thinking..."), view=self)

                # Trigger bot's move
                await self.make_bot_move()

            else:
                # Invalid move
                await interaction.response.send_message(f"Invalid move from {chess.square_name(self.selected_square)} to {chess.square_name(square)}. Try again.", ephemeral=True)
                # Keep the selection or reset? Resetting might be less confusing.
                self.selected_square = None

    async def make_bot_move(self):
        """Lets the Stockfish engine make a move."""
        if self.engine is None or self.board.turn != self.bot_color or self.is_thinking:
            return # Engine not ready, not bot's turn, or already thinking

        self.is_thinking = True
        try:
            # Use asyncio.to_thread to run the blocking engine call
            result = await asyncio.to_thread(
                self.engine.play,
                self.board,
                chess.engine.Limit(time=self.think_time)
            )
            if result.move:
                self.board.push(result.move)
                self.update_board_buttons() # Update board visually after bot move

                # Check game state *after* bot's move
                if await self.check_game_over(self.message.channel): # Use channel if interaction not available
                     return

                # Update message for player's turn
                if self.message:
                    try:
                        await self.message.edit(content=self.get_board_message("Your turn."), view=self)
                    except discord.NotFound:
                        print("ChessBotView: Failed to edit message after bot move, likely deleted.")
                    except discord.Forbidden:
                        print("ChessBotView: Missing permissions to edit message after bot move.")
            else:
                 print("ChessBotView: Engine returned no move.")
                 # Handle case where engine fails to produce a move (should be rare)
                 if self.message:
                     await self.message.edit(content=self.get_board_message("Bot failed to move. Your turn?"), view=self)

        except (chess.engine.EngineError, Exception) as e:
            print(f"Error during bot move: {e}")
            if self.message:
                 try:
                     await self.message.edit(content=self.get_board_message(f"Error during bot move: {e}. Your turn."), view=self)
                 except: pass # Ignore errors editing message here
        finally:
            self.is_thinking = False


    def get_board_message(self, status: str) -> str:
        """Generates the message content including status and whose turn it is."""
        turn_color = "White" if self.board.turn == chess.WHITE else "Black"
        player_mention = self.player.mention
        elo = self.SKILL_ELO_MAP.get(self.skill_level, "Unknown")
        variant_name = "Chess960" if self.variant == "chess960" else "Standard Chess"

        title = f"{variant_name}: {player_mention} ({'White' if self.player_color == chess.WHITE else 'Black'}) vs Bot (Skill: {self.skill_level}/20, ~{elo} ELO)"
        turn_indicator = f"Turn: **{'Your (White)' if self.board.turn == chess.WHITE and self.player_color == chess.WHITE else 'Your (Black)' if self.board.turn == chess.BLACK and self.player_color == chess.BLACK else 'Bot (White)' if self.board.turn == chess.WHITE else 'Bot (Black)'}**"

        # Add check indicator
        check_indicator = ""
        if self.board.is_check():
            check_indicator = " **Check!**"

        return f"{title}\n\n{status}{check_indicator}\n{turn_indicator}"

    async def check_game_over(self, source: Union[discord.Interaction, discord.TextChannel, discord.abc.Messageable]) -> bool:
        """Checks if the game has ended and updates the message."""
        outcome = self.board.outcome()
        if outcome:
            await self.disable_all_buttons()
            winner_text = ""
            if outcome.winner == chess.WHITE:
                winner = self.player if self.player_color == chess.WHITE else "Bot"
                winner_text = f"{winner} (White) wins!"
            elif outcome.winner == chess.BLACK:
                winner = self.player if self.player_color == chess.BLACK else "Bot"
                winner_text = f"{winner} (Black) wins!"
            else:
                winner_text = "It's a draw!"

            termination_reason = outcome.termination.name.replace("_", " ").title()
            final_message = f"{self.get_board_message('Game Over!')}\n\n**Result: {winner_text} by {termination_reason}**"

            # Try to edit the original message
            edit_success = False
            if isinstance(source, discord.Interaction) and not source.is_expired():
                 try:
                     await source.response.edit_message(content=final_message, view=self)
                     edit_success = True
                 except (discord.InteractionResponded, discord.NotFound, discord.Forbidden):
                     pass # Fallback below

            if not edit_success and self.message:
                 try:
                     await self.message.edit(content=final_message, view=self)
                 except (discord.NotFound, discord.Forbidden):
                     # If editing fails, try sending a new message
                     try:
                         if isinstance(source, discord.abc.Messageable): # Check if source can send messages
                             await source.send(final_message)
                         elif self.message: # Fallback to original message channel
                             await self.message.channel.send(final_message)
                     except discord.Forbidden:
                         print("ChessBotView: Cannot send final game message due to permissions.")
            elif not edit_success and isinstance(source, discord.abc.Messageable): # If no self.message, try source
                 try:
                     await source.send(final_message)
                 except discord.Forbidden:
                     print("ChessBotView: Cannot send final game message due to permissions.")


            await self.stop_engine() # Ensure engine is closed
            self.stop()
            return True
        return False

    async def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        # Update the view on the message if possible
        if self.message:
            try:
                # Don't pass interaction here, just edit the message state
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass # Ignore if message is gone or cannot be edited

    async def stop_engine(self):
        """Safely quits the chess engine."""
        if self.engine:
            try:
                await self.engine.quit()
                print("Stockfish engine quit successfully.")
            except (chess.engine.EngineError, BrokenPipeError, Exception) as e:
                print(f"Error quitting Stockfish engine: {e}")
            finally:
                self.engine = None

    async def on_timeout(self):
        if not self.is_finished(): # Only act if not already stopped (e.g., by game end)
            await self.disable_all_buttons()
            timeout_msg = f"Chess game for {self.player.mention} timed out."
            if self.message:
                try:
                    await self.message.edit(content=timeout_msg, view=self)
                except (discord.NotFound, discord.Forbidden):
                    pass
            await self.stop_engine()
            self.stop() # Ensure the view itself is stopped

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print(f"Error in ChessBotView interaction: {error}")
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
        await self.stop_engine()
        self.stop()

# --- Chess Bot Game --- END

class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store active bot game views to manage engine resources
        self.active_chess_bot_views = {} # Store by message ID

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

    @app_commands.command(name="chess", description="Challenge another user to a game of chess.")
    @app_commands.describe(opponent="The user you want to challenge.")
    async def chess(self, interaction: discord.Interaction, opponent: discord.Member):
        """Start a game of chess with another user."""
        initiator = interaction.user

        if opponent == initiator:
            await interaction.response.send_message("You cannot challenge yourself!", ephemeral=True)
            return
        if opponent.bot:
            await interaction.response.send_message("You cannot challenge a bot!", ephemeral=True)
            return

        # Initiator is white, opponent is black
        view = ChessView(initiator, opponent)
        initial_message = f"Chess: {initiator.mention} (White) vs {opponent.mention} (Black)\n\nTurn: **{initiator.mention}** (White)"
        await interaction.response.send_message(initial_message, view=view)
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
    async def chessbot(self, interaction: discord.Interaction, color: str = "white", variant: str = "standard", skill_level: int = 10, think_time: float = 1.0):
        """Starts a chess game against the Stockfish engine."""
        player = interaction.user
        player_color = chess.WHITE if color.lower() == "white" else chess.BLACK
        variant = variant.lower() # Ensure lowercase for consistency

        # Validate inputs
        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))

        # Check if variant is supported (currently standard and chess960)
        supported_variants = ["standard", "chess960"]
        if variant not in supported_variants:
            await interaction.response.send_message(f"Sorry, the variant '{variant}' is not currently supported. Choose from: {', '.join(supported_variants)}", ephemeral=True)
            return

        view = ChessBotView(player, player_color, variant, skill_level, think_time)

        # Start the engine asynchronously (now handles variant setup)
        await view.start_engine()
        if view.engine is None:
             # Error message already sent by start_engine or will be handled if message exists
             await interaction.response.send_message("Failed to initialize the chess engine. Cannot start game.", ephemeral=True)
             return # Stop if engine failed

        # Determine initial message based on who moves first
        initial_status = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
        initial_message = view.get_board_message(initial_status)

        await interaction.response.send_message(initial_message, view=view)
        message = await interaction.original_response()
        view.message = message
        self.active_chess_bot_views[message.id] = view # Track the view

        # If bot is black, make its first move
        if player_color == chess.WHITE:
            pass # Player (White) moves first
        else:
            await view.make_bot_move() # Bot (White) moves first

    # --- Prefix Commands ---

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

    @commands.command(name="chess")
    async def chess_prefix(self, ctx: commands.Context, opponent: discord.Member):
        """Start a game of chess with another user."""
        initiator = ctx.author
        
        if opponent.bot:
            await ctx.send("You cannot challenge a bot!")
            return

        # Initiator is white, opponent is black
        view = ChessView(initiator, opponent)
        initial_message = f"Chess: {initiator.mention} (White) vs {opponent.mention} (Black)\n\nTurn: **{initiator.mention}** (White)"
        message = await ctx.send(initial_message, view=view)
        view.message = message

    @commands.command(name="chessbot")
    async def chessbot_prefix(self, ctx: commands.Context, color: str = "white", variant: str = "standard", skill_level: int = 10, think_time: float = 1.0):
        """Play chess against the bot. Usage: !chessbot [white|black] [standard|chess960] [skill 0-20] [time 0.1-5.0]"""
        player = ctx.author
        player_color = chess.WHITE if color.lower() == "white" else chess.BLACK
        variant = variant.lower() # Ensure lowercase

        # Validate inputs
        skill_level = max(0, min(20, skill_level))
        think_time = max(0.1, min(5.0, think_time))

        # Check if variant is supported
        supported_variants = ["standard", "chess960"]
        if variant not in supported_variants:
            await ctx.send(f"Sorry, the variant '{variant}' is not currently supported. Choose from: {', '.join(supported_variants)}")
            return

        view = ChessBotView(player, player_color, variant, skill_level, think_time)

        # Start the engine asynchronously (now handles variant setup)
        await view.start_engine()
        if view.engine is None:
             await ctx.send("Failed to initialize the chess engine. Cannot start game.")
             return # Stop if engine failed

        # Determine initial message based on who moves first
        initial_status = "Your turn." if player_color == chess.WHITE else "Bot is thinking..."
        initial_message = view.get_board_message(initial_status)

        message = await ctx.send(initial_message, view=view)
        view.message = message
        self.active_chess_bot_views[message.id] = view # Track the view

        # If bot is black, make its first move
        if player_color == chess.WHITE:
            pass # Player (White) moves first
        else:
            await view.make_bot_move() # Bot (White) moves first

    # Listener to remove views from tracking when they stop (timeout or game end)
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # Check if the interaction is from a view associated with a message we track
        if interaction.message and interaction.message.id in self.active_chess_bot_views:
            view = self.active_chess_bot_views[interaction.message.id]
            # If the view is finished, remove it from tracking
            if view.is_finished():
                await view.stop_engine() # Ensure engine is stopped
                del self.active_chess_bot_views[interaction.message.id]
                print(f"Removed finished ChessBotView for message {interaction.message.id}")

    # Add a listener for message deletion to clean up views/engines
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.id in self.active_chess_bot_views:
            print(f"Chess game message {message.id} deleted. Stopping associated view and engine.")
            view = self.active_chess_bot_views.pop(message.id)
            await view.stop_engine()
            view.stop()


async def setup(bot: commands.Bot):
    # Ensure the chess library is available
    try:
        import chess
        import chess.engine
        # Check version if needed, e.g., for specific features
        # if chess.__version__ < '1.9.0':
        #     print("Warning: 'python-chess' version might be too old for some features.")
    except ImportError:
        print("Error: 'python-chess' library not found. Please install it (`pip install python-chess`) to use chess features.")
        return # Prevent loading cog if dependency missing

    # Check for Stockfish executable before adding cog
    try:
        get_stockfish_path() # This will raise FileNotFoundError or OSError if not found/configured
        await bot.add_cog(GamesCog(bot))
        print("GamesCog loaded successfully with Stockfish.")
    except (FileNotFoundError, OSError) as e:
        print(f"Error loading GamesCog: {e}. Chess bot features will be unavailable.")
        # Optionally load the cog without chessbot features, or prevent loading entirely
        # Example: Load anyway, but chessbot commands will fail gracefully if engine isn't found later
        # await bot.add_cog(GamesCog(bot))
        # print("GamesCog loaded, but Stockfish engine not found. Chess bot commands will fail.")

    # Note: If you choose to load the cog even without Stockfish,
    # the `chessbot` commands should handle the `view.engine is None` case gracefully.
