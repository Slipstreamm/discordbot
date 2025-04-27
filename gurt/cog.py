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
# Interpreter and docker might only be needed by tools.py now

# --- Relative Imports from Gurt Package ---
from .config import (
    API_KEY, TAVILY_API_KEY, OPENROUTER_API_URL, DEFAULT_MODEL, FALLBACK_MODEL,
    DB_PATH, CHROMA_PATH, SEMANTIC_MODEL_NAME, MAX_USER_FACTS, MAX_GENERAL_FACTS,
    MOOD_OPTIONS, BASELINE_PERSONALITY, BASELINE_INTERESTS, MOOD_CHANGE_INTERVAL_MIN,
    MOOD_CHANGE_INTERVAL_MAX, CHANNEL_TOPIC_CACHE_TTL, CONTEXT_WINDOW_SIZE,
    API_TIMEOUT, SUMMARY_API_TIMEOUT, API_RETRY_ATTEMPTS, API_RETRY_DELAY,
    PROACTIVE_LULL_THRESHOLD, PROACTIVE_BOT_SILENCE_THRESHOLD, PROACTIVE_LULL_CHANCE,
    PROACTIVE_TOPIC_RELEVANCE_THRESHOLD, PROACTIVE_TOPIC_CHANCE,
    PROACTIVE_RELATIONSHIP_SCORE_THRESHOLD, PROACTIVE_RELATIONSHIP_CHANCE,
    INTEREST_UPDATE_INTERVAL, INTEREST_DECAY_INTERVAL_HOURS,
    LEARNING_UPDATE_INTERVAL, TOPIC_UPDATE_INTERVAL, SENTIMENT_UPDATE_INTERVAL,
    EVOLUTION_UPDATE_INTERVAL, RESPONSE_SCHEMA, TOOLS # Import necessary configs
)
# Import functions/classes from other modules
from .memory import MemoryManager # Import from local memory.py
from .background import background_processing_task
from .commands import setup_commands # Import the setup helper
from .listeners import on_ready_listener, on_message_listener, on_reaction_add_listener, on_reaction_remove_listener # Import listener functions
# Tool mapping is used internally by api.py/process_requested_tools, no need to import here directly unless cog methods call tools directly (they shouldn't)
# Analysis, context, prompt, api, utils functions are called by listeners/commands/background task, not directly by cog methods here usually.

# Load environment variables (might be loaded globally in main bot script too)
load_dotenv()

