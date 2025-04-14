import discord
from discord import ui
from typing import Optional, List

# --- Tic Tac Toe (Player vs Player) ---
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

# --- Tic Tac Toe Bot Game ---
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
            import asyncio
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
