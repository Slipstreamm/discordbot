import logging
import asyncio
from fastapi import Depends, HTTPException, Request, status
import aiohttp
from functools import lru_cache
import os

# --- Configuration Loading ---
# Need to load settings here as well, or pass http_session/settings around
# Re-using the settings logic from api_server.py for simplicity
dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'discordbot', '.env')

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class ApiSettings(BaseSettings):
    DISCORD_CLIENT_ID: str
    DISCORD_CLIENT_SECRET: str
    DISCORD_REDIRECT_URI: str
    DISCORD_BOT_TOKEN: Optional[str] = None
    DASHBOARD_SECRET_KEY: str = "a_default_secret_key_for_development_only"
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_SETTINGS_DB: str
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    MOD_LOG_API_SECRET: Optional[str] = None
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 443
    SSL_CERT_FILE: Optional[str] = None
    SSL_KEY_FILE: Optional[str] = None
    GURT_STATS_PUSH_SECRET: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=dotenv_path,
        env_file_encoding='utf-8',
        extra='ignore'
    )

@lru_cache()
def get_api_settings() -> ApiSettings:
    if not os.path.exists(dotenv_path):
        print(f"Warning: .env file not found at {dotenv_path}. Using defaults or environment variables.")
    return ApiSettings()

settings = get_api_settings()

# --- Constants ---
DISCORD_API_BASE_URL = "https://discord.com/api/v10"
DISCORD_USER_URL = f"{DISCORD_API_BASE_URL}/users/@me"
DISCORD_USER_GUILDS_URL = f"{DISCORD_API_BASE_URL}/users/@me/guilds"

# --- Logging ---
log = logging.getLogger(__name__) # Use specific logger

# --- Global aiohttp Session (managed by api_server lifespan) ---
# We need access to the session created in api_server.py
# A simple way is to have api_server.py set it after creation.
http_session: Optional[aiohttp.ClientSession] = None

def set_http_session(session: aiohttp.ClientSession):
    """Sets the global aiohttp session for dependencies."""
    global http_session
    http_session = session

# --- Authentication Dependency (Dashboard Specific) ---
async def get_dashboard_user(request: Request) -> dict:
    """Dependency to check if user is authenticated via dashboard session and return user data."""
    user_id = request.session.get('user_id')
    username = request.session.get('username')
    access_token = request.session.get('access_token') # Needed for subsequent Discord API calls

    if not user_id or not username or not access_token:
        log.warning("Dashboard: Attempted access by unauthenticated user.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated for dashboard",
            headers={"WWW-Authenticate": "Bearer"}, # Standard header for 401
        )
    # Return essential user info and token for potential use in endpoints
    return {
        "user_id": user_id,
        "username": username,
        "avatar": request.session.get('avatar'),
        "access_token": access_token
        }

# --- Guild Admin Verification Dependency (Dashboard Specific) ---
async def verify_dashboard_guild_admin(guild_id: int, current_user: dict = Depends(get_dashboard_user)) -> bool:
    """Dependency to verify the dashboard session user is an admin of the specified guild."""
    global http_session # Use the global aiohttp session
    if not http_session:
         log.error("verify_dashboard_guild_admin: HTTP session not ready.")
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    user_headers = {'Authorization': f'Bearer {current_user["access_token"]}'}
    try:
        log.debug(f"Dashboard: Verifying admin status for user {current_user['user_id']} in guild {guild_id}")

        # Add rate limit handling
        max_retries = 3
        retry_count = 0
        retry_after = 0

        while retry_count < max_retries:
            if retry_after > 0:
                log.warning(f"Dashboard: Rate limited by Discord API, waiting {retry_after} seconds before retry")
                await asyncio.sleep(retry_after)

            async with http_session.get(DISCORD_USER_GUILDS_URL, headers=user_headers) as resp:
                if resp.status == 429:  # Rate limited
                    retry_count += 1
                    try:
                        retry_after = float(resp.headers.get('X-RateLimit-Reset-After', resp.headers.get('Retry-After', 1)))
                    except (ValueError, TypeError):
                        retry_after = 1.0 # Default wait time if header is invalid
                    is_global = resp.headers.get('X-RateLimit-Global') is not None
                    scope = resp.headers.get('X-RateLimit-Scope', 'unknown')
                    log.warning(
                        f"Dashboard: Discord API rate limit hit. "
                        f"Global: {is_global}, Scope: {scope}, "
                        f"Reset after: {retry_after}s, "
                        f"Retry: {retry_count}/{max_retries}"
                    )
                    if is_global: retry_after = max(retry_after, 5) # Wait longer for global limits
                    continue # Retry the request

                if resp.status == 401:
                    # Session token might be invalid, but we can't clear session here easily.
                    # Let the frontend handle re-authentication based on the 401.
                    raise HTTPException(status_code=401, detail="Discord token invalid or expired. Please re-login.")

                resp.raise_for_status() # Raise for other errors (4xx, 5xx)
                user_guilds = await resp.json()

                ADMINISTRATOR_PERMISSION = 0x8
                is_admin = False
                for guild in user_guilds:
                    if int(guild['id']) == guild_id:
                        permissions = int(guild['permissions'])
                        if (permissions & ADMINISTRATOR_PERMISSION) == ADMINISTRATOR_PERMISSION:
                            is_admin = True
                            break # Found the guild and user is admin

                if not is_admin:
                    log.warning(f"Dashboard: User {current_user['user_id']} is not admin or not in guild {guild_id}.")
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not an administrator of this guild.")

                log.debug(f"Dashboard: User {current_user['user_id']} verified as admin for guild {guild_id}.")
                return True # Indicate verification success

        # If loop finishes without returning True, it means retries were exhausted
        raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")

    except aiohttp.ClientResponseError as e:
        log.exception(f"Dashboard: HTTP error verifying guild admin status: {e.status} {e.message}")
        if e.status == 429: # Should be caught by the loop, but safeguard
            raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Dashboard: Generic error verifying guild admin status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred during permission verification.")
