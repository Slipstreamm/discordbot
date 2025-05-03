import aiohttp
import json
import datetime
from typing import Dict, List, Optional, Any, Union
from api_models import Conversation, UserSettings, Message

class ApiClient:
    def __init__(self, api_url: str, token: Optional[str] = None):
        """
        Initialize the API client

        Args:
            api_url: The URL of the API server
            token: The Discord token to use for authentication
        """
        self.api_url = api_url
        self.token = token

    def set_token(self, token: str):
        """Set the Discord token for authentication"""
        self.token = token

    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None):
        """
        Make a request to the API

        Args:
            method: The HTTP method to use
            endpoint: The API endpoint to call
            data: The data to send with the request

        Returns:
            The response data
        """
        if not self.token:
            raise ValueError("No token set for API client")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        url = f"{self.api_url}/{endpoint}"

        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API request failed: {response.status} - {error_text}")
                    response_text = await response.text()
                    return json.loads(response_text)
            elif method == "POST":
                # Convert data to JSON with datetime handling
                json_data = json.dumps(data, default=str, ensure_ascii=False) if data else None
                # Update headers for manually serialized JSON
                if json_data:
                    headers["Content-Type"] = "application/json"
                async with session.post(url, headers=headers, data=json_data) as response:
                    if response.status not in (200, 201):
                        error_text = await response.text()
                        raise Exception(f"API request failed: {response.status} - {error_text}")
                    response_text = await response.text()
                    return json.loads(response_text)
            elif method == "PUT":
                # Convert data to JSON with datetime handling
                json_data = json.dumps(data, default=str, ensure_ascii=False) if data else None
                # Update headers for manually serialized JSON
                if json_data:
                    headers["Content-Type"] = "application/json"
                async with session.put(url, headers=headers, data=json_data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API request failed: {response.status} - {error_text}")
                    response_text = await response.text()
                    return json.loads(response_text)
            elif method == "DELETE":
                async with session.delete(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API request failed: {response.status} - {error_text}")
                    response_text = await response.text()
                    return json.loads(response_text)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

    # ============= Conversation Methods =============

    async def get_conversations(self) -> List[Conversation]:
        """Get all conversations for the authenticated user"""
        response = await self._make_request("GET", "conversations")
        return [Conversation.model_validate(conv) for conv in response["conversations"]]

    async def get_conversation(self, conversation_id: str) -> Conversation:
        """Get a specific conversation"""
        response = await self._make_request("GET", f"conversations/{conversation_id}")
        return Conversation.model_validate(response)

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        """Create a new conversation"""
        response = await self._make_request("POST", "conversations", {"conversation": conversation.model_dump()})
        return Conversation.model_validate(response)

    async def update_conversation(self, conversation: Conversation) -> Conversation:
        """Update an existing conversation"""
        response = await self._make_request("PUT", f"conversations/{conversation.id}", {"conversation": conversation.model_dump()})
        return Conversation.model_validate(response)

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation"""
        response = await self._make_request("DELETE", f"conversations/{conversation_id}")
        return response["success"]

    # ============= Settings Methods =============

    async def get_settings(self) -> UserSettings:
        """Get settings for the authenticated user"""
        response = await self._make_request("GET", "settings")
        return UserSettings.model_validate(response["settings"])

    async def update_settings(self, settings: UserSettings) -> UserSettings:
        """Update settings for the authenticated user"""
        response = await self._make_request("PUT", "settings", {"settings": settings.model_dump()})
        return UserSettings.model_validate(response)

    # ============= Helper Methods =============

    async def save_discord_conversation(
        self,
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
    ) -> Conversation:
        """
        Save a conversation from Discord to the API

        Args:
            messages: List of message dictionaries with 'content', 'role', and 'timestamp'
            model_id: The model ID to use for the conversation
            conversation_id: Optional ID for the conversation (will create new if not provided)
            title: The title of the conversation
            reasoning_enabled: Whether reasoning is enabled for the conversation
            reasoning_effort: The reasoning effort level ("low", "medium", "high")
            temperature: The temperature setting for the model
            max_tokens: The maximum tokens setting for the model
            web_search_enabled: Whether web search is enabled for the conversation
            system_message: Optional system message for the conversation

        Returns:
            The saved Conversation object
        """
        # Convert messages to the API format
        api_messages = []
        for msg in messages:
            api_messages.append(Message(
                content=msg["content"],
                role=msg["role"],
                timestamp=msg.get("timestamp", datetime.datetime.now()),
                reasoning=msg.get("reasoning"),
                usage_data=msg.get("usage_data")
            ))

        # Create or update the conversation
        if conversation_id:
            # Try to get the existing conversation
            try:
                conversation = await self.get_conversation(conversation_id)
                # Update the conversation
                conversation.messages = api_messages
                conversation.model_id = model_id
                conversation.reasoning_enabled = reasoning_enabled
                conversation.reasoning_effort = reasoning_effort
                conversation.temperature = temperature
                conversation.max_tokens = max_tokens
                conversation.web_search_enabled = web_search_enabled
                conversation.system_message = system_message
                conversation.updated_at = datetime.datetime.now()

                return await self.update_conversation(conversation)
            except Exception:
                # Conversation doesn't exist, create a new one
                pass

        # Create a new conversation
        conversation = Conversation(
            id=conversation_id if conversation_id else None,
            title=title,
            messages=api_messages,
            model_id=model_id,
            reasoning_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_tokens=max_tokens,
            web_search_enabled=web_search_enabled,
            system_message=system_message,
            created_at=datetime.datetime.now(),
            updated_at=datetime.datetime.now()
        )

        return await self.create_conversation(conversation)
