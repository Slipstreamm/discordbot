import os
import discord
from discord.ext import commands
from discord import app_commands
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
    async def _rule34_logic(self, interaction_or_ctx, tags: str, hidden: bool = False) -> typing.Optional[str]:
        """Core logic for the rule34 command. Returns error message string or None."""
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
                    if loading_msg: # Prefix
                        await loading_msg.edit(content=content)
                    elif is_interaction: # Slash
                        # Send cached result respecting hidden flag
                        await interaction_or_ctx.followup.send(content, ephemeral=hidden)
                    return None # Success, message sent

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
                    if loading_msg: # Prefix
                        await loading_msg.edit(content=result_content)
                    elif is_interaction: # Slash
                        # Send result respecting hidden flag
                        await interaction_or_ctx.followup.send(result_content, ephemeral=hidden)
                    return None # Success

            except Exception as e:
                error_msg = f"An error occurred: {e}"
                print(f"Error in rule34 logic: {e}") # Log the error
                # Return error message, ephemeral handled by caller
                return error_msg

    # --- Prefix Command ---
    @commands.command(name="rule34")
    async def rule34(self, ctx: commands.Context, *, tags: str = "kasane_teto"):
        """Search for images on Rule34 with the provided tags."""
        # Call logic, hidden is False by default and irrelevant for prefix
        response = await self._rule34_logic(ctx, tags)
        # Logic handles sending/editing the message directly for prefix commands
        # If an error message is returned, it means the loading message wasn't sent or edited
        if response is not None:
             # Check if loading_msg was created before trying to edit
             # This path shouldn't normally be hit if logic works correctly
             # but handle defensively. A simple reply might be better here.
             print(f"Rule34 prefix command received error response unexpectedly: {response}")
             await ctx.reply(response) # Send error as a new message

    # --- Slash Command ---
    # Updated signature and logic
    @app_commands.command(name="rule34", description="Get random image from rule34 with specified tags")
    @app_commands.describe(
        tags="The tags to search for (e.g., 'kasane_teto rating:safe')",
        hidden="Set to True to make the response visible only to you (default: False)"
    )
    async def rule34_slash(self, interaction: discord.Interaction, tags: str, hidden: bool = False):
        """Slash command version of rule34."""
        # Pass hidden parameter to logic
        response = await self._rule34_logic(interaction, tags, hidden=hidden)
        # If response is None, the logic already sent the result via followup/deferral

        if response is not None: # An error occurred
            # Ensure interaction hasn't already been responded to or deferred incorrectly
            if not interaction.response.is_done():
                # Send error message ephemerally if hidden is True OR if it's the NSFW channel error
                ephemeral_error = hidden or response.startswith('This command can only be used')
                await interaction.response.send_message(response, ephemeral=ephemeral_error)
            else:
                # If deferred, use followup. Send ephemerally based on hidden flag.
                # Check if we can still send a followup
                try:
                    await interaction.followup.send(response, ephemeral=hidden)
                except discord.errors.NotFound:
                     print(f"Rule34 slash command: Interaction expired before sending error followup for tags '{tags}'.")
                except discord.HTTPException as e:
                     print(f"Rule34 slash command: Failed to send error followup for tags '{tags}': {e}")


async def setup(bot):
    await bot.add_cog(Rule34Cog(bot))
