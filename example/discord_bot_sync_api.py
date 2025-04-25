import os
import json
import asyncio
import datetime
from typing import Dict, List, Optional, Any, Union
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import discord
from discord.ext import commands
import aiohttp

# This file contains the API endpoints for syncing conversations between
# the Flutter app and the Discord bot.
# Add this code to your Discord bot project and import it in your main bot file.

# ============= Models =============

class SyncedMessage(BaseModel):
    content: str
    role: str  # "user", "assistant", or "system"
    timestamp: datetime.datetime
    reasoning: Optional[str] = None
    usage_data: Optional[Dict[str, Any]] = None

class SyncedConversation(BaseModel):
    id: str
    title: str
    messages: List[SyncedMessage]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    model_id: str
    sync_source: str = "discord"  # "discord" or "flutter"

class SyncRequest(BaseModel):
    conversations: List[SyncedConversation]
    last_sync_time: Optional[datetime.datetime] = None

class SyncResponse(BaseModel):
    success: bool
    message: str
    conversations: List[SyncedConversation] = []

# ============= Storage =============

# File to store synced conversations
SYNC_DATA_FILE = "synced_conversations.json"

# In-memory storage for conversations
user_conversations: Dict[str, List[SyncedConversation]] = {}

# Load conversations from file
def load_conversations():
    global user_conversations
    if os.path.exists(SYNC_DATA_FILE):
        try:
            with open(SYNC_DATA_FILE, "r") as f:
                data = json.load(f)
                # Convert string keys (user IDs) back to strings
                user_conversations = {k: [SyncedConversation.parse_obj(conv) for conv in v] 
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
            user_id: [conv.dict() for conv in convs]
            for user_id, convs in user_conversations.items()
        }
        with open(SYNC_DATA_FILE, "w") as f:
            json.dump(serializable_data, f, indent=2, default=str)
    except Exception as e:
        print(f"Error saving synced conversations: {e}")

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

app = FastAPI(title="Discord Bot Sync API")

# Add CORS middleware
app.add_middleware(
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

# ============= API Endpoints =============

@app.get("/")
async def root():
    return {"message": "Discord Bot Sync API is running"}

@app.get("/conversations")
async def get_conversations(user_id: str = Depends(verify_discord_token)):
    """Get all conversations for a user"""
    if user_id not in user_conversations:
        return {"conversations": []}
    
    return {"conversations": user_conversations[user_id]}

@app.post("/sync")
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
    
    return SyncResponse(
        success=True,
        message=f"Synced {len(updated_conversations)} conversations",
        conversations=existing_conversations
    )

@app.delete("/conversations/{conversation_id}")
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
            sync_source="discord"
        ))
    
    return synced_conversations

# This function should be called from your Discord bot's AI cog
# to save a new conversation from Discord
def save_discord_conversation(user_id: str, messages: List[Dict[str, Any]], model_id: str = "openai/gpt-3.5-turbo"):
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
            reasoning=None,
            usage_data=None
        ))
    
    # Create a unique ID for this conversation
    conv_id = f"discord_{user_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Create the synced conversation
    synced_conv = SyncedConversation(
        id=conv_id,
        title="Discord Conversation",
        messages=synced_messages,
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
        model_id=model_id,
        sync_source="discord"
    )
    
    # Add to storage
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    user_conversations[user_id].append(synced_conv)
    save_conversations()
    
    return synced_conv

# ============= Integration with AI Cog =============

# Add these functions to your AI cog to integrate with the sync API

"""
# In your ai_cog.py file, add these imports:
from discord_bot_sync_api import save_discord_conversation, load_conversations, user_conversations

# Then modify your _get_ai_response method to save conversations after getting a response:
async def _get_ai_response(self, user_id: int, prompt: str, system_prompt: str = None) -> str:
    # ... existing code ...
    
    # After getting the response and updating conversation_history:
    # Convert the conversation to the synced format and save it
    messages = conversation_history[user_id]
    save_discord_conversation(str(user_id), messages, settings["model"])
    
    return final_response

# You can also add a command to view synced conversations:
@commands.command(name="aisync")
async def ai_sync_status(self, ctx: commands.Context):
    user_id = str(ctx.author.id)
    if user_id not in user_conversations or not user_conversations[user_id]:
        await ctx.reply("You don't have any synced conversations.")
        return
        
    synced_count = len(user_conversations[user_id])
    await ctx.reply(f"You have {synced_count} synced conversations that can be accessed from the Flutter app.")
"""

# ============= Run the API =============

# To run this API with your Discord bot, you need to use uvicorn
# You can start it in a separate thread or process

"""
# In your main bot file, add:
import threading
import uvicorn

def run_api():
    uvicorn.run("discord_bot_sync_api:app", host="0.0.0.0", port=8000)

# Start the API in a separate thread
api_thread = threading.Thread(target=run_api)
api_thread.daemon = True
api_thread.start()
"""
