"""
Dashboard API endpoints for the bot dashboard.
These endpoints provide additional functionality for the dashboard UI.
"""

import logging
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

# Import the dependencies from api_server.py
try:
    # Try relative import first
    from .api_server import get_dashboard_user, verify_dashboard_guild_admin
except ImportError:
    # Fall back to absolute import
    from api_server import get_dashboard_user, verify_dashboard_guild_admin

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
