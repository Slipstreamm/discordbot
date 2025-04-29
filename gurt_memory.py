import aiosqlite
import asyncio
import os
import time
import datetime
import re
import hashlib # Added for chroma_id generation
import json # Added for personality trait serialization/deserialization
from typing import Dict, List, Any, Optional, Tuple, Union # Added Union
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
INTEREST_INITIAL_LEVEL = 0.1
INTEREST_MAX_LEVEL = 1.0
INTEREST_MIN_LEVEL = 0.0
INTEREST_DECAY_RATE = 0.02 # Default decay rate per cycle
INTEREST_DECAY_INTERVAL_HOURS = 24 # Default interval for decay check

# --- Helper Function for Keyword Scoring ---
def calculate_keyword_score(text: str, context: str) -> int:
    """Calculates a simple keyword overlap score."""
    if not context or not text:
        return 0
    context_words = set(re.findall(r'\b\w+\b', context.lower()))
    text_words = set(re.findall(r'\b\w+\b', text.lower()))
    # Ignore very common words (basic stopword list)
    stopwords = {"the", "a", "is", "in", "it", "of", "and", "to", "for", "on", "with", "that", "this", "i", "you", "me", "my", "your"}
    context_words -= stopwords
    text_words -= stopwords
    if not context_words: # Avoid division by zero if context is only stopwords
        return 0
    overlap = len(context_words.intersection(text_words))
    # Normalize score slightly by context length (more overlap needed for longer context)
    # score = overlap / (len(context_words) ** 0.5) # Example normalization
    score = overlap # Simpler score for now
    return score

