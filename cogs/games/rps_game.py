import discord
from discord import ui
from typing import Optional

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
