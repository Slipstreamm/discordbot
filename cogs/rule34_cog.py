import os
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
import random
import aiohttp
import time
import json
import typing # Need this for Optional

# Cache file path (consider making this configurable or relative to bot root)
CACHE_FILE = "rule34_cache.json"

class Rule34Cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache_data = self._load_cache()

    def _load_cache(self):
        """Loads the Rule34 cache from a JSON file."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Failed to load Rule34 cache file ({CACHE_FILE}): {e}")
        return {}

    def _save_cache(self):
        """Saves the Rule34 cache to a JSON file."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self.cache_data, f, indent=4)
        except Exception as e:
            print(f"Failed to save Rule34 cache file ({CACHE_FILE}): {e}")

    # Updated _rule34_logic
    async def _rule34_logic(self, interaction_or_ctx, tags: str, hidden: bool = False) -> typing.Union[str, tuple]:
        """Core logic for the rule34 command. 
        Returns either:
        - Error message string, or
        - Tuple of (random_result_url, all_results) on success"""
        base_url = "https://api.rule34.xxx/index.php"
        all_results = []
        current_pid = 0

        # NSFW Check
        is_nsfw_channel = False
        channel = interaction_or_ctx.channel
        if isinstance(channel, discord.TextChannel) and channel.is_nsfw():
            is_nsfw_channel = True
        elif isinstance(channel, discord.DMChannel):
            is_nsfw_channel = True

        # Allow if 'rating:safe' is explicitly included in tags, regardless of channel type
        allow_in_non_nsfw = 'rating:safe' in tags.lower()

        if not is_nsfw_channel and not allow_in_non_nsfw:
            # Return error message, ephemeral handled by caller
            return 'This command can only be used in age-restricted (NSFW) channels, DMs, or with the `rating:safe` tag.'

        # Defer or send loading message
        loading_msg = None
        is_interaction = not isinstance(interaction_or_ctx, commands.Context)
        if is_interaction:
            # Check if already deferred or responded
            if not interaction_or_ctx.response.is_done():
                 # Defer ephemerally based on hidden flag
                 await interaction_or_ctx.response.defer(ephemeral=hidden)
        else: # Prefix command
            loading_msg = await interaction_or_ctx.reply("Fetching data, please wait...")

        # Check cache for the given tags
        cache_key = tags.lower().strip() # Normalize tags for cache key
        if cache_key in self.cache_data:
            cached_entry = self.cache_data[cache_key]
            cache_timestamp = cached_entry.get("timestamp", 0)
            # Cache valid for 24 hours
            if time.time() - cache_timestamp < 86400:
                all_results = cached_entry.get("results", [])
                if all_results:
                    random_result = random.choice(all_results)
                    content = f"{random_result['file_url']}"
                    # Always return the data. The caller handles sending/editing.
                    return (content, all_results) # Success, return both random and all results

        # If no valid cache or cache is outdated, fetch from API
        all_results = [] # Reset results if cache was invalid/outdated
        async with aiohttp.ClientSession() as session:
            try:
                while True:
                    params = {
                        "page": "dapi", "s": "post", "q": "index",
                        "limit": 1000, "pid": current_pid, "tags": tags, "json": 1
                    }
                    async with session.get(base_url, params=params) as response:
                        if response.status == 200:
                            try:
                                data = await response.json()
                            except aiohttp.ContentTypeError:
                                print(f"Rule34 API returned non-JSON response for tags: {tags}, pid: {current_pid}")
                                data = None # Treat as no data

                            if not data or (isinstance(data, list) and len(data) == 0):
                                break  # No more results or empty response
                            if isinstance(data, list):
                                all_results.extend(data)
                            else:
                                print(f"Unexpected API response format (not list): {data}")
                                break # Stop processing if format is wrong
                            current_pid += 1
                        else:
                            # Return error message, ephemeral handled by caller
                            return f"Failed to fetch data. HTTP Status: {response.status}"

                # Save results to cache if new results were fetched
                if all_results: # Only save if we actually got results
                    self.cache_data[cache_key] = { # Use normalized key
                        "timestamp": int(time.time()),
                        "results": all_results
                    }
                    self._save_cache()

                # Handle results
                if not all_results:
                    # Return error message, ephemeral handled by caller
                    return "No results found for the given tags."
                else:
                    random_result = random.choice(all_results)
                    result_content = f"{random_result['file_url']}"
                    # Always return the data. The caller handles sending/editing.
                    return (result_content, all_results) # Success, return both random and all results

            except Exception as e:
                error_msg = f"An error occurred: {e}"
                print(f"Error in rule34 logic: {e}") # Log the error
                # Return error message, ephemeral handled by caller
                return error_msg

    class Rule34Buttons(View):
        def __init__(self, cog, tags: str, all_results: list, hidden: bool = False):
            super().__init__(timeout=60)
            self.cog = cog
            self.tags = tags
            self.all_results = all_results
            self.hidden = hidden
            self.current_index = 0

        @discord.ui.button(label="New Random", style=discord.ButtonStyle.primary)
        async def new_random(self, interaction: discord.Interaction, button: Button):
            random_result = random.choice(self.all_results)
            content = f"{random_result['file_url']}"
            await interaction.response.edit_message(content=content, view=self)

        @discord.ui.button(label="Random In New Message", style=discord.ButtonStyle.success)
        async def new_message(self, interaction: discord.Interaction, button: Button):
            random_result = random.choice(self.all_results)
            content = f"{random_result['file_url']}"
            # Send the new image and the original view in a single new message
            await interaction.response.send_message(content, view=self, ephemeral=self.hidden)

        @discord.ui.button(label="Browse Results", style=discord.ButtonStyle.secondary)
        async def browse_results(self, interaction: discord.Interaction, button: Button):
            if len(self.all_results) == 0:
                await interaction.response.send_message("No results to browse", ephemeral=True)
                return

            self.current_index = 0
            result = self.all_results[self.current_index]
            content = f"Result 1/{len(self.all_results)}:\n{result['file_url']}"
            view = self.BrowseView(self.cog, self.tags, self.all_results, self.hidden)
            await interaction.response.edit_message(content=content, view=view)

        @discord.ui.button(label="Pin", style=discord.ButtonStyle.danger)
        async def pin_message(self, interaction: discord.Interaction, button: Button):
            if interaction.message:
                try:
                    await interaction.message.pin()
                    await interaction.response.send_message("Message pinned successfully!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("I don't have permission to pin messages in this channel.", ephemeral=True)
                except discord.HTTPException as e:
                    await interaction.response.send_message(f"Failed to pin the message: {e}", ephemeral=True)

        class BrowseView(View):
            def __init__(self, cog, tags: str, all_results: list, hidden: bool = False):
                super().__init__(timeout=60)
                self.cog = cog
                self.tags = tags
                self.all_results = all_results
                self.hidden = hidden
                self.current_index = 0

            @discord.ui.button(label="First", style=discord.ButtonStyle.secondary)
            async def first(self, interaction: discord.Interaction, button: Button):
                self.current_index = 0
                result = self.all_results[self.current_index]
                content = f"Result 1/{len(self.all_results)}:\n{result['file_url']}"
                await interaction.response.edit_message(content=content, view=self)

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
            async def previous(self, interaction: discord.Interaction, button: Button):
                if self.current_index > 0:
                    self.current_index -= 1
                else:
                    self.current_index = len(self.all_results) - 1
                result = self.all_results[self.current_index]
                content = f"Result {self.current_index + 1}/{len(self.all_results)}:\n{result['file_url']}"
                await interaction.response.edit_message(content=content, view=self)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
            async def next(self, interaction: discord.Interaction, button: Button):
                if self.current_index < len(self.all_results) - 1:
                    self.current_index += 1
                else:
                    self.current_index = 0
                result = self.all_results[self.current_index]
                content = f"Result {self.current_index + 1}/{len(self.all_results)}:\n{result['file_url']}"
                await interaction.response.edit_message(content=content, view=self)

            @discord.ui.button(label="Last", style=discord.ButtonStyle.secondary)
            async def last(self, interaction: discord.Interaction, button: Button):
                self.current_index = len(self.all_results) - 1
                result = self.all_results[self.current_index]
                content = f"Result {len(self.all_results)}/{len(self.all_results)}:\n{result['file_url']}"
                await interaction.response.edit_message(content=content, view=self)

            @discord.ui.button(label="Go To", style=discord.ButtonStyle.primary)
            async def goto(self, interaction: discord.Interaction, button: Button):
                modal = self.GoToModal(len(self.all_results))
                await interaction.response.send_modal(modal)
                await modal.wait()
                if modal.value is not None:
                    self.current_index = modal.value - 1
                    result = self.all_results[self.current_index]
                    content = f"Result {modal.value}/{len(self.all_results)}:\n{result['file_url']}"
                    await interaction.followup.edit_message(interaction.message.id, content=content, view=self)

            class GoToModal(discord.ui.Modal):
                def __init__(self, max_pages: int):
                    super().__init__(title="Go To Page")
                    self.value = None
                    self.max_pages = max_pages
                    self.page_num = discord.ui.TextInput(
                        label=f"Page Number (1-{max_pages})",
                        placeholder=f"Enter a number between 1 and {max_pages}",
                        min_length=1,
                        max_length=len(str(max_pages))
                    )
                    self.add_item(self.page_num)

                async def on_submit(self, interaction: discord.Interaction):
                    try:
                        num = int(self.page_num.value)
                        if 1 <= num <= self.max_pages:
                            self.value = num
                            await interaction.response.defer()
                        else:
                            await interaction.response.send_message(
                                f"Please enter a number between 1 and {self.max_pages}",
                                ephemeral=True
                            )
                    except ValueError:
                        await interaction.response.send_message(
                            "Please enter a valid number",
                            ephemeral=True
                        )

            @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
            async def back(self, interaction: discord.Interaction, button: Button):
                random_result = random.choice(self.all_results)
                content = f"{random_result['file_url']}"
                view = Rule34Cog.Rule34Buttons(self.cog, self.tags, self.all_results, self.hidden)
                await interaction.response.edit_message(content=content, view=view)

    # --- Prefix Command ---
    @commands.command(name="rule34")
    async def rule34(self, ctx: commands.Context, *, tags: str = "kasane_teto"):
        """Search for images on Rule34 with the provided tags."""
        # Send initial loading message
        loading_msg = await ctx.reply("Fetching data, please wait...")

        # Call logic, passing the context (which includes the loading_msg reference indirectly)
        response = await self._rule34_logic(ctx, tags)

        if isinstance(response, tuple):
            content, all_results = response
            view = self.Rule34Buttons(self, tags, all_results)
            # Edit the original loading message with content and view
            await loading_msg.edit(content=content, view=view)
        elif response is not None: # Error occurred
            # Edit the original loading message with the error
            await loading_msg.edit(content=response, view=None) # Remove view on error

    # --- Slash Command ---
    @app_commands.command(name="rule34", description="Get random image from rule34 with specified tags")
    @app_commands.describe(
        tags="The tags to search for (e.g., 'kasane_teto rating:safe')",
        hidden="Set to True to make the response visible only to you (default: False)"
    )
    async def rule34_slash(self, interaction: discord.Interaction, tags: str, hidden: bool = False):
        """Slash command version of rule34."""
        # Pass hidden parameter to logic
        response = await self._rule34_logic(interaction, tags, hidden=hidden)
        
        if isinstance(response, tuple):
            content, all_results = response
            view = self.Rule34Buttons(self, tags, all_results, hidden)
            if interaction.response.is_done():
                await interaction.followup.send(content, view=view, ephemeral=hidden)
            else:
                await interaction.response.send_message(content, view=view, ephemeral=hidden)
        elif response is not None: # An error occurred
            if not interaction.response.is_done():
                ephemeral_error = hidden or response.startswith('This command can only be used')
                await interaction.response.send_message(response, ephemeral=ephemeral_error)
            else:
                try:
                    await interaction.followup.send(response, ephemeral=hidden)
                except discord.errors.NotFound:
                    print(f"Rule34 slash command: Interaction expired before sending error followup for tags '{tags}'.")
                except discord.HTTPException as e:
                    print(f"Rule34 slash command: Failed to send error followup for tags '{tags}': {e}")

    # --- New Browse Command ---
    @app_commands.command(name="rule34browse", description="Browse Rule34 results with navigation buttons")
    @app_commands.describe(
        tags="The tags to search for (e.g., 'kasane_teto rating:safe')",
        hidden="Set to True to make the response visible only to you (default: False)"
    )
    async def rule34_browse(self, interaction: discord.Interaction, tags: str, hidden: bool = False):
        """Browse Rule34 results with navigation buttons."""
        response = await self._rule34_logic(interaction, tags, hidden=hidden)
        
        if isinstance(response, tuple):
            _, all_results = response
            if len(all_results) == 0:
                content = "No results found"
                await interaction.response.send_message(content, ephemeral=hidden)
                return
                
            result = all_results[0]
            content = f"Result 1/{len(all_results)}:\n{result['file_url']}"
            view = self.Rule34Buttons.BrowseView(self, tags, all_results, hidden)
            if interaction.response.is_done():
                await interaction.followup.send(content, view=view, ephemeral=hidden)
            else:
                await interaction.response.send_message(content, view=view, ephemeral=hidden)
        elif response is not None: # An error occurred
            if not interaction.response.is_done():
                ephemeral_error = hidden or response.startswith('This command can only be used')
                await interaction.response.send_message(response, ephemeral=ephemeral_error)
            else:
                try:
                    await interaction.followup.send(response, ephemeral=hidden)
                except discord.errors.NotFound:
                    print(f"Rule34 browse command: Interaction expired before sending error followup for tags '{tags}'.")
                except discord.HTTPException as e:
                    print(f"Rule34 browse command: Failed to send error followup for tags '{tags}': {e}")


async def setup(bot):
    await bot.add_cog(Rule34Cog(bot))
