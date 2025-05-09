import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Button, View
import random
import aiohttp
import time
import json
import typing # Need this for Optional
import uuid # For subscription IDs
import asyncio
import logging # For logging

# Cache file path
CACHE_FILE = "rule34_cache.json"
# Subscriptions file path
SUBSCRIPTIONS_FILE = "rule34_subscriptions.json"

# Setup logger for this cog
log = logging.getLogger(__name__)

class Rule34Cog(commands.Cog, name="Rule34"): # Added name for clarity
    r34watch = app_commands.Group(name="r34watch", description="Manage Rule34 tag watchers for new posts.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache_data = self._load_cache()
        self.subscriptions_data = self._load_subscriptions()
        self.session: typing.Optional[aiohttp.ClientSession] = None
        # Start the task if the bot is ready, otherwise wait
        if bot.is_ready():
            asyncio.create_task(self.initialize_cog_async())
        else:
            asyncio.create_task(self.start_task_when_ready())


    async def initialize_cog_async(self):
        """Asynchronous part of cog initialization."""
        log.info("Initializing Rule34Cog...")
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            log.info("aiohttp ClientSession created for Rule34Cog.")
        if not self.check_new_posts.is_running():
            self.check_new_posts.start()
            log.info("Rule34 new post checker task started.")

    async def start_task_when_ready(self):
        """Waits until bot is ready, then initializes and starts tasks."""
        await self.bot.wait_until_ready()
        await self.initialize_cog_async()

    async def cog_load(self):
        # This method is called when the cog is loaded (e.g., on bot startup or after a load command)
        # It's a good place for setup that needs the bot to be at least partially ready.
        # However, tasks often need full readiness, so wait_until_ready is safer for starting them.
        # For session creation, it can be done here or in __init__ if it doesn't block.
        # The current __init__ structure with start_task_when_ready handles this.
        log.info(f"{self.__class__.__name__} cog loaded.")
        if self.session is None or self.session.closed: # Ensure session is created if not already
            self.session = aiohttp.ClientSession()
            log.info("aiohttp ClientSession (re)created during cog_load for Rule34Cog.")
        if not self.check_new_posts.is_running():
             # It's possible the task didn't start if cog was loaded after bot was already ready
             # and __init__ didn't catch it.
             if self.bot.is_ready():
                 self.check_new_posts.start()
                 log.info("Rule34 new post checker task started from cog_load.")
             else:
                 # This case should ideally be covered by __init__'s start_task_when_ready
                 log.warning("Rule34Cog loaded but bot not ready, task start deferred.")


    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.check_new_posts.cancel()
        log.info("Rule34 new post checker task stopped.")
        if self.session and not self.session.closed:
            await self.session.close()
            log.info("aiohttp ClientSession closed for Rule34Cog.")

    def _load_cache(self):
        """Loads the Rule34 image cache from a JSON file."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to load Rule34 cache file ({CACHE_FILE}): {e}")
        return {}

    def _save_cache(self):
        """Saves the Rule34 image cache to a JSON file."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self.cache_data, f, indent=4)
        except Exception as e:
            log.error(f"Failed to save Rule34 cache file ({CACHE_FILE}): {e}")

    def _load_subscriptions(self):
        """Loads the Rule34 subscriptions from a JSON file."""
        if os.path.exists(SUBSCRIPTIONS_FILE):
            try:
                with open(SUBSCRIPTIONS_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to load Rule34 subscriptions file ({SUBSCRIPTIONS_FILE}): {e}")
        return {} # { "guild_id": [ {sub_data}, ... ], ... }

    def _save_subscriptions(self):
        """Saves the Rule34 subscriptions to a JSON file."""
        try:
            with open(SUBSCRIPTIONS_FILE, "w") as f:
                json.dump(self.subscriptions_data, f, indent=4)
            log.debug(f"Saved Rule34 subscriptions to {SUBSCRIPTIONS_FILE}")
        except Exception as e:
            log.error(f"Failed to save Rule34 subscriptions file ({SUBSCRIPTIONS_FILE}): {e}")

    async def _get_or_create_webhook(self, channel: discord.TextChannel) -> typing.Optional[str]:
        """Gets an existing webhook URL or creates a new one for the bot in the channel."""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
            log.info("Recreated aiohttp.ClientSession in _get_or_create_webhook")

        # Check if we already have a webhook for this channel in any subscription for this guild
        guild_subs = self.subscriptions_data.get(str(channel.guild.id), [])
        for sub in guild_subs:
            if sub.get("channel_id") == str(channel.id) and sub.get("webhook_url"):
                try:
                    # Verify webhook
                    webhook = discord.Webhook.from_url(sub["webhook_url"], session=self.session)
                    await webhook.fetch() # Raises NotFound if invalid
                    if webhook.channel_id == channel.id:
                        log.debug(f"Reusing existing webhook {webhook.id} for channel {channel.id}")
                        return sub["webhook_url"]
                except (discord.NotFound, ValueError, discord.HTTPException):
                    log.warning(f"Found stored webhook URL for channel {channel.id} but it's invalid. Will try to create/find another.")
                    # Don't remove it from sub here, let the add command overwrite if a new one is made

        # If no valid stored webhook, try to find one owned by the bot in the channel
        try:
            webhooks = await channel.webhooks()
            for wh in webhooks:
                if wh.user == self.bot.user:
                    log.debug(f"Found existing bot-owned webhook {wh.id} ('{wh.name}') in channel {channel.id}")
                    return wh.url
        except discord.Forbidden:
            log.warning(f"Missing 'Manage Webhooks' permission in channel {channel.id} when trying to list webhooks.")
            return None # Cannot list, so cannot find existing
        except discord.HTTPException as e:
            log.error(f"HTTP error listing webhooks for channel {channel.id}: {e}")
            # Proceed to try creating one if this fails

        # If no suitable existing webhook, create a new one
        if not channel.permissions_for(channel.guild.me).manage_webhooks:
            log.warning(f"Missing 'Manage Webhooks' permission in channel {channel.id}. Cannot create webhook.")
            return None

        try:
            webhook_name = f"{self.bot.user.name} Rule34 Watcher"
            avatar_bytes = None
            if self.bot.user and self.bot.user.display_avatar:
                try:
                    avatar_bytes = await self.bot.user.display_avatar.read()
                except Exception as e:
                    log.warning(f"Could not read bot avatar for webhook creation: {e}")
            
            new_webhook = await channel.create_webhook(name=webhook_name, avatar=avatar_bytes, reason="Rule34 Tag Watcher")
            log.info(f"Created new webhook {new_webhook.id} ('{new_webhook.name}') in channel {channel.id}")
            return new_webhook.url
        except discord.HTTPException as e:
            log.error(f"Failed to create webhook in {channel.mention}: {e}")
            return None
        except Exception as e:
            log.exception(f"Unexpected error creating webhook in {channel.mention}")
            return None

    async def _send_via_webhook(self, webhook_url: str, content: str, thread_id: typing.Optional[str] = None):
        """Sends a message using the provided webhook URL, optionally to a thread."""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
            log.info("Recreated aiohttp.ClientSession in _send_via_webhook")
        
        try:
            webhook = discord.Webhook.from_url(webhook_url, session=self.session)
            target_thread_obj = None
            if thread_id:
                try:
                    target_thread_obj = discord.Object(id=int(thread_id))
                except ValueError:
                    log.error(f"Invalid thread_id format: {thread_id} for webhook {webhook_url[:30]}. Sending to main channel.")
            
            await webhook.send(
                content=content,
                username=f"{self.bot.user.name} Rule34 Watcher" if self.bot.user else "Rule34 Watcher",
                avatar_url=self.bot.user.display_avatar.url if self.bot.user and self.bot.user.display_avatar else None,
                thread=target_thread_obj
            )
            log.debug(f"Sent message via webhook to {webhook_url[:30]}... (Thread: {thread_id if thread_id else 'None'})")
            return True
        except ValueError:
            log.error(f"Invalid webhook URL format: {webhook_url[:30]}...")
        except discord.NotFound:
            log.error(f"Webhook not found (deleted?): {webhook_url[:30]}...")
        except discord.Forbidden:
            log.error(f"Forbidden to send to webhook (permissions issue?): {webhook_url[:30]}...")
        except discord.HTTPException as e:
            log.error(f"HTTP error sending to webhook {webhook_url[:30]}...: {e}")
        except aiohttp.ClientError as e:
            log.error(f"aiohttp client error sending to webhook {webhook_url[:30]}...: {e}")
        except Exception as e:
            log.exception(f"Unexpected error sending to webhook {webhook_url[:30]}...: {e}")
        return False


    # Updated _rule34_logic
    async def _rule34_logic(self, interaction_or_ctx: typing.Union[discord.Interaction, commands.Context, str], tags: str, pid_override: typing.Optional[int] = None, limit_override: typing.Optional[int] = None, hidden: bool = False) -> typing.Union[str, tuple[str, list], list]:
        """
        Core logic for fetching rule34 posts.
        Can be used by interactive commands or background tasks.

        Returns:
        - Error message string (str)
        - Tuple of (random_result_url, all_results_list) for interactive use (tuple[str, list])
        - List of all results (list) if pid_override is used (for background task)
        """
        base_url = "https://api.rule34.xxx/index.php"
        all_results = []
        current_pid = pid_override if pid_override is not None else 0
        # Use a specific limit if provided, otherwise default for interactive or background
        limit = limit_override if limit_override is not None else 1000 # Default for full fetch

        # NSFW Check (only if interaction_or_ctx is provided)
        if not isinstance(interaction_or_ctx, str) and interaction_or_ctx: # str indicates internal call
            is_nsfw_channel = False
            channel = interaction_or_ctx.channel
            if isinstance(channel, discord.TextChannel) and channel.is_nsfw():
                is_nsfw_channel = True
            elif isinstance(channel, discord.DMChannel): # DMs are considered NSFW for this purpose
                is_nsfw_channel = True

            allow_in_non_nsfw = 'rating:safe' in tags.lower()

            if not is_nsfw_channel and not allow_in_non_nsfw:
                return 'This command can only be used in age-restricted (NSFW) channels, DMs, or with the `rating:safe` tag.'

            # Defer or send loading message for interactive commands
            loading_msg = None
            is_interaction = not isinstance(interaction_or_ctx, commands.Context)
            if is_interaction:
                if not interaction_or_ctx.response.is_done():
                    await interaction_or_ctx.response.defer(ephemeral=hidden)
            else: # Prefix command
                # Check if interaction_or_ctx is a Context object before trying to reply
                if hasattr(interaction_or_ctx, 'reply'):
                    loading_msg = await interaction_or_ctx.reply("Fetching data, please wait...")
                else: # Likely an internal call where interaction_or_ctx is just for channel check
                    pass


        # Cache check (only for interactive, non-pid_override calls)
        if pid_override is None and limit_override is None: # Standard interactive call
            cache_key = tags.lower().strip()
            if cache_key in self.cache_data:
                cached_entry = self.cache_data[cache_key]
                cache_timestamp = cached_entry.get("timestamp", 0)
                if time.time() - cache_timestamp < 86400: # 24-hour cache
                    all_results = cached_entry.get("results", [])
                    if all_results:
                        random_result = random.choice(all_results)
                        return (f"{random_result['file_url']}", all_results)

        # Ensure session is available
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
            log.info("Recreated aiohttp.ClientSession in _rule34_logic")

        # Fetch from API
        all_results = [] # Reset if cache was invalid or this is a specific fetch
        
        # The original loop for fetching multiple pages is removed for simplicity with pid_override.
        # For background task, we fetch page 0 (latest) with a limit.
        # For interactive, we fetch page 0 with a larger limit for caching.
        # The API returns newest first.

        api_params = {
            "page": "dapi", "s": "post", "q": "index",
            "limit": limit, "pid": current_pid, "tags": tags, "json": 1
        }

        try:
            async with self.session.get(base_url, params=api_params) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                    except aiohttp.ContentTypeError:
                        log.warning(f"Rule34 API returned non-JSON for tags: {tags}, pid: {current_pid}, params: {api_params}")
                        data = None
                    
                    if data and isinstance(data, list):
                        all_results.extend(data)
                    elif isinstance(data, list) and len(data) == 0: # Empty list is a valid "no results"
                        pass # all_results remains empty
                    else: # Unexpected format
                        log.warning(f"Unexpected API response format (not list or empty list): {data} for tags: {tags}, pid: {current_pid}, params: {api_params}")
                        if pid_override is not None or limit_override is not None: # Internal call
                            return f"Unexpected API response format: {response.status}" # Return error string
                        # For interactive, it will fall through to "No results found" or error based on all_results
                else: # HTTP error
                    log.error(f"Failed to fetch Rule34 data. HTTP Status: {response.status} for tags: {tags}, pid: {current_pid}, params: {api_params}")
                    return f"Failed to fetch data. HTTP Status: {response.status}" # Return error string
        except aiohttp.ClientError as e:
            log.error(f"aiohttp.ClientError in _rule34_logic for tags {tags}: {e}")
            return f"Network error fetching data: {e}"
        except Exception as e:
            log.exception(f"Unexpected error in _rule34_logic API call for tags {tags}: {e}")
            return f"An unexpected error occurred during API call: {e}"


        # If this was a specific fetch for the background task or initial fetch, return all_results directly
        if pid_override is not None or limit_override is not None: # pid_override for subsequent checks, limit_override for initial fetch
            return all_results # Return the list of posts

        # --- For interactive calls (pid_override is None) ---
        # Save to cache if new results were fetched
        if all_results:
            cache_key = tags.lower().strip()
            self.cache_data[cache_key] = {
                "timestamp": int(time.time()),
                "results": all_results
            }
            self._save_cache()

        if not all_results:
            return "No results found for the given tags."
        else:
            random_result = random.choice(all_results)
            return (f"{random_result['file_url']}", all_results)


    class Rule34Buttons(View):
        def __init__(self, cog: 'Rule34Cog', tags: str, all_results: list, hidden: bool = False):
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
                content = "No results found for the given tags." # Consistent message
                if not interaction.response.is_done():
                    await interaction.response.send_message(content, ephemeral=hidden)
                else:
                    await interaction.followup.send(content, ephemeral=hidden)
                return
                
            result = all_results[0] # Should be safe if all_results is not empty
            content = f"Result 1/{len(all_results)}:\n{result['file_url']}"
            view = self.Rule34Buttons.BrowseView(self, tags, all_results, hidden)
            if interaction.response.is_done():
                await interaction.followup.send(content, view=view, ephemeral=hidden)
            else:
                await interaction.response.send_message(content, view=view, ephemeral=hidden)
        elif isinstance(response, str): # An error occurred, response is error string
            if not interaction.response.is_done():
                ephemeral_error = hidden or response.startswith('This command can only be used')
                await interaction.response.send_message(response, ephemeral=ephemeral_error)
            else:
                try:
                    await interaction.followup.send(response, ephemeral=hidden)
                except discord.errors.NotFound:
                    log.warning(f"Rule34 browse command: Interaction expired for tags '{tags}'.")
                except discord.HTTPException as e:
                    log.error(f"Rule34 browse command: Failed to send error followup for tags '{tags}': {e}")
        else: # Should not happen if logic returns str or tuple
            log.error(f"Rule34 browse: Unexpected response type from _rule34_logic: {type(response)}")
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
            else:
                await interaction.followup.send("An unexpected error occurred.", ephemeral=True)

    # --- Background Task for Checking New Posts ---
    @tasks.loop(minutes=10)
    async def check_new_posts(self):
        log.debug("Running Rule34 new post check...")
        if not self.subscriptions_data:
            # log.debug("No active Rule34 subscriptions to check.")
            return

        # Create a deep copy for iteration to avoid issues if modified during processing
        # Though direct modification during this loop is unlikely with current plan
        current_subscriptions = json.loads(json.dumps(self.subscriptions_data))
        needs_save = False

        for guild_id_str, subs_list in current_subscriptions.items():
            if not isinstance(subs_list, list): # Ensure structure
                log.warning(f"Malformed subscriptions for guild {guild_id_str}, skipping.")
                continue

            for sub_index, sub in enumerate(subs_list):
                if not isinstance(sub, dict): # Ensure structure
                    log.warning(f"Malformed subscription entry for guild {guild_id_str}, index {sub_index}, skipping.")
                    continue

                tags = sub.get("tags")
                webhook_url = sub.get("webhook_url")
                last_known_post_id = sub.get("last_known_post_id", 0) # Default to 0 if not set

                if not tags or not webhook_url:
                    log.warning(f"Subscription for guild {guild_id_str} missing tags or webhook_url, skipping: {sub.get('subscription_id')}")
                    continue
                
                log.debug(f"Checking tags '{tags}' for guild {guild_id_str}, sub_id {sub.get('subscription_id')}, last_id {last_known_post_id}")

                # Fetch latest posts (e.g., limit 50, pid 0)
                # The API returns newest first. We want posts with ID > last_known_post_id.
                # We only need to fetch page 0 (pid=0) with a reasonable limit.
                # If there are more new posts than our limit, they'll be caught in the next run.
                fetched_posts_response = await self._rule34_logic("internal_task_call", tags, pid_override=0, limit_override=100)

                if isinstance(fetched_posts_response, str): # Error fetching
                    log.error(f"Error fetching posts for subscription {sub.get('subscription_id')} (tags: {tags}): {fetched_posts_response}")
                    continue
                
                if not fetched_posts_response: # No posts found at all
                    log.debug(f"No posts found for tags '{tags}' in subscription {sub.get('subscription_id')}")
                    continue

                new_posts_to_send = []
                current_max_id_this_batch = last_known_post_id

                for post_data in fetched_posts_response:
                    if not isinstance(post_data, dict) or "id" not in post_data or "file_url" not in post_data:
                        log.warning(f"Malformed post data received for tags {tags}: {post_data}")
                        continue
                    
                    post_id = int(post_data["id"]) # Ensure it's an int for comparison
                    if post_id > last_known_post_id:
                        new_posts_to_send.append(post_data)
                    # Keep track of the highest ID encountered in this fetched batch, even if not "new"
                    # This helps if last_known_post_id was somehow far behind.
                    if post_id > current_max_id_this_batch:
                         current_max_id_this_batch = post_id


                if new_posts_to_send:
                    # Sort new posts by ID (oldest of the new first) to send in order
                    new_posts_to_send.sort(key=lambda p: int(p["id"]))
                    
                    log.info(f"Found {len(new_posts_to_send)} new post(s) for tags '{tags}', sub_id {sub.get('subscription_id')}")

                    latest_sent_id_for_this_sub = last_known_post_id
                    for new_post in new_posts_to_send:
                        post_id = int(new_post["id"])
                        message_content = f"New post for tags `{tags}`:\n{new_post['file_url']}"
                        
                        # NSFW check for the target channel before sending
                        # This requires getting the channel object, which can be slow in a loop.
                        # For now, assume webhook is in an appropriate channel as per setup.
                        # A more robust solution might store channel NSFW status or re-check.
                        
                        current_thread_id = sub.get("thread_id") # Get thread_id for this subscription
                        send_success = await self._send_via_webhook(webhook_url, message_content, thread_id=current_thread_id)
                        if send_success:
                            latest_sent_id_for_this_sub = post_id
                            # Update the original subscriptions_data immediately after successful send
                            # This is a bit tricky due to iterating over a copy.
                            # We need to find the exact subscription in self.subscriptions_data and update it.
                            original_guild_subs = self.subscriptions_data.get(guild_id_str)
                            if original_guild_subs:
                                for original_sub_entry in original_guild_subs:
                                    if original_sub_entry.get("subscription_id") == sub.get("subscription_id"):
                                        original_sub_entry["last_known_post_id"] = latest_sent_id_for_this_sub
                                        needs_save = True
                                        log.debug(f"Updated last_known_post_id to {latest_sent_id_for_this_sub} for sub {sub.get('subscription_id')}")
                                        break # Found and updated the specific subscription
                            await asyncio.sleep(1) # Small delay to avoid hitting webhook rate limits too hard
                        else:
                            log.error(f"Failed to send new post via webhook for sub {sub.get('subscription_id')}. Will retry later.")
                            # Don't update last_known_post_id if send failed, so it's retried.
                            # However, stop processing further new posts for THIS subscription in THIS run
                            # to avoid spamming if the webhook is broken.
                            break 
                
                # After processing all new posts for a subscription (or if none were new),
                # ensure its last_known_post_id reflects the highest ID seen in the fetched batch
                # if that ID is greater than what was sent. This helps catch up if many posts
                # appeared between checks and some weren't sent due to send failures or limits.
                # This should only happen if no *new* posts were sent in this iteration for this sub.
                if not new_posts_to_send and current_max_id_this_batch > last_known_post_id:
                    original_guild_subs = self.subscriptions_data.get(guild_id_str)
                    if original_guild_subs:
                        for original_sub_entry in original_guild_subs:
                            if original_sub_entry.get("subscription_id") == sub.get("subscription_id"):
                                if original_sub_entry.get("last_known_post_id", 0) < current_max_id_this_batch:
                                    original_sub_entry["last_known_post_id"] = current_max_id_this_batch
                                    needs_save = True
                                    log.debug(f"Fast-forwarded last_known_post_id to {current_max_id_this_batch} for sub {sub.get('subscription_id')} (no new posts sent).")
                                break


        if needs_save:
            self._save_subscriptions()
        log.debug("Finished Rule34 new post check.")

    @check_new_posts.before_loop
    async def before_check_new_posts(self):
        await self.bot.wait_until_ready()
        log.info("Rule34Cog: `check_new_posts` loop is waiting for bot readiness...")
        if self.session is None or self.session.closed: # Ensure session exists before loop starts
            self.session = aiohttp.ClientSession()
            log.info("aiohttp ClientSession created before check_new_posts loop.")

    # --- r34watch slash command group ---

    @r34watch.command(name="add", description="Watch for new rule34 posts with specific tags in a channel or thread.")
    @app_commands.describe(
        tags="The tags to search for (e.g., 'kasane_teto rating:safe').",
        channel="The parent channel for the subscription (and webhook).",
        thread_target="Optional: Name or ID of a thread within the channel to send messages to."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def r34watch_add(self, interaction: discord.Interaction, tags: str, channel: discord.TextChannel, thread_target: typing.Optional[str] = None):
        """Adds a new Rule34 tag watch subscription, optionally targeting a thread."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        # NSFW Check for the target channel itself before setting up
        # This is a basic check; the command user should ensure the channel is appropriate.
        # The `rating:safe` tag is the primary content filter.
        if not channel.is_nsfw() and 'rating:safe' not in tags.lower():
            await interaction.response.send_message(
                f"⚠️ The channel {channel.mention} is not marked as NSFW. "
                f"Subscriptions without 'rating:safe' in tags are only recommended for NSFW channels. "
                f"Please ensure this is intended or add 'rating:safe' to your tags.",
                ephemeral=True
            )
            # Allowing setup to proceed but with a warning. Could be made stricter.

        await interaction.response.defer(ephemeral=True)

        target_thread_id: typing.Optional[str] = None
        target_thread_mention: str = ""

        if thread_target:
            found_thread: typing.Optional[discord.Thread] = None
            # Try to find by ID first
            try:
                # Ensure guild object is available
                if not channel.guild: # Should not happen if interaction.guild is checked, but defensive
                    await interaction.followup.send("Error: Guild context not found for channel.")
                    return

                thread_as_obj = await channel.guild.fetch_channel(int(thread_target))
                if isinstance(thread_as_obj, discord.Thread) and thread_as_obj.parent_id == channel.id:
                    found_thread = thread_as_obj
            except (ValueError, discord.NotFound, discord.Forbidden): # Not an ID or not found/accessible
                pass # Try by name next
            except Exception as e: # Catch other potential errors during fetch_channel
                log.error(f"Error fetching thread by ID '{thread_target}': {e}")
                pass


            if not found_thread: # Try by name
                # Ensure channel.threads is accessible and correct type
                if hasattr(channel, 'threads'):
                    for t in channel.threads:
                        if t.name.lower() == thread_target.lower():
                            found_thread = t
                            break
                else:
                    log.warning(f"Channel {channel.mention} does not appear to support threads or threads attribute is missing.")

            if found_thread:
                target_thread_id = str(found_thread.id)
                target_thread_mention = found_thread.mention
            else:
                await interaction.followup.send(f"❌ Could not find an accessible thread named or with ID `{thread_target}` in {channel.mention}.")
                return

        webhook_url = await self._get_or_create_webhook(channel) # Webhook is on parent channel
        if not webhook_url:
            await interaction.followup.send(
                f"❌ Failed to get or create a webhook for {channel.mention}. "
                "I might be missing 'Manage Webhooks' permission, or the channel webhook limit (15) is reached."
            )
            return

        initial_posts = await self._rule34_logic("internal_initial_fetch", tags, pid_override=0, limit_override=1)
        last_known_post_id = 0
        if isinstance(initial_posts, list) and initial_posts:
            if isinstance(initial_posts[0], dict) and "id" in initial_posts[0]:
                 last_known_post_id = int(initial_posts[0]["id"])
            else:
                log.warning(f"Malformed post data during initial fetch for tags '{tags}': {initial_posts[0]}")
        elif isinstance(initial_posts, str):
            log.error(f"Error during initial post fetch for r34watch add (tags: {tags}): {initial_posts}")

        guild_id_str = str(interaction.guild_id)
        subscription_id = str(uuid.uuid4())
        
        new_subscription = {
            "subscription_id": subscription_id,
            "tags": tags.strip(),
            "channel_id": str(channel.id), # Parent channel for webhook
            "thread_id": target_thread_id, # Optional target thread ID
            "webhook_url": webhook_url,
            "last_known_post_id": last_known_post_id,
            "added_by_user_id": str(interaction.user.id),
            "added_timestamp": discord.utils.utcnow().isoformat()
        }

        if guild_id_str not in self.subscriptions_data:
            self.subscriptions_data[guild_id_str] = []
        
        # Check for duplicate subscription (same tags, same channel, same thread_id)
        for existing_sub in self.subscriptions_data[guild_id_str]:
            if (existing_sub.get("tags") == new_subscription["tags"] and
                existing_sub.get("channel_id") == new_subscription["channel_id"] and
                existing_sub.get("thread_id") == new_subscription["thread_id"]): # Also check thread_id
                target_location = f"{channel.mention}"
                if target_thread_mention:
                    target_location += f" (thread: {target_thread_mention})"
                await interaction.followup.send(f"⚠️ A subscription for tags `{tags}` in {target_location} already exists (ID: `{existing_sub.get('subscription_id')}`).")
                return

        self.subscriptions_data[guild_id_str].append(new_subscription)
        self._save_subscriptions()

        target_location_msg = f"in {channel.mention}"
        if target_thread_mention:
            target_location_msg += f" (thread: {target_thread_mention})"

        log.info(f"Added R34 watch: Guild {guild_id_str}, Tags '{tags}', Channel {channel.id}, Thread {target_thread_id}, Sub ID {subscription_id}, Last Post {last_known_post_id}")
        await interaction.followup.send(
            f"✅ Watching for new posts with tags `{tags}` {target_location_msg}.\n"
            f"Initial latest post ID set to: {last_known_post_id}.\n"
            f"Subscription ID: `{subscription_id}` (use this to remove the watch)."
        )

    @r34watch.command(name="list", description="List active Rule34 tag watches for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def r34watch_list(self, interaction: discord.Interaction):
        """Lists all active Rule34 tag watch subscriptions for the current server."""
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id_str = str(interaction.guild_id)
        guild_subs = self.subscriptions_data.get(guild_id_str, [])

        if not guild_subs:
            await interaction.response.send_message("No active Rule34 tag watches for this server.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Active Rule34 Tag Watches for {interaction.guild.name}", color=discord.Color.blue())
        
        description_parts = []
        for sub in guild_subs:
            channel_mention = f"<#{sub.get('channel_id', 'Unknown')}>"
            thread_id = sub.get('thread_id')
            target_location = channel_mention
            if thread_id:
                # Try to fetch thread for its name, fallback to ID
                try:
                    # Ensure guild object is available
                    guild = interaction.guild
                    if not guild: # Should ideally not happen if guild_id is present
                        target_location += f" (Thread ID: `{thread_id}` - Guild context lost)"
                    else:
                        thread_obj = await guild.fetch_channel(int(thread_id))
                        if isinstance(thread_obj, discord.Thread):
                            target_location += f" (Thread: {thread_obj.mention} `{thread_obj.name}`)"
                        else: # Should be a thread, but if not, show ID
                            target_location += f" (Thread ID: `{thread_id}` - Not a thread object)"
                except (discord.NotFound, discord.Forbidden, ValueError):
                    target_location += f" (Thread ID: `{thread_id}` - Not found or no access)"
                except Exception as e: # Catch any other error during fetch
                     log.warning(f"Error fetching thread {thread_id} for list command: {e}")
                     target_location += f" (Thread ID: `{thread_id}` - Error fetching name)"
            
            tags_str = sub.get('tags', 'Unknown tags')
            sub_id_str = sub.get('subscription_id', 'Unknown ID')
            last_id = sub.get('last_known_post_id', 'N/A')
            description_parts.append(
                f"**ID:** `{sub_id_str}`\n"
                f"  **Tags:** `{tags_str}`\n"
                f"  **Target:** {target_location}\n"
                f"  **Last Sent ID:** `{last_id}`\n"
                f"---"
            )
        
        full_description = "\n".join(description_parts)
        
        # Handle potential description length limits for embeds
        if len(full_description) > 4096:
            await interaction.response.send_message("Too many subscriptions to display in one message. This will be improved later.", ephemeral=True)
            # TODO: Implement pagination for long lists
        else:
            embed.description = full_description
            await interaction.response.send_message(embed=embed, ephemeral=True)


    @r34watch.command(name="remove", description="Stop watching for new Rule34 posts using a subscription ID.")
    @app_commands.describe(subscription_id="The ID of the subscription to remove (get from 'list' command).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def r34watch_remove(self, interaction: discord.Interaction, subscription_id: str):
        """Removes a Rule34 tag watch subscription by its ID."""
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id_str = str(interaction.guild_id)
        guild_subs = self.subscriptions_data.get(guild_id_str, [])
        
        removed_sub_info = None
        new_subs_list = []
        found = False
        for sub_entry in guild_subs: # Renamed loop variable to avoid conflict
            if sub_entry.get("subscription_id") == subscription_id:
                channel_id_for_removed = sub_entry.get('channel_id')
                thread_id_for_removed = sub_entry.get('thread_id')
                target_desc = f"<#{channel_id_for_removed}>"
                if thread_id_for_removed:
                    target_desc += f" (Thread ID: {thread_id_for_removed})"

                removed_sub_info = f"tags `{sub_entry.get('tags')}` in {target_desc}"
                found = True
                log.info(f"Removing R34 watch: Guild {guild_id_str}, Sub ID {subscription_id}")
            else:
                new_subs_list.append(sub_entry)
        
        if not found:
            await interaction.response.send_message(f"❌ Subscription ID `{subscription_id}` not found for this server.", ephemeral=True)
            return

        if not new_subs_list: # If it was the last one
            del self.subscriptions_data[guild_id_str]
        else:
            self.subscriptions_data[guild_id_str] = new_subs_list
        
        self._save_subscriptions()
        await interaction.response.send_message(f"✅ Successfully removed Rule34 watch for {removed_sub_info} (ID: `{subscription_id}`).", ephemeral=True)


async def setup(bot: commands.Bot): # Added type hint for bot
    await bot.add_cog(Rule34Cog(bot))
    log.info("Rule34Cog added to bot.")
