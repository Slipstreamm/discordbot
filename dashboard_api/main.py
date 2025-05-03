import logging
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import aiohttp
from urllib.parse import quote_plus
import sys
import os
from pydantic import BaseModel, Field
from typing import Dict, List, Optional # For type hinting

# Ensure discordbot is in path to import settings_manager
# This assumes dashboard_api is run from the project root (z:/projects_git/combined)
# or that the parent directory is in PYTHONPATH.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from discordbot import settings_manager
except ImportError as e:
    print(f"ERROR: Could not import discordbot.settings_manager: {e}")
    print("Ensure the API is run from the project root or discordbot is in PYTHONPATH.")
    settings_manager = None # Set to None to indicate failure

# Import settings and constants from config.py
from .config import settings, DISCORD_AUTH_URL, DISCORD_TOKEN_URL, DISCORD_USER_URL, DISCORD_USER_GUILDS_URL

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) # Basic logging for the API

# --- FastAPI App Setup ---
app = FastAPI(title="Discord Bot Dashboard API")

# Add Session Middleware
# IMPORTANT: The secret key *must* be set securely in a real environment.
# It's loaded from config.settings now.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.DASHBOARD_SECRET_KEY,
    session_cookie="dashboard_session",
    max_age=60 * 60 * 24 * 7 # 7 days expiry
)

# --- Discord API Client ---
# Use a single session for efficiency
http_session = None

