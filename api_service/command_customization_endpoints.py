"""
Command customization API endpoints for the bot dashboard.
These endpoints provide functionality for customizing command names and groups.
"""

import logging
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

# Import dependencies from the new dependencies module (use absolute path)
from discordbot.api_service.dependencies import get_dashboard_user, verify_dashboard_guild_admin

# Import models from the new dashboard_models module (use absolute path)
from discordbot.api_service.dashboard_models import (
    CommandCustomizationResponse,
    CommandCustomizationUpdate,
        GroupCustomizationUpdate,
    GroupCustomizationUpdate,
    CommandAliasAdd,
    CommandAliasRemove
)

# Import settings_manager for database access (use absolute path)
from discordbot import settings_manager

log = logging.getLogger(__name__)

# Create the router
router = APIRouter()

# --- Command Customization Endpoints ---

@router.get("/customizations/{guild_id}", response_model=CommandCustomizationResponse)
async def get_command_customizations(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Get all command customizations for a guild."""
    try:
        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
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

        # Convert command_customizations to the new format
        formatted_command_customizations = {}
        for cmd_name, cmd_data in command_customizations.items():
            formatted_command_customizations[cmd_name] = {
                'name': cmd_data.get('name', cmd_name),
                'description': cmd_data.get('description')
            }

        return CommandCustomizationResponse(
            command_customizations=formatted_command_customizations,
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

@router.post("/customizations/{guild_id}/commands", status_code=status.HTTP_200_OK)
async def set_command_customization(
    guild_id: int,
    customization: CommandCustomizationUpdate,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Set a custom name and/or description for a command in a guild."""
    try:
        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
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

        # Validate custom description if provided
        if customization.custom_description is not None:
            if len(customization.custom_description) > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom command descriptions must be 100 characters or less"
                )

        # Set the custom command name
        name_success = await settings_manager.set_custom_command_name(
            guild_id,
            customization.command_name,
            customization.custom_name
        )

        if not name_success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to set custom command name"
            )

        # Set the custom command description if provided
        if customization.custom_description is not None:
            desc_success = await settings_manager.set_custom_command_description(
                guild_id,
                customization.command_name,
                customization.custom_description
            )

            if not desc_success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to set custom command description"
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

@router.post("/customizations/{guild_id}/groups", status_code=status.HTTP_200_OK)
async def set_group_customization(
    guild_id: int,
    customization: GroupCustomizationUpdate,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Set a custom name for a command group in a guild."""
    try:
        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
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

@router.post("/customizations/{guild_id}/aliases", status_code=status.HTTP_200_OK)
async def add_command_alias(
    guild_id: int,
    alias: CommandAliasAdd,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Add an alias for a command in a guild."""
    try:
        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
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

@router.delete("/customizations/{guild_id}/aliases", status_code=status.HTTP_200_OK)
async def remove_command_alias(
    guild_id: int,
    alias: CommandAliasRemove,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Remove an alias for a command in a guild."""
    try:
        # Check if settings_manager is available
        if not settings_manager or not settings_manager.get_pg_pool():
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

@router.post("/customizations/{guild_id}/sync", status_code=status.HTTP_200_OK)
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