class GurtCog(commands.Cog, name="Gurt"): # Added explicit Cog name
    """A special cog for the Gurt bot that uses OpenRouter API"""

    def __init__(self, bot):
        self.bot = bot
        self.api_key = API_KEY # Use imported config
        self.tavily_api_key = TAVILY_API_KEY # Use imported config
        self.api_url = OPENROUTER_API_URL # Use imported config
        self.session: Optional[aiohttp.ClientSession] = None # Initialize session as None
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key) if self.tavily_api_key else None
        self.default_model = DEFAULT_MODEL # Use imported config
        self.fallback_model = FALLBACK_MODEL # Use imported config
        self.current_channel: Optional[Union[discord.TextChannel, discord.Thread, discord.DMChannel]] = None # Type hint current channel

        # Instantiate MemoryManager
        self.memory_manager = MemoryManager(
            db_path=DB_PATH,
            max_user_facts=MAX_USER_FACTS,
            max_general_facts=MAX_GENERAL_FACTS,
            chroma_path=CHROMA_PATH,
            semantic_model_name=SEMANTIC_MODEL_NAME
        )

        # --- State Variables ---
        # Keep state directly within the cog instance for now
        self.current_mood = random.choice(MOOD_OPTIONS)
        self.last_mood_change = time.time()
        self.needs_json_reminder = False # Flag to remind AI about JSON format

        # Learning variables (Consider moving to a dedicated state/learning manager later)
        self.conversation_patterns = defaultdict(list)
        self.user_preferences = defaultdict(dict)
        self.response_effectiveness = {}
        self.last_learning_update = time.time()
        # self.learning_update_interval = LEARNING_UPDATE_INTERVAL # Interval used in background task

        # Topic tracking
        self.active_topics = defaultdict(lambda: {
            "topics": [], "last_update": time.time(), "topic_history": [],
            "user_topic_interests": defaultdict(list)
        })
        # self.topic_update_interval = TOPIC_UPDATE_INTERVAL # Used in analysis

        # Conversation tracking / Caches
        self.conversation_history = defaultdict(lambda: deque(maxlen=100))
        self.thread_history = defaultdict(lambda: deque(maxlen=50))
        self.user_conversation_mapping = defaultdict(set)
        self.channel_activity = defaultdict(lambda: 0.0) # Use float for timestamp
        self.conversation_topics = defaultdict(str)
        self.user_relationships = defaultdict(dict)
        self.conversation_summaries: Dict[int, Dict[str, Any]] = {} # Store dict with summary and timestamp
        self.channel_topics_cache: Dict[int, Dict[str, Any]] = {} # Store dict with topic and timestamp
        # self.channel_topic_cache_ttl = CHANNEL_TOPIC_CACHE_TTL # Used in prompt building

        self.message_cache = {
            'by_channel': defaultdict(lambda: deque(maxlen=CONTEXT_WINDOW_SIZE)), # Use config
            'by_user': defaultdict(lambda: deque(maxlen=50)),
            'by_thread': defaultdict(lambda: deque(maxlen=50)),
            'global_recent': deque(maxlen=200),
            'mentioned': deque(maxlen=50),
            'replied_to': defaultdict(lambda: deque(maxlen=20))
        }

        self.active_conversations = {}
        self.bot_last_spoke = defaultdict(float)
        self.message_reply_map = {}

        # Enhanced sentiment tracking
        self.conversation_sentiment = defaultdict(lambda: {
            "overall": "neutral", "intensity": 0.5, "recent_trend": "stable",
            "user_sentiments": {}, "last_update": time.time()
        })
        # self.sentiment_update_interval = SENTIMENT_UPDATE_INTERVAL # Used in analysis

        # Interest Tracking State
        self.gurt_participation_topics = defaultdict(int)
        self.last_interest_update = time.time()
        self.gurt_message_reactions = defaultdict(lambda: {"positive": 0, "negative": 0, "topic": None, "timestamp": 0.0}) # Added timestamp

        # Background task handle
        self.background_task: Optional[asyncio.Task] = None
        self.last_evolution_update = time.time() # Used in background task

        # --- Setup Commands and Listeners ---
        # Add commands defined in commands.py
        setup_commands(self)
        # Add listeners defined in listeners.py
        # Note: Listeners need to be added to the bot instance, not the cog directly in this pattern.
        # We'll add them in cog_load or the main setup function.

        print("GurtCog initialized.")

    async def cog_load(self):
        """Create aiohttp session, initialize DB, load baselines, start background task"""
        self.session = aiohttp.ClientSession()
        print("GurtCog: aiohttp session created")

        # Initialize DB via MemoryManager
        await self.memory_manager.initialize_sqlite_database()
        await self.memory_manager.load_baseline_personality(BASELINE_PERSONALITY)
        await self.memory_manager.load_baseline_interests(BASELINE_INTERESTS)

        if not self.api_key:
            print("WARNING: OpenRouter API key not configured (AI_API_KEY).")
        else:
            print(f"GurtCog: Using model: {self.default_model}")
        if not self.tavily_api_key:
             print("WARNING: Tavily API key not configured (TAVILY_API_KEY). Web search disabled.")

        # Add listeners to the bot instance
        self.bot.add_listener(on_ready_listener(self), 'on_ready')
        self.bot.add_listener(on_message_listener(self), 'on_message')
        self.bot.add_listener(on_reaction_add_listener(self), 'on_reaction_add')
        self.bot.add_listener(on_reaction_remove_listener(self), 'on_reaction_remove')
        print("GurtCog: Listeners added.")

        # Start background task
        if self.background_task is None or self.background_task.done():
            self.background_task = asyncio.create_task(background_processing_task(self))
            print("GurtCog: Started background processing task.")
        else:
             print("GurtCog: Background processing task already running.")

    async def cog_unload(self):
        """Close session and cancel background task"""
        if self.session and not self.session.closed:
            await self.session.close()
            print("GurtCog: aiohttp session closed")
        if self.background_task and not self.background_task.done():
            self.background_task.cancel()
            print("GurtCog: Cancelled background processing task.")
        # Remove listeners
        # Note: Removing listeners dynamically added like this can be tricky.
        # It might be simpler to rely on cog unload handling by discord.py if listeners
        # were added via @commands.Cog.listener decorator within the class.
        # Since we added them manually, we should ideally remove them.
        try:
            self.bot.remove_listener(on_ready_listener(self), 'on_ready')
            self.bot.remove_listener(on_message_listener(self), 'on_message')
            self.bot.remove_listener(on_reaction_add_listener(self), 'on_reaction_add')
            self.bot.remove_listener(on_reaction_remove_listener(self), 'on_reaction_remove')
            print("GurtCog: Listeners removed.")
        except Exception as e:
            print(f"GurtCog: Error removing listeners: {e}")

        print("GurtCog unloaded.")

    # --- Helper methods that might remain in the cog ---
    # (Example: _update_relationship needs access to self.user_relationships)
    # Moved to utils.py, but needs access to cog state. Pass cog instance.
    def _update_relationship(self, user_id_1: str, user_id_2: str, change: float):
        """Updates the relationship score between two users."""
        # This method accesses self.user_relationships, so it stays here or utils needs cog passed.
        # Let's keep it here for simplicity for now.
        if user_id_1 > user_id_2: user_id_1, user_id_2 = user_id_2, user_id_1
        if user_id_1 not in self.user_relationships: self.user_relationships[user_id_1] = {}

        current_score = self.user_relationships[user_id_1].get(user_id_2, 0.0)
        new_score = max(0.0, min(current_score + change, 100.0)) # Clamp 0-100
        self.user_relationships[user_id_1][user_id_2] = new_score
        # print(f"Updated relationship {user_id_1}-{user_id_2}: {current_score:.1f} -> {new_score:.1f} ({change:+.1f})") # Debug log


# Setup function for loading the cog
async def setup(bot):
    """Add the GurtCog to the bot."""
    await bot.add_cog(GurtCog(bot))
    print("GurtCog setup complete.")
