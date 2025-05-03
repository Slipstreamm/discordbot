import os
import json
import asyncio
import datetime
from typing import Dict, List, Optional, Any, Union
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware # Import SessionMiddleware
import aiohttp
from database import Database # Existing DB
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Dict, List, Optional, Any, Union # Ensure this is imported

# --- Configuration Loading ---
# Determine the path to the .env file relative to this api_server.py file
# Go up one level from api_service/ to the project root, then into discordbot/
dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'discordbot', '.env')

class ApiSettings(BaseSettings):
    # Existing API settings (if any were loaded from env before)
    GURT_STATS_PUSH_SECRET: Optional[str] = None
    API_HOST: str = "0.0.0.0" # Keep existing default if used
    API_PORT: int = 443      # Keep existing default if used
    SSL_CERT_FILE: Optional[str] = None
    SSL_KEY_FILE: Optional[str] = None

    # Discord OAuth Credentials (from discordbot/.env)
    DISCORD_CLIENT_ID: str
    DISCORD_CLIENT_SECRET: str
    DISCORD_REDIRECT_URI: str

    # Secret key for dashboard session management
    DASHBOARD_SECRET_KEY: str = "a_default_secret_key_for_development_only" # Provide a default for dev

    # Database/Redis settings (Required for settings_manager)
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_SETTINGS_DB: str # The specific DB for settings
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None # Optional

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

# --- Constants derived from settings ---
DISCORD_API_BASE_URL = "https://discord.com/api/v10"
DISCORD_AUTH_URL = (
    f"https://discord.com/api/oauth2/authorize?client_id={settings.DISCORD_CLIENT_ID}"
    f"&redirect_uri={settings.DISCORD_REDIRECT_URI}&response_type=code&scope=identify guilds"
)
DISCORD_TOKEN_URL = f"{DISCORD_API_BASE_URL}/oauth2/token"
DISCORD_USER_URL = f"{DISCORD_API_BASE_URL}/users/@me"
DISCORD_USER_GUILDS_URL = f"{DISCORD_API_BASE_URL}/users/@me/guilds"


# --- Gurt Stats Storage (IPC) ---
latest_gurt_stats: Optional[Dict[str, Any]] = None
# GURT_STATS_PUSH_SECRET is now loaded via ApiSettings
if not settings.GURT_STATS_PUSH_SECRET:
    print("Warning: GURT_STATS_PUSH_SECRET not set. Internal stats update endpoint will be insecure.")
# ---------------------------------

from api_models import (
    Conversation,
    UserSettings,
    Message,
    GetConversationsResponse,
    GetSettingsResponse,
    UpdateSettingsRequest,
    UpdateConversationRequest,
    ApiResponse
)
import code_verifier_store

# Ensure discordbot is in path to import settings_manager
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from discordbot import settings_manager
except ImportError as e:
    print(f"ERROR: Could not import discordbot.settings_manager: {e}")
    print("Ensure the API is run from the project root or discordbot is in PYTHONPATH.")
    settings_manager = None # Set to None to indicate failure

# ============= API Setup =============

# Create the FastAPI app
app = FastAPI(title="Unified API Service")

# Add Session Middleware for Dashboard Auth
# Uses DASHBOARD_SECRET_KEY from settings
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.DASHBOARD_SECRET_KEY,
    session_cookie="dashboard_session", # Use a distinct cookie name
    max_age=60 * 60 * 24 * 7 # 7 days expiry
)

# Create a sub-application for the API with /api prefix
api_app = FastAPI(title="Unified API Service", docs_url="/docs", openapi_url="/openapi.json")

# Create a sub-application for backward compatibility with /discordapi prefix
# This will be deprecated in the future
discordapi_app = FastAPI(
    title="Discord Bot Sync API (DEPRECATED)",
    docs_url="/docs",
    openapi_url="/openapi.json",
    description="This API is deprecated and will be removed in the future. Please use the /api endpoint instead."
)

# Create a sub-application for the new Dashboard API
dashboard_api_app = FastAPI(
    title="Bot Dashboard API",
    docs_url="/docs", # Can have its own docs
    openapi_url="/openapi.json"
)

# Mount the API apps at their respective paths
app.mount("/api", api_app)
app.mount("/discordapi", discordapi_app)
app.mount("/dashboard/api", dashboard_api_app) # Mount the new dashboard API

# Create a middleware for redirecting /discordapi to /api with a deprecation warning
class DeprecationRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Check if the path starts with /discordapi
        if request.url.path.startswith('/discordapi'):
            # Add a deprecation warning header
            response = await call_next(request)
            response.headers['X-API-Deprecation-Warning'] = 'This endpoint is deprecated. Please use /api instead.'
            return response
        return await call_next(request)

# Add CORS middleware to all apps
for current_app in [app, api_app, discordapi_app]:
    current_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Adjust this in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Add the deprecation middleware to the main app
app.add_middleware(DeprecationRedirectMiddleware)

# Initialize database (existing)
db = Database()

# --- aiohttp Session for Discord API calls ---
http_session = None

# ============= Authentication =============

