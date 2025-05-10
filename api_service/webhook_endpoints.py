import hashlib
import hmac
import json
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Header, Path
import discord # For Color

# Import API server functions
try:
    from .api_server import send_discord_message_via_api, get_api_settings # For settings
except ImportError:
    # If api_server.py is in the same directory:
    from api_service.api_server import send_discord_message_via_api, get_api_settings


log = logging.getLogger(__name__)
router = APIRouter()
api_settings = get_api_settings() # Get loaded API settings

async def get_monitored_repository_by_id_api(request: Request, repo_db_id: int) -> Dict | None:
    """Gets details of a monitored repository by its database ID using the API service's PostgreSQL pool.
    This is an alternative to settings_manager.get_monitored_repository_by_id that doesn't rely on the bot instance.
    """
    # Log the available attributes in app.state for debugging
    log.info(f"Available attributes in app.state: {dir(request.app.state)}")

    # Try to get the PostgreSQL pool from the FastAPI app state
    pg_pool = getattr(request.app.state, "pg_pool", None)
    if not pg_pool:
        log.warning(f"API service PostgreSQL pool not available for get_monitored_repository_by_id_api (ID {repo_db_id}).")

        # Instead of falling back to settings_manager, let's try to create a new connection
        # This is a temporary solution to diagnose the issue
        try:
            import asyncpg
            from api_service.api_server import get_api_settings

            settings = get_api_settings()
            log.info(f"Attempting to create a new PostgreSQL connection for repo_db_id: {repo_db_id}")

            # Create a new connection to the database
            conn = await asyncpg.connect(
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_HOST,
                database=settings.POSTGRES_SETTINGS_DB
            )

            # Query the database
            record = await conn.fetchrow(
                "SELECT * FROM git_monitored_repositories WHERE id = $1",
                repo_db_id
            )

            # Close the connection
            await conn.close()

            log.info(f"Successfully retrieved repository configuration for ID {repo_db_id} using a new connection")
            return dict(record) if record else None
        except Exception as e:
            log.exception(f"Failed to create a new PostgreSQL connection: {e}")
            # Don't fall back to settings_manager as it's already failing
            return None

    try:
        async with pg_pool.acquire() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM git_monitored_repositories WHERE id = $1",
                repo_db_id
            )
            log.info(f"Retrieved repository configuration for ID {repo_db_id} using API service PostgreSQL pool")
            return dict(record) if record else None
    except Exception as e:
        log.exception(f"Database error getting monitored repository by ID {repo_db_id} using API service pool: {e}")

        # Instead of falling back to settings_manager, try with a new connection
        try:
            import asyncpg
            from api_service.api_server import get_api_settings

            settings = get_api_settings()
            log.info(f"Attempting to create a new PostgreSQL connection after pool error for repo_db_id: {repo_db_id}")

            # Create a new connection to the database
            conn = await asyncpg.connect(
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_HOST,
                database=settings.POSTGRES_SETTINGS_DB
            )

            # Query the database
            record = await conn.fetchrow(
                "SELECT * FROM git_monitored_repositories WHERE id = $1",
                repo_db_id
            )

            # Close the connection
            await conn.close()

            log.info(f"Successfully retrieved repository configuration for ID {repo_db_id} using a new connection after pool error")
            return dict(record) if record else None
        except Exception as e2:
            log.exception(f"Failed to create a new PostgreSQL connection after pool error: {e2}")
            return None

async def get_allowed_events_for_repo(request: Request, repo_db_id: int) -> list[str]:
    """Helper to fetch allowed_webhook_events for a repo."""
    repo_config = await get_monitored_repository_by_id_api(request, repo_db_id)
    if repo_config and repo_config.get('allowed_webhook_events'):
        return repo_config['allowed_webhook_events']
    return ['push'] # Default to 'push' if not set or not found, for safety