@app.on_event("startup")
async def startup_event():
    """Initialize resources on API startup."""
    global http_session
    http_session = aiohttp.ClientSession()
    log.info("aiohttp session started.")
    # Initialize settings_manager pools if available
    if settings_manager:
        try:
            # Pass config directly if needed, or rely on settings_manager loading its own .env
            await settings_manager.initialize_pools()
            log.info("Settings manager pools initialized.")
        except Exception as e:
            log.exception("Failed to initialize settings_manager pools during API startup.")
            # Depending on severity, might want to prevent API from starting fully
    else:
        log.error("settings_manager not imported, database/cache pools NOT initialized for API.")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on API shutdown."""
    if http_session:
        await http_session.close()
        log.info("aiohttp session closed.")
    # Close settings_manager pools if available and initialized
    if settings_manager and settings_manager.pg_pool: # Check if pool was initialized
        await settings_manager.close_pools()
        log.info("Settings manager pools closed.")

# --- Authentication Routes ---

@app.get("/api/auth/login", tags=["Authentication"])
async def login_with_discord():
    """Redirects the user to Discord for OAuth2 authorization."""
    log.info(f"Redirecting user to Discord auth URL: {DISCORD_AUTH_URL}")
    return RedirectResponse(url=DISCORD_AUTH_URL, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@app.get("/api/auth/callback", tags=["Authentication"])
async def auth_callback(request: Request, code: str | None = None, error: str | None = None):
    """Handles the callback from Discord after authorization."""
    if error:
        log.error(f"Discord OAuth error: {error}")
        # Redirect to frontend with error message?
        return RedirectResponse(url="/?error=discord_auth_failed") # Redirect to frontend root

    if not code:
        log.error("Discord OAuth callback missing code.")
        return RedirectResponse(url="/?error=missing_code")

    if not http_session:
         log.error("aiohttp session not initialized.")
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    try:
        # 1. Exchange code for access token
        token_data = {
            'client_id': settings.DISCORD_CLIENT_ID,
            'client_secret': settings.DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.DISCORD_REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        log.debug(f"Exchanging code for token at {DISCORD_TOKEN_URL}")
        async with http_session.post(DISCORD_TOKEN_URL, data=token_data, headers=headers) as resp:
            resp.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
            token_response = await resp.json()
            access_token = token_response.get('access_token')
            refresh_token = token_response.get('refresh_token') # Store this if you need long-term access
            expires_in = token_response.get('expires_in')
            log.debug("Token exchange successful.")

        if not access_token:
            log.error("Failed to get access token from Discord response.")
            raise HTTPException(status_code=500, detail="Could not retrieve access token from Discord.")

        # 2. Fetch user data using the access token
        user_headers = {'Authorization': f'Bearer {access_token}'}
        log.debug(f"Fetching user data from {DISCORD_USER_URL}")
        async with http_session.get(DISCORD_USER_URL, headers=user_headers) as resp:
            resp.raise_for_status()
            user_data = await resp.json()
            log.debug(f"User data fetched successfully for user ID: {user_data.get('id')}")

        # 3. Store relevant user data and token in session
        request.session['user_id'] = user_data.get('id')
        request.session['username'] = user_data.get('username')
        request.session['avatar'] = user_data.get('avatar')
        request.session['access_token'] = access_token # Store token for API calls
        # Optionally store refresh_token and expiry time if needed

        log.info(f"User {user_data.get('username')} ({user_data.get('id')}) logged in successfully.")
        # Redirect user back to the main dashboard page
        return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT) # Redirect to frontend root

    except aiohttp.ClientResponseError as e:
        log.exception(f"HTTP error during Discord OAuth callback: {e.status} {e.message}")
        # Try to get error details from response if possible
        error_detail = "Unknown Discord API error"
        try:
            error_body = await e.response.json()
            error_detail = error_body.get("error_description", error_detail)
        except Exception:
            pass # Ignore if response body isn't JSON or can't be read
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error communicating with Discord: {error_detail}")
    except Exception as e:
        log.exception(f"Generic error during Discord OAuth callback: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred during authentication.")


@app.post("/api/auth/logout", tags=["Authentication"], status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request):
    """Clears the user session."""
    user_id = request.session.get('user_id')
    request.session.clear()
    log.info(f"User {user_id} logged out.")
    # No content needed in response, status code 204 indicates success
    return

# --- Authentication Dependency ---
async def get_current_user(request: Request) -> dict:
    """Dependency to check if user is authenticated and return user data from session."""
    user_id = request.session.get('user_id')
    username = request.session.get('username')
    access_token = request.session.get('access_token') # Needed for subsequent Discord API calls

    if not user_id or not username or not access_token:
        log.warning("Attempted access by unauthenticated user.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}, # Standard header for 401
        )
    # Return essential user info and token for potential use in endpoints
    return {
        "user_id": user_id,
        "username": username,
        "avatar": request.session.get('avatar'),
        "access_token": access_token
        }

# --- User Endpoints ---
@app.get("/api/user/me", tags=["User"])
async def get_user_me(current_user: dict = Depends(get_current_user)):
    """Returns information about the currently logged-in user."""
    # The dependency already fetched and validated the user data
    # We can remove the access token before sending back to frontend if preferred
    user_info = current_user.copy()
    # del user_info['access_token'] # Optional: Don't expose token to frontend if not needed there
    return user_info

@app.get("/api/user/guilds", tags=["User"])
async def get_user_guilds(current_user: dict = Depends(get_current_user)):
    """Returns a list of guilds the user is an administrator in AND the bot is also in."""
    if not http_session:
         log.error("aiohttp session not initialized.")
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")
    if not settings_manager:
        log.error("settings_manager not available.")
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    access_token = current_user['access_token']
    user_headers = {'Authorization': f'Bearer {access_token}'}

    try:
        # 1. Fetch guilds user is in from Discord
        log.debug(f"Fetching user guilds from {DISCORD_USER_GUILDS_URL}")
        async with http_session.get(DISCORD_USER_GUILDS_URL, headers=user_headers) as resp:
            resp.raise_for_status()
            user_guilds = await resp.json()
        log.debug(f"Fetched {len(user_guilds)} guilds for user {current_user['user_id']}")

        # 2. Fetch guilds the bot is in from our DB
        bot_guild_ids = await settings_manager.get_bot_guild_ids()
        if bot_guild_ids is None:
            log.error("Failed to fetch bot guild IDs from settings_manager.")
            raise HTTPException(status_code=500, detail="Could not retrieve bot's guild list.")

        # 3. Filter user guilds
        manageable_guilds = []
        ADMINISTRATOR_PERMISSION = 0x8
        for guild in user_guilds:
            guild_id = int(guild['id'])
            permissions = int(guild['permissions'])

            # Check if user is admin AND bot is in the guild
            if (permissions & ADMINISTRATOR_PERMISSION) == ADMINISTRATOR_PERMISSION and guild_id in bot_guild_ids:
                manageable_guilds.append({
                    "id": guild['id'],
                    "name": guild['name'],
                    "icon": guild.get('icon'), # Can be None
                    # Add other relevant fields if needed
                })

        log.info(f"Found {len(manageable_guilds)} manageable guilds for user {current_user['user_id']}")
        return manageable_guilds

    except aiohttp.ClientResponseError as e:
        log.exception(f"HTTP error fetching user guilds: {e.status} {e.message}")
        if e.status == 401: # Token might have expired
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Discord token invalid or expired. Please re-login.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Generic error fetching user guilds: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching guilds.")


# --- Root endpoint (for basic check and potentially serving frontend) ---
@app.get("/")
async def read_root():
    # This could eventually serve the index.html file
    # from fastapi.responses import FileResponse
    # return FileResponse('path/to/your/frontend/index.html')
    return {"message": "Dashboard API is running - Frontend not served from here yet."}


# --- Pydantic Models for Settings ---

class GuildSettingsResponse(BaseModel):
    guild_id: str
    prefix: Optional[str] = None
    welcome_channel_id: Optional[str] = None
    welcome_message: Optional[str] = None
    goodbye_channel_id: Optional[str] = None
    goodbye_message: Optional[str] = None
    enabled_cogs: Dict[str, bool] = {} # Cog name -> enabled status
    command_permissions: Dict[str, List[str]] = {} # Command name -> List of allowed role IDs (as strings)
    # channels: List[dict] = [] # TODO: Need bot interaction to get this reliably
    # roles: List[dict] = [] # TODO: Need bot interaction to get this reliably

class GuildSettingsUpdate(BaseModel):
    # Use Optional fields for PATCH, only provided fields will be updated
    prefix: Optional[str] = Field(None, min_length=1, max_length=10)
    welcome_channel_id: Optional[str] = Field(None) # Allow empty string or null to disable
    welcome_message: Optional[str] = Field(None)
    goodbye_channel_id: Optional[str] = Field(None) # Allow empty string or null to disable
    goodbye_message: Optional[str] = Field(None)
    cogs: Optional[Dict[str, bool]] = Field(None) # Dict of {cog_name: enabled_status}
    # command_permissions: Optional[dict] = None # TODO: How to represent updates? Simpler to use dedicated endpoints.

# --- Command Permission Models ---
class CommandPermission(BaseModel):
    command_name: str
    role_id: str # Keep as string for consistency

class CommandPermissionsResponse(BaseModel):
    permissions: Dict[str, List[str]] # Command name -> List of allowed role IDs

# --- Guild Admin Verification Dependency ---

async def verify_guild_admin(guild_id: int, current_user: dict = Depends(get_current_user)) -> bool:
    """Dependency to verify the current user is an admin of the specified guild."""
    if not http_session:
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    user_headers = {'Authorization': f'Bearer {current_user["access_token"]}'}
    try:
        log.debug(f"Verifying admin status for user {current_user['user_id']} in guild {guild_id}")
        async with http_session.get(DISCORD_USER_GUILDS_URL, headers=user_headers) as resp:
            if resp.status == 401:
                raise HTTPException(status_code=401, detail="Discord token invalid or expired.")
            resp.raise_for_status()
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
            log.warning(f"User {current_user['user_id']} is not admin or not in guild {guild_id}.")
            # Use 403 Forbidden if user is authenticated but lacks permissions
            # Use 404 Not Found if the guild simply wasn't found in their list (less likely if they selected it)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not an administrator of this guild.")

        log.debug(f"User {current_user['user_id']} verified as admin for guild {guild_id}.")
        return True # Indicate verification success

    except aiohttp.ClientResponseError as e:
        log.exception(f"HTTP error verifying guild admin status: {e.status} {e.message}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Generic error verifying guild admin status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred during permission verification.")


# --- Guild Settings Endpoints ---

@app.get("/api/guilds/{guild_id}/settings", response_model=GuildSettingsResponse, tags=["Guild Settings"])
async def get_guild_settings(
    guild_id: int,
    current_user: dict = Depends(get_current_user),
    is_admin: bool = Depends(verify_guild_admin) # Verify admin status first
):
    """Fetches the current settings for a specific guild."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Fetching settings for guild {guild_id} requested by user {current_user['user_id']}")

    # Fetch settings using settings_manager
    # Note: get_setting returns None if not set, handle "__NONE__" marker if used
    prefix = await settings_manager.get_guild_prefix(guild_id, DEFAULT_PREFIX) # Use default from main.py
    wc_id = await settings_manager.get_setting(guild_id, 'welcome_channel_id')
    wc_msg = await settings_manager.get_setting(guild_id, 'welcome_message')
    gc_id = await settings_manager.get_setting(guild_id, 'goodbye_channel_id')
    gc_msg = await settings_manager.get_setting(guild_id, 'goodbye_message')

    # Fetch explicitly enabled/disabled cogs status
    # This requires knowing the full list of cogs the bot *could* have.
    # For now, we only fetch the ones explicitly set in the DB.
    # TODO: Get full cog list from bot instance or config?
    known_cogs_in_db = {}
    try:
        async with settings_manager.pg_pool.acquire() as conn:
            records = await conn.fetch("SELECT cog_name, enabled FROM enabled_cogs WHERE guild_id = $1", guild_id)
            for record in records:
                known_cogs_in_db[record['cog_name']] = record['enabled']
    except Exception as e:
        log.exception(f"Failed to fetch cog statuses from DB for guild {guild_id}: {e}")
        # Return empty dict or raise error? Let's return empty for now.

    # Construct response
    settings_data = GuildSettingsResponse(
        guild_id=str(guild_id),
        prefix=prefix,
        welcome_channel_id=wc_id if wc_id != "__NONE__" else None,
        welcome_message=wc_msg if wc_msg != "__NONE__" else None,
        goodbye_channel_id=gc_id if gc_id != "__NONE__" else None,
        goodbye_message=gc_msg if gc_msg != "__NONE__" else None,
        enabled_cogs=known_cogs_in_db,
        # command_permissions={}, # TODO: Populate this if needed in the main settings GET
        # channels=[] # Cannot reliably get channels without bot interaction yet
    )

    return settings_data


