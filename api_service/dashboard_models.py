"""
Pydantic models used by the Dashboard API endpoints.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any

class GuildSettingsResponse(BaseModel):
    guild_id: str
    prefix: Optional[str] = None
    welcome_channel_id: Optional[str] = None
    welcome_message: Optional[str] = None
    goodbye_channel_id: Optional[str] = None
    goodbye_message: Optional[str] = None
    enabled_cogs: Dict[str, bool] = {} # Cog name -> enabled status
    command_permissions: Dict[str, List[str]] = {} # Command name -> List of allowed role IDs (as strings)

class GuildSettingsUpdate(BaseModel):
    # Use Optional fields for PATCH, only provided fields will be updated
    prefix: Optional[str] = Field(None, min_length=1, max_length=10)
    welcome_channel_id: Optional[str] = Field(None) # Allow empty string or null to disable
    welcome_message: Optional[str] = Field(None)
    goodbye_channel_id: Optional[str] = Field(None) # Allow empty string or null to disable
    goodbye_message: Optional[str] = Field(None)
    cogs: Optional[Dict[str, bool]] = Field(None) # Dict of {cog_name: enabled_status}

class CommandPermission(BaseModel):
    command_name: str
    role_id: str # Keep as string for consistency

class CommandPermissionsResponse(BaseModel):
    permissions: Dict[str, List[str]] # Command name -> List of allowed role IDs

class CommandCustomizationDetail(BaseModel):
    name: str
    description: Optional[str] = None

class CommandCustomizationResponse(BaseModel):
    command_customizations: Dict[str, Dict[str, Optional[str]]] = {} # Original command name -> {name, description}
    group_customizations: Dict[str, str] = {} # Original group name -> Custom group name
    command_aliases: Dict[str, List[str]] = {} # Original command name -> List of aliases

class CommandCustomizationUpdate(BaseModel):
    command_name: str
    custom_name: Optional[str] = None # If None, removes customization
    custom_description: Optional[str] = None # If None, keeps existing or no description

class GroupCustomizationUpdate(BaseModel):
    group_name: str
    custom_name: Optional[str] = None # If None, removes customization

class CommandAliasAdd(BaseModel):
    command_name: str
    alias_name: str

class CommandAliasRemove(BaseModel):
    command_name: str
    alias_name: str

class CogCommandInfo(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True

class CogInfo(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    commands: List[Dict[str, Any]] = []
