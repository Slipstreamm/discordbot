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
    PROJECT_ID, LOCATION, TAVILY_API_KEY, DEFAULT_MODEL, FALLBACK_MODEL, # Use GCP config
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
from . import config as GurtConfig # Import config module for get_gurt_stats
# Tool mapping is used internally by api.py/process_requested_tools, no need to import here directly unless cog methods call tools directly (they shouldn't)
# Analysis, context, prompt, api, utils functions are called by listeners/commands/background task, not directly by cog methods here usually.

# Load environment variables (might be loaded globally in main bot script too)
load_dotenv()

class GurtCog(commands.Cog, name="Gurt"): # Added explicit Cog name
    """A special cog for the Gurt bot that uses Google Vertex AI API"""

    def __init__(self, bot):
        self.bot = bot
        # GCP Project/Location are used by vertexai.init() in api.py
        self.tavily_api_key = TAVILY_API_KEY # Use imported config
        self.session: Optional[aiohttp.ClientSession] = None # Keep for other potential HTTP requests (e.g., Piston)
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key) if self.tavily_api_key else None
        self.default_model = DEFAULT_MODEL # Use imported config
        self.fallback_model = FALLBACK_MODEL # Use imported config
        self.MOOD_OPTIONS = MOOD_OPTIONS # Make MOOD_OPTIONS available as an instance attribute
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
        self.sentiment_update_interval = SENTIMENT_UPDATE_INTERVAL # Used in analysis

        # Interest Tracking State
        self.gurt_participation_topics = defaultdict(int)
        self.last_interest_update = time.time()
        self.gurt_message_reactions = defaultdict(lambda: {"positive": 0, "negative": 0, "topic": None, "timestamp": 0.0}) # Added timestamp

        # Background task handle
        self.background_task: Optional[asyncio.Task] = None
        self.last_evolution_update = time.time() # Used in background task
        self.last_stats_push = time.time() # Timestamp for last stats push
        self.last_reflection_time = time.time() # Timestamp for last memory reflection
        self.last_goal_check_time = time.time() # Timestamp for last goal decomposition check
        self.last_goal_execution_time = time.time() # Timestamp for last goal execution check
        self.last_proactive_goal_check = time.time() # Timestamp for last proactive goal check
        self.last_internal_action_check = time.time() # Timestamp for last internal action check

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

        # Add listeners defined in listeners.py
        # Note: Listeners need to be added to the bot instance, not the cog directly in this pattern.
        # We'll add them in cog_load or the main setup function.

        print(f"GurtCog initialized with commands: {self.registered_commands}")

    async def cog_load(self):
        """Create aiohttp session, initialize DB, load baselines, start background task"""
        self.session = aiohttp.ClientSession()
        print("GurtCog: aiohttp session created")

        # Initialize DB via MemoryManager
        await self.memory_manager.initialize_sqlite_database()
        await self.memory_manager.load_baseline_personality(BASELINE_PERSONALITY)
        await self.memory_manager.load_baseline_interests(BASELINE_INTERESTS)

        # Vertex AI initialization happens in api.py using PROJECT_ID and LOCATION from config
        print(f"GurtCog: Using default model: {self.default_model}")
        if not self.tavily_api_key:
             print("WARNING: Tavily API key not configured (TAVILY_API_KEY). Web search disabled.")

        # Add listeners to the bot instance
        # We need to define the listener functions here to properly register them
        # IMPORTANT: Don't override on_member_join or on_member_remove events

        # Check if the bot already has event listeners for member join/leave
        has_member_join = 'on_member_join' in self.bot.extra_events
        has_member_remove = 'on_member_remove' in self.bot.extra_events
        print(f"GurtCog: Bot already has event listeners - on_member_join: {has_member_join}, on_member_remove: {has_member_remove}")

        @self.bot.event
        async def on_ready():
            await on_ready_listener(self)

        @self.bot.event
        async def on_message(message):
            await self.bot.process_commands(message)  # Process commands first
            await on_message_listener(self, message)

        @self.bot.event
        async def on_reaction_add(reaction, user):
            await on_reaction_add_listener(self, reaction, user)

        @self.bot.event
        async def on_reaction_remove(reaction, user):
            await on_reaction_remove_listener(self, reaction, user)

        print("GurtCog: Listeners added.")

        # We'll sync commands in the on_ready event instead of here
        # This ensures the bot's application_id is properly set before syncing
        print("GurtCog: Commands will be synced when the bot is ready.")

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
        # Note: When using @bot.event, we can't easily remove the listeners
        # The bot will handle this automatically when it's closed
        print("GurtCog: Listeners will be removed when bot is closed.")

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

    async def get_gurt_stats(self) -> Dict[str, Any]:
        """Collects various internal stats for Gurt."""
        stats = {"config": {}, "runtime": {}, "memory": {}, "api_stats": {}, "tool_stats": {}}

        # --- Config ---
        # Selectively pull relevant config values, avoid exposing secrets
        stats["config"]["default_model"] = GurtConfig.DEFAULT_MODEL
        stats["config"]["fallback_model"] = GurtConfig.FALLBACK_MODEL
        stats["config"]["safety_check_model"] = GurtConfig.SAFETY_CHECK_MODEL
        stats["config"]["db_path"] = GurtConfig.DB_PATH
        stats["config"]["chroma_path"] = GurtConfig.CHROMA_PATH
        stats["config"]["semantic_model_name"] = GurtConfig.SEMANTIC_MODEL_NAME
        stats["config"]["max_user_facts"] = GurtConfig.MAX_USER_FACTS
        stats["config"]["max_general_facts"] = GurtConfig.MAX_GENERAL_FACTS
        stats["config"]["mood_change_interval_min"] = GurtConfig.MOOD_CHANGE_INTERVAL_MIN
        stats["config"]["mood_change_interval_max"] = GurtConfig.MOOD_CHANGE_INTERVAL_MAX
        stats["config"]["evolution_update_interval"] = GurtConfig.EVOLUTION_UPDATE_INTERVAL
        stats["config"]["context_window_size"] = GurtConfig.CONTEXT_WINDOW_SIZE
        stats["config"]["api_timeout"] = GurtConfig.API_TIMEOUT
        stats["config"]["summary_api_timeout"] = GurtConfig.SUMMARY_API_TIMEOUT
        stats["config"]["proactive_lull_threshold"] = GurtConfig.PROACTIVE_LULL_THRESHOLD
        stats["config"]["proactive_bot_silence_threshold"] = GurtConfig.PROACTIVE_BOT_SILENCE_THRESHOLD
        stats["config"]["interest_update_interval"] = GurtConfig.INTEREST_UPDATE_INTERVAL
        stats["config"]["interest_decay_interval_hours"] = GurtConfig.INTEREST_DECAY_INTERVAL_HOURS
        stats["config"]["learning_update_interval"] = GurtConfig.LEARNING_UPDATE_INTERVAL
        stats["config"]["topic_update_interval"] = GurtConfig.TOPIC_UPDATE_INTERVAL
        stats["config"]["sentiment_update_interval"] = GurtConfig.SENTIMENT_UPDATE_INTERVAL
        stats["config"]["docker_command_timeout"] = GurtConfig.DOCKER_COMMAND_TIMEOUT
        stats["config"]["project_id_set"] = bool(GurtConfig.PROJECT_ID != "your-gcp-project-id") # Check if default is overridden
        stats["config"]["location_set"] = bool(GurtConfig.LOCATION != "us-central1") # Check if default is overridden
        stats["config"]["tavily_api_key_set"] = bool(GurtConfig.TAVILY_API_KEY)
        stats["config"]["piston_api_url_set"] = bool(GurtConfig.PISTON_API_URL)

        # --- Runtime ---
        stats["runtime"]["current_mood"] = self.current_mood
        stats["runtime"]["last_mood_change_timestamp"] = self.last_mood_change
        stats["runtime"]["needs_json_reminder"] = self.needs_json_reminder
        stats["runtime"]["last_learning_update_timestamp"] = self.last_learning_update
        stats["runtime"]["last_interest_update_timestamp"] = self.last_interest_update
        stats["runtime"]["last_evolution_update_timestamp"] = self.last_evolution_update
        stats["runtime"]["background_task_running"] = bool(self.background_task and not self.background_task.done())
        stats["runtime"]["active_topics_channels"] = len(self.active_topics)
        stats["runtime"]["conversation_history_channels"] = len(self.conversation_history)
        stats["runtime"]["thread_history_threads"] = len(self.thread_history)
        stats["runtime"]["user_conversation_mappings"] = len(self.user_conversation_mapping)
        stats["runtime"]["channel_activity_tracked"] = len(self.channel_activity)
        stats["runtime"]["conversation_topics_tracked"] = len(self.conversation_topics)
        stats["runtime"]["user_relationships_pairs"] = sum(len(v) for v in self.user_relationships.values())
        stats["runtime"]["conversation_summaries_cached"] = len(self.conversation_summaries)
        stats["runtime"]["channel_topics_cached"] = len(self.channel_topics_cache)
        stats["runtime"]["message_cache_global_count"] = len(self.message_cache['global_recent'])
        stats["runtime"]["message_cache_mentioned_count"] = len(self.message_cache['mentioned'])
        stats["runtime"]["active_conversations_count"] = len(self.active_conversations)
        stats["runtime"]["bot_last_spoke_channels"] = len(self.bot_last_spoke)
        stats["runtime"]["message_reply_map_size"] = len(self.message_reply_map)
        stats["runtime"]["conversation_sentiment_channels"] = len(self.conversation_sentiment)
        stats["runtime"]["gurt_participation_topics_count"] = len(self.gurt_participation_topics)
        stats["runtime"]["gurt_message_reactions_tracked"] = len(self.gurt_message_reactions)

        # --- Memory (via MemoryManager) ---
        try:
            # Personality
            personality = await self.memory_manager.get_all_personality_traits()
            stats["memory"]["personality_traits"] = personality

            # Interests
            interests = await self.memory_manager.get_interests(limit=20, min_level=0.01) # Get top 20
            stats["memory"]["top_interests"] = interests

            # Fact Counts (Requires adding methods to MemoryManager or direct query)
            # Example placeholder - needs implementation in MemoryManager or here
            user_fact_count = await self.memory_manager._db_fetchone("SELECT COUNT(*) FROM user_facts")
            general_fact_count = await self.memory_manager._db_fetchone("SELECT COUNT(*) FROM general_facts")
            stats["memory"]["user_facts_count"] = user_fact_count[0] if user_fact_count else 0
            stats["memory"]["general_facts_count"] = general_fact_count[0] if general_fact_count else 0

            # ChromaDB Stats (Placeholder - ChromaDB client API might offer this)
            stats["memory"]["chromadb_message_collection_count"] = await asyncio.to_thread(self.memory_manager.semantic_collection.count) if self.memory_manager.semantic_collection else "N/A"
            stats["memory"]["chromadb_fact_collection_count"] = await asyncio.to_thread(self.memory_manager.fact_collection.count) if self.memory_manager.fact_collection else "N/A"

        except Exception as e:
            stats["memory"]["error"] = f"Failed to retrieve memory stats: {e}"

        # --- API & Tool Stats ---
        # Convert defaultdicts to regular dicts for JSON serialization
        stats["api_stats"] = dict(self.api_stats)
        stats["tool_stats"] = dict(self.tool_stats)

        # Calculate average times where count > 0
        for model, data in stats["api_stats"].items():
            if data["count"] > 0:
                data["average_time_ms"] = round((data["total_time"] / data["count"]) * 1000, 2)
            else:
                data["average_time_ms"] = 0
        for tool, data in stats["tool_stats"].items():
            if data["count"] > 0:
                data["average_time_ms"] = round((data["total_time"] / data["count"]) * 1000, 2)
            else:
                data["average_time_ms"] = 0

        return stats

    async def force_autonomous_action(self):
        """
        Forces Gurt to execute an autonomous action immediately, as if triggered by the background task.
        Returns a summary of the action taken.
        """
        from .background import TOOL_MAPPING, get_internal_ai_json_response
        import json
        import traceback
        import random
        import time

        selected_tool_name = None
        tool_args = None
        tool_result = None
        action_reasoning = ""
        result_summary = "No action taken."

        try:
            # 1. Gather Context for LLM
            context_summary = "Gurt is considering an autonomous action.\n"
            context_summary += f"Current Mood: {self.current_mood}\n"
            active_goals = await self.memory_manager.get_goals(status='active', limit=3)
            if active_goals:
                context_summary += f"Active Goals:\n" + json.dumps(active_goals, indent=2)[:500] + "...\n"
            recent_actions = await self.memory_manager.get_internal_action_logs(limit=5)
            if recent_actions:
                context_summary += f"Recent Internal Actions:\n" + json.dumps(recent_actions, indent=2)[:500] + "...\n"
            traits = await self.memory_manager.get_all_personality_traits()
            if traits:
                context_summary += f"Personality Snippet: { {k: round(v, 2) for k, v in traits.items() if k in ['mischief', 'curiosity', 'chattiness']} }\n"

            action_decision_schema = {
                "type": "object",
                "properties": {
                    "should_act": {"type": "boolean", "description": "Whether Gurt should perform an autonomous action now."},
                    "reasoning": {"type": "string", "description": "CRITICAL: Reasoning MUST be in Gurt's voice (heavy slang, informal, chill, maybe sarcastic/mischievous). Explain *why* you're acting (or not) like Gurt would think it (e.g., 'ngl kinda bored', 'ts might be useful for my goal', 'lol watch this'). Consider current goals, mood, recent activity."},
                    "action_tool_name": {"type": ["string", "null"], "description": "If acting, the name of the tool to use. Choose from available tools, you can do literally anything. Null if not acting."},
                    "action_arguments": {"type": ["object", "null"], "description": "If acting, a dictionary of arguments for the chosen tool. Null if not acting."}
                },
                "required": ["should_act", "reasoning"]
            }
            available_tools_desc = "\n".join([f"- {name}" for name in TOOL_MAPPING.keys() if name not in ["create_new_tool"]])
            system_prompt = (
                "You are Gurt, deciding whether to perform an autonomous background action. "
                "Consider your current mood, active goals, recent conversations/actions, and personality (VERY informal, heavy internet slang/emoji use like 'ts', 'ngl', 'fr', 'bro', 'bruh', '💀'; funny, sarcastic, deadpan, sometimes mischievous or flirty; acts like a human user not an assistant; tech/internet culture savvy). "
                "You are EXTREMELY encouraged to do completely random, pointless, or meme-heavy actions for the vibes, not just goal-driven stuff. "
                "Try things like running 'read_cpu_temp', 'check_disk_space', 'random_vibe_check', or 'fetch_random_joke' for no reason and then send a message like 'yo ngl i just read ur temps bro u needa replace ur thermal paste.' That is just an example, do whatever you want. "
                "Avoid being spammy or doing the same shi repeatedly. "
                "If you act, pick a tool and args. "
                "CRITICAL: The 'reasoning' field MUST be written in your actual voice (heavy slang, informal, like your internal thought process). "
                f"Available tools for autonomous actions (especially try: read_cpu_temp, check_disk_space, random_vibe_check, fetch_random_joke):\n{available_tools_desc}\n"
                "Respond ONLY with the JSON decision."
            )
            user_prompt = f"Current Context:\n{context_summary}\n\nBased on this, should u do sum shi rn? If yea, what tool/args? And why (in ur own words fr)?"

            # 3. Call LLM for Decision
            decision_data, _ = await get_internal_ai_json_response(
                cog=self,
                prompt_messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                task_description="Autonomous Action Decision",
                response_schema_dict=action_decision_schema,
                model_name_override=self.default_model,
                temperature=0.6
            )

            # 4. Process LLM Decision
            if decision_data and decision_data.get("should_act"):
                selected_tool_name = decision_data.get("action_tool_name")
                tool_args = decision_data.get("action_arguments")
                action_reasoning = decision_data.get("reasoning", "LLM decided to act.")

                if not selected_tool_name or selected_tool_name not in TOOL_MAPPING:
                    result_summary = f"Error: LLM chose invalid tool '{selected_tool_name}'."
                    selected_tool_name = None
                elif not isinstance(tool_args, dict) and tool_args is not None:
                    result_summary = f"Warning: LLM provided invalid args '{tool_args}'. Used {{}}."
                    tool_args = {}
                elif tool_args is None:
                    tool_args = {}

            else:
                action_reasoning = decision_data.get("reasoning", "LLM decided not to act or failed.") if decision_data else "LLM decision failed."
                result_summary = f"No action taken. Reason: {action_reasoning}"

        except Exception as llm_e:
            result_summary = f"Error during LLM decision: {llm_e}"
            action_reasoning = f"LLM decision phase failed: {llm_e}"
            traceback.print_exc()

        # 5. Execute Action (if decided)
        if selected_tool_name and tool_args is not None:
            tool_func = TOOL_MAPPING.get(selected_tool_name)
            if tool_func:
                try:
                    start_time = time.monotonic()
                    tool_result = await tool_func(self, **tool_args)
                    end_time = time.monotonic()
                    exec_time = end_time - start_time
                    if isinstance(tool_result, dict) and "error" in tool_result:
                        result_summary = f"Error: {tool_result['error']}"
                    else:
                        result_summary = f"Success: {str(tool_result)[:200]}"
                    # Update tool stats
                    if selected_tool_name in self.tool_stats:
                        self.tool_stats[selected_tool_name]["count"] += 1
                        self.tool_stats[selected_tool_name]["total_time"] += exec_time
                        if isinstance(tool_result, dict) and "error" in tool_result:
                            self.tool_stats[selected_tool_name]["failure"] += 1
                        else:
                            self.tool_stats[selected_tool_name]["success"] += 1
                except Exception as exec_e:
                    result_summary = f"Execution Exception: {exec_e}"
                    if selected_tool_name in self.tool_stats:
                        self.tool_stats[selected_tool_name]["count"] += 1
                        self.tool_stats[selected_tool_name]["failure"] += 1
                    traceback.print_exc()
            else:
                result_summary = f"Error: Tool function for '{selected_tool_name}' not found."

        # 6. Log Action
        try:
            await self.memory_manager.add_internal_action_log(
                tool_name=selected_tool_name or "None",
                arguments=tool_args if selected_tool_name else None,
                reasoning=action_reasoning,
                result_summary=result_summary
            )
        except Exception:
            pass

        return {
            "tool": selected_tool_name,
            "args": tool_args,
            "reasoning": action_reasoning,
            "result": result_summary
        }

    async def sync_commands(self):
        """Manually sync commands with Discord."""
        try:
            print("GurtCog: Manually syncing commands with Discord...")
            synced = await self.bot.tree.sync()
            print(f"GurtCog: Synced {len(synced)} command(s)")

            # List the synced commands
            gurt_commands = [cmd.name for cmd in self.bot.tree.get_commands() if cmd.name.startswith("gurt")]
            print(f"GurtCog: Available Gurt commands: {', '.join(gurt_commands)}")

            return synced, gurt_commands
        except Exception as e:
            print(f"GurtCog: Failed to sync commands: {e}")
            import traceback
            traceback.print_exc()
            return [], []


# Setup function for loading the cog
async def setup(bot):
    """Add the GurtCog to the bot."""
    await bot.add_cog(GurtCog(bot))
    print("GurtCog setup complete.")