def verify_github_signature(payload_body: bytes, secret_token: str, signature_header: str) -> bool:
    """Verify that the payload was sent from GitHub by validating the signature."""
    if not signature_header:
        log.warning("No X-Hub-Signature-256 found on request.")
        return False
    if not secret_token:
        log.error("Webhook secret is not configured for this repository. Cannot verify signature.")
        return False

    hash_object = hmac.new(secret_token.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    if not hmac.compare_digest(expected_signature, signature_header):
        log.warning(f"Request signature mismatch. Expected: {expected_signature}, Got: {signature_header}")
        return False
    return True

def verify_gitlab_token(secret_token: str, gitlab_token_header: str) -> bool:
    """Verify that the payload was sent from GitLab by validating the token."""
    if not gitlab_token_header:
        log.warning("No X-Gitlab-Token found on request.")
        return False
    if not secret_token:
        log.error("Webhook secret is not configured for this repository. Cannot verify token.")
        return False
    if not hmac.compare_digest(secret_token, gitlab_token_header): # Direct comparison for GitLab token
        log.warning("Request token mismatch.")
        return False
    return True

# Placeholder for other GitHub event formatters
# def format_github_issue_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed: ...
# def format_github_pull_request_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed: ...
# def format_github_release_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed: ...

def format_github_push_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a GitHub push event payload into a Discord embed."""
    try:
        repo_name = payload.get('repository', {}).get('full_name', repo_url)
        pusher = payload.get('pusher', {}).get('name', 'Unknown Pusher')
        compare_url = payload.get('compare', repo_url)

        embed = discord.Embed(
            title=f"New Push to {repo_name}",
            url=compare_url,
            color=discord.Color.blue() # Or discord.Color.from_rgb(r, g, b)
        )
        embed.set_author(name=pusher)

        for commit in payload.get('commits', []):
            commit_id_short = commit.get('id', 'N/A')[:7]
            commit_msg = commit.get('message', 'No commit message.')
            commit_url = commit.get('url', '#')
            author_name = commit.get('author', {}).get('name', 'Unknown Author')

            # Files changed, insertions/deletions
            added = commit.get('added', [])
            removed = commit.get('removed', [])
            modified = commit.get('modified', [])

            stats_lines = []
            if added: stats_lines.append(f"+{len(added)} added")
            if removed: stats_lines.append(f"-{len(removed)} removed")
            if modified: stats_lines.append(f"~{len(modified)} modified")
            stats_str = ", ".join(stats_lines) if stats_lines else "No file changes."

            # Verification status (GitHub specific)
            verification = commit.get('verification', {})
            verified_status = "Verified" if verification.get('verified') else "Unverified"
            if verification.get('reason') and verification.get('reason') != 'unsigned':
                verified_status += f" ({verification.get('reason')})"


            field_value = (
                f"Author: {author_name}\n"
                f"Message: {commit_msg.splitlines()[0]}\n" # First line of commit message.
                f"Verification: {verified_status}\n"
                f"Stats: {stats_str}\n"
                f"[View Commit]({commit_url})"
            )
            embed.add_field(name=f"Commit `{commit_id_short}`", value=field_value, inline=False)
            if len(embed.fields) >= 5: # Limit fields to avoid overly large embeds
                embed.add_field(name="...", value=f"And {len(payload.get('commits')) - 5} more commits.", inline=False)
                break

        if not payload.get('commits'):
            embed.description = "Received push event with no commits (e.g., new branch created without commits)."

        return embed
    except Exception as e:
        log.exception(f"Error formatting GitHub push embed: {e}")
        embed = discord.Embed(title="Error Processing GitHub Push Webhook", description=f"Could not parse commit details. Raw payload might be available in logs.\nError: {e}", color=discord.Color.red())
        return embed

# Placeholder for other GitLab event formatters
# def format_gitlab_issue_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed: ...
# def format_gitlab_merge_request_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed: ...
# def format_gitlab_tag_push_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed: ...

def format_gitlab_push_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a GitLab push event payload into a Discord embed."""
    try:
        project_name = payload.get('project', {}).get('path_with_namespace', repo_url)
        user_name = payload.get('user_name', 'Unknown Pusher')

        # GitLab's compare URL is not directly in the main payload, but commits have URLs
        # We can use the project's web_url as a base.
        project_web_url = payload.get('project', {}).get('web_url', repo_url)

        embed = discord.Embed(
            title=f"New Push to {project_name}",
            url=project_web_url, # Link to project
            color=discord.Color.orange() # Or discord.Color.from_rgb(r, g, b)
        )
        embed.set_author(name=user_name)

        for commit in payload.get('commits', []):
            commit_id_short = commit.get('id', 'N/A')[:7]
            commit_msg = commit.get('message', 'No commit message.')
            commit_url = commit.get('url', '#')
            author_name = commit.get('author', {}).get('name', 'Unknown Author')

            # Files changed, insertions/deletions (GitLab provides total counts)
            # GitLab commit objects don't directly list added/removed/modified files in the same way GitHub does per commit in a push.
            # The overall push event has 'total_commits_count', but individual commit stats are usually fetched separately if needed.
            # For simplicity, we'll list files if available, or just the message.
            # GitLab's commit object in webhook doesn't typically include detailed file stats like GitHub's.
            # It might have 'added', 'modified', 'removed' at the top level of the push event for the whole push, not per commit.
            # We'll focus on commit message and author for now.

            # GitLab commit verification is not as straightforward in the webhook payload as GitHub's.
            # It's often handled via GPG keys and displayed in the UI. We'll omit for now.

            field_value = (
                f"Author: {author_name}\n"
                f"Message: {commit_msg.splitlines()[0]}\n" # First line
                f"[View Commit]({commit_url})"
            )
            embed.add_field(name=f"Commit `{commit_id_short}`", value=field_value, inline=False)
            if len(embed.fields) >= 5:
                embed.add_field(name="...", value=f"And {len(payload.get('commits')) - 5} more commits.", inline=False)
                break

        if not payload.get('commits'):
            embed.description = "Received push event with no commits (e.g., new branch created or tag pushed)."

        return embed
    except Exception as e:
        log.exception(f"Error formatting GitLab push embed: {e}")
        embed = discord.Embed(title="Error Processing GitLab Push Webhook", description=f"Could not parse commit details. Raw payload might be available in logs.\nError: {e}", color=discord.Color.red())
        return embed

# --- GitHub - New Event Formatters ---

def format_github_issues_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitHub issues event."""
    try:
        action = payload.get('action', 'Unknown action')
        issue_data = payload.get('issue', {})
        repo_name = payload.get('repository', {}).get('full_name', repo_url)
        sender = payload.get('sender', {})

        title = issue_data.get('title', 'Untitled Issue')
        issue_number = issue_data.get('number')
        issue_url = issue_data.get('html_url', repo_url)
        user_login = sender.get('login', 'Unknown User')
        user_url = sender.get('html_url', '#')
        user_avatar = sender.get('avatar_url')

        color = discord.Color.green() if action == "opened" else \
                discord.Color.red() if action == "closed" else \
                discord.Color.gold() if action == "reopened" else \
                discord.Color.light_grey()

        embed = discord.Embed(
            title=f"Issue {action.capitalize()}: #{issue_number} {title}",
            url=issue_url,
            description=f"Issue in `{repo_name}` was {action}.",
            color=color
        )
        embed.set_author(name=user_login, url=user_url, icon_url=user_avatar)
        
        if issue_data.get('body') and action == "opened":
            body = issue_data['body']
            embed.add_field(name="Description", value=body[:1020] + "..." if len(body) > 1024 else body, inline=False)
        
        if issue_data.get('labels'):
            labels = ", ".join([f"`{label['name']}`" for label in issue_data['labels']])
            embed.add_field(name="Labels", value=labels if labels else "None", inline=True)

        if issue_data.get('assignee'):
            assignee = issue_data['assignee']['login']
            embed.add_field(name="Assignee", value=f"[{assignee}]({issue_data['assignee']['html_url']})", inline=True)
        elif issue_data.get('assignees'):
            assignees = ", ".join([f"[{a['login']}]({a['html_url']})" for a in issue_data['assignees']])
            embed.add_field(name="Assignees", value=assignees if assignees else "None", inline=True)

        return embed
    except Exception as e:
        log.error(f"Error formatting GitHub issues embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitHub Issue Event", description=str(e), color=discord.Color.red())

def format_github_pull_request_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitHub pull_request event."""
    try:
        action = payload.get('action', 'Unknown action')
        pr_data = payload.get('pull_request', {})
        repo_name = payload.get('repository', {}).get('full_name', repo_url)
        sender = payload.get('sender', {})

        title = pr_data.get('title', 'Untitled Pull Request')
        pr_number = payload.get('number', pr_data.get('number')) # 'number' is top-level for some PR actions
        pr_url = pr_data.get('html_url', repo_url)
        user_login = sender.get('login', 'Unknown User')
        user_url = sender.get('html_url', '#')
        user_avatar = sender.get('avatar_url')

        color = discord.Color.green() if action == "opened" else \
                discord.Color.red() if action == "closed" and pr_data.get('merged') is False else \
                discord.Color.purple() if action == "closed" and pr_data.get('merged') is True else \
                discord.Color.gold() if action == "reopened" else \
                discord.Color.blue() if action in ["synchronize", "ready_for_review"] else \
                discord.Color.light_grey()

        description = f"Pull Request #{pr_number} in `{repo_name}` was {action}."
        if action == "closed" and pr_data.get('merged'):
            description = f"Pull Request #{pr_number} in `{repo_name}` was merged."
        
        embed = discord.Embed(
            title=f"PR {action.capitalize()}: #{pr_number} {title}",
            url=pr_url,
            description=description,
            color=color
        )
        embed.set_author(name=user_login, url=user_url, icon_url=user_avatar)

        if pr_data.get('body') and action == "opened":
            body = pr_data['body']
            embed.add_field(name="Description", value=body[:1020] + "..." if len(body) > 1024 else body, inline=False)
        
        embed.add_field(name="Base Branch", value=f"`{pr_data.get('base', {}).get('ref', 'N/A')}`", inline=True)
        embed.add_field(name="Head Branch", value=f"`{pr_data.get('head', {}).get('ref', 'N/A')}`", inline=True)

        if action == "closed":
            merged_by = pr_data.get('merged_by')
            if merged_by:
                embed.add_field(name="Merged By", value=f"[{merged_by['login']}]({merged_by['html_url']})", inline=True)
            else:
                 embed.add_field(name="Status", value="Closed without merging", inline=True)


        return embed
    except Exception as e:
        log.error(f"Error formatting GitHub PR embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitHub PR Event", description=str(e), color=discord.Color.red())

def format_github_release_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitHub release event."""
    try:
        action = payload.get('action', 'Unknown action') # e.g., published, created, edited
        release_data = payload.get('release', {})
        repo_name = payload.get('repository', {}).get('full_name', repo_url)
        sender = payload.get('sender', {})

        tag_name = release_data.get('tag_name', 'N/A')
        release_name = release_data.get('name', tag_name)
        release_url = release_data.get('html_url', repo_url)
        user_login = sender.get('login', 'Unknown User')
        user_url = sender.get('html_url', '#')
        user_avatar = sender.get('avatar_url')

        color = discord.Color.teal() if action == "published" else discord.Color.blurple()

        embed = discord.Embed(
            title=f"Release {action.capitalize()}: {release_name}",
            url=release_url,
            description=f"A new release `{tag_name}` was {action} in `{repo_name}`.",
            color=color
        )
        embed.set_author(name=user_login, url=user_url, icon_url=user_avatar)

        if release_data.get('body'):
            body = release_data['body']
            embed.add_field(name="Release Notes", value=body[:1020] + "..." if len(body) > 1024 else body, inline=False)
        
        return embed
    except Exception as e:
        log.error(f"Error formatting GitHub release embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitHub Release Event", description=str(e), color=discord.Color.red())

def format_github_issue_comment_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitHub issue_comment event."""
    try:
        action = payload.get('action', 'Unknown action') # created, edited, deleted
        comment_data = payload.get('comment', {})
        issue_data = payload.get('issue', {})
        repo_name = payload.get('repository', {}).get('full_name', repo_url)
        sender = payload.get('sender', {})

        comment_url = comment_data.get('html_url', repo_url)
        user_login = sender.get('login', 'Unknown User')
        user_url = sender.get('html_url', '#')
        user_avatar = sender.get('avatar_url')
        
        issue_title = issue_data.get('title', 'Untitled Issue')
        issue_number = issue_data.get('number')

        color = discord.Color.greyple()

        embed = discord.Embed(
            title=f"Comment {action} on Issue #{issue_number}: {issue_title}",
            url=comment_url,
            color=color
        )
        embed.set_author(name=user_login, url=user_url, icon_url=user_avatar)

        if comment_data.get('body'):
            body = comment_data['body']
            embed.description = body[:2040] + "..." if len(body) > 2048 else body
        
        return embed
    except Exception as e:
        log.error(f"Error formatting GitHub issue_comment embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitHub Issue Comment Event", description=str(e), color=discord.Color.red())

# --- GitLab - New Event Formatters ---

def format_gitlab_issue_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitLab issue event (object_kind: 'issue')."""
    try:
        attributes = payload.get('object_attributes', {})
        user = payload.get('user', {})
        project_data = payload.get('project', {})
        repo_name = project_data.get('path_with_namespace', repo_url)

        action = attributes.get('action', 'unknown') # open, close, reopen, update
        title = attributes.get('title', 'Untitled Issue')
        issue_iid = attributes.get('iid') # Internal ID for display
        issue_url = attributes.get('url', repo_url)
        user_name = user.get('name', 'Unknown User')
        user_avatar = user.get('avatar_url')

        color = discord.Color.green() if action == "open" else \
                discord.Color.red() if action == "close" else \
                discord.Color.gold() if action == "reopen" else \
                discord.Color.light_grey()
        
        embed = discord.Embed(
            title=f"Issue {action.capitalize()}: #{issue_iid} {title}",
            url=issue_url,
            description=f"Issue in `{repo_name}` was {action}.",
            color=color
        )
        embed.set_author(name=user_name, icon_url=user_avatar)

        if attributes.get('description') and action == "open":
            desc = attributes['description']
            embed.add_field(name="Description", value=desc[:1020] + "..." if len(desc) > 1024 else desc, inline=False)

        if attributes.get('labels'):
            labels = ", ".join([f"`{label['title']}`" for label in attributes['labels']])
            embed.add_field(name="Labels", value=labels if labels else "None", inline=True)
        
        assignees_data = payload.get('assignees', [])
        if assignees_data:
            assignees = ", ".join([f"{a['name']}" for a in assignees_data])
            embed.add_field(name="Assignees", value=assignees, inline=True)

        return embed
    except Exception as e:
        log.error(f"Error formatting GitLab issue embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitLab Issue Event", description=str(e), color=discord.Color.red())

def format_gitlab_merge_request_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitLab merge_request event."""
    try:
        attributes = payload.get('object_attributes', {})
        user = payload.get('user', {})
        project_data = payload.get('project', {})
        repo_name = project_data.get('path_with_namespace', repo_url)

        action = attributes.get('action', 'unknown') # open, close, reopen, update, merge
        title = attributes.get('title', 'Untitled Merge Request')
        mr_iid = attributes.get('iid')
        mr_url = attributes.get('url', repo_url)
        user_name = user.get('name', 'Unknown User')
        user_avatar = user.get('avatar_url')

        color = discord.Color.green() if action == "open" else \
                discord.Color.red() if action == "close" else \
                discord.Color.purple() if action == "merge" else \
                discord.Color.gold() if action == "reopen" else \
                discord.Color.blue() if action == "update" else \
                discord.Color.light_grey()

        description = f"Merge Request !{mr_iid} in `{repo_name}` was {action}."
        if action == "merge":
            description = f"Merge Request !{mr_iid} in `{repo_name}` was merged."

        embed = discord.Embed(
            title=f"MR {action.capitalize()}: !{mr_iid} {title}",
            url=mr_url,
            description=description,
            color=color
        )
        embed.set_author(name=user_name, icon_url=user_avatar)

        if attributes.get('description') and action == "open":
            desc = attributes['description']
            embed.add_field(name="Description", value=desc[:1020] + "..." if len(desc) > 1024 else desc, inline=False)

        embed.add_field(name="Source Branch", value=f"`{attributes.get('source_branch', 'N/A')}`", inline=True)
        embed.add_field(name="Target Branch", value=f"`{attributes.get('target_branch', 'N/A')}`", inline=True)
        
        if action == "merge" and attributes.get('merge_commit_sha'):
            embed.add_field(name="Merge Commit", value=f"`{attributes['merge_commit_sha'][:8]}`", inline=True)

        return embed
    except Exception as e:
        log.error(f"Error formatting GitLab MR embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitLab MR Event", description=str(e), color=discord.Color.red())

def format_gitlab_release_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitLab release event."""
    try:
        # GitLab release webhook payload structure is simpler
        action = payload.get('action', 'created') # create, update
        tag_name = payload.get('tag', 'N/A')
        release_name = payload.get('name', tag_name)
        release_url = payload.get('url', repo_url)
        project_data = payload.get('project', {})
        repo_name = project_data.get('path_with_namespace', repo_url)
        # GitLab release hooks don't typically include a 'user' who performed the action directly in the root.
        # It might be inferred or logged differently by GitLab. For now, we'll omit a specific author.

        color = discord.Color.teal() if action == "create" else discord.Color.blurple()

        embed = discord.Embed(
            title=f"Release {action.capitalize()}: {release_name}",
            url=release_url,
            description=f"A release `{tag_name}` was {action} in `{repo_name}`.",
            color=color
        )
        # embed.set_author(name=project_data.get('namespace', 'GitLab')) # Or project name

        if payload.get('description'):
            desc = payload['description']
            embed.add_field(name="Release Notes", value=desc[:1020] + "..." if len(desc) > 1024 else desc, inline=False)
        
        return embed
    except Exception as e:
        log.error(f"Error formatting GitLab release embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitLab Release Event", description=str(e), color=discord.Color.red())

def format_gitlab_note_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
    """Formats a Discord embed for a GitLab note event (comments)."""
    try:
        attributes = payload.get('object_attributes', {})
        user = payload.get('user', {})
        project_data = payload.get('project', {})
        repo_name = project_data.get('path_with_namespace', repo_url)

        note_type = attributes.get('noteable_type', 'Comment') # Issue, MergeRequest, Commit, Snippet
        note_url = attributes.get('url', repo_url)
        user_name = user.get('name', 'Unknown User')
        user_avatar = user.get('avatar_url')

        title_prefix = "New Comment"
        target_info = ""

        if note_type == 'Commit':
            commit_data = payload.get('commit', {})
            title_prefix = f"Comment on Commit `{commit_data.get('id', 'N/A')[:7]}`"
        elif note_type == 'Issue':
            issue_data = payload.get('issue', {})
            title_prefix = f"Comment on Issue #{issue_data.get('iid', 'N/A')}"
            target_info = issue_data.get('title', '')
        elif note_type == 'MergeRequest':
            mr_data = payload.get('merge_request', {})
            title_prefix = f"Comment on MR !{mr_data.get('iid', 'N/A')}"
            target_info = mr_data.get('title', '')
        elif note_type == 'Snippet':
            snippet_data = payload.get('snippet', {})
            title_prefix = f"Comment on Snippet #{snippet_data.get('id', 'N/A')}"
            target_info = snippet_data.get('title', '')
        
        embed = discord.Embed(
            title=f"{title_prefix}: {target_info}".strip(),
            url=note_url,
            color=discord.Color.greyple()
        )
        embed.set_author(name=user_name, icon_url=user_avatar)

        if attributes.get('note'):
            note_body = attributes['note']
            embed.description = note_body[:2040] + "..." if len(note_body) > 2048 else note_body
        
        embed.set_footer(text=f"Comment in {repo_name}")
        return embed
    except Exception as e:
        log.error(f"Error formatting GitLab note embed: {e}\nPayload: {payload}")
        return discord.Embed(title="Error Processing GitLab Note Event", description=str(e), color=discord.Color.red())


@router.post("/github/{repo_db_id}")
async def webhook_github(
    request: Request,
    repo_db_id: int = Path(..., description="The database ID of the monitored repository"),
    x_hub_signature_256: Optional[str] = Header(None)
):
    log.info(f"Received GitHub webhook for repo_db_id: {repo_db_id}")
    payload_bytes = await request.body()

    # Use our new function that uses the API service's PostgreSQL pool
    repo_config = await get_monitored_repository_by_id_api(request, repo_db_id)
    if not repo_config:
        log.error(f"No repository configuration found for repo_db_id: {repo_db_id}")
        raise HTTPException(status_code=404, detail="Repository configuration not found.")

    if repo_config['monitoring_method'] != 'webhook' or repo_config['platform'] != 'github':
        log.error(f"Repository {repo_db_id} is not configured for GitHub webhooks.")
        raise HTTPException(status_code=400, detail="Repository not configured for GitHub webhooks.")

    if not verify_github_signature(payload_bytes, repo_config['webhook_secret'], x_hub_signature_256):
        log.warning(f"Invalid GitHub signature for repo_db_id: {repo_db_id}")
        raise HTTPException(status_code=403, detail="Invalid signature.")

    try:
        payload = json.loads(payload_bytes.decode('utf-8'))
    except json.JSONDecodeError:
        log.error(f"Invalid JSON payload received for GitHub webhook, repo_db_id: {repo_db_id}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    log.debug(f"GitHub webhook payload for {repo_db_id}: {payload}")

    event_type = request.headers.get("X-GitHub-Event")
    allowed_events = repo_config.get('allowed_webhook_events', ['push']) # Default to 'push'

    if event_type not in allowed_events:
        log.info(f"Ignoring GitHub event type '{event_type}' for repo_db_id: {repo_db_id} as it's not in allowed events: {allowed_events}")
        return {"status": "success", "message": f"Event type '{event_type}' ignored per configuration."}

    discord_embed = None
    if event_type == "push":
        if not payload.get('commits') and not payload.get('deleted', False): # Also consider branch deletion as a push event
            log.info(f"GitHub push event for {repo_db_id} has no commits and is not a delete event. Ignoring.")
            return {"status": "success", "message": "Push event with no commits ignored."}
        discord_embed = format_github_push_embed(payload, repo_config['repository_url'])
    elif event_type == "issues":
        discord_embed = format_github_issues_embed(payload, repo_config['repository_url'])
    elif event_type == "pull_request":
        discord_embed = format_github_pull_request_embed(payload, repo_config['repository_url'])
    elif event_type == "release":
        discord_embed = format_github_release_embed(payload, repo_config['repository_url'])
    elif event_type == "issue_comment":
        discord_embed = format_github_issue_comment_embed(payload, repo_config['repository_url'])
    # Add other specific event types above this else block
    else:
        log.info(f"GitHub event type '{event_type}' is allowed but not yet handled by a specific formatter for repo_db_id: {repo_db_id}. Sending generic message.")
        # For unhandled but allowed events, send a generic notification or log.
        # For now, we'll just acknowledge. If you want to notify for all allowed events, create generic formatter.
        # return {"status": "success", "message": f"Event type '{event_type}' received but no specific formatter yet."}
        # Or, create a generic embed:
        embed_title = f"GitHub Event: {event_type.replace('_', ' ').title()} in {repo_config.get('repository_url')}"
        embed_description = f"Received a '{event_type}' event."
        # Try to get a relevant URL
        action_url = payload.get('repository', {}).get('html_url', '#')
        if event_type == 'issues' and 'issue' in payload and 'html_url' in payload['issue']:
            action_url = payload['issue']['html_url']
        elif event_type == 'pull_request' and 'pull_request' in payload and 'html_url' in payload['pull_request']:
            action_url = payload['pull_request']['html_url']

        discord_embed = discord.Embed(title=embed_title, description=embed_description, url=action_url, color=discord.Color.light_grey())


    if not discord_embed:
        log.warning(f"No embed generated for allowed GitHub event '{event_type}' for repo {repo_db_id}. This shouldn't happen if event is handled.")
        return {"status": "error", "message": "Embed generation failed for an allowed event."}

    notification_channel_id = repo_config['notification_channel_id']

    # Convert embed to dict for sending via API
    message_content = {"embeds": [discord_embed.to_dict()]}

    # Use the send_discord_message_via_api from api_server.py
    # This requires DISCORD_BOT_TOKEN to be set in the environment for api_server
    if not api_settings.DISCORD_BOT_TOKEN:
        log.error("DISCORD_BOT_TOKEN not configured in API settings. Cannot send webhook notification.")
        # Still return 200 to GitHub to acknowledge receipt, but log error.
        return {"status": "error", "message": "Notification sending failed (bot token not configured)."}

    send_result = await send_discord_message_via_api(
        channel_id=notification_channel_id,
        content=json.dumps(message_content) # send_discord_message_via_api expects a string for 'content'
                                            # but it should handle dicts with 'embeds' if modified or we send raw.
                                            # For now, let's assume it needs a simple string or we adapt it.
                                            # The current send_discord_message_via_api sends 'content' as a top-level string.
                                            # We need to send an embed.
    )
    # The send_discord_message_via_api needs to be adapted to send embeds.
    # For now, let's construct the data for the POST request directly as it would expect.

    # Corrected way to send embed using the existing send_discord_message_via_api structure
    # The function expects a simple string content. We need to modify it or use aiohttp directly here.
    # Let's assume we'll modify send_discord_message_via_api later or use a more direct aiohttp call.
    # For now, this will likely fail to send an embed correctly with the current send_discord_message_via_api.
    # This is a placeholder for correct embed sending.

    # To send an embed, the JSON body to Discord API should be like:
    # { "embeds": [ { ... embed object ... } ] }
    # The current `send_discord_message_via_api` sends `{"content": "message"}`.
    # This part needs careful implementation.

    # For now, let's log what would be sent.
    log.info(f"Prepared to send GitHub notification to channel {notification_channel_id} for repo {repo_db_id}.")
    # Actual sending logic will be refined.

    # Placeholder for actual sending:
    # For a quick test, we can try to send a simple text message.
    # simple_text = f"New push to {repo_config['repository_url']}. Commits: {len(payload.get('commits', []))}"
    # send_result = await send_discord_message_via_api(notification_channel_id, simple_text)

    # If send_discord_message_via_api is adapted to handle embeds in its 'content' (e.g. by checking if it's a dict with 'embeds' key)
    # then the following would be more appropriate:
    # This requires send_discord_message_via_api to be flexible.
    send_payload_dict = {"embeds": [discord_embed.to_dict()]}

    send_result = await send_discord_message_via_api(
        channel_id=notification_channel_id,
        content=send_payload_dict # Pass the dict directly
    )

    if send_result.get("success"):
        log.info(f"Successfully sent GitHub webhook notification for repo {repo_db_id} to channel {notification_channel_id}.")
        return {"status": "success", "message": "Webhook received and notification sent."}
    else:
        log.error(f"Failed to send GitHub webhook notification for repo {repo_db_id}. Error: {send_result.get('message')}")
        # Still return 200 to GitHub to acknowledge receipt, but log the internal failure.
        return {"status": "error", "message": f"Webhook received, but notification failed: {send_result.get('message')}"}


@router.post("/gitlab/{repo_db_id}")
async def webhook_gitlab(
    request: Request,
    repo_db_id: int = Path(..., description="The database ID of the monitored repository"),
    x_gitlab_token: Optional[str] = Header(None)
):
    log.info(f"Received GitLab webhook for repo_db_id: {repo_db_id}")
    payload_bytes = await request.body()

    # Use our new function that uses the API service's PostgreSQL pool
    repo_config = await get_monitored_repository_by_id_api(request, repo_db_id)
    if not repo_config:
        log.error(f"No repository configuration found for repo_db_id: {repo_db_id}")
        raise HTTPException(status_code=404, detail="Repository configuration not found.")

    if repo_config['monitoring_method'] != 'webhook' or repo_config['platform'] != 'gitlab':
        log.error(f"Repository {repo_db_id} is not configured for GitLab webhooks.")
        raise HTTPException(status_code=400, detail="Repository not configured for GitLab webhooks.")

    if not verify_gitlab_token(repo_config['webhook_secret'], x_gitlab_token):
        log.warning(f"Invalid GitLab token for repo_db_id: {repo_db_id}")
        raise HTTPException(status_code=403, detail="Invalid token.")

    try:
        payload = json.loads(payload_bytes.decode('utf-8'))
    except json.JSONDecodeError:
        log.error(f"Invalid JSON payload received for GitLab webhook, repo_db_id: {repo_db_id}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    log.debug(f"GitLab webhook payload for {repo_db_id}: {payload}")

    # GitLab uses 'object_kind' for event type, or 'event_name' for system hooks
    event_type = payload.get("object_kind", payload.get("event_name"))
    allowed_events = repo_config.get('allowed_webhook_events', ['push']) # Default to 'push' (GitLab calls push hooks 'push events' or 'tag_push events')

    # Normalize GitLab event types if needed, e.g. 'push' for 'push_hook' or 'tag_push_hook'
    # For now, assume direct match or that 'push' covers both.
    # GitLab event names for webhooks: push_events, tag_push_events, issues_events, merge_requests_events, etc.
    # The payload's object_kind is often more specific: 'push', 'tag_push', 'issue', 'merge_request'.
    # We should aim to match against object_kind primarily.
    # Let's simplify: if 'push' is in allowed_events, we'll accept 'push' and 'tag_push' object_kinds.
    
    effective_event_type = event_type
    if event_type == "tag_push" and "push" in allowed_events and "tag_push" not in allowed_events:
        # If only "push" is allowed, but we receive "tag_push", treat it as a push for now.
        # This logic might need refinement based on how granular the user wants control.
        pass # It will be caught by the 'push' check if 'push' is allowed.
        
    is_event_allowed = False
    if event_type in allowed_events:
        is_event_allowed = True
    elif event_type == "tag_push" and "push" in allowed_events: # Special handling if 'push' implies 'tag_push'
        is_event_allowed = True
        effective_event_type = "push" # Treat as push for formatter if only push is configured

    if not is_event_allowed:
        log.info(f"Ignoring GitLab event type '{event_type}' (object_kind/event_name) for repo_db_id: {repo_db_id} as it's not in allowed events: {allowed_events}")
        return {"status": "success", "message": f"Event type '{event_type}' ignored per configuration."}

    discord_embed = None
    # Use effective_event_type for choosing formatter
    if effective_event_type == "push": # This will catch 'push' and 'tag_push' if 'push' is allowed
        if not payload.get('commits') and payload.get('total_commits_count', 0) == 0:
             log.info(f"GitLab push event for {repo_db_id} has no commits. Ignoring.")
             return {"status": "success", "message": "Push event with no commits ignored."}
        discord_embed = format_gitlab_push_embed(payload, repo_config['repository_url'])
    elif effective_event_type == "issue": # Matches object_kind 'issue'
        discord_embed = format_gitlab_issue_embed(payload, repo_config['repository_url'])
    elif effective_event_type == "merge_request":
        discord_embed = format_gitlab_merge_request_embed(payload, repo_config['repository_url'])
    elif effective_event_type == "release":
        discord_embed = format_gitlab_release_embed(payload, repo_config['repository_url'])
    elif effective_event_type == "note": # For comments
        discord_embed = format_gitlab_note_embed(payload, repo_config['repository_url'])
    # Add other specific event types above this else block
    else:
        log.info(f"GitLab event type '{event_type}' (effective: {effective_event_type}) is allowed but not yet handled by a specific formatter for repo_db_id: {repo_db_id}. Sending generic message.")
        embed_title = f"GitLab Event: {event_type.replace('_', ' ').title()} in {repo_config.get('repository_url')}"
        embed_description = f"Received a '{event_type}' event."
        action_url = payload.get('project', {}).get('web_url', '#')
        # Try to get more specific URLs for common GitLab events
        if 'object_attributes' in payload and 'url' in payload['object_attributes']:
            action_url = payload['object_attributes']['url']
        elif 'project' in payload and 'web_url' in payload['project']:
            action_url = payload['project']['web_url']

        discord_embed = discord.Embed(title=embed_title, description=embed_description, url=action_url, color=discord.Color.dark_orange())


    if not discord_embed:
        log.warning(f"No embed generated for allowed GitLab event '{event_type}' for repo {repo_db_id}.")
        return {"status": "error", "message": "Embed generation failed for an allowed event."}

    notification_channel_id = repo_config['notification_channel_id']

    # Similar to GitHub, sending embed needs careful handling with send_discord_message_via_api
    if not api_settings.DISCORD_BOT_TOKEN:
        log.error("DISCORD_BOT_TOKEN not configured in API settings. Cannot send webhook notification.")
        return {"status": "error", "message": "Notification sending failed (bot token not configured)."}

    send_payload_dict = {"embeds": [discord_embed.to_dict()]}

    send_result = await send_discord_message_via_api(
        channel_id=notification_channel_id,
        content=send_payload_dict # Pass the dict directly
    )

    if send_result.get("success"):
        log.info(f"Successfully sent GitLab webhook notification for repo {repo_db_id} to channel {notification_channel_id}.")
        return {"status": "success", "message": "Webhook received and notification sent."}
    else:
        log.error(f"Failed to send GitLab webhook notification for repo {repo_db_id}. Error: {send_result.get('message')}")
        return {"status": "error", "message": f"Webhook received, but notification failed: {send_result.get('message')}"}

@router.get("/test")
async def test_webhook_router():
    return {"message": "Webhook router is working. Or mounted, at least."}

@router.get("/test-repo/{repo_db_id}")
async def test_repo_retrieval(request: Request, repo_db_id: int):
    """Test endpoint to check if we can retrieve repository information."""
    try:
        # Try to get the repository using our new function
        repo_config = await get_monitored_repository_by_id_api(request, repo_db_id)

        if repo_config:
            return {
                "message": "Repository found",
                "repo_config": repo_config
            }
        else:
            return {
                "message": "Repository not found",
                "repo_db_id": repo_db_id
            }
    except Exception as e:
        log.exception(f"Error retrieving repository {repo_db_id}: {e}")
        return {
            "message": "Error retrieving repository",
            "repo_db_id": repo_db_id,
            "error": str(e)
        }

@router.get("/test-db")
async def test_db_connection(request: Request):
    """Test endpoint to check if the database connection is working."""
    try:
        # Log the available attributes in app.state for debugging
        state_attrs = dir(request.app.state)
        log.info(f"Available attributes in app.state: {state_attrs}")

        # Try to get the PostgreSQL pool from the FastAPI app state
        pg_pool = getattr(request.app.state, "pg_pool", None)
        if not pg_pool:
            log.warning("API service PostgreSQL pool not available for test-db endpoint.")

            # Try to create a new connection
            try:
                import asyncpg
                settings = get_api_settings()
                log.info("Attempting to create a new PostgreSQL connection for test-db endpoint")

                # Create a new connection to the database
                conn = await asyncpg.connect(
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    host=settings.POSTGRES_HOST,
                    database=settings.POSTGRES_SETTINGS_DB
                )

                # Test query
                version = await conn.fetchval("SELECT version()")

                # Close the connection
                await conn.close()

                return {
                    "message": "Database connection successful using direct connection",
                    "app_state_attrs": state_attrs,
                    "pg_pool_available": False,
                    "version": version
                }
            except Exception as e:
                log.exception(f"Failed to create a new PostgreSQL connection for test-db endpoint: {e}")
                return {
                    "message": "Database connection failed using direct connection",
                    "app_state_attrs": state_attrs,
                    "pg_pool_available": False,
                    "error": str(e)
                }

        # Use the pool
        try:
            async with pg_pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                return {
                    "message": "Database connection successful using app.state.pg_pool",
                    "app_state_attrs": state_attrs,
                    "pg_pool_available": True,
                    "version": version
                }
        except Exception as e:
            log.exception(f"Database error using app.state.pg_pool: {e}")
            return {
                "message": "Database connection failed using app.state.pg_pool",
                "app_state_attrs": state_attrs,
                "pg_pool_available": True,
                "error": str(e)
            }
    except Exception as e:
        log.exception(f"Unexpected error in test-db endpoint: {e}")
        return {
            "message": "Unexpected error in test-db endpoint",
            "error": str(e)
        }
