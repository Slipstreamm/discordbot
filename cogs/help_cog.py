import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# Define friendly names for cogs
COG_DISPLAY_NAMES = {
    "AICog": "🤖 AI Chat",
    "AudioCog": "🎵 Audio Player",
    "GamesCog": "🎮 Games",
    "HelpCog": "❓ Help",
    "MultiConversationCog": "🤖 Multi-Conversation AI Chat",
    "MessageCog": "💬 Messages",
    "LevelingCog": "⭐ Leveling System",
    "MarriageCog": "💍 Marriage System",
    "ModerationCog": "🛡️ Moderation",
    "PingCog": "🏓 Ping",
    "RandomCog": "🎲 Random Image (NSFW)",
    "RoleCreatorCog": "✨ Role Management (Owner Only)",
    "RoleSelectorCog": "🎭 Role Selection (Owner Only)",
    "RoleplayCog": "💋 Roleplay",
    "Rule34Cog": "🔞 Rule34 Search (NSFW)",
    "ShellCommandCog": "🖥️ Shell Command",
    "SystemCheckCog": "📊 System Status",
    "WebdriverTorsoCog": "🌐 Webdriver Torso",
    "CommandDebugCog": "🐛 Command Debug (Owner Only)",
    "CommandFixCog": "🐛 Command Fix (Owner Only)",
    "TTSProviderCog": "🗣️ TTS Provider",
    "RandomTimeoutCog": "⏰ Random Timeout",
    "SyncCog": "🔄 Command Sync (Owner Only)",
    # Add other cogs here as needed
}

