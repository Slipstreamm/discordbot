from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
import datetime
import uuid

# ============= Data Models =============

class Message(BaseModel):
    content: str
    role: str  # "user", "assistant", or "system"
    timestamp: datetime.datetime
    reasoning: Optional[str] = None
    usage_data: Optional[Dict[str, Any]] = None

class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    messages: List[Message] = []
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    # Conversation-specific settings
    model_id: str = "openai/gpt-3.5-turbo"
    reasoning_enabled: bool = False
    reasoning_effort: str = "medium"  # "low", "medium", "high"
    temperature: float = 0.7
    max_tokens: int = 1000
    web_search_enabled: bool = False
    system_message: Optional[str] = None

class ThemeSettings(BaseModel):
    """Theme settings for the dashboard UI"""
    theme_mode: str = "light"  # "light", "dark", "custom"
    primary_color: str = "#5865F2"  # Discord blue
    secondary_color: str = "#2D3748"
    accent_color: str = "#7289DA"
    font_family: str = "Inter, sans-serif"
    custom_css: Optional[str] = None

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

    # Theme settings
    theme: ThemeSettings = Field(default_factory=ThemeSettings)

    # Last updated timestamp
    last_updated: datetime.datetime = Field(default_factory=datetime.datetime.now)

# ============= API Request/Response Models =============

class GetConversationsResponse(BaseModel):
    conversations: List[Conversation]

class GetSettingsResponse(BaseModel):
    settings: UserSettings

class UpdateSettingsRequest(BaseModel):
    settings: UserSettings

class UpdateConversationRequest(BaseModel):
    conversation: Conversation

class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None
