# Unified API Service

This is a centralized API service that both the Discord bot and Flutter app use to store and retrieve data. This ensures consistent data synchronization between both applications.

## Overview

The API service provides endpoints for:
- Managing conversations
- Managing user settings
- Authentication via Discord OAuth

## Setup Instructions

### 1. Install Dependencies

```bash
pip install fastapi uvicorn pydantic aiohttp
```

### 2. Configure Environment Variables

Create a `.env` file in the `api_service` directory with the following variables:

```
API_HOST=0.0.0.0
API_PORT=8000
DATA_DIR=data
```

### 3. Start the API Server

```bash
cd api_service
python api_server.py
```

The API server will start on the configured host and port (default: `0.0.0.0:8000`).

## Discord Bot Integration

### 1. Update the Discord Bot

1. Import the API integration in your bot's main file:

```python
from api_integration import init_api_client

# Initialize the API client
api_client = init_api_client("https://your-api-url.com/api")
```

2. Replace the existing AI cog with the updated version:

```python
# In your bot.py file
async def setup(bot):
    await bot.add_cog(AICog(bot))
```

### 2. Configure Discord OAuth

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application or use an existing one
3. Go to the OAuth2 section
4. Add a redirect URL: `https://your-api-url.com/api/auth`
5. Copy the Client ID and Client Secret

## Flutter App Integration

### 1. Update the Flutter App

1. Replace the existing `SyncService` with the new `ApiService`:

```dart
// In your main.dart file
final apiService = ApiService(discordOAuthService);
```

2. Update your providers:

```dart
providers: [
  ChangeNotifierProvider(create: (context) => DiscordOAuthService()),
  ChangeNotifierProxyProvider<DiscordOAuthService, ApiService>(
    create: (context) => ApiService(Provider.of<DiscordOAuthService>(context, listen: false)),
    update: (context, authService, previous) => previous!..update(authService),
  ),
  ChangeNotifierProxyProvider2<OpenRouterService, ApiService, ChatModel>(
    create: (context) => ChatModel(
      Provider.of<OpenRouterService>(context, listen: false),
      Provider.of<ApiService>(context, listen: false),
    ),
    update: (context, openRouterService, apiService, previous) =>
        previous!..update(openRouterService, apiService),
  ),
]
```

### 2. Configure Discord OAuth in Flutter

1. Update the Discord OAuth configuration in your Flutter app:

```dart
// In discord_oauth_service.dart
const String clientId = 'your-client-id';
const String redirectUri = 'openroutergui://auth';
```

## API Endpoints

### Authentication

- `GET /auth?code={code}&state={state}` - Handle OAuth callback

### Conversations

- `GET /conversations` - Get all conversations for the authenticated user
- `GET /conversations/{conversation_id}` - Get a specific conversation
- `POST /conversations` - Create a new conversation
- `PUT /conversations/{conversation_id}` - Update a conversation
- `DELETE /conversations/{conversation_id}` - Delete a conversation

### Settings

- `GET /settings` - Get settings for the authenticated user
- `PUT /settings` - Update settings for the authenticated user

## Security Considerations

- The API uses Discord OAuth for authentication
- All API requests require a valid Discord token
- The API verifies the token with Discord for each request
- Consider adding rate limiting and additional security measures for production use

## Troubleshooting

### API Connection Issues

- Ensure the API server is running and accessible
- Check that the API URL is correctly configured in both the Discord bot and Flutter app
- Verify that the Discord OAuth credentials are correct

### Authentication Issues

- Make sure the Discord OAuth redirect URL is correctly configured
- Check that the client ID and client secret are correct
- Ensure the user has granted the necessary permissions

### Data Synchronization Issues

- Check the API server logs for errors
- Verify that both the Discord bot and Flutter app are using the same API URL
- Ensure the user is authenticated in both applications
