import aiosqlite
import asyncio
import os
import time
import datetime
import re
from typing import Dict, List, Any, Optional, Tuple
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        self.semantic_collection = None
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
            )
            logger.info("ChromaDB collection initialized successfully.")

        except Exception as e:
            logger.error(f"Failed to initialize semantic memory: {e}", exc_info=True)
            # Set components to None to indicate failure
            self.chroma_client = None
            self.transformer_model = None
            self.embedding_function = None
            self.semantic_collection = None

    async def initialize_sqlite_database(self):
        """Initializes the SQLite database and creates tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    timestamp REAL DEFAULT (unixepoch('now')),
                    PRIMARY KEY (user_id, fact)
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_user_facts_user ON user_facts (user_id);")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS general_facts (
                    fact TEXT PRIMARY KEY NOT NULL,
                    timestamp REAL DEFAULT (unixepoch('now'))
                );
            """)
            # Removed channel/user state tables for brevity, can be added back if needed
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
            existing = await self._db_fetchone("SELECT 1 FROM user_facts WHERE user_id = ? AND fact = ?", (user_id, fact))
            if existing:
                logger.info(f"Fact already known for user {user_id}.")
                return {"status": "duplicate", "user_id": user_id, "fact": fact}

            count_result = await self._db_fetchone("SELECT COUNT(*) FROM user_facts WHERE user_id = ?", (user_id,))
            current_count = count_result[0] if count_result else 0

            status = "added"
            if current_count >= self.max_user_facts:
                logger.warning(f"User {user_id} fact limit ({self.max_user_facts}) reached. Deleting oldest.")
                oldest_fact_row = await self._db_fetchone("SELECT fact FROM user_facts WHERE user_id = ? ORDER BY timestamp ASC LIMIT 1", (user_id,))
                if oldest_fact_row:
                    await self._db_execute("DELETE FROM user_facts WHERE user_id = ? AND fact = ?", (user_id, oldest_fact_row[0]))
                    logger.info(f"Deleted oldest fact for user {user_id}: '{oldest_fact_row[0]}'")
                    status = "limit_reached" # Indicate limit was hit but fact was added

            await self._db_execute("INSERT INTO user_facts (user_id, fact) VALUES (?, ?)", (user_id, fact))
            logger.info(f"Fact added for user {user_id}.")
            return {"status": status, "user_id": user_id, "fact_added": fact}

        except Exception as e:
            logger.error(f"SQLite error adding user fact for {user_id}: {e}", exc_info=True)
            return {"error": f"Database error adding user fact: {str(e)}"}

    async def get_user_facts(self, user_id: str, context: Optional[str] = None) -> List[str]:
        """Retrieves stored facts about a user, optionally scored by relevance to context."""
        if not user_id:
            logger.warning("get_user_facts called without user_id.")
            return []
        logger.info(f"Retrieving facts for user {user_id} (context provided: {bool(context)})")
        try:
            rows = await self._db_fetchall("SELECT fact FROM user_facts WHERE user_id = ?", (user_id,))
            user_facts = [row[0] for row in rows]

            if context and user_facts:
                # Score facts based on context if provided
                scored_facts = []
                for fact in user_facts:
                    score = calculate_keyword_score(fact, context)
                    scored_facts.append({"fact": fact, "score": score})

                # Sort by score (descending), then fallback to original order (implicitly newest first if DB returns that way)
                scored_facts.sort(key=lambda x: x["score"], reverse=True)
                # Return top N facts based on score
                return [item["fact"] for item in scored_facts[:self.max_user_facts]]
            else:
                # No context or no facts, return newest N facts (assuming DB returns in insertion order or we add ORDER BY timestamp DESC)
                # Let's add ORDER BY timestamp DESC to be explicit
                 rows_ordered = await self._db_fetchall(
                     "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                     (user_id, self.max_user_facts)
                 )
                 return [row[0] for row in rows_ordered]

        except Exception as e:
            logger.error(f"SQLite error retrieving user facts for {user_id}: {e}", exc_info=True)
            return []

    # --- General Fact Memory Methods (SQLite + Relevance) ---

    async def add_general_fact(self, fact: str) -> Dict[str, Any]:
        """Stores a general fact in the SQLite database, enforcing limits."""
        if not fact:
            return {"error": "fact is required."}
        logger.info(f"Attempting to add general fact: '{fact}'")
        try:
            existing = await self._db_fetchone("SELECT 1 FROM general_facts WHERE fact = ?", (fact,))
            if existing:
                logger.info(f"General fact already known: '{fact}'")
                return {"status": "duplicate", "fact": fact}

            count_result = await self._db_fetchone("SELECT COUNT(*) FROM general_facts", ())
            current_count = count_result[0] if count_result else 0

            status = "added"
            if current_count >= self.max_general_facts:
                logger.warning(f"General fact limit ({self.max_general_facts}) reached. Deleting oldest.")
                oldest_fact_row = await self._db_fetchone("SELECT fact FROM general_facts ORDER BY timestamp ASC LIMIT 1", ())
                if oldest_fact_row:
                    await self._db_execute("DELETE FROM general_facts WHERE fact = ?", (oldest_fact_row[0],))
                    logger.info(f"Deleted oldest general fact: '{oldest_fact_row[0]}'")
                    status = "limit_reached"

            await self._db_execute("INSERT INTO general_facts (fact) VALUES (?)", (fact,))
            logger.info(f"General fact added: '{fact}'")
            return {"status": status, "fact_added": fact}

        except Exception as e:
            logger.error(f"SQLite error adding general fact: {e}", exc_info=True)
            return {"error": f"Database error adding general fact: {str(e)}"}

    async def get_general_facts(self, query: Optional[str] = None, limit: Optional[int] = 10, context: Optional[str] = None) -> List[str]:
        """Retrieves stored general facts, optionally filtering and scoring by relevance."""
        logger.info(f"Retrieving general facts (query='{query}', limit={limit}, context provided: {bool(context)})")
        limit = min(max(1, limit or 10), 50)

        try:
            sql = "SELECT fact FROM general_facts"
            params = []
            if query:
                sql += " WHERE fact LIKE ?"
                params.append(f"%{query}%")

            # Fetch all matching facts first for scoring
            rows = await self._db_fetchall(sql, tuple(params))
            all_facts = [row[0] for row in rows]

            if context and all_facts:
                # Score facts based on context
                scored_facts = []
                for fact in all_facts:
                    score = calculate_keyword_score(fact, context)
                    scored_facts.append({"fact": fact, "score": score})

                # Sort by score (descending)
                scored_facts.sort(key=lambda x: x["score"], reverse=True)
                # Return top N facts based on score
                return [item["fact"] for item in scored_facts[:limit]]
            else:
                # No context or no facts, return newest N facts matching query (if any)
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                rows_ordered = await self._db_fetchall(sql, tuple(params))
                return [row[0] for row in rows_ordered]

        except Exception as e:
            logger.error(f"SQLite error retrieving general facts: {e}", exc_info=True)
            return []

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
