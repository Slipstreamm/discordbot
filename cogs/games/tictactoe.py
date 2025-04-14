import discord
from discord.ext import commands
from discord import ui
from typing import Optional, List

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
