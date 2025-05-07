import os
import json
import sys
import asyncio
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import aiohttp
from database import Database # Existing DB
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field
from functools import lru_cache
from contextlib import asynccontextmanager
from enum import Enum
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# --- Logging Configuration ---
# Configure logging
log = logging.getLogger("api_server")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("api_server.log")
    ]
)

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
    DISCORD_BOT_TOKEN: Optional[str] = None  # Add bot token for API calls (optional)

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

    # Secret key for AI Moderation API endpoint
    MOD_LOG_API_SECRET: Optional[str] = None

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
DISCORD_API_ENDPOINT = DISCORD_API_BASE_URL  # Alias for backward compatibility

# Define dashboard-specific redirect URI
DASHBOARD_REDIRECT_URI = f"{settings.DISCORD_REDIRECT_URI.split('/api')[0]}/dashboard/api/auth/callback"

# We'll generate the full auth URL with PKCE parameters in the dashboard_login function
# This is just a base URL without the PKCE parameters
DISCORD_AUTH_BASE_URL = (
    f"https://discord.com/api/oauth2/authorize?client_id={settings.DISCORD_CLIENT_ID}"
    f"&redirect_uri={settings.DISCORD_REDIRECT_URI}&response_type=code&scope=identify guilds"
)

# Dashboard-specific auth base URL
DASHBOARD_AUTH_BASE_URL = (
    f"https://discord.com/api/oauth2/authorize?client_id={settings.DISCORD_CLIENT_ID}"
    f"&redirect_uri={DASHBOARD_REDIRECT_URI}&response_type=code&scope=identify guilds"
)

DISCORD_TOKEN_URL = f"{DISCORD_API_BASE_URL}/oauth2/token"
DISCORD_USER_URL = f"{DISCORD_API_BASE_URL}/users/@me"
DISCORD_USER_GUILDS_URL = f"{DISCORD_API_BASE_URL}/users/@me/guilds"
DISCORD_REDIRECT_URI = settings.DISCORD_REDIRECT_URI  # Make it accessible directly

# For backward compatibility, keep DISCORD_AUTH_URL but it will be replaced in the dashboard_login function
DISCORD_AUTH_URL = DISCORD_AUTH_BASE_URL


# --- Gurt Stats Storage (IPC) ---
latest_gurt_stats: Optional[Dict[str, Any]] = None
# GURT_STATS_PUSH_SECRET is now loaded via ApiSettings
if not settings.GURT_STATS_PUSH_SECRET:
    print("Warning: GURT_STATS_PUSH_SECRET not set. Internal stats update endpoint will be insecure.")

# --- Helper Functions ---
async def get_guild_name_from_api(guild_id: int, timeout: float = 5.0) -> str:
    """
    Get a guild's name from Discord API using the bot token.

    Args:
        guild_id: The Discord guild ID to get the name for
        timeout: Maximum time to wait for the API request (in seconds)

    Returns:
        The guild name if successful, otherwise a fallback string with the guild ID
    """
    fallback = f"Server {guild_id}"  # Default fallback

    if not settings.DISCORD_BOT_TOKEN:
        log.warning("DISCORD_BOT_TOKEN not set, using guild ID as fallback")
        return fallback

    try:
        # Use global http_session if available, otherwise create a new one
        session = http_session if http_session else aiohttp.ClientSession()

        # Headers for the request
        headers = {'Authorization': f'Bot {settings.DISCORD_BOT_TOKEN}'}

        # Send the request with a timeout
        async with session.get(
            f"https://discord.com/api/v10/guilds/{guild_id}",
            headers=headers,
            timeout=timeout
        ) as response:
            if response.status == 200:
                guild_data = await response.json()
                guild_name = guild_data.get('name', fallback)
                log.info(f"Retrieved guild name '{guild_name}' for guild ID {guild_id}")
                return guild_name
            else:
                log.warning(f"Failed to get guild name for guild ID {guild_id}: HTTP {response.status}")
                return fallback
    except asyncio.TimeoutError:
        log.error(f"Timeout getting guild name for guild ID {guild_id}")
        return fallback
    except Exception as e:
        log.error(f"Error getting guild name for guild ID {guild_id}: {e}")
        return fallback

