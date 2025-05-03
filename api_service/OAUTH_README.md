# OAuth2 Implementation in the API Service

This document explains how OAuth2 authentication is implemented in the API service.

## Overview

The API service now includes a proper OAuth2 implementation that allows users to:

1. Authenticate with their Discord account
2. Authorize the API service to access Discord resources on their behalf
3. Use the resulting token for API authentication

This implementation uses the OAuth2 Authorization Code flow with PKCE (Proof Key for Code Exchange) for enhanced security, which is the recommended approach for public clients like mobile apps and Discord bots.

## How It Works

### 1. Authorization Flow

1. The user initiates the OAuth flow by clicking an authorization link (typically from the Discord bot or Flutter app)
2. The user is redirected to Discord's authorization page
3. After authorizing the application, Discord redirects the user to the API service's `/auth` endpoint with an authorization code
4. The API service exchanges the code for an access token
5. The token is stored in the database and associated with the user's Discord ID
6. The user is shown a success page

### 2. Token Usage

1. The user includes the access token in the `Authorization` header of API requests
2. The API service verifies the token with Discord
3. If the token is valid, the API service identifies the user and processes the request
4. If the token is invalid, the API service returns a 401 Unauthorized error

## API Endpoints

### Authentication

- `GET /api/auth?code={code}&state={state}` - Handle OAuth callback from Discord
- `GET /api/token` - Get the access token for the authenticated user
- `DELETE /api/token` - Delete the access token for the authenticated user

## Configuration

The OAuth implementation requires the following environment variables:

```env
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_REDIRECT_URI=https://your-domain.com/api/auth
```

Note that we don't use a client secret because this is a public client implementation. Public clients (like mobile apps, single-page applications, or Discord bots) should use PKCE instead of a client secret for security.

## Security Considerations

- The API service stores tokens securely in the database
- Tokens are never exposed in logs or error messages
- The API service verifies tokens with Discord for each request
- The API service uses HTTPS to protect tokens in transit

## Integration with Discord Bot

The Discord bot can use the API service's OAuth implementation by:

1. Setting `API_OAUTH_ENABLED=true` in the bot's environment variables
2. Setting `API_URL` to the URL of the API service
3. Using the `!auth` command to initiate the OAuth flow
4. Using the resulting token for API requests

## Integration with Flutter App

The Flutter app can use the API service's OAuth implementation by:

1. Updating the OAuth configuration to use the API service's redirect URI
2. Using the resulting token for API requests

## Troubleshooting

### Common Issues

1. **"Invalid OAuth2 redirect_uri" error**
   - Make sure the redirect URI in your Discord application settings matches the one in your environment variables
   - The redirect URI should be `https://your-domain.com/api/auth`

2. **"Invalid client_id" error**
   - Make sure the client ID in your environment variables matches the one in your Discord application settings

3. **"Invalid request" error**
   - Make sure you're including the code_verifier parameter when exchanging the authorization code
   - The code_verifier must match the one used to generate the code_challenge

4. **"Invalid code" error**
   - The authorization code has expired or has already been used
   - Authorization codes are one-time use and expire after a short time

### Logs

The API service logs detailed information about the OAuth process. Check the API service's logs for error messages and debugging information.
