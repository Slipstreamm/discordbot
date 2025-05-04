import os
import json
import asyncio
import datetime
from typing import Dict, List, Optional, Any, Union
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles # Added for static files
from fastapi.responses import FileResponse # Added for serving HTML
from pydantic import BaseModel, Field
import discord
from discord.ext import commands
import aiohttp
import threading
from typing import Optional # Added for GurtCog type hint

# This file contains the API endpoints for syncing conversations between
# the Flutter app and the Discord bot, AND the Gurt stats endpoint.

# --- Placeholder for GurtCog instance and bot instance ---
# These need to be set by the script that starts the bot and API server
from discordbot.gurt.cog import GurtCog # Import GurtCog for type hint and access
gurt_cog_instance: Optional[GurtCog] = None
bot_instance = None  # Will be set to the Discord bot instance

# ============= Models =============

class SyncedMessage(BaseModel):
    content: str
    role: str  # "user", "assistant", or "system"
    timestamp: datetime.datetime
    reasoning: Optional[str] = None
    usage_data: Optional[Dict[str, Any]] = None

class UserSettings(BaseModel):
    # General settings
    model_id: str = "openai/gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1000

    # Reasoning settings
    reasoning_enabled: bool = False
    reasoning_effort: str = "medium"  # "low", "medium", "high"

    # Web search settings
    web_search_enabled: bool = False

    # System message
    system_message: Optional[str] = None

    # Character settings
    character: Optional[str] = None
    character_info: Optional[str] = None
    character_breakdown: bool = False
    custom_instructions: Optional[str] = None

    # UI settings
    advanced_view_enabled: bool = False
    streaming_enabled: bool = True

    # Last updated timestamp
    last_updated: datetime.datetime = Field(default_factory=datetime.datetime.now)
    sync_source: str = "discord"  # "discord" or "flutter"

class SyncedConversation(BaseModel):
    id: str
    title: str
    messages: List[SyncedMessage]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    model_id: str
    sync_source: str = "discord"  # "discord" or "flutter"
    last_synced_at: Optional[datetime.datetime] = None

    # Conversation-specific settings
    reasoning_enabled: bool = False
    reasoning_effort: str = "medium"  # "low", "medium", "high"
    temperature: float = 0.7
    max_tokens: int = 1000
    web_search_enabled: bool = False
    system_message: Optional[str] = None

    # Character-related settings
    character: Optional[str] = None
    character_info: Optional[str] = None
    character_breakdown: bool = False
    custom_instructions: Optional[str] = None

class SyncRequest(BaseModel):
    conversations: List[SyncedConversation]
    last_sync_time: Optional[datetime.datetime] = None
    user_settings: Optional[UserSettings] = None

class SettingsSyncRequest(BaseModel):
    user_settings: UserSettings

class SyncResponse(BaseModel):
    success: bool
    message: str
    conversations: List[SyncedConversation] = []
    user_settings: Optional[UserSettings] = None

# ============= Storage =============

# Files to store synced data
SYNC_DATA_FILE = "data/synced_conversations.json"
USER_SETTINGS_FILE = "data/synced_user_settings.json"

# Create data directory if it doesn't exist
os.makedirs(os.path.dirname(SYNC_DATA_FILE), exist_ok=True)

# In-memory storage for conversations and settings
user_conversations: Dict[str, List[SyncedConversation]] = {}
user_settings: Dict[str, UserSettings] = {}