async def send_discord_message_via_api(channel_id: int, content: str, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Send a message to a Discord channel using Discord's REST API directly.
    This avoids using Discord.py's channel.send() method which can cause issues with FastAPI.

    Args:
        channel_id: The Discord channel ID to send the message to
        content: The message content to send
        timeout: Maximum time to wait for the API request (in seconds)

    Returns:
        A dictionary with status information about the message send operation
    """
    if not settings.DISCORD_BOT_TOKEN:
        return {
            "success": False,
            "message": "Discord bot token not configured",
            "error": "no_token"
        }

    # Discord API endpoint for sending messages
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

    # Headers for the request
    headers = {
        "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    # Message data
    data = {
        "content": content
    }

    try:
        # Use global http_session if available, otherwise create a new one
        session = http_session if http_session else aiohttp.ClientSession()

        # Send the request with a timeout
        async with session.post(url, headers=headers, json=data, timeout=timeout) as response:
            if response.status == 200 or response.status == 201:
                # Message sent successfully
                response_data = await response.json()
                return {
                    "success": True,
                    "message": "Message sent successfully",
                    "message_id": response_data.get("id")
                }
            elif response.status == 403:
                # Missing permissions
                return {
                    "success": False,
                    "message": "Missing permissions to send message to this channel",
                    "error": "forbidden",
                    "status": response.status
                }
            elif response.status == 429:
                # Rate limited
                response_data = await response.json()
                retry_after = response_data.get("retry_after", 1)
                return {
                    "success": False,
                    "message": f"Rate limited by Discord API. Retry after {retry_after} seconds",
                    "error": "rate_limited",
                    "retry_after": retry_after,
                    "status": response.status
                }
            else:
                # Other error
                try:
                    response_data = await response.json()
                    return {
                        "success": False,
                        "message": f"Discord API error: {response.status}",
                        "error": "api_error",
                        "status": response.status,
                        "details": response_data
                    }
                except:
                    return {
                        "success": False,
                        "message": f"Discord API error: {response.status}",
                        "error": "api_error",
                        "status": response.status
                    }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": "Timeout sending message to Discord API",
            "error": "timeout"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error sending message: {str(e)}",
            "error": "unknown",
            "details": str(e)
        }
# ---------------------------------

# Import dependencies after defining settings and constants
# Use absolute imports to avoid issues when running the server directly
from discordbot.api_service import dependencies
from api_models import (
    Conversation,
    UserSettings,
    GetConversationsResponse,
    UpdateSettingsRequest,
    UpdateConversationRequest,
    ApiResponse
)
import code_verifier_store

# Ensure discordbot is in path to import settings_manager
discordbot_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if discordbot_path not in sys.path:
    sys.path.insert(0, discordbot_path)

try:
    from discordbot import settings_manager
    log.info("Successfully imported settings_manager module")
except ImportError as e:
    log.error(f"Could not import discordbot.settings_manager: {e}")
    log.error("Ensure the API is run from the project root or discordbot is in PYTHONPATH.")
    settings_manager = None # Set to None to indicate failure

# ============= API Setup =============

# Define lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(_: FastAPI):  # Underscore indicates unused but required parameter
    """Lifespan event handler for FastAPI app."""
    global http_session

    # Startup: Initialize resources
    log.info("Starting API server...")

    # Initialize existing database
    db.load_data()
    log.info("Existing database loaded.")

    # Start aiohttp session
    http_session = aiohttp.ClientSession()
    log.info("aiohttp session started.")
    dependencies.set_http_session(http_session) # Pass session to dependencies module
    log.info("aiohttp session passed to dependencies module.")

    # Initialize settings_manager pools for the API server
    # This is necessary because the API server runs in a different thread/event loop
    # than the main bot, so it needs its own connection pools
    if settings_manager:
        log.info("Initializing database and cache connection pools for API server...")

        # Add retry logic for database initialization
        max_retries = 3
        retry_count = 0
        success = False

        # --- New pool initialization logic ---
        import asyncpg
        import redis.asyncio as redis

        # These will be stored in app.state
        # pg_pool = None # No longer module/lifespan local like this for app.state version
        # redis_pool = None

        try:
            app.state.pg_pool = await asyncpg.create_pool(
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_HOST,
                database=settings.POSTGRES_SETTINGS_DB,
                min_size=1,
                max_size=10,
            )
            log.info("PostgreSQL pool created and stored in app.state.pg_pool.")

            redis_url = f"redis://{':' + settings.REDIS_PASSWORD + '@' if settings.REDIS_PASSWORD else ''}{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
            app.state.redis_pool = await redis.from_url(
                redis_url,
                decode_responses=True,
            )
            log.info("Redis pool created and stored in app.state.redis_pool.")

            # DO NOT call settings_manager.set_bot_pools from API server.
            # The bot (main.py) is responsible for setting the global pools in settings_manager.
            # API server will use its own pools from app.state and pass them explicitly if needed.
            if not settings_manager:
                 log.error("settings_manager not imported. API endpoints requiring it may fail.")

        except Exception as e:
            log.exception(f"Failed to initialize API server's connection pools: {e}")
            # Ensure app.state pools are None if creation failed
            app.state.pg_pool = None
            app.state.redis_pool = None


        yield # Lifespan part 1 ends here

        # Shutdown: Clean up resources
        log.info("Shutting down API server...")

        # Save existing database data
        db.save_data()
        log.info("Existing database saved.")

        # Close API server's database/cache pools
        if app.state.pg_pool:
            await app.state.pg_pool.close()
            log.info("API Server's PostgreSQL pool closed.")
            app.state.pg_pool = None
        if app.state.redis_pool:
            await app.state.redis_pool.close() # Assuming redis pool has a close method
            log.info("API Server's Redis pool closed.")
            app.state.redis_pool = None

        # Close aiohttp session
        if http_session:
            await http_session.close()
            log.info("aiohttp session closed.")

# Create the FastAPI app with lifespan
app = FastAPI(title="Unified API Service", lifespan=lifespan, debug=True)

@app.exception_handler(StarletteHTTPException)
async def teapot_override(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>418 I'm a teapot</title>
            <style>
                body { font-family: Arial, sans-serif; background-color: #fef6e4; text-align: center; padding: 50px; }
                h1 { font-size: 48px; color: #d62828; }
                p { font-size: 24px; color: #2b2d42; }
                .teapot { font-size: 100px; }
            </style>
        </head>
        <body>
            <div class="teapot">🫖</div>
            <h1>418 I'm a teapot</h1>
            <p>You asked for something I can't brew. Try a different path.</p>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=418)
    raise exc

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

# Import dashboard API endpoints
try:
    # Use absolute import
    from discordbot.api_service.dashboard_api_endpoints import router as dashboard_router
    # Add the dashboard router to the dashboard API app
    dashboard_api_app.include_router(dashboard_router)
    log.info("Dashboard API endpoints loaded successfully")

    # Add direct routes for test-welcome and test-goodbye endpoints
    # These routes need to be defined after the dependencies are defined
    # We'll add them later
except ImportError as e:
    log.error(f"Could not import dashboard API endpoints: {e}")
    log.error("Dashboard API endpoints will not be available")

# Import command customization models and endpoints
try:
    # Use absolute import
    from discordbot.api_service.command_customization_endpoints import router as customization_router
    # Add the command customization router to the dashboard API app
    dashboard_api_app.include_router(customization_router, prefix="/commands", tags=["Command Customization"])
    log.info("Command customization endpoints loaded successfully")
except ImportError as e:
    log.error(f"Could not import command customization endpoints: {e}")
    log.error("Command customization endpoints will not be available")

# Import cog management endpoints
try:
    # Use absolute import
    from discordbot.api_service.cog_management_endpoints import router as cog_management_router
    log.info("Successfully imported cog_management_endpoints")
    # Add the cog management router to the dashboard API app
    dashboard_api_app.include_router(cog_management_router, tags=["Cog Management"])
    log.info("Cog management endpoints loaded successfully")
except ImportError as e:
    log.error(f"Could not import cog management endpoints: {e}")
    # Try to import the module directly to see what's available (for debugging)
    try:
        import sys
        log.info(f"Python path: {sys.path}")
        # Try to find the module in the current directory
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        log.info(f"Current directory: {current_dir}")
        files = os.listdir(current_dir)
        log.info(f"Files in current directory: {files}")
        # Try to import the module with a full path
        sys.path.append(current_dir)
        import cog_management_endpoints # type: ignore
        log.info(f"Successfully imported cog_management_endpoints module directly")
    except Exception as e_debug:
        log.error(f"Debug import failed: {e_debug}")

    log.error("Cog management endpoints will not be available")

# Mount the API apps at their respective paths
app.mount("/api", api_app)
app.mount("/discordapi", discordapi_app)
app.mount("/dashboard/api", dashboard_api_app) # Mount the new dashboard API

# Log the available routes for debugging
log.info("Available routes in dashboard_api_app:")
for route in dashboard_api_app.routes:
    log.info(f"  {route.path} - {route.name} - {route.methods}")

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
    return RedirectResponse(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", status_code=301)

@app.get("/ip")
async def ip(request: Request):
    return Response(content=request.client.host, media_type="text/plain")

# Add root for dashboard API for clarity
@dashboard_api_app.get("/")
async def dashboard_api_root():
     return {"message": "Bot Dashboard API is running"}

# Add a test endpoint for cogs
@dashboard_api_app.get("/test-cogs", tags=["Test"])
async def test_cogs_endpoint():
    """Test endpoint to verify the API server is working correctly."""
    return {"message": "Test cogs endpoint is working"}

# Add a direct endpoint for cogs without dependencies
@dashboard_api_app.get("/guilds/{guild_id}/cogs-direct", tags=["Test"])
async def get_guild_cogs_no_deps(guild_id: int):
    """Get all cogs for a guild without any dependencies."""
    try:
        # First try to get cogs from the bot instance
        bot = None
        try:
            from discordbot import discord_bot_sync_api
            bot = discord_bot_sync_api.bot_instance
        except (ImportError, AttributeError) as e:
            log.warning(f"Could not import bot instance: {e}")

        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
            return {"error": "Settings manager not available", "cogs": []}

        # Get cogs from the database directly if bot is not available
        cogs_list = []

        if bot:
            # Get cogs from the bot instance
            log.info(f"Getting cogs from bot instance for guild {guild_id}")
            for cog_name, cog in bot.cogs.items():
                # Get enabled status from settings_manager
                is_enabled = True
                try:
                    is_enabled = await settings_manager.is_cog_enabled(guild_id, cog_name, default_enabled=True)
                except Exception as e:
                    log.error(f"Error getting cog enabled status: {e}")

                cogs_list.append({
                    "name": cog_name,
                    "description": cog.__doc__ or "No description available",
                    "enabled": is_enabled
                })
        else:
            # Fallback: Get cogs from the database directly
            log.info(f"Getting cogs from database for guild {guild_id}")
            try:
                # Get all cog enabled statuses from the database
                cog_statuses = await settings_manager.get_all_enabled_cogs(guild_id)

                # Add each cog to the list
                for cog_name, is_enabled in cog_statuses.items():
                    cogs_list.append({
                        "name": cog_name,
                        "description": "Description not available (bot instance not accessible)",
                        "enabled": is_enabled
                    })

                # If no cogs were found, add some default cogs
                if not cogs_list:
                    default_cogs = [
                        "SettingsCog", "HelpCog", "ModerationCog", "WelcomeCog",
                        "GurtCog", "EconomyCog", "UtilityCog"
                    ]
                    for cog_name in default_cogs:
                        # Try to get the enabled status from the database
                        try:
                            is_enabled = await settings_manager.is_cog_enabled(guild_id, cog_name, default_enabled=True)
                        except Exception:
                            is_enabled = True

                        cogs_list.append({
                            "name": cog_name,
                            "description": "Default cog (bot instance not accessible)",
                            "enabled": is_enabled
                        })
            except Exception as e:
                log.error(f"Error getting cogs from database: {e}")
                return {"error": f"Error getting cogs from database: {str(e)}", "cogs": []}

        return {"cogs": cogs_list}
    except Exception as e:
        log.error(f"Error getting cogs for guild {guild_id}: {e}")
        return {"error": str(e), "cogs": []}


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
        print(f"Code verifier provided directly in URL: {code_verifier is not None}")
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
                from urllib.parse import urlparse
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

            # First try to get the code verifier from the store using the state parameter
            # This is the most reliable method since the code verifier should have been stored
            # by the Discord bot before the user was redirected here
            stored_code_verifier = None
            if state:
                stored_code_verifier = code_verifier_store.get_code_verifier(state)
                if stored_code_verifier:
                    print(f"Found code_verifier in store for state {state}: {stored_code_verifier[:10]}...")
                else:
                    print(f"No code_verifier found in store for state {state}, will check other sources")

            # If we have a code_verifier parameter directly in the URL, use that
            if code_verifier:
                data["code_verifier"] = code_verifier
                print(f"Using code_verifier from URL parameter: {code_verifier[:10]}...")
            # Otherwise use the stored code verifier if available
            elif stored_code_verifier:
                data["code_verifier"] = stored_code_verifier
                print(f"Using code_verifier from store: {stored_code_verifier[:10]}...")
                # Remove the code verifier from the store after using it
                code_verifier_store.remove_code_verifier(state)
            else:
                # If we still don't have a code verifier, log a warning
                print(f"WARNING: No code_verifier found for state {state} - OAuth will likely fail")
                # Return a more helpful error message
                return {
                    "message": "Authentication failed",
                    "error": "Missing code_verifier. This is required for PKCE OAuth flow. Please ensure the code_verifier is properly sent to the API server."
                }

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


# ============= Dashboard API Models =============
# Models are now in dashboard_models.py
# Dependencies are now in dependencies.py

from discordbot.api_service.dashboard_models import (
    GuildSettingsResponse,
    GuildSettingsUpdate,
    CommandPermission,
    CommandPermissionsResponse,
    CogInfo, # Needed for direct cog endpoint
    # Other models used by imported routers are not needed here directly
)

# --- AI Moderation Action Model ---
class AIModerationAction(BaseModel):
    timestamp: str
    guild_id: int
    guild_name: str
    channel_id: int
    channel_name: str
    message_id: int
    message_link: str
    user_id: int
    user_name: str
    action: str
    rule_violated: str
    reasoning: str
    violation: bool
    message_content: str
    attachments: list[str] = []
    ai_model: str
    result: str

# ============= Dashboard API Routes =============
# (Mounted under /dashboard/api)
# Dependencies are imported from dependencies.py

# --- Direct Cog Management Endpoints ---
# These are direct implementations in case the imported endpoints don't work

class CogCommandInfo(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True

class CogInfo(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    commands: List[Dict[str, Any]] = []

@dashboard_api_app.get("/guilds/{guild_id}/cogs", response_model=List[CogInfo], tags=["Cog Management"])
async def get_guild_cogs_direct(
    guild_id: int,
    _user: dict = Depends(dependencies.get_dashboard_user),
    _admin: bool = Depends(dependencies.verify_dashboard_guild_admin)
):
    """Get all cogs and their commands for a guild."""
    try:
        # First try to get cogs from the bot instance
        bot = None
        try:
            from discordbot import discord_bot_sync_api
            bot = discord_bot_sync_api.bot_instance
        except (ImportError, AttributeError) as e:
            log.warning(f"Could not import bot instance: {e}")

        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
            )

        # Get cogs from the database directly if bot is not available
        cogs_list = []

        if bot:
            # Get cogs from the bot instance
            log.info(f"Getting cogs from bot instance for guild {guild_id}")
            for cog_name, cog in bot.cogs.items():
                # Get enabled status from settings_manager
                is_enabled = await settings_manager.is_cog_enabled(guild_id, cog_name, default_enabled=True)

                # Get commands for this cog
                commands_list = []
                for command in cog.get_commands():
                    # Get command enabled status
                    cmd_enabled = await settings_manager.is_command_enabled(guild_id, command.qualified_name, default_enabled=True)
                    commands_list.append({
                        "name": command.qualified_name,
                        "description": command.help or "No description available",
                        "enabled": cmd_enabled
                    })

                # Add slash commands if any
                app_commands = [cmd for cmd in bot.tree.get_commands() if hasattr(cmd, 'cog') and cmd.cog and cmd.cog.qualified_name == cog_name]
                for cmd in app_commands:
                    # Get command enabled status
                    cmd_enabled = await settings_manager.is_command_enabled(guild_id, cmd.name, default_enabled=True)
                    if not any(c["name"] == cmd.name for c in commands_list):  # Avoid duplicates
                        commands_list.append({
                            "name": cmd.name,
                            "description": cmd.description or "No description available",
                            "enabled": cmd_enabled
                        })

                cogs_list.append(CogInfo(
                    name=cog_name,
                    description=cog.__doc__ or "No description available",
                    enabled=is_enabled,
                    commands=commands_list
                ))
        else:
            # Fallback: Get cogs from the database directly
            log.info(f"Getting cogs from database for guild {guild_id}")
            try:
                # Get all cog enabled statuses from the database
                cog_statuses = await settings_manager.get_all_enabled_cogs(guild_id)

                # Get all command enabled statuses from the database
                command_statuses = await settings_manager.get_all_enabled_commands(guild_id)

                # Add each cog to the list
                for cog_name, is_enabled in cog_statuses.items():
                    # Create a list of commands for this cog
                    commands_list = []

                    # Find commands that might belong to this cog
                    # We'll use a naming convention where commands starting with the cog name
                    # (minus "Cog" suffix) are assumed to belong to that cog
                    cog_prefix = cog_name.lower().replace("cog", "")
                    for cmd_name, cmd_enabled in command_statuses.items():
                        if cmd_name.lower().startswith(cog_prefix):
                            commands_list.append({
                                "name": cmd_name,
                                "description": "Description not available (bot instance not accessible)",
                                "enabled": cmd_enabled
                            })

                    cogs_list.append(CogInfo(
                        name=cog_name,
                        description="Description not available (bot instance not accessible)",
                        enabled=is_enabled,
                        commands=commands_list
                    ))

                # If no cogs were found, add some default cogs
                if not cogs_list:
                    default_cogs = [
                        "SettingsCog", "HelpCog", "ModerationCog", "WelcomeCog",
                        "GurtCog", "EconomyCog", "UtilityCog"
                    ]
                    for cog_name in default_cogs:
                        # Try to get the enabled status from the database
                        try:
                            is_enabled = await settings_manager.is_cog_enabled(guild_id, cog_name, default_enabled=True)
                        except Exception:
                            is_enabled = True

                        # Add some default commands for this cog
                        commands_list = []
                        cog_prefix = cog_name.lower().replace("cog", "")
                        default_commands = {
                            "settings": ["set", "get", "reset"],
                            "help": ["help", "commands"],
                            "moderation": ["ban", "kick", "mute", "unmute", "warn"],
                            "welcome": ["welcome", "goodbye", "setwelcome", "setgoodbye"],
                            "gurt": ["gurt", "gurtset"],
                            "economy": ["balance", "daily", "work", "gamble"],
                            "utility": ["ping", "info", "serverinfo", "userinfo"]
                        }

                        if cog_prefix in default_commands:
                            for cmd_suffix in default_commands[cog_prefix]:
                                cmd_name = f"{cog_prefix}{cmd_suffix}"
                                try:
                                    cmd_enabled = await settings_manager.is_command_enabled(guild_id, cmd_name, default_enabled=True)
                                except Exception:
                                    cmd_enabled = True

                                commands_list.append({
                                    "name": cmd_name,
                                    "description": "Default command (bot instance not accessible)",
                                    "enabled": cmd_enabled
                                })

                        cogs_list.append(CogInfo(
                            name=cog_name,
                            description="Default cog (bot instance not accessible)",
                            enabled=is_enabled,
                            commands=commands_list
                        ))
            except Exception as e:
                log.error(f"Error getting cogs from database: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error getting cogs from database: {str(e)}"
                )

        return cogs_list
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error getting cogs for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting cogs: {str(e)}"
        )

@dashboard_api_app.patch("/guilds/{guild_id}/cogs/{cog_name}", status_code=status.HTTP_200_OK, tags=["Cog Management"])
async def update_cog_status_direct(
    guild_id: int,
    cog_name: str,
    enabled: bool = Body(..., embed=True),
    _user: dict = Depends(dependencies.get_dashboard_user),
    _admin: bool = Depends(dependencies.verify_dashboard_guild_admin)
):
    """Enable or disable a cog for a guild."""
    try:
        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
            )

        # Try to get the bot instance, but don't require it
        bot = None
        try:
            from discordbot import discord_bot_sync_api
            bot = discord_bot_sync_api.bot_instance
        except (ImportError, AttributeError) as e:
            log.warning(f"Could not import bot instance: {e}")

        # If we have a bot instance, do some additional checks
        if bot:
            # Check if the cog exists
            if cog_name not in bot.cogs:
                log.warning(f"Cog '{cog_name}' not found in bot instance, but proceeding anyway")
            else:
                # Check if it's a core cog
                core_cogs = getattr(bot, 'core_cogs', {'SettingsCog', 'HelpCog'})
                if cog_name in core_cogs and not enabled:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Core cog '{cog_name}' cannot be disabled"
                    )
        else:
            # If we don't have a bot instance, check if this is a known core cog
            if cog_name in ['SettingsCog', 'HelpCog'] and not enabled:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Core cog '{cog_name}' cannot be disabled"
                )

        # Update the cog enabled status
        success = await settings_manager.set_cog_enabled(guild_id, cog_name, enabled)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update cog '{cog_name}' status"
            )

        return {"message": f"Cog '{cog_name}' {'enabled' if enabled else 'disabled'} successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error updating cog status for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating cog status: {str(e)}"
        )

@dashboard_api_app.patch("/guilds/{guild_id}/commands/{command_name}", status_code=status.HTTP_200_OK, tags=["Cog Management"])
async def update_command_status_direct(
    guild_id: int,
    command_name: str,
    enabled: bool = Body(..., embed=True),
    _user: dict = Depends(dependencies.get_dashboard_user),
    _admin: bool = Depends(dependencies.verify_dashboard_guild_admin)
):
    """Enable or disable a command for a guild."""
    try:
        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
            )

        # Try to get the bot instance, but don't require it
        bot = None
        try:
            from discordbot import discord_bot_sync_api
            bot = discord_bot_sync_api.bot_instance
        except (ImportError, AttributeError) as e:
            log.warning(f"Could not import bot instance: {e}")

        # If we have a bot instance, check if the command exists
        if bot:
            # Check if it's a prefix command
            command = bot.get_command(command_name)
            if not command:
                # Check if it's an app command
                app_commands = [cmd for cmd in bot.tree.get_commands() if cmd.name == command_name]
                if not app_commands:
                    log.warning(f"Command '{command_name}' not found in bot instance, but proceeding anyway")

        # Update the command enabled status
        success = await settings_manager.set_command_enabled(guild_id, command_name, enabled)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update command '{command_name}' status"
            )

        return {"message": f"Command '{command_name}' {'enabled' if enabled else 'disabled'} successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error updating command status for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating command status: {str(e)}"
        )

# --- Dashboard Authentication Routes ---
@dashboard_api_app.get("/auth/login", tags=["Dashboard Authentication"])
async def dashboard_login():
    """Redirects the user to Discord for OAuth2 authorization (Dashboard Flow) with PKCE."""
    import secrets
    import hashlib
    import base64

    # Generate a random state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Generate a code verifier for PKCE
    code_verifier = secrets.token_urlsafe(64)

    # Generate a code challenge from the code verifier
    code_challenge_bytes = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).decode().rstrip("=")

    # Store the code verifier for later use
    code_verifier_store.store_code_verifier(state, code_verifier)

    # Build the authorization URL with PKCE parameters using the dashboard-specific redirect URI
    auth_url = (
        f"{DASHBOARD_AUTH_BASE_URL}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&prompt=consent"
    )

    log.info(f"Dashboard: Redirecting user to Discord auth URL with PKCE: {auth_url}")
    log.info(f"Dashboard: Using redirect URI: {DASHBOARD_REDIRECT_URI}")
    log.info(f"Dashboard: Stored code verifier for state {state}: {code_verifier[:10]}...")

    return RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@dashboard_api_app.get("/auth/callback", tags=["Dashboard Authentication"])
async def dashboard_auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    """Handles the callback from Discord after authorization (Dashboard Flow)."""
    global http_session # Use the global aiohttp session
    if error:
        log.error(f"Dashboard: Discord OAuth error: {error}")
        return RedirectResponse(url="/dashboard?error=discord_auth_failed") # Redirect to frontend dashboard root

    if not code:
        log.error("Dashboard: Discord OAuth callback missing code.")
        return RedirectResponse(url="/dashboard?error=missing_code")

    if not state:
        log.error("Dashboard: Discord OAuth callback missing state parameter.")
        return RedirectResponse(url="/dashboard?error=missing_state")

    if not http_session:
         log.error("Dashboard: aiohttp session not initialized.")
         raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    try:
        # Get the code verifier from the store
        code_verifier = code_verifier_store.get_code_verifier(state)
        if not code_verifier:
            log.error(f"Dashboard: No code_verifier found for state {state}")
            return RedirectResponse(url="/dashboard?error=missing_code_verifier")

        log.info(f"Dashboard: Found code_verifier for state {state}: {code_verifier[:10]}...")

        # Remove the code verifier from the store after retrieving it
        code_verifier_store.remove_code_verifier(state)

        # 1. Exchange code for access token with PKCE
        token_data = {
            'client_id': settings.DISCORD_CLIENT_ID,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': DASHBOARD_REDIRECT_URI, # Must match exactly what was used in the auth request
            'code_verifier': code_verifier # Add the code verifier for PKCE
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        log.debug(f"Dashboard: Exchanging code for token at {DISCORD_TOKEN_URL} with PKCE")
        log.debug(f"Dashboard: Token exchange data: {token_data}")

        async with http_session.post(DISCORD_TOKEN_URL, data=token_data, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                log.error(f"Dashboard: Failed to exchange code: {error_text}")
                return RedirectResponse(url=f"/dashboard?error=token_exchange_failed&details={error_text}")

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

@dashboard_api_app.get("/auth/status", tags=["Dashboard Authentication"])
async def dashboard_auth_status(request: Request):
    """Checks if the user is authenticated in the dashboard session."""
    user_id = request.session.get('user_id')
    username = request.session.get('username')
    access_token = request.session.get('access_token')

    if not user_id or not username or not access_token:
        log.debug("Dashboard: Auth status check - user not authenticated")
        return {"authenticated": False, "message": "User is not authenticated"}

    # Verify the token is still valid with Discord
    try:
        if not http_session:
            log.error("Dashboard: aiohttp session not initialized.")
            return {"authenticated": False, "message": "Internal server error: HTTP session not ready"}

        user_headers = {'Authorization': f'Bearer {access_token}'}
        async with http_session.get(DISCORD_USER_URL, headers=user_headers) as resp:
            if resp.status != 200:
                log.warning(f"Dashboard: Auth status check - invalid token for user {user_id}")
                # Clear the invalid session
                request.session.clear()
                return {"authenticated": False, "message": "Discord token invalid or expired"}

            # Token is valid, get the latest user data
            user_data = await resp.json()

            # Update session with latest data
            request.session['username'] = user_data.get('username')
            request.session['avatar'] = user_data.get('avatar')

            log.debug(f"Dashboard: Auth status check - user {user_id} is authenticated")
            return {
                "authenticated": True,
                "user": {
                    "id": user_id,
                    "username": user_data.get('username'),
                    "avatar": user_data.get('avatar')
                }
            }
    except Exception as e:
        log.exception(f"Dashboard: Error checking auth status: {e}")
        return {"authenticated": False, "message": f"Error checking auth status: {str(e)}"}

# --- Dashboard User Endpoints ---
@dashboard_api_app.get("/user/me", tags=["Dashboard User"])
async def dashboard_get_user_me(current_user: dict = Depends(dependencies.get_dashboard_user)):
    """Returns information about the currently logged-in dashboard user."""
    user_info = current_user.copy()
    # del user_info['access_token'] # Optional: Don't expose token to frontend
    return user_info

@dashboard_api_app.get("/auth/user", tags=["Dashboard Authentication"])
async def dashboard_get_auth_user(request: Request):
    """Returns information about the currently logged-in dashboard user for the frontend."""
    user_id = request.session.get('user_id')
    username = request.session.get('username')
    avatar = request.session.get('avatar')

    if not user_id or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": user_id,
        "username": username,
        "avatar": avatar
    }

@dashboard_api_app.get("/user/guilds", tags=["Dashboard User"])
@dashboard_api_app.get("/guilds", tags=["Dashboard Guild Settings"])
async def dashboard_get_user_guilds(current_user: dict = Depends(dependencies.get_dashboard_user)):
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
        try:
            # Add retry logic for database operations
            max_db_retries = 3
            retry_count = 0
            bot_guild_ids = None

            while retry_count < max_db_retries and bot_guild_ids is None:
                try:
                    bot_guild_ids = await settings_manager.get_bot_guild_ids()
                    if bot_guild_ids is None:
                        log.warning(f"Dashboard: Failed to fetch bot guild IDs, retry {retry_count+1}/{max_db_retries}")
                        retry_count += 1
                        if retry_count < max_db_retries:
                            await asyncio.sleep(1)  # Wait before retrying
                except Exception as e:
                    log.warning(f"Dashboard: Error fetching bot guild IDs, retry {retry_count+1}/{max_db_retries}: {e}")
                    retry_count += 1
                    if retry_count < max_db_retries:
                        await asyncio.sleep(1)  # Wait before retrying

            # After retries, if still no data, raise exception
            if bot_guild_ids is None:
                log.error("Dashboard: Failed to fetch bot guild IDs from settings_manager after retries.")
                raise HTTPException(status_code=500, detail="Could not retrieve bot's guild list.")
        except Exception as e:
            log.exception("Dashboard: Exception while fetching bot guild IDs from settings_manager.")
            raise HTTPException(status_code=500, detail="Database error while retrieving bot's guild list.")

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
@dashboard_api_app.get("/guilds/{guild_id}/channels", tags=["Dashboard Guild Settings"])
async def dashboard_get_guild_channels(
    guild_id: int,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
):
    """Fetches the channels for a specific guild for the dashboard."""
    global http_session # Use the global aiohttp session
    if not http_session:
        raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    log.info(f"Dashboard: Fetching channels for guild {guild_id} requested by user {current_user['user_id']}")

    try:
        # Use Discord Bot Token to fetch channels if available
        if not settings.DISCORD_BOT_TOKEN:
            log.error("Dashboard: DISCORD_BOT_TOKEN not set in environment variables")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bot token not configured. Please set DISCORD_BOT_TOKEN in environment variables."
            )

        bot_headers = {'Authorization': f'Bot {settings.DISCORD_BOT_TOKEN}'}

        # Add rate limit handling
        max_retries = 3
        retry_count = 0
        retry_after = 0

        while retry_count < max_retries:
            if retry_after > 0:
                log.warning(f"Dashboard: Rate limited by Discord API, waiting {retry_after} seconds before retry")
                await asyncio.sleep(retry_after)

            async with http_session.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=bot_headers) as resp:
                if resp.status == 429:  # Rate limited
                    retry_count += 1

                    # Get the most accurate retry time from headers
                    retry_after = float(resp.headers.get('X-RateLimit-Reset-After',
                                      resp.headers.get('Retry-After', 1)))

                    # Check if this is a global rate limit
                    is_global = resp.headers.get('X-RateLimit-Global') is not None

                    # Get the rate limit scope if available
                    scope = resp.headers.get('X-RateLimit-Scope', 'unknown')

                    log.warning(
                        f"Dashboard: Discord API rate limit hit. "
                        f"Global: {is_global}, Scope: {scope}, "
                        f"Reset after: {retry_after}s, "
                        f"Retry: {retry_count}/{max_retries}"
                    )

                    # For global rate limits, we might want to wait longer
                    if is_global:
                        retry_after = max(retry_after, 5)  # At least 5 seconds for global limits

                    continue

                # Check rate limit headers and log them for monitoring
                rate_limit = {
                    'limit': resp.headers.get('X-RateLimit-Limit'),
                    'remaining': resp.headers.get('X-RateLimit-Remaining'),
                    'reset': resp.headers.get('X-RateLimit-Reset'),
                    'reset_after': resp.headers.get('X-RateLimit-Reset-After'),
                    'bucket': resp.headers.get('X-RateLimit-Bucket')
                }

                # If we're getting close to the rate limit, log a warning
                if rate_limit['remaining'] and rate_limit['limit']:
                    try:
                        remaining = int(rate_limit['remaining'])
                        limit = int(rate_limit['limit'])
                        if remaining < 5:
                            log.warning(
                                f"Dashboard: Rate limit warning: {remaining}/{limit} "
                                f"requests remaining in bucket {rate_limit['bucket'] or 'unknown'}. "
                                f"Resets in {rate_limit['reset_after'] or 'unknown'}s"
                            )
                    except (ValueError, TypeError):
                        # Handle case where headers might be present but not valid integers
                        pass

                resp.raise_for_status()
                channels = await resp.json()

                # Filter and format channels
                formatted_channels = []
                for channel in channels:
                    formatted_channels.append({
                        "id": channel["id"],
                        "name": channel["name"],
                        "type": channel["type"],
                        "parent_id": channel.get("parent_id")
                    })

                return formatted_channels

        # If we get here, we've exceeded our retry limit
        raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")
    except aiohttp.ClientResponseError as e:
        log.exception(f"Dashboard: HTTP error fetching guild channels: {e.status} {e.message}")
        if e.status == 429:
            raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Dashboard: Generic error fetching guild channels: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching channels.")

@dashboard_api_app.get("/guilds/{guild_id}/roles", tags=["Dashboard Guild Settings"])
async def dashboard_get_guild_roles(
    guild_id: int,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
):
    """Fetches the roles for a specific guild for the dashboard."""
    global http_session # Use the global aiohttp session
    if not http_session:
        raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    log.info(f"Dashboard: Fetching roles for guild {guild_id} requested by user {current_user['user_id']}")

    try:
        # Use Discord Bot Token to fetch roles if available
        if not settings.DISCORD_BOT_TOKEN:
            log.error("Dashboard: DISCORD_BOT_TOKEN not set in environment variables")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bot token not configured. Please set DISCORD_BOT_TOKEN in environment variables."
            )

        bot_headers = {'Authorization': f'Bot {settings.DISCORD_BOT_TOKEN}'}

        # Add rate limit handling
        max_retries = 3
        retry_count = 0
        retry_after = 0

        while retry_count < max_retries:
            if retry_after > 0:
                log.warning(f"Dashboard: Rate limited by Discord API, waiting {retry_after} seconds before retry")
                await asyncio.sleep(retry_after)

            async with http_session.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=bot_headers) as resp:
                if resp.status == 429:  # Rate limited
                    retry_count += 1

                    # Get the most accurate retry time from headers
                    retry_after = float(resp.headers.get('X-RateLimit-Reset-After',
                                      resp.headers.get('Retry-After', 1)))

                    # Check if this is a global rate limit
                    is_global = resp.headers.get('X-RateLimit-Global') is not None

                    # Get the rate limit scope if available
                    scope = resp.headers.get('X-RateLimit-Scope', 'unknown')

                    log.warning(
                        f"Dashboard: Discord API rate limit hit. "
                        f"Global: {is_global}, Scope: {scope}, "
                        f"Reset after: {retry_after}s, "
                        f"Retry: {retry_count}/{max_retries}"
                    )

                    # For global rate limits, we might want to wait longer
                    if is_global:
                        retry_after = max(retry_after, 5)  # At least 5 seconds for global limits

                    continue

                resp.raise_for_status()
                roles = await resp.json()

                # Filter and format roles
                formatted_roles = []
                for role in roles:
                    # Skip @everyone role
                    if role["name"] == "@everyone":
                        continue

                    formatted_roles.append({
                        "id": role["id"],
                        "name": role["name"],
                        "color": role["color"],
                        "position": role["position"],
                        "permissions": role["permissions"]
                    })

                # Sort roles by position (highest first)
                formatted_roles.sort(key=lambda r: r["position"], reverse=True)

                return formatted_roles

        # If we get here, we've exceeded our retry limit
        raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")
    except aiohttp.ClientResponseError as e:
        log.exception(f"Dashboard: HTTP error fetching guild roles: {e.status} {e.message}")
        if e.status == 429:
            raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Dashboard: Generic error fetching guild roles: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching roles.")

@dashboard_api_app.get("/guilds/{guild_id}/commands", tags=["Dashboard Guild Settings"])
async def dashboard_get_guild_commands(
    guild_id: int,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
):
    """Fetches the commands for a specific guild for the dashboard."""
    global http_session # Use the global aiohttp session
    if not http_session:
        raise HTTPException(status_code=500, detail="Internal server error: HTTP session not ready.")

    log.info(f"Dashboard: Fetching commands for guild {guild_id} requested by user {current_user['user_id']}")

    try:
        # Use Discord Bot Token to fetch application commands if available
        if not settings.DISCORD_BOT_TOKEN:
            log.error("Dashboard: DISCORD_BOT_TOKEN not set in environment variables")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Bot token not configured. Please set DISCORD_BOT_TOKEN in environment variables."
            )

        bot_headers = {'Authorization': f'Bot {settings.DISCORD_BOT_TOKEN}'}
        application_id = settings.DISCORD_CLIENT_ID  # This should be the same as your bot's application ID

        # Add rate limit handling
        max_retries = 3
        retry_count = 0
        retry_after = 0

        while retry_count < max_retries:
            if retry_after > 0:
                log.warning(f"Dashboard: Rate limited by Discord API, waiting {retry_after} seconds before retry")
                await asyncio.sleep(retry_after)

            async with http_session.get(f"https://discord.com/api/v10/applications/{application_id}/guilds/{guild_id}/commands", headers=bot_headers) as resp:
                if resp.status == 429:  # Rate limited
                    retry_count += 1

                    # Get the most accurate retry time from headers
                    retry_after = float(resp.headers.get('X-RateLimit-Reset-After',
                                      resp.headers.get('Retry-After', 1)))

                    # Check if this is a global rate limit
                    is_global = resp.headers.get('X-RateLimit-Global') is not None

                    # Get the rate limit scope if available
                    scope = resp.headers.get('X-RateLimit-Scope', 'unknown')

                    log.warning(
                        f"Dashboard: Discord API rate limit hit. "
                        f"Global: {is_global}, Scope: {scope}, "
                        f"Reset after: {retry_after}s, "
                        f"Retry: {retry_count}/{max_retries}"
                    )

                    # For global rate limits, we might want to wait longer
                    if is_global:
                        retry_after = max(retry_after, 5)  # At least 5 seconds for global limits

                    continue

                # Handle 404 specially - it's not an error, just means no commands are registered
                if resp.status == 404:
                    return []

                resp.raise_for_status()
                commands = await resp.json()

                # Format commands
                formatted_commands = []
                for cmd in commands:
                    formatted_commands.append({
                        "id": cmd["id"],
                        "name": cmd["name"],
                        "description": cmd.get("description", ""),
                        "type": cmd.get("type", 1),  # Default to CHAT_INPUT type
                        "options": cmd.get("options", [])
                    })

                return formatted_commands

        # If we get here, we've exceeded our retry limit
        raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")
    except aiohttp.ClientResponseError as e:
        log.exception(f"Dashboard: HTTP error fetching guild commands: {e.status} {e.message}")
        if e.status == 404:
            # If no commands are registered yet, return an empty list
            return []
        if e.status == 429:
            raise HTTPException(status_code=429, detail="Rate limited by Discord API. Please try again later.")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error communicating with Discord API.")
    except Exception as e:
        log.exception(f"Dashboard: Generic error fetching guild commands: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching commands.")

@dashboard_api_app.get("/settings", tags=["Dashboard Settings"])
async def dashboard_get_settings(current_user: dict = Depends(dependencies.get_dashboard_user)):
    """Fetches the global AI settings for the dashboard."""
    log.info(f"Dashboard: Fetching global settings requested by user {current_user['user_id']}")

    try:
        # Get settings from the database
        settings_data = db.get_user_settings(current_user['user_id'])

        if not settings_data:
            # Return default settings if none exist
            return {
                "model": "openai/gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 1000,
                "system_message": "",
                "character": "",
                "character_info": "",
                "custom_instructions": ""
            }

        return settings_data
    except Exception as e:
        log.exception(f"Dashboard: Error fetching global settings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred while fetching settings.")

@dashboard_api_app.post("/settings", tags=["Dashboard Settings"])
@dashboard_api_app.put("/settings", tags=["Dashboard Settings"])
async def dashboard_update_settings(request: Request, current_user: dict = Depends(dependencies.get_dashboard_user)):
    """Updates the global AI settings for the dashboard."""
    log.info(f"Dashboard: Updating global settings requested by user {current_user['user_id']}")

    try:
        # Parse the request body
        body_text = await request.body()
        body = json.loads(body_text.decode('utf-8'))

        log.debug(f"Dashboard: Received settings update: {body}")

        # Extract settings from the request body
        settings_data = None

        # Try different formats to be flexible
        if "settings" in body:
            settings_data = body["settings"]
        elif isinstance(body, dict) and "model" in body:
            # Direct settings object
            settings_data = body

        if not settings_data:
            raise HTTPException(status_code=400, detail="Invalid settings format. Expected 'settings' field or direct settings object.")

        # Create a UserSettings object
        try:
            settings = UserSettings.model_validate(settings_data)
        except Exception as e:
            log.exception(f"Dashboard: Error validating settings: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid settings data: {str(e)}")

        # Save the settings
        result = db.save_user_settings(current_user['user_id'], settings)
        log.info(f"Dashboard: Successfully updated settings for user {current_user['user_id']}")

        return result
    except json.JSONDecodeError:
        log.exception(f"Dashboard: Error decoding JSON in settings update")
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")
    except Exception as e:
        log.exception(f"Dashboard: Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred while updating settings: {str(e)}")

@dashboard_api_app.get("/guilds/{guild_id}/settings", response_model=GuildSettingsResponse, tags=["Dashboard Guild Settings"])
async def dashboard_get_guild_settings(
    guild_id: int,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
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
        if settings_manager.get_pg_pool():
             async with settings_manager.get_pg_pool().acquire() as conn:
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
        if settings_manager.get_pg_pool():
            async with settings_manager.get_pg_pool().acquire() as conn:
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
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
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
async def dashboard_get_all_guild_command_permissions_map(
    guild_id: int,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
):
    """Fetches all command permissions currently set for the guild for the dashboard as a map."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Dashboard: Fetching all command permissions map for guild {guild_id} requested by user {current_user['user_id']}")
    permissions_map: Dict[str, List[str]] = {}
    try:
        if settings_manager.get_pg_pool():
            async with settings_manager.get_pg_pool().acquire() as conn:
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

