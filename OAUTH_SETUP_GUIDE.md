# Discord OAuth2 Setup Guide

This guide explains how to set up Discord OAuth2 authentication for the Discord bot, allowing users to authenticate with their Discord accounts and authorize the bot to access the API on their behalf.

## Overview

The Discord bot now includes a proper OAuth2 implementation that allows users to:

1. Authenticate with their Discord account
2. Authorize the bot to access the API on their behalf
3. Securely store and manage tokens
4. Automatically refresh tokens when they expire

This implementation uses the OAuth2 Authorization Code flow with PKCE (Proof Key for Code Exchange) for enhanced security.

## Setup Instructions

### 1. Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name (e.g., "Your Bot Name")
3. Go to the "OAuth2" section
4. Add a redirect URL: `http://your-server-address:8080/oauth/callback`
   - For local testing, you can use `http://localhost:8080/oauth/callback`
   - For production, use your server's domain name or IP address
5. Copy the "Client ID" and "Client Secret" - you'll need these for the bot configuration

### 2. Configure Environment Variables

Create a `.env` file in the bot directory based on the provided `.env.example`:

```bash
cp .env.example .env
```

Edit the `.env` file and update the OAuth configuration:

```
# OAuth Configuration
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
OAUTH_HOST=0.0.0.0
OAUTH_PORT=8080
DISCORD_REDIRECT_URI=http://your-server-address:8080/oauth/callback
```

Replace `your_discord_client_id` and `your_discord_client_secret` with the values from the Discord Developer Portal.

### 3. Configure Port Forwarding (for Production)

If you're running the bot on a server, you'll need to configure port forwarding to allow external access to the OAuth callback server:

1. Forward port 8080 (or whatever port you specified in `OAUTH_PORT`) to your server
2. Make sure your firewall allows incoming connections on this port
3. If you're using a domain name, make sure it points to your server's IP address

### 4. Start the Bot

Start the bot as usual:

```bash
python main.py
```

The bot will automatically start the OAuth callback server on the specified host and port.

## Using OAuth Commands

The bot now includes several commands for managing OAuth authentication:

### `!auth`

This command starts the OAuth flow for a user. It will:

1. Generate a unique state parameter and code verifier for security
2. Create an authorization URL with the Discord OAuth2 endpoint
3. Send the URL to the user via DM (or in the channel if DMs are disabled)
4. Wait for the user to complete the authorization flow
5. Store the resulting token securely

Example:
```
!auth
```

### `!deauth`

This command revokes the bot's access to the user's Discord account by deleting their token.

Example:
```
!deauth
```

### `!authstatus`

This command checks the user's authentication status and displays information about their token.

Example:
```
!authstatus
```

### `!authhelp`

This command displays help information about the OAuth commands.

Example:
```
!authhelp
```

## Integration with AI Commands

The OAuth system is integrated with the existing AI commands:

- `!aiset` - Now uses the OAuth token for API authentication
- `!ai` - Now uses the OAuth token for API authentication
- `!aisyncsettings` - Now uses the OAuth token for API authentication
- `!aiapicheck` - Now uses the OAuth token for API authentication
- `!aitokencheck` - Now uses the OAuth token for API authentication

Users need to authenticate with `!auth` before they can use these commands with API integration.

## Technical Details

### Token Storage

Tokens are stored securely in JSON files in the `tokens` directory. Each file is named with the user's Discord ID and contains:

- Access token
- Refresh token (if available)
- Token expiration time
- Token type
- Scope

### Token Refresh

The system automatically refreshes tokens when they expire. If a token cannot be refreshed, the user will need to authenticate again using the `!auth` command.

### Security Considerations

- The implementation uses PKCE to prevent authorization code interception attacks
- State parameters are used to prevent CSRF attacks
- Tokens are stored securely and not exposed in logs or error messages
- The OAuth callback server only accepts connections from authorized sources

## Troubleshooting

### Common Issues

1. **"No Discord token available" error**
   - The user needs to authenticate with `!auth` first
   - Check if the token file exists in the `tokens` directory

2. **"Failed to exchange code" error**
   - Check if the redirect URI in the Discord Developer Portal matches the one in your `.env` file
   - Check if the client ID and client secret are correct

3. **"Invalid state parameter" error**
   - The state parameter in the callback doesn't match the one sent in the authorization request
   - This could indicate a CSRF attack or a timeout (the state parameter expires after 10 minutes)

4. **OAuth callback server not starting**
   - Check if the port is already in use
   - Check if the host is correctly configured
   - Check if the bot has permission to bind to the specified port

### Logs

The OAuth system logs detailed information about the authentication process. Check the bot's console output for error messages and debugging information.
