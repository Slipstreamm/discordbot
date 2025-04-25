# Discord Bot Sync Features

This document explains the new synchronization features added to the Discord bot to ensure settings are properly synced between the Discord bot and Flutter app.

## Overview

The Discord bot now includes several new commands and features to help diagnose and fix synchronization issues between the Discord bot and Flutter app. These features allow you to:

1. Check the API connection status
2. Verify your Discord token
3. Force sync settings with the API
4. Save a Discord token for testing purposes
5. Get help with all AI commands

## New Commands

### `!aisyncsettings`

This command forces a sync of your settings with the API. It will:
- First try to fetch settings from the API
- If that fails, it will try to push your local settings to the API
- Display the result of the sync operation

Example:
```
!aisyncsettings
```

### `!aiapicheck`

This command checks if the API server is accessible. It will:
- Try to connect to the API server
- Display the status code and response
- Let you know if the connection was successful

Example:
```
!aiapicheck
```

### `!aitokencheck`

This command checks if you have a valid Discord token for API authentication. It will:
- Try to authenticate with the API using your token
- Display whether the token is valid
- Show a preview of your settings if authentication is successful

Example:
```
!aitokencheck
```

### `!aisavetoken` (Owner only)

This command allows the bot owner to save a Discord token for API authentication. This is primarily for testing purposes.

Example:
```
!aisavetoken your_discord_token_here
```

### `!aihelp`

This command displays help for all AI commands, including the new sync commands.

Example:
```
!aihelp
```

## Troubleshooting Sync Issues

If your settings aren't syncing properly between the Discord bot and Flutter app, follow these steps:

1. Use `!aiapicheck` to verify the API is accessible
2. Use `!aitokencheck` to verify your Discord token is valid
3. Use `!aisyncsettings` to force a sync with the API
4. Make sure you're logged in to the Flutter app with the same Discord account

## Technical Details

### Token Storage

For testing purposes, the bot can store Discord tokens in the following ways:
- Environment variables: `DISCORD_TOKEN_{user_id}` or `DISCORD_TEST_TOKEN`
- Token files: `tokens/{user_id}.token`

In a production environment, you would use a more secure method of storing tokens, such as a database with encryption.

### API Integration

The bot communicates with the API server using the following endpoints:
- `/settings` - Get or update user settings
- `/sync` - Sync conversations and settings

All API requests include the Discord token for authentication.

### Settings Synchronization

The bot now fetches settings from the API in the following situations:
- When the bot starts up (for all users)
- When a user uses the `!aiset` command
- When a user uses the `!ai` command
- When a user uses the `!aisyncsettings` command

This ensures that the bot always has the latest settings from the API.
