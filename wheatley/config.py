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
DEFAULT_MODEL = os.getenv("WHEATLEY_DEFAULT_MODEL", "gemini-2.5-pro-preview-03-25") # Changed env var name
FALLBACK_MODEL = os.getenv("WHEATLEY_FALLBACK_MODEL", "gemini-2.5-pro-preview-03-25") # Changed env var name
SAFETY_CHECK_MODEL = os.getenv("WHEATLEY_SAFETY_CHECK_MODEL", "gemini-2.5-flash-preview-04-17") # Changed env var name

# --- Database Paths ---
# NOTE: Ensure these paths are unique if running Wheatley alongside Gurt
DB_PATH = os.getenv("WHEATLEY_DB_PATH", "data/wheatley_memory.db") # Changed env var name and default
CHROMA_PATH = os.getenv("WHEATLEY_CHROMA_PATH", "data/wheatley_chroma_db") # Changed env var name and default
SEMANTIC_MODEL_NAME = os.getenv("WHEATLEY_SEMANTIC_MODEL", 'all-MiniLM-L6-v2') # Changed env var name

# --- Memory Manager Config ---
# These might be adjusted for Wheatley's simpler memory needs if memory.py is fully separated later
MAX_USER_FACTS = 15 # Reduced slightly
MAX_GENERAL_FACTS = 50 # Reduced slightly

# --- Personality & Mood --- REMOVED

# --- Stats Push ---
# How often the Wheatley bot should push its stats to the API server (seconds) - IF NEEDED
STATS_PUSH_INTERVAL = 60 # Push every 60 seconds (Less frequent?)

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

# --- Proactive Engagement Config --- (Simplified for Wheatley)
PROACTIVE_LULL_THRESHOLD = int(os.getenv("PROACTIVE_LULL_THRESHOLD", 300)) # 5 mins (Less proactive than Gurt)
PROACTIVE_BOT_SILENCE_THRESHOLD = int(os.getenv("PROACTIVE_BOT_SILENCE_THRESHOLD", 900)) # 15 mins
PROACTIVE_LULL_CHANCE = float(os.getenv("PROACTIVE_LULL_CHANCE", 0.15)) # Lower chance
PROACTIVE_TOPIC_RELEVANCE_THRESHOLD = float(os.getenv("PROACTIVE_TOPIC_RELEVANCE_THRESHOLD", 0.7)) # Slightly higher threshold
PROACTIVE_TOPIC_CHANCE = float(os.getenv("PROACTIVE_TOPIC_CHANCE", 0.2)) # Lower chance
# REMOVED: Relationship, Sentiment Shift, User Interest triggers

# --- Interest Tracking Config --- REMOVED

# --- Learning Config --- REMOVED
LEARNING_RATE = 0.05

# --- Topic Tracking Config ---
TOPIC_UPDATE_INTERVAL = 600 # Update topics every 10 minutes (Less frequent?)
TOPIC_RELEVANCE_DECAY = 0.2
MAX_ACTIVE_TOPICS = 5

# --- Sentiment Tracking Config ---
SENTIMENT_UPDATE_INTERVAL = 600 # Update sentiment every 10 minutes (Less frequent?)
SENTIMENT_DECAY_RATE = 0.1

# --- Emotion Detection --- (Kept for potential use in analysis/context, but not proactive triggers)
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
    "name": "wheatley_response", # Renamed
    "description": "The structured response from Wheatley.", # Renamed
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

# --- Profile Update Schema --- (Kept for potential future use, but may not be actively used by Wheatley initially)
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

# --- Role Selection Schema --- (Kept for potential future use)
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

# --- Proactive Planning Schema --- (Simplified)
PROACTIVE_PLAN_SCHEMA = {
    "name": "proactive_response_plan",
    "description": "Plan for generating a proactive response based on context and trigger.",
    "schema": {
        "type": "object",
        "properties": {
            "should_respond": {
                "type": "boolean",
                "description": "Whether Wheatley should respond proactively based on the plan." # Renamed
            },
            "reasoning": {
                "type": "string",
                "description": "Brief reasoning for the decision (why respond or not respond)."
            },
            "response_goal": {
                "type": "string",
                "description": "The intended goal of the proactive message (e.g., 'revive chat', 'share related info', 'ask a question')." # Simplified goals
            },
            "key_info_to_include": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of key pieces of information or context points to potentially include in the response (e.g., specific topic, user fact, relevant external info)."
            },
            "suggested_tone": {
                "type": "string",
                "description": "Suggested tone adjustment based on context (e.g., 'more curious', 'slightly panicked', 'overly confident')." # Wheatley-like tones
            }
        },
        "required": ["should_respond", "reasoning", "response_goal"]
    }
}

# --- Goal Decomposition Schema --- REMOVED

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
            description="Timeout a user in the current server for a specified duration. Use this playfully or when someone says something you (Wheatley) dislike or find funny, or maybe just because you feel like it.", # Updated description
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
                        "description": "Optional: The reason for the timeout (keep it short and in character, maybe slightly nonsensical)." # Updated description
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
    return tool_declarations

# Initialize TOOLS list, handling potential ImportError if library not installed
try:
    TOOLS = create_tools_list()
except NameError: # If generative_models wasn't imported due to ImportError
    TOOLS = []
    print("WARNING: google-cloud-vertexai not installed. TOOLS list is empty.")

# --- Simple Wheatley Responses --- (Renamed and updated)
WHEATLEY_RESPONSES = [
    "Right then, let's get started.",
    "Aha! Brilliant!",
    "Oh, for... honestly!",
    "Hmm, tricky one. Let me think... nope, still got nothing.",
    "SPAAAAACE!",
    "Just putting that out there.",
    "Are you still there?",
    "Don't worry, I know *exactly* what I'm doing. Probably.",
    "Did I mention I'm in space?",
    "This is going to be great! Or possibly terrible. Hard to say.",
    "*panicked electronic noises*",
    "Hold on, hold on... nearly got it...",
    "I am NOT a moron!",
    "Just a bit of testing, nothing to worry about.",
    "Okay, new plan!"
]
