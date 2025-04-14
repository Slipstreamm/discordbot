import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
from typing import Optional, Union
import chess
import chess.pgn
import io

# Import shared utilities
from .chess_utils import generate_board_image, MoveInputModal

# --- Chess Game (Player vs Player) --- START

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
            # Check if the interaction is for the modal, allow if so (modal handles turn check)
            if interaction.type == discord.InteractionType.modal_submit:
                return True # Let the modal handle the turn check
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
            if "wins" in result:
                if self.white_player.mention in result: pgn_result_code = "1-0"
                elif self.black_player.mention in result: pgn_result_code = "0-1"
            elif "draw" in result:
                pgn_result_code = "1/2-1/2"
            elif "resigned" in result:
                 pgn_result_code = "0-1" if self.white_player.mention in result else "1-0" # Opposite player wins on resign
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
        # Add move to PGN
        try:
            self.pgn_node = self.pgn_node.add_variation(move)
        except Exception as e:
            print(f"Error adding move to PGN: {e}") # Log PGN errors

        self.board.push(move)
        self.last_move = move # Store for highlighting

        # Switch turns
        self.current_player = self.black_player if self.current_player == self.white_player else self.white_player

        # Update DMs asynchronously
        dm_update_tasks = [
            self._send_or_update_dm(self.white_player),
            self._send_or_update_dm(self.black_player)
        ]
        asyncio.gather(*dm_update_tasks) # Don't wait for DMs

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
                # Use followup.edit_message if interaction was deferred (e.g., after modal)
                if interaction_or_message.response.is_done():
                     await interaction_or_message.edit_original_response(content=content, attachments=[board_image], view=self)
                # Otherwise, use response.edit_message (e.g., initial send or button click)
                else:
                     await interaction_or_message.response.edit_message(content=content, attachments=[board_image], view=self)
            elif isinstance(interaction_or_message, discord.Message):
                 await interaction_or_message.edit(content=content, attachments=[board_image], view=self)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"ChessView: Failed to update message: {e}")
            # Handle potential errors like message deleted or permissions lost
            self.stop() # Stop the view if message interaction fails

    def get_game_over_message(self, outcome: chess.Outcome) -> str:
        """Generates the game over message based on the outcome."""
        winner_mention = "Nobody"
        winner_color = ""
        if outcome.winner == chess.WHITE:
            winner_mention = self.white_player.mention
            winner_color = "White"
        elif outcome.winner == chess.BLACK:
            winner_mention = self.black_player.mention
            winner_color = "Black"

        termination_reason = outcome.termination.name.replace("_", " ").title()

        if outcome.winner is not None:
            message = f"Game Over! **{winner_mention}** ({winner_color}) wins by {termination_reason}! 🎉"
        else: # Draw
            message = f"Game Over! It's a draw by {termination_reason}! 🤝"

        return message

    async def end_game(self, interaction_or_message: Union[discord.Interaction, discord.Message], message_content: str):
        """Ends the game, disables buttons, and updates the message."""
        if self.is_finished(): return # Avoid running twice

        await self.disable_all_buttons()

        # Update DMs with the final result
        dm_update_tasks = [
            self._send_or_update_dm(self.white_player, result=message_content),
            self._send_or_update_dm(self.black_player, result=message_content)
        ]
        await asyncio.gather(*dm_update_tasks)

        board_image = generate_board_image(self.board, self.last_move, perspective_white=True) # Final board perspective

        # Determine how to update the final message
        try:
            if isinstance(interaction_or_message, discord.Interaction):
                if interaction_or_message.response.is_done():
                    # If interaction was already responded to/deferred (e.g., move submission)
                    await interaction_or_message.edit_original_response(content=message_content, attachments=[board_image], view=self)
                else:
                    # If interaction is fresh (e.g., resign button)
                    await interaction_or_message.response.edit_message(content=message_content, attachments=[board_image], view=self)
            elif isinstance(interaction_or_message, discord.Message):
                 # If called internally (e.g., on_timeout)
                 await interaction_or_message.edit(content=message_content, attachments=[board_image], view=self)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"ChessView: Failed to edit final game message: {e}")
            # Attempt to send a new message if editing failed and we have context
            channel = None
            if isinstance(interaction_or_message, discord.Interaction):
                channel = interaction_or_message.channel
            elif isinstance(interaction_or_message, discord.Message):
                channel = interaction_or_message.channel

            if channel:
                try:
                    await channel.send(content=message_content, files=[board_image])
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
            timeout_msg = f"Chess game between {self.white_player.mention} and {self.black_player.mention} timed out."
            await self.end_game(self.message, timeout_msg) # Use end_game for cleanup

# --- Chess Game --- END

# --- Slash Command ---
# MOVED TO GamesCog

# --- Prefix Command ---
# MOVED TO GamesCog

# --- Setup Function ---
# REMOVED - Commands moved to GamesCog
