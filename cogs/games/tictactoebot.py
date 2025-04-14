import discord
from discord.ext import commands
from discord import ui
import asyncio
import sys
import os
from typing import Optional
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
