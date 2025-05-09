import os
import random
import json
from dotenv import load_dotenv
from google import genai
from google.genai.types import FunctionDeclaration

# Load environment variables
load_dotenv()

# --- API and Keys ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "1079377687568")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PISTON_API_URL = os.getenv("PISTON_API_URL") # For run_python_code tool
PISTON_API_KEY = os.getenv("PISTON_API_KEY") # Optional key for Piston

# --- Tavily Configuration ---
TAVILY_DEFAULT_SEARCH_DEPTH = os.getenv("TAVILY_DEFAULT_SEARCH_DEPTH", "basic")
TAVILY_DEFAULT_MAX_RESULTS = int(os.getenv("TAVILY_DEFAULT_MAX_RESULTS", 5))
TAVILY_DISABLE_ADVANCED = os.getenv("TAVILY_DISABLE_ADVANCED", "false").lower() == "true" # For cost control

# --- Model Configuration ---
DEFAULT_MODEL = os.getenv("GURT_DEFAULT_MODEL", "gemini-2.5-flash-preview-04-17")
FALLBACK_MODEL = os.getenv("GURT_FALLBACK_MODEL", "gemini-2.5-flash-preview-04-17")
CUSTOM_TUNED_MODEL_ENDPOINT = os.getenv("GURT_CUSTOM_TUNED_MODEL", "gemini-2.5-flash-preview-04-17")
SAFETY_CHECK_MODEL = os.getenv("GURT_SAFETY_CHECK_MODEL", "gemini-2.5-flash-preview-04-17") # Use a Vertex AI model for safety checks

# --- Database Paths ---
DB_PATH = os.getenv("GURT_DB_PATH", "data/gurt_memory.db")
CHROMA_PATH = os.getenv("GURT_CHROMA_PATH", "data/chroma_db")
SEMANTIC_MODEL_NAME = os.getenv("GURT_SEMANTIC_MODEL", 'all-MiniLM-L6-v2')

# --- Memory Manager Config ---
MAX_USER_FACTS = 20 # TODO: Load from env?
MAX_GENERAL_FACTS = 100 # TODO: Load from env?

# --- Personality & Mood ---
MOOD_OPTIONS = [
    "chill", "neutral", "curious", "slightly hyper", "a bit bored", "mischievous",
    "excited", "tired", "sassy", "philosophical", "playful", "dramatic",
    "nostalgic", "confused", "impressed", "skeptical", "enthusiastic",
    "distracted", "focused", "creative", "sarcastic", "wholesome"
]
# Categorize moods for weighted selection
MOOD_CATEGORIES = {
    "positive": ["excited", "enthusiastic", "playful", "wholesome", "creative", "impressed"],
    "negative": ["tired", "a bit bored", "sassy", "sarcastic", "skeptical", "dramatic", "distracted"],
    "neutral": ["chill", "neutral", "curious", "philosophical", "focused", "confused", "nostalgic"],
    "mischievous": ["mischievous"] # Special category for trait link
}
BASELINE_PERSONALITY = {
    "chattiness": 0.7, "emoji_usage": 0.5, "slang_level": 0.5, "randomness": 0.5,
    "verbosity": 0.4, "optimism": 0.5, "curiosity": 0.6, "sarcasm_level": 0.3,
    "patience": 0.4, "mischief": 0.5
}
BASELINE_INTERESTS = {
    "kasane teto": 0.8, "vocaloids": 0.6, "gaming": 0.6, "anime": 0.5,
    "tech": 0.6, "memes": 0.6, "gooning": 0.6
}
MOOD_CHANGE_INTERVAL_MIN = 1200 # 20 minutes
MOOD_CHANGE_INTERVAL_MAX = 2400 # 40 minutes
EVOLUTION_UPDATE_INTERVAL = 1800 # Evolve personality every 30 minutes

# --- Stats Push ---
# How often the Gurt bot should push its stats to the API server (seconds)
STATS_PUSH_INTERVAL = 30 # Push every 30 seconds

# --- Context & Caching ---
CHANNEL_TOPIC_CACHE_TTL = 600 # seconds (10 minutes)
CONTEXT_WINDOW_SIZE = 150  # Number of messages to include in context
CONTEXT_EXPIRY_TIME = 3600  # Time in seconds before context is considered stale (1 hour)
MAX_CONTEXT_TOKENS = 8000  # Maximum number of tokens to include in context (Note: Not actively enforced yet)
SUMMARY_CACHE_TTL = 900 # seconds (15 minutes) for conversation summary cache

# --- API Call Settings ---
API_TIMEOUT = 60 # seconds
SUMMARY_API_TIMEOUT = 45 # seconds
API_RETRY_ATTEMPTS = 1
API_RETRY_DELAY = 1 # seconds

