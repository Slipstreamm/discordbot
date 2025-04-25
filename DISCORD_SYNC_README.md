# Discord Sync Integration

This document explains how to set up the Discord OAuth integration between your Flutter app and Discord bot.

## Overview

The integration allows users to:
1. Log in with their Discord account
2. Sync conversations between the Flutter app and Discord bot
3. Import conversations from Discord to the Flutter app
4. Export conversations from the Flutter app to Discord

## Setup Instructions

### 1. Discord Developer Portal Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name (e.g., "OpenRouter GUI")
3. Go to the "OAuth2" section
4. Add a redirect URL: `openroutergui://auth`
5. Copy the "Client ID" - you'll need this for the Flutter app

### 2. Flutter App Setup

1. Open `lib/services/discord_oauth_service.dart`
2. Replace `YOUR_DISCORD_CLIENT_ID` with the Client ID from the Discord Developer Portal:
   ```dart
   static const String clientId = 'YOUR_DISCORD_CLIENT_ID';
   ```

3. Open `lib/services/sync_service.dart`
4. Replace `YOUR_BOT_API_URL` with the production API URL:
   ```dart
   static const String botApiUrl = 'https://slipstreamm.dev/discordapi';
   ```

### 3. SSL Certificates

1. SSL certificates are required for the production API
2. Place your SSL certificates in the following locations:
   ```
   certs/cert.pem  # SSL certificate file
   certs/key.pem   # SSL key file
   ```
3. The API will automatically use SSL if certificates are available
4. For development, the API will fall back to HTTP on port 8000 if certificates are not found

## Bot Commands

The following commands are available for managing synced conversations:

- `!aisync` - View your synced conversations status
- `!syncstatus` - Check the status of the Discord sync API
- `!synchelp` - Get help with setting up the Discord sync integration
- `!syncclear` - Clear your synced conversations
- `!synclist` - List your synced conversations

## Usage

1. In the Flutter app, go to Settings > Discord Integration
2. Click "Login with Discord" to authenticate
3. Use the "Sync Conversations" button to sync conversations
4. Use the "Import from Discord" button to import conversations from Discord

## Troubleshooting

- **Authentication Issues**: Make sure the Client ID is correct and the redirect URL is properly configured
- **Sync Issues**: Check that the bot API URL is accessible and the API is running
- **Import/Export Issues**: Verify that the Discord bot has saved conversations to sync

## Security Considerations

- The integration uses Discord OAuth for authentication, ensuring only authorized users can access their conversations
- All API requests require a valid Discord token
- The API verifies the token with Discord for each request
- Consider adding rate limiting and additional security measures for production use
