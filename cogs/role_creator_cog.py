import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID")) # Although commands.is_owner() handles this, loading for clarity/potential future use

class RoleCreatorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='create_roles', help='Creates predefined roles for reaction roles. Owner only.')
    @commands.is_owner() # Restricts this command to the bot owner specified during bot setup
    async def create_roles(self, ctx):
        """Creates a set of predefined roles typically used with reaction roles."""
        guild = ctx.guild
        if not guild:
            await ctx.send("This command can only be used in a server.")
            return

        # Check if the bot has permission to manage roles
        if not ctx.me.guild_permissions.manage_roles:
            await ctx.send("I don't have permission to manage roles.")
            logger.warning(f"Missing 'Manage Roles' permission in guild {guild.id} ({guild.name}).")
            return

        # Define color mapping for specific roles
        color_map = {
            "Red": discord.Color.red(),
            "Blue": discord.Color.blue(),
            "Green": discord.Color.green(),
            "Yellow": discord.Color.gold(),
            "Purple": discord.Color.purple(),
            "Orange": discord.Color.orange(),
            "Pink": discord.Color.fuchsia(),
            "Black": discord.Color(0x010101), # Near black to avoid blending with themes
            "White": discord.Color(0xFEFEFE)  # Near white to avoid blending
        }

        await ctx.send("Starting role creation/update process...")
        logger.info(f"Role creation/update initiated by {ctx.author} in guild {guild.id} ({guild.name}).")

        role_categories = {
            "Colors": ["Red", "Blue", "Green", "Yellow", "Purple", "Orange", "Pink", "Black", "White"],
            "Regions": ["NA East", "NA West", "EU", "Asia", "Oceania", "South America"],
            "Pronouns": ["He/Him", "She/Her", "They/Them", "Ask Pronouns"],
            "Interests": ["Art", "Music", "Movies", "Books", "Technology", "Science", "History", "Food", "Programming", "Anime", "Photography", "Travel", "Writing", "Cooking", "Fitness", "Nature", "Gaming", "Philosophy", "Psychology", "Design", "Machine Learning", "Cryptocurrency", "Astronomy", "Mythology", "Languages", "Architecture", "DIY Projects", "Hiking", "Streaming", "Virtual Reality", "Coding Challenges", "Board Games", "Meditation", "Urban Exploration", "Tattoo Art", "Comics", "Robotics", "3D Modeling", "Podcasts"],
            "Gaming Platforms": ["PC", "PlayStation", "Xbox", "Nintendo Switch", "Mobile"],
            "Favorite Vocaloids": ["Hatsune Miku", "Kasane Teto", "Akita Neru", "Kagamine Rin", "Kagamine Len", "Megurine Luka", "Kaito", "Meiko", "Gumi", "Kaai Yuki"],
            "Notifications": ["Announcements"]
        }

        created_count = 0
        updated_count = 0 # Renamed from eped_count
        skipped_other_count = 0 # For non-color roles that exist
        error_count = 0
        existing_roles = {role.name.lower(): role for role in guild.roles} # Cache existing roles for faster lookup

        for category, names in role_categories.items():
            logger.info(f"Processing category: {category}")
            for name in names:
                role_color = color_map.get(name) if category == "Colors" else None
                role_exists = name.lower() in existing_roles

                try:
                    if role_exists:
                        existing_role = existing_roles[name.lower()]
                        # Only edit if it's a color role and needs a color update (or just ensure color is set)
                        if category == "Colors" and role_color is not None:
                             # Check if color needs updating to avoid unnecessary API calls
                             if existing_role.color != role_color:
                                 await existing_role.edit(color=role_color)
                                 logger.info(f"Successfully updated color for existing role: {name}")
                                 updated_count += 1
                             else:
                                 logger.info(f"Role '{name}' already exists with correct color. Skipping update.")
                                 updated_count += 1 # Count as updated/checked even if no change needed
                        else:
                            # Non-color role exists, skip it
                            logger.info(f"Non-color role '{name}' already exists. Skipping.")
                            skipped_other_count += 1
                        continue # Move to next role name

                    # Role does not exist, create it
                    await guild.create_role(
                        name=name,
                        color=role_color or discord.Color.default(), # Use mapped color or default
                        permissions=discord.Permissions.none(),
                        mentionable=False
                    )
                    logger.info(f"Successfully created role: {name}" + (f" with color {role_color}" if role_color else ""))
                    created_count += 1

                except discord.Forbidden:
                    logger.error(f"Forbidden to {'edit' if role_exists else 'create'} role '{name}'. Check bot permissions.")
                    await ctx.send(f"Error: I lack permissions to {'edit' if role_exists else 'create'} the role '{name}'.")
                    error_count += 1
                    # Stop if permission error occurs, as it likely affects subsequent operations
                    await ctx.send(f"Stopping role processing due to permission error on role '{name}'.")
                    return
                except discord.HTTPException as e:
                    logger.error(f"Failed to {'edit' if role_exists else 'create'} role '{name}': {e}")
                    await ctx.send(f"Error {'editing' if role_exists else 'creating'} role '{name}': {e}")
                    error_count += 1
                except Exception as e:
                    logger.exception(f"An unexpected error occurred while processing role '{name}': {e}")
                    await ctx.send(f"An unexpected error occurred for role '{name}'. Check logs.")
                    error_count += 1


        summary_message = f"Role creation/update process complete.\n" \
                          f"Created: {created_count}\n" \
                          f"Updated/Checked Colors: {updated_count}\n" \
                          f"Skipped (Other existing): {skipped_other_count}\n" \
                          f"Errors: {error_count}"
        await ctx.send(summary_message)
        logger.info(summary_message)


async def setup(bot):
    # Ensure the owner ID is loaded correctly before adding the cog
    if not OWNER_USER_ID:
        logger.error("OWNER_USER_ID not found in .env file. RoleCreatorCog will not be loaded.")
        return
    # Check if the bot object has owner_id or owner_ids set, which discord.py uses for is_owner()
    if not bot.owner_id and not bot.owner_ids:
         logger.warning("Bot owner_id or owner_ids not set. The 'is_owner()' check might not function correctly.")
         # Potentially load from OWNER_USER_ID if needed, though discord.py usually handles this
         # bot.owner_id = OWNER_USER_ID # Uncomment if necessary and discord.py doesn't auto-load

    await bot.add_cog(RoleCreatorCog(bot))
    logger.info("RoleCreatorCog loaded successfully.")
