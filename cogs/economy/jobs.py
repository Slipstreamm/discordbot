import discord
from discord.ext import commands
from discord import app_commands # Required for choices/autocomplete
import datetime
import random
import logging
from typing import Optional, List

# Import database functions from the sibling module
from . import database

log = logging.getLogger(__name__)

# --- Job Definitions ---
# Store job details centrally for easier management
JOB_DEFINITIONS = {
    "miner": {
        "name": "Miner",
        "description": "Mine for ores and gems.",
        "command": "/mine",
        "cooldown": datetime.timedelta(hours=1),
        "base_currency": (15, 30), # Min/Max currency per action
        "base_xp": 15,
        "drops": { # Item Key: Chance (0.0 to 1.0)
            "raw_iron": 0.6,
            "coal": 0.4,
            "shiny_gem": 0.05 # Lower chance for rarer items
        },
        "level_bonus": { # Applied per level
            "currency_increase": 1, # Add +1 to min/max currency range per level
            "rare_find_increase": 0.005 # Increase shiny_gem chance by 0.5% per level
        }
    },
    "fisher": {
        "name": "Fisher",
        "description": "Catch fish and maybe find treasure.",
        "command": "/fish",
        "cooldown": datetime.timedelta(minutes=45),
        "base_currency": (5, 15),
        "base_xp": 10,
        "drops": {
            "common_fish": 0.8, # High chance for common
            "rare_fish": 0.15,
            "treasure_chest": 0.02
        },
        "level_bonus": {
            "currency_increase": 0.5, # Smaller increase
            "rare_find_increase": 0.003 # Increase rare_fish/treasure chance
        }
    },
    "crafter": {
        "name": "Crafter",
        "description": "Use materials to craft valuable items.",
        "command": "/craft",
        "cooldown": datetime.timedelta(minutes=15), # Cooldown per craft action
        "base_currency": (0, 0), # No direct currency
        "base_xp": 20, # Higher XP for crafting
        "recipes": { # Output Item Key: {Input Item Key: Quantity Required}
            "iron_ingot": {"raw_iron": 2, "coal": 1},
            "basic_tool": {"iron_ingot": 3}
        },
        "level_bonus": {
             "unlock_recipe_level": { # Level required to unlock recipe
                 "basic_tool": 5
             },
             # Could add reduced material cost later
        }
    }
}