async def verify_discord_token(authorization: str = Header(None)) -> str:
    """Verify the Discord token and return the user ID"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.replace("Bearer ", "")

    # Verify the token with Discord
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=401, detail="Invalid Discord token")

            user_data = await resp.json()
            return user_data["id"]

# ============= API Endpoints =============

@app.get("/")
async def root():
    return {"message": "Unified API Service is running"}

# Add root for dashboard API for clarity
@dashboard_api_app.get("/")
async def dashboard_api_root():
     return {"message": "Bot Dashboard API is running"}


@discordapi_app.get("/")
async def discordapi_root():
    return {
        "message": "DEPRECATED: This API endpoint (/discordapi) is deprecated and will be removed in the future.",
        "recommendation": "Please update your client to use the /api endpoint instead.",
        "new_endpoint": "/api"
    }

# Discord OAuth configuration now loaded via ApiSettings above
# DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1360717457852993576")
# DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://slipstreamm.dev/api/auth")
# DISCORD_API_ENDPOINT = "https://discord.com/api/v10"
# DISCORD_TOKEN_URL = f"{DISCORD_API_ENDPOINT}/oauth2/token"

# The existing /auth endpoint seems to handle a different OAuth flow (PKCE, no client secret)
# than the one needed for the dashboard (Authorization Code Grant with client secret).
# We will add the new dashboard auth flow under a different path prefix, e.g., /dashboard/api/auth/...
# Keep the existing /auth endpoint as is for now.

# @app.get("/auth") # Keep existing
@api_app.get("/auth")
@discordapi_app.get("/auth")
async def auth(code: str, state: str = None, code_verifier: str = None, request: Request = None):
    """Handle OAuth callback from Discord"""
    try:
        # Log the request details for debugging
        print(f"Received OAuth callback with code: {code[:10]}...")
        print(f"State: {state}")
        print(f"Code verifier provided: {code_verifier is not None}")
        print(f"Request URL: {request.url if request else 'No request object'}")
        print(f"Configured redirect URI: {DISCORD_REDIRECT_URI}")

        # Exchange the code for a token
        async with aiohttp.ClientSession() as session:
            # For public clients, we don't include a client secret
            # We use PKCE for security
            # Get the actual redirect URI that Discord used
            # This is important because we need to use the same redirect URI when exchanging the code
            actual_redirect_uri = DISCORD_REDIRECT_URI

            # If the request has a referer header, use that to extract the redirect URI
            referer = request.headers.get("referer") if request else None
            if referer and "code=" in referer:
                # Extract the redirect URI from the referer
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(referer)
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                print(f"Extracted base URL from referer: {base_url}")

                # Use this as the redirect URI if it's different from the configured one
                if base_url != DISCORD_REDIRECT_URI:
                    print(f"Using redirect URI from referer: {base_url}")
                    actual_redirect_uri = base_url

            data = {
                "client_id": settings.DISCORD_CLIENT_ID, # Use loaded setting
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": actual_redirect_uri,
            }

            # Add code_verifier if provided directly
            if code_verifier:
                data["code_verifier"] = code_verifier
                print(f"Using provided code_verifier parameter: {code_verifier[:10]}...")
            else:
                # Try to get the code verifier from the store using the state parameter
                stored_code_verifier = code_verifier_store.get_code_verifier(state) if state else None
                if stored_code_verifier:
                    data["code_verifier"] = stored_code_verifier
                    print(f"Using code_verifier from store for state {state}: {stored_code_verifier[:10]}...")
                    # Remove the code verifier from the store after using it
                    code_verifier_store.remove_code_verifier(state)
                else:
                    print(f"Warning: No code_verifier found for state {state}")

            # Log the token exchange request for debugging
            print(f"Exchanging code for token with data: {data}")

            async with session.post(DISCORD_TOKEN_URL, data=data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"Failed to exchange code: {error_text}")
                    return {"message": "Authentication failed", "error": error_text}

                token_data = await resp.json()

                # Get the user's information
                access_token = token_data.get("access_token")
                if not access_token:
                    return {"message": "Authentication failed", "error": "No access token in response"}

                # Get the user's Discord ID
                headers = {"Authorization": f"Bearer {access_token}"}
                async with session.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=headers) as user_resp:
                    if user_resp.status != 200:
                        error_text = await user_resp.text()
                        print(f"Failed to get user info: {error_text}")
                        return {"message": "Authentication failed", "error": error_text}

                    user_data = await user_resp.json()
                    user_id = user_data.get("id")

                    if not user_id:
                        return {"message": "Authentication failed", "error": "No user ID in response"}

                    # Store the token in the database
                    db.save_user_token(user_id, token_data)
                    print(f"Successfully authenticated user {user_id} and saved token")

                    # Check if this is a programmatic request (from the bot) or a browser request
                    accept_header = request.headers.get("accept", "")
                    is_browser = "text/html" in accept_header.lower()

                    if is_browser:
                        # Return a success page with instructions for browser requests
                        html_content = f"""
                        <html>
                            <head>
                                <title>Authentication Successful</title>
                                <style>
                                    body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                                    .success {{ color: green; }}
                                    .info {{ margin-top: 20px; }}
                                </style>
                            </head>
                            <body>
                                <h1 class="success">Authentication Successful!</h1>
                                <p>You have successfully authenticated with Discord.</p>
                                <div class="info">
                                    <p>You can now close this window and return to Discord.</p>
                                    <p>Your Discord bot is now authorized to access the API on your behalf.</p>
                                </div>
                            </body>
                        </html>
                        """

                        return Response(content=html_content, media_type="text/html")
                    else:
                        # Return JSON response with token for programmatic requests
                        return {
                            "message": "Authentication successful",
                            "user_id": user_id,
                            "token": token_data
                        }
    except Exception as e:
        print(f"Error in auth endpoint: {str(e)}")
        return {"message": "Authentication failed", "error": str(e)}


# ============= Dashboard API Models & Dependencies =============
# (Copied from previous dashboard_api/main.py logic)

from pydantic import BaseModel, Field # Ensure BaseModel/Field are imported if not already

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

class CommandPermission(BaseModel):
    command_name: str
    role_id: str # Keep as string for consistency

class CommandPermissionsResponse(BaseModel):
    permissions: Dict[str, List[str]] # Command name -> List of allowed role IDs

# --- Authentication Dependency (Dashboard Specific) ---
# Note: This uses session cookies set by the dashboard auth flow
async def get_dashboard_user(request: Request) -> dict:
    """Dependency to check if user is authenticated via dashboard session and return user data."""
    user_id = request.session.get('user_id')
    username = request.session.get('username')
    access_token = request.session.get('access_token') # Needed for subsequent Discord API calls

    if not user_id or not username or not access_token:
        logging.warning("Dashboard: Attempted access by unauthenticated user.")
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
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    user_headers = {'Authorization': f'Bearer {current_user["access_token"]}'}
    try:
        log.debug(f"Dashboard: Verifying admin status for user {current_user['user_id']} in guild {guild_id}")
        async with http_session.get(DISCORD_USER_GUILDS_URL, headers=user_headers) as resp:
            if resp.status == 401:
                # Clear session if token is invalid
                # request.session.clear() # Cannot access request here directly
                raise HTTPException(status_code=401, detail="Discord token invalid or expired. Please re-login.")
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
            log.warning(f"Dashboard: User {current_user['user_id']} is not admin or not in guild {guild_id}.")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not an administrator of this guild.")

        log.debug(f"Dashboard: User {current_user['user_id']} verified as admin for guild {guild_id}.")
        return True # Indicate verification success

    except aiohttp.ClientResponseError as e:
        log.exception(f"Dashboard: HTTP error verifying guild admin status: {e.status} {e.message}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Dashboard: Generic error verifying guild admin status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred during permission verification.")


# ============= Dashboard API Routes =============
# (Mounted under /dashboard/api)

# --- Dashboard Authentication Routes ---
@dashboard_api_app.get("/auth/login", tags=["Dashboard Authentication"])
async def dashboard_login():
    """Redirects the user to Discord for OAuth2 authorization (Dashboard Flow)."""
    # Uses constants derived from settings loaded at the top
    log.info(f"Dashboard: Redirecting user to Discord auth URL: {DISCORD_AUTH_URL}")
    return RedirectResponse(url=DISCORD_AUTH_URL, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@dashboard_api_app.get("/auth/callback", tags=["Dashboard Authentication"])
async def dashboard_auth_callback(request: Request, code: str | None = None, error: str | None = None):
    """Handles the callback from Discord after authorization (Dashboard Flow)."""
    global http_session # Use the global aiohttp session
    if error:
        log.error(f"Dashboard: Discord OAuth error: {error}")
        return RedirectResponse(url="/dashboard?error=discord_auth_failed") # Redirect to frontend dashboard root

    if not code:
        log.error("Dashboard: Discord OAuth callback missing code.")
        return RedirectResponse(url="/dashboard?error=missing_code")

    if not http_session:
         log.error("Dashboard: aiohttp session not initialized.")
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    try:
        # 1. Exchange code for access token
        token_data = {
            'client_id': settings.DISCORD_CLIENT_ID,
            'client_secret': settings.DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.DISCORD_REDIRECT_URI # Must match exactly
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        log.debug(f"Dashboard: Exchanging code for token at {DISCORD_TOKEN_URL}")
        async with http_session.post(DISCORD_TOKEN_URL, data=token_data, headers=headers) as resp:
            resp.raise_for_status()
            token_response = await resp.json()
            access_token = token_response.get('access_token')
            log.debug("Dashboard: Token exchange successful.")

        if not access_token:
            log.error("Dashboard: Failed to get access token from Discord response.")
            raise HTTPException(status_code=500, detail="Could not retrieve access token from Discord.")

        # 2. Fetch user data
        user_headers = {'Authorization': f'Bearer {access_token}'}
        log.debug(f"Dashboard: Fetching user data from {DISCORD_USER_URL}")
        async with http_session.get(DISCORD_USER_URL, headers=user_headers) as resp:
            resp.raise_for_status()
            user_data = await resp.json()
            log.debug(f"Dashboard: User data fetched successfully for user ID: {user_data.get('id')}")

        # 3. Store in session
        request.session['user_id'] = user_data.get('id')
        request.session['username'] = user_data.get('username')
        request.session['avatar'] = user_data.get('avatar')
        request.session['access_token'] = access_token

        log.info(f"Dashboard: User {user_data.get('username')} ({user_data.get('id')}) logged in successfully.")
        # Redirect user back to the main dashboard page (served by static files)
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    except aiohttp.ClientResponseError as e:
        log.exception(f"Dashboard: HTTP error during Discord OAuth callback: {e.status} {e.message}")
        error_detail = "Unknown Discord API error"
        try:
            error_body = await e.response.json()
            error_detail = error_body.get("error_description", error_detail)
        except Exception: pass
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error communicating with Discord: {error_detail}")
    except Exception as e:
        log.exception(f"Dashboard: Generic error during Discord OAuth callback: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred during authentication.")

@dashboard_api_app.post("/auth/logout", tags=["Dashboard Authentication"], status_code=status.HTTP_204_NO_CONTENT)
async def dashboard_logout(request: Request):
    """Clears the dashboard user session."""
    user_id = request.session.get('user_id')
    request.session.clear()
    log.info(f"Dashboard: User {user_id} logged out.")
    return

# --- Dashboard User Endpoints ---
@dashboard_api_app.get("/user/me", tags=["Dashboard User"])
async def dashboard_get_user_me(current_user: dict = Depends(get_dashboard_user)):
    """Returns information about the currently logged-in dashboard user."""
    user_info = current_user.copy()
    # del user_info['access_token'] # Optional: Don't expose token to frontend
    return user_info

@dashboard_api_app.get("/user/guilds", tags=["Dashboard User"])
async def dashboard_get_user_guilds(current_user: dict = Depends(get_dashboard_user)):
    """Returns a list of guilds the user is an administrator in AND the bot is also in."""
    global http_session # Use the global aiohttp session
    if not http_session:
         log.error("Dashboard: aiohttp session not initialized.")
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")
    if not settings_manager:
        log.error("Dashboard: settings_manager not available.")
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    access_token = current_user['access_token']
    user_headers = {'Authorization': f'Bearer {access_token}'}

    try:
        # 1. Fetch guilds user is in from Discord
        log.debug(f"Dashboard: Fetching user guilds from {DISCORD_USER_GUILDS_URL}")
        async with http_session.get(DISCORD_USER_GUILDS_URL, headers=user_headers) as resp:
            resp.raise_for_status()
            user_guilds = await resp.json()
        log.debug(f"Dashboard: Fetched {len(user_guilds)} guilds for user {current_user['user_id']}")

        # 2. Fetch guilds the bot is in from our DB
        bot_guild_ids = await settings_manager.get_bot_guild_ids()
        if bot_guild_ids is None:
            log.error("Dashboard: Failed to fetch bot guild IDs from settings_manager.")
            raise HTTPException(status_code=500, detail="Could not retrieve bot's guild list.")

        # 3. Filter user guilds
        manageable_guilds = []
        ADMINISTRATOR_PERMISSION = 0x8
        for guild in user_guilds:
            guild_id = int(guild['id'])
            permissions = int(guild['permissions'])

            if (permissions & ADMINISTRATOR_PERMISSION) == ADMINISTRATOR_PERMISSION and guild_id in bot_guild_ids:
                manageable_guilds.append({
                    "id": guild['id'],
                    "name": guild['name'],
                    "icon": guild.get('icon'),
                })

        log.info(f"Dashboard: Found {len(manageable_guilds)} manageable guilds for user {current_user['user_id']}")
        return manageable_guilds

    except aiohttp.ClientResponseError as e:
        log.exception(f"Dashboard: HTTP error fetching user guilds: {e.status} {e.message}")
        if e.status == 401:
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Discord token invalid or expired. Please re-login.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Dashboard: Generic error fetching user guilds: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching guilds.")

# --- Dashboard Guild Settings Endpoints ---
@dashboard_api_app.get("/guilds/{guild_id}/settings", response_model=GuildSettingsResponse, tags=["Dashboard Guild Settings"])
async def dashboard_get_guild_settings(
    guild_id: int,
    current_user: dict = Depends(get_dashboard_user),
    is_admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Fetches the current settings for a specific guild for the dashboard."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Dashboard: Fetching settings for guild {guild_id} requested by user {current_user['user_id']}")

    prefix = await settings_manager.get_guild_prefix(guild_id, "!") # Use default prefix constant
    wc_id = await settings_manager.get_setting(guild_id, 'welcome_channel_id')
    wc_msg = await settings_manager.get_setting(guild_id, 'welcome_message')
    gc_id = await settings_manager.get_setting(guild_id, 'goodbye_channel_id')
    gc_msg = await settings_manager.get_setting(guild_id, 'goodbye_message')

    known_cogs_in_db = {}
    try:
        # Need to acquire connection from pool managed by settings_manager
        if settings_manager.pg_pool:
             async with settings_manager.pg_pool.acquire() as conn:
                records = await conn.fetch("SELECT cog_name, enabled FROM enabled_cogs WHERE guild_id = $1", guild_id)
                for record in records:
                    known_cogs_in_db[record['cog_name']] = record['enabled']
        else:
             log.error("Dashboard: settings_manager pg_pool not initialized.")
             # Decide how to handle - return empty or error?
    except Exception as e:
        log.exception(f"Dashboard: Failed to fetch cog statuses from DB for guild {guild_id}: {e}")

    # Fetch command permissions
    permissions_map: Dict[str, List[str]] = {}
    try:
        if settings_manager.pg_pool:
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
    except Exception as e:
        log.exception(f"Dashboard: Failed to fetch command permissions from DB for guild {guild_id}: {e}")


    settings_data = GuildSettingsResponse(
        guild_id=str(guild_id),
        prefix=prefix,
        welcome_channel_id=wc_id if wc_id != "__NONE__" else None,
        welcome_message=wc_msg if wc_msg != "__NONE__" else None,
        goodbye_channel_id=gc_id if gc_id != "__NONE__" else None,
        goodbye_message=gc_msg if gc_msg != "__NONE__" else None,
        enabled_cogs=known_cogs_in_db,
        command_permissions=permissions_map
    )
    return settings_data

@dashboard_api_app.patch("/guilds/{guild_id}/settings", status_code=status.HTTP_200_OK, tags=["Dashboard Guild Settings"])
async def dashboard_update_guild_settings(
    guild_id: int,
    settings_update: GuildSettingsUpdate,
    current_user: dict = Depends(get_dashboard_user),
    is_admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Updates specific settings for a guild via the dashboard."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Dashboard: Updating settings for guild {guild_id} requested by user {current_user['user_id']}")
    update_data = settings_update.model_dump(exclude_unset=True)
    log.debug(f"Dashboard: Update data received: {update_data}")

    success_flags = []
    core_cogs_list = {'SettingsCog', 'HelpCog'} # TODO: Get this reliably

    if 'prefix' in update_data:
        success = await settings_manager.set_guild_prefix(guild_id, update_data['prefix'])
        success_flags.append(success)
        if not success: log.error(f"Dashboard: Failed to update prefix for guild {guild_id}")
    if 'welcome_channel_id' in update_data:
        value = update_data['welcome_channel_id'] if update_data['welcome_channel_id'] else None
        success = await settings_manager.set_setting(guild_id, 'welcome_channel_id', value)
        success_flags.append(success)
        if not success: log.error(f"Dashboard: Failed to update welcome_channel_id for guild {guild_id}")
    if 'welcome_message' in update_data:
        success = await settings_manager.set_setting(guild_id, 'welcome_message', update_data['welcome_message'])
        success_flags.append(success)
        if not success: log.error(f"Dashboard: Failed to update welcome_message for guild {guild_id}")
    if 'goodbye_channel_id' in update_data:
        value = update_data['goodbye_channel_id'] if update_data['goodbye_channel_id'] else None
        success = await settings_manager.set_setting(guild_id, 'goodbye_channel_id', value)
        success_flags.append(success)
        if not success: log.error(f"Dashboard: Failed to update goodbye_channel_id for guild {guild_id}")
    if 'goodbye_message' in update_data:
        success = await settings_manager.set_setting(guild_id, 'goodbye_message', update_data['goodbye_message'])
        success_flags.append(success)
        if not success: log.error(f"Dashboard: Failed to update goodbye_message for guild {guild_id}")
    if 'cogs' in update_data and update_data['cogs'] is not None:
        for cog_name, enabled_status in update_data['cogs'].items():
            if cog_name not in core_cogs_list:
                success = await settings_manager.set_cog_enabled(guild_id, cog_name, enabled_status)
                success_flags.append(success)
                if not success: log.error(f"Dashboard: Failed to update status for cog '{cog_name}' for guild {guild_id}")
            else:
                log.warning(f"Dashboard: Attempted to change status of core cog '{cog_name}' for guild {guild_id} - ignored.")

    if all(s is True for s in success_flags): # Check if all operations returned True
        return {"message": "Settings updated successfully."}
    else:
        raise HTTPException(status_code=500, detail="One or more settings failed to update. Check server logs.")

# --- Dashboard Command Permission Endpoints ---
@dashboard_api_app.get("/guilds/{guild_id}/permissions", response_model=CommandPermissionsResponse, tags=["Dashboard Guild Settings"])
async def dashboard_get_all_guild_command_permissions(
    guild_id: int,
    current_user: dict = Depends(get_dashboard_user),
    is_admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Fetches all command permissions currently set for the guild for the dashboard."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Dashboard: Fetching all command permissions for guild {guild_id} requested by user {current_user['user_id']}")
    permissions_map: Dict[str, List[str]] = {}
    try:
        if settings_manager.pg_pool:
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
        else:
             log.error("Dashboard: settings_manager pg_pool not initialized.")

        return CommandPermissionsResponse(permissions=permissions_map)

    except Exception as e:
        log.exception(f"Dashboard: Database error fetching all command permissions for guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch command permissions.")

@dashboard_api_app.post("/guilds/{guild_id}/permissions", status_code=status.HTTP_201_CREATED, tags=["Dashboard Guild Settings"])
async def dashboard_add_guild_command_permission(
    guild_id: int,
    permission: CommandPermission,
    current_user: dict = Depends(get_dashboard_user),
    is_admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Adds a role permission for a specific command via the dashboard."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Dashboard: Adding command permission for command '{permission.command_name}', role '{permission.role_id}' in guild {guild_id} requested by user {current_user['user_id']}")

    try:
        role_id = int(permission.role_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role_id format. Must be numeric.")

    success = await settings_manager.add_command_permission(guild_id, permission.command_name, role_id)

    if success:
        return {"message": "Permission added successfully.", "command": permission.command_name, "role_id": permission.role_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to add command permission. Check server logs.")

@dashboard_api_app.delete("/guilds/{guild_id}/permissions", status_code=status.HTTP_200_OK, tags=["Dashboard Guild Settings"])
async def dashboard_remove_guild_command_permission(
    guild_id: int,
    permission: CommandPermission,
    current_user: dict = Depends(get_dashboard_user),
    is_admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Removes a role permission for a specific command via the dashboard."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Dashboard: Removing command permission for command '{permission.command_name}', role '{permission.role_id}' in guild {guild_id} requested by user {current_user['user_id']}")

    try:
        role_id = int(permission.role_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role_id format. Must be numeric.")

    success = await settings_manager.remove_command_permission(guild_id, permission.command_name, role_id)

    if success:
        return {"message": "Permission removed successfully.", "command": permission.command_name, "role_id": permission.role_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to remove command permission. Check server logs.")


# ============= Conversation Endpoints =============
# (Keep existing conversation/settings endpoints under /api and /discordapi)

@api_app.get("/conversations", response_model=GetConversationsResponse)
@discordapi_app.get("/conversations", response_model=GetConversationsResponse)
async def get_conversations(user_id: str = Depends(verify_discord_token)):
    """Get all conversations for a user"""
    conversations = db.get_user_conversations(user_id)
    return {"conversations": conversations}

@api_app.get("/conversations/{conversation_id}")
@discordapi_app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user_id: str = Depends(verify_discord_token)):
    """Get a specific conversation for a user"""
    conversation = db.get_conversation(user_id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation

@api_app.post("/conversations", response_model=Conversation)
@discordapi_app.post("/conversations", response_model=Conversation)
async def create_conversation(
    conversation_request: UpdateConversationRequest,
    user_id: str = Depends(verify_discord_token)
):
    """Create or update a conversation for a user"""
    conversation = conversation_request.conversation
    return db.save_conversation(user_id, conversation)

@api_app.put("/conversations/{conversation_id}", response_model=Conversation)
@discordapi_app.put("/conversations/{conversation_id}", response_model=Conversation)
async def update_conversation(
    conversation_id: str,
    conversation_request: UpdateConversationRequest,
    user_id: str = Depends(verify_discord_token)
):
    """Update a specific conversation for a user"""
    conversation = conversation_request.conversation

    # Ensure the conversation ID in the path matches the one in the request
    if conversation_id != conversation.id:
        raise HTTPException(status_code=400, detail="Conversation ID mismatch")

    # Check if the conversation exists
    existing_conversation = db.get_conversation(user_id, conversation_id)
    if not existing_conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return db.save_conversation(user_id, conversation)

@api_app.delete("/conversations/{conversation_id}", response_model=ApiResponse)
@discordapi_app.delete("/conversations/{conversation_id}", response_model=ApiResponse)
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(verify_discord_token)
):
    """Delete a specific conversation for a user"""
    success = db.delete_conversation(user_id, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"success": True, "message": "Conversation deleted successfully"}

# ============= Settings Endpoints =============

@api_app.get("/settings")
@discordapi_app.get("/settings")
async def get_settings(user_id: str = Depends(verify_discord_token)):
    """Get settings for a user"""
    settings = db.get_user_settings(user_id)
    # Return both formats for compatibility
    return {"settings": settings, "user_settings": settings}

@api_app.put("/settings", response_model=UserSettings)
@discordapi_app.put("/settings", response_model=UserSettings)
async def update_settings_put(
    settings_request: UpdateSettingsRequest,
    user_id: str = Depends(verify_discord_token)
):
    """Update settings for a user using PUT method"""
    settings = settings_request.settings
    return db.save_user_settings(user_id, settings)

@api_app.post("/settings", response_model=UserSettings)
@discordapi_app.post("/settings", response_model=UserSettings)
async def update_settings_post(
    request: Request,
    user_id: str = Depends(verify_discord_token)
):
    """Update settings for a user using POST method (for Flutter app compatibility)"""
    try:
        # Parse the request body with UTF-8 encoding
        body_text = await request.body()
        body = json.loads(body_text.decode('utf-8'))

        # Log the received body for debugging
        print(f"Received settings POST request with body: {body}")

        # Check if the settings are wrapped in a 'user_settings' field (Flutter app format)
        if "user_settings" in body:
            settings_data = body["user_settings"]
            try:
                settings = UserSettings.model_validate(settings_data)
                # Save the settings and return the result
                result = db.save_user_settings(user_id, settings)
                print(f"Saved settings for user {user_id} from 'user_settings' field")
                return result
            except Exception as e:
                print(f"Error validating user_settings: {e}")
                # Fall through to try other formats

        # Try standard format with 'settings' field
        if "settings" in body:
            settings_data = body["settings"]
            try:
                settings = UserSettings.model_validate(settings_data)
                # Save the settings and return the result
                result = db.save_user_settings(user_id, settings)
                print(f"Saved settings for user {user_id} from 'settings' field")
                return result
            except Exception as e:
                print(f"Error validating settings field: {e}")
                # Fall through to try other formats

        # Try direct format (body is the settings object itself)
        try:
            settings = UserSettings.model_validate(body)
            # Save the settings and return the result
            result = db.save_user_settings(user_id, settings)
            print(f"Saved settings for user {user_id} from direct body")
            return result
        except Exception as e:
            print(f"Error validating direct body: {e}")
            # Fall through to final error

        # If we get here, none of the formats worked
        raise ValueError("Could not parse settings from any expected format")
    except Exception as e:
        print(f"Error in update_settings_post: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid settings format: {str(e)}")

# ============= Backward Compatibility Endpoints =============

# Define the sync function to be reused by both endpoints
async def _sync_conversations(request: Request, user_id: str):
    try:
        # Parse the request body with UTF-8 encoding
        body_text = await request.body()
        body = json.loads(body_text.decode('utf-8'))

        # Log the received body for debugging
        print(f"Received sync request with body: {body}")

        # Get conversations from the request
        request_conversations = body.get("conversations", [])

        # Get last sync time (for future use with incremental sync)
        # Store the last sync time for future use
        _ = body.get("last_sync_time")  # Currently unused, will be used for incremental sync in the future

        # Get user settings from the request if available
        user_settings_data = body.get("user_settings")
        if user_settings_data:
            # Save user settings
            try:
                settings = UserSettings.model_validate(user_settings_data)
                settings = db.save_user_settings(user_id, settings)
                print(f"Saved user settings for {user_id} during sync")
            except Exception as e:
                print(f"Error saving user settings during sync: {e}")

        # Get all conversations for the user
        user_conversations = db.get_user_conversations(user_id)
        print(f"Retrieved {len(user_conversations)} conversations for user {user_id}")

        # Process incoming conversations
        for conv_data in request_conversations:
            try:
                conversation = Conversation.model_validate(conv_data)
                db.save_conversation(user_id, conversation)
                print(f"Saved conversation {conversation.id} for user {user_id}")
            except Exception as e:
                print(f"Error saving conversation: {e}")

        # Get the user's settings
        settings = db.get_user_settings(user_id)
        print(f"Retrieved settings for user {user_id}")

        # Return all conversations and settings
        response = {
            "success": True,
            "message": "Sync successful",
            "conversations": user_conversations,
        }

        # Add settings to the response if available
        if settings:
            # Include both 'settings' and 'user_settings' for compatibility
            response["settings"] = settings
            response["user_settings"] = settings

        return response
    except Exception as e:
        print(f"Sync failed: {str(e)}")
        return {
            "success": False,
            "message": f"Sync failed: {str(e)}",
            "conversations": []
        }

@api_app.post("/sync")
async def api_sync_conversations(request: Request, user_id: str = Depends(verify_discord_token)):
    """Sync conversations and settings"""
    return await _sync_conversations(request, user_id)

@discordapi_app.post("/sync")
async def discordapi_sync_conversations(request: Request, user_id: str = Depends(verify_discord_token)):
    """Backward compatibility endpoint for syncing conversations"""
    response = await _sync_conversations(request, user_id)
    # Add deprecation warning to the response
    if isinstance(response, dict):
        response["deprecated"] = True
        response["deprecation_message"] = "This endpoint (/discordapi/sync) is deprecated. Please use /api/sync instead."
    return response

# ============= Server Startup/Shutdown Events =============

@app.on_event("startup")
async def startup_event():
    """Initialize resources on API startup."""
    global http_session
    # Initialize existing database
    db.load_data()
    log.info("Existing database loaded.")
    # Start aiohttp session
    http_session = aiohttp.ClientSession()
    log.info("aiohttp session started.")
    # Initialize settings_manager pools if available
    # REMOVED: Pool initialization is handled by the main bot process (discordbot/main.py)
    # The API will rely on the pools being initialized before it receives requests.
    if not settings_manager:
         log.error("settings_manager not imported. Dashboard endpoints requiring DB/cache will fail.")
    elif not settings_manager.pg_pool or not settings_manager.redis_pool:
         log.warning("settings_manager pools appear uninitialized. Ensure the main bot initializes them.")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on API shutdown."""
    global http_session # Ensure http_session is accessible
    # Save existing database data
    db.save_data()
    log.info("Existing database saved.")
    # Close aiohttp session
    if http_session:
        await http_session.close()
        log.info("aiohttp session closed.")
    # Close settings_manager pools if available and initialized
    # REMOVED: Pool closing is handled by the main bot process (discordbot/main.py)
    # if settings_manager and settings_manager.pg_pool: # Check if pool was initialized
    #     await settings_manager.close_pools()
    #     log.info("Settings manager pools closed.")