class MemoryManager:
    """Handles database interactions for Gurt's memory (facts and semantic)."""

    def __init__(self, db_path: str, max_user_facts: int = 20, max_general_facts: int = 100, semantic_model_name: str = 'all-MiniLM-L6-v2', chroma_path: str = "data/chroma_db"):
        self.db_path = db_path
        self.max_user_facts = max_user_facts
        self.max_general_facts = max_general_facts
        self.db_lock = asyncio.Lock() # Lock for SQLite operations

        # Ensure data directories exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(chroma_path, exist_ok=True)
        logger.info(f"MemoryManager initialized with db_path: {self.db_path}, chroma_path: {chroma_path}")

        # --- Semantic Memory Setup ---
        self.chroma_path = chroma_path
        self.semantic_model_name = semantic_model_name
        self.chroma_client = None
        self.embedding_function = None
        self.semantic_collection = None # For messages
        self.fact_collection = None # For facts
        self.transformer_model = None
        self._initialize_semantic_memory_sync() # Initialize semantic components synchronously for simplicity during init

    def _initialize_semantic_memory_sync(self):
        """Synchronously initializes ChromaDB client, model, and collection."""
        try:
            logger.info("Initializing ChromaDB client...")
            # Use PersistentClient for saving data to disk
            self.chroma_client = chromadb.PersistentClient(path=self.chroma_path)

            logger.info(f"Loading Sentence Transformer model: {self.semantic_model_name}...")
            # Load the model directly
            self.transformer_model = SentenceTransformer(self.semantic_model_name)

            # Create a custom embedding function using the loaded model
            class CustomEmbeddingFunction(embedding_functions.EmbeddingFunction):
                def __init__(self, model):
                    self.model = model
                def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
                    # Ensure input is a list of strings
                    if not isinstance(input, list):
                        input = [str(input)] # Convert single item to list
                    elif not all(isinstance(item, str) for item in input):
                         input = [str(item) for item in input] # Ensure all items are strings

                    logger.debug(f"Generating embeddings for {len(input)} documents.")
                    embeddings = self.model.encode(input, show_progress_bar=False).tolist()
                    logger.debug(f"Generated {len(embeddings)} embeddings.")
                    return embeddings

            self.embedding_function = CustomEmbeddingFunction(self.transformer_model)

            logger.info("Getting/Creating ChromaDB collection 'gurt_semantic_memory'...")
            # Get or create the collection with the custom embedding function
            self.semantic_collection = self.chroma_client.get_or_create_collection(
                name="gurt_semantic_memory",
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"} # Use cosine distance for similarity
            ) # Added missing closing parenthesis
            logger.info("ChromaDB message collection initialized successfully.")

            logger.info("Getting/Creating ChromaDB collection 'gurt_fact_memory'...")
            # Get or create the collection for facts
            self.fact_collection = self.chroma_client.get_or_create_collection(
                name="gurt_fact_memory",
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"} # Use cosine distance for similarity
            )
            logger.info("ChromaDB fact collection initialized successfully.")

        except Exception as e:
            logger.error(f"Failed to initialize semantic memory (ChromaDB): {e}", exc_info=True)
            # Set components to None to indicate failure
            self.chroma_client = None
            self.transformer_model = None
            self.embedding_function = None
            self.semantic_collection = None
            self.fact_collection = None # Also set fact_collection to None on error

    async def initialize_sqlite_database(self):
        """Initializes the SQLite database and creates tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")

            # Create user_facts table if it doesn't exist
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    chroma_id TEXT, -- Added for linking to ChromaDB
                    timestamp REAL DEFAULT (unixepoch('now')),
                    PRIMARY KEY (user_id, fact)
                );
            """)

            # Check if chroma_id column exists in user_facts table
            try:
                # Try to get column info
                cursor = await db.execute("PRAGMA table_info(user_facts)")
                columns = await cursor.fetchall()
                column_names = [column[1] for column in columns]

                # If chroma_id column doesn't exist, add it
                if 'chroma_id' not in column_names:
                    logger.info("Adding chroma_id column to user_facts table")
                    await db.execute("ALTER TABLE user_facts ADD COLUMN chroma_id TEXT")
            except Exception as e:
                logger.error(f"Error checking/adding chroma_id column to user_facts: {e}", exc_info=True)

            # Create indexes
            await db.execute("CREATE INDEX IF NOT EXISTS idx_user_facts_user ON user_facts (user_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_user_facts_chroma_id ON user_facts (chroma_id);") # Index for chroma_id

            # Create general_facts table if it doesn't exist
            await db.execute("""
                CREATE TABLE IF NOT EXISTS general_facts (
                    fact TEXT PRIMARY KEY NOT NULL,
                    chroma_id TEXT, -- Added for linking to ChromaDB
                    timestamp REAL DEFAULT (unixepoch('now'))
                );
            """)

            # Check if chroma_id column exists in general_facts table
            try:
                # Try to get column info
                cursor = await db.execute("PRAGMA table_info(general_facts)")
                columns = await cursor.fetchall()
                column_names = [column[1] for column in columns]

                # If chroma_id column doesn't exist, add it
                if 'chroma_id' not in column_names:
                    logger.info("Adding chroma_id column to general_facts table")
                    await db.execute("ALTER TABLE general_facts ADD COLUMN chroma_id TEXT")
            except Exception as e:
                logger.error(f"Error checking/adding chroma_id column to general_facts: {e}", exc_info=True)

            # Create index for general_facts
            await db.execute("CREATE INDEX IF NOT EXISTS idx_general_facts_chroma_id ON general_facts (chroma_id);") # Index for chroma_id

            # --- Add Personality Table ---
            await db.execute("""
                CREATE TABLE IF NOT EXISTS gurt_personality (
                    trait_key TEXT PRIMARY KEY NOT NULL,
                    trait_value TEXT NOT NULL, -- Store value as JSON string
                    last_updated REAL DEFAULT (unixepoch('now'))
                );
            """)
            logger.info("Personality table created/verified.")
            # --- End Personality Table ---

            # --- Add Interests Table ---
            await db.execute("""
                CREATE TABLE IF NOT EXISTS gurt_interests (
                    interest_topic TEXT PRIMARY KEY NOT NULL,
                    interest_level REAL DEFAULT 0.1, -- Start with a small default level
                    last_updated REAL DEFAULT (unixepoch('now'))
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_interest_level ON gurt_interests (interest_level);")
            logger.info("Interests table created/verified.")
            # --- End Interests Table ---

            # --- Add Goals Table ---
            await db.execute("""
                CREATE TABLE IF NOT EXISTS gurt_goals (
                    goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL UNIQUE, -- The goal description
                    status TEXT DEFAULT 'pending', -- e.g., pending, active, completed, failed
                    priority INTEGER DEFAULT 5, -- Lower number = higher priority
                    created_timestamp REAL DEFAULT (unixepoch('now')),
                    last_updated REAL DEFAULT (unixepoch('now')),
                    details TEXT -- Optional JSON blob for sub-tasks, progress, etc.
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_goal_status ON gurt_goals (status);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_goal_priority ON gurt_goals (priority);")
            logger.info("Goals table created/verified.")
            # --- End Goals Table ---

            # --- Add Internal Actions Log Table ---
            await db.execute("""
                CREATE TABLE IF NOT EXISTS internal_actions (
                    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL DEFAULT (unixepoch('now')),
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT, -- Store arguments as JSON string
                    reasoning TEXT, -- Added: Reasoning behind the action
                    result_summary TEXT -- Store a summary of the result or error message
                );
            """)
            # Check if reasoning column exists
            try:
                cursor = await db.execute("PRAGMA table_info(internal_actions)")
                columns = await cursor.fetchall()
                column_names = [column[1] for column in columns]
                if 'reasoning' not in column_names:
                    logger.info("Adding reasoning column to internal_actions table")
                    await db.execute("ALTER TABLE internal_actions ADD COLUMN reasoning TEXT")
            except Exception as e:
                logger.error(f"Error checking/adding reasoning column to internal_actions: {e}", exc_info=True)

            await db.execute("CREATE INDEX IF NOT EXISTS idx_internal_actions_timestamp ON internal_actions (timestamp);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_internal_actions_tool_name ON internal_actions (tool_name);")
            logger.info("Internal Actions Log table created/verified.")
            # --- End Internal Actions Log Table ---

            await db.commit()
            logger.info(f"SQLite database initialized/verified at {self.db_path}")

    # --- SQLite Helper Methods ---
    async def _db_execute(self, sql: str, params: tuple = ()):
        async with self.db_lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(sql, params)
                await db.commit()

    async def _db_fetchone(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(sql, params) as cursor:
                return await cursor.fetchone()

    async def _db_fetchall(self, sql: str, params: tuple = ()) -> List[tuple]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(sql, params) as cursor:
                return await cursor.fetchall()

    # --- User Fact Memory Methods (SQLite + Relevance) ---

    async def add_user_fact(self, user_id: str, fact: str) -> Dict[str, Any]:
        """Stores a fact about a user in the SQLite database, enforcing limits."""
        if not user_id or not fact:
            return {"error": "user_id and fact are required."}
        logger.info(f"Attempting to add user fact for {user_id}: '{fact}'")
        try:
            # Check SQLite first
            existing = await self._db_fetchone("SELECT chroma_id FROM user_facts WHERE user_id = ? AND fact = ?", (user_id, fact))
            if existing:
                logger.info(f"Fact already known for user {user_id} (SQLite).")
                return {"status": "duplicate", "user_id": user_id, "fact": fact}

            count_result = await self._db_fetchone("SELECT COUNT(*) FROM user_facts WHERE user_id = ?", (user_id,))
            current_count = count_result[0] if count_result else 0

            status = "added"
            deleted_chroma_id = None
            if current_count >= self.max_user_facts:
                logger.warning(f"User {user_id} fact limit ({self.max_user_facts}) reached. Deleting oldest.")
                # Fetch oldest fact and its chroma_id for deletion
                oldest_fact_row = await self._db_fetchone("SELECT fact, chroma_id FROM user_facts WHERE user_id = ? ORDER BY timestamp ASC LIMIT 1", (user_id,))
                if oldest_fact_row:
                    oldest_fact, deleted_chroma_id = oldest_fact_row
                    await self._db_execute("DELETE FROM user_facts WHERE user_id = ? AND fact = ?", (user_id, oldest_fact))
                    logger.info(f"Deleted oldest fact for user {user_id} from SQLite: '{oldest_fact}'")
                    status = "limit_reached" # Indicate limit was hit but fact was added

            # Generate chroma_id
            fact_hash = hashlib.sha1(fact.encode()).hexdigest()[:16] # Short hash
            chroma_id = f"user-{user_id}-{fact_hash}"

            # Insert into SQLite
            await self._db_execute("INSERT INTO user_facts (user_id, fact, chroma_id) VALUES (?, ?, ?)", (user_id, fact, chroma_id))
            logger.info(f"Fact added for user {user_id} to SQLite.")

            # Add to ChromaDB fact collection
            if self.fact_collection and self.embedding_function:
                try:
                    metadata = {"user_id": user_id, "type": "user", "timestamp": time.time()}
                    await asyncio.to_thread(
                        self.fact_collection.add,
                        documents=[fact],
                        metadatas=[metadata],
                        ids=[chroma_id]
                    )
                    logger.info(f"Fact added/updated for user {user_id} in ChromaDB (ID: {chroma_id}).")

                    # Delete the oldest fact from ChromaDB if limit was reached
                    if deleted_chroma_id:
                        logger.info(f"Attempting to delete oldest fact from ChromaDB (ID: {deleted_chroma_id}).")
                        await asyncio.to_thread(self.fact_collection.delete, ids=[deleted_chroma_id])
                        logger.info(f"Successfully deleted oldest fact from ChromaDB (ID: {deleted_chroma_id}).")

                except Exception as chroma_e:
                    logger.error(f"ChromaDB error adding/deleting user fact for {user_id} (ID: {chroma_id}): {chroma_e}", exc_info=True)
                    # Note: Fact is still in SQLite, but ChromaDB might be inconsistent. Consider rollback? For now, just log.
            else:
                 logger.warning(f"ChromaDB fact collection not available. Skipping embedding for user fact {user_id}.")


            return {"status": status, "user_id": user_id, "fact_added": fact}

        except Exception as e:
            logger.error(f"Error adding user fact for {user_id}: {e}", exc_info=True)
            return {"error": f"Database error adding user fact: {str(e)}"}

    async def get_user_facts(self, user_id: str, context: Optional[str] = None) -> List[str]:
        """Retrieves stored facts about a user, optionally scored by relevance to context."""
        if not user_id:
            logger.warning("get_user_facts called without user_id.")
            return []
        logger.info(f"Retrieving facts for user {user_id} (context provided: {bool(context)})")
        limit = self.max_user_facts # Use the class attribute for limit

        try:
            if context and self.fact_collection and self.embedding_function:
                # --- Semantic Search ---
                logger.debug(f"Performing semantic search for user facts (User: {user_id}, Limit: {limit})")
                try:
                    # Query ChromaDB for facts relevant to the context
                    results = await asyncio.to_thread(
                        self.fact_collection.query,
                        query_texts=[context],
                        n_results=limit,
                        where={ # Use $and for multiple conditions
                            "$and": [
                                {"user_id": user_id},
                                {"type": "user"}
                            ]
                        },
                        include=['documents'] # Only need the fact text
                    )
                    logger.debug(f"ChromaDB user fact query results: {results}")

                    if results and results.get('documents') and results['documents'][0]:
                        relevant_facts = results['documents'][0]
                        logger.info(f"Found {len(relevant_facts)} semantically relevant user facts for {user_id}.")
                        return relevant_facts
                    else:
                        logger.info(f"No semantic user facts found for {user_id} matching context.")
                        return [] # Return empty list if no semantic matches

                except Exception as chroma_e:
                    logger.error(f"ChromaDB error searching user facts for {user_id}: {chroma_e}", exc_info=True)
                    # Fallback to SQLite retrieval on ChromaDB error
                    logger.warning(f"Falling back to SQLite retrieval for user facts {user_id} due to ChromaDB error.")
                    # Proceed to the SQLite block below
            # --- SQLite Fallback / No Context ---
            # If no context, or if ChromaDB failed/unavailable, get newest N facts from SQLite
            logger.debug(f"Retrieving user facts from SQLite (User: {user_id}, Limit: {limit})")
            rows_ordered = await self._db_fetchall(
                "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit)
            )
            sqlite_facts = [row[0] for row in rows_ordered]
            logger.info(f"Retrieved {len(sqlite_facts)} user facts from SQLite for {user_id}.")
            return sqlite_facts

        except Exception as e:
            logger.error(f"Error retrieving user facts for {user_id}: {e}", exc_info=True)
            return []

    # --- General Fact Memory Methods (SQLite + Relevance) ---

    async def add_general_fact(self, fact: str) -> Dict[str, Any]:
        """Stores a general fact in the SQLite database, enforcing limits."""
        if not fact:
            return {"error": "fact is required."}
        logger.info(f"Attempting to add general fact: '{fact}'")
        try:
            # Check SQLite first
            existing = await self._db_fetchone("SELECT chroma_id FROM general_facts WHERE fact = ?", (fact,))
            if existing:
                logger.info(f"General fact already known (SQLite): '{fact}'")
                return {"status": "duplicate", "fact": fact}

            count_result = await self._db_fetchone("SELECT COUNT(*) FROM general_facts", ())
            current_count = count_result[0] if count_result else 0

            status = "added"
            deleted_chroma_id = None
            if current_count >= self.max_general_facts:
                logger.warning(f"General fact limit ({self.max_general_facts}) reached. Deleting oldest.")
                # Fetch oldest fact and its chroma_id for deletion
                oldest_fact_row = await self._db_fetchone("SELECT fact, chroma_id FROM general_facts ORDER BY timestamp ASC LIMIT 1", ())
                if oldest_fact_row:
                    oldest_fact, deleted_chroma_id = oldest_fact_row
                    await self._db_execute("DELETE FROM general_facts WHERE fact = ?", (oldest_fact,))
                    logger.info(f"Deleted oldest general fact from SQLite: '{oldest_fact}'")
                    status = "limit_reached"

            # Generate chroma_id
            fact_hash = hashlib.sha1(fact.encode()).hexdigest()[:16] # Short hash
            chroma_id = f"general-{fact_hash}"

            # Insert into SQLite
            await self._db_execute("INSERT INTO general_facts (fact, chroma_id) VALUES (?, ?)", (fact, chroma_id))
            logger.info(f"General fact added to SQLite: '{fact}'")

            # Add to ChromaDB fact collection
            if self.fact_collection and self.embedding_function:
                try:
                    metadata = {"type": "general", "timestamp": time.time()}
                    await asyncio.to_thread(
                        self.fact_collection.add,
                        documents=[fact],
                        metadatas=[metadata],
                        ids=[chroma_id]
                    )
                    logger.info(f"General fact added/updated in ChromaDB (ID: {chroma_id}).")

                    # Delete the oldest fact from ChromaDB if limit was reached
                    if deleted_chroma_id:
                        logger.info(f"Attempting to delete oldest general fact from ChromaDB (ID: {deleted_chroma_id}).")
                        await asyncio.to_thread(self.fact_collection.delete, ids=[deleted_chroma_id])
                        logger.info(f"Successfully deleted oldest general fact from ChromaDB (ID: {deleted_chroma_id}).")

                except Exception as chroma_e:
                    logger.error(f"ChromaDB error adding/deleting general fact (ID: {chroma_id}): {chroma_e}", exc_info=True)
                    # Note: Fact is still in SQLite.
            else:
                 logger.warning(f"ChromaDB fact collection not available. Skipping embedding for general fact.")

            return {"status": status, "fact_added": fact}

        except Exception as e:
            logger.error(f"Error adding general fact: {e}", exc_info=True)
            return {"error": f"Database error adding general fact: {str(e)}"}

    async def get_general_facts(self, query: Optional[str] = None, limit: Optional[int] = 10, context: Optional[str] = None) -> List[str]:
        """Retrieves stored general facts, optionally filtering by query or scoring by context relevance."""
        logger.info(f"Retrieving general facts (query='{query}', limit={limit}, context provided: {bool(context)})")
        limit = min(max(1, limit or 10), 50) # Use provided limit or default 10, max 50

        try:
            if context and self.fact_collection and self.embedding_function:
                # --- Semantic Search (Prioritized if context is provided) ---
                # Note: The 'query' parameter is ignored when context is provided for semantic search.
                logger.debug(f"Performing semantic search for general facts (Limit: {limit})")
                try:
                    results = await asyncio.to_thread(
                        self.fact_collection.query,
                        query_texts=[context],
                        n_results=limit,
                        where={"type": "general"}, # Filter by type
                        include=['documents'] # Only need the fact text
                    )
                    logger.debug(f"ChromaDB general fact query results: {results}")

                    if results and results.get('documents') and results['documents'][0]:
                        relevant_facts = results['documents'][0]
                        logger.info(f"Found {len(relevant_facts)} semantically relevant general facts.")
                        return relevant_facts
                    else:
                        logger.info("No semantic general facts found matching context.")
                        return [] # Return empty list if no semantic matches

                except Exception as chroma_e:
                    logger.error(f"ChromaDB error searching general facts: {chroma_e}", exc_info=True)
                    # Fallback to SQLite retrieval on ChromaDB error
                    logger.warning("Falling back to SQLite retrieval for general facts due to ChromaDB error.")
                    # Proceed to the SQLite block below, respecting the original 'query' if present
            # --- SQLite Fallback / No Context / ChromaDB Error ---
            # If no context, or if ChromaDB failed/unavailable, get newest N facts from SQLite, applying query if present.
            logger.debug(f"Retrieving general facts from SQLite (Query: '{query}', Limit: {limit})")
            sql = "SELECT fact FROM general_facts"
            params = []
            if query:
                # Apply the LIKE query only in the SQLite fallback scenario
                sql += " WHERE fact LIKE ?"
                params.append(f"%{query}%")

            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows_ordered = await self._db_fetchall(sql, tuple(params))
            sqlite_facts = [row[0] for row in rows_ordered]
            logger.info(f"Retrieved {len(sqlite_facts)} general facts from SQLite (Query: '{query}').")
            return sqlite_facts

        except Exception as e:
            logger.error(f"Error retrieving general facts: {e}", exc_info=True)
            return []

    # --- Personality Trait Methods (SQLite) ---

    async def set_personality_trait(self, key: str, value: Any):
        """Stores or updates a personality trait in the database."""
        if not key:
            logger.error("set_personality_trait called with empty key.")
            return
        try:
            # Serialize the value to a JSON string to handle different types (str, int, float, bool)
            value_json = json.dumps(value)
            await self._db_execute(
                "INSERT OR REPLACE INTO gurt_personality (trait_key, trait_value, last_updated) VALUES (?, ?, unixepoch('now'))",
                (key, value_json)
            )
            logger.info(f"Personality trait '{key}' set/updated.")
        except Exception as e:
            logger.error(f"Error setting personality trait '{key}': {e}", exc_info=True)

    async def get_personality_trait(self, key: str) -> Optional[Any]:
        """Retrieves a specific personality trait from the database."""
        if not key:
            logger.error("get_personality_trait called with empty key.")
            return None
        try:
            row = await self._db_fetchone("SELECT trait_value FROM gurt_personality WHERE trait_key = ?", (key,))
            if row:
                # Deserialize the JSON string back to its original type
                value = json.loads(row[0])
                logger.debug(f"Retrieved personality trait '{key}': {value}")
                return value
            else:
                logger.debug(f"Personality trait '{key}' not found.")
                return None
        except Exception as e:
            logger.error(f"Error getting personality trait '{key}': {e}", exc_info=True)
            return None

    async def get_all_personality_traits(self) -> Dict[str, Any]:
        """Retrieves all personality traits from the database."""
        traits = {}
        try:
            rows = await self._db_fetchall("SELECT trait_key, trait_value FROM gurt_personality", ())
            for key, value_json in rows:
                try:
                    # Deserialize each value
                    traits[key] = json.loads(value_json)
                except json.JSONDecodeError as json_e:
                    logger.error(f"Error decoding JSON for trait '{key}': {json_e}. Value: {value_json}")
                    traits[key] = None # Or handle error differently
            logger.info(f"Retrieved {len(traits)} personality traits.")
            return traits
        except Exception as e:
            logger.error(f"Error getting all personality traits: {e}", exc_info=True)
            return {}

    async def load_baseline_personality(self, baseline_traits: Dict[str, Any]):
        """Loads baseline traits into the personality table ONLY if it's empty."""
        if not baseline_traits:
            logger.warning("load_baseline_personality called with empty baseline traits.")
            return
        try:
            # Check if the table is empty
            count_result = await self._db_fetchone("SELECT COUNT(*) FROM gurt_personality", ())
            current_count = count_result[0] if count_result else 0

            if current_count == 0:
                logger.info("Personality table is empty. Loading baseline traits...")
                for key, value in baseline_traits.items():
                    await self.set_personality_trait(key, value)
                logger.info(f"Loaded {len(baseline_traits)} baseline traits.")
            else:
                logger.info(f"Personality table already contains {current_count} traits. Skipping baseline load.")
        except Exception as e:
            logger.error(f"Error loading baseline personality: {e}", exc_info=True)

    async def load_baseline_interests(self, baseline_interests: Dict[str, float]):
        """Loads baseline interests into the interests table ONLY if it's empty."""
        if not baseline_interests:
            logger.warning("load_baseline_interests called with empty baseline interests.")
            return
        try:
            # Check if the table is empty
            count_result = await self._db_fetchone("SELECT COUNT(*) FROM gurt_interests", ())
            current_count = count_result[0] if count_result else 0

            if current_count == 0:
                logger.info("Interests table is empty. Loading baseline interests...")
                async with self.db_lock:
                    async with aiosqlite.connect(self.db_path) as db:
                        for topic, level in baseline_interests.items():
                            topic_normalized = topic.lower().strip()
                            if not topic_normalized: continue # Skip empty topics
                            # Clamp initial level just in case
                            level_clamped = max(INTEREST_MIN_LEVEL, min(INTEREST_MAX_LEVEL, level))
                            await db.execute(
                                """
                                INSERT INTO gurt_interests (interest_topic, interest_level, last_updated)
                                VALUES (?, ?, unixepoch('now'))
                                """,
                                (topic_normalized, level_clamped)
                            )
                        await db.commit()
                logger.info(f"Loaded {len(baseline_interests)} baseline interests.")
            else:
                logger.info(f"Interests table already contains {current_count} interests. Skipping baseline load.")
        except Exception as e:
            logger.error(f"Error loading baseline interests: {e}", exc_info=True)


    # --- Interest Methods (SQLite) ---

    async def update_interest(self, topic: str, change: float):
        """
        Updates the interest level for a given topic. Creates the topic if it doesn't exist.
        Clamps the interest level between INTEREST_MIN_LEVEL and INTEREST_MAX_LEVEL.

        Args:
            topic: The interest topic (e.g., "gaming", "anime").
            change: The amount to change the interest level by (can be positive or negative).
        """
        if not topic:
            logger.error("update_interest called with empty topic.")
            return
        topic = topic.lower().strip() # Normalize topic
        if not topic:
            logger.error("update_interest called with empty topic after normalization.")
            return

        try:
            async with self.db_lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # Check if topic exists
                    cursor = await db.execute("SELECT interest_level FROM gurt_interests WHERE interest_topic = ?", (topic,))
                    row = await cursor.fetchone()

                    if row:
                        current_level = row[0]
                        new_level = current_level + change
                    else:
                        # Topic doesn't exist, create it with initial level + change
                        current_level = INTEREST_INITIAL_LEVEL # Use constant for initial level
                        new_level = current_level + change
                        logger.info(f"Creating new interest: '{topic}' with initial level {current_level:.3f} + change {change:.3f}")

                    # Clamp the new level
                    new_level_clamped = max(INTEREST_MIN_LEVEL, min(INTEREST_MAX_LEVEL, new_level))

                    # Insert or update the topic
                    await db.execute(
                        """
                        INSERT INTO gurt_interests (interest_topic, interest_level, last_updated)
                        VALUES (?, ?, unixepoch('now'))
                        ON CONFLICT(interest_topic) DO UPDATE SET
                            interest_level = excluded.interest_level,
                            last_updated = excluded.last_updated;
                        """,
                        (topic, new_level_clamped)
                    )
                    await db.commit()
                    logger.info(f"Interest '{topic}' updated: {current_level:.3f} -> {new_level_clamped:.3f} (Change: {change:.3f})")

        except Exception as e:
            logger.error(f"Error updating interest '{topic}': {e}", exc_info=True)

    async def get_interests(self, limit: int = 5, min_level: float = 0.2) -> List[Tuple[str, float]]:
        """
        Retrieves the top interests above a minimum level, ordered by interest level descending.

        Args:
            limit: The maximum number of interests to return.
            min_level: The minimum interest level required to be included.

        Returns:
            A list of tuples, where each tuple is (interest_topic, interest_level).
        """
        interests = []
        try:
            rows = await self._db_fetchall(
                "SELECT interest_topic, interest_level FROM gurt_interests WHERE interest_level >= ? ORDER BY interest_level DESC LIMIT ?",
                (min_level, limit)
            )
            interests = [(row[0], row[1]) for row in rows]
            logger.info(f"Retrieved {len(interests)} interests (Limit: {limit}, Min Level: {min_level}).")
            return interests
        except Exception as e:
            logger.error(f"Error getting interests: {e}", exc_info=True)
            return []

    async def decay_interests(self, decay_rate: float = INTEREST_DECAY_RATE, decay_interval_hours: int = INTEREST_DECAY_INTERVAL_HOURS):
        """
        Applies decay to interest levels for topics not updated recently.

        Args:
            decay_rate: The fraction to reduce the interest level by (e.g., 0.01 for 1% decay).
            decay_interval_hours: Only decay interests not updated within this many hours.
        """
        if not (0 < decay_rate < 1):
            logger.error(f"Invalid decay_rate: {decay_rate}. Must be between 0 and 1.")
            return
        if decay_interval_hours <= 0:
             logger.error(f"Invalid decay_interval_hours: {decay_interval_hours}. Must be positive.")
             return

        try:
            cutoff_timestamp = time.time() - (decay_interval_hours * 3600)
            logger.info(f"Applying interest decay (Rate: {decay_rate}) for interests not updated since {datetime.datetime.fromtimestamp(cutoff_timestamp).isoformat()}...")

            async with self.db_lock:
                async with aiosqlite.connect(self.db_path) as db:
                    # Select topics eligible for decay
                    cursor = await db.execute(
                        "SELECT interest_topic, interest_level FROM gurt_interests WHERE last_updated < ?",
                        (cutoff_timestamp,)
                    )
                    topics_to_decay = await cursor.fetchall()

                    if not topics_to_decay:
                        logger.info("No interests found eligible for decay.")
                        return

                    updated_count = 0
                    # Apply decay and update
                    for topic, current_level in topics_to_decay:
                        # Calculate decay amount (ensure it doesn't go below min level instantly)
                        decay_amount = current_level * decay_rate
                        new_level = current_level - decay_amount
                        # Ensure level doesn't drop below the minimum threshold due to decay
                        new_level_clamped = max(INTEREST_MIN_LEVEL, new_level)

                        # Only update if the level actually changes significantly
                        if abs(new_level_clamped - current_level) > 0.001:
                            await db.execute(
                                "UPDATE gurt_interests SET interest_level = ? WHERE interest_topic = ?",
                                (new_level_clamped, topic)
                            )
                            logger.debug(f"Decayed interest '{topic}': {current_level:.3f} -> {new_level_clamped:.3f}")
                            updated_count += 1

                    await db.commit()
                    logger.info(f"Interest decay cycle complete. Updated {updated_count}/{len(topics_to_decay)} eligible interests.")

        except Exception as e:
            logger.error(f"Error during interest decay: {e}", exc_info=True)

    # --- Semantic Memory Methods (ChromaDB) ---

    async def add_message_embedding(self, message_id: str, formatted_message_data: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates embedding and stores a message (including attachment descriptions)
        in ChromaDB.
        """
        if not self.semantic_collection:
            return {"error": "Semantic memory (ChromaDB) is not initialized."}

        # Construct the text to embed: content + attachment descriptions
        text_to_embed_parts = []
        if formatted_message_data.get('content'):
            text_to_embed_parts.append(formatted_message_data['content'])

        attachment_descs = formatted_message_data.get('attachment_descriptions', [])
        if attachment_descs:
            # Add a separator if there's content AND attachments
            if text_to_embed_parts:
                 text_to_embed_parts.append("\n") # Add newline separator
            # Append descriptions
            for att in attachment_descs:
                text_to_embed_parts.append(att.get('description', ''))

        text_to_embed = " ".join(text_to_embed_parts).strip()

        if not text_to_embed:
             # This might happen if a message ONLY contains attachments and no text content,
             # but format_message should always produce descriptions. Log if empty.
             logger.warning(f"Message {message_id} resulted in empty text_to_embed. Original data: {formatted_message_data}")
             return {"error": "Cannot add empty derived text to semantic memory."}

        logger.info(f"Adding message {message_id} to semantic memory (including attachments).")
        try:
            # ChromaDB expects lists for inputs
            await asyncio.to_thread(
                self.semantic_collection.add,
                documents=[text_to_embed], # Embed the combined text
                metadatas=[metadata],
                ids=[message_id]
            )
            logger.info(f"Successfully added message {message_id} to ChromaDB.")
            return {"status": "success", "message_id": message_id}
        except Exception as e:
            logger.error(f"ChromaDB error adding message {message_id}: {e}", exc_info=True)
            return {"error": f"Semantic memory error adding message: {str(e)}"}

    async def search_semantic_memory(self, query_text: str, n_results: int = 5, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Searches ChromaDB for messages semantically similar to the query text."""
        if not self.semantic_collection:
            logger.warning("Search semantic memory called, but ChromaDB is not initialized.")
            return []
        if not query_text:
             logger.warning("Search semantic memory called with empty query text.")
             return []

        logger.info(f"Searching semantic memory (n_results={n_results}, filter={filter_metadata}) for query: '{query_text[:50]}...'")
        try:
            # Perform the query in a separate thread as ChromaDB operations can be blocking
            results = await asyncio.to_thread(
                self.semantic_collection.query,
                query_texts=[query_text],
                n_results=n_results,
                where=filter_metadata, # Optional filter based on metadata
                include=['metadatas', 'documents', 'distances'] # Include distance for relevance
            )
            logger.debug(f"ChromaDB query results: {results}")

            # Process results
            processed_results = []
            if results and results.get('ids') and results['ids'][0]:
                for i, doc_id in enumerate(results['ids'][0]):
                    processed_results.append({
                        "id": doc_id,
                        "document": results['documents'][0][i] if results.get('documents') else None,
                        "metadata": results['metadatas'][0][i] if results.get('metadatas') else None,
                        "distance": results['distances'][0][i] if results.get('distances') else None,
                    })
            logger.info(f"Found {len(processed_results)} semantic results.")
            return processed_results

        except Exception as e:
            logger.error(f"ChromaDB error searching memory for query '{query_text[:50]}...': {e}", exc_info=True)
            return []

    async def delete_user_fact(self, user_id: str, fact_to_delete: str) -> Dict[str, Any]:
        """Deletes a specific fact for a user from both SQLite and ChromaDB."""
        if not user_id or not fact_to_delete:
            return {"error": "user_id and fact_to_delete are required."}
        logger.info(f"Attempting to delete user fact for {user_id}: '{fact_to_delete}'")
        deleted_chroma_id = None
        try:
            # Check if fact exists and get chroma_id
            row = await self._db_fetchone("SELECT chroma_id FROM user_facts WHERE user_id = ? AND fact = ?", (user_id, fact_to_delete))
            if not row:
                logger.warning(f"Fact not found in SQLite for user {user_id}: '{fact_to_delete}'")
                return {"status": "not_found", "user_id": user_id, "fact": fact_to_delete}

            deleted_chroma_id = row[0]

            # Delete from SQLite
            await self._db_execute("DELETE FROM user_facts WHERE user_id = ? AND fact = ?", (user_id, fact_to_delete))
            logger.info(f"Deleted fact from SQLite for user {user_id}: '{fact_to_delete}'")

            # Delete from ChromaDB if chroma_id exists
            if deleted_chroma_id and self.fact_collection:
                try:
                    logger.info(f"Attempting to delete fact from ChromaDB (ID: {deleted_chroma_id}).")
                    await asyncio.to_thread(self.fact_collection.delete, ids=[deleted_chroma_id])
                    logger.info(f"Successfully deleted fact from ChromaDB (ID: {deleted_chroma_id}).")
                except Exception as chroma_e:
                    logger.error(f"ChromaDB error deleting user fact ID {deleted_chroma_id}: {chroma_e}", exc_info=True)
                    # Log error but consider SQLite deletion successful

            return {"status": "deleted", "user_id": user_id, "fact_deleted": fact_to_delete}

        except Exception as e:
            logger.error(f"Error deleting user fact for {user_id}: {e}", exc_info=True)
            return {"error": f"Database error deleting user fact: {str(e)}"}

    async def delete_general_fact(self, fact_to_delete: str) -> Dict[str, Any]:
        """Deletes a specific general fact from both SQLite and ChromaDB."""
        if not fact_to_delete:
            return {"error": "fact_to_delete is required."}
        logger.info(f"Attempting to delete general fact: '{fact_to_delete}'")
        deleted_chroma_id = None
        try:
            # Check if fact exists and get chroma_id
            row = await self._db_fetchone("SELECT chroma_id FROM general_facts WHERE fact = ?", (fact_to_delete,))
            if not row:
                logger.warning(f"General fact not found in SQLite: '{fact_to_delete}'")
                return {"status": "not_found", "fact": fact_to_delete}

            deleted_chroma_id = row[0]

            # Delete from SQLite
            await self._db_execute("DELETE FROM general_facts WHERE fact = ?", (fact_to_delete,))
            logger.info(f"Deleted general fact from SQLite: '{fact_to_delete}'")

            # Delete from ChromaDB if chroma_id exists
            if deleted_chroma_id and self.fact_collection:
                try:
                    logger.info(f"Attempting to delete general fact from ChromaDB (ID: {deleted_chroma_id}).")
                    await asyncio.to_thread(self.fact_collection.delete, ids=[deleted_chroma_id])
                    logger.info(f"Successfully deleted general fact from ChromaDB (ID: {deleted_chroma_id}).")
                except Exception as chroma_e:
                    logger.error(f"ChromaDB error deleting general fact ID {deleted_chroma_id}: {chroma_e}", exc_info=True)
                    # Log error but consider SQLite deletion successful

            return {"status": "deleted", "fact_deleted": fact_to_delete}

        except Exception as e:
            logger.error(f"Error deleting general fact: {e}", exc_info=True)
            return {"error": f"Database error deleting general fact: {str(e)}"}

    # --- Goal Management Methods (SQLite) ---

    async def add_goal(self, description: str, priority: int = 5, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Adds a new goal to the database."""
        if not description:
            return {"error": "Goal description is required."}
        logger.info(f"Adding new goal (Priority {priority}): '{description}'")
        details_json = json.dumps(details) if details else None
        try:
            # Check if goal already exists
            existing = await self._db_fetchone("SELECT goal_id FROM gurt_goals WHERE description = ?", (description,))
            if existing:
                logger.warning(f"Goal already exists: '{description}' (ID: {existing[0]})")
                return {"status": "duplicate", "goal_id": existing[0], "description": description}

            async with self.db_lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        """
                        INSERT INTO gurt_goals (description, priority, details, status, last_updated)
                        VALUES (?, ?, ?, 'pending', unixepoch('now'))
                        """,
                        (description, priority, details_json)
                    )
                    await db.commit()
                    goal_id = cursor.lastrowid
            logger.info(f"Goal added successfully (ID: {goal_id}): '{description}'")
            return {"status": "added", "goal_id": goal_id, "description": description}
        except Exception as e:
            logger.error(f"Error adding goal '{description}': {e}", exc_info=True)
            return {"error": f"Database error adding goal: {str(e)}"}

    async def get_goals(self, status: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves goals, optionally filtered by status, ordered by priority."""
        logger.info(f"Retrieving goals (Status: {status or 'any'}, Limit: {limit})")
        goals = []
        try:
            sql = "SELECT goal_id, description, status, priority, created_timestamp, last_updated, details FROM gurt_goals"
            params = []
            if status:
                sql += " WHERE status = ?"
                params.append(status)
            sql += " ORDER BY priority ASC, created_timestamp ASC LIMIT ?"
            params.append(limit)

            rows = await self._db_fetchall(sql, tuple(params))
            for row in rows:
                details = json.loads(row[6]) if row[6] else None
                goals.append({
                    "goal_id": row[0],
                    "description": row[1],
                    "status": row[2],
                    "priority": row[3],
                    "created_timestamp": row[4],
                    "last_updated": row[5],
                    "details": details
                })
            logger.info(f"Retrieved {len(goals)} goals.")
            return goals
        except Exception as e:
            logger.error(f"Error retrieving goals: {e}", exc_info=True)
            return []

    async def update_goal(self, goal_id: int, status: Optional[str] = None, priority: Optional[int] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Updates the status, priority, or details of a goal."""
        logger.info(f"Updating goal ID {goal_id} (Status: {status}, Priority: {priority}, Details: {bool(details)})")
        if not any([status, priority is not None, details is not None]):
            return {"error": "No update parameters provided."}

        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if details is not None:
            updates.append("details = ?")
            params.append(json.dumps(details))

        updates.append("last_updated = unixepoch('now')")
        params.append(goal_id)

        sql = f"UPDATE gurt_goals SET {', '.join(updates)} WHERE goal_id = ?"

        try:
            async with self.db_lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(sql, tuple(params))
                    await db.commit()
                    if cursor.rowcount == 0:
                        logger.warning(f"Goal ID {goal_id} not found for update.")
                        return {"status": "not_found", "goal_id": goal_id}
            logger.info(f"Goal ID {goal_id} updated successfully.")
            return {"status": "updated", "goal_id": goal_id}
        except Exception as e:
            logger.error(f"Error updating goal ID {goal_id}: {e}", exc_info=True)
            return {"error": f"Database error updating goal: {str(e)}"}

    async def delete_goal(self, goal_id: int) -> Dict[str, Any]:
        """Deletes a goal from the database."""
        logger.info(f"Attempting to delete goal ID {goal_id}")
        try:
            async with self.db_lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute("DELETE FROM gurt_goals WHERE goal_id = ?", (goal_id,))
                    await db.commit()
                    if cursor.rowcount == 0:
                        logger.warning(f"Goal ID {goal_id} not found for deletion.")
                        return {"status": "not_found", "goal_id": goal_id}
            logger.info(f"Goal ID {goal_id} deleted successfully.")
            return {"status": "deleted", "goal_id": goal_id}
        except Exception as e:
            logger.error(f"Error deleting goal ID {goal_id}: {e}", exc_info=True)
            return {"error": f"Database error deleting goal: {str(e)}"}

    # --- Internal Action Log Methods ---

    async def add_internal_action_log(self, tool_name: str, arguments: Optional[Dict[str, Any]], result_summary: str, reasoning: Optional[str] = None) -> Dict[str, Any]:
        """Logs the execution of an internal background action, including reasoning."""
        if not tool_name:
            return {"error": "Tool name is required for logging internal action."}
        logger.info(f"Logging internal action: Tool='{tool_name}', Args={arguments}, Reason='{reasoning}', Result='{result_summary[:100]}...'")
        args_json = json.dumps(arguments) if arguments else None
        # Truncate result summary and reasoning if too long for DB
        max_len = 1000
        truncated_summary = result_summary[:max_len] + ('...' if len(result_summary) > max_len else '')
        truncated_reasoning = reasoning[:max_len] + ('...' if reasoning and len(reasoning) > max_len else '') if reasoning else None

        try:
            async with self.db_lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        """
                        INSERT INTO internal_actions (tool_name, arguments_json, reasoning, result_summary, timestamp)
                        VALUES (?, ?, ?, ?, unixepoch('now'))
                        """,
                        (tool_name, args_json, truncated_reasoning, truncated_summary)
                    )
                    await db.commit()
                    action_id = cursor.lastrowid
            logger.info(f"Internal action logged successfully (ID: {action_id}): Tool='{tool_name}'")
            return {"status": "logged", "action_id": action_id}
        except Exception as e:
            logger.error(f"Error logging internal action '{tool_name}': {e}", exc_info=True)
            return {"error": f"Database error logging internal action: {str(e)}"}

    async def get_internal_action_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves the most recent internal action logs."""
        logger.info(f"Retrieving last {limit} internal action logs.")
        logs = []
        try:
            rows = await self._db_fetchall(
                """
                SELECT action_id, timestamp, tool_name, arguments_json, reasoning, result_summary
                FROM internal_actions
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,)
            )
            for row in rows:
                arguments = json.loads(row[3]) if row[3] else None
                logs.append({
                    "action_id": row[0],
                    "timestamp": row[1],
                    "tool_name": row[2],
                    "arguments": arguments,
                    "reasoning": row[4],
                    "result_summary": row[5]
                })
            logger.info(f"Retrieved {len(logs)} internal action logs.")
            return logs
        except Exception as e:
            logger.error(f"Error retrieving internal action logs: {e}", exc_info=True)
            return []
