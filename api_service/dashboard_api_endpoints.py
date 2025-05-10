"""
Dashboard API endpoints for the bot dashboard.
These endpoints provide additional functionality for the dashboard UI.
"""

import logging
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, Field

# Default prefix for commands
DEFAULT_PREFIX = "!"

# Import dependencies using absolute paths
from api_service.dependencies import get_dashboard_user, verify_dashboard_guild_admin

# Import models using absolute paths
from api_service.dashboard_models import (
    CommandCustomizationResponse,
    CommandCustomizationUpdate,
    GroupCustomizationUpdate,
    CommandAliasAdd,
    CommandAliasRemove,
    # Add other models used in this file if they were previously imported from api_service.api_server
    # GuildSettingsResponse, GuildSettingsUpdate, CommandPermission, CommandPermissionsResponse,
    # CogInfo, CommandInfo # Assuming these might be needed based on context below
)


# Import settings_manager for database access (use absolute path)
import settings_manager

# Set up logging
log = logging.getLogger(__name__)

# Create a router for the dashboard API endpoints
router = APIRouter(tags=["Dashboard API"])

# --- Models ---
class Channel(BaseModel):
    id: str
    name: str
    type: int  # 0 = text, 2 = voice, etc.

class Role(BaseModel):
    id: str
    name: str
    color: int
    position: int
    permissions: str

class Command(BaseModel):
    name: str
    description: Optional[str] = None

class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int

class Message(BaseModel):
    id: str
    content: str
    role: str  # 'user' or 'assistant'
    created_at: str

class ThemeSettings(BaseModel):
    theme_mode: str = "light"  # "light", "dark", "custom"
    primary_color: str = "#5865F2"  # Discord blue
    secondary_color: str = "#2D3748"
    accent_color: str = "#7289DA"
    font_family: str = "Inter, sans-serif"
    custom_css: Optional[str] = None

class GlobalSettings(BaseModel):
    system_message: Optional[str] = None
    character: Optional[str] = None
    character_info: Optional[str] = None
    custom_instructions: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    theme: Optional[ThemeSettings] = None

# CogInfo and CommandInfo models are now imported from dashboard_models

# class CommandInfo(BaseModel): # Removed - Imported from dashboard_models
#     name: str
#     description: Optional[str] = None
    enabled: bool = True
    cog_name: Optional[str] = None

class Guild(BaseModel):
    id: str
    name: str
    icon_url: Optional[str] = None

# --- Endpoints ---

@router.get("/user-guilds", response_model=List[Guild])
async def get_user_guilds(
    user: dict = Depends(get_dashboard_user)
):
    """Get all guilds the user is an admin of."""
    try:
        # This would normally fetch guilds from Discord API or the bot
        # For now, we'll return a mock response
        # TODO: Replace mock data with actual API call to Discord
        guilds = [
            Guild(id="123456789", name="My Awesome Server", icon_url="https://cdn.discordapp.com/icons/123456789/abc123def456ghi789jkl012mno345pqr.png"),
            Guild(id="987654321", name="Another Great Server", icon_url="https://cdn.discordapp.com/icons/987654321/zyx987wvu654tsr321qpo098mlk765jih.png")
        ]
        return guilds
    except Exception as e:
        log.error(f"Error getting user guilds: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting user guilds: {str(e)}"
        )

@router.get("/guilds/{guild_id}/channels", response_model=List[Channel])
async def get_guild_channels(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),  # Underscore prefix to indicate unused parameter
    _: bool = Depends(verify_dashboard_guild_admin)
):
    """Get all channels for a guild."""
    try:
        # This would normally fetch channels from Discord API or the bot
        # For now, we'll return a mock response
        # TODO: Replace mock data with actual API call to Discord
        channels = [
            Channel(id="123456789", name="general", type=0),
            Channel(id="123456790", name="welcome", type=0),
            Channel(id="123456791", name="announcements", type=0),
            Channel(id="123456792", name="voice-chat", type=2)
        ]
        return channels
    except Exception as e:
        log.error(f"Error getting channels for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting channels: {str(e)}"
        )