# ============= Code Verifier Endpoints =============

@api_app.post("/code_verifier")
@discordapi_app.post("/code_verifier")
async def store_code_verifier(request: Request):
    """Store a code verifier for a state"""
    try:
        body_text = await request.body()
        data = json.loads(body_text.decode('utf-8'))
        state = data.get("state")
        code_verifier = data.get("code_verifier")

        if not state or not code_verifier:
            raise HTTPException(status_code=400, detail="Missing state or code_verifier")

        code_verifier_store.store_code_verifier(state, code_verifier)
        return {"success": True, "message": "Code verifier stored successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error storing code verifier: {str(e)}")

@api_app.get("/code_verifier/{state}")
@discordapi_app.get("/code_verifier/{state}")
async def get_code_verifier(state: str):
    """Get the code verifier for a state"""
    code_verifier = code_verifier_store.get_code_verifier(state)
    if not code_verifier:
        raise HTTPException(status_code=404, detail="No code verifier found for this state")

    return {"code_verifier": code_verifier}

# ============= Token Endpoints =============

@api_app.get("/token")
@discordapi_app.get("/token")
async def get_token(user_id: str = Depends(verify_discord_token)):
    """Get the token for a user"""
    token_data = db.get_user_token(user_id)
    if not token_data:
        raise HTTPException(status_code=404, detail="No token found for this user")

    # Return only the access token, not the full token data
    return {"access_token": token_data.get("access_token")}

