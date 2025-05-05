import discord
from discord.ext import commands
import asyncio
import os
import json
import aiohttp
import random
import time
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional, Tuple, Set, Union

# Third-party imports needed by the Cog itself or its direct methods
from dotenv import load_dotenv
from tavily import TavilyClient # Needed for tavily_client init

# --- Relative Imports from Wheatley Package ---
from .config import (
    PROJECT_ID, LOCATION, TAVILY_API_KEY, DEFAULT_MODEL, FALLBACK_MODEL, # Use GCP config
    DB_PATH, CHROMA_PATH, SEMANTIC_MODEL_NAME, MAX_USER_FACTS, MAX_GENERAL_FACTS,
    # Removed Mood/Personality/Interest/Learning/Goal configs
    CHANNEL_TOPIC_CACHE_TTL, CONTEXT_WINDOW_SIZE,
    API_TIMEOUT, SUMMARY_API_TIMEOUT, API_RETRY_ATTEMPTS, API_RETRY_DELAY,
    PROACTIVE_LULL_THRESHOLD, PROACTIVE_BOT_SILENCE_THRESHOLD, PROACTIVE_LULL_CHANCE,
    PROACTIVE_TOPIC_RELEVANCE_THRESHOLD, PROACTIVE_TOPIC_CHANCE,
    # Removed Relationship/Sentiment/Interest proactive configs
    TOPIC_UPDATE_INTERVAL, SENTIMENT_UPDATE_INTERVAL,
    RESPONSE_SCHEMA, TOOLS # Import necessary configs
)
# Import functions/classes from other modules
from .memory import MemoryManager # Import from local memory.py
from .background import background_processing_task # Keep background task for potential future use (e.g., cache cleanup)
from .commands import setup_commands # Import the setup helper
from .listeners import on_ready_listener, on_message_listener, on_reaction_add_listener, on_reaction_remove_listener # Import listener functions
from . import config as WheatleyConfig # Import config module for get_wheatley_stats

# Load environment variables (might be loaded globally in main bot script too)
load_dotenv()

