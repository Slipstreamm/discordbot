import os
import json
import datetime
from typing import Dict, List, Optional, Any
from api_models import Conversation, UserSettings, Message

# ============= Database Class =============

class Database:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.conversations_file = os.path.join(data_dir, "conversations.json")
        self.settings_file = os.path.join(data_dir, "user_settings.json")
        self.tokens_file = os.path.join(data_dir, "user_tokens.json")

        # Create data directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)

        # In-memory storage
        self.conversations: Dict[str, Dict[str, Conversation]] = {}  # user_id -> conversation_id -> Conversation
        self.user_settings: Dict[str, UserSettings] = {}  # user_id -> UserSettings
        self.user_tokens: Dict[str, Dict[str, Any]] = {}  # user_id -> token_data

        # Load data from files
        self.load_data()

    def load_data(self):
        """Load all data from files"""
        self.load_conversations()
        self.load_user_settings()
        self.load_user_tokens()

    def save_data(self):
        """Save all data to files"""
        self.save_conversations()
        self.save_all_user_settings()
        self.save_user_tokens()

    def load_conversations(self):
        """Load conversations from file"""
        if os.path.exists(self.conversations_file):
            try:
                with open(self.conversations_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Convert to Conversation objects
                    self.conversations = {
                        user_id: {
                            conv_id: Conversation.model_validate(conv_data)
                            for conv_id, conv_data in user_convs.items()
                        }
                        for user_id, user_convs in data.items()
                    }
                print(f"Loaded conversations for {len(self.conversations)} users")
            except Exception as e:
                print(f"Error loading conversations: {e}")
                self.conversations = {}

    def save_conversations(self):
        """Save conversations to file"""
        try:
            # Convert to JSON-serializable format
            serializable_data = {
                user_id: {
                    conv_id: conv.model_dump()
                    for conv_id, conv in user_convs.items()
                }
                for user_id, user_convs in self.conversations.items()
            }
            with open(self.conversations_file, "w", encoding="utf-8") as f:
                json.dump(serializable_data, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving conversations: {e}")

    def load_user_settings(self):
        """Load user settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Convert to UserSettings objects
                    self.user_settings = {
                        user_id: UserSettings.model_validate(settings_data)
                        for user_id, settings_data in data.items()
                    }
                print(f"Loaded settings for {len(self.user_settings)} users")
            except Exception as e:
                print(f"Error loading user settings: {e}")
                self.user_settings = {}

    def save_all_user_settings(self):
        """Save all user settings to file"""
        try:
            # Convert to JSON-serializable format
            serializable_data = {
                user_id: settings.model_dump()
                for user_id, settings in self.user_settings.items()
            }
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(serializable_data, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving user settings: {e}")

    # ============= Conversation Methods =============

    def get_user_conversations(self, user_id: str) -> List[Conversation]:
        """Get all conversations for a user"""
        return list(self.conversations.get(user_id, {}).values())

    def get_conversation(self, user_id: str, conversation_id: str) -> Optional[Conversation]:
        """Get a specific conversation for a user"""
        return self.conversations.get(user_id, {}).get(conversation_id)

    def save_conversation(self, user_id: str, conversation: Conversation) -> Conversation:
        """Save a conversation for a user"""
        # Update the timestamp
        conversation.updated_at = datetime.datetime.now()

        # Initialize user's conversations dict if it doesn't exist
        if user_id not in self.conversations:
            self.conversations[user_id] = {}

        # Save the conversation
        self.conversations[user_id][conversation.id] = conversation

        # Save to disk
        self.save_conversations()

        return conversation

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        """Delete a conversation for a user"""
        if user_id in self.conversations and conversation_id in self.conversations[user_id]:
            del self.conversations[user_id][conversation_id]
            self.save_conversations()
            return True
        return False

    # ============= User Settings Methods =============

    def get_user_settings(self, user_id: str) -> UserSettings:
        """Get settings for a user, creating default settings if they don't exist"""
        if user_id not in self.user_settings:
            self.user_settings[user_id] = UserSettings()

        return self.user_settings[user_id]

    def save_user_settings(self, user_id: str, settings: UserSettings) -> UserSettings:
        """Save settings for a user"""
        # Update the timestamp
        settings.last_updated = datetime.datetime.now()

        # Save the settings
        self.user_settings[user_id] = settings

        # Save to disk
        self.save_all_user_settings()

        return settings

    # ============= User Tokens Methods =============

    def load_user_tokens(self):
        """Load user tokens from file"""
        if os.path.exists(self.tokens_file):
            try:
                with open(self.tokens_file, "r", encoding="utf-8") as f:
                    self.user_tokens = json.load(f)
                print(f"Loaded tokens for {len(self.user_tokens)} users")
            except Exception as e:
                print(f"Error loading user tokens: {e}")
                self.user_tokens = {}

    def save_user_tokens(self):
        """Save user tokens to file"""
        try:
            with open(self.tokens_file, "w", encoding="utf-8") as f:
                json.dump(self.user_tokens, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving user tokens: {e}")

    def get_user_token(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get token data for a user"""
        return self.user_tokens.get(user_id)

    def save_user_token(self, user_id: str, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save token data for a user"""
        # Add the time when the token was saved
        token_data["saved_at"] = datetime.datetime.now().isoformat()

        # Save the token data
        self.user_tokens[user_id] = token_data

        # Save to disk
        self.save_user_tokens()

        return token_data

    def delete_user_token(self, user_id: str) -> bool:
        """Delete token data for a user"""
        if user_id in self.user_tokens:
            del self.user_tokens[user_id]
            self.save_user_tokens()
            return True
        return False
