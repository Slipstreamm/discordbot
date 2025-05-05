import discord
from discord.ext import commands
from discord.ui import View, Select, select
import json
import os
from typing import List, Dict, Optional, Set, Tuple
import asyncio # Added for sleep

# Role structure expected (based on role_creator_cog)
# Using original category names from role_creator_cog as keys
EXPECTED_ROLES: Dict[str, List[str]] = {
    "Colors": ["Red", "Blue", "Green", "Yellow", "Purple", "Orange", "Pink", "Black", "White"],
    "Regions": ["NA East", "NA West", "EU", "Asia", "Oceania", "South America"],
    "Pronouns": ["He/Him", "She/Her", "They/Them", "Ask Pronouns"],
    "Interests": ["Art", "Music", "Movies", "Books", "Technology", "Science", "History", "Food", "Programming", "Anime", "Photography", "Travel", "Writing", "Cooking", "Fitness", "Nature", "Gaming", "Philosophy", "Psychology", "Design", "Machine Learning", "Cryptocurrency", "Astronomy", "Mythology", "Languages", "Architecture", "DIY Projects", "Hiking", "Streaming", "Virtual Reality", "Coding Challenges", "Board Games", "Meditation", "Urban Exploration", "Tattoo Art", "Comics", "Robotics", "3D Modeling", "Podcasts"],
    "Gaming Platforms": ["PC", "PlayStation", "Xbox", "Nintendo Switch", "Mobile"],
    "Favorite Vocaloids": ["Hatsune Miku", "Kasane Teto", "Akita Neru", "Kagamine Rin", "Kagamine Len", "Megurine Luka", "Kaito", "Meiko", "Gumi", "Kaai Yuki", "Yowane Haku", "Adachi Rei"],
    "Notifications": ["Announcements"]
}

# Mapping creator categories to selector categories (for single-choice logic etc.)
# and providing display names/embed titles
CATEGORY_DETAILS = {
    "Colors": {"selector_category": "color", "title": "🎨 Color Roles", "description": "Choose your favorite color role.", "color": discord.Color.green(), "max_values": 1},
    "Regions": {"selector_category": "region", "title": "🌍 Region Roles", "description": "Select your region.", "color": discord.Color.orange(), "max_values": 1},
    "Pronouns": {"selector_category": "name", "title": "📛 Pronoun Roles", "description": "Select your pronoun roles.", "color": discord.Color.blue(), "max_values": 4}, # Allow multiple pronouns
    "Interests": {"selector_category": "interests", "title": "💡 Interests", "description": "Select your interests.", "color": discord.Color.purple(), "max_values": 16}, # Allow multiple (Increased max_values again)
    "Gaming Platforms": {"selector_category": "gaming", "title": "🎮 Gaming Platforms", "description": "Select your gaming platforms.", "color": discord.Color.dark_grey(), "max_values": 5}, # Allow multiple
    "Favorite Vocaloids": {"selector_category": "vocaloid", "title": "🎤 Favorite Vocaloids", "description": "Select your favorite Vocaloids.", "color": discord.Color.teal(), "max_values": 10}, # Allow multiple
    "Notifications": {"selector_category": "notifications", "title": "🔔 Notifications", "description": "Opt-in for notifications.", "color": discord.Color.light_grey(), "max_values": 1} # Allow multiple (or single if only one role)
}

