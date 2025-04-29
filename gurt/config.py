import os
import random
import json
from dotenv import load_dotenv

# Placeholder for actual import - will be handled at runtime
try:
    from vertexai import generative_models
except ImportError:
    # Define a dummy class if the library isn't installed,
    # so eval doesn't immediately fail.
    # This assumes the code won't actually run without the library.
    class DummyGenerativeModels:
        class FunctionDeclaration:
            def __init__(self, name, description, parameters):
                pass
    generative_models = DummyGenerativeModels()


# Load environment variables
load_dotenv()

# --- API and Keys ---
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "your-gcp-project-id")
LOCATION = os.getenv("GCP_LOCATION", "us-central1")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PISTON_API_URL = os.getenv("PISTON_API_URL") # For run_python_code tool
PISTON_API_KEY = os.getenv("PISTON_API_KEY") # Optional key for Piston

# --- Tavily Configuration ---
TAVILY_DEFAULT_SEARCH_DEPTH = os.getenv("TAVILY_DEFAULT_SEARCH_DEPTH", "basic")
TAVILY_DEFAULT_MAX_RESULTS = int(os.getenv("TAVILY_DEFAULT_MAX_RESULTS", 5))
TAVILY_DISABLE_ADVANCED = os.getenv("TAVILY_DISABLE_ADVANCED", "false").lower() == "true" # For cost control

# --- Model Configuration ---
DEFAULT_MODEL = os.getenv("GURT_DEFAULT_MODEL", "gemini-2.5-pro-preview-03-25")
FALLBACK_MODEL = os.getenv("GURT_FALLBACK_MODEL", "gemini-2.5-pro-preview-03-25")
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
CONTEXT_WINDOW_SIZE = 200  # Number of messages to include in context
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
INTERNAL_ACTION_INTERVAL_SECONDS = int(os.getenv("INTERNAL_ACTION_INTERVAL_SECONDS", 600)) # How often to *consider* a random action (10 mins)
INTERNAL_ACTION_PROBABILITY = float(os.getenv("INTERNAL_ACTION_PROBABILITY", 0.1)) # Chance of performing an action each interval (10%)

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
    # It requires 'generative_models' to be imported.
    # We define it here but call it later, assuming the import succeeded.
    tool_declarations = []
    tool_declarations.append(
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
            name="read_file_content",
            description="Reads the content of a specified file within the project directory. Useful for understanding code, configuration, or logs.",
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
        generative_models.FunctionDeclaration(
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
        generative_models.FunctionDeclaration(
            name="execute_internal_command",
            description="Executes a shell command directly on the host machine. WARNING: This tool is intended ONLY for internal Gurt operations and MUST NOT be used to execute arbitrary commands requested by users due to significant security risks. Use with extreme caution.",
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
                    }
                },
                "required": ["command"]
            }
        )
    )

    # --- get_user_id ---
    tool_declarations.append(
        generative_models.FunctionDeclaration(
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
    return tool_declarations

# Initialize TOOLS list, handling potential ImportError if library not installed
try:
    TOOLS = create_tools_list()
except NameError: # If generative_models wasn't imported due to ImportError
    TOOLS = []
    print("WARNING: google-cloud-vertexai not installed. TOOLS list is empty.")


# --- Simple Gurt Responses ---
GURT_RESPONSES = [
    "Gurt!", "Gurt gurt!", "Gurt... gurt gurt.", "*gurts happily*",
    "*gurts sadly*", "*confused gurting*", "Gurt? Gurt gurt!", "GURT!",
    "gurt...", "Gurt gurt gurt!", "*aggressive gurting*"
]