class WheatleyCog(commands.Cog, name="Wheatley"): # Renamed class and Cog name
    """A special cog for the Wheatley bot that uses Google Vertex AI API""" # Updated docstring

    def __init__(self, bot):
        self.bot = bot
        # GCP Project/Location are used by vertexai.init() in api.py
        self.tavily_api_key = TAVILY_API_KEY # Use imported config
        self.session: Optional[aiohttp.ClientSession] = None # Keep for other potential HTTP requests (e.g., Piston)
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key) if self.tavily_api_key else None
        self.default_model = DEFAULT_MODEL # Use imported config
        self.fallback_model = FALLBACK_MODEL # Use imported config
        # Removed MOOD_OPTIONS
        self.current_channel: Optional[Union[discord.TextChannel, discord.Thread, discord.DMChannel]] = None # Type hint current channel

        # Instantiate MemoryManager
        self.memory_manager = MemoryManager(
            db_path=DB_PATH,
            max_user_facts=MAX_USER_FACTS,
            max_general_facts=MAX_GENERAL_FACTS,
            chroma_path=CHROMA_PATH,
            semantic_model_name=SEMANTIC_MODEL_NAME
        )

        # --- State Variables (Simplified for Wheatley) ---
        # Removed mood, personality evolution, interest tracking, learning state
        self.needs_json_reminder = False # Flag to remind AI about JSON format

        # Topic tracking (Kept for context)
        self.active_topics = defaultdict(lambda: {
            "topics": [], "last_update": time.time(), "topic_history": [],
            "user_topic_interests": defaultdict(list) # Kept for potential future analysis, not proactive triggers
        })

        # Conversation tracking / Caches
        self.conversation_history = defaultdict(lambda: deque(maxlen=100))
        self.thread_history = defaultdict(lambda: deque(maxlen=50))
        self.user_conversation_mapping = defaultdict(set)
        self.channel_activity = defaultdict(lambda: 0.0) # Use float for timestamp
        self.conversation_topics = defaultdict(str) # Simplified topic tracking
        self.user_relationships = defaultdict(dict) # Kept for potential context/analysis
        self.conversation_summaries: Dict[int, Dict[str, Any]] = {} # Store dict with summary and timestamp
        self.channel_topics_cache: Dict[int, Dict[str, Any]] = {} # Store dict with topic and timestamp

        self.message_cache = {
            'by_channel': defaultdict(lambda: deque(maxlen=CONTEXT_WINDOW_SIZE)), # Use config
            'by_user': defaultdict(lambda: deque(maxlen=50)),
            'by_thread': defaultdict(lambda: deque(maxlen=50)),
            'global_recent': deque(maxlen=200),
            'mentioned': deque(maxlen=50),
            'replied_to': defaultdict(lambda: deque(maxlen=20))
        }

        self.active_conversations = {} # Kept for basic tracking
        self.bot_last_spoke = defaultdict(float)
        self.message_reply_map = {}

        # Enhanced sentiment tracking (Kept for context/analysis)
        self.conversation_sentiment = defaultdict(lambda: {
            "overall": "neutral", "intensity": 0.5, "recent_trend": "stable",
            "user_sentiments": {}, "last_update": time.time()
        })
        # Removed self.sentiment_update_interval as it was only used in analysis

        # Reaction Tracking (Renamed)
        self.wheatley_message_reactions = defaultdict(lambda: {"positive": 0, "negative": 0, "topic": None, "timestamp": 0.0}) # Renamed

        # Background task handle (Kept for potential future tasks like cache cleanup)
        self.background_task: Optional[asyncio.Task] = None
        self.last_stats_push = time.time() # Timestamp for last stats push
        # Removed evolution, reflection, goal timestamps

        # --- Stats Tracking ---
        self.api_stats = defaultdict(lambda: {"success": 0, "failure": 0, "retries": 0, "total_time": 0.0, "count": 0}) # Keyed by model name
        self.tool_stats = defaultdict(lambda: {"success": 0, "failure": 0, "total_time": 0.0, "count": 0}) # Keyed by tool name

        # --- Setup Commands and Listeners ---
        # Add commands defined in commands.py
        self.command_functions = setup_commands(self)

        # Store command names for reference - safely handle Command objects
        self.registered_commands = []
        for func in self.command_functions:
            # For app commands, use the name attribute directly
            if hasattr(func, "name"):
                self.registered_commands.append(func.name)
            # For regular functions, use __name__
            elif hasattr(func, "__name__"):
                self.registered_commands.append(func.__name__)
            else:
                self.registered_commands.append(str(func))

        print(f"WheatleyCog initialized with commands: {self.registered_commands}") # Updated print

    async def cog_load(self):
        """Create aiohttp session, initialize DB, start background task"""
        self.session = aiohttp.ClientSession()
        print("WheatleyCog: aiohttp session created") # Updated print

        # Initialize DB via MemoryManager
        await self.memory_manager.initialize_sqlite_database()
        # Removed loading of baseline personality and interests

        # Vertex AI initialization happens in api.py using PROJECT_ID and LOCATION from config
        print(f"WheatleyCog: Using default model: {self.default_model}") # Updated print
        if not self.tavily_api_key:
             print("WARNING: Tavily API key not configured (TAVILY_API_KEY). Web search disabled.")

        # Add listeners to the bot instance
        # IMPORTANT: Don't override on_member_join or on_member_remove events

        # Check if the bot already has event listeners for member join/leave
        has_member_join = 'on_member_join' in self.bot.extra_events
        has_member_remove = 'on_member_remove' in self.bot.extra_events
        print(f"WheatleyCog: Bot already has event listeners - on_member_join: {has_member_join}, on_member_remove: {has_member_remove}")

        @self.bot.event
        async def on_ready():
            await on_ready_listener(self)

        @self.bot.event
        async def on_message(message):
            # Ensure commands are processed if using command prefix
            if message.content.startswith(self.bot.command_prefix):
                 await self.bot.process_commands(message)
            # Always run the message listener for potential AI responses/tracking
            await on_message_listener(self, message)

        @self.bot.event
        async def on_reaction_add(reaction, user):
            await on_reaction_add_listener(self, reaction, user)

        @self.bot.event
        async def on_reaction_remove(reaction, user):
            await on_reaction_remove_listener(self, reaction, user)

        print("WheatleyCog: Listeners added.") # Updated print

        # Commands will be synced in on_ready
        print("WheatleyCog: Commands will be synced when the bot is ready.") # Updated print

        # Start background task (kept for potential future use)
        if self.background_task is None or self.background_task.done():
            self.background_task = asyncio.create_task(background_processing_task(self))
            print("WheatleyCog: Started background processing task.") # Updated print
        else:
             print("WheatleyCog: Background processing task already running.") # Updated print

    async def cog_unload(self):
        """Close session and cancel background task"""
        if self.session and not self.session.closed:
            await self.session.close()
            print("WheatleyCog: aiohttp session closed") # Updated print
        if self.background_task and not self.background_task.done():
            self.background_task.cancel()
            print("WheatleyCog: Cancelled background processing task.") # Updated print
        print("WheatleyCog: Listeners will be removed when bot is closed.") # Updated print

        print("WheatleyCog unloaded.") # Updated print

    # --- Helper methods that might remain in the cog ---
    # _update_relationship kept for potential context/analysis use
    def _update_relationship(self, user_id_1: str, user_id_2: str, change: float):
        """Updates the relationship score between two users."""
        if user_id_1 > user_id_2: user_id_1, user_id_2 = user_id_2, user_id_1
        if user_id_1 not in self.user_relationships: self.user_relationships[user_id_1] = {}

        current_score = self.user_relationships[user_id_1].get(user_id_2, 0.0)
        new_score = max(0.0, min(current_score + change, 100.0)) # Clamp 0-100
        self.user_relationships[user_id_1][user_id_2] = new_score
        # print(f"Updated relationship {user_id_1}-{user_id_2}: {current_score:.1f} -> {new_score:.1f} ({change:+.1f})") # Debug log

    async def get_wheatley_stats(self) -> Dict[str, Any]: # Renamed method
        """Collects various internal stats for Wheatley.""" # Updated docstring
        stats = {"config": {}, "runtime": {}, "memory": {}, "api_stats": {}, "tool_stats": {}}

        # --- Config (Simplified) ---
        stats["config"]["default_model"] = WheatleyConfig.DEFAULT_MODEL
        stats["config"]["fallback_model"] = WheatleyConfig.FALLBACK_MODEL
        stats["config"]["safety_check_model"] = WheatleyConfig.SAFETY_CHECK_MODEL
        stats["config"]["db_path"] = WheatleyConfig.DB_PATH
        stats["config"]["chroma_path"] = WheatleyConfig.CHROMA_PATH
        stats["config"]["semantic_model_name"] = WheatleyConfig.SEMANTIC_MODEL_NAME
        stats["config"]["max_user_facts"] = WheatleyConfig.MAX_USER_FACTS
        stats["config"]["max_general_facts"] = WheatleyConfig.MAX_GENERAL_FACTS
        stats["config"]["context_window_size"] = WheatleyConfig.CONTEXT_WINDOW_SIZE
        stats["config"]["api_timeout"] = WheatleyConfig.API_TIMEOUT
        stats["config"]["summary_api_timeout"] = WheatleyConfig.SUMMARY_API_TIMEOUT
        stats["config"]["proactive_lull_threshold"] = WheatleyConfig.PROACTIVE_LULL_THRESHOLD
        stats["config"]["proactive_bot_silence_threshold"] = WheatleyConfig.PROACTIVE_BOT_SILENCE_THRESHOLD
        stats["config"]["topic_update_interval"] = WheatleyConfig.TOPIC_UPDATE_INTERVAL
        stats["config"]["sentiment_update_interval"] = WheatleyConfig.SENTIMENT_UPDATE_INTERVAL
        stats["config"]["docker_command_timeout"] = WheatleyConfig.DOCKER_COMMAND_TIMEOUT
        stats["config"]["project_id_set"] = bool(WheatleyConfig.PROJECT_ID != "your-gcp-project-id")
        stats["config"]["location_set"] = bool(WheatleyConfig.LOCATION != "us-central1")
        stats["config"]["tavily_api_key_set"] = bool(WheatleyConfig.TAVILY_API_KEY)
        stats["config"]["piston_api_url_set"] = bool(WheatleyConfig.PISTON_API_URL)

        # --- Runtime (Simplified) ---
        # Removed mood, evolution
        stats["runtime"]["needs_json_reminder"] = self.needs_json_reminder
        stats["runtime"]["background_task_running"] = bool(self.background_task and not self.background_task.done())
        stats["runtime"]["active_topics_channels"] = len(self.active_topics)
        stats["runtime"]["conversation_history_channels"] = len(self.conversation_history)
        stats["runtime"]["thread_history_threads"] = len(self.thread_history)
        stats["runtime"]["user_conversation_mappings"] = len(self.user_conversation_mapping)
        stats["runtime"]["channel_activity_tracked"] = len(self.channel_activity)
        stats["runtime"]["conversation_topics_tracked"] = len(self.conversation_topics) # Simplified topic tracking
        stats["runtime"]["user_relationships_pairs"] = sum(len(v) for v in self.user_relationships.values())
        stats["runtime"]["conversation_summaries_cached"] = len(self.conversation_summaries)
        stats["runtime"]["channel_topics_cached"] = len(self.channel_topics_cache)
        stats["runtime"]["message_cache_global_count"] = len(self.message_cache['global_recent'])
        stats["runtime"]["message_cache_mentioned_count"] = len(self.message_cache['mentioned'])
        stats["runtime"]["active_conversations_count"] = len(self.active_conversations)
        stats["runtime"]["bot_last_spoke_channels"] = len(self.bot_last_spoke)
        stats["runtime"]["message_reply_map_size"] = len(self.message_reply_map)
        stats["runtime"]["conversation_sentiment_channels"] = len(self.conversation_sentiment)
        # Removed Gurt participation topics
        stats["runtime"]["wheatley_message_reactions_tracked"] = len(self.wheatley_message_reactions) # Renamed

        # --- Memory (Simplified) ---
        try:
            # Removed Personality, Interests
            user_fact_count = await self.memory_manager._db_fetchone("SELECT COUNT(*) FROM user_facts")
            general_fact_count = await self.memory_manager._db_fetchone("SELECT COUNT(*) FROM general_facts")
            stats["memory"]["user_facts_count"] = user_fact_count[0] if user_fact_count else 0
            stats["memory"]["general_facts_count"] = general_fact_count[0] if general_fact_count else 0

            # ChromaDB Stats
            stats["memory"]["chromadb_message_collection_count"] = await asyncio.to_thread(self.memory_manager.semantic_collection.count) if self.memory_manager.semantic_collection else "N/A"
            stats["memory"]["chromadb_fact_collection_count"] = await asyncio.to_thread(self.memory_manager.fact_collection.count) if self.memory_manager.fact_collection else "N/A"

        except Exception as e:
            stats["memory"]["error"] = f"Failed to retrieve memory stats: {e}"

        # --- API & Tool Stats ---
        stats["api_stats"] = dict(self.api_stats)
        stats["tool_stats"] = dict(self.tool_stats)

        # Calculate average times
        for model, data in stats["api_stats"].items():
            if data["count"] > 0: data["average_time_ms"] = round((data["total_time"] / data["count"]) * 1000, 2)
            else: data["average_time_ms"] = 0
        for tool, data in stats["tool_stats"].items():
            if data["count"] > 0: data["average_time_ms"] = round((data["total_time"] / data["count"]) * 1000, 2)
            else: data["average_time_ms"] = 0

        return stats

    async def sync_commands(self):
        """Manually sync commands with Discord."""
        try:
            print("WheatleyCog: Manually syncing commands with Discord...") # Updated print
            synced = await self.bot.tree.sync()
            print(f"WheatleyCog: Synced {len(synced)} command(s)") # Updated print

            # List the synced commands
            wheatley_commands = [cmd.name for cmd in self.bot.tree.get_commands() if cmd.name.startswith("wheatley")] # Updated prefix
            print(f"WheatleyCog: Available Wheatley commands: {', '.join(wheatley_commands)}") # Updated print

            return synced, wheatley_commands
        except Exception as e:
            print(f"WheatleyCog: Failed to sync commands: {e}") # Updated print
            import traceback
            traceback.print_exc()
            return [], []

# Setup function for loading the cog
async def setup(bot):
    """Add the WheatleyCog to the bot.""" # Updated docstring
    await bot.add_cog(WheatleyCog(bot)) # Use renamed class
    print("WheatleyCog setup complete.") # Updated print