@router.get("/guilds/{guild_id}/roles", response_model=List[Role])
async def get_guild_roles(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),  # Underscore prefix to indicate unused parameter
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Get all roles for a guild."""
    try:
        # This would normally fetch roles from Discord API or the bot
        # For now, we'll return a mock response
        # TODO: Replace mock data with actual API call to Discord
        roles = [
            Role(id="123456789", name="@everyone", color=0, position=0, permissions="0"),
            Role(id="123456790", name="Admin", color=16711680, position=1, permissions="8"),
            Role(id="123456791", name="Moderator", color=65280, position=2, permissions="4"),
            Role(id="123456792", name="Member", color=255, position=3, permissions="1")
        ]
        return roles
    except Exception as e:
        log.error(f"Error getting roles for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting roles: {str(e)}"
        )

@router.get("/guilds/{guild_id}/commands", response_model=List[Command])
async def get_guild_commands(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),  # Underscore prefix to indicate unused parameter
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Get all commands available in the guild."""
    try:
        # This would normally fetch commands from the bot
        # For now, we'll return a mock response
        # TODO: Replace mock data with actual bot command introspection
        commands = [
            Command(name="help", description="Show help message"),
            Command(name="ping", description="Check bot latency"),
            Command(name="ban", description="Ban a user"),
            Command(name="kick", description="Kick a user"),
            Command(name="mute", description="Mute a user"),
            Command(name="unmute", description="Unmute a user"),
            Command(name="clear", description="Clear messages"),
            Command(name="ai", description="Get AI response"),
            Command(name="aiset", description="Configure AI settings"),
            Command(name="chat", description="Chat with AI"),
            Command(name="convs", description="Manage conversations")
        ]
        return commands
    except Exception as e:
        log.error(f"Error getting commands for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting commands: {str(e)}"
        )

# --- Command Customization Endpoints ---

@router.get("/guilds/{guild_id}/command-customizations", response_model=CommandCustomizationResponse)
async def get_command_customizations(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Get all command customizations for a guild."""
    try:
        # Check if settings_manager is available
        from global_bot_accessor import get_bot_instance
        bot = get_bot_instance()
        if not settings_manager or not bot or not bot.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager or database connection not available"
            )

        # Get command customizations
        command_customizations = await settings_manager.get_all_command_customizations(guild_id)
        if command_customizations is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get command customizations"
            )

        # Get group customizations
        group_customizations = await settings_manager.get_all_group_customizations(guild_id)
        if group_customizations is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get group customizations"
            )

        # Get command aliases
        command_aliases = await settings_manager.get_all_command_aliases(guild_id)
        if command_aliases is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get command aliases"
            )

        return CommandCustomizationResponse(
            command_customizations=command_customizations,
            group_customizations=group_customizations,
            command_aliases=command_aliases
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error getting command customizations for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting command customizations: {str(e)}"
        )

@router.post("/guilds/{guild_id}/command-customizations/commands", status_code=status.HTTP_200_OK)
async def set_command_customization(
    guild_id: int,
    customization: CommandCustomizationUpdate,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Set a custom name for a command in a guild."""
    try:
        # Check if settings_manager is available
        from global_bot_accessor import get_bot_instance
        bot = get_bot_instance()
        if not settings_manager or not bot or not bot.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager or database connection not available"
            )

        # Validate custom name format if provided
        if customization.custom_name is not None:
            if not customization.custom_name.islower() or not customization.custom_name.replace('_', '').isalnum():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom command names must be lowercase and contain only letters, numbers, and underscores"
                )

            if len(customization.custom_name) < 1 or len(customization.custom_name) > 32:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom command names must be between 1 and 32 characters long"
                )

        # Set the custom command name
        success = await settings_manager.set_custom_command_name(
            guild_id,
            customization.command_name,
            customization.custom_name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to set custom command name"
            )

        return {"message": "Command customization updated successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error setting command customization for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting command customization: {str(e)}"
        )

