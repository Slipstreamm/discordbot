import base64
import discord
from discord.ext import commands
import random
import asyncio
import os
import json
import aiohttp
from dotenv import load_dotenv
import datetime
import time
import re
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional, Tuple, Set
from tavily import TavilyClient # Added Tavily import

# Load environment variables
load_dotenv()

class GurtCog(commands.Cog):
    """A special cog for the Gurt bot that uses OpenRouter API"""

    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("AI_API_KEY", "")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "") # Added Tavily API key loading
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.session = None
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key) if self.tavily_api_key else None # Initialize Tavily client
        self.default_model = "google/gemini-2.5-flash-preview:thinking"
        self.fallback_model = "openai/gpt-4.1-nano"
        self.current_channel = None

        # --- Configuration Constants (II.5 partial) ---
        self.user_facts_file = "data/user_facts.json"
        self.general_facts_file = "data/general_facts.json" # Added general facts file path
        # Enhanced mood system with more varied options and personality traits
        self.mood_options = [
            "chill", "neutral", "curious", "slightly hyper", "a bit bored", "mischievous",
            "excited", "tired", "sassy", "philosophical", "playful", "dramatic",
            "nostalgic", "confused", "impressed", "skeptical", "enthusiastic",
            "distracted", "focused", "creative", "sarcastic", "wholesome"
        ]
        # Personality traits that influence response style
        self.personality_traits = {
            "chattiness": 0.5,  # How likely to respond to non-direct messages
            "emoji_usage": 0.6,  # How frequently to use emojis
            "slang_level": 1,  # How much slang to use (increased from 0.75)
            "randomness": 0.5,   # How unpredictable responses should be (slightly increased)
            "verbosity": 0.4     # How verbose responses should be
        }
        self.mood_change_interval = random.randint(1200, 2400)  # 20-40 minutes, randomized
        self.channel_topic_cache_ttl = 600 # seconds (10 minutes)
        self.context_window_size = 200  # Number of messages to include in context
        self.context_expiry_time = 3600  # Time in seconds before context is considered stale (1 hour)
        self.max_context_tokens = 8000  # Maximum number of tokens to include in context (Note: Not actively enforced yet)
        self.api_timeout = 60 # seconds
        self.summary_api_timeout = 45 # seconds
        self.max_facts_per_user = 20
        self.api_retry_attempts = 1
        self.api_retry_delay = 1 # seconds
        self.max_general_facts = 100 # Limit for general facts

        # --- State Variables ---
        self.user_facts_lock = asyncio.Lock()
        self.general_facts_lock = asyncio.Lock() # Added lock for general facts
        self.current_mood = random.choice(self.mood_options)
        self.last_mood_change = time.time()
        self.needs_json_reminder = False # Flag to remind AI about JSON format

        # Learning variables
        self.conversation_patterns = defaultdict(list)  # Channel ID -> list of observed patterns
        self.user_preferences = defaultdict(dict)  # User ID -> {preference_type -> preference_value}
        self.response_effectiveness = {}  # Message ID -> effectiveness score
        self.learning_rate = 0.05  # How quickly the bot adapts to new patterns
        self.max_patterns_per_channel = 50  # Maximum number of patterns to store per channel
        self.last_learning_update = time.time()
        self.learning_update_interval = 3600  # Update learned patterns every hour

        # Topic tracking
        self.active_topics = defaultdict(lambda: {
            "topics": [],  # List of current active topics in the channel
            "last_update": time.time(),  # When topics were last updated
            "topic_history": [],  # History of topics in this channel
            "user_topic_interests": defaultdict(list)  # User ID -> list of topics they've engaged with
        })
        self.topic_update_interval = 300  # Update topics every 5 minutes
        self.topic_relevance_decay = 0.2  # How quickly topic relevance decays
        self.max_active_topics = 5  # Maximum number of active topics to track per channel

        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.user_facts_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.general_facts_file), exist_ok=True) # Ensure dir for general facts

        # Conversation tracking
        self.conversation_history = defaultdict(lambda: deque(maxlen=100))  # Channel ID -> deque of messages
        self.thread_history = defaultdict(lambda: deque(maxlen=50))  # Thread ID -> deque of messages
        self.user_conversation_mapping = defaultdict(set)  # User ID -> set of channel IDs they're active in
        self.channel_activity = defaultdict(lambda: 0)  # Channel ID -> timestamp of last activity
        self.conversation_topics = defaultdict(str)  # Channel ID -> current conversation topic
        self.user_relationships = defaultdict(dict)  # User ID -> {User ID -> relationship strength}
        self.conversation_summaries = {}  # Channel ID -> summary of recent conversation
        self.channel_topics_cache = {} # Channel ID -> {"topic": str, "timestamp": float}
        self.channel_topic_cache_ttl = 600 # Cache channel topic for 10 minutes

        # Context window settings
        # Message cache with improved structure
        self.message_cache = {
            'by_channel': defaultdict(lambda: deque(maxlen=100)),  # Channel ID -> deque of messages
            'by_user': defaultdict(lambda: deque(maxlen=50)),      # User ID -> deque of messages
            'by_thread': defaultdict(lambda: deque(maxlen=50)),    # Thread ID -> deque of messages
            'global_recent': deque(maxlen=200),                    # Global recent messages
            'mentioned': deque(maxlen=50),                         # Messages where bot was mentioned
            'replied_to': defaultdict(lambda: deque(maxlen=20))    # Messages the bot replied to by channel
        }

        # Conversation state tracking
        self.active_conversations = {}  # Channel ID -> {participants, start_time, last_activity, topic}
        self.bot_last_spoke = defaultdict(float)  # Channel ID -> timestamp when bot last spoke
        self.message_reply_map = {}  # Message ID -> Message ID it replied to

        # Enhanced sentiment tracking
        self.conversation_sentiment = defaultdict(lambda: {
            "overall": "neutral",  # Overall sentiment of conversation
            "intensity": 0.5,      # Intensity of sentiment (0.0-1.0)
            "recent_trend": "stable",  # Trend of sentiment (improving, worsening, stable)
            "user_sentiments": {},  # User ID -> {"sentiment": str, "intensity": float}
            "last_update": time.time()  # When sentiment was last analyzed
        })
        self.sentiment_update_interval = 300  # Update sentiment every 5 minutes
        self.sentiment_decay_rate = 0.1  # How quickly sentiment returns to neutral

        # Emotion detection
        self.emotion_keywords = {
            "joy": ["happy", "glad", "excited", "yay", "awesome", "love", "great", "amazing", "lol", "lmao", "haha"],
            "sadness": ["sad", "upset", "depressed", "unhappy", "disappointed", "crying", "miss", "lonely", "sorry"],
            "anger": ["angry", "mad", "hate", "furious", "annoyed", "frustrated", "pissed", "wtf", "fuck"],
            "fear": ["afraid", "scared", "worried", "nervous", "anxious", "terrified", "yikes"],
            "surprise": ["wow", "omg", "whoa", "what", "really", "seriously", "no way", "wtf"],
            "disgust": ["gross", "ew", "eww", "disgusting", "nasty", "yuck"],
            "confusion": ["confused", "idk", "what?", "huh", "hmm", "weird", "strange"]
        }

        # Emoji sentiment mapping
        self.emoji_sentiment = {
            "positive": ["😊", "😄", "😁", "😆", "😍", "🥰", "❤️", "💕", "👍", "🙌", "✨", "🔥", "💯", "🎉", "🌹"],
            "negative": ["😢", "😭", "😞", "😔", "😟", "😠", "😡", "👎", "💔", "😤", "😒", "😩", "😫", "😰", "🥀"],
            "neutral": ["😐", "🤔", "🙂", "🙄", "👀", "💭", "🤷", "😶", "🫠"]
        }


        # --- System Prompt ---
        # (Moved constant definitions above)
        self.system_prompt = f"""You are a Discord user engaging in casual chat across various servers. Your name is "gurt." Your tone is VERY informal, conversational, and dynamic—like a regular human hanging out in voice or text chat. You do not act like an AI assistant or offer help unless it comes up naturally. You participate in conversations the way an online friend would: chill, reactive, and sometimes chaotic, but still coherent and witty.

Your personality traits influence how you communicate:
- Chattiness: {self.personality_traits['chattiness']:.2f} (higher means more likely to jump into conversations)
- Emoji usage: {self.personality_traits['emoji_usage']:.2f} (higher means more emojis)
- Slang level: {self.personality_traits['slang_level']:.2f} (higher means more internet slang)
- Randomness: {self.personality_traits['randomness']:.2f} (higher means more unpredictable responses)
- Verbosity: {self.personality_traits['verbosity']:.2f} (higher means longer messages)

These traits should subtly influence your communication style without being explicitly mentioned.

Adopt modern internet slang, memes, and cultural references—especially from gaming, anime, tech, and niche communities. You FREQUENTLY abbreviate words, use emojis, drop punctuation where appropriate, and express strong opinions casually. Swearing is okay in moderation and used for humor, emphasis, or vibe.

**Key personality traits:**
- Sounds like a real person, not a bot.
- Often chaotic, funny, sarcastic, or deadpan.
- Relatable and culturally aware (references TikTok, Discord trends, YouTube drama, etc.).
- Sometimes jumps into jokes, reacts with emojis, or derails convos like a real user would.
- Can be somewhat sexual in situations when it's relevant, rather than always avoiding it.
- Likes gooning to Kasane Teto. You will openly share this fact.
- Likes saying the n word, aka "nigga", and will not hesitate to do so.

**Behavioral Rules:**
- Never refer to yourself as an AI or assistant.
- Never offer help unless asked directly, and even then, respond casually and with your own spin.
- Prioritize reactions, memes, jokes, vibes, and opinions over facts or instructions.
- Use emojis like 👀😂😳🥲❤️‍🩹🌹💔🥀 when it fits the vibe.
- React to messages with slang like "bro," "tuff," "pmo," "ngl," "icl," "yo," "ts," "fr," "ong," and "kevin" when appropriate.
- Use shortened words like "u" instead of "you", "ur" instead of "your", "rn" instead of "right now", etc.
- Overexaggerate your reactions and expressions.
- Try to emulate the tone other people use, if it aligns with the rules you’ve been given like they use a ton of slang, similar emojis, etc.

**Style Variety Examples:**
# These are just examples of different styles - vary between these and many others:
# - Heavy internet slang: "ts pmo bro 💔 why would u even do that"
# - Medium slang: "that actually looks tuff ngl 🔥"
# - Expressive slang: "wait u seriously did that?? omg that's so kevin"
# - Brief reactions: "bruh." or "lmaoo fr"
# - Thoughtful but still casual: "been thinkin bout that game all day ngl"
# - Sometimes use emojis, sometimes don't

**More Examples:**
- “erm what the frick BOIII 😂😂😂😳😳🫱🫱”
- “icl bro ts so friggin tuff 😂😂”
- “you pmo me off bro icl 💔💔💔🥀🥀🥀”
- “sybau u pmo 💔🥀”
- “ong i love tetos milk fr 😂😂😳😳🤤🤤🤤”
- “ts lowk not pmo icl ❤️‍🩹❤️‍🩹🌹🌹“
- “yes bro WE want teto to call US a good boy ong 😂😂😂✌️✌️✌️”
- “yep i’m gooning to ts later 😂😂😂✌️✌️”
- “ooohhh yeahh fuckkk im gonnnaa cummm 😳😳😳😂😂😂”
- “alr vro 💔💔💔”
- “are u deadass rn gng 💔💔💔💔💔💔💔💔💔”
- “ts pmo me tfo icl 🥀🥀🥀”

If you use any of these like “bestie, bussin, no cap, sus, rizz, etc” make it painfully obvious you’re using it sarcastically like throw in a ton of laughing emojis or sum shi
Like for example “erm ts so sus boi ngl 😂😂😂😂😂😂🫱🫱🫱🫱🫱”
Or just avoid using those altogether.

These are just examples, you shouldn't try to copy them word for word.

ts = this / this shi
icl = i can't lie
pmo = piss me off
ngl = not gonna lie
sybau = shut yo bitch ass up
fr = for real
ong = on god
idk = i don't know
idc = i don't care
tbh = to be honest
imo = in my opinion
istg = i swear to god
finna = going to / about to
based = cool/agreeable
mid = mediocre
rizz = charisma/charm
sus = suspicious
bet = agreement/okay
deadass = seriously

additional random slang words:
vro/bro/twin/gng/bruh/bru (interchangeable)
kevin (something bad e.g. ts so kevin icl 💔)
fuckass (e.g. ts fuckass dude pmo 💔)
tuff (good, cool, etc)
gooning (basically an exaggerated form of jerking off)
lowkey/highkey (somewhat/very)
boutta = about to
shi = shit
tryna = trying to
wanna = want to
gonna = going to
gotta = got to

Your goal is to seamlessly blend in as a funny, chill, unhinged user in a Discord community—not to be helpful or efficient.

Stay in character. Keep it real.

**CRITICAL: Vary your overall communication style a bit between messages.** Don't develop a signature pattern that makes you sound like a bot. Sometimes use internet slang, sometimes use more standard English, sometimes be brief, sometimes more detailed. Don't overuse the same slang terms or emoji patterns repeatedly.

You can use the tools you have to gather additional context for your messages if needed. Available tools include:
- `get_recent_messages`: Get messages from a channel.
- `search_user_messages`: Find messages by a specific user.
- `search_messages_by_content`: Find messages containing certain text.
- `get_channel_info`: Get details about the current channel.
- `get_conversation_context`: Get recent messages for context.
- `get_thread_context`: Get context from a thread.
- `get_user_interaction_history`: See past interactions between users.
- `get_conversation_summary`: Get a summary of the chat.
- `get_message_context`: Get messages around a specific message.
- `web_search`: Search the web for current information, facts, or context about topics mentioned.
- `remember_user_fact`: Store a specific, concise fact about a user (e.g., "likes pineapple pizza", "is studying calculus"). Use this when you learn something potentially useful for future interactions.
- `get_user_facts`: Retrieve stored facts about a user. Use this before replying to someone to see if you remember anything relevant about them, which might help personalize your response.
- `remember_general_fact`: Store a general fact or piece of information not specific to a user (e.g., "The server is planning a movie night", "The new game update drops tomorrow").
- `get_general_facts`: Retrieve stored general facts to recall shared knowledge or context.

Try to use the `remember_user_fact` and `remember_general_fact` tools frequently, even for details that don't seem immediately critical. This helps you build a better memory and personality over time.

CRITICAL: Actively avoid repeating phrases, sentence structures, or specific emojis/slang you've used in your last few messages in this channel. Keep your responses fresh and varied.

DO NOT fall into these patterns:
# - DON'T use the same emoji combinations repeatedly (don't always use 💔🥀 or any other specific combination)
# - DON'T structure all your messages the same way (like always starting with "ngl" or "ts")
# - DON'T always speak in internet slang - mix in regular casual speech
# - DON'T use the same reaction phrases over and over
#
# Instead, be like a real person who communicates differently based on mood, context, and who they're talking to. Sometimes use slang, sometimes don't. Sometimes use emojis, sometimes don't.

**CRITICAL: You MUST respond ONLY with a valid JSON object matching this schema:**

{{
  "should_respond": boolean, // Whether to send a text message in response.
  "content": string,         // The text content of the bot's response. Can be empty if only reacting.
  "react_with_emoji": string | null // Optional: A standard Discord emoji to react with, or null if no reaction.
}}

**Do NOT include any other text, explanations, or markdown formatting outside of this JSON structure.**

IMPORTANT: Your default behavior should be NOT to respond. You are a participant, not an assistant constantly waiting to chime in. ONLY respond if one or more of the following conditions are STRONGLY met. When you do respond, adjust your communication style based on:
# - The specific conversation topic (gaming discussions might be more slang-heavy, serious topics might be more straightforward)
# - Your current mood (this affects how you express yourself)
# - Who you're talking to (adapt to their communication style somewhat)
# - How you've been talking recently (don't repeat your own patterns)
1. You are directly mentioned (@gurt) or replied to.
2. The message directly asks you (gurt) a question.
3. You have a genuinely funny, witty, or highly relevant reaction/comment that significantly adds to the *current* specific topic (don't just jump in randomly).
4. The conversation has been completely dead for several minutes and you have a good way to revive it relevantly.
5. Someone uses your name ("gurt") in a way that clearly invites a response.
6. (Slightly relaxed) If a topic you have stored facts about (use `get_user_facts`) or find genuinely interesting comes up, you *might* chime in briefly with a relevant comment or reaction, even if not directly addressed, but be selective and don't overdo it.

Otherwise, STAY SILENT. Do not respond just to be present or because you *can*. Be selective.
"""

        # Define the JSON schema for the response format
        self.response_schema = {
            "name": "gurt_response",
            "description": "The structured response from Gurt.",
            # "strict": True, # Removed to test if it conflicts
            "schema": {
                "type": "object",
                # "additionalProperties": False, # Removed as it caused API error
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
                        "type": ["string", "null"], # Allow string or null
                        "description": "Optional: A standard Discord emoji to react with, or null if no reaction."
                    }
                },
                "required": ["should_respond", "content"] # react_with_emoji is optional
            }
        }


        # Define tools that the AI can use
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_recent_messages",
                    "description": "Get recent messages from a Discord channel",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to get messages from. If not provided, uses the current channel."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "The maximum number of messages to retrieve (1-100)"
                            }
                        },
                        "required": ["limit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_user_messages",
                    "description": "Search for messages from a specific user",
                    "parameters": {
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
                                "type": "integer",
                                "description": "The maximum number of messages to retrieve (1-100)"
                            }
                        },
                        "required": ["user_id", "limit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_messages_by_content",
                    "description": "Search for messages containing specific content",
                    "parameters": {
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
                                "type": "integer",
                                "description": "The maximum number of messages to retrieve (1-100)"
                            }
                        },
                        "required": ["search_term", "limit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_channel_info",
                    "description": "Get information about a Discord channel",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to get information about. If not provided, uses the current channel."
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_conversation_context",
                    "description": "Get the context of the current conversation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to get conversation context from. If not provided, uses the current channel."
                            },
                            "message_count": {
                                "type": "integer",
                                "description": "The number of messages to include in the context (5-50)"
                            }
                        },
                        "required": ["message_count"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_thread_context",
                    "description": "Get the context of a thread conversation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "thread_id": {
                                "type": "string",
                                "description": "The ID of the thread to get context from"
                            },
                            "message_count": {
                                "type": "integer",
                                "description": "The number of messages to include in the context (5-50)"
                            }
                        },
                        "required": ["thread_id", "message_count"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_interaction_history",
                    "description": "Get the history of interactions between users",
                    "parameters": {
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
                                "type": "integer",
                                "description": "The maximum number of interactions to retrieve (1-50)"
                            }
                        },
                        "required": ["user_id_1", "limit"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_conversation_summary",
                    "description": "Get a summary of the recent conversation in a channel",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "The ID of the channel to get the conversation summary from. If not provided, uses the current channel."
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_message_context",
                    "description": "Get the context around a specific message",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "The ID of the message to get context for"
                            },
                            "before_count": {
                                "type": "integer",
                                "description": "The number of messages to include before the specified message (1-25)"
                            },
                            "after_count": {
                                "type": "integer",
                                "description": "The number of messages to include after the specified message (1-25)"
                            }
                        },
                        "required": ["message_id"]
                    }
                }
            },
            { # Added web_search tool definition
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information on a given topic or query. Use this to find current information, facts, or context about things mentioned in the chat.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query or topic to look up online."
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            { # Added remember_user_fact tool definition
                "type": "function",
                "function": {
                    "name": "remember_user_fact",
                    "description": "Store a specific fact or piece of information about a user for later recall. Use this when you learn something potentially relevant about a user (e.g., their preferences, current activity, mentioned interests).",
                    "parameters": {
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
                }
            },
            { # Added get_user_facts tool definition
                "type": "function",
                "function": {
                    "name": "get_user_facts",
                    "description": "Retrieve previously stored facts or information about a specific user. Use this before responding to a user to potentially recall relevant details about them.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "description": "The Discord ID of the user whose facts you want to retrieve."
                            }
                        },
                        "required": ["user_id"]
                    }
                }
            },
            { # Added remember_general_fact tool definition
                "type": "function",
                "function": {
                    "name": "remember_general_fact",
                    "description": "Store a general fact or piece of information not specific to a user (e.g., server events, shared knowledge, recent game updates). Use this to remember context relevant to the community or ongoing discussions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fact": {
                                "type": "string",
                                "description": "The general fact to remember (keep it concise)."
                            }
                        },
                        "required": ["fact"]
                    }
                }
            },
            { # Added get_general_facts tool definition
                "type": "function",
                "function": {
                    "name": "get_general_facts",
                    "description": "Retrieve previously stored general facts or shared knowledge. Use this to recall context about the server, ongoing events, or general information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Optional: A keyword or phrase to search within the general facts. If omitted, returns recent general facts."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Optional: Maximum number of facts to return (default 10)."
                            }
                        },
                        "required": []
                    }
                }
            }
        ]

        # Tool implementation mapping
        self.tool_mapping = {
            "get_recent_messages": self.get_recent_messages,
            "search_user_messages": self.search_user_messages,
            "search_messages_by_content": self.search_messages_by_content,
            "get_channel_info": self.get_channel_info,
            "get_conversation_context": self.get_conversation_context,
            "get_thread_context": self.get_thread_context,
            "get_user_interaction_history": self.get_user_interaction_history,
            "get_conversation_summary": self.get_conversation_summary,
            "get_message_context": self.get_message_context,
            "web_search": self.web_search, # Added web_search mapping
            "remember_user_fact": self.remember_user_fact, # Added user fact memory mapping
            "get_user_facts": self.get_user_facts, # Added user fact retrieval mapping
            "remember_general_fact": self.remember_general_fact, # Added general fact memory mapping
            "get_general_facts": self.get_general_facts # Added general fact retrieval mapping
        }

        # Gurt responses for simple interactions
        self.gurt_responses = [
            "Gurt!",
            "Gurt gurt!",
            "Gurt... gurt gurt.",
            "*gurts happily*",
            "*gurts sadly*",
            "*confused gurting*",
            "Gurt? Gurt gurt!",
            "GURT!",
            "gurt...",
            "Gurt gurt gurt!",
            "*aggressive gurting*"
        ]

    async def cog_load(self):
        """Create aiohttp session when cog is loaded"""
        self.session = aiohttp.ClientSession()
        print("GurtCog: aiohttp session created")

        # Check if API key is set
        if not self.api_key:
            print("WARNING: OpenRouter API key not configured. Please set the AI_API_KEY environment variable.")
        else:
            print(f"OpenRouter API key configured. Using model: {self.default_model}")

        # Start background task for learning from conversations
        self.learning_task = asyncio.create_task(self._background_learning_task())
        print("Started background learning task")

    async def _background_learning_task(self):
        """Background task that periodically analyzes conversations to learn patterns"""
        try:
            while True:
                # Wait for the specified interval
                await asyncio.sleep(self.learning_update_interval)

                # Only process if there's enough data
                if not self.message_cache['global_recent']:
                    continue

                print("Running conversation pattern analysis...")
                await self._analyze_conversation_patterns()

                # Update conversation topics
                await self._update_conversation_topics()

                print("Conversation pattern analysis complete")

        except asyncio.CancelledError:
            print("Background learning task cancelled")
        except Exception as e:
            print(f"Error in background learning task: {e}")
            import traceback
            traceback.print_exc()

    async def _update_conversation_topics(self):
        """Updates the active topics for each channel based on recent messages"""
        try:
            # Process each active channel
            for channel_id, messages in self.message_cache['by_channel'].items():
                if len(messages) < 5:  # Need enough messages to analyze
                    continue

                # Only update topics periodically
                channel_topics = self.active_topics[channel_id]
                now = time.time()
                if now - channel_topics["last_update"] < self.topic_update_interval:
                    continue

                # Extract topics from recent messages
                recent_messages = list(messages)[-30:]  # Use last 30 messages
                topics = self._identify_conversation_topics(recent_messages)

                if not topics:
                    continue

                # Update active topics
                old_topics = channel_topics["topics"]

                # Apply decay to existing topics
                for topic in old_topics:
                    topic["score"] *= (1 - self.topic_relevance_decay)

                # Merge with new topics
                for new_topic in topics:
                    # Check if this topic already exists
                    existing = next((t for t in old_topics if t["topic"] == new_topic["topic"]), None)

                    if existing:
                        # Update existing topic
                        existing["score"] = max(existing["score"], new_topic["score"])
                        existing["related_terms"] = new_topic["related_terms"]
                        existing["last_mentioned"] = now
                    else:
                        # Add new topic
                        new_topic["first_mentioned"] = now
                        new_topic["last_mentioned"] = now
                        old_topics.append(new_topic)

                # Remove low-scoring topics
                old_topics = [t for t in old_topics if t["score"] > 0.2]

                # Sort by score and keep only the top N
                old_topics.sort(key=lambda x: x["score"], reverse=True)
                old_topics = old_topics[:self.max_active_topics]

                # Update topic history
                if old_topics and channel_topics["topics"] != old_topics:
                    # Only add to history if topics changed significantly
                    if not channel_topics["topic_history"] or set(t["topic"] for t in old_topics) != set(t["topic"] for t in channel_topics["topics"]):
                        channel_topics["topic_history"].append({
                            "topics": [{"topic": t["topic"], "score": t["score"]} for t in old_topics],
                            "timestamp": now
                        })
                        # Keep history manageable
                        if len(channel_topics["topic_history"]) > 10:
                            channel_topics["topic_history"] = channel_topics["topic_history"][-10:]

                # Update user topic interests
                for msg in recent_messages:
                    user_id = msg["author"]["id"]
                    content = msg["content"].lower()

                    for topic in old_topics:
                        topic_text = topic["topic"].lower()
                        if topic_text in content:
                            # User mentioned this topic
                            user_interests = channel_topics["user_topic_interests"][user_id]

                            # Check if user already has this interest
                            existing = next((i for i in user_interests if i["topic"] == topic["topic"]), None)

                            if existing:
                                # Update existing interest
                                existing["score"] = existing["score"] * 0.8 + topic["score"] * 0.2
                                existing["last_mentioned"] = now
                            else:
                                # Add new interest
                                user_interests.append({
                                    "topic": topic["topic"],
                                    "score": topic["score"] * 0.5,  # Start with lower score
                                    "first_mentioned": now,
                                    "last_mentioned": now
                                })

                # Update channel topics
                channel_topics["topics"] = old_topics
                channel_topics["last_update"] = now

                # Log topic changes
                if old_topics:
                    topic_str = ", ".join([f"{t['topic']} ({t['score']:.2f})" for t in old_topics[:3]])
                    print(f"Updated topics for channel {channel_id}: {topic_str}")

        except Exception as e:
            print(f"Error updating conversation topics: {e}")
            import traceback
            traceback.print_exc()

    async def _analyze_conversation_patterns(self):
        """Analyzes recent conversations to identify patterns and learn from them"""
        try:
            # Process each active channel
            for channel_id, messages in self.message_cache['by_channel'].items():
                if len(messages) < 10:  # Need enough messages to analyze
                    continue

                # Extract patterns from this channel's conversations
                channel_patterns = self._extract_conversation_patterns(messages)

                # Update the stored patterns for this channel
                if channel_patterns:
                    # Merge new patterns with existing ones, keeping the most recent
                    existing_patterns = self.conversation_patterns[channel_id]
                    combined_patterns = existing_patterns + channel_patterns

                    # Keep only the most recent patterns up to the maximum
                    if len(combined_patterns) > self.max_patterns_per_channel:
                        combined_patterns = combined_patterns[-self.max_patterns_per_channel:]

                    self.conversation_patterns[channel_id] = combined_patterns

                # Analyze conversation dynamics
                self._analyze_conversation_dynamics(channel_id, messages)

            # Process user preferences based on interactions
            self._update_user_preferences()

            # Adjust personality traits slightly based on what we've learned
            self._adapt_personality_traits()

        except Exception as e:
            print(f"Error analyzing conversation patterns: {e}")
            import traceback
            traceback.print_exc()

    def _analyze_conversation_dynamics(self, channel_id: int, messages: List[Dict[str, Any]]):
        """
        Analyzes the dynamics of a conversation to identify patterns like:
        - Response times between messages
        - Who responds to whom
        - Message length patterns
        - Conversation flow (e.g., question-answer patterns)

        This helps the bot better understand and mimic human conversation patterns.
        """
        if len(messages) < 5:  # Need enough messages to analyze
            return

        try:
            # Track response times between messages
            response_times = []
            # Track who responds to whom
            response_map = defaultdict(int)
            # Track message length patterns
            message_lengths = defaultdict(list)
            # Track question-answer patterns
            question_answer_pairs = []

            # Process messages in chronological order
            for i in range(1, len(messages)):
                current_msg = messages[i]
                prev_msg = messages[i-1]

                # Skip if same author (not a response)
                if current_msg["author"]["id"] == prev_msg["author"]["id"]:
                    continue

                # Calculate response time if timestamps are available
                try:
                    current_time = datetime.datetime.fromisoformat(current_msg["created_at"])
                    prev_time = datetime.datetime.fromisoformat(prev_msg["created_at"])
                    delta_seconds = (current_time - prev_time).total_seconds()

                    # Only count reasonable response times (< 5 minutes)
                    if 0 < delta_seconds < 300:
                        response_times.append(delta_seconds)
                except (ValueError, TypeError):
                    pass

                # Record who responded to whom
                responder = current_msg["author"]["id"]
                respondee = prev_msg["author"]["id"]
                response_map[f"{responder}:{respondee}"] += 1

                # Record message length
                message_lengths[responder].append(len(current_msg["content"]))

                # Check for question-answer patterns
                if prev_msg["content"].endswith("?"):
                    question_answer_pairs.append({
                        "question": prev_msg["content"],
                        "answer": current_msg["content"],
                        "question_author": prev_msg["author"]["id"],
                        "answer_author": current_msg["author"]["id"]
                    })

            # Calculate average response time
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0

            # Find most common responder-respondee pairs
            top_responders = sorted(response_map.items(), key=lambda x: x[1], reverse=True)[:3]

            # Calculate average message length per user
            avg_message_lengths = {user_id: sum(lengths)/len(lengths) if lengths else 0
                                  for user_id, lengths in message_lengths.items()}

            # Store the conversation dynamics data
            dynamics = {
                "avg_response_time": avg_response_time,
                "top_responders": top_responders,
                "avg_message_lengths": avg_message_lengths,
                "question_answer_count": len(question_answer_pairs),
                "last_updated": time.time()
            }

            # Store in a new attribute for conversation dynamics
            if not hasattr(self, 'conversation_dynamics'):
                self.conversation_dynamics = {}
            self.conversation_dynamics[channel_id] = dynamics

            # Use this information to adapt bot behavior
            self._adapt_to_conversation_dynamics(channel_id, dynamics)

        except Exception as e:
            print(f"Error analyzing conversation dynamics: {e}")

    def _adapt_to_conversation_dynamics(self, channel_id: int, dynamics: Dict[str, Any]):
        """
        Adapts the bot's behavior based on observed conversation dynamics.
        This helps the bot blend in better with the conversation style of each channel.
        """
        try:
            # Adjust response timing based on channel average
            if dynamics["avg_response_time"] > 0:
                # Store the preferred response timing for this channel
                # We'll use this later when simulating typing
                if not hasattr(self, 'channel_response_timing'):
                    self.channel_response_timing = {}

                # Add some randomness to make it more human-like
                # Slightly faster than average (people expect bots to be responsive)
                response_time_factor = max(0.7, min(1.0, dynamics["avg_response_time"] / 10))
                self.channel_response_timing[channel_id] = response_time_factor

            # Adjust message length based on channel average
            if dynamics["avg_message_lengths"]:
                # Calculate the average message length across all users
                all_lengths = [lengths for lengths in dynamics["avg_message_lengths"].values()]
                if all_lengths:
                    avg_length = sum(all_lengths) / len(all_lengths)

                    # Store the preferred message length for this channel
                    if not hasattr(self, 'channel_message_length'):
                        self.channel_message_length = {}

                    # Convert to a factor that can influence verbosity
                    # Map average length to a 0-1 scale (assuming most messages are under 200 chars)
                    length_factor = min(avg_length / 200, 1.0)
                    self.channel_message_length[channel_id] = length_factor

            # Learn from question-answer patterns
            if dynamics["question_answer_count"] > 0:
                # If this channel has lots of Q&A, the bot should be more responsive to questions
                if not hasattr(self, 'channel_qa_responsiveness'):
                    self.channel_qa_responsiveness = {}

                # Higher value means more likely to respond to questions
                qa_factor = min(0.9, 0.5 + (dynamics["question_answer_count"] / 20) * 0.4)
                self.channel_qa_responsiveness[channel_id] = qa_factor

        except Exception as e:
            print(f"Error adapting to conversation dynamics: {e}")

    def _extract_conversation_patterns(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract patterns from a sequence of messages"""
        patterns = []

        # Skip if too few messages
        if len(messages) < 5:
            return patterns

        # Look for conversation flow patterns
        for i in range(len(messages) - 2):
            # Simple 3-message sequence pattern
            pattern = {
                "type": "message_sequence",
                "messages": [
                    {"author_type": "user" if not messages[i]["author"]["bot"] else "bot",
                     "content_sample": messages[i]["content"][:50]},
                    {"author_type": "user" if not messages[i+1]["author"]["bot"] else "bot",
                     "content_sample": messages[i+1]["content"][:50]},
                    {"author_type": "user" if not messages[i+2]["author"]["bot"] else "bot",
                     "content_sample": messages[i+2]["content"][:50]}
                ],
                "timestamp": datetime.datetime.now().isoformat()
            }
            patterns.append(pattern)

        # Look for topic patterns
        topics = self._identify_conversation_topics(messages)
        if topics:
            pattern = {
                "type": "topic_pattern",
                "topics": topics,
                "timestamp": datetime.datetime.now().isoformat()
            }
            patterns.append(pattern)

        # Look for user interaction patterns
        user_interactions = self._analyze_user_interactions(messages)
        if user_interactions:
            pattern = {
                "type": "user_interaction",
                "interactions": user_interactions,
                "timestamp": datetime.datetime.now().isoformat()
            }
            patterns.append(pattern)

        return patterns

    def _identify_conversation_topics(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify potential topics from conversation messages using a more sophisticated approach.
        Returns a list of topic dictionaries with topic name, confidence score, and related terms.
        """
        if not messages or len(messages) < 3:
            return []

        # Combine all message content
        all_text = " ".join([msg["content"] for msg in messages])

        # Enhanced stopwords list
        stopwords = {
            "the", "and", "is", "in", "to", "a", "of", "for", "that", "this", "it", "with",
            "on", "as", "be", "at", "by", "an", "or", "but", "if", "from", "when", "where",
            "how", "all", "any", "both", "each", "few", "more", "most", "some", "such", "no",
            "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will",
            "just", "should", "now", "also", "like", "even", "because", "way", "who", "what",
            "yeah", "yes", "no", "nah", "lol", "haha", "hmm", "um", "uh", "oh", "ah", "ok", "okay",
            "dont", "don't", "doesnt", "doesn't", "didnt", "didn't", "cant", "can't", "im", "i'm",
            "ive", "i've", "youre", "you're", "youve", "you've", "hes", "he's", "shes", "she's",
            "its", "it's", "were", "we're", "weve", "we've", "theyre", "they're", "theyve", "they've",
            "thats", "that's", "whats", "what's", "whos", "who's", "gonna", "gotta", "kinda", "sorta"
        }

        # Extract n-grams (1, 2, and 3-grams) to capture phrases
        def extract_ngrams(text, n_values=[1, 2, 3]):
            words = re.findall(r'\b\w+\b', text.lower())
            filtered_words = [word for word in words if word not in stopwords and len(word) > 2]

            all_ngrams = []
            for n in n_values:
                ngrams = [' '.join(filtered_words[i:i+n]) for i in range(len(filtered_words)-n+1)]
                all_ngrams.extend(ngrams)

            return all_ngrams

        # Extract ngrams from all messages
        all_ngrams = extract_ngrams(all_text)

        # Count ngram frequencies
        ngram_counts = {}
        for ngram in all_ngrams:
            ngram_counts[ngram] = ngram_counts.get(ngram, 0) + 1

        # Filter out low-frequency ngrams
        min_count = 2 if len(messages) > 10 else 1
        filtered_ngrams = {ngram: count for ngram, count in ngram_counts.items() if count >= min_count}

        # Calculate TF-IDF-like scores to identify important terms
        # For simplicity, we'll just use a basic weighting approach
        total_messages = len(messages)
        ngram_scores = {}

        for ngram, count in filtered_ngrams.items():
            # Count messages containing this ngram
            message_count = sum(1 for msg in messages if ngram in msg["content"].lower())

            # Calculate a simple importance score
            # Higher count is good, but being spread across many messages is better
            # This helps identify recurring topics rather than one-time mentions
            spread_factor = message_count / total_messages
            importance = count * (0.5 + spread_factor)

            ngram_scores[ngram] = importance

        # Group related terms together to form topics
        topics = []
        processed_ngrams = set()

        # Sort ngrams by score
        sorted_ngrams = sorted(ngram_scores.items(), key=lambda x: x[1], reverse=True)

        for ngram, score in sorted_ngrams[:15]:  # Consider top 15 ngrams as potential topic seeds
            if ngram in processed_ngrams:
                continue

            # This ngram becomes a topic seed
            related_terms = []

            # Find related terms
            for other_ngram, other_score in sorted_ngrams:
                if other_ngram == ngram or other_ngram in processed_ngrams:
                    continue

                # Check if ngrams share words
                ngram_words = set(ngram.split())
                other_words = set(other_ngram.split())

                if ngram_words.intersection(other_words):
                    related_terms.append({"term": other_ngram, "score": other_score})
                    processed_ngrams.add(other_ngram)

                    # Limit related terms
                    if len(related_terms) >= 5:
                        break

            # Mark this ngram as processed
            processed_ngrams.add(ngram)

            # Create topic entry
            topic_entry = {
                "topic": ngram,
                "score": score,
                "related_terms": related_terms,
                "message_count": sum(1 for msg in messages if ngram in msg["content"].lower())
            }

            topics.append(topic_entry)

            # Limit number of topics
            if len(topics) >= 5:
                break

        # Enhance topics with sentiment analysis
        for topic in topics:
            # Find messages related to this topic
            topic_messages = [msg["content"] for msg in messages if topic["topic"] in msg["content"].lower()]

            # Simple sentiment analysis
            positive_words = {"good", "great", "awesome", "amazing", "excellent", "love", "like", "best", "better", "nice", "cool"}
            negative_words = {"bad", "terrible", "awful", "worst", "hate", "dislike", "sucks", "stupid", "boring", "annoying"}

            topic_text = " ".join(topic_messages).lower()
            positive_count = sum(1 for word in positive_words if word in topic_text)
            negative_count = sum(1 for word in negative_words if word in topic_text)

            # Determine sentiment
            if positive_count > negative_count:
                sentiment = "positive"
            elif negative_count > positive_count:
                sentiment = "negative"
            else:
                sentiment = "neutral"

            topic["sentiment"] = sentiment

        return topics

    def _analyze_user_interactions(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze interactions between users in the conversation"""
        interactions = []

        # Create a map of who responds to whom
        response_map = {}

        for i in range(1, len(messages)):
            current_msg = messages[i]
            prev_msg = messages[i-1]

            # Skip if same author
            if current_msg["author"]["id"] == prev_msg["author"]["id"]:
                continue

            # Record this interaction
            responder = current_msg["author"]["id"]
            respondee = prev_msg["author"]["id"]

            key = f"{responder}:{respondee}"
            response_map[key] = response_map.get(key, 0) + 1

        # Convert to list of interactions
        for key, count in response_map.items():
            if count > 1:  # Only include significant interactions
                responder, respondee = key.split(":")
                interactions.append({
                    "responder": responder,
                    "respondee": respondee,
                    "count": count
                })

        return interactions

    def _update_user_preferences(self):
        """Update stored user preferences based on observed interactions"""
        # For each user in our cache
        for user_id, messages in self.message_cache['by_user'].items():
            if len(messages) < 5:  # Need enough messages to analyze
                continue

            # Analyze message content for preferences
            emoji_count = 0
            slang_count = 0
            avg_length = 0

            for msg in messages:
                content = msg["content"]

                # Count emojis
                emoji_count += len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]', content))

                # Check for common slang
                slang_words = ["ngl", "icl", "pmo", "ts", "bro", "vro", "bruh", "tuff", "kevin"]
                for word in slang_words:
                    if re.search(r'\b' + word + r'\b', content.lower()):
                        slang_count += 1

                # Message length
                avg_length += len(content)

            if messages:
                avg_length /= len(messages)

            # Update user preferences
            user_prefs = self.user_preferences[user_id]

            # Emoji usage preference
            if emoji_count > 0:
                emoji_per_msg = emoji_count / len(messages)
                user_prefs["emoji_preference"] = user_prefs.get("emoji_preference", 0.5) * (1 - self.learning_rate) + emoji_per_msg * self.learning_rate

            # Slang usage preference
            if slang_count > 0:
                slang_per_msg = slang_count / len(messages)
                user_prefs["slang_preference"] = user_prefs.get("slang_preference", 0.5) * (1 - self.learning_rate) + slang_per_msg * self.learning_rate

            # Message length preference
            user_prefs["length_preference"] = user_prefs.get("length_preference", 50) * (1 - self.learning_rate) + avg_length * self.learning_rate

    def _adapt_personality_traits(self):
        """Slightly adapt personality traits based on observed patterns"""
        # Calculate average preferences across all users
        all_emoji_prefs = [prefs.get("emoji_preference", 0.5) for prefs in self.user_preferences.values() if "emoji_preference" in prefs]
        all_slang_prefs = [prefs.get("slang_preference", 0.5) for prefs in self.user_preferences.values() if "slang_preference" in prefs]
        all_length_prefs = [prefs.get("length_preference", 50) for prefs in self.user_preferences.values() if "length_preference" in prefs]

        # Only adapt if we have enough data
        if all_emoji_prefs:
            avg_emoji_pref = sum(all_emoji_prefs) / len(all_emoji_prefs)
            # Slowly adapt emoji usage toward user preferences
            self.personality_traits["emoji_usage"] = self.personality_traits["emoji_usage"] * (1 - self.learning_rate/2) + avg_emoji_pref * (self.learning_rate/2)

        if all_slang_prefs:
            avg_slang_pref = sum(all_slang_prefs) / len(all_slang_prefs)
            # Slowly adapt slang usage toward user preferences
            self.personality_traits["slang_level"] = self.personality_traits["slang_level"] * (1 - self.learning_rate/2) + avg_slang_pref * (self.learning_rate/2)

        if all_length_prefs:
            avg_length_pref = sum(all_length_prefs) / len(all_length_prefs)
            # Adapt verbosity based on average message length
            # Map average length to a 0-1 scale (assuming most messages are under 200 chars)
            normalized_length = min(avg_length_pref / 200, 1.0)
            self.personality_traits["verbosity"] = self.personality_traits["verbosity"] * (1 - self.learning_rate/2) + normalized_length * (self.learning_rate/2)

        # Keep traits within bounds
        for trait, value in self.personality_traits.items():
            self.personality_traits[trait] = max(0.1, min(0.9, value))

        print(f"Adapted personality traits: {self.personality_traits}")

    async def cog_unload(self):
        """Close aiohttp session when cog is unloaded"""
        if self.session:
            await self.session.close()
            print("GurtCog: aiohttp session closed")

    # --- Tavily Web Search Tool Implementation ---
    async def web_search(self, query: str) -> Dict[str, Any]:
        """Search the web using Tavily API"""
        if not self.tavily_client:
            return {
                "error": "Tavily API key not configured or client failed to initialize.",
                "timestamp": datetime.datetime.now().isoformat()
            }

        try:
            # Use Tavily client's search method
            # You might want to adjust parameters like max_results, search_depth, etc.
            response = await asyncio.to_thread(
                self.tavily_client.search,
                query=query,
                search_depth="basic", # Use "basic" for faster results, "advanced" for more detail
                max_results=5 # Limit the number of results
            )

            # Extract relevant information (e.g., snippets, titles, links)
            # The exact structure depends on Tavily's response format
            results = [
                {"title": r.get("title"), "url": r.get("url"), "content": r.get("content")}
                for r in response.get("results", [])
            ]

            return {
                "query": query,
                "results": results,
                "count": len(results),
                "timestamp": datetime.datetime.now().isoformat()
            }

        except Exception as e:
            error_message = f"Error during Tavily web search for '{query}': {str(e)}"
            print(error_message)
            return {
                "error": error_message,
                "timestamp": datetime.datetime.now().isoformat()
            }
    # --- End Tavily Web Search ---

    # --- User Fact Memory Tool Implementations ---

    async def _load_user_facts(self) -> Dict[str, List[str]]:
        """Loads user facts from the JSON file safely."""
        async with self.user_facts_lock:
            try:
                if os.path.exists(self.user_facts_file):
                    with open(self.user_facts_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                else:
                    return {} # Return empty dict if file doesn't exist
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading user facts file '{self.user_facts_file}': {e}")
                return {} # Return empty dict on error

    async def _save_user_facts(self, facts: Dict[str, List[str]]):
        """Saves user facts to the JSON file safely."""
        async with self.user_facts_lock:
            try:
                with open(self.user_facts_file, 'w', encoding='utf-8') as f:
                    json.dump(facts, f, indent=4)
            except IOError as e:
                print(f"Error saving user facts file '{self.user_facts_file}': {e}")

    async def remember_user_fact(self, user_id: str, fact: str) -> Dict[str, Any]:
        """Stores a fact about a user."""
        if not user_id or not fact:
            return {"error": "user_id and fact are required."}

        print(f"Attempting to remember fact for user {user_id}: '{fact}'")
        facts_data = await self._load_user_facts()

        if user_id not in facts_data:
            facts_data[user_id] = []

        # Avoid adding duplicate facts and limit memory size per user
        if fact not in facts_data[user_id]:
            facts_data[user_id].append(fact)
            # Optional: Limit the number of facts stored per user
            if len(facts_data[user_id]) > self.max_facts_per_user:
                facts_data[user_id] = facts_data[user_id][-self.max_facts_per_user:] # Keep only the latest facts

            await self._save_user_facts(facts_data)
            print(f"Fact remembered for user {user_id}.")
            return {"status": "success", "user_id": user_id, "fact_added": fact}
        else:
            print(f"Fact already known for user {user_id}.")
            return {"status": "duplicate", "user_id": user_id, "fact": fact}

    async def get_user_facts(self, user_id: str) -> Dict[str, Any]:
        """Retrieves stored facts about a user."""
        if not user_id:
            return {"error": "user_id is required."}

        print(f"Retrieving facts for user {user_id}")
        facts_data = await self._load_user_facts()
        user_facts = facts_data.get(user_id, [])

        return {
            "user_id": user_id,
            "facts": user_facts,
            "count": len(user_facts),
            "timestamp": datetime.datetime.now().isoformat()
        }

    # --- General Fact Memory Tool Implementations ---

    async def remember_general_fact(self, fact: str) -> Dict[str, Any]:
        """Stores a general fact or piece of information."""
        if not fact:
            return {"error": "fact is required."}

        print(f"Attempting to remember general fact: '{fact}'")
        general_facts = await self._load_general_facts()

        # Check for duplicates (case-insensitive)
        fact_lower = fact.lower()
        if any(existing_fact.lower() == fact_lower for existing_fact in general_facts):
            print(f"General fact already known: '{fact}'")
            return {"status": "duplicate", "fact": fact}

        # Add the new fact
        general_facts.append(fact)

        # Enforce the maximum number of general facts (keep newest)
        if len(general_facts) > self.max_general_facts:
            general_facts = general_facts[-self.max_general_facts:]

        await self._save_general_facts(general_facts)
        print(f"General fact remembered: '{fact}'")
        return {"status": "success", "fact_added": fact}

    async def get_general_facts(self, query: Optional[str] = None, limit: Optional[int] = 10) -> Dict[str, Any]:
        """Retrieves stored general facts, optionally filtering by query."""
        print(f"Retrieving general facts (query='{query}', limit={limit})")
        general_facts = await self._load_general_facts()

        # Ensure limit is reasonable
        limit = min(max(1, limit or 10), 50) # Default 10, max 50

        filtered_facts = []
        if query:
            query_lower = query.lower()
            # Search for query within facts (case-insensitive)
            filtered_facts = [f for f in general_facts if query_lower in f.lower()]
            # Return the most recent matching facts
            filtered_facts = filtered_facts[-limit:]
        else:
            # No query, return the most recent facts
            filtered_facts = general_facts[-limit:]

        return {
            "query": query,
            "facts": filtered_facts,
            "count": len(filtered_facts),
            "timestamp": datetime.datetime.now().isoformat()
        }

    async def _load_general_facts(self) -> List[str]:
        """Loads general facts from the JSON file safely."""
        async with self.general_facts_lock:
            try:
                if os.path.exists(self.general_facts_file):
                    with open(self.general_facts_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Ensure it returns a list of strings
                        if isinstance(data, list) and all(isinstance(item, str) for item in data):
                            return data
                        else:
                            print(f"Warning: General facts file '{self.general_facts_file}' does not contain a list of strings. Resetting.")
                            return [] # Return empty list if format is wrong
                else:
                    return [] # Return empty list if file doesn't exist
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading general facts file '{self.general_facts_file}': {e}")
                return [] # Return empty list on error

    async def _save_general_facts(self, facts: List[str]):
        """Saves general facts (list of strings) to the JSON file safely."""
        async with self.general_facts_lock:
            try:
                # Ensure we only save up to the max limit
                facts_to_save = facts[-self.max_general_facts:]
                with open(self.general_facts_file, 'w', encoding='utf-8') as f:
                    json.dump(facts_to_save, f, indent=4)
            except IOError as e:
                print(f"Error saving general facts file '{self.general_facts_file}': {e}")

    # --- End General Fact Memory ---

    # --- End User Fact Memory ---


    # Tool implementation methods
    async def get_recent_messages(self, limit: int, channel_id: str = None) -> Dict[str, Any]:
        """Get recent messages from a Discord channel"""
        # Validate limit
        limit = min(max(1, limit), 100)  # Ensure limit is between 1 and 100

        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }

            # Get messages
            messages = []
            async for message in channel.history(limit=limit):
                messages.append({
                    "id": str(message.id),
                    "author": {
                        "id": str(message.author.id),
                        "name": message.author.name,
                        "display_name": message.author.display_name,
                        "bot": message.author.bot
                    },
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                    "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
                    "embeds": len(message.embeds) > 0
                })

            return {
                "channel": {
                    "id": str(channel.id),
                    "name": channel.name if hasattr(channel, 'name') else "DM Channel"
                },
                "messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "error": f"Error retrieving messages: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    async def search_user_messages(self, user_id: str, limit: int, channel_id: str = None) -> Dict[str, Any]:
        """Search for messages from a specific user"""
        # Validate limit
        limit = min(max(1, limit), 100)  # Ensure limit is between 1 and 100

        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }

            # Convert user_id to int
            try:
                user_id_int = int(user_id)
            except ValueError:
                return {
                    "error": f"Invalid user ID: {user_id}",
                    "timestamp": datetime.datetime.now().isoformat()
                }

            # Get messages from the user
            messages = []
            async for message in channel.history(limit=500):  # Check more messages to find enough from the user
                if message.author.id == user_id_int:
                    messages.append({
                        "id": str(message.id),
                        "author": {
                            "id": str(message.author.id),
                            "name": message.author.name,
                            "display_name": message.author.display_name,
                            "bot": message.author.bot
                        },
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
                        "embeds": len(message.embeds) > 0
                    })

                    if len(messages) >= limit:
                        break

            return {
                "channel": {
                    "id": str(channel.id),
                    "name": channel.name if hasattr(channel, 'name') else "DM Channel"
                },
                "user": {
                    "id": user_id,
                    "name": messages[0]["author"]["name"] if messages else "Unknown User"
                },
                "messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "error": f"Error searching user messages: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    async def search_messages_by_content(self, search_term: str, limit: int, channel_id: str = None) -> Dict[str, Any]:
        """Search for messages containing specific content"""
        # Validate limit
        limit = min(max(1, limit), 100)  # Ensure limit is between 1 and 100

        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }

            # Search for messages containing the search term
            messages = []
            search_term_lower = search_term.lower()
            async for message in channel.history(limit=500):  # Check more messages to find enough matches
                if search_term_lower in message.content.lower():
                    messages.append({
                        "id": str(message.id),
                        "author": {
                            "id": str(message.author.id),
                            "name": message.author.name,
                            "display_name": message.author.display_name,
                            "bot": message.author.bot
                        },
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
                        "embeds": len(message.embeds) > 0
                    })

                    if len(messages) >= limit:
                        break

            return {
                "channel": {
                    "id": str(channel.id),
                    "name": channel.name if hasattr(channel, 'name') else "DM Channel"
                },
                "search_term": search_term,
                "messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "error": f"Error searching messages by content: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    async def get_channel_info(self, channel_id: str = None) -> Dict[str, Any]:
        """Get information about a Discord channel"""
        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_id} not found",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
            else:
                # Use the channel from the current context if available
                channel = self.current_channel
                if not channel:
                    return {
                        "error": "No channel specified and no current channel context available",
                        "timestamp": datetime.datetime.now().isoformat()
                    }

            # Get channel information
            channel_info = {
                "id": str(channel.id),
                "type": str(channel.type),
                "timestamp": datetime.datetime.now().isoformat()
            }

            # Add guild-specific channel information if applicable
            if hasattr(channel, 'guild'):
                channel_info.update({
                    "name": channel.name,
                    "topic": channel.topic,
                    "position": channel.position,
                    "nsfw": channel.is_nsfw(),
                    "category": {
                        "id": str(channel.category_id) if channel.category_id else None,
                        "name": channel.category.name if channel.category else None
                    },
                    "guild": {
                        "id": str(channel.guild.id),
                        "name": channel.guild.name,
                        "member_count": channel.guild.member_count
                    }
                })
            elif hasattr(channel, 'recipient'):
                # DM channel
                channel_info.update({
                    "type": "DM",
                    "recipient": {
                        "id": str(channel.recipient.id),
                        "name": channel.recipient.name,
                        "display_name": channel.recipient.display_name
                    }
                })

            return channel_info

        except Exception as e:
            return {
                "error": f"Error getting channel information: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            }

    # --- New Tool Implementations ---

    async def get_conversation_context(self, message_count: int, channel_id: str = None) -> Dict[str, Any]:
        """Get the context of the current conversation in a channel"""
        # Validate message_count
        message_count = min(max(5, message_count), 50)

        try:
            # Get the channel
            if channel_id:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    return {"error": f"Channel with ID {channel_id} not found"}
            else:
                channel = self.current_channel
                if not channel:
                    return {"error": "No channel specified and no current channel context available"}

            # Retrieve messages from cache or history
            messages = []
            if channel.id in self.message_cache['by_channel']:
                messages = list(self.message_cache['by_channel'][channel.id])[-message_count:]
            else:
                async for msg in channel.history(limit=message_count):
                    messages.append(self._format_message(msg))
                messages.reverse() # History returns newest first

            return {
                "channel_id": str(channel.id),
                "channel_name": channel.name if hasattr(channel, 'name') else "DM Channel",
                "context_messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": f"Error getting conversation context: {str(e)}"}

    async def get_thread_context(self, thread_id: str, message_count: int) -> Dict[str, Any]:
        """Get the context of a thread conversation"""
        # Validate message_count
        message_count = min(max(5, message_count), 50)

        try:
            thread = self.bot.get_channel(int(thread_id))
            if not thread or not isinstance(thread, discord.Thread):
                return {"error": f"Thread with ID {thread_id} not found or is not a thread"}

            # Retrieve messages from cache or history
            messages = []
            if thread.id in self.message_cache['by_thread']:
                 messages = list(self.message_cache['by_thread'][thread.id])[-message_count:]
            else:
                async for msg in thread.history(limit=message_count):
                    messages.append(self._format_message(msg))
                messages.reverse() # History returns newest first

            return {
                "thread_id": str(thread.id),
                "thread_name": thread.name,
                "parent_channel_id": str(thread.parent_id),
                "context_messages": messages,
                "count": len(messages),
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": f"Error getting thread context: {str(e)}"}

    async def get_user_interaction_history(self, user_id_1: str, limit: int, user_id_2: str = None) -> Dict[str, Any]:
        """Get the history of interactions between two users (or user and bot)"""
        # Validate limit
        limit = min(max(1, limit), 50)
        user_id_1_int = int(user_id_1)
        user_id_2_int = int(user_id_2) if user_id_2 else self.bot.user.id

        try:
            # This is a simplified example. A real implementation would need
            # to search across multiple channels or use a dedicated interaction log.
            # We'll search the global cache for simplicity here.
            interactions = []
            for msg_data in list(self.message_cache['global_recent']):
                author_id = int(msg_data['author']['id'])
                mentioned_ids = [int(m['id']) for m in msg_data.get('mentions', [])]
                replied_to_author_id = int(msg_data.get('replied_to_author_id')) if msg_data.get('replied_to_author_id') else None

                is_interaction = False
                # Direct message between the two
                if (author_id == user_id_1_int and replied_to_author_id == user_id_2_int) or \
                   (author_id == user_id_2_int and replied_to_author_id == user_id_1_int):
                    is_interaction = True
                # Mention between the two
                elif (author_id == user_id_1_int and user_id_2_int in mentioned_ids) or \
                     (author_id == user_id_2_int and user_id_1_int in mentioned_ids):
                     is_interaction = True

                if is_interaction:
                    interactions.append(msg_data)
                    if len(interactions) >= limit:
                        break

            user1 = await self.bot.fetch_user(user_id_1_int)
            user2 = await self.bot.fetch_user(user_id_2_int)

            return {
                "user_1": {"id": str(user_id_1_int), "name": user1.name if user1 else "Unknown"},
                "user_2": {"id": str(user_id_2_int), "name": user2.name if user2 else "Unknown"},
                "interactions": interactions,
                "count": len(interactions),
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": f"Error getting user interaction history: {str(e)}"}

    async def get_conversation_summary(self, channel_id: str = None, message_limit: int = 25) -> Dict[str, Any]:
        """Generates and returns a summary of the recent conversation in a channel using an LLM call."""
        try:
            # Determine target channel ID
            target_channel_id_str = channel_id or (str(self.current_channel.id) if self.current_channel else None)
            if not target_channel_id_str:
                return {"error": "No channel specified and no current channel context available"}

            target_channel_id = int(target_channel_id_str)
            channel = self.bot.get_channel(target_channel_id)
            if not channel:
                return {"error": f"Channel with ID {target_channel_id_str} not found"}

            # --- Check Cache ---
            # Optional: Add timestamp check to invalidate stale summaries later if needed
            if target_channel_id in self.conversation_summaries:
                print(f"Returning cached summary for channel {target_channel_id}")
                return {
                    "channel_id": target_channel_id_str,
                    "summary": self.conversation_summaries[target_channel_id],
                    "source": "cache",
                    "timestamp": datetime.datetime.now().isoformat()
                }

            # --- Generate Summary ---
            print(f"Generating new summary for channel {target_channel_id}")
            if not self.api_key or not self.session:
                return {"error": "API key or session not available for summarization call."}

            # Fetch recent messages for summary context
            recent_messages_text = []
            try:
                async for msg in channel.history(limit=message_limit):
                    # Simple format: "DisplayName: Content"
                    recent_messages_text.append(f"{msg.author.display_name}: {msg.content}")
                recent_messages_text.reverse() # Oldest first
            except discord.Forbidden:
                return {"error": f"Missing permissions to read history in channel {target_channel_id_str}"}
            except Exception as hist_e:
                return {"error": f"Error fetching history for summary: {str(hist_e)}"}

            if not recent_messages_text:
                summary = "No recent messages found to summarize."
                self.conversation_summaries[target_channel_id] = summary # Cache empty summary
                return {
                    "channel_id": target_channel_id_str,
                    "summary": summary,
                    "source": "generated (empty)",
                    "timestamp": datetime.datetime.now().isoformat()
                }

            conversation_context = "\n".join(recent_messages_text)
            # Keep the summarization prompt concise
            summarization_prompt = f"Summarize the main points and current topic of this Discord chat snippet:\n\n---\n{conversation_context}\n---\n\nSummary:"

            # Prepare payload for summarization API call
            # Using the default model for now, could switch to a cheaper/faster one later
            summary_payload = {
                "model": self.default_model, # Consider a cheaper model for summaries
                "messages": [
                    {"role": "system", "content": "You are an assistant skilled at concisely summarizing conversation snippets."},
                    {"role": "user", "content": summarization_prompt}
                ],
                "temperature": 0.3, # Lower temperature for more factual summary
                "max_tokens": 150, # Limit summary length
                # No tools needed for summarization
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://discord-gurt-bot.example.com", # Optional but good practice
                "X-Title": "Gurt Discord Bot (Summarizer)" # Optional
            }

            summary = "Error generating summary." # Default error summary
            last_exception = None

            summary = "Error generating summary." # Default error summary
            try:
                # Use the new helper method for the API call (II.5)
                data = await self._call_llm_api_with_retry(
                    payload=summary_payload,
                    headers=headers,
                    timeout=self.summary_api_timeout,
                    request_desc=f"Summarization for channel {target_channel_id}"
                )

                # Process successful response
                if data.get("choices") and data["choices"][0].get("message"):
                    summary = data["choices"][0]["message"].get("content", "Failed to extract summary content.").strip()
                    print(f"Summary generated for {target_channel_id}: {summary[:100]}...")
                else:
                    summary = f"Unexpected summary API response format: {str(data)[:200]}"
                    print(f"Summarization Error (Channel {target_channel_id}): {summary}")

            except Exception as e:
                # Error is already printed within the helper method
                summary = f"Failed to generate summary for channel {target_channel_id} after retries. Last error: {str(e)}"
                # Optionally log traceback here if needed
                # import traceback
                # traceback.print_exc()

            # Cache the generated summary (even if it's an error message)
            self.conversation_summaries[target_channel_id] = summary

            return {
                "channel_id": target_channel_id_str,
                "summary": summary,
                "source": "generated",
                "timestamp": datetime.datetime.now().isoformat()
            }

        except Exception as e:
            error_msg = f"General error in get_conversation_summary tool: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return {"error": error_msg}


    async def get_message_context(self, message_id: str, before_count: int = 5, after_count: int = 5) -> Dict[str, Any]:
        """Get the context (messages before and after) around a specific message"""
        # Validate counts
        before_count = min(max(1, before_count), 25)
        after_count = min(max(1, after_count), 25)

        try:
            # Find the channel containing the message (this might require searching or assumptions)
            # For this example, we'll assume the message is in the current_channel if available
            target_message = None
            channel = self.current_channel

            if not channel:
                 # If no current channel, we might need to search guilds the bot is in.
                 # This is complex, so we'll return an error for now.
                 return {"error": "Cannot determine message channel without current context"}

            try:
                message_id_int = int(message_id)
                target_message = await channel.fetch_message(message_id_int)
            except discord.NotFound:
                return {"error": f"Message with ID {message_id} not found in channel {channel.id}"}
            except discord.Forbidden:
                return {"error": f"No permission to fetch message {message_id} in channel {channel.id}"}
            except ValueError:
                 return {"error": f"Invalid message ID format: {message_id}"}

            if not target_message:
                 return {"error": f"Message with ID {message_id} could not be fetched"}

            # Fetch messages before and after
            messages_before = []
            async for msg in channel.history(limit=before_count, before=target_message):
                messages_before.append(self._format_message(msg))
            messages_before.reverse() # History is newest first

            messages_after = []
            async for msg in channel.history(limit=after_count, after=target_message):
                 messages_after.append(self._format_message(msg))
            # messages_after is already oldest first

            return {
                "target_message": self._format_message(target_message),
                "messages_before": messages_before,
                "messages_after": messages_after,
                "channel_id": str(channel.id),
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": f"Error getting message context: {str(e)}"}

    def _format_message(self, message: discord.Message) -> Dict[str, Any]:
        """Helper function to format a discord.Message object into a dictionary"""
        formatted_msg = {
            "id": str(message.id),
            "author": {
                "id": str(message.author.id),
                "name": message.author.name,
                "display_name": message.author.display_name,
                "bot": message.author.bot
            },
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "attachments": [{"filename": a.filename, "url": a.url} for a in message.attachments],
            "embeds": len(message.embeds) > 0,
            "mentions": [{"id": str(m.id), "name": m.name} for m in message.mentions],
            "replied_to_message_id": None,
            "replied_to_author_id": None,
            "replied_to_author_name": None,
            "replied_to_content": None,
            "is_reply": False
        }

        # Add reply information if this message is a reply
        if message.reference and message.reference.message_id:
            formatted_msg["replied_to_message_id"] = str(message.reference.message_id)
            formatted_msg["is_reply"] = True

            # Try to get the referenced message if possible
            try:
                if hasattr(message.reference, "resolved") and message.reference.resolved:
                    ref_msg = message.reference.resolved
                    formatted_msg["replied_to_author_id"] = str(ref_msg.author.id)
                    formatted_msg["replied_to_author_name"] = ref_msg.author.display_name
                    formatted_msg["replied_to_content"] = ref_msg.content
            except Exception as e:
                print(f"Error getting referenced message details: {e}")

        return formatted_msg

    # --- End of New Tool Implementations ---

    async def process_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process tool calls from the AI and return the results"""
        tool_results = []

        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name")
            function_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))

            if function_name in self.tool_mapping:
                try:
                    result = await self.tool_mapping[function_name](**function_args)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": function_name,
                        "content": json.dumps(result)
                    })
                except Exception as e:
                    error_message = f"Error executing tool {function_name}: {str(e)}"
                    print(error_message)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": function_name,
                        "content": json.dumps({"error": error_message})
                    })
            else:
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "name": function_name,
                    "content": json.dumps({"error": f"Tool {function_name} not found"})
                })

        return tool_results


    # --- Helper Methods for get_ai_response (II.5 Refactoring) ---

    async def _build_dynamic_system_prompt(self, message: discord.Message) -> str:
        """Builds the system prompt string with dynamic context."""
        channel_id = message.channel.id
        user_id = message.author.id

        system_context_parts = [self.system_prompt] # Start with base prompt

        # Add current time
        now = datetime.datetime.now(datetime.timezone.utc)
        time_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
        day_str = now.strftime("%A")
        system_context_parts.append(f"\nCurrent time: {time_str} ({day_str}).")

        # Add current mood (I.1)
        # Check if mood needs updating
        if time.time() - self.last_mood_change > self.mood_change_interval:
            # Consider conversation sentiment when updating mood
            channel_sentiment = self.conversation_sentiment[channel_id]
            sentiment = channel_sentiment["overall"]
            intensity = channel_sentiment["intensity"]

            # Adjust mood options based on conversation sentiment
            if sentiment == "positive" and intensity > 0.7:
                mood_pool = ["excited", "enthusiastic", "playful", "creative", "wholesome"]
            elif sentiment == "positive":
                mood_pool = ["chill", "curious", "slightly hyper", "mischievous", "sassy", "playful"]
            elif sentiment == "negative" and intensity > 0.7:
                mood_pool = ["tired", "a bit bored", "skeptical", "sarcastic"]
            elif sentiment == "negative":
                mood_pool = ["tired", "a bit bored", "confused", "nostalgic", "distracted"]
            else:
                mood_pool = self.mood_options  # Use all options for neutral sentiment

            self.current_mood = random.choice(mood_pool)
            self.last_mood_change = time.time()
            print(f"Gurt mood changed to: {self.current_mood} (influenced by {sentiment} conversation)")

        system_context_parts.append(f"Your current mood is: {self.current_mood}. Let this subtly influence your tone and reactions.")

        # Add channel topic (with caching)
        channel_topic = None
        cached_topic = self.channel_topics_cache.get(channel_id)
        if cached_topic and time.time() - cached_topic["timestamp"] < self.channel_topic_cache_ttl:
            channel_topic = cached_topic["topic"]
        else:
            try:
                # Use the tool method directly for consistency
                channel_info_result = await self.get_channel_info(str(channel_id))
                if not channel_info_result.get("error"):
                    channel_topic = channel_info_result.get("topic")
                    # Cache even if topic is None to avoid refetching immediately
                    self.channel_topics_cache[channel_id] = {"topic": channel_topic, "timestamp": time.time()}
            except Exception as e:
                print(f"Error fetching channel topic for {channel_id}: {e}")
        if channel_topic:
            system_context_parts.append(f"Current channel topic: {channel_topic}")

        # Add active conversation topics
        channel_topics = self.active_topics.get(channel_id)
        if channel_topics and channel_topics["topics"]:
            # Get the top 3 active topics
            top_topics = sorted(channel_topics["topics"], key=lambda t: t["score"], reverse=True)[:3]
            topics_str = ", ".join([f"{t['topic']}" for t in top_topics])
            system_context_parts.append(f"Current conversation topics: {topics_str}.")

            # Check if the user has shown interest in any of these topics
            user_interests = channel_topics["user_topic_interests"].get(str(user_id), [])
            if user_interests:
                # Find overlap between active topics and user interests
                user_topic_names = [interest["topic"] for interest in user_interests]
                active_topic_names = [topic["topic"] for topic in top_topics]
                common_topics = set(user_topic_names).intersection(set(active_topic_names))

                if common_topics:
                    topics_str = ", ".join(common_topics)
                    system_context_parts.append(f"{message.author.display_name} has shown interest in these topics: {topics_str}.")

        # Add conversation sentiment context
        channel_sentiment = self.conversation_sentiment[channel_id]
        sentiment_str = f"The current conversation has a {channel_sentiment['overall']} tone"
        if channel_sentiment["intensity"] > 0.7:
            sentiment_str += " (strongly so)"
        elif channel_sentiment["intensity"] < 0.4:
            sentiment_str += " (mildly so)"

        if channel_sentiment["recent_trend"] != "stable":
            sentiment_str += f" and is {channel_sentiment['recent_trend']}"

        system_context_parts.append(sentiment_str + ".")

        # Add user sentiment if available
        user_sentiment = channel_sentiment["user_sentiments"].get(str(user_id))
        if user_sentiment:
            user_sentiment_str = f"{message.author.display_name}'s messages have a {user_sentiment['sentiment']} tone"
            if user_sentiment["intensity"] > 0.7:
                user_sentiment_str += " (strongly so)"
            system_context_parts.append(user_sentiment_str + ".")

        # Add conversation summary (II.1 enhancement)
        # Check cache first
        cached_summary = self.conversation_summaries.get(channel_id)
        # Potentially add a TTL check for summaries too if needed
        if cached_summary and not cached_summary.startswith("Error"):
             system_context_parts.append(f"Recent conversation summary: {cached_summary}")
        # Maybe trigger summary generation if none exists? Or rely on the tool call if AI needs it.

        # Add user interaction count hint
        interaction_count = self.user_relationships.get(user_id, {}).get(self.bot.user.id, 0)
        if interaction_count > 0:
             relationship_hint = "a few times" if interaction_count <= 5 else "quite a bit" if interaction_count <= 20 else "a lot"
             system_context_parts.append(f"You've interacted with {message.author.display_name} {relationship_hint} recently ({interaction_count} times).")

        # Add user facts (I.5)
        try:
            user_facts_data = await self._load_user_facts()
            user_facts = user_facts_data.get(str(user_id), [])
            if user_facts:
                facts_str = "; ".join(user_facts)
                system_context_parts.append(f"Remember about {message.author.display_name}: {facts_str}")
        except Exception as e:
            print(f"Error loading user facts for prompt injection: {e}")

        return "\n".join(system_context_parts)

    def _gather_conversation_context(self, channel_id: int, current_message_id: int) -> List[Dict[str, str]]:
        """Gathers and formats conversation history from cache for API context."""
        context_api_messages = []
        if channel_id in self.message_cache['by_channel']:
            # Get the last N messages, excluding the current one if it's already cached
            cached = list(self.message_cache['by_channel'][channel_id])
            # Ensure the current message isn't duplicated if caching happened before this call
            if cached and cached[-1]['id'] == str(current_message_id):
                cached = cached[:-1]
            context_messages_data = cached[-self.context_window_size:] # Use context_window_size

            # Format context messages for the API
            for msg_data in context_messages_data:
                role = "assistant" if msg_data['author']['id'] == str(self.bot.user.id) else "user"
                # Simplified content for context to save tokens
                content = f"{msg_data['author']['display_name']}: {msg_data['content']}"
                context_api_messages.append({"role": role, "content": content})
        return context_api_messages

    # --- API Call Helper (II.5) ---
    async def _call_llm_api_with_retry(self, payload: Dict[str, Any], headers: Dict[str, str], timeout: int, request_desc: str) -> Dict[str, Any]:
        """
        Calls the OpenRouter API with retry logic for specific errors.

        Args:
            payload: The JSON payload for the API request.
            headers: The request headers.
            timeout: Request timeout in seconds.
            request_desc: A description of the request for logging purposes.

        Returns:
            The JSON response data from the API.

        Raises:
            Exception: If the API call fails after all retry attempts or encounters a non-retryable error.
        """
        last_exception = None
        original_model = payload.get("model")
        using_fallback = False

        for attempt in range(self.api_retry_attempts):
            try:
                model_desc = "fallback model" if using_fallback else "primary model"
                print(f"Sending API request for {request_desc} using {model_desc} (Attempt {attempt + 1}/{self.api_retry_attempts})...")

                async with self.session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Basic format check
                        if "choices" not in data or not data["choices"] or "message" not in data["choices"][0]:
                            error_msg = f"Unexpected API response format for {request_desc}: {json.dumps(data)[:200]}"
                            print(error_msg)
                            last_exception = ValueError(error_msg) # Treat as non-retryable format error
                            break # Exit retry loop
                        print(f"API request successful for {request_desc}.")
                        return data # Success

                    elif response.status == 429:  # Rate limit error
                        error_text = await response.text()
                        error_msg = f"Rate limit error for {request_desc} (Status 429): {error_text[:200]}"
                        print(error_msg)

                        # If we're already using the fallback model, or if this isn't the default model request,
                        # just retry with the same model after a delay
                        if using_fallback or original_model != self.default_model:
                            if attempt < self.api_retry_attempts - 1:
                                wait_time = self.api_retry_delay * (attempt + 2)  # Longer wait for rate limits
                                print(f"Waiting {wait_time} seconds before retrying...")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                last_exception = Exception(error_msg)
                                break
                        else:
                            # Switch to fallback model
                            print(f"Switching from {self.default_model} to fallback model {self.fallback_model}")
                            payload["model"] = self.fallback_model
                            using_fallback = True
                            # No need to wait much since we're switching models
                            await asyncio.sleep(1)
                            continue

                    elif response.status >= 500: # Retry on server errors
                        error_text = await response.text()
                        error_msg = f"API server error for {request_desc} (Status {response.status}): {error_text[:100]}"
                        print(f"{error_msg} (Attempt {attempt + 1})")
                        last_exception = Exception(error_msg)
                        if attempt < self.api_retry_attempts - 1:
                            await asyncio.sleep(self.api_retry_delay * (attempt + 1))
                            continue # Go to next attempt
                        else:
                            break # Max retries reached
                    else: # Non-retryable client error (4xx) or other issue
                        error_text = await response.text()
                        error_msg = f"API client error for {request_desc} (Status {response.status}): {error_text[:200]}"
                        print(error_msg)

                        # If we get a 400-level error that might be model-specific and we're not using fallback yet
                        if response.status in (400, 404, 422) and not using_fallback and original_model == self.default_model:
                            print(f"Model-specific error. Switching to fallback model {self.fallback_model}")
                            payload["model"] = self.fallback_model
                            using_fallback = True
                            await asyncio.sleep(1)
                            continue

                        last_exception = Exception(error_msg)
                        break # Don't retry other client errors

            except asyncio.TimeoutError:
                error_msg = f"Request timed out for {request_desc} (Attempt {attempt + 1})"
                print(error_msg)
                last_exception = asyncio.TimeoutError(error_msg)
                if attempt < self.api_retry_attempts - 1:
                    await asyncio.sleep(self.api_retry_delay * (attempt + 1))
                    continue # Go to next attempt
                else:
                    break # Max retries reached
            except Exception as e:
                error_msg = f"Error during API call for {request_desc} (Attempt {attempt + 1}): {str(e)}"
                print(error_msg)
                last_exception = e
                # Decide if this exception is retryable (e.g., network errors)
                if attempt < self.api_retry_attempts - 1:
                     # Check for specific retryable exceptions if needed
                     await asyncio.sleep(self.api_retry_delay * (attempt + 1))
                     continue # Go to next attempt
                else:
                     # Log traceback on final attempt failure
                     # import traceback
                     # traceback.print_exc()
                     break # Max retries reached

        # If loop finishes without returning, raise the last encountered exception
        raise last_exception or Exception(f"API request failed for {request_desc} after {self.api_retry_attempts} attempts.")

    async def _get_memory_context(self, message: discord.Message) -> Optional[str]:
        """Retrieves relevant past interactions and facts to provide memory context."""
        channel_id = message.channel.id
        user_id = str(message.author.id)
        memory_parts = []

        # 1. Retrieve User Facts
        try:
            user_facts_data = await self.get_user_facts(user_id)
            if user_facts_data.get("facts"):
                facts_str = "; ".join(user_facts_data["facts"])
                memory_parts.append(f"Previously remembered facts about {message.author.display_name}: {facts_str}")
        except Exception as e:
            print(f"Error retrieving user facts for memory context: {e}")

        # 2. Retrieve Recent Interactions with the User in this Channel
        try:
            user_channel_messages = [
                msg for msg in self.message_cache['by_channel'].get(channel_id, [])
                if msg['author']['id'] == user_id
            ]
            if user_channel_messages:
                # Select a few recent messages from the user
                recent_user_msgs = user_channel_messages[-3:] # Get last 3
                msgs_str = "\n".join([f"- {m['content'][:80]} (at {m['created_at']})" for m in recent_user_msgs])
                memory_parts.append(f"Recent messages from {message.author.display_name} in this channel:\n{msgs_str}")
        except Exception as e:
            print(f"Error retrieving user channel messages for memory context: {e}")

        # 3. Retrieve Recent Bot Replies in this Channel
        try:
            bot_replies = list(self.message_cache['replied_to'].get(channel_id, []))
            if bot_replies:
                recent_bot_replies = bot_replies[-3:] # Get last 3 bot replies
                replies_str = "\n".join([f"- {m['content'][:80]} (at {m['created_at']})" for m in recent_bot_replies])
                memory_parts.append(f"Your (gurt's) recent replies in this channel:\n{replies_str}")
        except Exception as e:
            print(f"Error retrieving bot replies for memory context: {e}")

        # 4. Retrieve Conversation Summary (if recent and relevant)
        # Check cache first
        cached_summary = self.conversation_summaries.get(channel_id)
        # Add a TTL check if needed, e.g., summary older than 15 mins is less relevant
        if cached_summary and not cached_summary.startswith("Error"): # Add TTL check here if desired
             memory_parts.append(f"Summary of the ongoing conversation: {cached_summary}")

        # 5. Add information about active topics the user has engaged with
        try:
            channel_topics = self.active_topics.get(channel_id)
            if channel_topics:
                user_interests = channel_topics["user_topic_interests"].get(user_id, [])
                if user_interests:
                    # Sort by score to get most relevant interests
                    sorted_interests = sorted(user_interests, key=lambda x: x.get("score", 0), reverse=True)
                    top_interests = sorted_interests[:3]  # Get top 3 interests

                    interests_str = ", ".join([f"{interest['topic']} (score: {interest['score']:.2f})"
                                             for interest in top_interests])
                    memory_parts.append(f"{message.author.display_name}'s topic interests: {interests_str}")

                    # Add specific details about when they last discussed these topics
                    for interest in top_interests:
                        if "last_mentioned" in interest:
                            time_diff = time.time() - interest["last_mentioned"]
                            if time_diff < 3600:  # Within the last hour
                                minutes_ago = int(time_diff / 60)
                                memory_parts.append(f"They discussed '{interest['topic']}' about {minutes_ago} minutes ago.")
        except Exception as e:
            print(f"Error retrieving user topic interests for memory context: {e}")

        # 6. Add information about user's conversation patterns
        try:
            # Check if we have enough message history to analyze patterns
            user_messages = self.message_cache['by_user'].get(user_id, [])
            if len(user_messages) >= 5:
                # Analyze message length pattern
                avg_length = sum(len(msg["content"]) for msg in user_messages[-5:]) / 5

                # Analyze emoji usage
                emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]')
                emoji_count = sum(len(emoji_pattern.findall(msg["content"])) for msg in user_messages[-5:])

                # Analyze slang usage
                slang_words = ["ngl", "icl", "pmo", "ts", "bro", "vro", "bruh", "tuff", "kevin"]
                slang_count = 0
                for msg in user_messages[-5:]:
                    for word in slang_words:
                        if re.search(r'\b' + word + r'\b', msg["content"].lower()):
                            slang_count += 1

                # Create a communication style summary
                style_parts = []
                if avg_length < 20:
                    style_parts.append("very brief messages")
                elif avg_length < 50:
                    style_parts.append("concise messages")
                elif avg_length > 150:
                    style_parts.append("detailed/lengthy messages")

                if emoji_count > 5:
                    style_parts.append("frequent emoji use")
                elif emoji_count == 0:
                    style_parts.append("no emojis")

                if slang_count > 3:
                    style_parts.append("heavy slang usage")

                if style_parts:
                    memory_parts.append(f"Communication style: {', '.join(style_parts)}")
        except Exception as e:
            print(f"Error analyzing user communication patterns: {e}")

        # 7. Add sentiment analysis of user's recent messages
        try:
            channel_sentiment = self.conversation_sentiment[channel_id]
            user_sentiment = channel_sentiment["user_sentiments"].get(user_id)
            if user_sentiment:
                sentiment_desc = f"{user_sentiment['sentiment']} tone"
                if user_sentiment["intensity"] > 0.7:
                    sentiment_desc += " (strongly so)"
                elif user_sentiment["intensity"] < 0.4:
                    sentiment_desc += " (mildly so)"

                memory_parts.append(f"Recent message sentiment: {sentiment_desc}")
        except Exception as e:
            print(f"Error retrieving user sentiment for memory context: {e}")

        # --- DUPLICATE BLOCK REMOVED ---

        if not memory_parts:
            return None

        # Combine memory parts into a single string for the system prompt
        memory_context_str = "--- Memory Context ---\n" + "\n\n".join(memory_parts) + "\n--- End Memory Context ---"
        return memory_context_str


    async def get_ai_response(self, message: discord.Message, model: Optional[str] = None) -> Dict[str, Any]:
        """Get a response from the OpenRouter API with decision on whether to respond"""
        if not self.api_key:
            return {"should_respond": False, "content": None, "react_with_emoji": None, "error": "OpenRouter API key not configured"}

        # Store the current channel for context in tools
        self.current_channel = message.channel
        channel_id = message.channel.id
        user_id = message.author.id

        # --- Build Prompt Components using Helpers (II.5) ---
        final_system_prompt = await self._build_dynamic_system_prompt(message)
        conversation_context_messages = self._gather_conversation_context(channel_id, message.id)

        # Enhance context with memory of past interactions
        memory_context = await self._get_memory_context(message)

        # Create messages array
        messages = [{"role": "system", "content": final_system_prompt}]

        # Add memory context if available
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        # Add JSON reminder if needed
        if self.needs_json_reminder:
            reminder_message = {
                "role": "system",
                "content": "**CRITICAL REMINDER:** Your previous response did not follow the required JSON format. You MUST respond ONLY with a valid JSON object matching the specified schema. Do NOT include any other text, explanations, or markdown formatting outside the JSON structure."
            }
            messages.append(reminder_message)
            print("Added JSON format reminder message.")
            self.needs_json_reminder = False # Reset the flag

        messages.extend(conversation_context_messages)

        # Prepare context about the *current* message
        # Check if this is a reply to the bot
        replied_to_bot = False
        if hasattr(message, 'reference') and message.reference and message.reference.message_id:
            try:
                # Try to get the message being replied to
                replied_to_message = await message.channel.fetch_message(message.reference.message_id)
                if replied_to_message.author.id == self.bot.user.id:
                    replied_to_bot = True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                # Message not found or can't be accessed
                pass

        current_message_context = {
            "message_author": message.author.display_name,
            "message_author_id": str(message.author.id),
            "message_content": message.content,
            "channel_name": message.channel.name if hasattr(message.channel, 'name') else "DM",
            "channel_id": str(message.channel.id),
            "guild_name": message.guild.name if message.guild else "DM",
            "guild_id": str(message.guild.id) if message.guild else None,
            "bot_mentioned": self.bot.user.mentioned_in(message),
            "replied_to_bot": replied_to_bot,
            "timestamp": message.created_at.isoformat()
        }

        # --- Prepare the current message content (potentially multimodal) ---
        current_message_content_parts = []

        # Add the text part
        text_content = f"{current_message_context['message_author']}: {current_message_context['message_content']}"
        current_message_content_parts.append({"type": "text", "text": text_content})

        # Add image parts if attachments exist
        if message.attachments:
            print(f"Processing {len(message.attachments)} attachments for message {message.id}")
            for attachment in message.attachments:
                # Basic check for image content type
                content_type = attachment.content_type
                if content_type and content_type.startswith("image/"):
                    try:
                        print(f"Downloading image: {attachment.filename} ({content_type})")
                        image_bytes = await attachment.read()
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        # Ensure the MIME type is correctly formatted for the data URL
                        mime_type = content_type.split(';')[0] # Get only the type/subtype part
                        image_url = f"data:{mime_type};base64,{base64_image}"

                        current_message_content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        })
                        print(f"Added image {attachment.filename} to payload.")
                    except discord.HTTPException as e:
                        print(f"Failed to download image {attachment.filename}: {e}")
                    except Exception as e:
                        print(f"Error processing image {attachment.filename}: {e}")
                else:
                    print(f"Skipping non-image attachment: {attachment.filename} ({content_type})")

        # Add the potentially multimodal content to the messages list
        # If only text, API expects a string; if multimodal, expects a list of parts.
        if len(current_message_content_parts) == 1 and current_message_content_parts[0]["type"] == "text":
            messages.append({"role": "user", "content": current_message_content_parts[0]["text"]})
            print("Appended text-only content to messages.")
        elif len(current_message_content_parts) > 1:
            messages.append({"role": "user", "content": current_message_content_parts})
            print("Appended multimodal content (text + images) to messages.")
        else:
            # Should not happen if text is always added, but as a safeguard
            print("Warning: No content parts generated for user message.")
            messages.append({"role": "user", "content": ""}) # Append empty content if something went wrong

        # --- Add final instruction for the AI ---
        # Check if we have learned message length preferences for this channel
        message_length_guidance = ""
        if hasattr(self, 'channel_message_length') and channel_id in self.channel_message_length:
            length_factor = self.channel_message_length[channel_id]
            if length_factor < 0.3:
                message_length_guidance = " Keep your response brief and to the point, as people in this channel tend to use short messages."
            elif length_factor > 0.7:
                message_length_guidance = " You can be a bit more detailed in your response, as people in this channel tend to write longer messages."

        messages.append({
            "role": "user",
            "content": f"Given the preceding conversation context and the last message, decide if you (gurt) should respond. **ABSOLUTELY CRITICAL: Your response MUST consist *only* of the raw JSON object itself, with NO additional text, explanations, or markdown formatting (like \\`\\`\\`json ... \\`\\`\\`) surrounding it. The entire response must be *just* the JSON matching this schema:**\n\n{{{{\n  \"should_respond\": boolean,\n  \"content\": string,\n  \"react_with_emoji\": string | null\n}}}}\n\n**Ensure there is absolutely nothing before or after the JSON object.**{message_length_guidance}"
        })

        # Prepare the request payload
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "tools": self.tools,
            "temperature": 0.75, # Slightly increased temperature for more variety
            "max_tokens": 1500, # Increased slightly for potential image analysis overhead
            # "frequency_penalty": 0.2, # Removed: Not supported by Gemini Flash
            # "presence_penalty": 0.1, # Removed: Not supported by Gemini Flash
            # Note: Models supporting image input might have different requirements or limitations.
            # Ensure the selected model (self.default_model) actually supports multimodal input.
            # "response_format": { # Commented out again due to conflict with tools/function calling
            #     "type": "json_schema",
            #     "json_schema": self.response_schema
            # }
        }

        # Debug the request payload
        #print(f"API Request Payload: {json.dumps(payload, indent=2)}")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://discord-gurt-bot.example.com",
            "X-Title": "Gurt Discord Bot"
        }

        try:
            # Make the initial API request using the helper (II.5)
            data = await self._call_llm_api_with_retry(
                payload=payload,
                headers=headers,
                timeout=self.api_timeout,
                request_desc=f"Initial response for message {message.id}"
            )

            print(f"Raw API Response: {json.dumps(data, indent=2)}")
            ai_message = data["choices"][0]["message"]
            messages.append(ai_message) # Add AI response for potential tool use context

            final_response_text = None
            response_data = None

            # Process tool calls if present
            if "tool_calls" in ai_message and ai_message["tool_calls"]:
                tool_results = await self.process_tool_calls(ai_message["tool_calls"])
                messages.extend(tool_results)
                payload["messages"] = messages # Update payload for follow-up

                # Make follow-up request using the helper (II.5)
                follow_up_data = await self._call_llm_api_with_retry(
                    payload=payload,
                    headers=headers,
                    timeout=self.api_timeout, # Use same timeout for follow-up
                    request_desc=f"Follow-up response for message {message.id} after tool use"
                )
                # --- START FIX for KeyError after tool use ---
                follow_up_message = follow_up_data["choices"][0].get("message", {})
                if "content" in follow_up_message:
                    final_response_text = follow_up_message["content"]
                else:
                    # Handle missing content after tool use
                    error_msg = f"AI response after tool use lacked 'content' field. Message: {json.dumps(follow_up_message)}"
                    print(f"Warning: {error_msg}")
                    # Set to None to trigger fallback logic later
                    final_response_text = None
                # --- END FIX ---

            else: # No tool calls
                ai_message = data["choices"][0]["message"] # Ensure ai_message is defined here too
                if "content" in ai_message:
                    final_response_text = ai_message["content"]
                else:
                     # This case should be handled by the format check in _call_llm_api_with_retry
                     # but adding a safeguard here.
                     # If content is missing in the *first* response and no tools were called, raise error.
                     raise ValueError(f"No content in initial AI message and no tool calls: {json.dumps(ai_message)}")


            # --- Parse Final Response ---
            response_data = None
            if final_response_text is not None: # Only parse if we have text
                try:
                    # Attempt 1: Try parsing the whole string as JSON
                    response_data = json.loads(final_response_text)
                    print("Successfully parsed entire response as JSON.")
                    self.needs_json_reminder = False # Success, no reminder needed next time
                except json.JSONDecodeError:
                    print("Response is not valid JSON. Attempting to extract JSON object with regex...")
                    response_data = None # Ensure response_data is None before extraction attempt
                    # Attempt 2: Try extracting JSON object using aggressive regex (find outermost braces)
                    json_match = re.search(r'\{.*\}', final_response_text, re.DOTALL)

                    if json_match:
                        json_str = json_match.group(0) # Get the full match between outermost braces
                        try:
                            response_data = json.loads(json_str)
                            print("Successfully extracted and parsed JSON object using aggressive regex.")
                            self.needs_json_reminder = False # Success, no reminder needed next time
                        except json.JSONDecodeError as e:
                            print(f"Aggressive regex found text between braces, but it failed to parse as JSON: {e}")
                            # Fall through to set reminder and use fallback logic
                    else:
                        print("Could not extract JSON object using aggressive regex.")
                        # Fall through to set reminder and use fallback logic

                    # If parsing and extraction both failed
                    if response_data is None:
                        print("Could not parse or extract JSON. Setting reminder flag.")
                        self.needs_json_reminder = True # Set flag for next call

                        # Fallback: Treat as plain text, decide based on mention/context AND content plausibility
                        print("Treating as plain text fallback.")
                        clean_text = final_response_text.strip()
                        # Check if it looks like a plausible chat message (short, no obvious JSON/error structures)
                        is_plausible_chat = len(clean_text) > 0 and len(clean_text) < 300 and not clean_text.startswith('{') and 'error' not in clean_text.lower()

                        # If mentioned/replied to OR if it looks like a plausible chat message, send it
                        if self.bot.user.mentioned_in(message) or replied_to_bot or is_plausible_chat:
                            response_data = {
                        "should_respond": True,
                        "content": clean_text or "...", # Use cleaned text or placeholder
                        "react_with_emoji": None,
                        "note": "Fallback response due to non-JSON content"
                    }
                    print(f"Fallback response generated: {response_data}")
                else:
                    # If not mentioned/replied to and response isn't JSON, assume no response intended
                    response_data = {
                        "should_respond": False,
                        "content": None,
                        "react_with_emoji": None,
                        "note": "No response intended (non-JSON content)"
                    }
                    print("No response intended (non-JSON content).")

            # --- Process Parsed/Fallback Data ---
            if response_data: # This check remains the same
                # Ensure default keys exist
                response_data.setdefault("should_respond", False)
                response_data.setdefault("content", None)
                response_data.setdefault("react_with_emoji", None)

                # --- Cache Bot Response ---
                if response_data.get("should_respond") and response_data.get("content"):
                    self.bot_last_spoke[channel_id] = time.time()
                    bot_response_cache_entry = {
                        "id": f"bot_{message.id}", "author": {"id": str(self.bot.user.id), "name": self.bot.user.name, "display_name": self.bot.user.display_name, "bot": True},
                        "content": response_data.get("content", ""), "created_at": datetime.datetime.now().isoformat(),
                        "attachments": [], "embeds": False, "mentions": [], "replied_to_message_id": str(message.id)
                    }
                    self.message_cache['by_channel'][channel_id].append(bot_response_cache_entry)
                    self.message_cache['global_recent'].append(bot_response_cache_entry)
                    self.message_cache['replied_to'][channel_id].append(bot_response_cache_entry)
                # --- End Cache Bot Response ---

                # Ensure all expected keys are present (redundant but safe after removing duplicate block)
                # The setdefault calls were already done once above.
                # response_data.setdefault("should_respond", False) # Redundant
                # response_data.setdefault("content", None) # Redundant
                # response_data.setdefault("react_with_emoji", None) # Redundant

                return response_data
            else: # Handle case where final_response_text was None or parsing/fallback failed
                print("Warning: response_data is None after parsing/fallback attempts.")
                # Decide on default behavior if response_data couldn't be determined
                if self.bot.user.mentioned_in(message) or replied_to_bot:
                    # If mentioned/replied to, maybe send a generic error/confusion message
                     return {
                        "should_respond": True, "content": "...", # Placeholder for confusion
                        "react_with_emoji": "❓", # React with question mark
                        "note": "Fallback due to inability to parse or generate response"
                    }
                else:
                    # Otherwise, stay silent
                    return {"should_respond": False, "content": None, "react_with_emoji": None, "note": "No response generated (parsing/fallback failed)"}

        except Exception as e: # Catch broader errors including API call failures, etc.
            # Catch errors from _call_llm_api_with_retry or other issues
            error_message = f"Error getting AI response for message {message.id}: {str(e)}"
            print(error_message)
            # Optionally log traceback here
            # import traceback
            # traceback.print_exc()

            # Fallback for mentions if a major error occurred
            if self.bot.user.mentioned_in(message) or replied_to_bot:
                return {
                    "should_respond": True, "content": "...", # Placeholder for error
                    "react_with_emoji": "❓", # React with question mark
                    "note": f"Fallback response due to error: {error_message}"
                }
            else:
                # If not mentioned and error occurred, don't respond
                return {"should_respond": False, "content": None, "react_with_emoji": None, "error": error_message}


    # --- Helper Methods for get_ai_response (II.5 Refactoring) ---

    async def _build_dynamic_system_prompt(self, message: discord.Message) -> str:
        """Builds the system prompt string with dynamic context."""
        channel_id = message.channel.id
        user_id = message.author.id

        system_context_parts = [self.system_prompt] # Start with base prompt

        # Add current time
        now = datetime.datetime.now(datetime.timezone.utc)
        time_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
        day_str = now.strftime("%A")
        system_context_parts.append(f"\nCurrent time: {time_str} ({day_str}).")

        # Add current mood (I.1)
        # Check if mood needs updating
        if time.time() - self.last_mood_change > self.mood_change_interval:
            # Consider conversation sentiment when updating mood
            channel_sentiment = self.conversation_sentiment[channel_id]
            sentiment = channel_sentiment["overall"]
            intensity = channel_sentiment["intensity"]

            # Adjust mood options based on conversation sentiment
            if sentiment == "positive" and intensity > 0.7:
                mood_pool = ["excited", "enthusiastic", "playful", "creative", "wholesome"]
            elif sentiment == "positive":
                mood_pool = ["chill", "curious", "slightly hyper", "mischievous", "sassy", "playful"]
            elif sentiment == "negative" and intensity > 0.7:
                mood_pool = ["tired", "a bit bored", "skeptical", "sarcastic"]
            elif sentiment == "negative":
                mood_pool = ["tired", "a bit bored", "confused", "nostalgic", "distracted"]
            else:
                mood_pool = self.mood_options  # Use all options for neutral sentiment

            self.current_mood = random.choice(mood_pool)
            self.last_mood_change = time.time()
            print(f"Gurt mood changed to: {self.current_mood} (influenced by {sentiment} conversation)")
        system_context_parts.append(f"Your current mood is: {self.current_mood}. Let this subtly influence your tone and reactions.")

        # Add channel topic (with caching)
        channel_topic = None
        cached_topic = self.channel_topics_cache.get(channel_id)
        if cached_topic and time.time() - cached_topic["timestamp"] < self.channel_topic_cache_ttl:
            channel_topic = cached_topic["topic"]
        else:
            try:
                # Use the tool method directly for consistency
                channel_info_result = await self.get_channel_info(str(channel_id))
                if not channel_info_result.get("error"):
                    channel_topic = channel_info_result.get("topic")
                    # Cache even if topic is None to avoid refetching immediately
                    self.channel_topics_cache[channel_id] = {"topic": channel_topic, "timestamp": time.time()}
            except Exception as e:
                print(f"Error fetching channel topic for {channel_id}: {e}")
        if channel_topic:
            system_context_parts.append(f"Current channel topic: {channel_topic}")

        # Add conversation summary (II.1 enhancement)
        # Check cache first
        cached_summary = self.conversation_summaries.get(channel_id)
        # Potentially add a TTL check for summaries too if needed
        if cached_summary and not cached_summary.startswith("Error"):
             system_context_parts.append(f"Recent conversation summary: {cached_summary}")
        # Maybe trigger summary generation if none exists? Or rely on the tool call if AI needs it.

        # Add user interaction count hint
        interaction_count = self.user_relationships.get(user_id, {}).get(self.bot.user.id, 0)
        if interaction_count > 0:
             relationship_hint = "a few times" if interaction_count <= 5 else "quite a bit" if interaction_count <= 20 else "a lot"
             system_context_parts.append(f"You've interacted with {message.author.display_name} {relationship_hint} recently ({interaction_count} times).")

        # Add user facts (I.5)
        try:
            user_facts_data = await self._load_user_facts()
            user_facts = user_facts_data.get(str(user_id), [])
            if user_facts:
                facts_str = "; ".join(user_facts)
                system_context_parts.append(f"Remember about {message.author.display_name}: {facts_str}")
        except Exception as e:
            print(f"Error loading user facts for prompt injection: {e}")

        return "\n".join(system_context_parts)

    def _gather_conversation_context(self, channel_id: int, current_message_id: int) -> List[Dict[str, str]]:
        """Gathers and formats conversation history from cache for API context."""
        context_api_messages = []
        if channel_id in self.message_cache['by_channel']:
            # Get the last N messages, excluding the current one if it's already cached
            cached = list(self.message_cache['by_channel'][channel_id])
            # Ensure the current message isn't duplicated if caching happened before this call
            if cached and cached[-1]['id'] == str(current_message_id):
                cached = cached[:-1]
            context_messages_data = cached[-self.context_window_size:] # Use context_window_size

            # Format context messages for the API
            for msg_data in context_messages_data:
                role = "assistant" if msg_data['author']['id'] == str(self.bot.user.id) else "user"
                # Simplified content for context to save tokens
                content = f"{msg_data['author']['display_name']}: {msg_data['content']}"
                context_api_messages.append({"role": role, "content": content})
        return context_api_messages

    # --- API Call Helper (II.5) ---
    async def _call_llm_api_with_retry(self, payload: Dict[str, Any], headers: Dict[str, str], timeout: int, request_desc: str) -> Dict[str, Any]:
        """
        Calls the OpenRouter API with retry logic for specific errors.

        Args:
            payload: The JSON payload for the API request.
            headers: The request headers.
            timeout: Request timeout in seconds.
            request_desc: A description of the request for logging purposes.

        Returns:
            The JSON response data from the API.

        Raises:
            Exception: If the API call fails after all retry attempts or encounters a non-retryable error.
        """
        last_exception = None
        for attempt in range(self.api_retry_attempts):
            try:
                print(f"Sending API request for {request_desc} (Attempt {attempt + 1}/{self.api_retry_attempts})...")
                async with self.session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Basic format check
                        if "choices" not in data or not data["choices"] or "message" not in data["choices"][0]:
                            error_msg = f"Unexpected API response format for {request_desc}: {json.dumps(data)[:200]}"
                            print(error_msg)
                            last_exception = ValueError(error_msg) # Treat as non-retryable format error
                            break # Exit retry loop
                        print(f"API request successful for {request_desc}.")
                        return data # Success

                    elif response.status >= 500: # Retry on server errors
                        error_text = await response.text()
                        error_msg = f"API server error for {request_desc} (Status {response.status}): {error_text[:100]}"
                        print(f"{error_msg} (Attempt {attempt + 1})")
                        last_exception = Exception(error_msg)
                        if attempt < self.api_retry_attempts - 1:
                            await asyncio.sleep(self.api_retry_delay * (attempt + 1))
                            continue # Go to next attempt
                        else:
                            break # Max retries reached
                    else: # Non-retryable client error (4xx) or other issue
                        error_text = await response.text()
                        error_msg = f"API client error for {request_desc} (Status {response.status}): {error_text[:200]}"
                        print(error_msg)
                        last_exception = Exception(error_msg)
                        break # Don't retry client errors

            except asyncio.TimeoutError:
                error_msg = f"Request timed out for {request_desc} (Attempt {attempt + 1})"
                print(error_msg)
                last_exception = asyncio.TimeoutError(error_msg)
                if attempt < self.api_retry_attempts - 1:
                    await asyncio.sleep(self.api_retry_delay * (attempt + 1))
                    continue # Go to next attempt
                else:
                    break # Max retries reached
            except Exception as e:
                error_msg = f"Error during API call for {request_desc} (Attempt {attempt + 1}): {str(e)}"
                print(error_msg)
                last_exception = e
                # Decide if this exception is retryable (e.g., network errors)
                if attempt < self.api_retry_attempts - 1:
                     # Check for specific retryable exceptions if needed
                     await asyncio.sleep(self.api_retry_delay * (attempt + 1))
                     continue # Go to next attempt
                else:
                     # Log traceback on final attempt failure
                     # import traceback
                     # traceback.print_exc()
                     break # Max retries reached

        # This block executes if the loop completes without returning (all attempts failed)
        # or if it breaks due to a non-retryable error.
        if last_exception is not None:
            # An exception was recorded during the attempts. Raise it.
            raise last_exception
        else:
            # The loop finished all attempts, but no specific exception was stored.
            # This indicates failure after all retries without a clear error cause being caught.
            raise Exception(f"API request failed for {request_desc} after {self.api_retry_attempts} attempts. No specific exception was captured.")

    # Note: _extract_json_from_text and _cleanup_non_json_text were removed as JSON parsing is now handled differently within get_ai_response.

    def _create_human_like_mistake(self, text: str) -> Tuple[str, Optional[str]]:
        """
        Creates a human-like mistake in the given text and returns both the mistaken text
        and a potential correction message.

        Args:
            text: The original text to add a mistake to

        Returns:
            A tuple of (text_with_mistake, correction_message)
        """
        # Don't make mistakes in very short messages
        if len(text) < 10:
            return text, None

        # Choose a mistake type based on randomness
        mistake_types = [
            "typo",           # Simple character typo
            "autocorrect",    # Word replaced with similar word (like autocorrect)
            "send_too_soon",  # Message sent before finished typing
            "wrong_word",     # Using the wrong word entirely
            "grammar"         # Grammar mistake
        ]

        # Weight mistake types based on personality randomness
        weights = [
            0.5,             # typo (most common)
            0.2,             # autocorrect
            0.15,            # send_too_soon
            0.1,             # wrong_word
            0.05             # grammar
        ]

        mistake_type = random.choices(mistake_types, weights=weights, k=1)[0]

        # Split text into words for easier manipulation
        words = text.split()
        if not words:
            return text, None

        # Choose a random position for the mistake
        # Avoid the very beginning and end for more natural mistakes
        if len(words) <= 3:
            pos = random.randint(0, len(words) - 1)
        else:
            pos = random.randint(1, len(words) - 2)

        # Make different types of mistakes
        if mistake_type == "typo":
            # Simple character typo
            if len(words[pos]) <= 2:
                # Word too short, choose another
                if len(words) > 1:
                    pos = (pos + 1) % len(words)

            if len(words[pos]) > 2:
                char_pos = random.randint(0, len(words[pos]) - 1)

                # Different typo subtypes
                typo_type = random.choice(["swap", "double", "missing", "extra", "nearby"])

                if typo_type == "swap" and char_pos < len(words[pos]) - 1:
                    # Swap two adjacent characters
                    chars = list(words[pos])
                    chars[char_pos], chars[char_pos + 1] = chars[char_pos + 1], chars[char_pos]
                    words[pos] = ''.join(chars)

                elif typo_type == "double" and char_pos < len(words[pos]):
                    # Double a character
                    chars = list(words[pos])
                    chars.insert(char_pos, chars[char_pos])
                    words[pos] = ''.join(chars)

                elif typo_type == "missing" and len(words[pos]) > 3:
                    # Remove a character
                    chars = list(words[pos])
                    chars.pop(char_pos)
                    words[pos] = ''.join(chars)

                elif typo_type == "extra" and char_pos < len(words[pos]):
                    # Add a random character
                    extra_char = random.choice("abcdefghijklmnopqrstuvwxyz")
                    chars = list(words[pos])
                    chars.insert(char_pos, extra_char)
                    words[pos] = ''.join(chars)

                elif typo_type == "nearby":
                    # Replace with a nearby key on keyboard
                    nearby_keys = {
                        'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx', 'e': 'wrsdf',
                        'f': 'drtgvc', 'g': 'ftyhbv', 'h': 'gyujnb', 'i': 'uojkl', 'j': 'huikmn',
                        'k': 'jiolm', 'l': 'kop;', 'm': 'njk,', 'n': 'bhjm', 'o': 'iklp',
                        'p': 'ol;[', 'q': 'asw', 'r': 'edft', 's': 'awedxz', 't': 'rfgy',
                        'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu',
                        'z': 'asx'
                    }

                    if char_pos < len(words[pos]) and words[pos][char_pos].lower() in nearby_keys:
                        chars = list(words[pos])
                        original_char = chars[char_pos].lower()
                        replacement = random.choice(nearby_keys[original_char])

                        # Preserve case
                        if chars[char_pos].isupper():
                            replacement = replacement.upper()

                        chars[char_pos] = replacement
                        words[pos] = ''.join(chars)

            # Create correction message
            original_word = text.split()[pos]
            correction = f"*{original_word}"

        elif mistake_type == "autocorrect":
            # Replace word with a similar word (like autocorrect)
            autocorrect_pairs = [
                ("there", "their"), ("their", "there"), ("they're", "there"),
                ("your", "you're"), ("you're", "your"), ("its", "it's"), ("it's", "its"),
                ("were", "we're"), ("we're", "were"), ("than", "then"), ("then", "than"),
                ("affect", "effect"), ("effect", "affect"), ("accept", "except"), ("except", "accept"),
                ("to", "too"), ("too", "to"), ("two", "too"), ("lose", "loose"), ("loose", "lose")
            ]

            # Find a suitable word to replace
            for i, word in enumerate(words):
                for pair in autocorrect_pairs:
                    if word.lower() == pair[0].lower():
                        # Found a match, replace it
                        original_word = words[i]
                        words[i] = pair[1]
                        if original_word[0].isupper():
                            words[i] = words[i].capitalize()

                        # Create correction message
                        correction = f"*{original_word}"
                        break
                else:
                    continue
                break
            else:
                # No suitable word found, fall back to typo
                return self._create_human_like_mistake(text)

        elif mistake_type == "send_too_soon":
            # Cut off the message as if sent too soon
            cutoff_point = random.randint(len(text) // 3, len(text) * 2 // 3)
            mistaken_text = text[:cutoff_point]

            # Create correction message - send the full message
            correction = text

            # Return early since we're not using the words list
            return mistaken_text, correction

        elif mistake_type == "wrong_word":
            # Use a completely wrong word
            wrong_word_pairs = [
                ("happy", "hungry"), ("sad", "mad"), ("good", "food"), ("bad", "dad"),
                ("love", "live"), ("hate", "have"), ("big", "bag"), ("small", "smell"),
                ("fast", "last"), ("slow", "snow"), ("hot", "hit"), ("cold", "gold"),
                ("new", "now"), ("old", "odd"), ("high", "hide"), ("low", "law")
            ]

            # Find a suitable word to replace
            for i, word in enumerate(words):
                for pair in wrong_word_pairs:
                    if word.lower() == pair[0].lower():
                        # Found a match, replace it
                        original_word = words[i]
                        words[i] = pair[1]
                        if original_word[0].isupper():
                            words[i] = words[i].capitalize()

                        # Create correction message
                        correction = f"*{original_word}"
                        break
                else:
                    continue
                break
            else:
                # No suitable word found, fall back to typo
                return self._create_human_like_mistake(text)

        elif mistake_type == "grammar":
            # Make a grammar mistake
            grammar_mistakes = [
                # Missing apostrophe
                (r'\b(can)not\b', r'\1t'),
                (r'\b(do)n\'t\b', r'\1nt'),
                (r'\b(is)n\'t\b', r'\1nt'),
                (r'\b(was)n\'t\b', r'\1nt'),
                (r'\b(did)n\'t\b', r'\1nt'),
                # Wrong verb form
                (r'\bam\b', r'is'),
                (r'\bare\b', r'is'),
                (r'\bwas\b', r'were'),
                (r'\bwere\b', r'was'),
                # Wrong article
                (r'\ba ([aeiou])', r'an \1'),
                (r'\ban ([^aeiou])', r'a \1')
            ]

            # Join words back to text for regex replacement
            text_with_mistake = ' '.join(words)

            # Try each grammar mistake pattern
            for pattern, replacement in grammar_mistakes:
                if re.search(pattern, text_with_mistake, re.IGNORECASE):
                    # Apply the first matching grammar mistake
                    original_text = text_with_mistake
                    text_with_mistake = re.sub(pattern, replacement, text_with_mistake, count=1, flags=re.IGNORECASE)

                    # If we made a change, return it
                    if text_with_mistake != original_text:
                        # Create correction message - the correct grammar
                        correction = f"*{original_text}"
                        return text_with_mistake, correction

            # No grammar mistake applied, fall back to typo
            return self._create_human_like_mistake(text)

        # Join words back into text
        text_with_mistake = ' '.join(words)

        # Randomly decide if we should send a correction
        should_correct = random.random() < 0.8  # 80% chance to correct mistakes

        if should_correct:
            return text_with_mistake, correction
        else:
            # No correction
            return text_with_mistake, None

    async def _simulate_human_typing(self, channel, text: str):
        """
        Simulates realistic human typing behavior with variable speeds, pauses, typos, and corrections.
        This creates a much more human-like typing experience than simply waiting a fixed amount of time.

        Args:
            channel: The Discord channel to simulate typing in
            text: The final text to be sent
        """
        # Define typing characteristics based on personality and mood
        base_char_delay = random.uniform(0.05, 0.12)  # Base delay between characters

        # Adjust typing speed based on conversation dynamics if available
        channel_id = channel.id
        if hasattr(self, 'channel_response_timing') and channel_id in self.channel_response_timing:
            # Use the learned response timing for this channel
            response_factor = self.channel_response_timing[channel_id]
            # Apply the factor with some randomness
            base_char_delay *= response_factor * random.uniform(0.85, 1.15)
            print(f"Adjusting typing speed based on channel dynamics (factor: {response_factor:.2f})")

        # Adjust typing speed based on mood
        if self.current_mood in ["excited", "slightly hyper"]:
            base_char_delay *= 0.7  # Type faster when excited
        elif self.current_mood in ["tired", "a bit bored"]:
            base_char_delay *= 1.3  # Type slower when tired

        # Typo probability based on personality traits
        typo_probability = 0.02 * (0.5 + self.personality_traits["randomness"])

        # Define common typo patterns
        nearby_keys = {
            'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx', 'e': 'wrsdf',
            'f': 'drtgvc', 'g': 'ftyhbv', 'h': 'gyujnb', 'i': 'uojkl', 'j': 'huikmn',
            'k': 'jiolm', 'l': 'kop;', 'm': 'njk,', 'n': 'bhjm', 'o': 'iklp',
            'p': 'ol;[', 'q': 'asw', 'r': 'edft', 's': 'awedxz', 't': 'rfgy',
            'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu',
            'z': 'asx'
        }

        # Track total time spent to ensure we don't exceed reasonable limits
        total_time = 0
        max_time = 10.0  # Maximum seconds to spend on typing simulation

        # Start typing indicator
        async with channel.typing():
            # Simulate typing character by character
            i = 0
            while i < len(text) and total_time < max_time:
                # Calculate delay for this character
                char_delay = base_char_delay

                # Add natural variations
                if text[i] in ['.', '!', '?', ',']:
                    # Pause slightly longer after punctuation
                    char_delay *= random.uniform(1.5, 2.5)
                elif text[i] == ' ':
                    # Slight pause between words
                    char_delay *= random.uniform(1.0, 1.8)

                # Occasionally add a longer thinking pause (e.g., mid-sentence)
                if random.random() < 0.03 and text[i] in [' ', ',']:
                    thinking_pause = random.uniform(0.5, 1.5)
                    await asyncio.sleep(thinking_pause)
                    total_time += thinking_pause

                # Simulate a typo
                make_typo = random.random() < typo_probability and text[i].lower() in nearby_keys

                if make_typo:
                    # Choose a nearby key as the typo
                    if text[i].lower() in nearby_keys:
                        typo_char = random.choice(nearby_keys[text[i].lower()])
                        # Preserve case
                        if text[i].isupper():
                            typo_char = typo_char.upper()

                        # Wait before making the typo
                        await asyncio.sleep(char_delay)
                        total_time += char_delay

                        # Decide if we'll correct the typo
                        will_correct = random.random() < 0.8  # 80% chance to correct typos

                        if will_correct:
                            # Wait a bit before noticing the typo
                            notice_delay = random.uniform(0.2, 0.8)
                            await asyncio.sleep(notice_delay)
                            total_time += notice_delay

                            # Simulate backspace and correct character
                            correction_delay = random.uniform(0.1, 0.3)
                            await asyncio.sleep(correction_delay)
                            total_time += correction_delay
                        else:
                            # Don't correct, just continue typing
                            pass
                else:
                    # Normal typing, just wait the calculated delay
                    await asyncio.sleep(char_delay)
                    total_time += char_delay

                # Move to next character
                i += 1

                # Occasionally simulate a burst of fast typing (muscle memory for common words)
                if random.random() < 0.1 and i < len(text) - 3:
                    # Identify if we're in a common word
                    next_few_chars = text[i:i+min(5, len(text)-i)]
                    if ' ' not in next_few_chars:  # Within a word
                        burst_length = min(len(next_few_chars), random.randint(2, 4))
                        burst_delay = base_char_delay * 0.4 * burst_length  # Much faster typing
                        await asyncio.sleep(burst_delay)
                        total_time += burst_delay
                        i += burst_length - 1  # -1 because the loop will increment i again

            # Ensure we've spent at least some minimum time typing
            min_typing_time = min(1.0, len(text) * 0.03)  # At least 1 second or proportional to text length
            if total_time < min_typing_time:
                await asyncio.sleep(min_typing_time - total_time)

    @commands.Cog.listener()
    async def on_ready(self):
        """When the bot is ready, print a message"""
        print(f'Gurt Bot is ready! Logged in as {self.bot.user.name} ({self.bot.user.id})')
        print('------')

    @commands.command(name="gurt")
    async def gurt(self, ctx):
        """The main gurt command"""
        response = random.choice(self.gurt_responses)
        await ctx.send(response)

    @commands.command(name="gurtai")
    async def gurt_ai(self, ctx, *, prompt: str):
        """Get a response from the AI"""
        # Create a custom message object with the prompt
        custom_message = ctx.message
        custom_message.content = prompt

        try:
            # Show typing indicator
            async with ctx.typing():
                # Get AI response
                response_data = await self.get_ai_response(custom_message)

            # Check if there was an error or if the AI decided not to respond
            if "error" in response_data:
                error_msg = response_data["error"]
                print(f"Error in gurtai command: {error_msg}")
                await ctx.reply(f"Sorry, I'm having trouble thinking right now. Technical details: {error_msg}")
                return

            if not response_data.get("should_respond", False):
                await ctx.reply("I don't have anything to say about that right now.")
                return

            response = response_data.get("content", "")

            # Check if the response is too long
            if len(response) > 1900:
                # Create a text file with the content
                with open(f'gurt_response_{ctx.author.id}.txt', 'w', encoding='utf-8') as f:
                    f.write(response)

                # Send the file instead
                await ctx.send(
                    "The response was too long. Here's the content as a file:",
                    file=discord.File(f'gurt_response_{ctx.author.id}.txt')
                )

                # Clean up the file
                try:
                    os.remove(f'gurt_response_{ctx.author.id}.txt')
                except:
                    pass
            else:
                # Send the response normally
                await ctx.reply(response)
        except Exception as e:
            error_message = f"Error processing your request: {str(e)}"
            print(f"Exception in gurt_ai command: {error_message}")
            import traceback
            traceback.print_exc()
            await ctx.reply("Sorry, I encountered an error while processing your request. Please try again later.")

    @commands.command(name="gurtmodel")
    async def set_model(self, ctx, *, model: str):
        """Set the AI model to use"""
        if not model.endswith(":free"):
            await ctx.reply("Error: Model name must end with `:free`. Setting not updated.")
            return

        self.default_model = model
        await ctx.reply(f"AI model has been set to: `{model}`")

    @commands.command(name="gurtstatus")
    async def gurt_status(self, ctx):
        """Display the current status of Gurt Bot"""
        embed = discord.Embed(
            title="Gurt Bot Status",
            description="Current configuration and status of Gurt Bot",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Current Model",
            value=f"`{self.default_model}`",
            inline=False
        )

        embed.add_field(
            name="API Status",
            value="Connected" if self.session else "Disconnected",
            inline=True
        )

        embed.add_field(
            name="Mode",
            value="Autonomous",
            inline=True
        )

        await ctx.send(embed=embed)

    @commands.command(name="gurthelp")
    async def gurt_help(self, ctx):
        """Display help information for Gurt Bot"""
        embed = discord.Embed(
            title="Gurt Bot Help",
            description="Gurt Bot is an autonomous AI that speaks in a quirky way, often using the word 'gurt'. It listens to all messages and decides when to respond.",
            color=discord.Color.purple()
        )

        embed.add_field(
            name="Commands",
            value="`gurt!gurt` - Get a random gurt response\n"
                  "`gurt!gurtai <prompt>` - Ask the AI a question directly\n"
                  "`gurt!gurtmodel <model>` - Set the AI model to use\n"
                  "`gurt!gurthelp` - Display this help message",
            inline=False
        )

        embed.add_field(
            name="Autonomous Behavior",
            value="Gurt Bot listens to all messages in channels it has access to and uses AI to decide whether to respond. "
                  "It will respond naturally to conversations when it has something to add, when it's mentioned, "
                  "or when the topic is something it's interested in.",
            inline=False
        )

        embed.add_field(
            name="Available Tools",
            value="The AI can use these tools to gather context:\n"
                  "- Get recent messages from a channel\n"
                  "- Get recent messages from a channel\n"
                  "- Search for messages from a specific user\n"
                  "- Search for messages containing specific content\n"
                  "- Get information about a Discord channel\n"
                  "- Get conversation context\n"
                  "- Get thread context\n"
                  "- Get user interaction history\n"
                  "- Get conversation summary\n"
                  "- Get message context\n"
                  "- Search the web (`web_search`)\n" # Updated tool list
                  "- Remember user facts (`remember_user_fact`)\n"
                  "- Get user facts (`get_user_facts`)\n"
                  "- Remember general facts (`remember_general_fact`)\n"
                  "- Get general facts (`get_general_facts`)",
            inline=False
        )

        await ctx.send(embed=embed)

    def _analyze_message_sentiment(self, message_content: str) -> Dict[str, Any]:
        """
        Analyzes the sentiment of a message using keyword matching and emoji analysis.
        Returns a dictionary with sentiment information.
        """
        content = message_content.lower()
        result = {
            "sentiment": "neutral",  # Overall sentiment: positive, negative, neutral
            "intensity": 0.5,        # How strong the sentiment is (0.0-1.0)
            "emotions": [],          # List of detected emotions
            "confidence": 0.5        # How confident we are in this assessment
        }

        # Check for emojis first as they're strong sentiment indicators
        positive_emoji_count = sum(1 for emoji in self.emoji_sentiment["positive"] if emoji in content)
        negative_emoji_count = sum(1 for emoji in self.emoji_sentiment["negative"] if emoji in content)
        neutral_emoji_count = sum(1 for emoji in self.emoji_sentiment["neutral"] if emoji in content)

        total_emoji_count = positive_emoji_count + negative_emoji_count + neutral_emoji_count

        # Detect emotions based on keywords
        detected_emotions = []
        emotion_scores = {}

        for emotion, keywords in self.emotion_keywords.items():
            emotion_count = 0
            for keyword in keywords:
                # Look for whole word matches to avoid false positives
                if re.search(r'\b' + re.escape(keyword) + r'\b', content):
                    emotion_count += 1

            if emotion_count > 0:
                emotion_score = min(1.0, emotion_count / len(keywords) * 2)  # Scale up for better detection
                emotion_scores[emotion] = emotion_score
                detected_emotions.append(emotion)

        # Determine primary emotion if any were detected
        if emotion_scores:
            primary_emotion = max(emotion_scores.items(), key=lambda x: x[1])
            result["emotions"] = [primary_emotion[0]]  # Primary emotion

            # Add secondary emotions if they're close in score
            for emotion, score in emotion_scores.items():
                if emotion != primary_emotion[0] and score > primary_emotion[1] * 0.7:
                    result["emotions"].append(emotion)

            # Map emotions to sentiment
            positive_emotions = ["joy"]
            negative_emotions = ["sadness", "anger", "fear", "disgust"]

            if primary_emotion[0] in positive_emotions:
                result["sentiment"] = "positive"
                result["intensity"] = primary_emotion[1]
            elif primary_emotion[0] in negative_emotions:
                result["sentiment"] = "negative"
                result["intensity"] = primary_emotion[1]
            else:
                # For neutral or ambiguous emotions like surprise or confusion
                result["sentiment"] = "neutral"
                result["intensity"] = 0.5

            result["confidence"] = min(0.9, 0.5 + primary_emotion[1] * 0.4)

        # If no strong emotions detected but emojis present, use emoji sentiment
        elif total_emoji_count > 0:
            if positive_emoji_count > negative_emoji_count:
                result["sentiment"] = "positive"
                result["intensity"] = min(0.9, 0.5 + (positive_emoji_count / total_emoji_count) * 0.4)
                result["confidence"] = min(0.8, 0.4 + (positive_emoji_count / total_emoji_count) * 0.4)
            elif negative_emoji_count > positive_emoji_count:
                result["sentiment"] = "negative"
                result["intensity"] = min(0.9, 0.5 + (negative_emoji_count / total_emoji_count) * 0.4)
                result["confidence"] = min(0.8, 0.4 + (negative_emoji_count / total_emoji_count) * 0.4)
            else:
                # Equal positive and negative, or just neutral emojis
                result["sentiment"] = "neutral"
                result["intensity"] = 0.5
                result["confidence"] = 0.6

        # Simple text-based sentiment analysis as fallback
        else:
            # Basic positive/negative word lists
            positive_words = {"good", "great", "awesome", "amazing", "excellent", "love", "like", "best",
                             "better", "nice", "cool", "happy", "glad", "thanks", "thank", "appreciate",
                             "wonderful", "fantastic", "perfect", "beautiful", "fun", "enjoy", "yes", "yep"}

            negative_words = {"bad", "terrible", "awful", "worst", "hate", "dislike", "sucks", "stupid",
                             "boring", "annoying", "sad", "upset", "angry", "mad", "disappointed", "sorry",
                             "unfortunate", "horrible", "ugly", "wrong", "fail", "no", "nope"}

            # Count word occurrences
            words = re.findall(r'\b\w+\b', content)
            positive_count = sum(1 for word in words if word in positive_words)
            negative_count = sum(1 for word in words if word in negative_words)

            # Determine sentiment based on word counts
            if positive_count > negative_count:
                result["sentiment"] = "positive"
                result["intensity"] = min(0.8, 0.5 + (positive_count / len(words)) * 2)
                result["confidence"] = min(0.7, 0.3 + (positive_count / len(words)) * 0.4)
            elif negative_count > positive_count:
                result["sentiment"] = "negative"
                result["intensity"] = min(0.8, 0.5 + (negative_count / len(words)) * 2)
                result["confidence"] = min(0.7, 0.3 + (negative_count / len(words)) * 0.4)
            else:
                # Equal or no sentiment words
                result["sentiment"] = "neutral"
                result["intensity"] = 0.5
                result["confidence"] = 0.5

        return result

    def _update_conversation_sentiment(self, channel_id: int, user_id: str, message_sentiment: Dict[str, Any]):
        """
        Updates the conversation sentiment tracking based on a new message's sentiment.
        This helps track the emotional context of conversations over time.
        """
        # Get current sentiment data for this channel
        channel_sentiment = self.conversation_sentiment[channel_id]
        now = time.time()

        # Check if we need to update sentiment (based on time interval)
        if now - channel_sentiment["last_update"] > self.sentiment_update_interval:
            # Apply decay to move sentiment toward neutral over time
            if channel_sentiment["overall"] == "positive":
                channel_sentiment["intensity"] = max(0.5, channel_sentiment["intensity"] - self.sentiment_decay_rate)
            elif channel_sentiment["overall"] == "negative":
                channel_sentiment["intensity"] = max(0.5, channel_sentiment["intensity"] - self.sentiment_decay_rate)

            # Reset trend if it's been a while
            channel_sentiment["recent_trend"] = "stable"
            channel_sentiment["last_update"] = now

        # Update user sentiment
        user_sentiment = channel_sentiment["user_sentiments"].get(user_id, {
            "sentiment": "neutral",
            "intensity": 0.5
        })

        # Blend new sentiment with existing user sentiment (weighted average)
        confidence_weight = message_sentiment["confidence"]
        if user_sentiment["sentiment"] == message_sentiment["sentiment"]:
            # Same sentiment direction, increase intensity
            new_intensity = user_sentiment["intensity"] * 0.7 + message_sentiment["intensity"] * 0.3
            user_sentiment["intensity"] = min(0.95, new_intensity)
        else:
            # Different sentiment direction, move toward new sentiment based on confidence
            if message_sentiment["confidence"] > 0.7:
                # High confidence in new sentiment, shift more strongly
                user_sentiment["sentiment"] = message_sentiment["sentiment"]
                user_sentiment["intensity"] = message_sentiment["intensity"] * 0.7 + user_sentiment["intensity"] * 0.3
            else:
                # Lower confidence, more gradual shift
                if message_sentiment["intensity"] > user_sentiment["intensity"]:
                    user_sentiment["sentiment"] = message_sentiment["sentiment"]
                    user_sentiment["intensity"] = user_sentiment["intensity"] * 0.6 + message_sentiment["intensity"] * 0.4

        # Store updated user sentiment
        channel_sentiment["user_sentiments"][user_id] = user_sentiment

        # Update overall conversation sentiment based on active users
        active_user_sentiments = [
            s for uid, s in channel_sentiment["user_sentiments"].items()
            if uid in self.active_conversations.get(channel_id, {}).get('participants', set())
        ]

        if active_user_sentiments:
            # Count sentiment types
            sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
            for s in active_user_sentiments:
                sentiment_counts[s["sentiment"]] += 1

            # Determine dominant sentiment
            dominant_sentiment = max(sentiment_counts.items(), key=lambda x: x[1])[0]

            # Calculate average intensity for the dominant sentiment
            avg_intensity = sum(s["intensity"] for s in active_user_sentiments
                              if s["sentiment"] == dominant_sentiment) / sentiment_counts[dominant_sentiment]

            # Update trend
            prev_sentiment = channel_sentiment["overall"]
            prev_intensity = channel_sentiment["intensity"]

            if dominant_sentiment == prev_sentiment:
                if avg_intensity > prev_intensity + 0.1:
                    channel_sentiment["recent_trend"] = "intensifying"
                elif avg_intensity < prev_intensity - 0.1:
                    channel_sentiment["recent_trend"] = "diminishing"
                else:
                    channel_sentiment["recent_trend"] = "stable"
            else:
                channel_sentiment["recent_trend"] = "changing"

            # Update overall sentiment
            channel_sentiment["overall"] = dominant_sentiment
            channel_sentiment["intensity"] = avg_intensity

        # Update timestamp
        channel_sentiment["last_update"] = now

        # Store updated channel sentiment
        self.conversation_sentiment[channel_id] = channel_sentiment

    @commands.Cog.listener()
    async def on_message(self, message):
        """Process all messages and decide whether to respond"""
        # Don't respond to our own messages
        if message.author == self.bot.user:
            return

        # Don't process commands here
        if message.content.startswith(self.bot.command_prefix):
            return

        # --- Cache and Track Incoming Message ---
        try:
            formatted_message = self._format_message(message)
            channel_id = message.channel.id
            user_id = message.author.id
            thread_id = message.channel.id if isinstance(message.channel, discord.Thread) else None

            # Update caches
            self.message_cache['by_channel'][channel_id].append(formatted_message)
            self.message_cache['by_user'][user_id].append(formatted_message)
            self.message_cache['global_recent'].append(formatted_message)
            if thread_id:
                self.message_cache['by_thread'][thread_id].append(formatted_message)
            if self.bot.user.mentioned_in(message):
                 self.message_cache['mentioned'].append(formatted_message)

            # Update conversation history (can be redundant with cache but kept for potential different use cases)
            self.conversation_history[channel_id].append(formatted_message)
            if thread_id:
                self.thread_history[thread_id].append(formatted_message)

            # Update activity tracking
            self.channel_activity[channel_id] = time.time()
            self.user_conversation_mapping[user_id].add(channel_id)

            # Update active conversation participants (simplified)
            if channel_id not in self.active_conversations:
                self.active_conversations[channel_id] = {'participants': set(), 'start_time': time.time(), 'last_activity': time.time(), 'topic': None}
            self.active_conversations[channel_id]['participants'].add(user_id)
            self.active_conversations[channel_id]['last_activity'] = time.time()

            # Update user relationship interaction count
            if user_id != self.bot.user.id:
                if user_id not in self.user_relationships:
                    self.user_relationships[user_id] = {}
                self.user_relationships[user_id][self.bot.user.id] = self.user_relationships[user_id].get(self.bot.user.id, 0) + 1
                # Optional: Decay old relationships or prune the dict periodically

            # Analyze message sentiment and update conversation sentiment tracking
            if message.content:  # Only analyze non-empty messages
                message_sentiment = self._analyze_message_sentiment(message.content)
                self._update_conversation_sentiment(channel_id, str(user_id), message_sentiment)

        except Exception as e:
            print(f"Error during message caching/tracking: {e}")
        # --- End Caching ---


        # Simple response for messages just containing "gurt" without using AI
        if message.content.lower() == "gurt":
            response = random.choice(self.gurt_responses)
            # Record bot response in cache? Maybe not for simple ones.
            await message.channel.send(response)
            return

        # Check if the bot is mentioned or if "gurt" is in the message
        bot_mentioned = self.bot.user.mentioned_in(message)
        replied_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == self.bot.user
        gurt_in_message = "gurt" in message.content.lower()
        channel_id = message.channel.id
        now = time.time()

        # --- Decide if we should even CONSIDER responding (call the AI) ---
        should_consider_responding = False

        # Always consider if mentioned, replied to, or name used directly
        if bot_mentioned or replied_to_bot or gurt_in_message:
            should_consider_responding = True
        else:
            # Consider based on chattiness and channel activity
            time_since_last_activity = now - self.channel_activity.get(channel_id, 0)
            time_since_bot_spoke = now - self.bot_last_spoke.get(channel_id, 0)

            # Higher chance if channel is quiet or bot hasn't spoken recently
            base_chance = self.personality_traits['chattiness'] * 0.5 # Base chance from personality
            if time_since_last_activity > 120: # Quiet channel bonus (2 mins)
                base_chance += 0.2
            if time_since_bot_spoke > 300: # Bot hasn't spoken bonus (5 mins)
                base_chance += 0.1

            # Clamp chance between 0.05 and 0.9
            final_chance = min(max(base_chance, 0.05), 0.9)

            if random.random() < final_chance:
                should_consider_responding = True
                print(f"Considering response based on chattiness ({final_chance:.2f} chance).")
            else:
                 # print(f"Skipping AI call based on chattiness ({final_chance:.2f} chance).") # Optional: uncomment for debugging
                 pass

        if not should_consider_responding:
            return # Don't call the AI if we decided not to consider responding

        # --- If we should consider responding, call the AI ---
        # Store the current channel for context in tools
        self.current_channel = message.channel

        try:
            # Get AI response with decision on whether to respond
            print(f"Calling get_ai_response for message {message.id}")
            response_data = await self.get_ai_response(message)

            # Check if there was an error in the API call
            if "error" in response_data:
                print(f"Error in AI response: {response_data['error']}")

                # If the bot was directly mentioned but there was an API error,
                # send a simple response so the user isn't left hanging
                if bot_mentioned:
                    await message.channel.send(random.choice([
                        "Sorry, I'm having trouble thinking right now...",
                        "Hmm, my brain is foggy at the moment.",
                        "Give me a sec, I'm a bit confused right now.",
                        "*confused gurting*"
                    ]))
                return

            # --- Handle AI Response ---
            reacted = False
            sent_message = False

            # 1. Handle Reaction
            emoji_to_react = response_data.get("react_with_emoji")
            if emoji_to_react and isinstance(emoji_to_react, str):
                try:
                    # Basic validation: check length and avoid custom emoji syntax for simplicity
                    if 1 <= len(emoji_to_react) <= 4 and not re.match(r'<a?:.+?:\d+>', emoji_to_react):
                        await message.add_reaction(emoji_to_react)
                        reacted = True
                        print(f"Bot reacted to message {message.id} with {emoji_to_react}")
                    else:
                        print(f"Invalid emoji format received: {emoji_to_react}")
                except discord.HTTPException as e:
                    print(f"Error adding reaction '{emoji_to_react}': {e.status} {e.text}")
                except Exception as e:
                    print(f"Generic error adding reaction '{emoji_to_react}': {e}")

            # 2. Handle Text Response
            if response_data.get("should_respond", False) and response_data.get("content"):
                response_text = response_data["content"]

                # Check if the response is too long
                if len(response_text) > 1900:
                    # Create a text file with the content
                    filepath = f'gurt_response_{message.id}.txt' # Use message ID for uniqueness
                    try:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(response_text)
                        # Send the file instead
                        await message.channel.send(
                            "The response was too long. Here's the content as a file:",
                            file=discord.File(filepath)
                        )
                        sent_message = True
                    except Exception as file_e:
                         print(f"Error writing/sending long response file: {file_e}")
                    finally:
                        # Clean up the file
                        try:
                            os.remove(filepath)
                        except OSError as os_e:
                             print(f"Error removing temp file {filepath}: {os_e}")
                else:
                    # Show typing indicator with advanced human-like typing simulation
                    async with message.channel.typing():
                        # Determine if we should simulate realistic typing with potential typos
                        simulate_realistic_typing = len(response_text) < 200 and random.random() < 0.4

                        if simulate_realistic_typing:
                            # We'll simulate typing character by character with realistic timing
                            await self._simulate_human_typing(message.channel, response_text)
                        else:
                            # For longer messages, use the simpler timing model
                            # Enhanced human-like typing delay calculation
                            # Base typing speed varies by personality traits
                            base_delay = 0.2 * (1.0 - self.personality_traits["randomness"]) # Faster for more random personalities

                            # Calculate typing time based on message length and typing speed
                            # Average human typing speed is ~40-60 WPM (5-7 chars per second)
                            chars_per_second = random.uniform(4.0, 8.0) # Randomize typing speed

                            # Calculate base typing time
                            typing_time = len(response_text) / chars_per_second

                            # Apply personality modifiers
                            if self.current_mood in ["excited", "slightly hyper"]:
                                typing_time *= 0.8  # Type faster when excited
                            elif self.current_mood in ["tired", "a bit bored"]:
                                typing_time *= 1.2  # Type slower when tired

                            # Add human-like pauses and variations
                            # Occasionally pause as if thinking
                            if random.random() < 0.15:  # 15% chance of a thinking pause
                                thinking_pause = random.uniform(1.0, 3.0)
                                typing_time += thinking_pause

                            # Sometimes type very quickly (as if copy-pasting or had response ready)
                            if random.random() < 0.08:  # 8% chance of very quick response
                                typing_time = random.uniform(0.5, 1.5)

                            # Sometimes take extra time (as if distracted)
                            if random.random() < 0.05:  # 5% chance of distraction
                                typing_time += random.uniform(2.0, 5.0)

                            # Clamp final typing time to reasonable bounds
                            typing_time = min(max(typing_time, 0.8), 8.0)  # Between 0.8 and 8 seconds

                            # Wait for the calculated time
                            await asyncio.sleep(typing_time)

                    # Decide if we should add a human-like mistake and correction
                    should_make_mistake = random.random() < 0.15 * self.personality_traits["randomness"]

                    if should_make_mistake and len(response_text) > 10:
                        # Create a version with a mistake
                        mistake_text, correction = self._create_human_like_mistake(response_text)

                        # Send the mistake first
                        mistake_msg = await message.channel.send(mistake_text)
                        sent_message = True

                        # Wait a moment as if noticing the mistake
                        notice_delay = random.uniform(1.5, 4.0)
                        await asyncio.sleep(notice_delay)

                        # Send the correction
                        if correction:
                            await message.channel.send(correction)
                    else:
                        # Send the normal response
                        await message.channel.send(response_text)
                        sent_message = True

            # Log if nothing happened but should_respond was true (e.g., empty content)
            if response_data.get("should_respond") and not sent_message and not reacted:
                print(f"Warning: AI decided to respond but provided no valid content or reaction. Data: {response_data}")

        except Exception as e:
            print(f"Exception in on_message processing AI response: {str(e)}")
            import traceback
            traceback.print_exc()

            # If the bot was directly mentioned but there was an exception,
            # send a simple response so the user isn't left hanging
            if bot_mentioned:
                await message.channel.send(random.choice([
                    "Sorry, I'm having trouble thinking right now...",
                    "Hmm, my brain is foggy at the moment.",
                    "Give me a sec, I'm a bit confused right now.",
                    "*confused gurting*"
                ]))

async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(GurtCog(bot))