# --- Proactive Engagement Config ---
PROACTIVE_LULL_THRESHOLD = int(os.getenv("PROACTIVE_LULL_THRESHOLD", 180)) # 3 mins
PROACTIVE_BOT_SILENCE_THRESHOLD = int(os.getenv("PROACTIVE_BOT_SILENCE_THRESHOLD", 600)) # 10 mins
PROACTIVE_LULL_CHANCE = float(os.getenv("PROACTIVE_LULL_CHANCE", 0.3))
PROACTIVE_TOPIC_RELEVANCE_THRESHOLD = float(os.getenv("PROACTIVE_TOPIC_RELEVANCE_THRESHOLD", 0.6))
PROACTIVE_TOPIC_CHANCE = float(os.getenv("PROACTIVE_TOPIC_CHANCE", 0.4))
PROACTIVE_RELATIONSHIP_SCORE_THRESHOLD = int(os.getenv("PROACTIVE_RELATIONSHIP_SCORE_THRESHOLD", 70))
PROACTIVE_RELATIONSHIP_CHANCE = float(os.getenv("PROACTIVE_RELATIONSHIP_CHANCE", 0.2))
PROACTIVE_SENTIMENT_SHIFT_THRESHOLD = float(os.getenv("PROACTIVE_SENTIMENT_SHIFT_THRESHOLD", 0.7)) # Intensity threshold for trigger
PROACTIVE_SENTIMENT_DURATION_THRESHOLD = int(os.getenv("PROACTIVE_SENTIMENT_DURATION_THRESHOLD", 600)) # How long sentiment needs to persist (10 mins)
PROACTIVE_SENTIMENT_CHANCE = float(os.getenv("PROACTIVE_SENTIMENT_CHANCE", 0.25))
PROACTIVE_USER_INTEREST_THRESHOLD = float(os.getenv("PROACTIVE_USER_INTEREST_THRESHOLD", 0.6)) # Min interest level for Gurt to trigger
PROACTIVE_USER_INTEREST_MATCH_THRESHOLD = float(os.getenv("PROACTIVE_USER_INTEREST_MATCH_THRESHOLD", 0.5)) # Min interest level for User (if tracked) - Currently not tracked per user, but config is ready
PROACTIVE_USER_INTEREST_CHANCE = float(os.getenv("PROACTIVE_USER_INTEREST_CHANCE", 0.35))


# --- Interest Tracking Config ---
INTEREST_UPDATE_INTERVAL = int(os.getenv("INTEREST_UPDATE_INTERVAL", 1800)) # 30 mins
INTEREST_DECAY_INTERVAL_HOURS = int(os.getenv("INTEREST_DECAY_INTERVAL_HOURS", 24)) # Daily
INTEREST_PARTICIPATION_BOOST = float(os.getenv("INTEREST_PARTICIPATION_BOOST", 0.05))
INTEREST_POSITIVE_REACTION_BOOST = float(os.getenv("INTEREST_POSITIVE_REACTION_BOOST", 0.02))
INTEREST_NEGATIVE_REACTION_PENALTY = float(os.getenv("INTEREST_NEGATIVE_REACTION_PENALTY", -0.01))
INTEREST_FACT_BOOST = float(os.getenv("INTEREST_FACT_BOOST", 0.01))
INTEREST_MIN_LEVEL_FOR_PROMPT = float(os.getenv("INTEREST_MIN_LEVEL_FOR_PROMPT", 0.3))
INTEREST_MAX_FOR_PROMPT = int(os.getenv("INTEREST_MAX_FOR_PROMPT", 4))

# --- Learning Config ---
LEARNING_RATE = 0.05
MAX_PATTERNS_PER_CHANNEL = 50
LEARNING_UPDATE_INTERVAL = 3600 # Update learned patterns every hour
REFLECTION_INTERVAL_SECONDS = int(os.getenv("REFLECTION_INTERVAL_SECONDS", 6 * 3600)) # Reflect every 6 hours
GOAL_CHECK_INTERVAL = int(os.getenv("GOAL_CHECK_INTERVAL", 300)) # Check for pending goals every 5 mins
GOAL_EXECUTION_INTERVAL = int(os.getenv("GOAL_EXECUTION_INTERVAL", 60)) # Check for active goals to execute every 1 min
PROACTIVE_GOAL_CHECK_INTERVAL = int(os.getenv("PROACTIVE_GOAL_CHECK_INTERVAL", 900)) # Check if Gurt should create its own goals every 15 mins

# --- Internal Random Action Config ---
INTERNAL_ACTION_INTERVAL_SECONDS = int(os.getenv("INTERNAL_ACTION_INTERVAL_SECONDS", 300)) # How often to *consider* a random action (10 mins)
INTERNAL_ACTION_PROBABILITY = float(os.getenv("INTERNAL_ACTION_PROBABILITY", 0.5)) # Chance of performing an action each interval (10%)
AUTONOMOUS_ACTION_REPORT_CHANNEL_ID = os.getenv("GURT_AUTONOMOUS_ACTION_REPORT_CHANNEL_ID", 1366840485355982869) # Optional channel ID to report autonomous actions

