# Discord Bot Project

A versatile, modular Discord bot framework with multiple bot personalities and extensive features. This project includes a main bot with a cog-based architecture, specialized AI-powered bots (Gurt, Wheatley), and a unified API service.

## 🤖 Features

### Core Bot Features
- **Modular Cog System**: Easily add, remove, or disable functionalities through cogs
- **Dynamic Command Prefixes**: Customize command prefixes per server
- **Comprehensive Error Handling**: Robust error management for commands
- **Settings Management**: Per-guild settings configuration
- **Help System**: Interactive help command with categories

### AI-Powered Bots
- **Gurt Bot**: AI assistant with memory, web search capabilities, and proactive engagement
- **Wheatley Bot**: Specialized AI personality with unique features
- **Multi-Bot System**: Run multiple AI personalities (Neru, Miku) with different configurations

### Additional Features
- **Moderation Tools**: Ban, kick, mute, warn commands
- **Leveling System**: Track user activity and assign levels
- **Role Management**: Create and assign roles
- **Audio Player**: Play music and audio in voice channels
- **Games**: Fun mini-games for server engagement
- **Unified API Service**: Central API for data storage and retrieval

## 📋 Prerequisites

- Python 3.10+
- Discord Bot Token(s)
- Dependencies (install via `pip install -r requirements.txt`)
- PostgreSQL database (optional, for advanced features)
- Redis (optional, for caching)

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd discordbot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   
   Create a `.env` file in the root directory with the following variables:
   ```
   # Required
   DISCORD_TOKEN=your_main_discord_bot_token
   OWNER_USER_ID=your_discord_user_id
   
   # For specific bots (optional)
   DISCORD_TOKEN_GURT=your_gurt_bot_token
   DISCORD_TOKEN_WHEATLEY=your_wheatley_bot_token
   DISCORD_TOKEN_NERU=your_neru_bot_token
   DISCORD_TOKEN_MIKU=your_miku_bot_token
   
   # For AI features (if using)
   AI_API_KEY=your_openrouter_api_key
   GCP_PROJECT_ID=your_gcp_project_id
   GCP_LOCATION=us-central1
   
   # For web search (optional)
   TAVILY_API_KEY=your_tavily_api_key
   
   # For database (if using)
   POSTGRES_USER=your_postgres_user
   POSTGRES_PASSWORD=your_postgres_password
   POSTGRES_HOST=localhost
   POSTGRES_SETTINGS_DB=discord_bot_settings
   
   # For Redis (if using)
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_PASSWORD=your_redis_password
   ```

4. **Create necessary directories**
   ```bash
   mkdir -p data/chroma_db
   ```

## 🎮 Usage

### Running the Main Bot

```bash
python main.py
```

### Running Specific Bots

**Gurt Bot**
```bash
python run_gurt_bot.py
```

**Wheatley Bot**
```bash
python run_wheatley_bot.py
```

**Multiple Bots**
```bash
python run_additional_bots.py
```

### API Service

```bash
python api_service/api_server.py
```

## 📚 Bot Commands

### Main Bot
- Default prefix: `!` (customizable per server)
- Use `!help` to see available commands

### Gurt Bot
- Default prefix: `%`
- Use `%ai <prompt>` to interact with the AI
- Use `%aihelp` for AI command help
- Use `%gurtmood` to check or set Gurt's mood

### Wheatley Bot
- Default prefix: `%`
- Use `%ai <prompt>` to interact with Wheatley
- Use `/wheatleymemory` to interact with Wheatley's memory

### Multi-Bot Commands
- Use `/multibot start <bot_id>` to start a specific bot
- Use `/multibot stop <bot_id>` to stop a specific bot
- Use `/multibot startall` to start all configured bots

## 🧩 Project Structure

- **`main.py`**: Main bot entry point
- **`gurt_bot.py`/`wheatley_bot.py`**: Specialized bot entry points
- **`multi_bot.py`**: Multi-bot system for running multiple AI personalities
- **`cogs/`**: Directory containing different modules (cogs)
- **`gurt/`**: Gurt bot-specific modules
- **`wheatley/`**: Wheatley bot-specific modules
- **`api_service/`**: API service for data persistence
- **`settings_manager.py`**: Handles guild-specific settings
- **`error_handler.py`**: Centralized error handling

## 🔧 Configuration

### Bot Configuration
- Edit `config.json` to adjust bot settings
- Use environment variables for sensitive information

### Multi-Bot Configuration
- Edit `data/multi_bot_config.json` to configure multiple bot personalities

## 🤝 Contributing

Contributions are welcome! Please follow standard coding practices and ensure your changes are well-documented.

## 📄 License
There is no license.
[UNLICENSE](https://unlicense.org/)