@app.patch("/api/guilds/{guild_id}/settings", status_code=status.HTTP_200_OK, tags=["Guild Settings"])
async def update_guild_settings(
    guild_id: int,
    settings_update: GuildSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    is_admin: bool = Depends(verify_guild_admin) # Verify admin status
):
    """Updates specific settings for a guild."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Updating settings for guild {guild_id} requested by user {current_user['user_id']}")
    update_data = settings_update.model_dump(exclude_unset=True) # Get only provided fields
    log.debug(f"Update data received: {update_data}")

    success_flags = []

    # Update prefix if provided
    if 'prefix' in update_data:
        success = await settings_manager.set_guild_prefix(guild_id, update_data['prefix'])
        success_flags.append(success)
        if not success: log.error(f"Failed to update prefix for guild {guild_id}")

    # Update welcome settings if provided
    if 'welcome_channel_id' in update_data:
        # Allow null/empty string to disable
        value = update_data['welcome_channel_id'] if update_data['welcome_channel_id'] else None
        success = await settings_manager.set_setting(guild_id, 'welcome_channel_id', value)
        success_flags.append(success)
        if not success: log.error(f"Failed to update welcome_channel_id for guild {guild_id}")
    if 'welcome_message' in update_data:
        success = await settings_manager.set_setting(guild_id, 'welcome_message', update_data['welcome_message'])
        success_flags.append(success)
        if not success: log.error(f"Failed to update welcome_message for guild {guild_id}")

    # Update goodbye settings if provided
    if 'goodbye_channel_id' in update_data:
        value = update_data['goodbye_channel_id'] if update_data['goodbye_channel_id'] else None
        success = await settings_manager.set_setting(guild_id, 'goodbye_channel_id', value)
        success_flags.append(success)
        if not success: log.error(f"Failed to update goodbye_channel_id for guild {guild_id}")
    if 'goodbye_message' in update_data:
        success = await settings_manager.set_setting(guild_id, 'goodbye_message', update_data['goodbye_message'])
        success_flags.append(success)
        if not success: log.error(f"Failed to update goodbye_message for guild {guild_id}")

    # Update cog statuses if provided
    if 'cogs' in update_data and update_data['cogs'] is not None:
        # TODO: Get CORE_COGS list reliably (e.g., from config or bot instance if possible)
        core_cogs_list = {'SettingsCog', 'HelpCog'} # Hardcoded for now
        for cog_name, enabled_status in update_data['cogs'].items():
            if cog_name not in core_cogs_list: # Prevent changing core cogs
                success = await settings_manager.set_cog_enabled(guild_id, cog_name, enabled_status)
                success_flags.append(success)
                if not success: log.error(f"Failed to update status for cog '{cog_name}' for guild {guild_id}")
            else:
                log.warning(f"Attempted to change status of core cog '{cog_name}' for guild {guild_id} - ignored.")


    # Check if all requested updates were successful
    if all(success_flags):
        return {"message": "Settings updated successfully."}
    else:
        # Return a partial success or error? For now, generic error if any failed.
        raise HTTPException(status_code=500, detail="One or more settings failed to update. Check server logs.")


# --- Command Permission Endpoints ---

@app.get("/api/guilds/{guild_id}/permissions", response_model=CommandPermissionsResponse, tags=["Guild Settings"])
async def get_all_guild_command_permissions(
    guild_id: int,
    current_user: dict = Depends(get_current_user),
    is_admin: bool = Depends(verify_guild_admin)
):
    """Fetches all command permissions currently set for the guild."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Fetching all command permissions for guild {guild_id} requested by user {current_user['user_id']}")
    permissions_map: Dict[str, List[str]] = {}
    try:
        # Fetch all permissions directly from DB for this guild
        async with settings_manager.pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT command_name, allowed_role_id FROM command_permissions WHERE guild_id = $1 ORDER BY command_name, allowed_role_id",
                guild_id
            )
        for record in records:
            cmd = record['command_name']
            role_id_str = str(record['allowed_role_id'])
            if cmd not in permissions_map:
                permissions_map[cmd] = []
            permissions_map[cmd].append(role_id_str)

        return CommandPermissionsResponse(permissions=permissions_map)

    except Exception as e:
        log.exception(f"Database error fetching all command permissions for guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch command permissions.")


