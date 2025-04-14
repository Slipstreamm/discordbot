import discord
from discord.ext import commands
from discord import ui
import random
from typing import Optional

class CoinFlipView(ui.View):
    def __init__(self, initiator: discord.Member, opponent: discord.Member):
        super().__init__(timeout=180.0)  # 3-minute timeout
        self.initiator = initiator
        self.opponent = opponent
        self.initiator_choice: Optional[str] = None
        self.opponent_choice: Optional[str] = None
        self.result: Optional[str] = None
        self.winner: Optional[discord.Member] = None
        self.message: Optional[discord.Message] = None  # To store the message for editing

        # Initial state: Initiator chooses side
        self.add_item(self.HeadsButton())
        self.add_item(self.TailsButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check who is interacting at which stage."""
        if self.initiator_choice is None:
            if interaction.user.id != self.initiator.id:
                await interaction.response.send_message("Only the initiator can choose their side.", ephemeral=True)
                return False
            return True
        else:
            if interaction.user.id != self.opponent.id:
                await interaction.response.send_message("Only the opponent can accept or decline the game.", ephemeral=True)
                return False
            return True

    async def update_view_state(self, interaction: discord.Interaction):
        """Updates the view items based on the current state."""
        self.clear_items()
        if self.initiator_choice is None:
            self.add_item(self.HeadsButton())
            self.add_item(self.TailsButton())
        elif self.result is None:
            self.add_item(self.AcceptButton())
            self.add_item(self.DeclineButton())
        else:
            pass

        if self.message:
            try:
                if interaction and interaction.message and interaction.message.id == self.message.id:
                    await interaction.response.edit_message(view=self)
                else:
                    await self.message.edit(view=self)
            except discord.NotFound:
                print("CoinFlipView: Failed to edit message, likely deleted.")
            except discord.Forbidden:
                print("CoinFlipView: Missing permissions to edit message.")
            except discord.InteractionResponded:
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
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass

    async def on_timeout(self):
        if self.message and not self.is_finished():
            await self.disable_all_buttons()
            timeout_msg = f"Coin flip game between {self.initiator.mention} and {self.opponent.mention} timed out."
            try:
                await self.message.edit(content=timeout_msg, view=self)
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass
        self.stop()

    class HeadsButton(ui.Button):
        def __init__(self):
            super().__init__(label="Heads", style=discord.ButtonStyle.primary, custom_id="cf_heads")

        async def callback(self, interaction: discord.Interaction):
            view: 'CoinFlipView' = self.view
            view.initiator_choice = "Heads"
            view.opponent_choice = "Tails"
            await view.update_view_state(interaction)
            await interaction.edit_original_response(
                content=f"{view.opponent.mention}, {view.initiator.mention} has chosen **Heads**! You get **Tails**. Do you accept?"
            )

    class TailsButton(ui.Button):
        def __init__(self):
            super().__init__(label="Tails", style=discord.ButtonStyle.primary, custom_id="cf_tails")

        async def callback(self, interaction: discord.Interaction):
            view: 'CoinFlipView' = self.view
            view.initiator_choice = "Tails"
            view.opponent_choice = "Heads"
            await view.update_view_state(interaction)
            await interaction.edit_original_response(
                content=f"{view.opponent.mention}, {view.initiator.mention} has chosen **Tails**! You get **Heads**. Do you accept?"
            )

    class AcceptButton(ui.Button):
        def __init__(self):
            super().__init__(label="Accept", style=discord.ButtonStyle.success, custom_id="cf_accept")

        async def callback(self, interaction: discord.Interaction):
            view: 'CoinFlipView' = self.view
            view.result = random.choice(["Heads", "Tails"])

            if view.result == view.initiator_choice:
                view.winner = view.initiator
            else:
                view.winner = view.opponent

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
