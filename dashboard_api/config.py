import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# Determine the path to the .env file relative to this config file
# Go up one level from dashboard_api/ to the project root where .env should be
dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'discordbot', '.env')

class Settings(BaseSettings):
    # Discord OAuth Credentials
    DISCORD_CLIENT_ID: str
    DISCORD_CLIENT_SECRET: str
    DISCORD_REDIRECT_URI: str # Should match the one set in main.py and Discord Dev Portal

    # Secret key for session management (signing cookies)
    # Generate a strong random key for production, e.g., using:
    # python -c 'import secrets; print(secrets.token_hex(32))'
    DASHBOARD_SECRET_KEY: str = "a_default_secret_key_for_development_only" # Provide a default for dev

    # API settings (optional, if needed)
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000 # Default port for the dashboard API

    # Database/Redis settings - Required for the API to use settings_manager
    # These should match the ones used by the bot in discordbot/.env
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_SETTINGS_DB: str # The specific DB for settings
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None # Optional

    # Pydantic Settings configuration
    model_config = SettingsConfigDict(
        env_file=dotenv_path,
        env_file_encoding='utf-8',
        extra='ignore' # Ignore extra fields from .env if any
    )

# Use lru_cache to load settings only once
@lru_cache()
def get_settings() -> Settings:
    # Check if the .env file exists before loading
    if not os.path.exists(dotenv_path):
        print(f"Warning: .env file not found at {dotenv_path}. Using defaults or environment variables.")
    return Settings()

# Load settings instance
settings = get_settings()

# --- Constants derived from settings ---
DISCORD_API_BASE_URL = "https://discord.com/api/v10" # Use API v10
DISCORD_AUTH_URL = (
    f"https://discord.com/api/oauth2/authorize?client_id={settings.DISCORD_CLIENT_ID}"
    f"&redirect_uri={settings.DISCORD_REDIRECT_URI}&response_type=code&scope=identify guilds"
)
DISCORD_TOKEN_URL = f"{DISCORD_API_BASE_URL}/oauth2/token"
DISCORD_USER_URL = f"{DISCORD_API_BASE_URL}/users/@me"
DISCORD_USER_GUILDS_URL = f"{DISCORD_API_BASE_URL}/users/@me/guilds"