@dashboard_api_app.get("/guilds/{guild_id}/command-permissions", tags=["Dashboard Guild Settings"])
async def dashboard_get_all_guild_command_permissions(
    guild_id: int,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
):
    """Fetches all command permissions currently set for the guild for the dashboard as an array of objects."""
    if not settings_manager:
        raise HTTPException(status_code=500, detail="Internal server error: Settings manager not available.")

    log.info(f"Dashboard: Fetching all command permissions for guild {guild_id} requested by user {current_user['user_id']}")
    permissions_list = []
    try:
        if settings_manager.get_pg_pool():
            async with settings_manager.get_pg_pool().acquire() as conn:
                records = await conn.fetch(
                    "SELECT command_name, allowed_role_id FROM command_permissions WHERE guild_id = $1 ORDER BY command_name, allowed_role_id",
                    guild_id
                )

            # Get role information to include role names
            bot_headers = {'Authorization': f'Bot {settings.DISCORD_BOT_TOKEN}'}
            roles = []
            try:
                async with http_session.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=bot_headers) as resp:
                    if resp.status == 200:
                        roles = await resp.json()
            except Exception as e:
                log.warning(f"Failed to fetch role information: {e}")

            # Create a map of role IDs to role names
            role_map = {str(role["id"]): role["name"] for role in roles} if roles else {}

            for record in records:
                cmd = record['command_name']
                role_id_str = str(record['allowed_role_id'])
                role_name = role_map.get(role_id_str, f"Role ID: {role_id_str}")

                permissions_list.append({
                    "command": cmd,
                    "role_id": role_id_str,
                    "role_name": role_name
                })
        else:
             log.error("Dashboard: settings_manager pg_pool not initialized.")

        return permissions_list

    except Exception as e:
        log.exception(f"Dashboard: Database error fetching all command permissions for guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch command permissions.")

