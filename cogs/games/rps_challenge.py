import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Optional

# --- Rock Paper Scissors Challenge (Player vs Player) --- START

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
        if self.message and not self.is_finished():
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
            return "player1" # Initiator wins
        else:
            return "player2" # Opponent wins

    @ui.button(label="Rock", style=discord.ButtonStyle.primary, custom_id="rps_rock")
    async def rock_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Rock")

    @ui.button(label="Paper", style=discord.ButtonStyle.success, custom_id="rps_paper")
    async def paper_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Paper")

    @ui.button(label="Scissors", style=discord.ButtonStyle.danger, custom_id="rps_scissors")
    async def scissors_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Scissors")

    async def make_choice(self, interaction: discord.Interaction, choice: str):
        player = interaction.user

        # Record the choice for the appropriate player
        if player.id == self.initiator.id:
            if self.initiator_choice:
                 await interaction.response.send_message("You have already chosen!", ephemeral=True)
                 return
            self.initiator_choice = choice
            await interaction.response.send_message(f"You chose **{choice}**!", ephemeral=True)
        elif player.id == self.opponent.id:
            if self.opponent_choice:
                 await interaction.response.send_message("You have already chosen!", ephemeral=True)
                 return
            self.opponent_choice = choice
            await interaction.response.send_message(f"You chose **{choice}**!", ephemeral=True)
        else: # Should be caught by interaction_check, but safety first
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return

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
            # Edit the original message (stored in self.message)
            if self.message:
                try:
                    await self.message.edit(content=result_message, view=self)
                except discord.NotFound:
                    print("RPS Challenge: Failed to edit original message, likely deleted.")
                except discord.Forbidden:
                    print("RPS Challenge: Missing permissions to edit original message.")
            self.stop()

# --- Rock Paper Scissors Challenge --- END

# --- Slash Command ---
@app_commands.command(name="rpschallenge", description="Challenge another user to a game of Rock-Paper-Scissors.")
@app_commands.describe(opponent="The user you want to challenge.")
async def rpschallenge_slash(interaction: discord.Interaction, opponent: discord.Member):
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

# --- Prefix Command ---
@commands.command(name="rpschallenge")
async def rpschallenge_prefix(ctx: commands.Context, opponent: discord.Member):
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

# --- Setup Function ---
async def setup(bot: commands.Bot, cog: commands.Cog):
    tree = bot.tree
    tree.add_command(rpschallenge_slash, guild=cog.guild)
    bot.add_command(rpschallenge_prefix)
