import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# Define friendly names for cogs
COG_DISPLAY_NAMES = {
    "AudioCog": "🎵 Audio Player",
    "HelpCog": "❓ Help",
    "PingCog": "🏓 Ping",
    "RandomCog": "🎲 Random Image (NSFW)",
    "RoleCreatorCog": "✨ Role Management (Owner Only)",
    "RoleSelectorCog": "🎭 Role Selection (Owner Only)",
    "Rule34Cog": "🔞 Rule34 Search (NSFW)",
    "SystemCheckCog": "📊 System Status",
    # Add other cogs here as needed
}

class HelpSelect(discord.ui.Select):
    def __init__(self, view: 'HelpView'):
        self.help_view = view
        options = [discord.SelectOption(label="General Overview", description="Go back to the main help page.", value="-1")] # Value -1 for overview page
        for i, cog in enumerate(view.cogs):
            display_name = COG_DISPLAY_NAMES.get(cog.qualified_name, cog.qualified_name)
            # Truncate description if too long for Discord API limit (100 chars)
            description = f"Commands for {display_name}"[:100]
            options.append(discord.SelectOption(label=display_name, description=description, value=str(i)))

        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_value = int(self.values[0])
        if selected_value == -1: # General Overview selected
            self.help_view.current_page = 0
        else:
            self.help_view.current_page = selected_value + 1 # +1 because page 0 is overview

        self.help_view._update_buttons()
        # Update the placeholder to show the current selection
        current_option_label = "General Overview" if self.help_view.current_page == 0 else COG_DISPLAY_NAMES.get(self.help_view.cogs[self.help_view.current_page - 1].qualified_name)
        self.placeholder = current_option_label
        await interaction.response.edit_message(embed=self.help_view.pages[self.help_view.current_page], view=self.help_view)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.current_page = 0
        # Filter cogs and sort them using the display name mapping
        self.cogs = sorted(
            [cog for cog_name, cog in bot.cogs.items() if cog.get_commands()],
            key=lambda cog: COG_DISPLAY_NAMES.get(cog.qualified_name, cog.qualified_name) # Sort alphabetically by display name
        )
        self.pages = self._create_pages()

        # Add components in order: Select, Previous, Next
        self.select_menu = HelpSelect(self)
        self.add_item(self.select_menu)
        # Buttons are added via decorators later, ensure they appear after select if desired layout matters

        self._update_buttons() # Initial button state

    def _create_pages(self):
        pages = []
        # Page 0: General overview
        embed = discord.Embed(
            title="Help Command",
            description=f"Use the buttons below to navigate through command categories.\nTotal Categories: {len(self.cogs)}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Page 0 / {}".format(len(self.cogs)))
        pages.append(embed)

        # Subsequent pages: One per cog
        for i, cog in enumerate(self.cogs):
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
            embed.set_footer(text=f"Page {i + 1} / {len(self.cogs)}")
            pages.append(embed)
        return pages

    def _update_buttons(self):
        # Disable previous button if on the first page
        # Assuming previous button is the second item added (index 1 after select menu)
        prev_button = self.children[1] # Adjust index if component order changes
        prev_button.disabled = self.current_page == 0
        # Disable next button if on the last page
        # Assuming next button is the third item added (index 2 after select menu)
        next_button = self.children[2] # Adjust index if component order changes
        next_button.disabled = self.current_page == len(self.pages) - 1

        # Update select menu placeholder
        current_option_label = "General Overview"
        if self.current_page > 0 and self.current_page <= len(self.cogs):
             current_option_label = COG_DISPLAY_NAMES.get(self.cogs[self.current_page - 1].qualified_name, self.cogs[self.current_page - 1].qualified_name)
        self.select_menu.placeholder = current_option_label

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey, row=1) # Specify row if needed
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons() # This will now also update the select placeholder
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey, row=1) # Specify row if needed
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_buttons() # This will now also update the select placeholder
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
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

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')


async def setup(bot: commands.Bot):
    # Ensure the cog is added only after the bot is ready enough to have cogs attribute
    # Or handle potential race conditions if setup is called very early
    await bot.add_cog(HelpCog(bot))
