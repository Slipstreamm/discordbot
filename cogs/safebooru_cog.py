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
CACHE_FILE = "safebooru_cache.json"
# Subscriptions file path
SUBSCRIPTIONS_FILE = "safebooru_subscriptions.json"
# Pending requests file path
PENDING_REQUESTS_FILE = "safebooru_pending_requests.json"

# Setup logger for this cog
log = logging.getLogger(__name__)

class SafebooruCog(commands.Cog, name="Safebooru"): # Added name for clarity
    safebooruwatch = app_commands.Group(name="safebooruwatch", description="Manage Safebooru tag watchers for new posts.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache_data = self._load_cache()
        self.subscriptions_data = self._load_subscriptions()
        self.pending_requests_data = self._load_pending_requests()
        self.session: typing.Optional[aiohttp.ClientSession] = None
        # Start the task if the bot is ready, otherwise wait
        if bot.is_ready():
            asyncio.create_task(self.initialize_cog_async())
        else:
            asyncio.create_task(self.start_task_when_ready())


    async def initialize_cog_async(self):
        """Asynchronous part of cog initialization."""
        log.info("Initializing SafebooruCog...")
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            log.info("aiohttp ClientSession created for SafebooruCog.")
        if not self.check_new_posts.is_running():
            self.check_new_posts.start()
            log.info("Safebooru new post checker task started.")

    async def start_task_when_ready(self):
        """Waits until bot is ready, then initializes and starts tasks."""
        await self.bot.wait_until_ready()
        await self.initialize_cog_async()

    async def cog_load(self):
        log.info(f"{self.__class__.__name__} cog loaded.")
        if self.session is None or self.session.closed: 
            self.session = aiohttp.ClientSession()
            log.info("aiohttp ClientSession (re)created during cog_load for SafebooruCog.")
        if not self.check_new_posts.is_running():
             if self.bot.is_ready():
                 self.check_new_posts.start()
                 log.info("Safebooru new post checker task started from cog_load.")
             else:
                 log.warning("SafebooruCog loaded but bot not ready, task start deferred.")


    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.check_new_posts.cancel()
        log.info("Safebooru new post checker task stopped.")
        if self.session and not self.session.closed:
            await self.session.close()
            log.info("aiohttp ClientSession closed for SafebooruCog.")

    def _load_cache(self):
        """Loads the Safebooru image cache from a JSON file."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to load Safebooru cache file ({CACHE_FILE}): {e}")
        return {}

    def _save_cache(self):
        """Saves the Safebooru image cache to a JSON file."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self.cache_data, f, indent=4)
        except Exception as e:
            log.error(f"Failed to save Safebooru cache file ({CACHE_FILE}): {e}")

    def _load_subscriptions(self):
        """Loads the Safebooru subscriptions from a JSON file."""
        if os.path.exists(SUBSCRIPTIONS_FILE):
            try:
                with open(SUBSCRIPTIONS_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to load Safebooru subscriptions file ({SUBSCRIPTIONS_FILE}): {e}")
        return {} 

    def _save_subscriptions(self):
        """Saves the Safebooru subscriptions to a JSON file."""
        try:
            with open(SUBSCRIPTIONS_FILE, "w") as f:
                json.dump(self.subscriptions_data, f, indent=4)
            log.debug(f"Saved Safebooru subscriptions to {SUBSCRIPTIONS_FILE}")
        except Exception as e:
            log.error(f"Failed to save Safebooru subscriptions file ({SUBSCRIPTIONS_FILE}): {e}")

    def _load_pending_requests(self):
        """Loads pending Safebooru watch requests from a JSON file."""
        if os.path.exists(PENDING_REQUESTS_FILE):
            try:
                with open(PENDING_REQUESTS_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Failed to load Safebooru pending requests file ({PENDING_REQUESTS_FILE}): {e}")
        return {}

    def _save_pending_requests(self):
        """Saves pending Safebooru watch requests to a JSON file."""
        try:
            with open(PENDING_REQUESTS_FILE, "w") as f:
                json.dump(self.pending_requests_data, f, indent=4)
            log.debug(f"Saved Safebooru pending requests to {PENDING_REQUESTS_FILE}")
        except Exception as e:
            log.error(f"Failed to save Safebooru pending requests file ({PENDING_REQUESTS_FILE}): {e}")

    async def _get_or_create_webhook(self, channel: typing.Union[discord.TextChannel, discord.ForumChannel]) -> typing.Optional[str]:
        """Gets an existing webhook URL or creates a new one for the bot in the channel."""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
            log.info("Recreated aiohttp.ClientSession in _get_or_create_webhook")

        guild_subs = self.subscriptions_data.get(str(channel.guild.id), [])
        for sub in guild_subs:
            if sub.get("channel_id") == str(channel.id) and sub.get("webhook_url"):
                try:
                    webhook = discord.Webhook.from_url(sub["webhook_url"], session=self.session)
                    await webhook.fetch() 
                    if webhook.channel_id == channel.id:
                        log.debug(f"Reusing existing webhook {webhook.id} for channel {channel.id}")
                        return sub["webhook_url"]
                except (discord.NotFound, ValueError, discord.HTTPException):
                    log.warning(f"Found stored webhook URL for channel {channel.id} but it's invalid. Will try to create/find another.")

        try:
            webhooks = await channel.webhooks()
            for wh in webhooks:
                if wh.user == self.bot.user:
                    log.debug(f"Found existing bot-owned webhook {wh.id} ('{wh.name}') in channel {channel.id}")
                    return wh.url
        except discord.Forbidden:
            log.warning(f"Missing 'Manage Webhooks' permission in channel {channel.id} when trying to list webhooks.")
            return None
        except discord.HTTPException as e:
            log.error(f"HTTP error listing webhooks for channel {channel.id}: {e}")

        if not channel.permissions_for(channel.guild.me).manage_webhooks:
            log.warning(f"Missing 'Manage Webhooks' permission in channel {channel.id}. Cannot create webhook.")
            return None

        try:
            webhook_name = f"{self.bot.user.name} Safebooru Watcher"
            avatar_bytes = None
            if self.bot.user and self.bot.user.display_avatar:
                try:
                    avatar_bytes = await self.bot.user.display_avatar.read()
                except Exception as e:
                    log.warning(f"Could not read bot avatar for webhook creation: {e}")
            
            new_webhook = await channel.create_webhook(name=webhook_name, avatar=avatar_bytes, reason="Safebooru Tag Watcher")
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
                username=f"{self.bot.user.name} Safebooru Watcher" if self.bot.user else "Safebooru Watcher",
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

    async def _safebooru_logic(self, interaction_or_ctx: typing.Union[discord.Interaction, commands.Context, str], tags: str, pid_override: typing.Optional[int] = None, limit_override: typing.Optional[int] = None, hidden: bool = False) -> typing.Union[str, tuple[str, list], list]:
        """
        Core logic for fetching safebooru posts.
        Can be used by interactive commands or background tasks.
        Returns:
        - Error message string (str)
        - Tuple of (random_result_url, all_results_list) for interactive use (tuple[str, list])
        - List of all results (list) if pid_override is used (for background task)
        """
        base_url = "https://safebooru.org/index.php?page=dapi&s=post&q=index"
        all_results = []
        current_pid = pid_override if pid_override is not None else 0
        limit = limit_override if limit_override is not None else 1000 

        if not isinstance(interaction_or_ctx, str) and interaction_or_ctx: 
            loading_msg = None
            is_interaction = not isinstance(interaction_or_ctx, commands.Context)
            if is_interaction:
                if not interaction_or_ctx.response.is_done():
                    await interaction_or_ctx.response.defer(ephemeral=hidden)
            else: 
                if hasattr(interaction_or_ctx, 'reply'):
                    loading_msg = await interaction_or_ctx.reply("Fetching data, please wait...")
                else: 
                    pass

        if pid_override is None and limit_override is None: 
            cache_key = tags.lower().strip()
            if cache_key in self.cache_data:
                cached_entry = self.cache_data[cache_key]
                cache_timestamp = cached_entry.get("timestamp", 0)
                if time.time() - cache_timestamp < 86400: 
                    all_results = cached_entry.get("results", [])
                    if all_results:
                        random_result = random.choice(all_results)
                        return (f"{random_result['file_url']}", all_results)

        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
            log.info("Recreated aiohttp.ClientSession in _safebooru_logic")

        all_results = [] 
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
                        log.warning(f"Safebooru API returned non-JSON for tags: {tags}, pid: {current_pid}, params: {api_params}")
                        data = None
                    
                    if data and isinstance(data, list):
                        all_results.extend(data)
                    elif isinstance(data, list) and len(data) == 0: 
                        pass 
                    else: 
                        log.warning(f"Unexpected API response format (not list or empty list): {data} for tags: {tags}, pid: {current_pid}, params: {api_params}")
                        if pid_override is not None or limit_override is not None: 
                            return f"Unexpected API response format: {response.status}" 
                else: 
                    log.error(f"Failed to fetch Safebooru data. HTTP Status: {response.status} for tags: {tags}, pid: {current_pid}, params: {api_params}")
                    return f"Failed to fetch data. HTTP Status: {response.status}"
        except aiohttp.ClientError as e:
            log.error(f"aiohttp.ClientError in _safebooru_logic for tags {tags}: {e}")
            return f"Network error fetching data: {e}"
        except Exception as e:
            log.exception(f"Unexpected error in _safebooru_logic API call for tags {tags}: {e}")
            return f"An unexpected error occurred during API call: {e}"

        if pid_override is not None or limit_override is not None: 
            return all_results 

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


    class SafebooruButtons(View):
        def __init__(self, cog: 'SafebooruCog', tags: str, all_results: list, hidden: bool = False):
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
                view = SafebooruCog.SafebooruButtons(self.cog, self.tags, self.all_results, self.hidden)
                await interaction.response.edit_message(content=content, view=view)

    # --- Prefix Command ---
    @commands.command(name="safebooru")
    async def safebooru(self, ctx: commands.Context, *, tags: str = "1girl"):
        """Search for images on Safebooru with the provided tags."""
        loading_msg = await ctx.reply("Fetching data, please wait...")
        response = await self._safebooru_logic(ctx, tags)

        if isinstance(response, tuple):
            content, all_results = response
            view = self.SafebooruButtons(self, tags, all_results)
            await loading_msg.edit(content=content, view=view)
        elif response is not None: 
            await loading_msg.edit(content=response, view=None) 

    # --- Slash Command ---
    @app_commands.command(name="safebooru", description="Get random image from Safebooru with specified tags")
    @app_commands.describe(
        tags="The tags to search for (e.g., '1girl cat_ears')",
        hidden="Set to True to make the response visible only to you (default: False)"
    )
    async def safebooru_slash(self, interaction: discord.Interaction, tags: str, hidden: bool = False):
        """Slash command version of safebooru."""
        response = await self._safebooru_logic(interaction, tags, hidden=hidden)
        
        if isinstance(response, tuple):
            content, all_results = response
            view = self.SafebooruButtons(self, tags, all_results, hidden)
            if interaction.response.is_done():
                await interaction.followup.send(content, view=view, ephemeral=hidden)
            else:
                await interaction.response.send_message(content, view=view, ephemeral=hidden)
        elif response is not None: 
            if not interaction.response.is_done():
                await interaction.response.send_message(response, ephemeral=hidden)
            else:
                try:
                    await interaction.followup.send(response, ephemeral=hidden)
                except discord.errors.NotFound:
                    print(f"Safebooru slash command: Interaction expired before sending error followup for tags '{tags}'.")
                except discord.HTTPException as e:
                    print(f"Safebooru slash command: Failed to send error followup for tags '{tags}': {e}")

    # --- New Browse Command ---
    @app_commands.command(name="safeboorubrowse", description="Browse Safebooru results with navigation buttons")
    @app_commands.describe(
        tags="The tags to search for (e.g., '1girl dog_ears')",
        hidden="Set to True to make the response visible only to you (default: False)"
    )
    async def safebooru_browse(self, interaction: discord.Interaction, tags: str, hidden: bool = False):
        """Browse Safebooru results with navigation buttons."""
        response = await self._safebooru_logic(interaction, tags, hidden=hidden)
        
        if isinstance(response, tuple):
            _, all_results = response
            if len(all_results) == 0:
                content = "No results found for the given tags." 
                if not interaction.response.is_done():
                    await interaction.response.send_message(content, ephemeral=hidden)
                else:
                    await interaction.followup.send(content, ephemeral=hidden)
                return
                
            result = all_results[0] 
            content = f"Result 1/{len(all_results)}:\n{result['file_url']}"
            view = self.SafebooruButtons.BrowseView(self, tags, all_results, hidden)
            if interaction.response.is_done():
                await interaction.followup.send(content, view=view, ephemeral=hidden)
            else:
                await interaction.response.send_message(content, view=view, ephemeral=hidden)
        elif isinstance(response, str): 
            if not interaction.response.is_done():
                await interaction.response.send_message(response, ephemeral=hidden)
            else:
                try:
                    await interaction.followup.send(response, ephemeral=hidden)
                except discord.errors.NotFound:
                    log.warning(f"Safebooru browse command: Interaction expired for tags '{tags}'.")
                except discord.HTTPException as e:
                    log.error(f"Safebooru browse command: Failed to send error followup for tags '{tags}': {e}")
        else: 
            log.error(f"Safebooru browse: Unexpected response type from _safebooru_logic: {type(response)}")
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)
            else:
                await interaction.followup.send("An unexpected error occurred.", ephemeral=True)

    # --- Background Task for Checking New Posts ---
    @tasks.loop(minutes=10)
    async def check_new_posts(self):
        log.debug("Running Safebooru new post check...")
        if not self.subscriptions_data:
            log.debug("No active Safebooru subscriptions to check.")
            return

        current_subscriptions = json.loads(json.dumps(self.subscriptions_data))
        needs_save = False

        for guild_id_str, subs_list in current_subscriptions.items():
            if not isinstance(subs_list, list): 
                log.warning(f"Malformed subscriptions for guild {guild_id_str}, skipping.")
                continue

            for sub_index, sub in enumerate(subs_list):
                if not isinstance(sub, dict): 
                    log.warning(f"Malformed subscription entry for guild {guild_id_str}, index {sub_index}, skipping.")
                    continue

                tags = sub.get("tags")
                webhook_url = sub.get("webhook_url")
                last_known_post_id = sub.get("last_known_post_id", 0) 

                if not tags or not webhook_url:
                    log.warning(f"Subscription for guild {guild_id_str} missing tags or webhook_url, skipping: {sub.get('subscription_id')}")
                    continue
                
                log.debug(f"Checking tags '{tags}' for guild {guild_id_str}, sub_id {sub.get('subscription_id')}, last_id {last_known_post_id}")
                
                fetched_posts_response = await self._safebooru_logic("internal_task_call", tags, pid_override=0, limit_override=100)

                if isinstance(fetched_posts_response, str): 
                    log.error(f"Error fetching posts for subscription {sub.get('subscription_id')} (tags: {tags}): {fetched_posts_response}")
                    continue
                
                if not fetched_posts_response: 
                    log.debug(f"No posts found for tags '{tags}' in subscription {sub.get('subscription_id')}")
                    continue

                new_posts_to_send = []
                current_max_id_this_batch = last_known_post_id

                for post_data in fetched_posts_response:
                    if not isinstance(post_data, dict) or "id" not in post_data or "file_url" not in post_data:
                        log.warning(f"Malformed post data received for tags {tags}: {post_data}")
                        continue
                    
                    post_id = int(post_data["id"]) 
                    if post_id > last_known_post_id:
                        new_posts_to_send.append(post_data)
                    if post_id > current_max_id_this_batch:
                         current_max_id_this_batch = post_id

                if new_posts_to_send:
                    new_posts_to_send.sort(key=lambda p: int(p["id"]))
                    log.info(f"Found {len(new_posts_to_send)} new post(s) for tags '{tags}', sub_id {sub.get('subscription_id')}")
                    latest_sent_id_for_this_sub = last_known_post_id
                    for new_post in new_posts_to_send:
                        post_id = int(new_post["id"])
                        message_content = f"New post for tags `{tags}`:\n{new_post['file_url']}"
                        
                        webhook_target_thread_id: typing.Optional[str] = None
                        if sub.get("forum_channel_id") and sub.get("target_post_id"):
                            webhook_target_thread_id = sub.get("target_post_id")
                        elif sub.get("channel_id") and sub.get("thread_id"):
                            webhook_target_thread_id = sub.get("thread_id")
                        
                        send_success = await self._send_via_webhook(webhook_url, message_content, thread_id=webhook_target_thread_id)
                        if send_success:
                            latest_sent_id_for_this_sub = post_id
                            original_guild_subs = self.subscriptions_data.get(guild_id_str)
                            if original_guild_subs:
                                for original_sub_entry in original_guild_subs:
                                    if original_sub_entry.get("subscription_id") == sub.get("subscription_id"):
                                        original_sub_entry["last_known_post_id"] = latest_sent_id_for_this_sub
                                        needs_save = True
                                        log.debug(f"Updated last_known_post_id to {latest_sent_id_for_this_sub} for sub {sub.get('subscription_id')}")
                                        break 
                            await asyncio.sleep(1) 
                        else:
                            log.error(f"Failed to send new post via webhook for sub {sub.get('subscription_id')}. Will retry later.")
                            break 
                
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
        log.debug("Finished Safebooru new post check.")

    @check_new_posts.before_loop
    async def before_check_new_posts(self):
        await self.bot.wait_until_ready()
        log.info("SafebooruCog: `check_new_posts` loop is waiting for bot readiness...")
        if self.session is None or self.session.closed: 
            self.session = aiohttp.ClientSession()
            log.info("aiohttp ClientSession created before check_new_posts loop.")

    @safebooruwatch.command(name="add", description="Watch for new Safebooru posts with specific tags in a channel or thread.")
    @app_commands.describe(
        tags="The tags to search for (e.g., '1girl cat_ears').",
        channel="The parent channel for the subscription (and webhook). Must be a Forum Channel if using forum mode.",
        thread_target="Optional: Name or ID of a thread within the channel (for TextChannels only)."
    )
    @app_commands.checks.has_permissions(manage_guild=True) 
    async def safebooruwatch_add(self, interaction: discord.Interaction, tags: str, channel: typing.Union[discord.TextChannel, discord.ForumChannel], thread_target: typing.Optional[str] = None, post_title: typing.Optional[str] = None):
        """Adds a new Safebooru tag watch directly (Admin). For ForumChannels, post_title is used for the new forum post."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if isinstance(channel, discord.TextChannel) and post_title:
            await interaction.response.send_message("`post_title` is only applicable when the target channel is a Forum Channel.", ephemeral=True)
            return
        if isinstance(channel, discord.ForumChannel) and thread_target:
            await interaction.response.send_message("`thread_target` is only applicable when the target channel is a Text Channel. For Forum Channels, a new post (thread) will be created.", ephemeral=True)
            return

        response_message = await self._create_new_subscription(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            tags=tags,
            target_channel=channel,
            requested_thread_target=thread_target, 
            requested_post_title=post_title 
        )
        
        if interaction.response.is_done():
            await interaction.followup.send(response_message, ephemeral=True)
        else:
            await interaction.response.send_message(response_message, ephemeral=True)


    async def _create_new_subscription(self, guild_id: int, user_id: int, tags: str, 
                                       target_channel: typing.Union[discord.TextChannel, discord.ForumChannel], 
                                       requested_thread_target: typing.Optional[str] = None,
                                       requested_post_title: typing.Optional[str] = None,
                                       is_request_approval: bool = False,
                                       requester_mention: typing.Optional[str] = None) -> str:
        await asyncio.sleep(0) 

        actual_target_thread_id: typing.Optional[str] = None
        actual_target_thread_mention: str = ""
        actual_post_title = requested_post_title or f"Safebooru Watch: {tags[:50]}" 

        if isinstance(target_channel, discord.TextChannel):
            if requested_thread_target:
                found_thread: typing.Optional[discord.Thread] = None
                try:
                    if not target_channel.guild: 
                         return "Error: Guild context not found for text channel."
                    thread_as_obj = await target_channel.guild.fetch_channel(int(requested_thread_target))
                    if isinstance(thread_as_obj, discord.Thread) and thread_as_obj.parent_id == target_channel.id:
                        found_thread = thread_as_obj
                except (ValueError, discord.NotFound, discord.Forbidden): pass
                except Exception as e: log.error(f"Error fetching thread by ID '{requested_thread_target}': {e}")

                if not found_thread and hasattr(target_channel, 'threads'):
                    for t in target_channel.threads:
                        if t.name.lower() == requested_thread_target.lower():
                            found_thread = t; break
                
                if found_thread:
                    actual_target_thread_id = str(found_thread.id)
                    actual_target_thread_mention = found_thread.mention
                else:
                    return f"❌ Could not find an accessible thread named or with ID `{requested_thread_target}` in {target_channel.mention}."
        
        elif isinstance(target_channel, discord.ForumChannel):
            forum_post_initial_message = f"✨ **New Safebooru Watch Initialized!** ✨\nNow monitoring tags: `{tags}`"
            if is_request_approval and requester_mention:
                forum_post_initial_message += f"\n_Requested by: {requester_mention}_"
            
            try:
                if not target_channel.permissions_for(target_channel.guild.me).create_public_threads: 
                    return f"❌ I don't have permission to create posts/threads in the forum channel {target_channel.mention}."

                new_forum_post = await target_channel.create_thread(
                    name=actual_post_title,
                    content=forum_post_initial_message,
                    reason=f"SafebooruWatch subscription for tags: {tags}"
                )
                actual_target_thread_id = str(new_forum_post.thread.id) 
                actual_target_thread_mention = new_forum_post.thread.mention
                log.info(f"Created new forum post {new_forum_post.thread.id} for tags '{tags}' in forum {target_channel.id}")
            except discord.HTTPException as e:
                log.error(f"Failed to create forum post for tags '{tags}' in {target_channel.mention}: {e}")
                return f"❌ Failed to create a new post in forum {target_channel.mention}. Error: {e}"
            except Exception as e:
                log.exception(f"Unexpected error creating forum post for tags '{tags}' in {target_channel.mention}")
                return f"❌ An unexpected error occurred while creating the forum post."

        webhook_url = await self._get_or_create_webhook(target_channel)
        if not webhook_url:
            return f"❌ Failed to get/create webhook for {target_channel.mention}. Check permissions."

        initial_posts = await self._safebooru_logic("internal_initial_fetch", tags, pid_override=0, limit_override=1)
        last_known_post_id = 0
        if isinstance(initial_posts, list) and initial_posts:
            if isinstance(initial_posts[0], dict) and "id" in initial_posts[0]:
                 last_known_post_id = int(initial_posts[0]["id"])
            else: log.warning(f"Malformed post data for initial fetch (tags: '{tags}'): {initial_posts[0]}")
        elif isinstance(initial_posts, str): log.error(f"API error on initial fetch (tags: '{tags}'): {initial_posts}")

        guild_id_str = str(guild_id)
        subscription_id = str(uuid.uuid4())
        
        new_sub_data = {
            "subscription_id": subscription_id, "tags": tags.strip(),
            "webhook_url": webhook_url, "last_known_post_id": last_known_post_id,
            "added_by_user_id": str(user_id), "added_timestamp": discord.utils.utcnow().isoformat()
        }
        if isinstance(target_channel, discord.ForumChannel):
            new_sub_data["forum_channel_id"] = str(target_channel.id)
            new_sub_data["target_post_id"] = actual_target_thread_id 
            new_sub_data["post_title"] = actual_post_title
        else: 
            new_sub_data["channel_id"] = str(target_channel.id)
            new_sub_data["thread_id"] = actual_target_thread_id 

        if guild_id_str not in self.subscriptions_data:
            self.subscriptions_data[guild_id_str] = []
        
        for existing_sub in self.subscriptions_data[guild_id_str]:
            is_dup_tags = existing_sub.get("tags") == new_sub_data["tags"]
            is_dup_forum = isinstance(target_channel, discord.ForumChannel) and \
                           existing_sub.get("forum_channel_id") == new_sub_data.get("forum_channel_id") and \
                           existing_sub.get("target_post_id") == new_sub_data.get("target_post_id") 
            is_dup_text_chan = isinstance(target_channel, discord.TextChannel) and \
                               existing_sub.get("channel_id") == new_sub_data.get("channel_id") and \
                               existing_sub.get("thread_id") == new_sub_data.get("thread_id")
            if is_dup_tags and (is_dup_forum or is_dup_text_chan):
                return f"⚠️ A subscription for these tags in this exact location already exists (ID: `{existing_sub.get('subscription_id')}`)."

        self.subscriptions_data[guild_id_str].append(new_sub_data)
        self._save_subscriptions()

        target_desc = f"in {target_channel.mention}"
        if isinstance(target_channel, discord.ForumChannel) and actual_target_thread_mention:
            target_desc = f"in forum post {actual_target_thread_mention} within {target_channel.mention}"
        elif actual_target_thread_mention: 
            target_desc += f" (thread: {actual_target_thread_mention})"
        
        log.info(f"Subscription added: Guild {guild_id_str}, Tags '{tags}', Target {target_desc}, SubID {subscription_id}")
        return (f"✅ Watching for new posts with tags `{tags}` {target_desc}.\n"
                f"Initial latest post ID set to: {last_known_post_id}.\n"
                f"Subscription ID: `{subscription_id}`.")


    @safebooruwatch.command(name="request", description="Request a new Safebooru tag watch (requires moderator approval).")
    @app_commands.describe(
        tags="The tags you want to watch.",
        forum_channel="The Forum Channel where a new post for this watch should be created.",
        post_title="Optional: A title for the new forum post (defaults to tags)."
    )
    async def safebooruwatch_request(self, interaction: discord.Interaction, tags: str, forum_channel: discord.ForumChannel, post_title: typing.Optional[str] = None):
        """Allows users to request a new Safebooru tag watch, creating a post in a ForumChannel upon approval."""
        if not interaction.guild_id or not interaction.user:
            await interaction.response.send_message("This command can only be used in a server by a user.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        guild_id_str = str(interaction.guild_id)
        request_id = str(uuid.uuid4())
        actual_post_title = post_title or f"Safebooru Watch: {tags[:50]}" 

        new_request = {
            "request_id": request_id,
            "requester_id": str(interaction.user.id),
            "requester_name": str(interaction.user),
            "requested_tags": tags.strip(),
            "target_forum_channel_id": str(forum_channel.id),
            "requested_post_title": actual_post_title,
            "status": "pending",
            "request_timestamp": discord.utils.utcnow().isoformat(),
            "moderator_id": None,
            "moderation_timestamp": None
        }

        if guild_id_str not in self.pending_requests_data:
            self.pending_requests_data[guild_id_str] = []
        
        self.pending_requests_data[guild_id_str].append(new_request)
        self._save_pending_requests()

        log.info(f"New Safebooru watch request: Guild {guild_id_str}, Requester {interaction.user} ({interaction.user.id}), Tags '{tags}', Forum {forum_channel.id}, ReqID {request_id}")
        
        mod_notification_message = (
            f"📝 New Safebooru watch request (ID: `{request_id}`) from {interaction.user.mention} for tags `{tags}` "
            f"targeting forum {forum_channel.mention} with title \"{actual_post_title}\".\n"
            f"Use `/safebooruwatch pending_list` or `/safebooruwatch approve_request request_id:{request_id}` / `/safebooruwatch reject_request request_id:{request_id}`."
        )
        log.info(f"Moderator alert (logged): {mod_notification_message}")

        await interaction.followup.send(
            f"✅ Your request to watch tags `{tags}` in forum {forum_channel.mention} (proposed title: \"{actual_post_title}\") has been submitted.\n"
            f"Request ID: `{request_id}`. It is now awaiting moderator approval."
        )

    @safebooruwatch.command(name="pending_list", description="Lists all pending Safebooru watch requests.")
    @app_commands.checks.has_permissions(manage_guild=True) 
    async def safebooruwatch_pending_list(self, interaction: discord.Interaction):
        """Displays a list of pending Safebooru watch requests."""
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id_str = str(interaction.guild_id)
        pending_reqs = [req for req in self.pending_requests_data.get(guild_id_str, []) if req.get("status") == "pending"]

        if not pending_reqs:
            await interaction.response.send_message("No pending Safebooru watch requests for this server.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Pending Safebooru Watch Requests for {interaction.guild.name}", color=discord.Color.orange())
        description_parts = []
        for req in pending_reqs:
            forum_channel_mention = f"<#{req.get('target_forum_channel_id', 'Unknown')}>"
            requester_name = req.get('requester_name', 'Unknown User')
            description_parts.append(
                f"**ID:** `{req.get('request_id')}`\n"
                f"  **Requester:** {requester_name} (`{req.get('requester_id')}`)\n"
                f"  **Tags:** `{req.get('requested_tags')}`\n"
                f"  **Target Forum:** {forum_channel_mention}\n"
                f"  **Proposed Title:** \"{req.get('requested_post_title')}\"\n"
                f"  **Requested:** {discord.utils.format_dt(discord.utils.parse_isoformat(req.get('request_timestamp')), style='R') if req.get('request_timestamp') else 'Unknown time'}\n"
                f"---"
            )
        
        full_description = "\n".join(description_parts)
        if len(full_description) > 4096: 
            await interaction.response.send_message("Too many pending requests to display. Please approve/reject some.", ephemeral=True)
        else:
            embed.description = full_description
            await interaction.response.send_message(embed=embed, ephemeral=True)


    @safebooruwatch.command(name="approve_request", description="Approves a pending Safebooru watch request.")
    @app_commands.describe(request_id="The ID of the request to approve.")
    @app_commands.checks.has_permissions(manage_guild=True) 
    async def safebooruwatch_approve_request(self, interaction: discord.Interaction, request_id: str):
        """Approves a pending Safebooru watch request."""
        if not interaction.guild_id or not interaction.user:
            await interaction.response.send_message("This command can only be used in a server by a moderator.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild_id_str = str(interaction.guild_id)
        
        request_to_approve = None
        req_index = -1

        guild_pending_requests = self.pending_requests_data.get(guild_id_str, [])
        for i, req in enumerate(guild_pending_requests):
            if req.get("request_id") == request_id and req.get("status") == "pending":
                request_to_approve = req
                req_index = i
                break
        
        if not request_to_approve:
            await interaction.followup.send(f"❌ Pending request ID `{request_id}` not found or already processed.", ephemeral=True)
            return

        target_forum_channel_id = request_to_approve.get("target_forum_channel_id")
        target_forum_channel = None
        if target_forum_channel_id:
            try:
                target_forum_channel = await interaction.guild.fetch_channel(int(target_forum_channel_id))
                if not isinstance(target_forum_channel, discord.ForumChannel):
                    await interaction.followup.send(f"❌ Target channel ID `{target_forum_channel_id}` is not a Forum Channel.", ephemeral=True)
                    return
            except (discord.NotFound, discord.Forbidden, ValueError):
                await interaction.followup.send(f"❌ Could not find or access the target forum channel (ID: {target_forum_channel_id}).", ephemeral=True)
                return
        
        if not target_forum_channel: 
            await interaction.followup.send(f"❌ Target forum channel not resolved for request `{request_id}`.", ephemeral=True)
            return

        creation_response = await self._create_new_subscription(
            guild_id=interaction.guild_id,
            user_id=int(request_to_approve["requester_id"]), 
            tags=request_to_approve["requested_tags"],
            target_channel=target_forum_channel, 
            requested_post_title=request_to_approve["requested_post_title"],
            is_request_approval=True, 
            requester_mention=f"<@{request_to_approve['requester_id']}>"
        )

        if creation_response.startswith("✅"):
            request_to_approve["status"] = "approved"
            request_to_approve["moderator_id"] = str(interaction.user.id)
            request_to_approve["moderation_timestamp"] = discord.utils.utcnow().isoformat()
            self.pending_requests_data[guild_id_str][req_index] = request_to_approve
            self._save_pending_requests()
            
            await interaction.followup.send(f"✅ Request ID `{request_id}` approved. {creation_response}", ephemeral=True)
            
            try:
                requester = await self.bot.fetch_user(int(request_to_approve["requester_id"]))
                if requester:
                    await requester.send(
                        f"🎉 Your Safebooru watch request (ID: `{request_id}`) for tags `{request_to_approve['requested_tags']}` "
                        f"in server `{interaction.guild.name}` has been **approved** by {interaction.user.mention}!\n"
                        f"The subscription details: {creation_response.replace('Subscription ID:', 'New Subscription ID:')}" 
                    )
            except Exception as e:
                log.error(f"Failed to notify requester {request_to_approve['requester_id']} about approval: {e}")
        else:
            await interaction.followup.send(f"❌ Failed to approve request `{request_id}`. Subscription creation failed: {creation_response}", ephemeral=True)


    @safebooruwatch.command(name="reject_request", description="Rejects a pending Safebooru watch request.")
    @app_commands.describe(request_id="The ID of the request to reject.", reason="Optional reason for rejection.")
    @app_commands.checks.has_permissions(manage_guild=True) 
    async def safebooruwatch_reject_request(self, interaction: discord.Interaction, request_id: str, reason: typing.Optional[str] = None):
        """Rejects a pending Safebooru watch request."""
        if not interaction.guild_id or not interaction.user:
            await interaction.response.send_message("This command can only be used in a server by a moderator.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild_id_str = str(interaction.guild_id)

        request_to_reject = None
        req_index = -1
        guild_pending_requests = self.pending_requests_data.get(guild_id_str, [])
        for i, req in enumerate(guild_pending_requests):
            if req.get("request_id") == request_id and req.get("status") == "pending":
                request_to_reject = req
                req_index = i
                break
        
        if not request_to_reject:
            await interaction.followup.send(f"❌ Pending request ID `{request_id}` not found or already processed.", ephemeral=True)
            return

        request_to_reject["status"] = "rejected"
        request_to_reject["moderator_id"] = str(interaction.user.id)
        request_to_reject["moderation_timestamp"] = discord.utils.utcnow().isoformat()
        request_to_reject["rejection_reason"] = reason
        self.pending_requests_data[guild_id_str][req_index] = request_to_reject
        self._save_pending_requests()

        await interaction.followup.send(f"🗑️ Request ID `{request_id}` has been rejected.", ephemeral=True)

        try:
            requester = await self.bot.fetch_user(int(request_to_reject["requester_id"]))
            if requester:
                rejection_msg = (
                    f"😥 Your Safebooru watch request (ID: `{request_id}`) for tags `{request_to_reject['requested_tags']}` "
                    f"in server `{interaction.guild.name}` has been **rejected** by {interaction.user.mention}."
                )
                if reason:
                    rejection_msg += f"\nReason: {reason}"
                await requester.send(rejection_msg)
        except Exception as e:
            log.error(f"Failed to notify requester {request_to_reject['requester_id']} about rejection: {e}")


    @safebooruwatch.command(name="list", description="List active Safebooru tag watches for this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def safebooruwatch_list(self, interaction: discord.Interaction):
        """Lists all active Safebooru tag watch subscriptions for the current server."""
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id_str = str(interaction.guild_id)
        guild_subs = self.subscriptions_data.get(guild_id_str, [])

        if not guild_subs:
            await interaction.response.send_message("No active Safebooru tag watches for this server.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Active Safebooru Tag Watches for {interaction.guild.name}", color=discord.Color.blue())
        
        description_parts = []
        for sub in guild_subs:
            forum_channel_id = sub.get('forum_channel_id')
            target_post_id = sub.get('target_post_id') 
            channel_id = sub.get('channel_id')
            thread_id = sub.get('thread_id') 
            target_location = ""

            guild = interaction.guild 
            if not guild:
                target_location = "Error: Guild context lost for this subscription."
            elif forum_channel_id and target_post_id:
                forum_mention = f"<#{forum_channel_id}>"
                try:
                    post_thread_obj = await guild.fetch_channel(int(target_post_id))
                    if isinstance(post_thread_obj, discord.Thread):
                        target_location = f"Forum Post {post_thread_obj.mention} (`{post_thread_obj.name}`) in Forum {forum_mention}"
                    else:
                        target_location = f"Forum Post <#{target_post_id}> (Not a thread object) in Forum {forum_mention}"
                except (discord.NotFound, discord.Forbidden, ValueError):
                    target_location = f"Forum Post <#{target_post_id}> (Not found or no access) in Forum {forum_mention}"
                except Exception as e:
                    log.warning(f"Error fetching forum post thread {target_post_id} for list command: {e}")
                    target_location = f"Forum Post <#{target_post_id}> (Error fetching name) in Forum {forum_mention}"
            elif channel_id:
                target_location = f"<#{channel_id}>"
                if thread_id:
                    try:
                        thread_obj = await guild.fetch_channel(int(thread_id))
                        if isinstance(thread_obj, discord.Thread):
                            target_location += f" (Thread: {thread_obj.mention} `{thread_obj.name}`)"
                        else:
                            target_location += f" (Thread ID: `{thread_id}` - Not a thread object)"
                    except (discord.NotFound, discord.Forbidden, ValueError):
                        target_location += f" (Thread ID: `{thread_id}` - Not found or no access)"
                    except Exception as e:
                        log.warning(f"Error fetching thread {thread_id} for list command: {e}")
                        target_location += f" (Thread ID: `{thread_id}` - Error fetching name)"
            else:
                target_location = "Unknown Target (Missing channel/forum info)"

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
        
        if len(full_description) > 4096:
            await interaction.response.send_message("Too many subscriptions to display in one message. This will be improved later.", ephemeral=True)
        else:
            embed.description = full_description
            await interaction.response.send_message(embed=embed, ephemeral=True)


    @safebooruwatch.command(name="remove", description="Stop watching for new Safebooru posts using a subscription ID.")
    @app_commands.describe(subscription_id="The ID of the subscription to remove (get from 'list' command).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def safebooruwatch_remove(self, interaction: discord.Interaction, subscription_id: str):
        """Removes a Safebooru tag watch subscription by its ID."""
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id_str = str(interaction.guild_id)
        guild_subs = self.subscriptions_data.get(guild_id_str, [])
        
        removed_sub_info = None
        new_subs_list = []
        found = False
        for sub_entry in guild_subs: 
            if sub_entry.get("subscription_id") == subscription_id:
                channel_id_for_removed = sub_entry.get('channel_id')
                thread_id_for_removed = sub_entry.get('thread_id')
                forum_channel_id_for_removed = sub_entry.get('forum_channel_id')
                target_post_id_for_removed = sub_entry.get('target_post_id')
                
                target_desc = "Unknown Location"
                if forum_channel_id_for_removed and target_post_id_for_removed:
                    target_desc = f"forum post in <#{forum_channel_id_for_removed}>"
                elif channel_id_for_removed:
                     target_desc = f"<#{channel_id_for_removed}>"
                     if thread_id_for_removed:
                         target_desc += f" (Thread ID: {thread_id_for_removed})"

                removed_sub_info = f"tags `{sub_entry.get('tags')}` in {target_desc}"
                found = True
                log.info(f"Removing Safebooru watch: Guild {guild_id_str}, Sub ID {subscription_id}")
            else:
                new_subs_list.append(sub_entry)
        
        if not found:
            await interaction.response.send_message(f"❌ Subscription ID `{subscription_id}` not found for this server.", ephemeral=True)
            return

        if not new_subs_list: 
            del self.subscriptions_data[guild_id_str]
        else:
            self.subscriptions_data[guild_id_str] = new_subs_list
        
        self._save_subscriptions()
        await interaction.response.send_message(f"✅ Successfully removed Safebooru watch for {removed_sub_info} (ID: `{subscription_id}`).", ephemeral=True)


async def setup(bot: commands.Bot): 
    await bot.add_cog(SafebooruCog(bot))
    log.info("SafebooruCog added to bot.")
