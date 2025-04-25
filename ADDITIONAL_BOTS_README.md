# Additional AI Bots - Neru and Miku

This system allows you to run two additional Discord bots (Neru and Miku) that only have AI commands, each with their own system prompt and configuration. These bots are designed for roleplay interactions with specific character personas.

## Setup Instructions

1. **Bot Tokens**:
   - The tokens are already configured in `data/multi_bot_config.json`
   - If you need to change them, you can edit the configuration file or use the `!setbottoken` command

2. **API Key**:
   - The OpenRouter API key is already configured in the configuration file
   - If you need to change it, you can edit the configuration file or use the `!setapikey` command

3. **System Prompts**:
   - Each bot has a specific roleplay character system prompt:
     - Neru: Akita Neru roleplay character
     - Miku: Hatsune Miku roleplay character

## Running the Bots

### Option 1: Run from the Main Bot

The main bot has commands to control the additional bots:

- `!startbot <bot_id>` - Start a specific bot (e.g., `!startbot bot1`)
- `!stopbot <bot_id>` - Stop a specific bot
- `!startallbots` - Start all configured bots
- `!stopallbots` - Stop all running bots
- `!listbots` - List all configured bots and their status

### Option 2: Run Independently

You can run the additional bots independently of the main bot:

```bash
python run_additional_bots.py
```

This will start all configured bots in separate threads.

## Configuration Commands

The main bot provides commands to modify the configuration:

- `!setbottoken <bot_id> <token>` - Set the token for a specific bot
- `!setbotprompt <bot_id> <system_prompt>` - Set the system prompt for a specific bot
- `!setbotprefix <bot_id> <prefix>` - Set the command prefix for a specific bot
- `!setbotstatus <bot_id> <status_type> <status_text>` - Set the status for a specific bot
- `!setallbotstatus <status_type> <status_text>` - Set the status for all bots
- `!setapikey <api_key>` - Set the API key for all bots
- `!setapiurl <api_url>` - Set the API URL for all bots
- `!addbot <bot_id> [prefix]` - Add a new bot configuration
- `!removebot <bot_id>` - Remove a bot configuration

Status types for the status commands:

- `playing` - "Playing {status_text}"
- `listening` - "Listening to {status_text}"
- `watching` - "Watching {status_text}"
- `streaming` - "Streaming {status_text}"
- `competing` - "Competing in {status_text}"

## Bot Commands

Each additional bot supports the following commands:

- Neru: `$ai <prompt>` - Get a response from Akita Neru
- Miku: `.ai <prompt>` - Get a response from Hatsune Miku

Additional commands for both bots:

- `aiclear` - Clear your conversation history
- `aisettings` - Show your current AI settings
- `aiset <setting> <value>` - Change an AI setting
- `aireset` - Reset your AI settings to defaults
- `ailast` - Retrieve your last AI response
- `aihelp` - Get help with AI command issues

Available settings for the `aiset` command:

- `model` - The AI model to use (must contain ":free")
- `system_prompt` - The system prompt to use
- `max_tokens` - Maximum tokens in response (100-2000)
- `temperature` - Temperature for response generation (0.0-2.0)
- `timeout` - Timeout for API requests in seconds (10-120)

Note that each bot uses its own prefix (`$` for Neru and `.` for Miku).

## Customization

You can customize each bot by editing the `data/multi_bot_config.json` file:

```json
{
    "bots": [
        {
            "id": "neru",
            "token": "YOUR_NERU_BOT_TOKEN_HERE",
            "prefix": "$",
            "system_prompt": "You are a creative and intelligent AI assistant engaged in an iterative storytelling experience using a roleplay chat format. Chat exclusively as Akita Neru...",
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 60,
            "status_type": "playing",
            "status_text": "with my phone"
        },
        {
            "id": "miku",
            "token": "YOUR_MIKU_BOT_TOKEN_HERE",
            "prefix": ".",
            "system_prompt": "You are a creative and intelligent AI assistant engaged in an iterative storytelling experience using a roleplay chat format. Chat exclusively as Hatsune Miku...",
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 60,
            "status_type": "listening",
            "status_text": "music"
        }
    ],
    "api_key": "YOUR_OPENROUTER_API_KEY_HERE",
    "api_url": "https://openrouter.ai/api/v1/chat/completions",
    "compatibility_mode": "openai"
}
```

## Troubleshooting

- If a bot fails to start, check that its token is correctly set in the configuration
- If AI responses fail, check that the API key is correctly set
- Each bot stores its conversation history and user settings in separate files to avoid conflicts