@api_app.get("/token/{user_id}")
@discordapi_app.get("/token/{user_id}")
async def get_token_by_user_id(user_id: str):
    """Get the token for a specific user by ID (for bot use)"""
    token_data = db.get_user_token(user_id)
    if not token_data:
        raise HTTPException(status_code=404, detail="No token found for this user")

    # Return the full token data for the bot to save
    return token_data

@api_app.get("/check_auth/{user_id}")
@discordapi_app.get("/check_auth/{user_id}")
async def check_auth_status(user_id: str):
    """Check if a user is authenticated"""
    token_data = db.get_user_token(user_id)
    if not token_data:
        return {"authenticated": False, "message": "User is not authenticated"}

    # Check if the token is valid
    try:
        access_token = token_data.get("access_token")
        if not access_token:
            return {"authenticated": False, "message": "No access token found"}

        # Verify the token with Discord
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {access_token}"}
            async with session.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=headers) as resp:
                if resp.status != 200:
                    return {"authenticated": False, "message": "Invalid token"}

                # Token is valid
                return {"authenticated": True, "message": "User is authenticated"}
    except Exception as e:
        print(f"Error checking auth status: {e}")
        return {"authenticated": False, "message": f"Error checking auth status: {str(e)}"}

@api_app.delete("/token")
@discordapi_app.delete("/token")
async def delete_token(user_id: str = Depends(verify_discord_token)):
    """Delete the token for a user"""
    success = db.delete_user_token(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="No token found for this user")

    return {"success": True, "message": "Token deleted successfully"}