@router.post("/guilds/{guild_id}/command-customizations/groups", status_code=status.HTTP_200_OK)
async def set_group_customization(
    guild_id: int,
    customization: GroupCustomizationUpdate,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Set a custom name for a command group in a guild."""
    try:
        # Check if settings_manager is available
        from global_bot_accessor import get_bot_instance
        bot = get_bot_instance()
        if not settings_manager or not bot or not bot.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager or database connection not available"
            )

        # Validate custom name format if provided
        if customization.custom_name is not None:
            if not customization.custom_name.islower() or not customization.custom_name.replace('_', '').isalnum():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom group names must be lowercase and contain only letters, numbers, and underscores"
                )

            if len(customization.custom_name) < 1 or len(customization.custom_name) > 32:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom group names must be between 1 and 32 characters long"
                )

        # Set the custom group name
        success = await settings_manager.set_custom_group_name(
            guild_id,
            customization.group_name,
            customization.custom_name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to set custom group name"
            )

        return {"message": "Group customization updated successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error setting group customization for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting group customization: {str(e)}"
        )

@router.post("/guilds/{guild_id}/command-customizations/aliases", status_code=status.HTTP_200_OK)
async def add_command_alias(
    guild_id: int,
    alias: CommandAliasAdd,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Add an alias for a command in a guild."""
    try:
        # Check if settings_manager is available
        from global_bot_accessor import get_bot_instance
        bot = get_bot_instance()
        if not settings_manager or not bot or not bot.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager or database connection not available"
            )

        # Validate alias format
        if not alias.alias_name.islower() or not alias.alias_name.replace('_', '').isalnum():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aliases must be lowercase and contain only letters, numbers, and underscores"
            )

        if len(alias.alias_name) < 1 or len(alias.alias_name) > 32:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aliases must be between 1 and 32 characters long"
            )

        # Add the command alias
        success = await settings_manager.add_command_alias(
            guild_id,
            alias.command_name,
            alias.alias_name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add command alias"
            )

        return {"message": "Command alias added successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error adding command alias for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding command alias: {str(e)}"
        )

@router.delete("/guilds/{guild_id}/command-customizations/aliases", status_code=status.HTTP_200_OK)
async def remove_command_alias(
    guild_id: int,
    alias: CommandAliasRemove,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Remove an alias for a command in a guild."""
    try:
        # Check if settings_manager is available
        from global_bot_accessor import get_bot_instance
        bot = get_bot_instance()
        if not settings_manager or not bot or not bot.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager or database connection not available"
            )

        # Remove the command alias
        success = await settings_manager.remove_command_alias(
            guild_id,
            alias.command_name,
            alias.alias_name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove command alias"
            )

        return {"message": "Command alias removed successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error removing command alias for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing command alias: {str(e)}"
        )

@router.get("/guilds/{guild_id}/settings", response_model=Dict[str, Any])
async def get_guild_settings(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Get settings for a guild."""
    try:
        # Check if settings_manager is available
        from global_bot_accessor import get_bot_instance
        bot = get_bot_instance()
        if not settings_manager or not bot or not bot.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager or database connection not available"
            )

        # Initialize settings with defaults
        settings = {
            "prefix": DEFAULT_PREFIX,
            "welcome_channel_id": None,
            "welcome_message": None,
            "goodbye_channel_id": None,
            "goodbye_message": None,
            "cogs": {},
            "commands": {}
        }

        # Get prefix with error handling
        try:
            settings["prefix"] = await settings_manager.get_guild_prefix(guild_id, DEFAULT_PREFIX)
        except Exception as e:
            log.warning(f"Error getting prefix for guild {guild_id}, using default: {e}")
            # Keep default prefix

        # Get welcome/goodbye settings with error handling
        try:
            settings["welcome_channel_id"] = await settings_manager.get_setting(guild_id, 'welcome_channel_id')
        except Exception as e:
            log.warning(f"Error getting welcome_channel_id for guild {guild_id}: {e}")

        try:
            settings["welcome_message"] = await settings_manager.get_setting(guild_id, 'welcome_message')
        except Exception as e:
            log.warning(f"Error getting welcome_message for guild {guild_id}: {e}")

        try:
            settings["goodbye_channel_id"] = await settings_manager.get_setting(guild_id, 'goodbye_channel_id')
        except Exception as e:
            log.warning(f"Error getting goodbye_channel_id for guild {guild_id}: {e}")

        try:
            settings["goodbye_message"] = await settings_manager.get_setting(guild_id, 'goodbye_message')
        except Exception as e:
            log.warning(f"Error getting goodbye_message for guild {guild_id}: {e}")

        # Get cog enabled statuses with error handling
        try:
            settings["cogs"] = await settings_manager.get_all_enabled_cogs(guild_id)
        except Exception as e:
            log.warning(f"Error getting cog enabled statuses for guild {guild_id}: {e}")
            # Keep empty dict for cogs

        # Get command enabled statuses with error handling
        try:
            settings["commands"] = await settings_manager.get_all_enabled_commands(guild_id)
        except Exception as e:
            log.warning(f"Error getting command enabled statuses for guild {guild_id}: {e}")
            # Keep empty dict for commands

        return settings
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except RuntimeError as e:
        # Handle event loop errors specifically
        if "got Future" in str(e) and "attached to a different loop" in str(e):
            log.error(f"Event loop error getting settings for guild {guild_id}: {e}")
            # Return a more helpful error message
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error. Please try again."
            )
        else:
            log.error(f"Runtime error getting settings for guild {guild_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error getting settings: {str(e)}"
            )
    except Exception as e:
        log.error(f"Error getting settings for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting settings: {str(e)}"
        )