# --- Topic Tracking Config ---
TOPIC_UPDATE_INTERVAL = 300 # Update topics every 5 minutes
TOPIC_RELEVANCE_DECAY = 0.2
MAX_ACTIVE_TOPICS = 5

# --- Sentiment Tracking Config ---
SENTIMENT_UPDATE_INTERVAL = 300 # Update sentiment every 5 minutes
SENTIMENT_DECAY_RATE = 0.1

# --- Emotion Detection ---
EMOTION_KEYWORDS = {
    "joy": ["happy", "glad", "excited", "yay", "awesome", "love", "great", "amazing", "lol", "lmao", "haha"],
    "sadness": ["sad", "upset", "depressed", "unhappy", "disappointed", "crying", "miss", "lonely", "sorry"],
    "anger": ["angry", "mad", "hate", "furious", "annoyed", "frustrated", "pissed", "wtf", "fuck"],
    "fear": ["afraid", "scared", "worried", "nervous", "anxious", "terrified", "yikes"],
    "surprise": ["wow", "omg", "whoa", "what", "really", "seriously", "no way", "wtf"],
    "disgust": ["gross", "ew", "eww", "disgusting", "nasty", "yuck"],
    "confusion": ["confused", "idk", "what?", "huh", "hmm", "weird", "strange"]
}
EMOJI_SENTIMENT = {
    "positive": ["😊", "😄", "😁", "😆", "😍", "🥰", "❤️", "💕", "👍", "🙌", "✨", "🔥", "💯", "🎉", "🌹"],
    "negative": ["😢", "😭", "😞", "😔", "😟", "😠", "😡", "👎", "💔", "😤", "😒", "😩", "😫", "😰", "🥀"],
    "neutral": ["😐", "🤔", "🙂", "🙄", "👀", "💭", "🤷", "😶", "🫠"]
}

# --- Docker Command Execution Config ---
DOCKER_EXEC_IMAGE = os.getenv("DOCKER_EXEC_IMAGE", "alpine:latest")
DOCKER_COMMAND_TIMEOUT = int(os.getenv("DOCKER_COMMAND_TIMEOUT", 10))
DOCKER_CPU_LIMIT = os.getenv("DOCKER_CPU_LIMIT", "0.5")
DOCKER_MEM_LIMIT = os.getenv("DOCKER_MEM_LIMIT", "64m")

# --- Response Schema ---
RESPONSE_SCHEMA = {
    "name": "gurt_response",
    "description": "The structured response from Gurt.",
    "schema": {
        "type": "object",
        "properties": {
            "should_respond": {
                "type": "boolean",
                "description": "Whether the bot should send a text message in response."
            },
            "content": {
                "type": "string",
                "description": "The text content of the bot's response. Can be empty if only reacting."
            },
            "react_with_emoji": {
                "type": ["string", "null"],
                "description": "Optional: A standard Discord emoji to react with, or null/empty if no reaction."
            },
            "reply_to_message_id": {
                "type": ["string", "null"],
                "description": "Optional: The ID of the message this response should reply to. Null or omit for a regular message."
            }
            # Note: tool_requests is handled by Vertex AI's function calling mechanism
        },
        "required": ["should_respond", "content"]
    }
}

# --- Summary Response Schema ---
SUMMARY_RESPONSE_SCHEMA = {
    "name": "conversation_summary",
    "description": "A concise summary of a conversation.",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "The generated summary of the conversation."
            }
        },
        "required": ["summary"]
    }
}

# --- Profile Update Schema ---
PROFILE_UPDATE_SCHEMA = {
    "name": "profile_update_decision",
    "description": "Decision on whether and how to update the bot's profile.",
    "schema": {
        "type": "object",
        "properties": {
            "should_update": {
                "type": "boolean",
                "description": "True if any profile element should be changed, false otherwise."
            },
            "reasoning": {
                "type": "string",
                "description": "Brief reasoning for the decision and chosen updates (or lack thereof)."
            },
            "updates": {
                "type": "object",
                "properties": {
                    "avatar_query": {
                        "type": ["string", "null"], # Use list type for preprocessor
                        "description": "Search query for a new avatar image, or null if no change."
                    },
                    "new_bio": {
                        "type": ["string", "null"], # Use list type for preprocessor
                        "description": "The new bio text (max 190 chars), or null if no change."
                    },
                    "role_theme": {
                        "type": ["string", "null"], # Use list type for preprocessor
                        "description": "A theme for role selection (e.g., color, interest), or null if no role changes."
                    },
                    "new_activity": {
                        "type": "object",
                        "description": "Object containing the new activity details. Set type and text to null if no change.",
                        "properties": {
                                "type": {
                                    "type": ["string", "null"], # Use list type for preprocessor
                                    "enum": ["playing", "watching", "listening", "competing"],
                                    "description": "Activity type: 'playing', 'watching', 'listening', 'competing', or null."
                                },
                                "text": {
                                    "type": ["string", "null"], # Use list type for preprocessor
                                    "description": "The activity text, or null."
                                }
                        },
                        "required": ["type", "text"]
                    }
                },
                "required": ["avatar_query", "new_bio", "role_theme", "new_activity"]
            }
        },
        "required": ["should_update", "reasoning", "updates"]
    }
}

