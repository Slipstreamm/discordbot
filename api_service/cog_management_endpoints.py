"""
Cog Management API endpoints for the bot dashboard.
These endpoints provide functionality for managing cogs and commands.
"""

import logging
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, Field

# Import dependencies from the new dependencies module (use absolute path)
from api_service.dependencies import get_dashboard_user, verify_dashboard_guild_admin

# Import settings_manager for database access (use absolute path)
import settings_manager

# Set up logging
log = logging.getLogger(__name__)

# Import models from the new dashboard_models module (use absolute path)
from api_service.dashboard_models import CogInfo # Import necessary models

# Create a router for the cog management API endpoints
router = APIRouter(tags=["Cog Management"])

# --- Endpoints ---
# Models CogInfo and CommandInfo are now imported from dashboard_models.py
@router.get("/guilds/{guild_id}/cogs", response_model=List[CogInfo])
async def get_guild_cogs(
    guild_id: int,
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Get all cogs and their commands for a guild."""
    try:
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
async def update_cog_status(
    guild_id: int,
    cog_name: str,
    enabled: bool = Body(..., embed=True),
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Enable or disable a cog for a guild."""
    try:
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
            if cog_name in bot.core_cogs:
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
async def update_command_status(
    guild_id: int,
    command_name: str,
    enabled: bool = Body(..., embed=True),
    _user: dict = Depends(get_dashboard_user),
    _admin: bool = Depends(verify_dashboard_guild_admin)
):
    """Enable or disable a command for a guild."""
    try:
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