@router.patch("/guilds/{guild_id}/settings", status_code=status.HTTP_200_OK)
async def update_guild_settings(
    guild_id: int,
    settings_update: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Update settings for a guild."""
    try:
        # Check if settings_manager is available
        from global_bot_accessor import get_bot_instance
        bot = get_bot_instance()
        if not settings_manager or not bot or not bot.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager or database connection not available"
            )

        log.info(f"Updating settings for guild {guild_id} requested by user {_user.get('user_id')}")
        log.debug(f"Update data received: {settings_update}")

        success_flags = []

        # Get bot instance for core cogs check
        try:
            import discord_bot_sync_api
            bot = discord_bot_sync_api.bot_instance
            core_cogs_list = bot.core_cogs if bot and hasattr(bot, 'core_cogs') else {'SettingsCog', 'HelpCog'}
        except ImportError:
            core_cogs_list = {'SettingsCog', 'HelpCog'}  # Core cogs that cannot be disabled

        # Update prefix if provided
        if 'prefix' in settings_update:
            success = await settings_manager.set_guild_prefix(guild_id, settings_update['prefix'])
            success_flags.append(success)
            if not success:
                log.error(f"Failed to update prefix for guild {guild_id}")

        # Update welcome channel if provided
        if 'welcome_channel_id' in settings_update:
            value = settings_update['welcome_channel_id'] if settings_update['welcome_channel_id'] else None
            success = await settings_manager.set_setting(guild_id, 'welcome_channel_id', value)
            success_flags.append(success)
            if not success:
                log.error(f"Failed to update welcome_channel_id for guild {guild_id}")

        # Update welcome message if provided
        if 'welcome_message' in settings_update:
            success = await settings_manager.set_setting(guild_id, 'welcome_message', settings_update['welcome_message'])
            success_flags.append(success)
            if not success:
                log.error(f"Failed to update welcome_message for guild {guild_id}")

        # Update goodbye channel if provided
        if 'goodbye_channel_id' in settings_update:
            value = settings_update['goodbye_channel_id'] if settings_update['goodbye_channel_id'] else None
            success = await settings_manager.set_setting(guild_id, 'goodbye_channel_id', value)
            success_flags.append(success)
            if not success:
                log.error(f"Failed to update goodbye_channel_id for guild {guild_id}")

        # Update goodbye message if provided
        if 'goodbye_message' in settings_update:
            success = await settings_manager.set_setting(guild_id, 'goodbye_message', settings_update['goodbye_message'])
            success_flags.append(success)
            if not success:
                log.error(f"Failed to update goodbye_message for guild {guild_id}")

        # Update cogs if provided
        if 'cogs' in settings_update and isinstance(settings_update['cogs'], dict):
            for cog_name, enabled_status in settings_update['cogs'].items():
                if cog_name not in core_cogs_list:
                    success = await settings_manager.set_cog_enabled(guild_id, cog_name, enabled_status)
                    success_flags.append(success)
                    if not success:
                        log.error(f"Failed to update status for cog '{cog_name}' for guild {guild_id}")
                else:
                    log.warning(f"Attempted to change status of core cog '{cog_name}' for guild {guild_id} - ignored.")

        # Update commands if provided
        if 'commands' in settings_update and isinstance(settings_update['commands'], dict):
            for command_name, enabled_status in settings_update['commands'].items():
                success = await settings_manager.set_command_enabled(guild_id, command_name, enabled_status)
                success_flags.append(success)
                if not success:
                    log.error(f"Failed to update status for command '{command_name}' for guild {guild_id}")

        if all(s is True for s in success_flags):  # Check if all operations returned True
            return {"message": "Settings updated successfully."}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="One or more settings failed to update. Check server logs."
            )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error updating settings for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating settings: {str(e)}"
        )

@router.post("/guilds/{guild_id}/sync-commands", status_code=status.HTTP_200_OK)
async def sync_guild_commands(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Sync commands for a guild to apply customizations."""
    try:
        # This endpoint would trigger a command sync for the guild
        # In a real implementation, this would communicate with the bot to sync commands
        # For now, we'll just return a success message
        # TODO: Implement actual command syncing logic
        return {"message": "Command sync requested. This may take a moment to complete."}
    except Exception as e:
        log.error(f"Error syncing commands for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error syncing commands: {str(e)}"
        )

@router.post("/guilds/{guild_id}/test-welcome", status_code=status.HTTP_200_OK)
async def test_welcome_message(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Test the welcome message for a guild."""
    # This endpoint is now handled by the main API server
    # We'll just redirect to the main API server endpoint
    try:
        # Import the main API server endpoint
        try:
            from api_service.api_server import dashboard_test_welcome_message
        except ImportError:
            from .api_server import dashboard_test_welcome_message

        # Call the main API server endpoint
        return await dashboard_test_welcome_message(guild_id, _user, _admin)
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error testing welcome message for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing welcome message: {str(e)}"
        )

@router.post("/guilds/{guild_id}/test-goodbye", status_code=status.HTTP_200_OK)
async def test_goodbye_message(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Test the goodbye message for a guild."""
    # This endpoint is now handled by the main API server
    # We'll just redirect to the main API server endpoint
    try:
        # Import the main API server endpoint
        try:
            from api_service.api_server import dashboard_test_goodbye_message
        except ImportError:
            from .api_server import dashboard_test_goodbye_message

        # Call the main API server endpoint
        return await dashboard_test_goodbye_message(guild_id, _user, _admin)
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error testing goodbye message for guild {guild_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing goodbye message: {str(e)}"
        )

# --- Global Settings Endpoints ---

@router.get("/settings", response_model=GlobalSettings)
async def get_global_settings(
    _user: dict = Depends(get_dashboard_user)
):
    """Get global settings for the current user."""
    try:
        # Import the database module for user settings
        try:
            from api_service.api_server import db
        except ImportError:
            from api_service.api_server import db

        if not db:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available"
            )

        # Get user settings from the database
        user_id = _user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not found in session"
            )

        user_settings = db.get_user_settings(user_id)
        if not user_settings:
            # Return default settings if none exist
            return GlobalSettings(
                system_message="",
                character="",
                character_info="",
                custom_instructions="",
                model="openai/gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=1000
            )

        # Convert from UserSettings to GlobalSettings
        global_settings = GlobalSettings(
            system_message=user_settings.get("system_message", ""),
            character=user_settings.get("character", ""),
            character_info=user_settings.get("character_info", ""),
            custom_instructions=user_settings.get("custom_instructions", ""),
            model=user_settings.get("model_id", "openai/gpt-3.5-turbo"),
            temperature=user_settings.get("temperature", 0.7),
            max_tokens=user_settings.get("max_tokens", 1000)
        )

        # Add theme settings if available
        if "theme" in user_settings:
            theme_data = user_settings["theme"]
            global_settings.theme = ThemeSettings(
                theme_mode=theme_data.get("theme_mode", "light"),
                primary_color=theme_data.get("primary_color", "#5865F2"),
                secondary_color=theme_data.get("secondary_color", "#2D3748"),
                accent_color=theme_data.get("accent_color", "#7289DA"),
                font_family=theme_data.get("font_family", "Inter, sans-serif"),
                custom_css=theme_data.get("custom_css")
            )

        return global_settings
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error getting global settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting global settings: {str(e)}"
        )

