import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import re
import secrets
import datetime # Added for timezone.utc
from typing import Literal, Optional, List, Dict, Any
import asyncio # For sleep
import aiohttp # For API calls
import requests.utils # For url encoding gitlab project path

# Assuming settings_manager is in the parent directory
# Adjust the import path if your project structure is different
try:
    from .. import settings_manager # If cogs is a package
except ImportError:
    import settings_manager # If run from the root or cogs is not a package

log = logging.getLogger(__name__)

# Helper to parse repo URL and determine platform
def parse_repo_url(url: str) -> tuple[Optional[str], Optional[str]]:
    """Parses a Git repository URL to extract platform and a simplified repo identifier."""
    # Changed from +? to + for the repo name part for robustness, though unlikely to be the issue for simple URLs.
    github_match = re.match(r"https^(?:https?://)?(?:www\.)?github\.com/([\w.-]+/[\w.-]+)(?:\.git)?/?$", url)
    if github_match:
        return "github", github_match.group(1)

    gitlab_match = re.match(r"^(?:https?://)?(?:www\.)?gitlab\.com/([\w.-]+(?:/[\w.-]+)+)(?:\.git)?/?$", url)
    if gitlab_match:
        return "gitlab", gitlab_match.group(1)
    return None, None


class GitMonitorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_repositories_task.start()
        log.info("GitMonitorCog initialized and polling task started.")

    def cog_unload(self):
        self.poll_repositories_task.cancel()
        log.info("GitMonitorCog unloaded and polling task cancelled.")

    @tasks.loop(minutes=5.0) # Default, can be adjusted or made dynamic later
    async def poll_repositories_task(self):
        log.debug("Git repository polling task running...")
        try:
            repos_to_poll = await settings_manager.get_all_repositories_for_polling()
            if not repos_to_poll:
                log.debug("No repositories configured for polling.")
                return

            log.info(f"Found {len(repos_to_poll)} repositories to poll.")

            for repo_config in repos_to_poll:
                repo_id = repo_config['id']
                guild_id = repo_config['guild_id']
                repo_url = repo_config['repository_url']
                platform = repo_config['platform']
                channel_id = repo_config['notification_channel_id']
                target_branch = repo_config['target_branch'] # Get the target branch
                last_sha = repo_config['last_polled_commit_sha']
                # polling_interval = repo_config['polling_interval_minutes'] # Use this if intervals are dynamic per repo

                log.debug(f"Polling {platform} repo: {repo_url} (Branch: {target_branch or 'default'}) (ID: {repo_id}) for guild {guild_id}")

                new_commits_data: List[Dict[str, Any]] = []
                latest_fetched_sha = last_sha

                try:
                    async with aiohttp.ClientSession(headers={"User-Agent": "DiscordBot/1.0"}) as session:
                        if platform == "github":
                            # GitHub API: GET /repos/{owner}/{repo}/commits
                            # We need to parse owner/repo from repo_url
                            _, owner_repo_path = parse_repo_url(repo_url) # e.g. "user/repo"
                            if owner_repo_path:
                                api_url = f"https://api.github.com/repos/{owner_repo_path}/commits"
                                params = {"per_page": 10} # Fetch up to 10 recent commits
                                if target_branch:
                                    params["sha"] = target_branch # GitHub uses 'sha' for branch/tag/commit SHA
                                # No 'since_sha' for GitHub commits list. Manual filtering after fetch.
                                
                                async with session.get(api_url, params=params) as response:
                                    if response.status == 200:
                                        commits_payload = await response.json()
                                        temp_new_commits = []
                                        for commit_item in reversed(commits_payload): # Process oldest first
                                            if commit_item['sha'] == last_sha:
                                                temp_new_commits = [] # Clear previous if we found the last one
                                                continue
                                            temp_new_commits.append(commit_item)
                                        
                                        if temp_new_commits:
                                            new_commits_data = temp_new_commits
                                            latest_fetched_sha = new_commits_data[-1]['sha']
                                    elif response.status == 403: # Rate limit
                                        log.warning(f"GitHub API rate limit hit for {repo_url}. Headers: {response.headers}")
                                        # Consider increasing loop wait time or specific backoff for this repo
                                    elif response.status == 404:
                                        log.error(f"Repository {repo_url} not found on GitHub (404). Consider removing or marking as invalid.")
                                    else:
                                        log.error(f"Error fetching GitHub commits for {repo_url}: {response.status} - {await response.text()}")

                        elif platform == "gitlab":
                            # GitLab API: GET /projects/{id}/repository/commits
                            # We need project ID or URL-encoded path.
                            _, project_path = parse_repo_url(repo_url) # e.g. "group/subgroup/project"
                            if project_path:
                                encoded_project_path = requests.utils.quote(project_path, safe='')
                                api_url = f"https://gitlab.com/api/v4/projects/{encoded_project_path}/repository/commits"
                                params = {"per_page": 10}
                                if target_branch:
                                    params["ref_name"] = target_branch # GitLab uses 'ref_name' for branch/tag
                                # No 'since_sha' for GitLab. Manual filtering.

                                async with session.get(api_url, params=params) as response:
                                    if response.status == 200:
                                        commits_payload = await response.json()
                                        temp_new_commits = []
                                        for commit_item in reversed(commits_payload):
                                            if commit_item['id'] == last_sha:
                                                temp_new_commits = []
                                                continue
                                            temp_new_commits.append(commit_item)
                                        
                                        if temp_new_commits:
                                            new_commits_data = temp_new_commits
                                            latest_fetched_sha = new_commits_data[-1]['id']
                                    elif response.status == 403:
                                        log.warning(f"GitLab API rate limit hit for {repo_url}. Headers: {response.headers}")
                                    elif response.status == 404:
                                        log.error(f"Repository {repo_url} not found on GitLab (404).")
                                    else:
                                        log.error(f"Error fetching GitLab commits for {repo_url}: {response.status} - {await response.text()}")
                except aiohttp.ClientError as ce:
                    log.error(f"AIOHTTP client error polling {repo_url}: {ce}")
                except Exception as ex:
                    log.exception(f"Generic error polling {repo_url}: {ex}")


                if new_commits_data:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        for commit_item_data in new_commits_data:
                            embed = None
                            if platform == "github":
                                commit_sha = commit_item_data.get('sha', 'N/A')
                                commit_id_short = commit_sha[:7]
                                commit_data = commit_item_data.get('commit', {})
                                commit_msg = commit_data.get('message', 'No message.')
                                commit_url = commit_item_data.get('html_url', '#')
                                author_info = commit_data.get('author', {}) # Committer info is also available
                                author_name = author_info.get('name', 'Unknown Author')
                                # Branch information is not directly available in this specific commit object from /commits endpoint.
                                # It's part of the push event or needs to be inferred/fetched differently for polling.
                                # For polling, we typically monitor a specific branch, or assume default.
                                # Verification status
                                verification = commit_data.get('verification', {})
                                verified_status = "Verified" if verification.get('verified') else "Unverified"
                                if verification.get('reason') and verification.get('reason') != 'unsigned':
                                    verified_status += f" ({verification.get('reason')})"
                                
                                # Files changed and stats require another API call per commit: GET /repos/{owner}/{repo}/commits/{sha}
                                # This is too API intensive for a simple polling loop.
                                # We will omit detailed file stats for polled GitHub commits for now.
                                files_changed_str = "File stats not fetched for polled commits."

                                embed = discord.Embed(
                                    title=f"New Commit in {repo_url}",
                                    description=commit_msg.splitlines()[0], # First line
                                    color=discord.Color.blue(),
                                    url=commit_url
                                )
                                embed.set_author(name=author_name)
                                embed.add_field(name="Commit", value=f"[`{commit_id_short}`]({commit_url})", inline=True)
                                embed.add_field(name="Verification", value=verified_status, inline=True)
                                # embed.add_field(name="Branch", value="default (polling)", inline=True) # Placeholder
                                embed.add_field(name="Changes", value=files_changed_str, inline=False)

                            elif platform == "gitlab":
                                commit_id = commit_item_data.get('id', 'N/A')
                                commit_id_short = commit_item_data.get('short_id', commit_id[:7])
                                commit_msg = commit_item_data.get('title', 'No message.') # GitLab uses 'title' for first line
                                commit_url = commit_item_data.get('web_url', '#')
                                author_name = commit_item_data.get('author_name', 'Unknown Author')
                                # Branch information is not directly in this commit object from /commits.
                                # It's part of the push event or needs to be inferred.
                                # GitLab commit stats (added/deleted lines) are in the commit details, not list.
                                files_changed_str = "File stats not fetched for polled commits."

                                embed = discord.Embed(
                                    title=f"New Commit in {repo_url}",
                                    description=commit_msg.splitlines()[0],
                                    color=discord.Color.orange(),
                                    url=commit_url
                                )
                                embed.set_author(name=author_name)
                                embed.add_field(name="Commit", value=f"[`{commit_id_short}`]({commit_url})", inline=True)
                                # embed.add_field(name="Branch", value="default (polling)", inline=True) # Placeholder
                                embed.add_field(name="Changes", value=files_changed_str, inline=False)
                            
                            if embed:
                                try:
                                    await channel.send(embed=embed)
                                    log.info(f"Sent polled notification for commit {commit_id_short} in {repo_url} to channel {channel_id}")
                                except discord.Forbidden:
                                    log.error(f"Missing permissions to send message in channel {channel_id} for guild {guild_id}")
                                except discord.HTTPException as dhe:
                                    log.error(f"Discord HTTP error sending message for {repo_url}: {dhe}")
                    else:
                        log.warning(f"Channel {channel_id} not found for guild {guild_id} for repo {repo_url}")
                
                # Update polling status in DB
                if latest_fetched_sha != last_sha or not new_commits_data : # Update if new sha or just to update timestamp
                    await settings_manager.update_repository_polling_status(repo_id, latest_fetched_sha, datetime.datetime.now(datetime.timezone.utc))
                
                # Small delay between processing each repo to be nice to APIs
                await asyncio.sleep(2) # 2 seconds delay

        except Exception as e:
            log.exception("Error occurred during repository polling task:", exc_info=e)

    @poll_repositories_task.before_loop
    async def before_poll_repositories_task(self):
        await self.bot.wait_until_ready()
        log.info("Polling task is waiting for bot to be ready...")

    gitlistener_group = app_commands.Group(name="gitlistener", description="Manage Git repository monitoring.")

    @gitlistener_group.command(name="add", description="Add a repository to monitor for commits.")
    @app_commands.describe(
        repository_url="The full URL of the GitHub or GitLab repository (e.g., https://github.com/user/repo).",
        channel="The channel where commit notifications should be sent.",
        monitoring_method="Choose 'webhook' for real-time (requires repo admin rights) or 'poll' for periodic checks.",
        branch="The specific branch to monitor (for 'poll' method, defaults to main/master if not specified)."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_repository(self, interaction: discord.Interaction,
                             repository_url: str,
                             channel: discord.TextChannel,
                             monitoring_method: Literal['webhook', 'poll'],
                             branch: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        cleaned_repository_url = repository_url.strip() # Strip whitespace

        if monitoring_method == 'poll' and not branch:
            log.info(f"Branch not specified for polling method for {cleaned_repository_url}. Will use default in polling task or API default.")
            # If branch is None, the polling task will attempt to use the repo's default branch.
            pass

        platform, repo_identifier = parse_repo_url(cleaned_repository_url) # Use cleaned URL
        if not platform or not repo_identifier:
            await interaction.followup.send(f"Invalid repository URL: `{repository_url}`. Please provide a valid GitHub or GitLab URL (e.g., https://github.com/user/repo).", ephemeral=True)
            return

        guild_id = interaction.guild_id
        added_by_user_id = interaction.user.id
        notification_channel_id = channel.id

        # Check if this exact repo and channel combination already exists
        existing_config = await settings_manager.get_monitored_repository_by_url(guild_id, repository_url, notification_channel_id)
        if existing_config:
            await interaction.followup.send(f"This repository ({repository_url}) is already being monitored in {channel.mention}.", ephemeral=True)
            return

        webhook_secret = None
        db_repo_id = None
        reply_message = ""

        if monitoring_method == 'webhook':
            webhook_secret = secrets.token_hex(32)
            # The API server needs the bot's domain. This should be configured.
            # For now, we'll use a placeholder.
            # TODO: Fetch API base URL from config or bot instance
            api_base_url = getattr(self.bot, 'config', {}).get('API_BASE_URL', 'YOUR_API_DOMAIN_HERE.com')
            if api_base_url == 'YOUR_API_DOMAIN_HERE.com':
                 log.warning("API_BASE_URL not configured for webhook URL generation. Using placeholder.")


            db_repo_id = await settings_manager.add_monitored_repository(
                guild_id=guild_id, repository_url=cleaned_repository_url, platform=platform, # Use cleaned URL
                monitoring_method='webhook', notification_channel_id=notification_channel_id,
                added_by_user_id=added_by_user_id, webhook_secret=webhook_secret, target_branch=None # Branch not used for webhooks
            )
            if db_repo_id:
                payload_url = f"https://{api_base_url}/webhook/{platform}/{db_repo_id}"
                reply_message = (
                    f"Webhook monitoring for `{repo_identifier}` ({platform.capitalize()}) added for {channel.mention}!\n\n"
                    f"**Action Required:**\n"
                    f"1. Go to your repository's settings: `{cleaned_repository_url}/settings/hooks` (GitHub) or `{cleaned_repository_url}/-/hooks` (GitLab).\n"
                    f"2. Add a new webhook.\n"
                    f"   - **Payload URL:** `{payload_url}`\n"
                    f"   - **Content type:** `application/json`\n"
                    f"   - **Secret:** `{webhook_secret}`\n"
                    f"   - **Events:** Select 'Just the push event' (GitHub) or 'Push events' (GitLab).\n"
                    f"3. Click 'Add webhook'."
                )
            else:
                reply_message = "Failed to add repository for webhook monitoring. It might already exist or there was a database error."

        elif monitoring_method == 'poll':
            # For polling, we might want to fetch the latest commit SHA now to avoid initial old notifications
            # This is a placeholder; actual fetching needs platform-specific API calls
            initial_sha = None # TODO: Implement initial SHA fetch if desired
            db_repo_id = await settings_manager.add_monitored_repository(
                guild_id=guild_id, repository_url=cleaned_repository_url, platform=platform, # Use cleaned URL
                monitoring_method='poll', notification_channel_id=notification_channel_id,
                added_by_user_id=added_by_user_id, target_branch=branch, # Pass the branch for polling
                last_polled_commit_sha=initial_sha
            )
            if db_repo_id:
                branch_info = f"on branch `{branch}`" if branch else "on the default branch"
                reply_message = (
                    f"Polling monitoring for `{repo_identifier}` ({platform.capitalize()}) {branch_info} added for {channel.mention}.\n"
                    f"The bot will check for new commits periodically (around every 5-15 minutes)."
                )
            else:
                reply_message = "Failed to add repository for polling. It might already exist or there was a database error."

        if db_repo_id:
            await interaction.followup.send(reply_message, ephemeral=True)
        else:
            await interaction.followup.send(reply_message or "An unexpected error occurred.", ephemeral=True)


    @gitlistener_group.command(name="remove", description="Remove a repository from monitoring.")
    @app_commands.describe(
        repository_url="The full URL of the repository to remove.",
        channel="The channel it's sending notifications to."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remove_repository(self, interaction: discord.Interaction, repository_url: str, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        notification_channel_id = channel.id

        platform, repo_identifier = parse_repo_url(repository_url)
        if not platform: # repo_identifier can be None if URL is valid but not parsable to simple form
            await interaction.followup.send("Invalid repository URL provided.", ephemeral=True)
            return

        success = await settings_manager.remove_monitored_repository(guild_id, repository_url, notification_channel_id)

        if success:
            await interaction.followup.send(
                f"Successfully removed monitoring for `{repository_url}` from {channel.mention}.\n"
                f"If this was a webhook, remember to also delete the webhook from the repository settings on {platform.capitalize()}.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(f"Could not find a monitoring setup for `{repository_url}` in {channel.mention} to remove, or a database error occurred.", ephemeral=True)

    @gitlistener_group.command(name="list", description="List repositories currently being monitored in this server.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_repositories(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        monitored_repos = await settings_manager.list_monitored_repositories_for_guild(guild_id)

        if not monitored_repos:
            await interaction.followup.send("No repositories are currently being monitored in this server.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Monitored Repositories for {interaction.guild.name}", color=discord.Color.blue())
        
        description_lines = []
        for repo in monitored_repos:
            channel = self.bot.get_channel(repo['notification_channel_id'])
            channel_mention = channel.mention if channel else f"ID: {repo['notification_channel_id']}"
            method = repo['monitoring_method'].capitalize()
            platform = repo['platform'].capitalize()
            
            # Attempt to get a cleaner repo name if possible
            _, repo_name_simple = parse_repo_url(repo['repository_url'])
            display_name = repo_name_simple if repo_name_simple else repo['repository_url']

            description_lines.append(
                f"**[{display_name}]({repo['repository_url']})**\n"
                f"- Platform: {platform}\n"
                f"- Method: {method}\n"
                f"- Channel: {channel_mention}\n"
                f"- DB ID: `{repo['id']}`"
            )
        
        embed.description = "\n\n".join(description_lines)
        if len(embed.description) > 4000 : # Discord embed description limit
            embed.description = embed.description[:3990] + "\n... (list truncated)"


        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    # Ensure settings_manager's pools are set if this cog is loaded after bot's setup_hook
    # This is more of a safeguard; ideally, pools are set before cogs are loaded.
    if settings_manager and not getattr(settings_manager, '_active_pg_pool', None):
        log.warning("GitMonitorCog: settings_manager pools might not be set. Attempting to ensure they are via bot instance.")
        # This relies on bot having pg_pool and redis_pool attributes set by its setup_hook
        # settings_manager.set_bot_pools(getattr(bot, 'pg_pool', None), getattr(bot, 'redis_pool', None))

    await bot.add_cog(GitMonitorCog(bot))
    log.info("GitMonitorCog added to bot.")
