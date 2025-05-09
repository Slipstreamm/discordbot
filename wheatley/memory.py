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
# Use a specific logger name for Wheatley's memory
logger = logging.getLogger('wheatley_memory')

# Constants (Removed Interest constants)

# --- Helper Function for Keyword Scoring (Kept for potential future use, but unused currently) ---
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
    """Handles database interactions for Wheatley's memory (facts and semantic).""" # Updated docstring

    def __init__(self, db_path: str, max_user_facts: int = 20, max_general_facts: int = 100, semantic_model_name: str = 'all-MiniLM-L6-v2', chroma_path: str = "data/chroma_db_wheatley"): # Changed default chroma_path
        self.db_path = db_path
        self.max_user_facts = max_user_facts
        self.max_general_facts = max_general_facts
        self.db_lock = asyncio.Lock() # Lock for SQLite operations

        # Ensure data directories exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(chroma_path, exist_ok=True)
        logger.info(f"Wheatley MemoryManager initialized with db_path: {self.db_path}, chroma_path: {chroma_path}") # Updated text

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

            logger.info("Getting/Creating ChromaDB collection 'wheatley_semantic_memory'...") # Renamed collection
            # Get or create the collection with the custom embedding function
            self.semantic_collection = self.chroma_client.get_or_create_collection(
                name="wheatley_semantic_memory", # Renamed collection
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"} # Use cosine distance for similarity
            )
            logger.info("ChromaDB message collection initialized successfully.")

            logger.info("Getting/Creating ChromaDB collection 'wheatley_fact_memory'...") # Renamed collection
            # Get or create the collection for facts
            self.fact_collection = self.chroma_client.get_or_create_collection(
                name="wheatley_fact_memory", # Renamed collection
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
                cursor = await db.execute("PRAGMA table_info(user_facts)")
                columns = await cursor.fetchall()
                column_names = [column[1] for column in columns]
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
                cursor = await db.execute("PRAGMA table_info(general_facts)")
                columns = await cursor.fetchall()
                column_names = [column[1] for column in columns]
                if 'chroma_id' not in column_names:
                    logger.info("Adding chroma_id column to general_facts table")
                    await db.execute("ALTER TABLE general_facts ADD COLUMN chroma_id TEXT")
            except Exception as e:
                logger.error(f"Error checking/adding chroma_id column to general_facts: {e}", exc_info=True)

            # Create index for general_facts
            await db.execute("CREATE INDEX IF NOT EXISTS idx_general_facts_chroma_id ON general_facts (chroma_id);") # Index for chroma_id

            # --- Removed Personality Table ---
            # --- Removed Interests Table ---
            # --- Removed Goals Table ---

            await db.commit()
            logger.info(f"Wheatley SQLite database initialized/verified at {self.db_path}") # Updated text

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

    # --- Personality Trait Methods (REMOVED) ---
    # --- Interest Methods (REMOVED) ---
    # --- Goal Management Methods (REMOVED) ---

    # --- Semantic Memory Methods (ChromaDB) ---

    async def add_message_embedding(self, message_id: str, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Generates embedding and stores a message in ChromaDB."""
        if not self.semantic_collection:
            return {"error": "Semantic memory (ChromaDB) is not initialized."}
        if not text:
             return {"error": "Cannot add empty text to semantic memory."}

        logger.info(f"Adding message {message_id} to semantic memory.")
        try:
            # ChromaDB expects lists for inputs
            await asyncio.to_thread(
                self.semantic_collection.add,
                documents=[text],
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