@router.post("/settings", status_code=status.HTTP_200_OK)
@router.put("/settings", status_code=status.HTTP_200_OK)
async def update_global_settings(
    settings: GlobalSettings,
    _user: dict = Depends(get_dashboard_user)
):
    """Update global settings for the current user."""
    try:
        # Import the database module for user settings
        try:
            from api_service.api_server import db
            from api_service.api_models import UserSettings
        except ImportError:
            from api_service.api_server import db
            from api_models import UserSettings

        if not db:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available"
            )

        # Get user ID from session
        user_id = _user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not found in session"
            )

        # Convert from GlobalSettings to UserSettings
        user_settings = UserSettings(
            model_id=settings.model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            system_message=settings.system_message,
            character=settings.character,
            character_info=settings.character_info,
            custom_instructions=settings.custom_instructions
        )

        # Add theme settings if provided
        if settings.theme:
            from api_service.api_models import ThemeSettings as ApiThemeSettings
            user_settings.theme = ApiThemeSettings(
                theme_mode=settings.theme.theme_mode,
                primary_color=settings.theme.primary_color,
                secondary_color=settings.theme.secondary_color,
                accent_color=settings.theme.accent_color,
                font_family=settings.theme.font_family,
                custom_css=settings.theme.custom_css
            )

        # Save user settings to the database
        updated_settings = db.save_user_settings(user_id, user_settings)
        if not updated_settings:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save user settings"
            )

        log.info(f"Updated global settings for user {user_id}")
        return {"message": "Settings updated successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Error updating global settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating global settings: {str(e)}"
        )

