import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import datetime
from typing import Dict, List, Optional, Tuple

# File to store marriage data
MARRIAGES_FILE = "data/marriages.json"

# Ensure the data directory exists
os.makedirs(os.path.dirname(MARRIAGES_FILE), exist_ok=True)

class MarriageView(ui.View):
    """View for marriage proposal buttons"""

    def __init__(self, cog: 'MarriageCog', proposer: discord.Member, proposed_to: discord.Member):
        super().__init__(timeout=300.0)  # 5-minute timeout
        self.cog = cog
        self.proposer = proposer
        self.proposed_to = proposed_to
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the proposed person to interact with the buttons"""
        if interaction.user.id != self.proposed_to.id:
            await interaction.response.send_message("This proposal isn't for you to answer!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        """Handle timeout - edit the message to show the proposal expired"""
        if self.message:
            # Disable all buttons
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            # Update the message
            await self.message.edit(
                content=f"💔 {self.proposed_to.mention} didn't respond to {self.proposer.mention}'s proposal in time.",
                view=self
            )

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="💍")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Accept the marriage proposal"""
        # Create the marriage
        success, message = await self.cog.create_marriage(self.proposer, self.proposed_to)

        # Disable all buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if success:
            await interaction.response.edit_message(
                content=f"💖 {self.proposed_to.mention} has accepted {self.proposer.mention}'s proposal! Congratulations on your marriage!",
                view=self
            )
        else:
            await interaction.response.edit_message(
                content=f"❌ {message}",
                view=self
            )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="💔")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decline the marriage proposal"""
        # Disable all buttons
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await interaction.response.edit_message(
            content=f"💔 {self.proposed_to.mention} has declined {self.proposer.mention}'s proposal.",
            view=self
        )

class MarriageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.marriages = {}
        self.load_marriages()

    def load_marriages(self):
        """Load marriages from JSON file"""
        if os.path.exists(MARRIAGES_FILE):
            try:
                with open(MARRIAGES_FILE, "r") as f:
                    data = json.load(f)
                    # Convert string keys back to integers
                    self.marriages = {int(k): v for k, v in data.items()}
                print(f"Loaded {len(self.marriages)} marriages")
            except Exception as e:
                print(f"Error loading marriages: {e}")
                self.marriages = {}

    def save_marriages(self):
        """Save marriages to JSON file"""
        try:
            # Convert int keys to strings for JSON serialization
            serializable_data = {str(k): v for k, v in self.marriages.items()}
            with open(MARRIAGES_FILE, "w") as f:
                json.dump(serializable_data, f, indent=4)
        except Exception as e:
            print(f"Error saving marriages: {e}")

    async def create_marriage(self, user1: discord.Member, user2: discord.Member) -> Tuple[bool, str]:
        """Create a new marriage between two users"""
        # Check if either user is already married
        user1_id = user1.id
        user2_id = user2.id

        # Check if user1 is already married
        if user1_id in self.marriages and self.marriages[user1_id]["status"] == "married":
            return False, f"{user1.display_name} is already married!"

        # Check if user2 is already married
        if user2_id in self.marriages and self.marriages[user2_id]["status"] == "married":
            return False, f"{user2.display_name} is already married!"

        # Create marriage data
        marriage_date = datetime.datetime.now().isoformat()

        # Store marriage data for both users
        marriage_data = {
            "partner_id": user2_id,
            "marriage_date": marriage_date,
            "status": "married"
        }
        self.marriages[user1_id] = marriage_data

        marriage_data = {
            "partner_id": user1_id,
            "marriage_date": marriage_date,
            "status": "married"
        }
        self.marriages[user2_id] = marriage_data

        # Save to file
        self.save_marriages()

        return True, "Marriage created successfully!"

    async def divorce(self, user_id: int) -> Tuple[bool, str]:
        """End a marriage"""
        if user_id not in self.marriages or self.marriages[user_id]["status"] != "married":
            return False, "You are not currently married!"

        # Get partner's ID
        partner_id = self.marriages[user_id]["partner_id"]

        # Update status for both users
        if user_id in self.marriages:
            self.marriages[user_id]["status"] = "divorced"

        if partner_id in self.marriages:
            self.marriages[partner_id]["status"] = "divorced"

        # Save to file
        self.save_marriages()

        return True, "Divorce completed."

    def get_marriage_days(self, user_id: int) -> int:
        """Get the number of days a marriage has lasted"""
        if user_id not in self.marriages:
            return 0

        marriage_data = self.marriages[user_id]
        marriage_date = datetime.datetime.fromisoformat(marriage_data["marriage_date"])
        current_date = datetime.datetime.now()

        # Calculate days
        delta = current_date - marriage_date
        return delta.days

    def get_all_marriages(self) -> List[Tuple[int, int, int]]:
        """Get all active marriages sorted by duration"""
        active_marriages = []
        processed_pairs = set()

        for user_id, marriage_data in self.marriages.items():
            if marriage_data["status"] == "married":
                partner_id = marriage_data["partner_id"]

                # Avoid duplicates (each marriage appears twice in self.marriages)
                pair = tuple(sorted([user_id, partner_id]))
                if pair in processed_pairs:
                    continue

                processed_pairs.add(pair)

                # Calculate days
                marriage_date = datetime.datetime.fromisoformat(marriage_data["marriage_date"])
                current_date = datetime.datetime.now()
                delta = current_date - marriage_date
                days = delta.days

                active_marriages.append((user_id, partner_id, days))

        # Sort by days (descending)
        return sorted(active_marriages, key=lambda x: x[2], reverse=True)

    @app_commands.command(name="propose", description="Propose marriage to another user")
    @app_commands.describe(user="The user you want to propose to")
    async def propose_command(self, interaction: discord.Interaction, user: discord.Member):
        """Propose marriage to another user"""
        proposer = interaction.user

        # Check if proposing to self
        if user.id == proposer.id:
            await interaction.response.send_message("You can't propose to yourself!", ephemeral=True)
            return

        # Check if proposer is already married
        if proposer.id in self.marriages and self.marriages[proposer.id]["status"] == "married":
            partner_id = self.marriages[proposer.id]["partner_id"]
            partner = interaction.guild.get_member(partner_id)
            partner_name = partner.display_name if partner else "someone"
            await interaction.response.send_message(f"You're already married to {partner_name}!", ephemeral=True)
            return

        # Check if proposed person is already married
        if user.id in self.marriages and self.marriages[user.id]["status"] == "married":
            partner_id = self.marriages[user.id]["partner_id"]
            partner = interaction.guild.get_member(partner_id)
            partner_name = partner.display_name if partner else "someone"
            await interaction.response.send_message(f"{user.display_name} is already married to {partner_name}!", ephemeral=True)
            return

        # Create the proposal view
        view = MarriageView(self, proposer, user)

        # Send the proposal
        await interaction.response.send_message(
            f"💍 {proposer.mention} has proposed to {user.mention}! Will they accept?",
            view=view
        )

        # Store the message for timeout handling
        view.message = await interaction.original_response()

    @app_commands.command(name="marriage", description="View your current marriage status")
    async def marriage_command(self, interaction: discord.Interaction):
        """View your current marriage status"""
        user_id = interaction.user.id

        if user_id not in self.marriages or self.marriages[user_id]["status"] != "married":
            await interaction.response.send_message("You are not currently married.", ephemeral=False)
            return

        # Get marriage info
        marriage_data = self.marriages[user_id]
        partner_id = marriage_data["partner_id"]
        partner = interaction.guild.get_member(partner_id)
        partner_name = partner.display_name if partner else f"Unknown User ({partner_id})"

        # Calculate days
        days = self.get_marriage_days(user_id)

        # Create embed
        embed = discord.Embed(
            title="💖 Marriage Status",
            color=discord.Color.pink()
        )
        embed.add_field(name="Married To", value=partner.mention if partner else partner_name, inline=False)
        embed.add_field(name="Marriage Date", value=marriage_data["marriage_date"].split("T")[0], inline=True)
        embed.add_field(name="Days Married", value=str(days), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="divorce", description="End your current marriage")
    async def divorce_command(self, interaction: discord.Interaction):
        """End your current marriage"""
        user_id = interaction.user.id

        # Check if user is married
        if user_id not in self.marriages or self.marriages[user_id]["status"] != "married":
            await interaction.response.send_message("You are not currently married.", ephemeral=True)
            return

        # Get partner info
        partner_id = self.marriages[user_id]["partner_id"]
        partner = interaction.guild.get_member(partner_id)
        partner_name = partner.mention if partner else f"Unknown User ({partner_id})"

        # Process divorce
        success, message = await self.divorce(user_id)

        if success:
            await interaction.response.send_message(f"💔 {interaction.user.mention} has divorced {partner_name}. The marriage has ended.", ephemeral=False)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="marriages", description="View the marriage leaderboard")
    async def marriages_command(self, interaction: discord.Interaction):
        """View the marriage leaderboard"""
        marriages = self.get_all_marriages()

        if not marriages:
            await interaction.response.send_message("There are no active marriages.", ephemeral=False)
            return

        # Create embed
        embed = discord.Embed(
            title="💖 Marriage Leaderboard",
            description="Marriages ranked by duration",
            color=discord.Color.pink()
        )

        # Add top 10 marriages
        for i, (user1_id, user2_id, days) in enumerate(marriages[:10], 1):
            user1 = interaction.guild.get_member(user1_id)
            user2 = interaction.guild.get_member(user2_id)

            user1_name = user1.display_name if user1 else f"Unknown User ({user1_id})"
            user2_name = user2.display_name if user2 else f"Unknown User ({user2_id})"

            embed.add_field(
                name=f"{i}. {user1_name} & {user2_name}",
                value=f"{days} days",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(MarriageCog(bot))