# Helper function to format time delta
def format_timedelta(delta: datetime.timedelta) -> str:
    """Formats a timedelta into a human-readable string (e.g., 1h 30m 15s)."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "now"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts: # Show seconds if it's the only unit or > 0
        parts.append(f"{seconds}s")
    return " ".join(parts)

class JobsCommands(commands.Cog):
    """Cog containing job-related economy commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Job Management Commands ---

    @commands.hybrid_command(name="jobs", description="List available jobs.")
    async def list_jobs(self, ctx: commands.Context):
        """Displays available jobs and their basic information."""
        embed = discord.Embed(title="Available Jobs", color=discord.Color.blue())
        description = "Choose a job to specialize your earning potential!\n\n"
        for key, details in JOB_DEFINITIONS.items():
            description += f"**{details['name']} (`{key}`)**\n"
            description += f"- {details['description']}\n"
            description += f"- Command: `{details['command']}`\n"
            description += f"- Cooldown: {format_timedelta(details['cooldown'])}\n\n"
        embed.description = description
        embed.set_footer(text="Use /choosejob <job_name> to select a job.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="myjob", description="Show your current job status.")
    async def my_job(self, ctx: commands.Context):
        """Displays the user's current job, level, and XP."""
        user_id = ctx.author.id
        job_info = await database.get_user_job(user_id)

        if not job_info or not job_info.get("name"):
            await ctx.send("You don't currently have a job. Use `/jobs` to see available options and `/choosejob <job_name>` to pick one.", ephemeral=True)
            return

        job_key = job_info["name"]
        level = job_info["level"]
        xp = job_info["xp"]
        job_details = JOB_DEFINITIONS.get(job_key)

        if not job_details:
             await ctx.send(f"Error: Your job '{job_key}' is not recognized. Please contact an admin.", ephemeral=True)
             log.error(f"User {user_id} has unrecognized job '{job_key}' in database.")
             return

        xp_needed = level * 100 # Matches logic in database.py
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Job: {job_details['name']}", color=discord.Color.green())
        embed.add_field(name="Level", value=level, inline=True)
        embed.add_field(name="XP", value=f"{xp} / {xp_needed}", inline=True)

        # Cooldown check
        last_action = job_info.get("last_action")
        cooldown = job_details['cooldown']
        if last_action:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            time_since = now_utc - last_action
            if time_since < cooldown:
                time_left = cooldown - time_since
                embed.add_field(name="Cooldown", value=f"Ready in: {format_timedelta(time_left)}", inline=False)
            else:
                embed.add_field(name="Cooldown", value="Ready!", inline=False)
        else:
             embed.add_field(name="Cooldown", value="Ready!", inline=False)

        embed.set_footer(text=f"Use {job_details['command']} to perform your job action.")
        await ctx.send(embed=embed)

    # Autocomplete for choosejob and leavejob
    async def job_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=details["name"], value=key)
            for key, details in JOB_DEFINITIONS.items() if current.lower() in key.lower() or current.lower() in details["name"].lower()
        ][:25] # Limit to 25 choices

    @commands.hybrid_command(name="choosejob", description="Select a job to pursue.")
    @app_commands.autocomplete(job_name=job_autocomplete)
    async def choose_job(self, ctx: commands.Context, job_name: str):
        """Sets the user's active job."""
        user_id = ctx.author.id
        job_key = job_name.lower()

        if job_key not in JOB_DEFINITIONS:
            await ctx.send(f"Invalid job name '{job_name}'. Use `/jobs` to see available options.", ephemeral=True)
            return

        current_job_info = await database.get_user_job(user_id)
        if current_job_info and current_job_info.get("name") == job_key:
            await ctx.send(f"You are already a {JOB_DEFINITIONS[job_key]['name']}.", ephemeral=True)
            return

        # Implement switching cost/cooldown here if desired
        # For now, allow free switching, resetting progress
        await database.set_user_job(user_id, job_key)
        await ctx.send(f"Congratulations! You are now a **{JOB_DEFINITIONS[job_key]['name']}**. Your previous job progress (if any) has been reset.")

    @commands.hybrid_command(name="leavejob", description="Leave your current job.")
    async def leave_job(self, ctx: commands.Context):
        """Abandons the user's current job, resetting progress."""
        user_id = ctx.author.id
        current_job_info = await database.get_user_job(user_id)

        if not current_job_info or not current_job_info.get("name"):
            await ctx.send("You don't have a job to leave.", ephemeral=True)
            return

        job_key = current_job_info["name"]
        job_name = JOB_DEFINITIONS.get(job_key, {}).get("name", "Unknown Job")

        await database.set_user_job(user_id, None) # Set job to NULL
        await ctx.send(f"You have left your job as a **{job_name}**. Your level and XP for this job have been reset. You can choose a new job with `/choosejob`.")

    # --- Job Action Commands ---

    async def _handle_job_action(self, ctx: commands.Context, job_key: str):
        """Internal handler for job actions to check cooldowns, grant rewards, etc."""
        user_id = ctx.author.id
        job_info = await database.get_user_job(user_id)

        # 1. Check if user has the correct job
        if not job_info or job_info.get("name") != job_key:
            correct_job_info = await database.get_user_job(user_id)
            if correct_job_info and correct_job_info.get("name"):
                 correct_job_details = JOB_DEFINITIONS.get(correct_job_info["name"])
                 await ctx.send(f"You need to be a {JOB_DEFINITIONS[job_key]['name']} to use this command. Your current job is {correct_job_details['name']}. Use `{correct_job_details['command']}` instead, or change jobs with `/choosejob`.", ephemeral=True)
            else:
                 await ctx.send(f"You need to be a {JOB_DEFINITIONS[job_key]['name']} to use this command. You don't have a job. Use `/choosejob {job_key}` first.", ephemeral=True)
            return None # Indicate failure

        job_details = JOB_DEFINITIONS[job_key]
        level = job_info["level"]

        # 2. Check Cooldown
        last_action = job_info.get("last_action")
        cooldown = job_details['cooldown']
        if last_action:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            time_since = now_utc - last_action
            if time_since < cooldown:
                time_left = cooldown - time_since
                await ctx.send(f"You need to wait **{format_timedelta(time_left)}** before you can {job_key} again.", ephemeral=True)
                return None # Indicate failure

        # 3. Set Cooldown Immediately
        await database.set_job_cooldown(user_id)

        # 4. Calculate Rewards
        level_bonus = job_details.get("level_bonus", {})
        currency_bonus = level * level_bonus.get("currency_increase", 0)
        min_curr, max_curr = job_details["base_currency"]
        currency_earned = random.randint(int(min_curr + currency_bonus), int(max_curr + currency_bonus))

        items_found = {}
        if "drops" in job_details:
            rare_find_bonus = level * level_bonus.get("rare_find_increase", 0)
            for item_key, base_chance in job_details["drops"].items():
                # Apply level bonus to specific rare items if configured (e.g., gems for miner)
                current_chance = base_chance
                if item_key == 'shiny_gem' and job_key == 'miner':
                    current_chance += rare_find_bonus
                elif (item_key == 'rare_fish' or item_key == 'treasure_chest') and job_key == 'fisher':
                     current_chance += rare_find_bonus

                if random.random() < current_chance:
                    items_found[item_key] = items_found.get(item_key, 0) + 1

        # 5. Grant Rewards (DB updates)
        if currency_earned > 0:
            await database.update_balance(user_id, currency_earned)
        for item_key, quantity in items_found.items():
            await database.add_item_to_inventory(user_id, item_key, quantity)

        # 6. Grant XP & Handle Level Up
        xp_earned = job_details["base_xp"] # Could add level bonus to XP later
        new_level, new_xp, did_level_up = await database.add_job_xp(user_id, xp_earned)

        # 7. Construct Response Message
        response_parts = []
        if currency_earned > 0:
            response_parts.append(f"earned **${currency_earned:,}**")
        if items_found:
            item_strings = []
            for item_key, quantity in items_found.items():
                 item_details = await database.get_item_details(item_key)
                 item_name = item_details['name'] if item_details else item_key
                 item_strings.append(f"{quantity}x **{item_name}**")
            response_parts.append(f"found {', '.join(item_strings)}")

        response_parts.append(f"gained **{xp_earned} XP**")

        action_verb = job_key.capitalize() # "Mine", "Fish"
        message = f"⛏️ You {action_verb} and {', '.join(response_parts)}." # Default message

        # Customize message based on job
        if job_key == "miner":
             message = f"⛏️ You mined and {', '.join(response_parts)}."
        elif job_key == "fisher":
             message = f"🎣 You fished and {', '.join(response_parts)}."
        # Crafter handled separately

        if did_level_up:
            message += f"\n**Congratulations! You reached Level {new_level} in {job_details['name']}!** 🎉"

        current_balance = await database.get_balance(user_id)
        message += f"\nYour current balance is **${current_balance:,}**."

        return message # Indicate success and return message

    @commands.hybrid_command(name="mine", description="Mine for ores and gems (Miner job).")
    async def mine(self, ctx: commands.Context):
        """Performs the Miner job action."""
        result_message = await self._handle_job_action(ctx, "miner")
        if result_message:
            await ctx.send(result_message)

    @commands.hybrid_command(name="fish", description="Catch fish and maybe find treasure (Fisher job).")
    async def fish(self, ctx: commands.Context):
        """Performs the Fisher job action."""
        result_message = await self._handle_job_action(ctx, "fisher")
        if result_message:
            await ctx.send(result_message)

    # --- Crafter Specific ---
    async def craft_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        job_info = await database.get_user_job(user_id)
        choices = []
        if job_info and job_info.get("name") == "crafter":
            crafter_details = JOB_DEFINITIONS["crafter"]
            level = job_info["level"]
            for item_key, recipe in crafter_details.get("recipes", {}).items():
                # Check level requirement
                required_level = crafter_details.get("level_bonus", {}).get("unlock_recipe_level", {}).get(item_key, 1)
                if level < required_level:
                    continue

                item_details = await database.get_item_details(item_key)
                item_name = item_details['name'] if item_details else item_key
                if current.lower() in item_key.lower() or current.lower() in item_name.lower():
                     choices.append(app_commands.Choice(name=item_name, value=item_key))
        return choices[:25]

    @commands.hybrid_command(name="craft", description="Craft items using materials (Crafter job).")
    @app_commands.autocomplete(item_to_craft=craft_autocomplete)
    async def craft(self, ctx: commands.Context, item_to_craft: str):
        """Performs the Crafter job action."""
        user_id = ctx.author.id
        job_key = "crafter"
        job_info = await database.get_user_job(user_id)

        # 1. Check if user has the correct job
        if not job_info or job_info.get("name") != job_key:
            await ctx.send("You need to be a Crafter to use this command. Use `/choosejob crafter` first.", ephemeral=True)
            return

        job_details = JOB_DEFINITIONS[job_key]
        level = job_info["level"]
        recipe_key = item_to_craft.lower()

        # 2. Check if recipe exists
        recipes = job_details.get("recipes", {})
        if recipe_key not in recipes:
            await ctx.send(f"Unknown recipe: '{item_to_craft}'. Check available recipes.", ephemeral=True) # TODO: Add /recipes command?
            return

        # 3. Check Level Requirement
        required_level = job_details.get("level_bonus", {}).get("unlock_recipe_level", {}).get(recipe_key, 1)
        if level < required_level:
             await ctx.send(f"You need to be Level {required_level} to craft this item. You are currently Level {level}.", ephemeral=True)
             return

        # 4. Check Cooldown
        last_action = job_info.get("last_action")
        cooldown = job_details['cooldown']
        if last_action:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            time_since = now_utc - last_action
            if time_since < cooldown:
                time_left = cooldown - time_since
                await ctx.send(f"You need to wait **{format_timedelta(time_left)}** before you can craft again.", ephemeral=True)
                return

        # 5. Check Materials
        required_materials = recipes[recipe_key]
        inventory = await database.get_inventory(user_id)
        inventory_map = {item['key']: item['quantity'] for item in inventory}
        missing_materials = []
        can_craft = True
        for mat_key, mat_qty in required_materials.items():
            if inventory_map.get(mat_key, 0) < mat_qty:
                can_craft = False
                mat_details = await database.get_item_details(mat_key)
                mat_name = mat_details['name'] if mat_details else mat_key
                missing_materials.append(f"{mat_qty - inventory_map.get(mat_key, 0)}x {mat_name}")

        if not can_craft:
            await ctx.send(f"You don't have the required materials. You still need: {', '.join(missing_materials)}.", ephemeral=True)
            return

        # 6. Set Cooldown Immediately
        await database.set_job_cooldown(user_id)

        # 7. Consume Materials & Grant Item
        success = True
        for mat_key, mat_qty in required_materials.items():
            if not await database.remove_item_from_inventory(user_id, mat_key, mat_qty):
                success = False
                log.error(f"Failed to remove material {mat_key} x{mat_qty} for user {user_id} during crafting, despite check.")
                await ctx.send("An error occurred while consuming materials. Please try again.", ephemeral=True)
                # Should ideally revert cooldown here, but that's complex.
                return

        if success:
            await database.add_item_to_inventory(user_id, recipe_key, 1)

            # 8. Grant XP & Handle Level Up
            xp_earned = job_details["base_xp"]
            new_level, new_xp, did_level_up = await database.add_job_xp(user_id, xp_earned)

            # 9. Construct Response
            crafted_item_details = await database.get_item_details(recipe_key)
            crafted_item_name = crafted_item_details['name'] if crafted_item_details else recipe_key
            message = f"🛠️ You successfully crafted 1x **{crafted_item_name}** and gained **{xp_earned} XP**."

            if did_level_up:
                message += f"\n**Congratulations! You reached Level {new_level} in {job_details['name']}!** 🎉"

            await ctx.send(message)


    # --- Inventory Commands ---

    @commands.hybrid_command(name="inventory", aliases=["inv"], description="View your items.")
    async def inventory(self, ctx: commands.Context):
        """Displays the items in the user's inventory."""
        user_id = ctx.author.id
        inventory_items = await database.get_inventory(user_id)

        if not inventory_items:
            await ctx.send("Your inventory is empty.", ephemeral=True)
            return

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Inventory", color=discord.Color.orange())
        description = ""
        for item in inventory_items:
            sell_info = f" (Sell: ${item['sell_price']:,})" if item['sell_price'] > 0 else ""
            description += f"- **{item['name']}** x{item['quantity']}{sell_info}\n"
            if item['description']:
                 description += f"  *({item['description']})*\n" # Add description if available

        # Handle potential description length limit
        if len(description) > 4000: # Embed description limit is 4096
             description = description[:4000] + "\n... (Inventory too large to display fully)"

        embed.description = description
        await ctx.send(embed=embed)

    # Autocomplete for sell command
    async def inventory_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        user_id = interaction.user.id
        inventory = await database.get_inventory(user_id)
        return [
            app_commands.Choice(name=f"{item['name']} (Have: {item['quantity']})", value=item['key'])
            for item in inventory if item['sell_price'] > 0 and (current.lower() in item['key'].lower() or current.lower() in item['name'].lower())
        ][:25]

    @commands.hybrid_command(name="sell", description="Sell items from your inventory.")
    @app_commands.autocomplete(item_key=inventory_autocomplete)
    async def sell(self, ctx: commands.Context, item_key: str, quantity: Optional[int] = 1):
        """Sells a specified quantity of an item from the inventory."""
        user_id = ctx.author.id

        if quantity <= 0:
            await ctx.send("Please enter a positive quantity to sell.", ephemeral=True)
            return

        item_details = await database.get_item_details(item_key)
        if not item_details:
            await ctx.send(f"Invalid item key '{item_key}'. Check your `/inventory`.", ephemeral=True)
            return

        if item_details['sell_price'] <= 0:
            await ctx.send(f"You cannot sell **{item_details['name']}**.", ephemeral=True)
            return

        # Try to remove items first
        removed = await database.remove_item_from_inventory(user_id, item_key, quantity)

        if not removed:
            # Get current quantity to show in error message
            inventory = await database.get_inventory(user_id)
            current_quantity = 0
            for item in inventory:
                if item['key'] == item_key:
                    current_quantity = item['quantity']
                    break
            await ctx.send(f"You don't have {quantity}x **{item_details['name']}** to sell. You only have {current_quantity}.", ephemeral=True)
            return

        # Grant money if removal was successful
        total_earnings = item_details['sell_price'] * quantity
        await database.update_balance(user_id, total_earnings)

        current_balance = await database.get_balance(user_id)
        await ctx.send(f"💰 You sold {quantity}x **{item_details['name']}** for **${total_earnings:,}**. Your new balance is **${current_balance:,}**.")