# --- Cog and Command Management Endpoints ---
# Note: These endpoints have been moved to cog_management_endpoints.py

# --- Cog Management Endpoints ---
# These endpoints provide direct implementation and fallback for cog management

# Define models needed for cog management
class CogCommandInfo(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True

class CogInfo(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    commands: List[Dict[str, Any]] = []

@router.get("/guilds/{guild_id}/cogs", response_model=List[Any])
async def get_guild_cogs_redirect(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Get all cogs and their commands for a guild."""
    try:
        # First try to use the dedicated cog management endpoint
        try:
            # Try relative import first
            from .cog_management_endpoints import get_guild_cogs
            log.info(f"Successfully imported get_guild_cogs via relative import")

            # Call the cog management endpoint
            log.info(f"Calling get_guild_cogs for guild {guild_id}")
            result = await get_guild_cogs(guild_id, _user, _admin)
            log.info(f"Successfully retrieved cogs for guild {guild_id}")
            return result
        except ImportError as e:
            log.warning(f"Relative import failed: {e}, trying absolute import")
            try:
                # Fall back to absolute import
                from cog_management_endpoints import get_guild_cogs
                log.info(f"Successfully imported get_guild_cogs via absolute import")

                # Call the cog management endpoint
                log.info(f"Calling get_guild_cogs for guild {guild_id}")
                result = await get_guild_cogs(guild_id, _user, _admin)
                log.info(f"Successfully retrieved cogs for guild {guild_id}")
                return result
            except ImportError as e2:
                log.error(f"Both import attempts failed: {e2}")
                log.warning("Falling back to direct implementation")

                # Fall back to direct implementation
                # Check if bot instance is available via discord_bot_sync_api
                try:
                    import discord_bot_sync_api
                    bot = discord_bot_sync_api.bot_instance
                    if not bot:
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Bot instance not available"
                        )
                except ImportError:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Bot sync API not available"
                    )

                # Get all cogs from the bot
                cogs_list = []
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

@router.patch("/guilds/{guild_id}/cogs/{cog_name}", status_code=status.HTTP_200_OK)
async def update_cog_status_redirect(
    guild_id: int,
    cog_name: str,
    enabled: bool = Body(..., embed=True),
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Enable or disable a cog for a guild."""
    try:
        # First try to use the dedicated cog management endpoint
        try:
            # Try relative import first
            from .cog_management_endpoints import update_cog_status
            log.info(f"Successfully imported update_cog_status via relative import")

            # Call the cog management endpoint
            log.info(f"Calling update_cog_status for guild {guild_id}, cog {cog_name}, enabled={enabled}")
            result = await update_cog_status(guild_id, cog_name, enabled, _user, _admin)
            log.info(f"Successfully updated cog status for guild {guild_id}, cog {cog_name}")
            return result
        except ImportError as e:
            log.warning(f"Relative import failed: {e}, trying absolute import")
            try:
                # Fall back to absolute import
                from cog_management_endpoints import update_cog_status
                log.info(f"Successfully imported update_cog_status via absolute import")

                # Call the cog management endpoint
                log.info(f"Calling update_cog_status for guild {guild_id}, cog {cog_name}, enabled={enabled}")
                result = await update_cog_status(guild_id, cog_name, enabled, _user, _admin)
                log.info(f"Successfully updated cog status for guild {guild_id}, cog {cog_name}")
                return result
            except ImportError as e2:
                log.error(f"Both import attempts failed: {e2}")
                log.warning("Falling back to direct implementation")

                # Fall back to direct implementation
                # Check if settings_manager is available
                from global_bot_accessor import get_bot_instance
                bot = get_bot_instance()
                if not settings_manager or not bot or not bot.pg_pool:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Settings manager or database connection not available"
                    )

                # Check if the cog exists
                try:
                    import discord_bot_sync_api
                    bot = discord_bot_sync_api.bot_instance
                    if not bot:
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Bot instance not available"
                        )

                    if cog_name not in bot.cogs:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Cog '{cog_name}' not found"
                        )

                    # Check if it's a core cog
                    core_cogs = getattr(bot, 'core_cogs', {'SettingsCog', 'HelpCog'})
                    if cog_name in core_cogs:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Core cog '{cog_name}' cannot be disabled"
                        )
                except ImportError:
                    # If we can't import the bot, we'll just assume the cog exists
                    log.warning("Bot sync API not available, skipping cog existence check")

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