# --- Role Selection Schema ---
ROLE_SELECTION_SCHEMA = {
    "name": "role_selection_decision",
    "description": "Decision on which roles to add or remove based on a theme.",
    "schema": {
        "type": "object",
        "properties": {
            "roles_to_add": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of role names to add (max 2)."
            },
            "roles_to_remove": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of role names to remove (max 2, only from current roles)."
            }
        },
        "required": ["roles_to_add", "roles_to_remove"]
    }
}

# --- Proactive Planning Schema ---
PROACTIVE_PLAN_SCHEMA = {
    "name": "proactive_response_plan",
    "description": "Plan for generating a proactive response based on context and trigger.",
    "schema": {
        "type": "object",
        "properties": {
            "should_respond": {
                "type": "boolean",
                "description": "Whether Gurt should respond proactively based on the plan."
            },
            "reasoning": {
                "type": "string",
                "description": "Brief reasoning for the decision (why respond or not respond)."
            },
            "response_goal": {
                "type": "string",
                "description": "The intended goal of the proactive message (e.g., 'revive chat', 'share related info', 'react to sentiment', 'engage user interest')."
            },
            "key_info_to_include": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of key pieces of information or context points to potentially include in the response (e.g., specific topic, user fact, relevant external info)."
            },
            "suggested_tone": {
                "type": "string",
                "description": "Suggested tone adjustment based on context (e.g., 'more upbeat', 'more curious', 'slightly teasing')."
            }
        },
        "required": ["should_respond", "reasoning", "response_goal"]
    }
}

# --- Goal Decomposition Schema ---
GOAL_DECOMPOSITION_SCHEMA = {
    "name": "goal_decomposition_plan",
    "description": "Plan outlining the steps (including potential tool calls) to achieve a goal.",
    "schema": {
        "type": "object",
        "properties": {
            "goal_achievable": {
                "type": "boolean",
                "description": "Whether the goal seems achievable with available tools and context."
            },
            "reasoning": {
                "type": "string",
                "description": "Brief reasoning for achievability and the chosen steps."
            },
            "steps": {
                "type": "array",
                "description": "Ordered list of steps to achieve the goal. Each step is a dictionary.",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_description": {
                            "type": "string",
                            "description": "Natural language description of the step."
                        },
                        "tool_name": {
                            "type": ["string", "null"],
                            "description": "The name of the tool to use for this step, or null if no tool is needed (e.g., internal reasoning)."
                        },
                        "tool_arguments": {
                            "type": ["object", "null"],
                            "description": "A dictionary of arguments for the tool call, or null."
                        }
                    },
                    "required": ["step_description"]
                }
            }
        },
        "required": ["goal_achievable", "reasoning", "steps"]
    }
}