@dashboard_api_app.post(
    "/guilds/{guild_id}/ai-moderation-action",
    status_code=status.HTTP_201_CREATED,
    tags=["Moderation", "AI Integration"]
)
async def ai_moderation_action(
    guild_id: int,
    action: AIModerationAction,
    request: Request
):
    """
    Endpoint for external AI moderator to log moderation actions and add them to cases.
    Requires header: Authorization: Bearer <MOD_LOG_API_SECRET>
    """
    # Security check
    auth_header = request.headers.get("Authorization")
    if not settings.MOD_LOG_API_SECRET or not auth_header or auth_header != f"Bearer {settings.MOD_LOG_API_SECRET}":
        log.warning(f"Unauthorized attempt to use AI moderation endpoint. Headers: {request.headers}")
        raise HTTPException(status_code=403, detail="Forbidden")

    # Validate guild_id in path matches payload
    if guild_id != action.guild_id:
        log.error(f"Mismatch between guild_id in path ({guild_id}) and payload ({action.guild_id}).")
        raise HTTPException(status_code=400, detail="guild_id in path does not match payload")

    # Insert into moderation log
    if not settings_manager or not settings_manager.get_pg_pool():
        log.error("settings_manager or pg_pool not available for AI moderation logging.")
        raise HTTPException(status_code=503, detail="Moderation logging unavailable")

    # Use bot ID 0 for AI actions (or a reserved ID)
    AI_MODERATOR_ID = 0

    # Map action type to internal action_type if needed
    action_type = action.action.upper()
    reason = f"[AI:{action.ai_model}] Rule {action.rule_violated}: {action.reasoning}"

    # Add to moderation log
    try:
        from discordbot.db import mod_log_db
        case_id = await mod_log_db.add_mod_log(
            settings_manager.get_pg_pool(),
            guild_id=action.guild_id,
            moderator_id=AI_MODERATOR_ID,
            target_user_id=action.user_id,
            action_type=action_type,
            reason=reason,
            duration_seconds=None
        )
        # Optionally update with message/channel info
        if case_id and action.message_id and action.channel_id:
            await mod_log_db.update_mod_log_message_details(
                settings_manager.get_pg_pool(),
                case_id=case_id,
                message_id=action.message_id,
                channel_id=action.channel_id
            )
        log.info(f"AI moderation action logged successfully for guild {guild_id}, user {action.user_id}, action {action_type}, case {case_id}")
        return {"success": True, "case_id": case_id}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        log.error(
            f"Error logging AI moderation action for guild {guild_id}, user {action.user_id}, "
            f"action {action_type}, reason: {reason}. Exception: {e}\nTraceback: {tb}"
        )
        return {"success": False, "error": str(e), "traceback": tb}

