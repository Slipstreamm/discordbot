"""
Dashboard API endpoints for the bot dashboard.
These endpoints provide additional functionality for the dashboard UI.
"""

import logging
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, Field

# Import the dependencies from api_server.py
try:
    # Try relative import first
    from .api_server import (
        get_dashboard_user,
        verify_dashboard_guild_admin,
        CommandCustomizationResponse,
        CommandCustomizationUpdate,
        GroupCustomizationUpdate,
        CommandAliasAdd,
        CommandAliasRemove
    )
except ImportError:
    # Fall back to absolute import
    from api_server import (
        get_dashboard_user,
        verify_dashboard_guild_admin,
        CommandCustomizationResponse,
        CommandCustomizationUpdate,
        GroupCustomizationUpdate,
        CommandAliasAdd,
        CommandAliasRemove
    )

# Import settings_manager for database access
try:
    from discordbot import settings_manager
except ImportError:
    # Try relative import
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from discordbot import settings_manager

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

class GlobalSettings(BaseModel):
    system_message: Optional[str] = None
    character: Optional[str] = None
    character_info: Optional[str] = None
    custom_instructions: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

# --- Endpoints ---
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
        if not settings_manager or not settings_manager.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
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
        if not settings_manager or not settings_manager.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
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
        if not settings_manager or not settings_manager.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
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
        if not settings_manager or not settings_manager.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
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
        if not settings_manager or not settings_manager.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
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
        if not settings_manager or not settings_manager.pg_pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Settings manager not available"
            )

        log.info(f"Updating settings for guild {guild_id} requested by user {_user.get('user_id')}")
        log.debug(f"Update data received: {settings_update}")

        success_flags = []
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
    try:
        # Get welcome settings
        welcome_channel_id_str = await settings_manager.get_setting(guild_id, 'welcome_channel_id')
        welcome_message_template = await settings_manager.get_setting(guild_id, 'welcome_message', default="Welcome {user} to {server}!")

        # Check if welcome channel is set
        if not welcome_channel_id_str or welcome_channel_id_str == "__NONE__":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Welcome channel not configured"
            )

        # In a real implementation, this would send a test message to the welcome channel
        # For now, we'll just return a success message with the formatted message
        formatted_message = welcome_message_template.format(
            user="@TestUser",
            username="TestUser",
            server=f"Server {guild_id}"
        )

        return {
            "message": "Test welcome message sent",
            "channel_id": welcome_channel_id_str,
            "formatted_message": formatted_message
        }
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

        # In a real implementation, this would send a test message to the goodbye channel
        # For now, we'll just return a success message with the formatted message
        formatted_message = goodbye_message_template.format(
            username="TestUser",
            server=f"Server {guild_id}"
        )

        return {
            "message": "Test goodbye message sent",
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

# --- Global Settings Endpoints ---

@router.get("/settings", response_model=GlobalSettings)
async def get_global_settings(
    _user: dict = Depends(get_dashboard_user)
):
    """Get global settings for the current user."""
    try:
        # Import the database module for user settings
        try:
            from discordbot.api_service.api_server import db
        except ImportError:
            from api_server import db

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
        return GlobalSettings(
            system_message=user_settings.get("system_message", ""),
            character=user_settings.get("character", ""),
            character_info=user_settings.get("character_info", ""),
            custom_instructions=user_settings.get("custom_instructions", ""),
            model=user_settings.get("model_id", "openai/gpt-3.5-turbo"),
            temperature=user_settings.get("temperature", 0.7),
            max_tokens=user_settings.get("max_tokens", 1000)
        )
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
            from discordbot.api_service.api_server import db
            from discordbot.api_service.api_models import UserSettings
        except ImportError:
            from api_server import db
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

# --- Conversations Endpoints ---

@router.get("/conversations", response_model=List[Conversation])
async def get_conversations(
    _user: dict = Depends(get_dashboard_user)
):
    """Get all conversations for the current user."""
    try:
        # This would normally fetch conversations from the database
        # For now, we'll return a mock response
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