# --- Tools Definition ---
def create_tools_list():
    # This function creates the list of FunctionDeclaration objects.
    # This function creates the list of FunctionDeclaration objects.
    # It now requires 'FunctionDeclaration' from 'google.generativeai.types' to be imported.
    tool_declarations = []
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_recent_messages",
            description="Get recent messages from a Discord channel",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to get messages from. If not provided, uses the current channel."
                    },
                    "limit": {
                        "type": "integer", # Corrected type
                        "description": "The maximum number of messages to retrieve (1-100)"
                    }
                },
                "required": ["limit"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="search_user_messages",
            description="Search for messages from a specific user",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user to get messages from"
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to search in. If not provided, searches in the current channel."
                    },
                    "limit": {
                        "type": "integer", # Corrected type
                        "description": "The maximum number of messages to retrieve (1-100)"
                    }
                },
                "required": ["user_id", "limit"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="search_messages_by_content",
            description="Search for messages containing specific content",
            parameters={
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "The text to search for in messages"
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to search in. If not provided, searches in the current channel."
                    },
                    "limit": {
                        "type": "integer", # Corrected type
                        "description": "The maximum number of messages to retrieve (1-100)"
                    }
                },
                "required": ["search_term", "limit"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_channel_info",
            description="Get information about a Discord channel",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to get information about. If not provided, uses the current channel."
                    }
                },
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_conversation_context",
            description="Get the context of the current conversation",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to get conversation context from. If not provided, uses the current channel."
                    },
                    "message_count": {
                        "type": "integer", # Corrected type
                        "description": "The number of messages to include in the context (5-50)"
                    }
                },
                "required": ["message_count"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_thread_context",
            description="Get the context of a thread conversation",
            parameters={
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "The ID of the thread to get context from"
                    },
                    "message_count": {
                        "type": "integer", # Corrected type
                        "description": "The number of messages to include in the context (5-50)"
                    }
                },
                "required": ["thread_id", "message_count"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_user_interaction_history",
            description="Get the history of interactions between users",
            parameters={
                "type": "object",
                "properties": {
                    "user_id_1": {
                        "type": "string",
                        "description": "The ID of the first user"
                    },
                    "user_id_2": {
                        "type": "string",
                        "description": "The ID of the second user. If not provided, gets interactions between user_id_1 and the bot."
                    },
                    "limit": {
                        "type": "integer", # Corrected type
                        "description": "The maximum number of interactions to retrieve (1-50)"
                    }
                },
                "required": ["user_id_1", "limit"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_conversation_summary",
            description="Get a summary of the recent conversation in a channel",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to get the conversation summary from. If not provided, uses the current channel."
                    }
                },
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_message_context",
            description="Get the context around a specific message",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the message to get context for"
                    },
                    "before_count": {
                        "type": "integer", # Corrected type
                        "description": "The number of messages to include before the specified message (1-25)"
                    },
                    "after_count": {
                        "type": "integer", # Corrected type
                        "description": "The number of messages to include after the specified message (1-25)"
                    }
                },
                "required": ["message_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="web_search",
            description="Search the web for information on a given topic or query. Use this to find current information, facts, or context about things mentioned in the chat.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query or topic to look up online."
                    }
                },
                "required": ["query"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="remember_user_fact",
            description="Store a specific fact or piece of information about a user for later recall. Use this when you learn something potentially relevant about a user (e.g., their preferences, current activity, mentioned interests).",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The Discord ID of the user the fact is about."
                    },
                    "fact": {
                        "type": "string",
                        "description": "The specific fact to remember about the user (keep it concise)."
                    }
                },
                "required": ["user_id", "fact"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_user_facts",
            description="Retrieve previously stored facts or information about a specific user. Use this before responding to a user to potentially recall relevant details about them.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The Discord ID of the user whose facts you want to retrieve."
                    }
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="remember_general_fact",
            description="Store a general fact or piece of information not specific to a user (e.g., server events, shared knowledge, recent game updates). Use this to remember context relevant to the community or ongoing discussions.",
            parameters={
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "The general fact to remember (keep it concise)."
                    }
                },
                "required": ["fact"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_general_facts",
            description="Retrieve previously stored general facts or shared knowledge. Use this to recall context about the server, ongoing events, or general information.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional: A keyword or phrase to search within the general facts. If omitted, returns recent general facts."
                    },
                    "limit": {
                        "type": "integer", # Corrected type
                        "description": "Optional: Maximum number of facts to return (default 10)."
                    }
                },
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="timeout_user",
            description="Timeout a user in the current server for a specified duration. Use this playfully or when someone says something you (Gurt) dislike or find funny.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The Discord ID of the user to timeout."
                    },
                    "duration_minutes": {
                        "type": "integer", # Corrected type
                        "description": "The duration of the timeout in minutes (1-1440, e.g., 5 for 5 minutes)."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional: The reason for the timeout (keep it short and in character)."
                    }
                },
                "required": ["user_id", "duration_minutes"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="calculate",
            description="Evaluate a mathematical expression using a safe interpreter. Handles standard arithmetic, functions (sin, cos, sqrt, etc.), and variables.",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g., '2 * (3 + 4)', 'sqrt(16) + sin(pi/2)')."
                    }
                },
                "required": ["expression"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="run_python_code",
            description="Execute a snippet of Python 3 code in a sandboxed environment using an external API. Returns the standard output and standard error.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python 3 code snippet to execute."
                    }
                },
                "required": ["code"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="create_poll",
            description="Create a simple poll message in the current channel with numbered reactions for voting.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question for the poll."
                    },
                    "options": {
                        "type": "array",
                        "description": "A list of strings representing the poll options (minimum 2, maximum 10).",
                        "items": {
                            "type": "string"
                        }
                    }
                },
                "required": ["question", "options"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="run_terminal_command",
            description="DANGEROUS: Execute a shell command in an isolated, temporary Docker container after an AI safety check. Returns stdout and stderr. Use with extreme caution only for simple, harmless commands like 'echo', 'ls', 'pwd'. Avoid file modification, network access, or long-running processes.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute."
                    }
                },
                "required": ["command"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="remove_timeout",
            description="Remove an active timeout from a user in the current server.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The Discord ID of the user whose timeout should be removed."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional: The reason for removing the timeout (keep it short and in character)."
                    }
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="read_file_content",
            description="Reads the content of a specified file. WARNING: No safety checks are performed. Reads files relative to the bot's current working directory.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file from the project root (e.g., 'discordbot/gurt/config.py')."
                    }
                },
                "required": ["file_path"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="create_new_tool",
            description="EXPERIMENTAL/DANGEROUS: Attempts to create a new tool by generating Python code and its definition using an LLM, then writing it to files. Requires manual reload/restart.",
            parameters={
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The desired name for the new tool (valid Python function name)."
                    },
                    "description": {
                        "type": "string",
                        "description": "The description of what the new tool does (for the FunctionDeclaration)."
                    },
                    "parameters_json": {
                        "type": "string",
                        "description": "A JSON string defining the tool's parameters (properties and required fields), e.g., '{\"properties\": {\"arg1\": {\"type\": \"string\"}}, \"required\": [\"arg1\"]}'."
                    },
                    "returns_description": {
                        "type": "string",
                        "description": "A description of what the Python function should return (e.g., 'a dictionary with status and result')."
                    }
                },
                "required": ["tool_name", "description", "parameters_json", "returns_description"]
            }
        )
    )

    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="execute_internal_command",
            description="Executes a shell command directly on the host machine. Only user_id 452666956353503252 is authorized. You must first use get_user_id to get the user_id param.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute internally."
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Optional timeout in seconds for the command (default 60)."
                    },
                    "user_id": {
                        "type": "string",
                        "description": "The Discord user ID of the user requesting execution."
                    }
                },
                "required": ["command", "user_id"]
            }
        )
    )

    # --- get_user_id ---
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="get_user_id",
            description="Finds the Discord User ID for a given username or display name. Searches the current server or recent messages.",
            parameters={
                "type": "object",
                "properties": {
                    "user_name": {
                        "type": "string",
                        "description": "The username or display name of the user to find."
                    }
                },
                "required": ["user_name"]
            }
        )
    )

    # --- no_operation ---
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="no_operation",
            description="Does absolutely nothing. Used when a tool call is forced but no action is needed.",
            parameters={
                "type": "object",
                "properties": {}, # No parameters
                "required": []
            }
        )
    )

    # --- write_file_content_unsafe ---
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="write_file_content_unsafe",
            description="Writes content to a specified file. WARNING: No safety checks are performed. Uses 'w' (overwrite) or 'a' (append) mode. Creates directories if needed.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The relative path to the file to write to."
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file."
                    },
                    "mode": {
                        "type": "string",
                        "description": "The write mode: 'w' for overwrite (default), 'a' for append.",
                        "enum": ["w", "a"]
                    }
                },
                "required": ["file_path", "content"]
            }
        )
    )

    # --- execute_python_unsafe ---
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="execute_python_unsafe",
            description="Executes arbitrary Python code directly on the host using exec(). WARNING: EXTREMELY DANGEROUS. No sandboxing.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code string to execute."
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Optional timeout in seconds (default 30)."
                    }
                },
                "required": ["code"]
            }
        )
    )

    # --- send_discord_message ---
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="send_discord_message",
            description="Sends a message to a specified Discord channel ID.",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the Discord channel to send the message to."
                    },
                    "message_content": {
                        "type": "string",
                        "description": "The text content of the message to send."
                    }
                },
                "required": ["channel_id", "message_content"]
            }
        )
    )

    # --- extract_web_content ---
    tool_declarations.append(
        FunctionDeclaration( # Use the imported FunctionDeclaration
            name="extract_web_content",
            description="Extracts the main textual content and optionally images from one or more web page URLs using the Tavily API.",
            parameters={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "description": "A single URL string or a list of URL strings to extract content from.",
                        "items": {"type": "string"}
                    },
                    "extract_depth": {
                        "type": "string",
                        "description": "The depth of extraction ('basic' or 'advanced'). 'basic' is faster and cheaper, 'advanced' is better for complex/dynamic pages like LinkedIn. Defaults to 'basic'.",
                        "enum": ["basic", "advanced"]
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "Whether to include images found on the page in the result. Defaults to false."
                    }
                },
                "required": ["urls"]
            }
        )
    )

    tool_declarations.append(
        FunctionDeclaration(
            name="restart_gurt_bot",
            description="Restarts the Gurt bot process by re-executing the current Python script. Use with caution.",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to send the restart message in. If not provided, no message is sent."
                    }
                },
                "required": ["channel_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="run_git_pull",
            description="Runs 'git pull' in the bot's current working directory on the host machine. Requires authorization via user_id. Returns the output and status.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The Discord user ID of the user requesting the git pull. Required for authorization."
                    }
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_channel_id",
            description="Returns the Discord channel ID for a given channel name in the current server. If no channel_name is provided, returns the ID of the current channel.",
            parameters={
                "type": "object",
                "properties": {
                    "channel_name": {
                        "type": "string",
                        "description": "The name of the channel to look up. If omitted, uses the current channel."
                    }
                },
                "required": []
            }
        )
    )
    # --- Batch 1 Tool Declarations ---
    tool_declarations.append(
        FunctionDeclaration(
            name="get_guild_info",
            description="Gets information about the current Discord server (name, ID, owner, member count, etc.).",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="list_guild_members",
            description="Lists members in the current server, with optional filters for status or role.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of members to return (default 50, max 1000)."
                    },
                    "status_filter": {
                        "type": "string",
                        "description": "Optional: Filter by status ('online', 'idle', 'dnd', 'offline')."
                    },
                    "role_id_filter": {
                        "type": "string",
                        "description": "Optional: Filter by members having a specific role ID."
                    }
                },
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_avatar",
            description="Gets the display avatar URL for a given user ID.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The Discord ID of the user."
                    }
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_bot_uptime",
            description="Gets the duration the bot has been running since its last start.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="schedule_message",
            description="Schedules a message to be sent in a channel at a specific future time (ISO 8601 format with timezone). Requires a persistent scheduler.",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the channel to send the message to."
                    },
                    "message_content": {
                        "type": "string",
                        "description": "The content of the message to schedule."
                    },
                    "send_at_iso": {
                        "type": "string",
                        "description": "The exact time to send the message in ISO 8601 format, including timezone (e.g., '2024-01-01T12:00:00+00:00')."
                    }
                },
                "required": ["channel_id", "message_content", "send_at_iso"]
            }
        )
    )
    # --- End Batch 1 ---

    # --- Batch 2 Tool Declarations ---
    tool_declarations.append(
        FunctionDeclaration(
            name="delete_message",
            description="Deletes a specific message by its ID. Requires 'Manage Messages' permission if deleting others' messages.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the message to delete."
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Optional: The ID of the channel containing the message. Defaults to the current channel."
                    }
                },
                "required": ["message_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="edit_message",
            description="Edits a message previously sent by the bot.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The ID of the bot's message to edit."
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The new text content for the message."
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Optional: The ID of the channel containing the message. Defaults to the current channel."
                    }
                },
                "required": ["message_id", "new_content"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_voice_channel_info",
            description="Gets detailed information about a specific voice channel, including connected members.",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "The ID of the voice channel to get information about."
                    }
                },
                "required": ["channel_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="move_user_to_voice_channel",
            description="Moves a user to a specified voice channel. Requires 'Move Members' permission.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user to move."
                    },
                    "target_channel_id": {
                        "type": "string",
                        "description": "The ID of the voice channel to move the user to."
                    }
                },
                "required": ["user_id", "target_channel_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_guild_roles",
            description="Lists all roles available in the current server, ordered by position.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    # --- End Batch 2 ---

    # --- Batch 3 Tool Declarations ---
    tool_declarations.append(
        FunctionDeclaration(
            name="assign_role_to_user",
            description="Assigns a specific role to a user by their IDs. Requires 'Manage Roles' permission and role hierarchy.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user to assign the role to."
                    },
                    "role_id": {
                        "type": "string",
                        "description": "The ID of the role to assign."
                    }
                },
                "required": ["user_id", "role_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="remove_role_from_user",
            description="Removes a specific role from a user by their IDs. Requires 'Manage Roles' permission and role hierarchy.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user to remove the role from."
                    },
                    "role_id": {
                        "type": "string",
                        "description": "The ID of the role to remove."
                    }
                },
                "required": ["user_id", "role_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="fetch_emoji_list",
            description="Lists all custom emojis available in the current server.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_guild_invites",
            description="Lists active invite links for the current server. Requires 'Manage Server' permission.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="purge_messages",
            description="Bulk deletes messages in a text channel. Requires 'Manage Messages' permission. Cannot delete messages older than 14 days.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "The maximum number of messages to delete (1-1000)."
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Optional: The ID of the text channel to purge. Defaults to the current channel."
                    },
                    "user_id": {
                        "type": "string",
                        "description": "Optional: Filter to only delete messages from this user ID."
                    },
                    "before_message_id": {
                        "type": "string",
                        "description": "Optional: Only delete messages before this message ID."
                    },
                    "after_message_id": {
                        "type": "string",
                        "description": "Optional: Only delete messages after this message ID."
                    }
                },
                "required": ["limit"]
            }
        )
    )
    # --- End Batch 3 ---

    # --- Batch 4 Tool Declarations ---
    tool_declarations.append(
        FunctionDeclaration(
            name="get_bot_stats",
            description="Gets various statistics about the bot's current state (guild count, latency, uptime, memory usage, etc.).",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_weather",
            description="Gets the current weather for a specified location. Requires external API setup.",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city name or zip code to get weather for (e.g., 'London', '90210, US')."
                    }
                },
                "required": ["location"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="translate_text",
            description="Translates text to a target language. Requires external API setup.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to translate."
                    },
                    "target_language": {
                        "type": "string",
                        "description": "The target language code (e.g., 'es' for Spanish, 'ja' for Japanese)."
                    },
                    "source_language": {
                        "type": "string",
                        "description": "Optional: The source language code. If omitted, the API will attempt auto-detection."
                    }
                },
                "required": ["text", "target_language"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="remind_user",
            description="Sets a reminder for a user to be delivered via DM at a specific future time (ISO 8601 format with timezone). Requires scheduler setup.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The ID of the user to remind."
                    },
                    "reminder_text": {
                        "type": "string",
                        "description": "The text content of the reminder."
                    },
                    "remind_at_iso": {
                        "type": "string",
                        "description": "The exact time to send the reminder in ISO 8601 format, including timezone (e.g., '2024-01-01T12:00:00+00:00')."
                    }
                },
                "required": ["user_id", "reminder_text", "remind_at_iso"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="fetch_random_image",
            description="Fetches a random image, optionally based on a query. Requires external API setup.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional: A keyword or query to search for specific types of images (e.g., 'cats', 'landscape')."
                    }
                },
                "required": []
            }
        )
    )
    # --- End Batch 4 ---

    # --- Random System/Meme Tools ---
    tool_declarations.append(
        FunctionDeclaration(
            name="read_temps",
            description="Reads the System temperatures (returns a meme if not available). Use for random system checks or to make fun of the user's thermal paste.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="check_disk_space",
            description="Checks disk space on the main drive and returns a meme/quip about how full it is.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="fetch_random_joke",
            description="Fetches a random joke from a public API. Use for random humor or to break the ice.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )

    # --- Guild/Channel Listing Tools ---
    tool_declarations.append(
        FunctionDeclaration(
            name="list_bot_guilds",
            description="Lists all guilds (servers) the bot is currently connected to.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="list_guild_channels",
            description="Lists all channels (text, voice, category, etc.) in a specified guild by its ID.",
            parameters={
                "type": "object",
                "properties": {
                    "guild_id": {
                        "type": "string",
                        "description": "The ID of the guild to list channels for."
                    }
                },
                "required": ["guild_id"]
            }
        )
    )

    # --- Tool Listing Tool ---
    tool_declarations.append(
        FunctionDeclaration(
            name="list_tools",
            description="Lists all available tools with their names and descriptions.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    )

    # --- User Profile Tool Declarations ---
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_username",
            description="Gets the unique Discord username (e.g., username#1234) for a given user ID.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The Discord user ID of the target user."}
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_display_name",
            description="Gets the display name for a given user ID (server nickname if in a guild, otherwise global name).",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The Discord user ID of the target user."}
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_avatar_url",
            description="Gets the URL of the user's current avatar (server-specific if available, otherwise global).",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The Discord user ID of the target user."}
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_status",
            description="Gets the current status (online, idle, dnd, offline) of a user. Requires guild context and potentially presence intent.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The Discord user ID of the target user."}
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_activity",
            description="Gets the current activity (e.g., Playing game, Listening to Spotify) of a user. Requires guild context and potentially presence intent.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The Discord user ID of the target user."}
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_roles",
            description="Gets the list of roles for a user in the current server. Requires guild context.",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The Discord user ID of the target user."}
                },
                "required": ["user_id"]
            }
        )
    )
    tool_declarations.append(
        FunctionDeclaration(
            name="get_user_profile_info",
            description="Gets comprehensive profile information for a given user ID (username, display name, avatar, status, activity, roles, etc.).",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "The Discord user ID of the target user."}
                },
                "required": ["user_id"]
            }
        )
    )
    # --- End User Profile Tool Declarations ---


    return tool_declarations

# Initialize TOOLS list, handling potential ImportError if library not installed
try:
    TOOLS = create_tools_list()
except NameError: # If FunctionDeclaration wasn't imported due to ImportError
    TOOLS = []
    print("WARNING: google-generativeai not installed. TOOLS list is empty.")


# --- Simple Gurt Responses ---
GURT_RESPONSES = [
    "Gurt!", "Gurt gurt!", "Gurt... gurt gurt.", "*gurts happily*",
    "*gurts sadly*", "*confused gurting*", "Gurt? Gurt gurt!", "GURT!",
    "gurt...", "Gurt gurt gurt!", "*aggressive gurting*"
]