@dashboard_api_app.post("/guilds/{guild_id}/test-goodbye", status_code=status.HTTP_200_OK, tags=["Dashboard Guild Settings"])
async def dashboard_test_goodbye_message(
    guild_id: int,
    _user: dict = Depends(dependencies.get_dashboard_user),  # Underscore prefix to indicate unused parameter
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
):
    """Test the goodbye message for a guild."""
    try:
        # Get goodbye settings
        goodbye_channel_id_str = await settings_manager.get_setting(guild_id, 'goodbye_channel_id')
        goodbye_message_template = await settings_manager.get_setting(guild_id, 'goodbye_message', default="{username} has left the server.")

        # Check if goodbye channel is set
        if not goodbye_channel_id_str or goodbye_channel_id_str == "__NONE__":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Goodbye channel not configured"
            )

        # Get the guild name from Discord API
        guild_name = await get_guild_name_from_api(guild_id)

        # Format the message
        formatted_message = goodbye_message_template.format(
            username="TestUser",
            server=guild_name
        )

        # No need to import bot_instance anymore since we're using the direct API approach

        # Send the message directly via Discord API
        try:
            goodbye_channel_id = int(goodbye_channel_id_str)

            # Send the message using our direct API approach
            result = await send_discord_message_via_api(goodbye_channel_id, formatted_message)

            if result["success"]:
                log.info(f"Sent test goodbye message to channel {goodbye_channel_id} in guild {guild_id}")
                return {
                    "message": "Test goodbye message sent successfully",
                    "channel_id": goodbye_channel_id_str,
                    "formatted_message": formatted_message,
                    "message_id": result.get("message_id")
                }
            else:
                log.error(f"Error sending test goodbye message to channel {goodbye_channel_id} in guild {guild_id}: {result['message']}")
                return {
                    "message": f"Test goodbye message could not be sent: {result['message']}",
                    "channel_id": goodbye_channel_id_str,
                    "formatted_message": formatted_message,
                    "error": result.get("error")
                }
        except ValueError:
            log.error(f"Invalid goodbye channel ID '{goodbye_channel_id_str}' for guild {guild_id}")
            return {
                "message": "Test goodbye message could not be sent (invalid channel ID)",
                "channel_id": goodbye_channel_id_str,
                "formatted_message": formatted_message
            }
        except Exception as e:
            log.error(f"Error sending test goodbye message to channel {goodbye_channel_id_str} in guild {guild_id}: {e}")
            return {
                "message": f"Test goodbye message could not be sent: {str(e)}",
                "channel_id": goodbye_channel_id_str,
                "formatted_message": formatted_message
            }
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error testing goodbye message for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing goodbye message: {str(e)}"
        )