# Load conversations from file
def load_conversations():
    global user_conversations
    if os.path.exists(SYNC_DATA_FILE):
        try:
            with open(SYNC_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert string keys (user IDs) back to strings
                user_conversations = {k: [SyncedConversation.model_validate(conv) for conv in v]
                                     for k, v in data.items()}
            print(f"Loaded synced conversations for {len(user_conversations)} users")
        except Exception as e:
            print(f"Error loading synced conversations: {e}")
            user_conversations = {}

# Save conversations to file
def save_conversations():
    try:
        # Convert to JSON-serializable format
        serializable_data = {
            user_id: [conv.model_dump() for conv in convs]
            for user_id, convs in user_conversations.items()
        }
        with open(SYNC_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, indent=2, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving synced conversations: {e}")

# Load user settings from file
def load_user_settings():
    global user_settings
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert string keys (user IDs) back to strings
                user_settings = {k: UserSettings.model_validate(v) for k, v in data.items()}
            print(f"Loaded synced settings for {len(user_settings)} users")
        except Exception as e:
            print(f"Error loading synced user settings: {e}")
            user_settings = {}

# Save user settings to file
def save_all_user_settings():
    try:
        # Convert to JSON-serializable format
        serializable_data = {
            user_id: settings.model_dump()
            for user_id, settings in user_settings.items()
        }
        with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, indent=2, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving synced user settings: {e}")

# ============= Discord OAuth Verification =============

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

# ============= API Setup =============

# API Configuration
API_BASE_PATH = "/discordapi"  # Base path for the API
SSL_CERT_FILE = "/etc/letsencrypt/live/slipstreamm.dev/fullchain.pem"
SSL_KEY_FILE = "/etc/letsencrypt/live/slipstreamm.dev/privkey.pem"

# Create the main FastAPI app
app = FastAPI(title="Discord Bot Sync API")

# Create a sub-application for the API
api_app = FastAPI(title="Discord Bot Sync API", docs_url="/docs", openapi_url="/openapi.json")

# Mount the API app at the base path
app.mount(API_BASE_PATH, api_app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Also add CORS to the API app
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize by loading saved data
@app.on_event("startup")
async def startup_event():
    load_conversations()
    load_user_settings()

    # Try to load local settings from AI cog and merge them with synced settings
    try:
        from cogs.ai_cog import user_settings as local_user_settings, get_user_settings as get_local_settings
        print("Merging local AI cog settings with synced settings...")

        # Iterate through local settings and update synced settings
        for user_id_int, local_settings_dict in local_user_settings.items():
            user_id_str = str(user_id_int)

            # Get the full settings with defaults
            local_settings = get_local_settings(user_id_int)

            # Create synced settings if they don't exist
            if user_id_str not in user_settings:
                user_settings[user_id_str] = UserSettings()

            # Update synced settings with local settings
            synced_settings = user_settings[user_id_str]

            # Always update all settings from local settings
            synced_settings.model_id = local_settings.get("model", synced_settings.model_id)
            synced_settings.temperature = local_settings.get("temperature", synced_settings.temperature)
            synced_settings.max_tokens = local_settings.get("max_tokens", synced_settings.max_tokens)
            synced_settings.system_message = local_settings.get("system_prompt", synced_settings.system_message)

            # Handle character settings - explicitly check if they exist in local settings
            if "character" in local_settings:
                synced_settings.character = local_settings["character"]
            else:
                # If not in local settings, set to None
                synced_settings.character = None

            # Handle character_info - explicitly check if they exist in local settings
            if "character_info" in local_settings:
                synced_settings.character_info = local_settings["character_info"]
            else:
                # If not in local settings, set to None
                synced_settings.character_info = None

            # Always update character_breakdown
            synced_settings.character_breakdown = local_settings.get("character_breakdown", False)

            # Handle custom_instructions - explicitly check if they exist in local settings
            if "custom_instructions" in local_settings:
                synced_settings.custom_instructions = local_settings["custom_instructions"]
            else:
                # If not in local settings, set to None
                synced_settings.custom_instructions = None

            # Always update reasoning settings
            synced_settings.reasoning_enabled = local_settings.get("show_reasoning", False)
            synced_settings.reasoning_effort = local_settings.get("reasoning_effort", "medium")
            synced_settings.web_search_enabled = local_settings.get("web_search_enabled", False)

            # Update timestamp and sync source
            synced_settings.last_updated = datetime.datetime.now()
            synced_settings.sync_source = "discord"

        # Save the updated synced settings
        save_all_user_settings()
        print("Successfully merged local AI cog settings with synced settings")
    except Exception as e:
        print(f"Error merging local settings with synced settings: {e}")

# ============= API Endpoints =============

@app.get(API_BASE_PATH + "/")
async def root():
    return {"message": "Discord Bot Sync API is running"}

@api_app.get("/")
async def api_root():
    return {"message": "Discord Bot Sync API is running"}

@api_app.get("/auth")
async def auth(code: str, state: str = None):
    """Handle OAuth callback"""
    return {"message": "Authentication successful", "code": code, "state": state}

@api_app.get("/conversations")
async def get_conversations(user_id: str = Depends(verify_discord_token)):
    """Get all conversations for a user"""
    if user_id not in user_conversations:
        return {"conversations": []}

    return {"conversations": user_conversations[user_id]}

@api_app.post("/sync")
async def sync_conversations(
    sync_request: SyncRequest,
    user_id: str = Depends(verify_discord_token)
):
    """Sync conversations between the Flutter app and Discord bot"""
    # Get existing conversations for this user
    existing_conversations = user_conversations.get(user_id, [])

    # Process incoming conversations
    updated_conversations = []
    for incoming_conv in sync_request.conversations:
        # Check if this conversation already exists
        existing_conv = next((conv for conv in existing_conversations
                             if conv.id == incoming_conv.id), None)

        if existing_conv:
            # If the incoming conversation is newer, update it
            if incoming_conv.updated_at > existing_conv.updated_at:
                # Replace the existing conversation
                existing_conversations = [conv for conv in existing_conversations
                                         if conv.id != incoming_conv.id]
                existing_conversations.append(incoming_conv)
                updated_conversations.append(incoming_conv)
        else:
            # This is a new conversation, add it
            existing_conversations.append(incoming_conv)
            updated_conversations.append(incoming_conv)

    # Update the storage
    user_conversations[user_id] = existing_conversations
    save_conversations()

    # Process user settings if provided
    user_settings_response = None
    if sync_request.user_settings:
        incoming_settings = sync_request.user_settings
        existing_settings = user_settings.get(user_id)

        # If we have existing settings, check which is newer
        if existing_settings:
            if not existing_settings.last_updated or incoming_settings.last_updated > existing_settings.last_updated:
                user_settings[user_id] = incoming_settings
                save_all_user_settings()
                user_settings_response = incoming_settings
            else:
                user_settings_response = existing_settings
        else:
            # No existing settings, just save the incoming ones
            user_settings[user_id] = incoming_settings
            save_all_user_settings()
            user_settings_response = incoming_settings

    return SyncResponse(
        success=True,
        message=f"Synced {len(updated_conversations)} conversations",
        conversations=existing_conversations,
        user_settings=user_settings_response
    )

@api_app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(verify_discord_token)
):
    """Delete a conversation"""
    if user_id not in user_conversations:
        raise HTTPException(status_code=404, detail="No conversations found for this user")

    # Filter out the conversation to delete
    original_count = len(user_conversations[user_id])
    user_conversations[user_id] = [conv for conv in user_conversations[user_id]
                                  if conv.id != conversation_id]

    # Check if any conversation was deleted
    if len(user_conversations[user_id]) == original_count:
        raise HTTPException(status_code=404, detail="Conversation not found")

    save_conversations()

    return {"success": True, "message": "Conversation deleted"}


# --- Gurt Stats Endpoint ---
@api_app.get("/gurt/stats")
async def get_gurt_stats_api():
    """Get internal statistics for the Gurt bot."""
    if not gurt_cog_instance:
        raise HTTPException(status_code=503, detail="Gurt cog not available")
    try:
        stats_data = await gurt_cog_instance.get_gurt_stats()
        # Convert potential datetime objects if any (though get_gurt_stats should return serializable types)
        # For safety, let's ensure basic types or handle conversion if needed later.
        return stats_data
    except Exception as e:
        print(f"Error retrieving Gurt stats via API: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving Gurt stats: {e}")

# --- Gurt Dashboard Static Files ---
# Mount static files directory (adjust path if needed, assuming dashboard files are in discordbot/gurt_dashboard)
# Check if the directory exists before mounting
dashboard_dir = "discordbot/gurt_dashboard"
if os.path.exists(dashboard_dir) and os.path.isdir(dashboard_dir):
    api_app.mount("/gurt/static", StaticFiles(directory=dashboard_dir), name="gurt_static")
    print(f"Mounted Gurt dashboard static files from: {dashboard_dir}")

    # Route for the main dashboard HTML
    @api_app.get("/gurt/dashboard", response_class=FileResponse)
    async def get_gurt_dashboard():
        dashboard_html_path = os.path.join(dashboard_dir, "index.html")
        if os.path.exists(dashboard_html_path):
            return dashboard_html_path
        else:
            raise HTTPException(status_code=404, detail="Dashboard index.html not found")
else:
    print(f"Warning: Gurt dashboard directory '{dashboard_dir}' not found. Dashboard endpoints will not be available.")


@api_app.get("/settings")
async def get_user_settings(user_id: str = Depends(verify_discord_token)):
    """Get user settings"""
    # Import the AI cog's get_user_settings function to get local settings
    try:
        from cogs.ai_cog import get_user_settings as get_local_settings, user_settings as local_user_settings

        # Get local settings from the AI cog
        local_settings = get_local_settings(int(user_id))
        print(f"Local settings for user {user_id}:")
        print(f"Character: {local_settings.get('character')}")
        print(f"Character Info: {local_settings.get('character_info')}")
        print(f"Character Breakdown: {local_settings.get('character_breakdown')}")
        print(f"Custom Instructions: {local_settings.get('custom_instructions')}")
        print(f"System Prompt: {local_settings.get('system_prompt')}")

        # Create or get synced settings
        if user_id not in user_settings:
            user_settings[user_id] = UserSettings()

        # Update synced settings with local settings
        synced_settings = user_settings[user_id]

        # Always update all settings from local settings
        synced_settings.model_id = local_settings.get("model", synced_settings.model_id)
        synced_settings.temperature = local_settings.get("temperature", synced_settings.temperature)
        synced_settings.max_tokens = local_settings.get("max_tokens", synced_settings.max_tokens)
        synced_settings.system_message = local_settings.get("system_prompt", synced_settings.system_message)

        # Handle character settings - explicitly check if they exist in local settings
        if "character" in local_settings:
            synced_settings.character = local_settings["character"]
        else:
            # If not in local settings, set to None
            synced_settings.character = None

        # Handle character_info - explicitly check if they exist in local settings
        if "character_info" in local_settings:
            synced_settings.character_info = local_settings["character_info"]
        else:
            # If not in local settings, set to None
            synced_settings.character_info = None

        # Always update character_breakdown
        synced_settings.character_breakdown = local_settings.get("character_breakdown", False)

        # Handle custom_instructions - explicitly check if they exist in local settings
        if "custom_instructions" in local_settings:
            synced_settings.custom_instructions = local_settings["custom_instructions"]
        else:
            # If not in local settings, set to None
            synced_settings.custom_instructions = None

        # Always update reasoning settings
        synced_settings.reasoning_enabled = local_settings.get("show_reasoning", False)
        synced_settings.reasoning_effort = local_settings.get("reasoning_effort", "medium")
        synced_settings.web_search_enabled = local_settings.get("web_search_enabled", False)

        # Update timestamp and sync source
        synced_settings.last_updated = datetime.datetime.now()
        synced_settings.sync_source = "discord"

        # Save the updated synced settings
        save_all_user_settings()

        print(f"Updated synced settings for user {user_id}:")
        print(f"Character: {synced_settings.character}")
        print(f"Character Info: {synced_settings.character_info}")
        print(f"Character Breakdown: {synced_settings.character_breakdown}")
        print(f"Custom Instructions: {synced_settings.custom_instructions}")
        print(f"System Message: {synced_settings.system_message}")

        return {"settings": synced_settings}
    except Exception as e:
        print(f"Error merging settings: {e}")
        # Fallback to original behavior
        if user_id not in user_settings:
            # Create default settings if none exist
            user_settings[user_id] = UserSettings()
            save_all_user_settings()

        return {"settings": user_settings[user_id]}

@api_app.post("/settings")
async def update_user_settings(
    settings_request: SettingsSyncRequest,
    user_id: str = Depends(verify_discord_token)
):
    """Update user settings"""
    incoming_settings = settings_request.user_settings
    existing_settings = user_settings.get(user_id)

    # Debug logging for character settings
    print(f"Received settings update from user {user_id}:")
    print(f"Character: {incoming_settings.character}")
    print(f"Character Info: {incoming_settings.character_info}")
    print(f"Character Breakdown: {incoming_settings.character_breakdown}")
    print(f"Custom Instructions: {incoming_settings.custom_instructions}")
    print(f"Last Updated: {incoming_settings.last_updated}")
    print(f"Sync Source: {incoming_settings.sync_source}")

    if existing_settings:
        print(f"Existing settings for user {user_id}:")
        print(f"Character: {existing_settings.character}")
        print(f"Character Info: {existing_settings.character_info}")
        print(f"Last Updated: {existing_settings.last_updated}")
        print(f"Sync Source: {existing_settings.sync_source}")

    # If we have existing settings, check which is newer
    if existing_settings:
        if not existing_settings.last_updated or incoming_settings.last_updated > existing_settings.last_updated:
            print(f"Updating settings for user {user_id} (incoming settings are newer)")
            user_settings[user_id] = incoming_settings
            save_all_user_settings()
        else:
            # Return existing settings if they're newer
            print(f"Not updating settings for user {user_id} (existing settings are newer)")
            return {"success": True, "message": "Existing settings are newer", "settings": existing_settings}
    else:
        # No existing settings, just save the incoming ones
        print(f"Creating new settings for user {user_id}")
        user_settings[user_id] = incoming_settings
        save_all_user_settings()

    # Verify the settings were saved correctly
    saved_settings = user_settings.get(user_id)
    print(f"Saved settings for user {user_id}:")
    print(f"Character: {saved_settings.character}")
    print(f"Character Info: {saved_settings.character_info}")
    print(f"Character Breakdown: {saved_settings.character_breakdown}")
    print(f"Custom Instructions: {saved_settings.custom_instructions}")

    # Update the local settings in the AI cog
    try:
        from cogs.ai_cog import user_settings as local_user_settings, save_user_settings as save_local_user_settings

        # Convert user_id to int for the AI cog
        int_user_id = int(user_id)

        # Initialize local settings if not exist
        if int_user_id not in local_user_settings:
            local_user_settings[int_user_id] = {}

        # Update local settings with incoming settings
        # Always update all settings, including setting to None/null when appropriate
        local_user_settings[int_user_id]["model"] = incoming_settings.model_id
        local_user_settings[int_user_id]["temperature"] = incoming_settings.temperature
        local_user_settings[int_user_id]["max_tokens"] = incoming_settings.max_tokens
        local_user_settings[int_user_id]["system_prompt"] = incoming_settings.system_message

        # Handle character settings - explicitly set to None if null in incoming settings
        if incoming_settings.character is None:
            # Remove the character setting if it exists
            if "character" in local_user_settings[int_user_id]:
                local_user_settings[int_user_id].pop("character")
                print(f"Removed character setting for user {user_id}")
        else:
            local_user_settings[int_user_id]["character"] = incoming_settings.character

        # Handle character_info - explicitly set to None if null in incoming settings
        if incoming_settings.character_info is None:
            # Remove the character_info setting if it exists
            if "character_info" in local_user_settings[int_user_id]:
                local_user_settings[int_user_id].pop("character_info")
                print(f"Removed character_info setting for user {user_id}")
        else:
            local_user_settings[int_user_id]["character_info"] = incoming_settings.character_info

        # Always update character_breakdown
        local_user_settings[int_user_id]["character_breakdown"] = incoming_settings.character_breakdown

        # Handle custom_instructions - explicitly set to None if null in incoming settings
        if incoming_settings.custom_instructions is None:
            # Remove the custom_instructions setting if it exists
            if "custom_instructions" in local_user_settings[int_user_id]:
                local_user_settings[int_user_id].pop("custom_instructions")
                print(f"Removed custom_instructions setting for user {user_id}")
        else:
            local_user_settings[int_user_id]["custom_instructions"] = incoming_settings.custom_instructions

        # Always update reasoning settings
        local_user_settings[int_user_id]["show_reasoning"] = incoming_settings.reasoning_enabled
        local_user_settings[int_user_id]["reasoning_effort"] = incoming_settings.reasoning_effort
        local_user_settings[int_user_id]["web_search_enabled"] = incoming_settings.web_search_enabled

        # Save the updated local settings
        save_local_user_settings()

        print(f"Updated local settings in AI cog for user {user_id}:")
        print(f"Character: {local_user_settings[int_user_id].get('character')}")
        print(f"Character Info: {local_user_settings[int_user_id].get('character_info')}")
        print(f"Character Breakdown: {local_user_settings[int_user_id].get('character_breakdown')}")
        print(f"Custom Instructions: {local_user_settings[int_user_id].get('custom_instructions')}")
    except Exception as e:
        print(f"Error updating local settings in AI cog: {e}")

    return {"success": True, "message": "Settings updated", "settings": user_settings[user_id]}

# ============= Discord Bot Integration =============

# This function should be called from your Discord bot's AI cog
# to convert AI conversation history to the synced format
def convert_ai_history_to_synced(user_id: str, conversation_history: Dict[int, List[Dict[str, Any]]]):
    """Convert the AI conversation history to the synced format"""
    synced_conversations = []

    # Process each conversation in the history
    for discord_user_id, messages in conversation_history.items():
        if str(discord_user_id) != user_id:
            continue

        # Create a unique ID for this conversation
        conv_id = f"discord_{discord_user_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Convert messages to the synced format
        synced_messages = []
        for msg in messages:
            role = msg.get("role", "")
            if role not in ["user", "assistant", "system"]:
                continue

            synced_messages.append(SyncedMessage(
                content=msg.get("content", ""),
                role=role,
                timestamp=datetime.datetime.now(),  # Use current time as we don't have the original timestamp
                reasoning=None,  # Discord bot doesn't store reasoning
                usage_data=None  # Discord bot doesn't store usage data
            ))

        # Create the synced conversation
        synced_conversations.append(SyncedConversation(
            id=conv_id,
            title="Discord Conversation",  # Default title
            messages=synced_messages,
            created_at=datetime.datetime.now(),
            updated_at=datetime.datetime.now(),
            model_id="openai/gpt-3.5-turbo",  # Default model
            sync_source="discord",
            last_synced_at=datetime.datetime.now(),
            reasoning_enabled=False,
            reasoning_effort="medium",
            temperature=0.7,
            max_tokens=1000,
            web_search_enabled=False,
            system_message=None,
            character=None,
            character_info=None,
            character_breakdown=False,
            custom_instructions=None
        ))

    return synced_conversations

# This function should be called from your Discord bot's AI cog
# to save a new conversation from Discord
def save_discord_conversation(
    user_id: str,
    messages: List[Dict[str, Any]],
    model_id: str = "openai/gpt-3.5-turbo",
    conversation_id: Optional[str] = None,
    title: str = "Discord Conversation",
    reasoning_enabled: bool = False,
    reasoning_effort: str = "medium",
    temperature: float = 0.7,
    max_tokens: int = 1000,
    web_search_enabled: bool = False,
    system_message: Optional[str] = None,
    character: Optional[str] = None,
    character_info: Optional[str] = None,
    character_breakdown: bool = False,
    custom_instructions: Optional[str] = None
):
    """Save a conversation from Discord to the synced storage"""
    # Convert messages to the synced format
    synced_messages = []
    for msg in messages:
        role = msg.get("role", "")
        if role not in ["user", "assistant", "system"]:
            continue

        synced_messages.append(SyncedMessage(
            content=msg.get("content", ""),
            role=role,
            timestamp=datetime.datetime.now(),
            reasoning=msg.get("reasoning"),
            usage_data=msg.get("usage_data")
        ))

    # Create a unique ID for this conversation if not provided
    if not conversation_id:
        conversation_id = f"discord_{user_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Create the synced conversation
    synced_conv = SyncedConversation(
        id=conversation_id,
        title=title,
        messages=synced_messages,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
        model_id=model_id,
        sync_source="discord",
        last_synced_at=datetime.datetime.now(),
        reasoning_enabled=reasoning_enabled,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        max_tokens=max_tokens,
        web_search_enabled=web_search_enabled,
        system_message=system_message,
        character=character,
        character_info=character_info,
        character_breakdown=character_breakdown,
        custom_instructions=custom_instructions
    )

    # Add to storage
    if user_id not in user_conversations:
        user_conversations[user_id] = []

    # Check if we're updating an existing conversation
    if conversation_id:
        # Remove the old conversation with the same ID if it exists
        user_conversations[user_id] = [conv for conv in user_conversations[user_id]
                                      if conv.id != conversation_id]

    user_conversations[user_id].append(synced_conv)
    save_conversations()

    return synced_conv