@api_app.delete("/token/{user_id}")
@discordapi_app.delete("/token/{user_id}")
async def delete_token_by_user_id(user_id: str):
    """Delete the token for a specific user by ID (for bot use)"""
    success = db.delete_user_token(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="No token found for this user")

    return {"success": True, "message": "Token deleted successfully"}

# ============= Server Shutdown =============

@app.on_event("shutdown")
async def shutdown_event():
    """Save all data on shutdown"""
    db.save_data()

# ============= Gurt Stats Endpoints (IPC Approach) =============

# --- Internal Endpoint to Receive Stats ---
@app.post("/internal/gurt/update_stats") # Use the main app, not sub-apps
async def update_gurt_stats_internal(request: Request):
    """Internal endpoint for the Gurt bot process to push its stats."""
    global latest_gurt_stats
    # Basic security check
    auth_header = request.headers.get("Authorization")
    # Use loaded setting
    if not settings.GURT_STATS_PUSH_SECRET or not auth_header or auth_header != f"Bearer {settings.GURT_STATS_PUSH_SECRET}":
        print("Unauthorized attempt to update Gurt stats.")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        stats_data = await request.json()
        latest_gurt_stats = stats_data
        # print(f"Received Gurt stats update at {datetime.datetime.now()}") # Optional: Log successful updates
        return {"success": True, "message": "Stats updated"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        print(f"Error processing Gurt stats update: {e}")
        raise HTTPException(status_code=500, detail="Error processing stats update")

# --- Public Endpoint to Get Stats ---
@discordapi_app.get("/gurt/stats") # Add to the deprecated path for now
@api_app.get("/gurt/stats") # Add to the new path as well
async def get_gurt_stats_public():
    """Get latest internal statistics received from the Gurt bot."""
    if latest_gurt_stats is None:
        raise HTTPException(status_code=503, detail="Gurt stats not available yet. Please wait for the Gurt bot to send an update.")
    return latest_gurt_stats

# --- Gurt Dashboard Static Files & Route ---
dashboard_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'discordbot', 'gurt_dashboard'))
if os.path.exists(dashboard_dir) and os.path.isdir(dashboard_dir):
    # Mount static files (use a unique name like 'gurt_dashboard_static')
    # Mount on both /api and /discordapi for consistency during transition
    discordapi_app.mount("/gurt/static", StaticFiles(directory=dashboard_dir), name="gurt_dashboard_static_discord")
    api_app.mount("/gurt/static", StaticFiles(directory=dashboard_dir), name="gurt_dashboard_static_api")
    print(f"Mounted Gurt dashboard static files from: {dashboard_dir}")

    # Route for the main dashboard HTML
    @discordapi_app.get("/gurt/dashboard", response_class=FileResponse) # Add to deprecated path
    @api_app.get("/gurt/dashboard", response_class=FileResponse) # Add to new path
    async def get_gurt_dashboard_combined():
        dashboard_html_path = os.path.join(dashboard_dir, "index.html")
        if os.path.exists(dashboard_html_path):
            return dashboard_html_path
        else:
            raise HTTPException(status_code=404, detail="Dashboard index.html not found")