class HelpSelect(discord.ui.Select):
    def __init__(self, view: 'HelpView', start_index=0, max_options=24):
        self.help_view = view

        # Always include General Overview option
        options = [discord.SelectOption(label="General Overview", description="Go back to the main help page.", value="-1")] # Value -1 for overview page

        # Calculate end index, ensuring we don't go past the end of the cogs list
        end_index = min(start_index + max_options, len(view.cogs))

        # Add cog options for this page of the select menu
        for i in range(start_index, end_index):
            cog = view.cogs[i]
            display_name = COG_DISPLAY_NAMES.get(cog.qualified_name, cog.qualified_name)
            # Truncate description if too long for Discord API limit (100 chars)
            # Use a relative index (i - start_index) as the value to avoid confusion
            # when navigating between pages
            relative_index = i - start_index
            options.append(discord.SelectOption(label=display_name, value=str(relative_index)))

        # Store the range of cogs this select menu covers
        self.start_index = start_index
        self.end_index = end_index

        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_value = int(self.values[0])
        if selected_value == -1: # General Overview selected
            self.help_view.current_page = 0
        else:
            # The value is a relative index (0-based) within the current page of options
            # We need to convert it to an absolute index in the cogs list
            actual_cog_index = selected_value + self.start_index

            # Debug information
            print(f"Selected value: {selected_value}, start_index: {self.start_index}, actual_cog_index: {actual_cog_index}")

            # Make sure the index is valid
            if 0 <= actual_cog_index < len(self.help_view.cogs):
                self.help_view.current_page = actual_cog_index + 1 # +1 because page 0 is overview
            else:
                # If the index is invalid, go to the overview page
                self.help_view.current_page = 0
                await interaction.response.send_message(f"That category is no longer available. Showing overview. (Debug: value={selected_value}, start={self.start_index}, actual={actual_cog_index}, max={len(self.help_view.cogs)})", ephemeral=True)

        # Ensure current_page is within valid range
        if self.help_view.current_page >= len(self.help_view.pages):
            self.help_view.current_page = 0

        self.help_view._update_buttons()
        self.help_view._update_select_menu()

        # Update the placeholder to show the current selection
        if self.help_view.current_page == 0:
            current_option_label = "General Overview"
        else:
            cog_index = self.help_view.current_page - 1
            if 0 <= cog_index < len(self.help_view.cogs):
                current_option_label = COG_DISPLAY_NAMES.get(self.help_view.cogs[cog_index].qualified_name, self.help_view.cogs[cog_index].qualified_name)
            else:
                current_option_label = "Select a category..."
        self.placeholder = current_option_label

        try:
            await interaction.response.edit_message(embed=self.help_view.pages[self.help_view.current_page], view=self.help_view)
        except Exception as e:
            # If we can't edit the message, try to defer or send a new message
            try:
                await interaction.response.defer()
                print(f"Error in help command: {e}")
            except:
                pass


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.current_page = 0  # Current page in the embed pages
        self.current_select_page = 0  # Current page of the select menu
        self.max_select_options = 24  # Maximum number of cog options per select menu (25 total with General Overview)

        # Filter cogs and sort them using the display name mapping
        self.cogs = sorted(
            [cog for _, cog in bot.cogs.items() if cog.get_commands()],
            key=lambda cog: COG_DISPLAY_NAMES.get(cog.qualified_name, cog.qualified_name) # Sort alphabetically by display name
        )

        # Calculate total number of select menu pages needed
        self.total_select_pages = (len(self.cogs) + self.max_select_options - 1) // self.max_select_options

        # Create pages after total_select_pages is defined
        self.pages = self._create_pages()

        # Add components in order: Select, Previous/Next Page, Previous/Next Category
        self._update_select_menu()  # Initialize the select menu with the first page of options
        # Buttons are added via decorators later

        self._update_buttons()  # Initial button state

    def _create_overview_page(self):
        # Create the overview page (page 0)
        embed = discord.Embed(
            title="Help Command",
            description=f"Use the buttons below to navigate through command categories.\nTotal Categories: {len(self.cogs)}\nUse the Categories buttons to navigate between pages of categories.",
            color=discord.Color.blue()
        )

        # Calculate how many cogs are shown in the current select page
        start_index = self.current_select_page * self.max_select_options
        end_index = min(start_index + self.max_select_options, len(self.cogs))
        current_range = f"{start_index + 1}-{end_index}" if len(self.cogs) > self.max_select_options else f"1-{len(self.cogs)}"

        # Add information about which cogs are currently visible
        if len(self.cogs) > self.max_select_options:
            embed.add_field(
                name="Currently Showing",
                value=f"Categories {current_range} of {len(self.cogs)}",
                inline=False
            )

        embed.set_footer(text="Page 0 / {} | Category Page {} / {}".format(len(self.cogs), self.current_select_page + 1, self.total_select_pages))
        return embed

    def _create_pages(self):
        pages = []
        # Page 0: General overview
        pages.append(self._create_overview_page())

        # Subsequent pages: One per cog
        for i, cog in enumerate(self.cogs):
            try:
                cog_name = cog.qualified_name
                # Get the friendly display name, falling back to the original name
                display_name = COG_DISPLAY_NAMES.get(cog_name, cog_name)
                cog_commands = cog.get_commands()
                embed = discord.Embed(
                    title=f"{display_name} Commands", # Use the display name here
                    description=f"Commands available in the {display_name} category:",
                    color=discord.Color.green() # Or assign colors dynamically
                )
                for command in cog_commands:
                    # Skip subcommands for now, just show top-level commands in the cog
                    if isinstance(command, commands.Group):
                         # If it's a group, list its subcommands or just the group name
                         sub_cmds = ", ".join([f"`{sub.name}`" for sub in command.commands])
                         if sub_cmds:
                             embed.add_field(name=f"`{command.name}` (Group)", value=f"Subcommands: {sub_cmds}\n{command.short_doc or 'No description'}", inline=False)
                         else:
                             embed.add_field(name=f"`{command.name}` (Group)", value=f"{command.short_doc or 'No description'}", inline=False)

                    elif command.parent is None: # Only show top-level commands
                        signature = f"{command.name} {command.signature}"
                        embed.add_field(
                            name=f"`{signature.strip()}`",
                            value=command.short_doc or "No description provided.",
                            inline=False
                        )
                embed.set_footer(text=f"Page {i + 1} / {len(self.cogs)} | Category Page {self.current_select_page + 1} / {self.total_select_pages}")
                pages.append(embed)
            except Exception as e:
                # If there's an error creating a page for a cog, log it and continue
                print(f"Error creating help page for cog {i}: {e}")
                # Create a simple error page for this cog
                error_embed = discord.Embed(
                    title=f"Error displaying commands",
                    description=f"There was an error displaying commands for this category.\nPlease try again or contact the bot owner if the issue persists.",
                    color=discord.Color.red()
                )
                error_embed.set_footer(text=f"Page {i + 1} / {len(self.cogs)} | Category Page {self.current_select_page + 1} / {self.total_select_pages}")
                pages.append(error_embed)
        return pages

    def _update_select_menu(self):
        # Remove existing select menu if it exists
        for item in self.children.copy():
            if isinstance(item, HelpSelect):
                self.remove_item(item)

        # Calculate the starting index for this page of the select menu
        start_index = self.current_select_page * self.max_select_options

        # Check if the currently selected cog is in the current select page range
        current_cog_in_view = False
        if self.current_page > 0:  # If a cog is selected (not overview)
            cog_index = self.current_page - 1  # Convert page to cog index
            # Check if this cog is in the current select page range
            if start_index <= cog_index < start_index + self.max_select_options:
                current_cog_in_view = True

        # If the current cog is not in view and we're not on the overview page,
        # adjust the select page to include the current cog
        if not current_cog_in_view and self.current_page > 0:
            cog_index = self.current_page - 1
            self.current_select_page = cog_index // self.max_select_options
            # Recalculate start_index
            start_index = self.current_select_page * self.max_select_options

        # Create and add the new select menu
        self.select_menu = HelpSelect(self, start_index, self.max_select_options)
        self.add_item(self.select_menu)

        # Update the placeholder to show the current selection
        if self.current_page == 0:
            current_option_label = "General Overview"
        else:
            cog_index = self.current_page - 1
            if 0 <= cog_index < len(self.cogs):
                current_option_label = COG_DISPLAY_NAMES.get(self.cogs[cog_index].qualified_name, self.cogs[cog_index].qualified_name)
            else:
                current_option_label = "Select a category..."
        self.select_menu.placeholder = current_option_label

    def _update_buttons(self):
        # Find the buttons by their custom_id
        prev_page_button = None
        next_page_button = None
        prev_category_button = None
        next_category_button = None

        # First check if buttons have been added yet
        if len(self.children) <= 1:  # Only select menu exists
            return  # Buttons will be added by decorators later

        for item in self.children:
            if hasattr(item, 'custom_id'):
                if item.custom_id == 'prev_page':
                    prev_page_button = item
                elif item.custom_id == 'next_page':
                    next_page_button = item
                elif item.custom_id == 'prev_category':
                    prev_category_button = item
                elif item.custom_id == 'next_category':
                    next_category_button = item

        # Update page navigation buttons
        if prev_page_button:
            prev_page_button.disabled = self.current_page == 0
        if next_page_button:
            next_page_button.disabled = self.current_page == len(self.pages) - 1

        # Update category navigation buttons
        if prev_category_button:
            prev_category_button.disabled = self.current_select_page == 0
        if next_category_button:
            next_category_button.disabled = self.current_select_page == self.total_select_pages - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey, row=1, custom_id="prev_page")
    async def previous_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            self._update_select_menu()

            # Ensure current_page is within valid range
            if self.current_page >= len(self.pages):
                self.current_page = 0

            try:
                await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
            except Exception as e:
                try:
                    await interaction.response.defer()
                    print(f"Error in help command previous button: {e}")
                except:
                    pass
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey, row=1, custom_id="next_page")
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_buttons()
            self._update_select_menu()

            # Ensure current_page is within valid range
            if self.current_page >= len(self.pages):
                self.current_page = 0

            try:
                await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
            except Exception as e:
                try:
                    await interaction.response.defer()
                    print(f"Error in help command next button: {e}")
                except:
                    pass
        else:
            await interaction.response.defer()

    @discord.ui.button(label="◀ Categories", style=discord.ButtonStyle.primary, row=2, custom_id="prev_category")
    async def prev_category_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.current_select_page > 0:
            # Store the current page before updating
            old_page = self.current_page

            # Update the select page
            self.current_select_page -= 1

            # If we're on a cog page, check if we need to adjust the current page
            if old_page > 0:
                cog_index = old_page - 1
                start_index = self.current_select_page * self.max_select_options
                end_index = min(start_index + self.max_select_options, len(self.cogs))

                # If the current cog is no longer in the visible range, go to the overview page
                if cog_index < start_index or cog_index >= end_index:
                    self.current_page = 0

            # Update UI elements
            self._update_buttons()
            self._update_select_menu()

            # If on the overview page, recreate it to update the category information
            if self.current_page == 0:
                # Recreate the overview page with updated category info
                self.pages[0] = self._create_overview_page()

            # Ensure current_page is within valid range
            if self.current_page >= len(self.pages):
                self.current_page = 0

            try:
                await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
            except Exception as e:
                try:
                    await interaction.response.defer()
                    print(f"Error in help command prev category button: {e}")
                except:
                    pass
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Categories ▶", style=discord.ButtonStyle.primary, row=2, custom_id="next_category")
    async def next_category_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.current_select_page < self.total_select_pages - 1:
            # Store the current page before updating
            old_page = self.current_page

            # Update the select page
            self.current_select_page += 1

            # If we're on a cog page, check if we need to adjust the current page
            if old_page > 0:
                cog_index = old_page - 1
                start_index = self.current_select_page * self.max_select_options
                end_index = min(start_index + self.max_select_options, len(self.cogs))

                # If the current cog is no longer in the visible range, go to the overview page
                if cog_index < start_index or cog_index >= end_index:
                    self.current_page = 0

            # Update UI elements
            self._update_buttons()
            self._update_select_menu()

            # If on the overview page, recreate it to update the category information
            if self.current_page == 0:
                # Recreate the overview page with updated category info
                self.pages[0] = self._create_overview_page()

            # Ensure current_page is within valid range
            if self.current_page >= len(self.pages):
                self.current_page = 0

            try:
                await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
            except Exception as e:
                try:
                    await interaction.response.defer()
                    print(f"Error in help command next category button: {e}")
                except:
                    pass
        else:
            await interaction.response.defer()


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Remove the default help command before adding the custom one
        original_help_command = bot.get_command('help')
        if original_help_command:
            bot.remove_command(original_help_command.name)

    @commands.hybrid_command(name="help", description="Shows this help message.")
    async def help_command(self, ctx: commands.Context, command_name: str = None):
        """Displays an interactive help message with command categories or details about a specific command."""
        try:
            if command_name:
                command = self.bot.get_command(command_name)
                if command:
                    embed = discord.Embed(
                        title=f"Help for `{command.name}`",
                        description=command.help or "No detailed description provided.",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Usage", value=f"`{command.name} {command.signature}`", inline=False)
                    if isinstance(command, commands.Group):
                        subcommands = "\n".join([f"`{sub.name}`: {sub.short_doc or 'No description'}" for sub in command.commands])
                        embed.add_field(name="Subcommands", value=subcommands or "None", inline=False)
                    await ctx.send(embed=embed, ephemeral=True)
                else:
                    await ctx.send(f"Command `{command_name}` not found.", ephemeral=True)
            else:
                view = HelpView(self.bot)
                await ctx.send(embed=view.pages[0], view=view, ephemeral=True) # Send ephemeral so only user sees it
        except Exception as e:
            # If there's an error, send a simple error message
            print(f"Error in help command: {e}")
            await ctx.send(f"An error occurred while displaying the help command. Please try again or contact the bot owner if the issue persists.", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')


async def setup(bot: commands.Bot):
    # Ensure the cog is added only after the bot is ready enough to have cogs attribute
    # Or handle potential race conditions if setup is called very early
    await bot.add_cog(HelpCog(bot))
