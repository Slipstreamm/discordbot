import discord
from discord.ext import commands
from discord import app_commands
import asyncio

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.current_page = 0
        self.cogs = [cog for cog_name, cog in bot.cogs.items() if cog.get_commands()] # Get cogs with commands
        self.pages = self._create_pages()
        self._update_buttons()

    def _create_pages(self):
        pages = []
        # Page 0: General overview
        embed = discord.Embed(
            title="Help Command",
            description=f"Use the buttons below to navigate through command categories.\nTotal Cogs: {len(self.cogs)}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Page 0 / {}".format(len(self.cogs)))
        pages.append(embed)

        # Subsequent pages: One per cog
        for i, cog in enumerate(self.cogs):
            cog_name = cog.qualified_name
            cog_commands = cog.get_commands()
            embed = discord.Embed(
                title=f"{cog_name} Commands",
                description=f"Commands available in the {cog_name} category:",
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
        self.children[0].disabled = self.current_page == 0
        # Disable next button if on the last page
        self.children[1].disabled = self.current_page == len(self.pages) - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
             # Optionally send an ephemeral message if they try to go before the first page
            await interaction.response.defer()


    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            # Optionally send an ephemeral message if they try to go past the last page
            await interaction.response.defer()


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Remove the default help command before adding the custom one
        original_help_command = bot.get_command('help')
        if original_help_command:
            bot.remove_command(original_help_command.name)

    @commands.hybrid_command(name="help", description="Shows this help message.")
    async def help_command(self, ctx: commands.Context):
        """Displays an interactive help message with command categories."""
        view = HelpView(self.bot)
        await ctx.send(embed=view.pages[0], view=view, ephemeral=True) # Send ephemeral so only user sees it

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')


async def setup(bot: commands.Bot):
    # Ensure the cog is added only after the bot is ready enough to have cogs attribute
    # Or handle potential race conditions if setup is called very early
    await bot.add_cog(HelpCog(bot))
