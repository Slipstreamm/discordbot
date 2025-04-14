import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
from typing import Optional, List
import sys
import os

# Ensure the tictactoe engine can be imported (assuming it's in the project root)
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR)) # Go up two levels (cogs/games -> cogs -> root)
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)
    from tictactoe import TicTacToe
except ImportError:
    print("Error: Could not import TicTacToe engine from project root.")
    TicTacToe = None # Set to None to handle import failure gracefully

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
            # Handle specific engine errors like "Invalid move" or "Game is over"
            await interaction.response.send_message(f"Invalid move: {str(e)}", ephemeral=True)
        except Exception as e:
            # Catch other potential errors during bot's turn or message editing
            print(f"Error during Bot TTT callback: {e}")
            await interaction.followup.send("An unexpected error occurred.", ephemeral=True)


class BotTicTacToeView(ui.View):
    def __init__(self, game, player: discord.Member):
        super().__init__(timeout=300.0)  # 5 minute timeout
        self.game = game  # Instance of the TicTacToe engine
        self.player = player
        self.message: Optional[discord.Message] = None

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
            # If the interaction was deferred (bot move), use followup.edit_message
            if interaction.response.is_done():
                 await interaction.followup.edit_message(
                     message_id=self.message.id,
                     content=f"{content}\n\n{board_display}",
                     view=self
                 )
            # If interaction was not deferred (player move ended game), use response.edit_message
            else:
                 await interaction.response.edit_message(
                     content=f"{content}\n\n{board_display}",
                     view=self
                 )
        except (discord.NotFound, discord.HTTPException):
            # Fallback for interaction timeouts or message deleted
            if self.message:
                try:
                    await self.message.edit(content=f"{content}\n\n{board_display}", view=self)
                except: pass # Ignore further errors
        self.stop()

    async def on_timeout(self):
        if self.message and not self.is_finished():
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

# --- Slash Command ---
@app_commands.command(name="tictactoebot", description="Play a game of Tic-Tac-Toe against the bot.")
@app_commands.describe(difficulty="Bot difficulty: random, rule, or minimax (default: minimax)")
@app_commands.choices(difficulty=[
    app_commands.Choice(name="Random (Easy)", value="random"),
    app_commands.Choice(name="Rule-based (Medium)", value="rule"),
    app_commands.Choice(name="Minimax (Hard)", value="minimax")
])
async def tictactoebot_slash(interaction: discord.Interaction, difficulty: Optional[app_commands.Choice[str]] = None):
    """Play a game of Tic-Tac-Toe against the bot."""
    if TicTacToe is None:
        await interaction.response.send_message("Error: TicTacToe game engine module not found or failed to import.", ephemeral=True)
        return

    difficulty_value = difficulty.value if difficulty else "minimax"

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

# --- Prefix Command ---
@commands.command(name="tictactoebot")
async def tictactoebot_prefix(ctx: commands.Context, difficulty: str = "minimax"):
    """(Prefix) Play Tic-Tac-Toe against the bot."""
    if TicTacToe is None:
        await ctx.send("Error: TicTacToe game engine module not found or failed to import.")
        return

    difficulty_value = difficulty.lower()
    valid_difficulties = ["random", "rule", "minimax"]
    if difficulty_value not in valid_difficulties:
        await ctx.send(f"Invalid difficulty! Choose from: {', '.join(valid_difficulties)}")
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

# --- Setup Function ---
async def setup(bot: commands.Bot, cog: commands.Cog):
    # Add slash command if TicTacToe engine loaded
    if TicTacToe:
        tree = bot.tree
        tree.add_command(tictactoebot_slash, guild=cog.guild)
        bot.add_command(tictactoebot_prefix)
    else:
        print("TicTacToe Bot commands not loaded due to missing engine.")