@app.post("/api/guilds/{guild_id}/permissions", status_code=status.HTTP_201_CREATED, tags=["Guild Settings"])
async def add_guild_command_permission(
    guild_id: int,
    permission: CommandPermission,
    current_user: dict = Depends(get_current_user),
    is_admin: bool = Depends(verify_guild_admin)
):
    """Adds a role permission for a specific command."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Adding command permission for command '{permission.command_name}', role '{permission.role_id}' in guild {guild_id} requested by user {current_user['user_id']}")

    try:
        # Validate role_id format
        role_id = int(permission.role_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role_id format. Must be numeric.")

    # TODO: Validate command_name against actual bot commands? Difficult without bot interaction.

    success = await settings_manager.add_command_permission(guild_id, permission.command_name, role_id)

    if success:
        # Return the created permission details or just a success message
        return {"message": "Permission added successfully.", "command": permission.command_name, "role_id": permission.role_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to add command permission. Check server logs.")


@app.delete("/api/guilds/{guild_id}/permissions", status_code=status.HTTP_200_OK, tags=["Guild Settings"])
async def remove_guild_command_permission(
    guild_id: int,
    permission: CommandPermission, # Use the same model for identifying the permission to delete
    current_user: dict = Depends(get_current_user),
    is_admin: bool = Depends(verify_guild_admin)
):
    """Removes a role permission for a specific command."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Removing command permission for command '{permission.command_name}', role '{permission.role_id}' in guild {guild_id} requested by user {current_user['user_id']}")

    try:
        role_id = int(permission.role_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role_id format. Must be numeric.")

    success = await settings_manager.remove_command_permission(guild_id, permission.command_name, role_id)

    if success:
        return {"message": "Permission removed successfully.", "command": permission.command_name, "role_id": permission.role_id}
    else:
        # Could be a 404 if permission didn't exist, but 500 is safer if DB fails
        raise HTTPException(status_code=500, detail="Failed to remove command permission. Check server logs.")