@router.patch("/guilds/{guild_id}/commands/{command_name}", status_code=status.HTTP_200_OK)
async def update_command_status_redirect(
    guild_id: int,
    command_name: str,
    enabled: bool = Body(..., embed=True),
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Enable or disable a command for a guild."""
    try:
        # First try to use the dedicated cog management endpoint
        try:
            # Try relative import first
            from .cog_management_endpoints import update_command_status
            log.info(f"Successfully imported update_command_status via relative import")

            # Call the cog management endpoint
            log.info(f"Calling update_command_status for guild {guild_id}, command {command_name}, enabled={enabled}")
            result = await update_command_status(guild_id, command_name, enabled, _user, _admin)
            log.info(f"Successfully updated command status for guild {guild_id}, command {command_name}")
            return result
        except ImportError as e:
            log.warning(f"Relative import failed: {e}, trying absolute import")
            try:
                # Fall back to absolute import
                from cog_management_endpoints import update_command_status
                log.info(f"Successfully imported update_command_status via absolute import")

                # Call the cog management endpoint
                log.info(f"Calling update_command_status for guild {guild_id}, command {command_name}, enabled={enabled}")
                result = await update_command_status(guild_id, command_name, enabled, _user, _admin)
                log.info(f"Successfully updated command status for guild {guild_id}, command {command_name}")
                return result
            except ImportError as e2:
                log.error(f"Both import attempts failed: {e2}")
                log.warning("Falling back to direct implementation")

                # Fall back to direct implementation
                # Check if settings_manager is available
                from global_bot_accessor import get_bot_instance
                bot = get_bot_instance()
                if not settings_manager or not bot or not bot.pg_pool:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Settings manager or database connection not available"
                    )

                # Check if the command exists
                try:
                    import discord_bot_sync_api
                    bot = discord_bot_sync_api.bot_instance
                    if not bot:
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Bot instance not available"
                        )

                    # Check if it's a prefix command
                    command = bot.get_command(command_name)
                    if not command:
                        # Check if it's an app command
                        app_commands = [cmd for cmd in bot.tree.get_commands() if cmd.name == command_name]
                        if not app_commands:
                            raise HTTPException(
                                status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Command '{command_name}' not found"
                            )
                except ImportError:
                    # If we can't import the bot, we'll just assume the command exists
                    log.warning("Bot sync API not available, skipping command existence check")

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

# --- Conversations Endpoints ---

@router.get("/conversations", response_model=List[Conversation])
async def get_conversations(
    _user: dict = Depends(get_dashboard_user)
):
    """Get all conversations for the current user."""
    try:
        # This would normally fetch conversations from the database
        # For now, we'll return a mock response
        # TODO: Implement actual conversation fetching
        conversations = [
            Conversation(
                id="1",
                title="Conversation 1",
                created_at="2023-01-01T00:00:00Z",
                updated_at="2023-01-01T01:00:00Z",
                message_count=10
            ),
            Conversation(
                id="2",
                title="Conversation 2",
                created_at="2023-01-02T00:00:00Z",
                updated_at="2023-01-02T01:00:00Z",
                message_count=5
            )
        ]
        return conversations
    except Exception as e:
        log.error(f"Error getting conversations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting conversations: {str(e)}"
        )

@router.get("/conversations/{conversation_id}", response_model=List[Message])
async def get_conversation_messages(
    conversation_id: str,
    _user: dict = Depends(get_dashboard_user)
):
    """Get all messages for a conversation."""
    try:
        # This would normally fetch messages from the database
        # For now, we'll return a mock response
        # TODO: Implement actual message fetching
        messages = [
            Message(
                id="1",
                content="Hello, how are you?",
                role="user",
                created_at="2023-01-01T00:00:00Z"
            ),
            Message(
                id="2",
                content="I'm doing well, thank you for asking!",
                role="assistant",
                created_at="2023-01-01T00:00:01Z"
            )
        ]
        return messages
    except Exception as e:
        log.error(f"Error getting conversation messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting conversation messages: {str(e)}"
        )

# --- Git Monitor Webhook Event Configuration Endpoints ---

class GitRepositoryEventSettings(BaseModel):
    events: List[str]

class AvailableGitEventsResponse(BaseModel):
    platform: str
    events: List[str]

SUPPORTED_GITHUB_EVENTS = [
    "push", "issues", "issue_comment", "pull_request", "pull_request_review",
    "pull_request_review_comment", "release", "fork", "star", "watch",
    "commit_comment", "create", "delete", "deployment", "deployment_status",
    "gollum", "member", "milestone", "project_card", "project_column", "project",
    "public", "repository_dispatch", "status"
    # Add more as needed/supported by formatters
]
SUPPORTED_GITLAB_EVENTS = [
    "push", "tag_push", "issues", "note", "merge_request", "wiki_page",
    "pipeline", "job", "release"
    # Add more as needed/supported by formatters
    # GitLab uses "push_events", "issues_events" etc. in webhook config,
    # but object_kind in payload is often singular like "push", "issue".
    # We'll store and expect the singular/object_kind style.
]

@router.get("/git_monitors/available_events/{platform}", response_model=AvailableGitEventsResponse)
async def get_available_git_events(
    platform: str,
    _user: dict = Depends(get_dashboard_user) # Basic auth to access
):
    """Get a list of available/supported webhook event types for a given platform."""
    if platform == "github":
        return AvailableGitEventsResponse(platform="github", events=SUPPORTED_GITHUB_EVENTS)
    elif platform == "gitlab":
        return AvailableGitEventsResponse(platform="gitlab", events=SUPPORTED_GITLAB_EVENTS)
    else:
        raise HTTPException(status_code=400, detail="Invalid platform specified. Use 'github' or 'gitlab'.")


@router.get("/guilds/{guild_id}/git_monitors/{repo_db_id}/events", response_model=GitRepositoryEventSettings)
async def get_git_repository_event_settings(
    guild_id: int, # Added for verify_dashboard_guild_admin
    repo_db_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin) # Ensures user is admin of the guild
):
    """Get the current allowed webhook events for a specific monitored repository."""
    try:
        repo_config = await settings_manager.get_monitored_repository_by_id(repo_db_id)
        if not repo_config:
            raise HTTPException(status_code=404, detail="Monitored repository not found.")
        if repo_config['guild_id'] != guild_id: # Ensure the repo belongs to the specified guild
             raise HTTPException(status_code=403, detail="Repository does not belong to this guild.")

        allowed_events = repo_config.get('allowed_webhook_events', ['push']) # Default to ['push']
        return GitRepositoryEventSettings(events=allowed_events)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting git repository event settings for repo {repo_db_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve repository event settings.")

@router.put("/guilds/{guild_id}/git_monitors/{repo_db_id}/events", status_code=status.HTTP_200_OK)
async def update_git_repository_event_settings(
    guild_id: int, # Added for verify_dashboard_guild_admin
    repo_db_id: int,
    settings: GitRepositoryEventSettings,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin) # Ensures user is admin of the guild
):
    """Update the allowed webhook events for a specific monitored repository."""
    try:
        repo_config = await settings_manager.get_monitored_repository_by_id(repo_db_id)
        if not repo_config:
            raise HTTPException(status_code=404, detail="Monitored repository not found.")
        if repo_config['guild_id'] != guild_id: # Ensure the repo belongs to the specified guild
             raise HTTPException(status_code=403, detail="Repository does not belong to this guild.")
        if repo_config['monitoring_method'] != 'webhook':
            raise HTTPException(status_code=400, detail="Event settings are only applicable for webhook monitoring method.")

        # Validate events against supported list for the platform
        platform = repo_config['platform']
        supported_events = SUPPORTED_GITHUB_EVENTS if platform == "github" else SUPPORTED_GITLAB_EVENTS
        for event in settings.events:
            if event not in supported_events:
                raise HTTPException(status_code=400, detail=f"Event '{event}' is not supported for platform '{platform}'.")

        success = await settings_manager.update_monitored_repository_events(repo_db_id, settings.events)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update repository event settings.")
        return {"message": "Repository event settings updated successfully."}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error updating git repository event settings for repo {repo_db_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update repository event settings.")