@dashboard_api_app.post("/guilds/{guild_id}/permissions", status_code=status.HTTP_201_CREATED, tags=["Dashboard Guild Settings"])
@dashboard_api_app.post("/guilds/{guild_id}/command-permissions", status_code=status.HTTP_201_CREATED, tags=["Dashboard Guild Settings"])
async def dashboard_add_guild_command_permission(
    guild_id: int,
    permission: CommandPermission,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
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
@dashboard_api_app.delete("/guilds/{guild_id}/command-permissions", status_code=status.HTTP_200_OK, tags=["Dashboard Guild Settings"])
async def dashboard_remove_guild_command_permission(
    guild_id: int,
    permission: CommandPermission,
    current_user: dict = Depends(dependencies.get_dashboard_user),
    _: bool = Depends(dependencies.verify_dashboard_guild_admin)  # Underscore indicates unused but required dependency
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

# Note: Server startup/shutdown events are now handled by the lifespan context manager above


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

        # Store the code verifier
        code_verifier_store.store_code_verifier(state, code_verifier)

        # Clean up expired code verifiers
        code_verifier_store.cleanup_expired()

        # Log success
        print(f"Successfully stored code verifier for state {state}")
        return {"success": True, "message": "Code verifier stored successfully"}
    except Exception as e:
        error_msg = f"Error storing code verifier: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

@api_app.get("/code_verifier/{state}")
@discordapi_app.get("/code_verifier/{state}")
async def check_code_verifier(state: str):
    """Check if a code verifier exists for a state"""
    try:
        code_verifier = code_verifier_store.get_code_verifier(state)
        if code_verifier:
            # Don't return the actual code verifier for security reasons
            # Just confirm it exists
            return {"exists": True, "message": "Code verifier exists for this state"}
        else:
            return {"exists": False, "message": "No code verifier found for this state"}
    except Exception as e:
        error_msg = f"Error checking code verifier: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

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

# Note: Server shutdown is now handled by the lifespan context manager above

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