# --- Persistent View Definition ---
class RoleSelectorView(View):
    def __init__(self, category_roles: List[discord.Role], selector_category_name: str, max_values: int = 1):
        super().__init__(timeout=None)
        self.category_role_ids: Set[int] = {role.id for role in category_roles}
        self.selector_category_name = selector_category_name
        self.custom_id = f"persistent_role_select_view_{selector_category_name}"
        self.select_chunk_map: Dict[str, Set[int]] = {} # Map custom_id to role IDs in that chunk

        # Split roles into chunks of 25 for multiple select menus if needed
        self.role_chunks = [category_roles[i:i + 25] for i in range(0, len(category_roles), 25)]
        num_chunks = len(self.role_chunks)

        # Ensure total max_values doesn't exceed the total number of roles
        total_max_values = min(max_values, len(category_roles))
        # For multi-select, min_values is typically 0 unless explicitly required otherwise
        # For single-select categories, min_values should be 0 to allow deselecting by choosing nothing
        # Note: Discord UI might enforce min_values=1 if max_values=1. Let's keep min_values=0 for flexibility.
        actual_min_values = 0

        for i, chunk in enumerate(self.role_chunks):
            options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in chunk]
            chunk_role_ids = {role.id for role in chunk}
            if not options:
                continue

            # Determine max_values for this specific select menu
            # If multiple selects, allow selecting up to total_max_values across all of them.
            # Each individual select menu still has a max_values limit of 25.
            chunk_max_values = min(total_max_values, len(options)) # Allow selecting up to the total allowed, but capped by options in this chunk

            placeholder = f"Select {selector_category_name} role(s)..."
            if num_chunks > 1:
                placeholder = f"Select {selector_category_name} role(s) ({i+1}/{num_chunks})..."

            # Custom ID needs to be unique per select menu but linkable to the category
            select_custom_id = f"role_select_dropdown_{selector_category_name}_{i}"
            self.select_chunk_map[select_custom_id] = chunk_role_ids # Store mapping

            select_component = Select(
                placeholder=placeholder,
                min_values=actual_min_values, # Allow selecting zero from any individual dropdown
                max_values=chunk_max_values, # Max selectable from *this* dropdown
                options=options,
                custom_id=select_custom_id
            )
            select_component.callback = self.select_callback
            self.add_item(select_component)

    async def select_callback(self, interaction: discord.Interaction):
        # Callback logic remains largely the same, but needs to handle potentially
        # Callback logic needs to handle selections from one dropdown without
        # affecting selections made via other dropdowns in the same view/category.

        await interaction.response.defer(ephemeral=True, thinking=True)

        member = interaction.user
        guild = interaction.guild
        if not isinstance(member, discord.Member) or not guild:
            await interaction.followup.send("This interaction must be used within a server.", ephemeral=True)
            return

        # --- Identify interacted dropdown and its roles ---
        interacted_custom_id = interaction.data['custom_id']
        # Find the corresponding chunk role IDs using the stored map
        interacted_chunk_role_ids: Set[int] = set()
        if hasattr(self, 'select_chunk_map') and interacted_custom_id in self.select_chunk_map:
             interacted_chunk_role_ids = self.select_chunk_map[interacted_custom_id]
        else:
             # Fallback or error handling if map isn't populated (shouldn't happen in normal flow)
             print(f"Warning: Could not find chunk map for custom_id {interacted_custom_id} in view {self.custom_id}")
             # Attempt to find the component and its options as a less reliable fallback
             for component in self.children:
                 if isinstance(component, Select) and component.custom_id == interacted_custom_id:
                     interacted_chunk_role_ids = {int(opt.value) for opt in component.options}
                     break
             if not interacted_chunk_role_ids:
                 await interaction.followup.send("An internal error occurred trying to identify the roles for this dropdown.", ephemeral=True)
                 return


        selected_values = interaction.data.get('values', [])
        current_selector_category = self.selector_category_name

        # --- Calculate changes based on interaction ---
        selected_role_ids_from_interaction = {int(value) for value in selected_values}

        # Get all roles the member currently has within this entire category
        member_category_role_ids = {role.id for role in member.roles if role.id in self.category_role_ids}

        # Roles to add are those selected in this interaction that the member doesn't already have
        roles_to_add_ids = selected_role_ids_from_interaction - member_category_role_ids

        # Roles to remove are those from *this specific dropdown's chunk* that the member *had*, but are *no longer selected* in this interaction.
        member_roles_in_interacted_chunk = member_category_role_ids.intersection(interacted_chunk_role_ids)
        roles_to_remove_ids = member_roles_in_interacted_chunk - selected_role_ids_from_interaction

        # --- Single-choice category handling ---
        is_single_choice = current_selector_category in ['color', 'region', 'notifications'] # Add more if needed
        if is_single_choice and roles_to_add_ids:
            # Ensure only one role is being added
            if len(roles_to_add_ids) > 1:
                 await interaction.followup.send(f"Error: Cannot select multiple roles for the '{current_selector_category}' category.", ephemeral=True)
                 return # Stop processing
            role_to_add_id = list(roles_to_add_ids)[0]

            # Identify all other roles in the category the member currently has (excluding the one being added)
            other_member_roles_in_category = member_category_role_ids - {role_to_add_id}
            # Add these other roles to the removal set
            roles_to_remove_ids.update(other_member_roles_in_category)
            # Ensure only the single selected role is in the add set
            roles_to_add_ids = {role_to_add_id}

        # --- Convert IDs to Role objects ---
        roles_to_add = {guild.get_role(role_id) for role_id in roles_to_add_ids if guild.get_role(role_id)}
        roles_to_remove = {guild.get_role(role_id) for role_id in roles_to_remove_ids if guild.get_role(role_id)}

        # --- Apply changes and provide feedback ---
        added_names = []
        removed_names = []
        error_messages = []

        try:
            # Perform removals first
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Deselected/changed via {current_selector_category} role selector ({interacted_custom_id})")
                removed_names = [r.name for r in roles_to_remove if r]
            # Then perform additions
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason=f"Selected via {current_selector_category} role selector ({interacted_custom_id})")
                added_names = [r.name for r in roles_to_add if r]

            # Construct feedback message
            if added_names or removed_names:
                feedback = "Your roles have been updated!"
                if added_names:
                    feedback += f"\n+ Added: {', '.join(added_names)}"
                if removed_names:
                    feedback += f"\n- Removed: {', '.join(removed_names)}"
            elif selected_values: # Roles were selected, but no changes needed (already had them)
                 feedback = f"No changes needed for the roles selected in this dropdown."
            else: # No roles selected in this interaction
                 if member_roles_in_interacted_chunk: # Had roles from this chunk, now removed
                     feedback = f"Roles deselected from this dropdown."
                 else: # Had no roles from this chunk, selected none
                     feedback = f"No roles selected in this dropdown."


            await interaction.followup.send(feedback, ephemeral=True)

        except discord.Forbidden:
            error_messages.append("I don't have permission to manage roles.")
        except discord.HTTPException as e:
            error_messages.append(f"An error occurred while updating roles: {e}")
        except Exception as e:
             error_messages.append(f"An unexpected error occurred: {e}")
             print(f"Error in role selector callback: {e}")

        if error_messages:
            await interaction.followup.send("\n".join(error_messages), ephemeral=True)

class RoleSelectorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.register_persistent_views())

    def _get_guild_roles_by_name(self, guild: discord.Guild) -> Dict[str, discord.Role]:
        return {role.name.lower(): role for role in guild.roles}

    def _get_dynamic_roles_per_category(self, guild: discord.Guild) -> Dict[str, List[discord.Role]]:
        """Dynamically fetches roles and groups them by the original creator category."""
        guild_roles_map = self._get_guild_roles_by_name(guild)
        categorized_roles: Dict[str, List[discord.Role]] = {cat: [] for cat in EXPECTED_ROLES.keys()}
        missing_roles = []

        for creator_category, role_names in EXPECTED_ROLES.items():
            for role_name in role_names:
                role = guild_roles_map.get(role_name.lower())
                if role:
                    categorized_roles[creator_category].append(role)
                else:
                    missing_roles.append(f"'{role_name}' (Category: {creator_category})")

        if missing_roles:
            print(f"Warning: Roles not found in guild '{guild.name}' ({guild.id}): {', '.join(missing_roles)}")

        # Sort roles within each category alphabetically by name for consistent order
        for category in categorized_roles:
            categorized_roles[category].sort(key=lambda r: r.name)

        return categorized_roles

    async def register_persistent_views(self):
        """Registers persistent views dynamically for each category."""
        await self.bot.wait_until_ready()
        print("RoleSelectorCog: Registering persistent views...")
        registered_count = 0
        guild_count = 0
        for guild in self.bot.guilds:
            guild_count += 1
            print(f"Processing guild for view registration: {guild.name} ({guild.id})")
            roles_by_creator_category = self._get_dynamic_roles_per_category(guild)

            for creator_category, role_list in roles_by_creator_category.items():
                if role_list and creator_category in CATEGORY_DETAILS:
                    details = CATEGORY_DETAILS[creator_category]
                    selector_category = details["selector_category"]
                    max_values = details["max_values"]
                    try:
                        # Register a view for this specific category
                        self.bot.add_view(RoleSelectorView(role_list, selector_category, max_values=max_values))
                        registered_count += 1
                    except Exception as e:
                        print(f"  - Error registering view for '{creator_category}' in guild {guild.id}: {e}")
                elif not role_list and creator_category in CATEGORY_DETAILS:
                    print(f"  - No roles found for category '{creator_category}' in guild {guild.id}, skipping view registration.")
                elif creator_category not in CATEGORY_DETAILS:
                     print(f"  - Warning: Category '{creator_category}' found in EXPECTED_ROLES but not in CATEGORY_DETAILS. Cannot register view.")

        print(f"RoleSelectorCog: Finished registering {registered_count} persistent views across {guild_count} guild(s).")

    @commands.command(name="create_role_embeds")
    @commands.is_owner()
    async def create_role_embeds(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Creates embeds with persistent dropdowns for each role category. (Owner Only)"""
        target_channel = channel or ctx.channel
        guild = ctx.guild
        if not guild:
            await ctx.send("This command can only be used in a server.")
            return

        initial_message = await ctx.send(f"Fetching roles and creating embeds in {target_channel.mention}...")

        roles_by_creator_category = self._get_dynamic_roles_per_category(guild)

        if not any(roles_by_creator_category.values()):
             await initial_message.edit(content="No roles matching the expected names were found in this server. Please run the `create_roles` command first.")
             return

        sent_messages = 0
        # --- Create Embeds and attach Persistent Views for each category ---
        for creator_category, role_list in roles_by_creator_category.items():
            if role_list and creator_category in CATEGORY_DETAILS:
                details = CATEGORY_DETAILS[creator_category]
                selector_category = details["selector_category"]
                max_values = details["max_values"]

                embed = discord.Embed(
                    title=details["title"],
                    description=details["description"],
                    color=details["color"]
                )
                # Create a new view instance for sending
                view = RoleSelectorView(role_list, selector_category, max_values=max_values)
                try:
                    await target_channel.send(embed=embed, view=view)
                    sent_messages += 1
                except discord.Forbidden:
                    await ctx.send(f"Error: Missing permissions to send messages in {target_channel.mention}.")
                    await initial_message.delete() # Clean up initial message
                    return
                except discord.HTTPException as e:
                    await ctx.send(f"Error sending embed for '{creator_category}': {e}")
            elif not role_list and creator_category in CATEGORY_DETAILS:
                print(f"Skipping embed for empty category '{creator_category}' in guild {guild.id}")

        if sent_messages > 0:
            await initial_message.edit(content=f"Created {sent_messages} role selection embed(s) in {target_channel.mention} successfully!")
        else:
            await initial_message.edit(content=f"No roles found for any category to create embeds in {target_channel.mention}.")

    @commands.command(name="update_role_selectors")
    @commands.is_owner()
    async def update_role_selectors(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Updates existing role selector messages in a channel with the current roles. (Owner Only)"""
        target_channel = channel or ctx.channel
        guild = ctx.guild
        if not guild:
            await ctx.send("This command must be used within a server.")
            return

        await ctx.send(f"Starting update process for role selectors in {target_channel.mention}...")

        roles_by_creator_category = self._get_dynamic_roles_per_category(guild)
        updated_messages = 0
        checked_messages = 0
        errors = 0

        try:
            async for message in target_channel.history(limit=200): # Check recent messages
                checked_messages += 1
                if message.author == self.bot.user and message.embeds and message.components:
                    # Check if the message has a view with a select menu matching our pattern
                    view_component = message.components[0] # Assuming the view is the first component row
                    if not isinstance(view_component, discord.ActionRow) or not view_component.children:
                        continue

                    first_item = view_component.children[0]
                    if isinstance(first_item, discord.ui.Select) and first_item.custom_id and first_item.custom_id.startswith("role_select_dropdown_"):
                        selector_category_name = first_item.custom_id.split("role_select_dropdown_")[1]

                        # Find the original creator category based on the selector category name
                        creator_category = None
                        for cat, details in CATEGORY_DETAILS.items():
                            if details["selector_category"] == selector_category_name:
                                creator_category = cat
                                break

                        if creator_category and creator_category in roles_by_creator_category:
                            current_roles = roles_by_creator_category[creator_category]
                            if not current_roles:
                                print(f"Skipping update for {selector_category_name} in message {message.id} - no roles found for this category anymore.")
                                continue # Skip if no roles exist for this category now

                            details = CATEGORY_DETAILS[creator_category]
                            max_values = details["max_values"]

                            # Create a new view with the updated roles
                            new_view = RoleSelectorView(current_roles, selector_category_name, max_values=max_values)

                            # Check if the options or max_values actually changed to avoid unnecessary edits
                            select_in_old_message = first_item
                            select_in_new_view = new_view.children[0] if new_view.children and isinstance(new_view.children[0], discord.ui.Select) else None

                            if select_in_new_view:
                                old_options = {(opt.label, str(opt.value)) for opt in select_in_old_message.options}
                                new_options = {(opt.label, str(opt.value)) for opt in select_in_new_view.options}
                                old_max_values = select_in_old_message.max_values
                                new_max_values = select_in_new_view.max_values

                                if old_options != new_options or old_max_values != new_max_values:
                                    try:
                                        await message.edit(view=new_view)
                                        print(f"Updated role selector for '{selector_category_name}' in message {message.id} (Options changed: {old_options != new_options}, Max values changed: {old_max_values != new_max_values})")
                                        updated_messages += 1
                                    except discord.Forbidden:
                                        print(f"Error: Missing permissions to edit message {message.id} in {target_channel.name}")
                                        errors += 1
                                    except discord.HTTPException as e:
                                        print(f"Error: Failed to edit message {message.id}: {e}")
                                        errors += 1
                                    except Exception as e:
                                        print(f"Unexpected error editing message {message.id}: {e}")
                                        errors += 1
                                else:
                                    print(f"Skipping update for {selector_category_name} in message {message.id} - options and max_values unchanged.")
                            else:
                                print(f"Error: Could not find Select component in the newly generated view for category '{selector_category_name}'. Skipping message {message.id}.")
                        # else: # Debugging if needed
                        #     print(f"Message {message.id} has select menu '{selector_category_name}' but no matching category found in current config.")
                    # else: # Debugging if needed
                    #     print(f"Message {message.id} from bot has components, but first item is not a recognized select menu.")
                # else: # Debugging if needed
                #     if message.author == self.bot.user:
                #         print(f"Message {message.id} from bot skipped (Embeds: {bool(message.embeds)}, Components: {bool(message.components)})")


        except discord.Forbidden:
            await ctx.send(f"Error: I don't have permissions to read message history in {target_channel.mention}.")
            return
        except Exception as e:
            await ctx.send(f"An unexpected error occurred during the update process: {e}")
            print(f"Unexpected error in update_role_selectors: {e}")
            return

        await ctx.send(f"Role selector update process finished for {target_channel.mention}.\n"
                       f"Checked: {checked_messages} messages.\n"
                       f"Updated: {updated_messages} selectors.\n"
                       f"Errors: {errors}")

    @commands.command(name="recreate_role_embeds")
    @commands.is_owner()
    async def recreate_role_embeds(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Deletes existing role selectors in a channel and creates new ones. (Owner Only)"""
        target_channel = channel or ctx.channel
        guild = ctx.guild
        if not guild:
            await ctx.send("This command must be used within a server.")
            return

        initial_status_msg = await ctx.send(f"Starting recreation process for role selectors in {target_channel.mention}...")

        # --- Step 1: Find and Delete Existing Selectors ---
        deleted_messages = 0
        checked_messages = 0
        deletion_errors = 0
        messages_to_delete = []

        try:
            await initial_status_msg.edit(content=f"Searching for existing role selectors in {target_channel.mention} (checking last 500 messages)...")
            async for message in target_channel.history(limit=500): # Check a reasonable number of messages
                checked_messages += 1
                # --- MODIFIED: Delete any message sent by the bot ---
                if message.author == self.bot.user:
                    messages_to_delete.append(message)
                # --- END MODIFICATION ---

            if messages_to_delete:
                await initial_status_msg.edit(content=f"Found {len(messages_to_delete)} messages from the bot. Deleting...")
                # Delete messages one by one to handle potential rate limits and errors better
                for msg in messages_to_delete:
                    try:
                        await msg.delete()
                        deleted_messages += 1
                        await asyncio.sleep(1) # Add a small delay to avoid rate limits
                    except discord.Forbidden:
                        print(f"Error: Missing permissions to delete message {msg.id} in {target_channel.name}")
                        deletion_errors += 1
                    except discord.NotFound:
                        print(f"Warning: Message {msg.id} not found (already deleted?).")
                        # Don't count as an error, but maybe decrement deleted_messages if needed?
                    except discord.HTTPException as e:
                        print(f"Error: Failed to delete message {msg.id}: {e}")
                        deletion_errors += 1
                    except Exception as e:
                        print(f"Unexpected error deleting message {msg.id}: {e}")
                        deletion_errors += 1
                await initial_status_msg.edit(content=f"Deleted {deleted_messages} messages. Errors during deletion: {deletion_errors}.")
            else:
                await initial_status_msg.edit(content="No existing role selector messages found to delete.")

            await asyncio.sleep(2) # Brief pause before creating new ones

        except discord.Forbidden:
            await initial_status_msg.edit(content=f"Error: I don't have permissions to read message history or delete messages in {target_channel.mention}.")
            return
        except Exception as e:
            await initial_status_msg.edit(content=f"An unexpected error occurred during deletion: {e}")
            print(f"Unexpected error in recreate_role_embeds (deletion phase): {e}")
            return

        # --- Step 2: Create New Embeds (similar to create_role_embeds) ---
        await initial_status_msg.edit(content=f"Fetching roles and creating new embeds in {target_channel.mention}...")

        roles_by_creator_category = self._get_dynamic_roles_per_category(guild)

        if not any(roles_by_creator_category.values()):
             await initial_status_msg.edit(content="No roles matching the expected names were found in this server. Cannot create new embeds. Please run the `create_roles` command first.")
             return

        sent_messages = 0
        creation_errors = 0
        for creator_category, role_list in roles_by_creator_category.items():
            if role_list and creator_category in CATEGORY_DETAILS:
                details = CATEGORY_DETAILS[creator_category]
                selector_category = details["selector_category"]
                max_values = details["max_values"]

                embed = discord.Embed(
                    title=details["title"],
                    description=details["description"],
                    color=details["color"]
                )
                view = RoleSelectorView(role_list, selector_category, max_values=max_values)
                try:
                    await target_channel.send(embed=embed, view=view)
                    sent_messages += 1
                    await asyncio.sleep(0.5) # Small delay between sends
                except discord.Forbidden:
                    await ctx.send(f"Error: Missing permissions to send messages in {target_channel.mention}. Aborting creation.")
                    creation_errors += 1
                    break # Stop trying if permissions are missing
                except discord.HTTPException as e:
                    await ctx.send(f"Error sending embed for '{creator_category}': {e}")
                    creation_errors += 1
                except Exception as e:
                    print(f"Unexpected error sending embed for '{creator_category}': {e}")
                    creation_errors += 1

            elif not role_list and creator_category in CATEGORY_DETAILS:
                print(f"Skipping new embed for empty category '{creator_category}' in guild {guild.id}")

        final_message = f"Role selector recreation process finished for {target_channel.mention}.\n" \
                        f"Deleted: {deleted_messages} (Errors: {deletion_errors})\n" \
                        f"Created: {sent_messages} (Errors: {creation_errors})"
        await initial_status_msg.edit(content=final_message)


async def setup(bot):
    await bot.add_cog(RoleSelectorCog(bot))
    print("RoleSelectorCog loaded. Persistent views will be registered once the bot is ready.")
