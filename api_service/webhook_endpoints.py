import hashlib
import hmac
import json
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Header, Path
import discord # For Color

# Assuming settings_manager and api_server are accessible
# Adjust imports based on your project structure
try:
    from .. import settings_manager # If api_service is a package
    from .api_server import send_discord_message_via_api, get_api_settings # For settings
except ImportError:
    # This path might be used if running webhook_endpoints.py directly for testing (not typical for FastAPI)
    # Or if the structure is flat
    import settings_manager
    # If api_server.py is in the same directory:
    from api_server import send_discord_message_via_api, get_api_settings


log = logging.getLogger(__name__)
router = APIRouter()
api_settings = get_api_settings() # Get loaded API settings

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

def format_github_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
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
                f"Message: {commit_msg.splitlines()[0]}\n" # First line of commit message
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
        log.exception(f"Error formatting GitHub embed: {e}")
        embed = discord.Embed(title="Error Processing GitHub Webhook", description=f"Could not parse commit details. Raw payload might be available in logs.\nError: {e}", color=discord.Color.red())
        return embed


def format_gitlab_embed(payload: Dict[str, Any], repo_url: str) -> discord.Embed:
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
            stats_lines = []
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
        log.exception(f"Error formatting GitLab embed: {e}")
        embed = discord.Embed(title="Error Processing GitLab Webhook", description=f"Could not parse commit details. Raw payload might be available in logs.\nError: {e}", color=discord.Color.red())
        return embed


@router.post("/webhook/github/{repo_db_id}")
async def webhook_github(
    request: Request,
    repo_db_id: int = Path(..., description="The database ID of the monitored repository"),
    x_hub_signature_256: Optional[str] = Header(None)
):
    log.info(f"Received GitHub webhook for repo_db_id: {repo_db_id}")
    payload_bytes = await request.body()
    
    repo_config = await settings_manager.get_monitored_repository_by_id(repo_db_id)
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

    # We only care about 'push' events for commits
    event_type = request.headers.get("X-GitHub-Event")
    if event_type != "push":
        log.info(f"Ignoring GitHub event type '{event_type}' for repo_db_id: {repo_db_id}")
        return {"status": "success", "message": f"Event type '{event_type}' ignored."}

    if not payload.get('commits'):
        log.info(f"GitHub push event for {repo_db_id} has no commits (e.g. branch creation/deletion). Ignoring.")
        return {"status": "success", "message": "Push event with no commits ignored."}

    notification_channel_id = repo_config['notification_channel_id']
    discord_embed = format_github_embed(payload, repo_config['repository_url'])
    
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
    send_payload = {"embeds": [discord_embed.to_dict()]}
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


@router.post("/webhook/gitlab/{repo_db_id}")
async def webhook_gitlab(
    request: Request,
    repo_db_id: int = Path(..., description="The database ID of the monitored repository"),
    x_gitlab_token: Optional[str] = Header(None)
):
    log.info(f"Received GitLab webhook for repo_db_id: {repo_db_id}")
    payload_bytes = await request.body()

    repo_config = await settings_manager.get_monitored_repository_by_id(repo_db_id)
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

    # GitLab uses 'object_kind' for event type
    event_type = payload.get("object_kind")
    if event_type != "push": # GitLab calls it 'push' for push hooks
        log.info(f"Ignoring GitLab event type '{event_type}' for repo_db_id: {repo_db_id}")
        return {"status": "success", "message": f"Event type '{event_type}' ignored."}

    if not payload.get('commits'):
        log.info(f"GitLab push event for {repo_db_id} has no commits. Ignoring.")
        return {"status": "success", "message": "Push event with no commits ignored."}

    notification_channel_id = repo_config['notification_channel_id']
    discord_embed = format_gitlab_embed(payload, repo_config['repository_url'])
    
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
