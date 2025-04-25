# Multi-Conversation AI Feature

This document explains how to use the multi-conversation AI feature, which allows users to maintain multiple separate conversations with the AI, each with its own settings and history.

## Commands

### Basic Commands

- `!chat <message>` - Send a message to the AI using your active conversation
- `!convs` - Manage your conversations with a UI
- `!chatset` - View and update settings for your active conversation
- `!chatimport` - Import conversations from the sync API

### Slash Commands

- `/chat <message>` - Send a message to the AI using your active conversation

## Managing Conversations

Use the `!convs` command to see a list of your conversations. This will display a UI with the following options:

- **Dropdown Menu** - Select a conversation to switch to, or create a new one
- **Settings Button** - View and modify settings for the active conversation
- **Rename Button** - Change the title of the active conversation
- **Delete Button** - Delete the active conversation

## Conversation Settings

Each conversation has its own settings that can be viewed and modified using the `!chatset` command:

```
!chatset                    - Show current settings
!chatset temperature 0.8    - Set temperature to 0.8
!chatset max_tokens 2000    - Set maximum tokens
!chatset reasoning on       - Enable reasoning
!chatset reasoning_effort medium - Set reasoning effort (low, medium, high)
!chatset web_search on      - Enable web search
!chatset model gpt-4        - Set the model
!chatset system <message>   - Set system message
!chatset title <title>      - Set conversation title
!chatset character <name>   - Set character name
!chatset character_info <info> - Set character information
!chatset character_breakdown on - Enable character breakdown
!chatset custom_instructions <text> - Set custom instructions
```

## Syncing with Flutter App

The multi-conversation feature is compatible with the Discord sync API, allowing users to access their conversations from a Flutter app.

To import conversations from the sync API, use the `!chatimport` command. This will show a confirmation message with the number of conversations that will be imported.

## Examples

### Starting a New Conversation

```
!chat Hello, how are you?
```

### Managing Conversations

```
!convs
```

### Viewing Settings

```
!chatset
```

### Changing Settings

```
!chatset temperature 0.8
!chatset reasoning on
!chatset system You are a helpful assistant that specializes in programming.
!chatset character Hatsune Miku
!chatset character_info Hatsune Miku is a virtual singer and the most famous VOCALOID character.
!chatset character_breakdown on
```

### Importing Conversations

```
!chatimport
```

## Technical Details

- Conversations are stored in `ai_multi_conversations.json`
- Active conversation IDs are stored in `ai_multi_user_settings.json`
- Conversations are synced with the Discord sync API if available
- Each conversation has its own history, settings, system message, and character settings

## Tips for Best Results

1. **Use descriptive titles** for your conversations to easily identify them
2. **Customize the system message** for each conversation to get more relevant responses
3. **Use character settings** for roleplay conversations
4. **Add custom instructions** for specific requirements or constraints
5. **Adjust temperature** based on the task - lower for factual responses, higher for creative ones
6. **Enable reasoning** for complex questions that require step-by-step thinking
7. **Use web search** for conversations that need up-to-date information
