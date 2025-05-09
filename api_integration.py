import os
import asyncio
import datetime
from typing import Dict, List, Optional, Any, Union
import sys
import json

# Add the api_service directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'api_service'))

# Import the API client and models
from api_service.discord_client import ApiClient
from api_service.api_models import Conversation, UserSettings, Message

# API client instance
api_client = None

# Initialize the API client
def init_api_client(api_url: str):
    """Initialize the API client with the given URL"""
    global api_client
    api_client = ApiClient(api_url)
    return api_client

# Set the Discord token for the API client
def set_token(token: str):
    """Set the Discord token for the API client"""
    if api_client:
        api_client.set_token(token)
    else:
        raise ValueError("API client not initialized")

# ============= Conversation Methods =============

async def get_user_conversations(user_id: str, token: str) -> List[Conversation]:
    """Get all conversations for a user"""
    if not api_client:
        raise ValueError("API client not initialized")
    
    # Set the token for this request
    api_client.set_token(token)
    
    try:
        return await api_client.get_conversations()
    except Exception as e:
        print(f"Error getting conversations for user {user_id}: {e}")
        return []

async def save_discord_conversation(
    user_id: str,
    token: str,
    messages: List[Dict[str, Any]],
    model_id: str = "openai/gpt-3.5-turbo",
    conversation_id: Optional[str] = None,
    title: str = "Discord Conversation",
    reasoning_enabled: bool = False,
    reasoning_effort: str = "medium",
    temperature: float = 0.7,
    max_tokens: int = 1000,
    web_search_enabled: bool = False,
    system_message: Optional[str] = None
) -> Optional[Conversation]:
    """Save a conversation from Discord to the API"""
    if not api_client:
        raise ValueError("API client not initialized")
    
    # Set the token for this request
    api_client.set_token(token)
    
    try:
        return await api_client.save_discord_conversation(
            messages=messages,
            model_id=model_id,
            conversation_id=conversation_id,
            title=title,
            reasoning_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_tokens=max_tokens,
            web_search_enabled=web_search_enabled,
            system_message=system_message
        )
    except Exception as e:
        print(f"Error saving conversation for user {user_id}: {e}")
        return None

# ============= Settings Methods =============

async def get_user_settings(user_id: str, token: str) -> Optional[UserSettings]:
    """Get settings for a user"""
    if not api_client:
        raise ValueError("API client not initialized")
    
    # Set the token for this request
    api_client.set_token(token)
    
    try:
        return await api_client.get_settings()
    except Exception as e:
        print(f"Error getting settings for user {user_id}: {e}")
        return None

async def update_user_settings(
    user_id: str,
    token: str,
    settings: UserSettings
) -> Optional[UserSettings]:
    """Update settings for a user"""
    if not api_client:
        raise ValueError("API client not initialized")
    
    # Set the token for this request
    api_client.set_token(token)
    
    try:
        return await api_client.update_settings(settings)
    except Exception as e:
        print(f"Error updating settings for user {user_id}: {e}")
        return None

# ============= Helper Methods =============

def convert_discord_settings_to_api(settings: Dict[str, Any]) -> UserSettings:
    """Convert Discord bot settings to API UserSettings"""
    return UserSettings(
        model_id=settings.get("model", "openai/gpt-3.5-turbo"),
        temperature=settings.get("temperature", 0.7),
        max_tokens=settings.get("max_tokens", 1000),
        reasoning_enabled=settings.get("show_reasoning", False),
        reasoning_effort=settings.get("reasoning_effort", "medium"),
        web_search_enabled=settings.get("web_search_enabled", False),
        system_message=settings.get("system_prompt"),
        character=settings.get("character"),
        character_info=settings.get("character_info"),
        character_breakdown=settings.get("character_breakdown", False),
        custom_instructions=settings.get("custom_instructions"),
        advanced_view_enabled=False,  # Default value
        streaming_enabled=True,  # Default value
        last_updated=datetime.datetime.now()
    )

def convert_api_settings_to_discord(settings: UserSettings) -> Dict[str, Any]:
    """Convert API UserSettings to Discord bot settings"""
    return {
        "model": settings.model_id,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "show_reasoning": settings.reasoning_enabled,
        "reasoning_effort": settings.reasoning_effort,
        "web_search_enabled": settings.web_search_enabled,
        "system_prompt": settings.system_message,
        "character": settings.character,
        "character_info": settings.character_info,
        "character_breakdown": settings.character_breakdown,
        "custom_instructions": settings.custom_instructions
    }