else:
    print(f"Warning: Gurt dashboard directory '{dashboard_dir}' not found. Dashboard endpoints will not be available.")

# --- New Bot Settings Dashboard Static Files & Route ---
new_dashboard_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'dashboard_web'))
if os.path.exists(new_dashboard_dir) and os.path.isdir(new_dashboard_dir):
    # Mount static files at /dashboard/static (or just /dashboard and rely on html=True)
    app.mount("/dashboard", StaticFiles(directory=new_dashboard_dir, html=True), name="bot_dashboard_static")
    print(f"Mounted Bot Settings dashboard static files from: {new_dashboard_dir}")

    # Optional: Explicit route for index.html if needed, but html=True should handle it for "/"
    # @app.get("/dashboard", response_class=FileResponse)
    # async def get_bot_dashboard_index():
    #     index_path = os.path.join(new_dashboard_dir, "index.html")
    #     if os.path.exists(index_path):
    #         return index_path
    #     else:
    #         raise HTTPException(status_code=404, detail="Dashboard index.html not found")
else:
    print(f"Warning: Bot Settings dashboard directory '{new_dashboard_dir}' not found. Dashboard will not be available.")


# ============= Run the server =============

if __name__ == "__main__":
    import uvicorn
    # Use settings loaded by Pydantic
    ssl_available_main = settings.SSL_CERT_FILE and settings.SSL_KEY_FILE and os.path.exists(settings.SSL_CERT_FILE) and os.path.exists(settings.SSL_KEY_FILE)

    uvicorn.run(
        "api_server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info",
        ssl_certfile=settings.SSL_CERT_FILE if ssl_available_main else None,
        ssl_keyfile=settings.SSL_KEY_FILE if ssl_available_main else None,
    )
