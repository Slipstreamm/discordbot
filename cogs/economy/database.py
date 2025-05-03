import asyncpg
import redis.asyncio as redis # Use asyncio version of redis library
import os
import datetime
import logging
import json
from typing import Optional, List, Dict, Any, Tuple

# Configure logging
log = logging.getLogger(__name__)

# --- Global Variables ---
pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis.Redis] = None

# --- Cache Keys ---
# Using f-strings for dynamic keys
CACHE_BALANCE_KEY = "economy:balance:{user_id}"
CACHE_JOB_KEY = "economy:job:{user_id}"
CACHE_ITEM_KEY = "economy:item:{item_key}"
CACHE_INVENTORY_KEY = "economy:inventory:{user_id}"
CACHE_COOLDOWN_KEY = "economy:cooldown:{user_id}:{command_name}"
CACHE_LEADERBOARD_KEY = "economy:leaderboard:{count}"

# --- Cache Durations (in seconds) ---
CACHE_DEFAULT_TTL = 60 * 5 # 5 minutes for most things
CACHE_ITEM_TTL = 60 * 60 * 24 # 24 hours for item details (rarely change)
CACHE_LEADERBOARD_TTL = 60 * 15 # 15 minutes for leaderboard

# --- Database Setup ---

async def init_db():
    """Initializes the PostgreSQL connection pool and Redis client."""
    global pool, redis_client
    if pool and redis_client:
        log.info("Database connections already initialized.")
        return

    try:
        # --- PostgreSQL Setup ---
        db_host = os.environ.get("POSTGRES_HOST", "localhost")
        db_user = os.environ.get("POSTGRES_USER")
        db_password = os.environ.get("POSTGRES_PASSWORD")
        db_name = os.environ.get("POSTGRES_DB")
        db_port = os.environ.get("POSTGRES_PORT", 5432) # Default PostgreSQL port

        if not all([db_user, db_password, db_name]):
            log.error("Missing PostgreSQL environment variables (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)")
            raise ConnectionError("Missing PostgreSQL credentials in environment variables.")

        conn_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        pool = await asyncpg.create_pool(conn_string, min_size=1, max_size=10)
        if pool:
             log.info(f"PostgreSQL connection pool established to {db_host}:{db_port}/{db_name}")
             # Run table creation check (idempotent)
             await _create_tables_if_not_exist(pool)
        else:
             log.error("Failed to create PostgreSQL connection pool.")
             raise ConnectionError("Failed to create PostgreSQL connection pool.")


        # --- Redis Setup ---
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", 6379))

        redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True) # decode_responses=True to get strings
        await redis_client.ping() # Check connection
        log.info(f"Redis client connected to {redis_host}:{redis_port}")

    except redis.exceptions.ConnectionError as e:
        log.error(f"Failed to connect to Redis at {redis_host}:{redis_port}: {e}", exc_info=True)
        redis_client = None # Ensure client is None if connection fails
        # Decide if this is fatal - for now, let it continue but caching will fail
        log.warning("Redis connection failed. Caching will be disabled.")
    except Exception as e:
        log.error(f"Failed to initialize database connections: {e}", exc_info=True)
        # Clean up partially initialized connections if necessary
        if pool:
            await pool.close()
            pool = None
        if redis_client:
            await redis_client.close()
            redis_client = None
        raise # Re-raise the exception to prevent cog loading if critical

async def _create_tables_if_not_exist(db_pool: asyncpg.Pool):
    """Creates tables if they don't exist. Called internally by init_db."""
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Create economy table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS economy (
                    user_id BIGINT PRIMARY KEY,
                    balance BIGINT NOT NULL DEFAULT 0
                )
            """)
            log.debug("Checked/created 'economy' table in PostgreSQL.")

            # Create command_cooldowns table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS command_cooldowns (
                    user_id BIGINT NOT NULL,
                    command_name TEXT NOT NULL,
                    last_used TIMESTAMP WITH TIME ZONE NOT NULL,
                    PRIMARY KEY (user_id, command_name)
                )
            """)
            log.debug("Checked/created 'command_cooldowns' table in PostgreSQL.")

            # Create user_jobs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_jobs (
                    user_id BIGINT PRIMARY KEY,
                    job_name TEXT,
                    job_level INTEGER NOT NULL DEFAULT 1,
                    job_xp INTEGER NOT NULL DEFAULT 0,
                    last_job_action TIMESTAMP WITH TIME ZONE,
                    FOREIGN KEY (user_id) REFERENCES economy(user_id) ON DELETE CASCADE
                )
            """)
            log.debug("Checked/created 'user_jobs' table in PostgreSQL.")

            # Create items table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    sell_price BIGINT NOT NULL DEFAULT 0
                )
            """)
            log.debug("Checked/created 'items' table in PostgreSQL.")

            # Create user_inventory table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_inventory (
                    user_id BIGINT NOT NULL,
                    item_key TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (user_id, item_key),
                    FOREIGN KEY (user_id) REFERENCES economy(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (item_key) REFERENCES items(item_key) ON DELETE CASCADE
                )
            """)
            log.debug("Checked/created 'user_inventory' table in PostgreSQL.")

            # --- Add some basic items ---
            initial_items = [
                ('raw_iron', 'Raw Iron Ore', 'Basic metal ore.', 5),
                ('coal', 'Coal', 'A lump of fossil fuel.', 3),
                ('shiny_gem', 'Shiny Gem', 'A pretty, potentially valuable gem.', 50),
                ('common_fish', 'Common Fish', 'A standard fish.', 4),
                ('rare_fish', 'Rare Fish', 'An uncommon fish.', 15),
                ('treasure_chest', 'Treasure Chest', 'Might contain goodies!', 0),
                ('iron_ingot', 'Iron Ingot', 'Refined iron, ready for crafting.', 12),
                ('basic_tool', 'Basic Tool', 'A simple tool.', 25)
            ]
            # Use ON CONFLICT DO NOTHING to avoid errors if items already exist
            await conn.executemany("""
                INSERT INTO items (item_key, name, description, sell_price)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (item_key) DO NOTHING
            """, initial_items)
            log.debug("Ensured initial items exist in PostgreSQL.")

# --- Database Helper Functions ---

async def get_balance(user_id: int) -> int:
    """Gets the balance for a user, creating an entry if needed. Uses Redis cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_BALANCE_KEY.format(user_id=user_id)

    # 1. Check Cache
    if redis_client:
        try:
            cached_balance = await redis_client.get(cache_key)
            if cached_balance is not None:
                log.debug(f"Cache hit for balance user_id: {user_id}")
                return int(cached_balance)
        except Exception as e:
            log.warning(f"Redis GET failed for key {cache_key}: {e}", exc_info=True)
            # Proceed to DB query if cache fails

    log.debug(f"Cache miss for balance user_id: {user_id}")
    # 2. Query Database
    async with pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM economy WHERE user_id = $1", user_id)

        if balance is None:
            # User doesn't exist, create entry
            try:
                await conn.execute("INSERT INTO economy (user_id, balance) VALUES ($1, 0)", user_id)
                log.info(f"Created new economy entry for user_id: {user_id}")
                balance = 0
            except asyncpg.UniqueViolationError:
                # Race condition: another process inserted the user between SELECT and INSERT
                log.warning(f"Race condition handled for user_id: {user_id} during balance fetch.")
                balance = await conn.fetchval("SELECT balance FROM economy WHERE user_id = $1", user_id)
                balance = balance if balance is not None else 0 # Ensure balance is 0 if somehow still None

    # 3. Update Cache
    if redis_client:
        try:
            await redis_client.set(cache_key, balance, ex=CACHE_DEFAULT_TTL)
        except Exception as e:
            log.warning(f"Redis SET failed for key {cache_key}: {e}", exc_info=True)

    return balance if balance is not None else 0

async def update_balance(user_id: int, amount: int):
    """Updates a user's balance by adding the specified amount (can be negative). Invalidates cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_BALANCE_KEY.format(user_id=user_id)
    leaderboard_pattern = CACHE_LEADERBOARD_KEY.format(count='*') # Pattern to invalidate all leaderboard caches

    async with pool.acquire() as conn:
        # Ensure user exists first (get_balance handles creation)
        await get_balance(user_id)
        # Use RETURNING to get the new balance efficiently, though not strictly needed here
        await conn.execute("UPDATE economy SET balance = balance + $1 WHERE user_id = $2", amount, user_id)
        log.debug(f"Updated balance for user_id {user_id} by {amount}.")

    # Invalidate Caches
    if redis_client:
        try:
            # Invalidate specific user balance
            await redis_client.delete(cache_key)
            # Invalidate all leaderboard caches (since balances changed)
            async for key in redis_client.scan_iter(match=leaderboard_pattern):
                await redis_client.delete(key)
            log.debug(f"Invalidated cache for balance user_id: {user_id} and leaderboards.")
        except Exception as e:
            log.warning(f"Redis DELETE failed for balance/leaderboard invalidation (user {user_id}): {e}", exc_info=True)


async def check_cooldown(user_id: int, command_name: str) -> Optional[datetime.datetime]:
    """Checks if a command is on cooldown. Uses Redis cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_COOLDOWN_KEY.format(user_id=user_id, command_name=command_name)

    # 1. Check Cache
    if redis_client:
        try:
            cached_cooldown = await redis_client.get(cache_key)
            if cached_cooldown:
                if cached_cooldown == "NULL": # Handle explicitly stored null case
                    return None
                try:
                    # Timestamps stored in ISO format in cache
                    last_used_dt = datetime.datetime.fromisoformat(cached_cooldown)
                    # Ensure timezone aware (should be stored as UTC)
                    if last_used_dt.tzinfo is None:
                         last_used_dt = last_used_dt.replace(tzinfo=datetime.timezone.utc)
                    log.debug(f"Cache hit for cooldown user {user_id}, cmd {command_name}")
                    return last_used_dt
                except ValueError:
                     log.error(f"Could not parse cached timestamp '{cached_cooldown}' for user {user_id}, cmd {command_name}")
                     # Fall through to DB query if cache data is bad
            elif cached_cooldown is not None: # Empty string means checked DB and no cooldown exists
                 log.debug(f"Cache hit (no cooldown) for user {user_id}, cmd {command_name}")
                 return None

        except Exception as e:
            log.warning(f"Redis GET failed for key {cache_key}: {e}", exc_info=True)

    log.debug(f"Cache miss for cooldown user {user_id}, cmd {command_name}")
    # 2. Query Database
    async with pool.acquire() as conn:
        last_used_dt = await conn.fetchval(
            "SELECT last_used FROM command_cooldowns WHERE user_id = $1 AND command_name = $2",
            user_id, command_name
        )

    # 3. Update Cache
    if redis_client:
        try:
            value_to_cache = last_used_dt.isoformat() if last_used_dt else "NULL" # Store NULL explicitly
            await redis_client.set(cache_key, value_to_cache, ex=CACHE_DEFAULT_TTL)
        except Exception as e:
            log.warning(f"Redis SET failed for key {cache_key}: {e}", exc_info=True)

    return last_used_dt # Already timezone-aware from PostgreSQL TIMESTAMP WITH TIME ZONE

async def set_cooldown(user_id: int, command_name: str):
    """Sets or updates the cooldown timestamp. Invalidates cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_COOLDOWN_KEY.format(user_id=user_id, command_name=command_name)
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    async with pool.acquire() as conn:
        # Use ON CONFLICT DO UPDATE for UPSERT behavior
        await conn.execute("""
            INSERT INTO command_cooldowns (user_id, command_name, last_used)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, command_name) DO UPDATE SET last_used = EXCLUDED.last_used
        """, user_id, command_name, now_utc)
        log.debug(f"Set cooldown for user_id {user_id}, command {command_name} to {now_utc.isoformat()}")

    # Update Cache directly (faster than invalidating and re-querying)
    if redis_client:
        try:
            await redis_client.set(cache_key, now_utc.isoformat(), ex=CACHE_DEFAULT_TTL)
        except Exception as e:
            log.warning(f"Redis SET failed for key {cache_key} during update: {e}", exc_info=True)


async def get_leaderboard(count: int = 10) -> List[Tuple[int, int]]:
    """Retrieves the top users by balance. Uses Redis cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_LEADERBOARD_KEY.format(count=count)

    # 1. Check Cache
    if redis_client:
        try:
            cached_leaderboard = await redis_client.get(cache_key)
            if cached_leaderboard:
                log.debug(f"Cache hit for leaderboard (count={count})")
                # Data stored as JSON string in cache
                return json.loads(cached_leaderboard)
        except Exception as e:
            log.warning(f"Redis GET failed for key {cache_key}: {e}", exc_info=True)

    log.debug(f"Cache miss for leaderboard (count={count})")
    # 2. Query Database
    async with pool.acquire() as conn:
        results = await conn.fetch(
            "SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT $1",
            count
        )
        # Convert asyncpg Records to simple list of tuples
        leaderboard_data = [(r['user_id'], r['balance']) for r in results]

    # 3. Update Cache
    if redis_client:
        try:
            # Store as JSON string
            await redis_client.set(cache_key, json.dumps(leaderboard_data), ex=CACHE_LEADERBOARD_TTL)
        except Exception as e:
            log.warning(f"Redis SET failed for key {cache_key}: {e}", exc_info=True)

    return leaderboard_data

# --- Job Functions ---

async def get_user_job(user_id: int) -> Optional[Dict[str, Any]]:
    """Gets the user's job details. Uses Redis cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_JOB_KEY.format(user_id=user_id)

    # 1. Check Cache
    if redis_client:
        try:
            cached_job = await redis_client.get(cache_key)
            if cached_job:
                log.debug(f"Cache hit for job user_id: {user_id}")
                job_data = json.loads(cached_job)
                # Convert timestamp string back to datetime object
                if job_data.get("last_action"):
                    try:
                        job_data["last_action"] = datetime.datetime.fromisoformat(job_data["last_action"])
                    except (ValueError, TypeError):
                         log.error(f"Could not parse cached job timestamp '{job_data['last_action']}' for user {user_id}")
                         job_data["last_action"] = None # Set to None if parsing fails
                return job_data
        except Exception as e:
            log.warning(f"Redis GET failed for key {cache_key}: {e}", exc_info=True)

    log.debug(f"Cache miss for job user_id: {user_id}")
    # 2. Query Database
    async with pool.acquire() as conn:
        # Ensure user exists in economy table first
        await get_balance(user_id)
        # Fetch job details
        job_record = await conn.fetchrow(
            "SELECT job_name, job_level, job_xp, last_job_action FROM user_jobs WHERE user_id = $1",
            user_id
        )

        job_data: Optional[Dict[str, Any]] = None
        if job_record:
            job_data = {
                "name": job_record['job_name'],
                "level": job_record['job_level'],
                "xp": job_record['job_xp'],
                "last_action": job_record['last_job_action'] # Already timezone-aware
            }
        else:
            # Create job entry if it doesn't exist
            try:
                await conn.execute(
                    "INSERT INTO user_jobs (user_id, job_name, job_level, job_xp, last_job_action) VALUES ($1, NULL, 1, 0, NULL)",
                    user_id
                )
                log.info(f"Created default job entry for user_id: {user_id}")
                job_data = {"name": None, "level": 1, "xp": 0, "last_action": None}
            except asyncpg.UniqueViolationError:
                log.warning(f"Race condition handled for user_id: {user_id} during job fetch.")
                job_record_retry = await conn.fetchrow(
                    "SELECT job_name, job_level, job_xp, last_job_action FROM user_jobs WHERE user_id = $1",
                    user_id
                )
                if job_record_retry:
                     job_data = {
                        "name": job_record_retry['job_name'],
                        "level": job_record_retry['job_level'],
                        "xp": job_record_retry['job_xp'],
                        "last_action": job_record_retry['last_job_action']
                    }
                else: # Should not happen, but handle defensively
                    job_data = {"name": None, "level": 1, "xp": 0, "last_action": None}

    # 3. Update Cache
    if redis_client and job_data is not None:
        try:
            # Convert datetime to ISO string for JSON serialization
            job_data_to_cache = job_data.copy()
            if job_data_to_cache.get("last_action"):
                job_data_to_cache["last_action"] = job_data_to_cache["last_action"].isoformat()

            await redis_client.set(cache_key, json.dumps(job_data_to_cache), ex=CACHE_DEFAULT_TTL)
        except Exception as e:
            log.warning(f"Redis SET failed for key {cache_key}: {e}", exc_info=True)

    return job_data

async def set_user_job(user_id: int, job_name: Optional[str]):
    """Sets or clears a user's job. Resets level/xp. Invalidates cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_JOB_KEY.format(user_id=user_id)

    async with pool.acquire() as conn:
        # Ensure job entry exists
        await get_user_job(user_id)
        # Update job, resetting level/xp
        await conn.execute(
            "UPDATE user_jobs SET job_name = $1, job_level = 1, job_xp = 0 WHERE user_id = $2",
            job_name, user_id
        )
        log.info(f"Set job for user_id {user_id} to {job_name}. Level/XP reset.")

    # Invalidate Cache
    if redis_client:
        try:
            await redis_client.delete(cache_key)
            log.debug(f"Invalidated cache for job user_id: {user_id}")
        except Exception as e:
            log.warning(f"Redis DELETE failed for key {cache_key}: {e}", exc_info=True)

async def add_job_xp(user_id: int, xp_amount: int) -> Tuple[int, int, bool]:
    """Adds XP to the user's job, handles level ups. Invalidates cache. Returns (new_level, new_xp, did_level_up)."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_JOB_KEY.format(user_id=user_id)

    async with pool.acquire() as conn:
        # Use transaction to ensure atomicity of read-modify-write
        async with conn.transaction():
            job_info = await conn.fetchrow(
                 "SELECT job_name, job_level, job_xp FROM user_jobs WHERE user_id = $1 FOR UPDATE", # Lock row
                 user_id
            )

            if not job_info or not job_info['job_name']:
                log.warning(f"Attempted to add XP to user {user_id} with no job.")
                return (1, 0, False)

            current_level = job_info["job_level"]
            current_xp = job_info["job_xp"]
            new_xp = current_xp + xp_amount
            did_level_up = False

            # --- Leveling Logic ---
            xp_needed = current_level * 100

            while new_xp >= xp_needed:
                new_xp -= xp_needed
                current_level += 1
                xp_needed = current_level * 100
                did_level_up = True
                log.info(f"User {user_id} leveled up their job to {current_level}!")

            # Update database
            await conn.execute(
                "UPDATE user_jobs SET job_level = $1, job_xp = $2 WHERE user_id = $3",
                current_level, new_xp, user_id
            )
            log.debug(f"Updated job XP for user {user_id}. New Level: {current_level}, New XP: {new_xp}")

    # Invalidate Cache outside transaction
    if redis_client:
        try:
            await redis_client.delete(cache_key)
            log.debug(f"Invalidated cache for job user_id: {user_id} after XP update.")
        except Exception as e:
            log.warning(f"Redis DELETE failed for key {cache_key} after XP update: {e}", exc_info=True)

    return (current_level, new_xp, did_level_up)

async def set_job_cooldown(user_id: int):
    """Sets the job cooldown timestamp. Invalidates cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_JOB_KEY.format(user_id=user_id)
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_jobs SET last_job_action = $1 WHERE user_id = $2",
            now_utc, user_id
        )
        log.debug(f"Set job cooldown for user_id {user_id} to {now_utc.isoformat()}")

    # Invalidate Cache
    if redis_client:
        try:
            await redis_client.delete(cache_key)
            log.debug(f"Invalidated cache for job user_id: {user_id} after setting cooldown.")
        except Exception as e:
            log.warning(f"Redis DELETE failed for key {cache_key} after setting cooldown: {e}", exc_info=True)

# --- Item/Inventory Functions ---

async def get_item_details(item_key: str) -> Optional[Dict[str, Any]]:
    """Gets details for a specific item. Uses Redis cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_ITEM_KEY.format(item_key=item_key)

    # 1. Check Cache
    if redis_client:
        try:
            cached_item = await redis_client.get(cache_key)
            if cached_item:
                log.debug(f"Cache hit for item: {item_key}")
                return json.loads(cached_item)
        except Exception as e:
            log.warning(f"Redis GET failed for key {cache_key}: {e}", exc_info=True)

    log.debug(f"Cache miss for item: {item_key}")
    # 2. Query Database
    async with pool.acquire() as conn:
        item_record = await conn.fetchrow(
            "SELECT name, description, sell_price FROM items WHERE item_key = $1",
            item_key
        )

        item_data: Optional[Dict[str, Any]] = None
        if item_record:
            item_data = {
                "key": item_key,
                "name": item_record['name'],
                "description": item_record['description'],
                "sell_price": item_record['sell_price']
            }

    # 3. Update Cache (use longer TTL for items)
    if redis_client and item_data:
        try:
            await redis_client.set(cache_key, json.dumps(item_data), ex=CACHE_ITEM_TTL)
        except Exception as e:
            log.warning(f"Redis SET failed for key {cache_key}: {e}", exc_info=True)

    return item_data

async def get_inventory(user_id: int) -> List[Dict[str, Any]]:
    """Gets a user's inventory. Uses Redis cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_INVENTORY_KEY.format(user_id=user_id)

    # 1. Check Cache
    if redis_client:
        try:
            cached_inventory = await redis_client.get(cache_key)
            if cached_inventory:
                log.debug(f"Cache hit for inventory user_id: {user_id}")
                return json.loads(cached_inventory)
        except Exception as e:
            log.warning(f"Redis GET failed for key {cache_key}: {e}", exc_info=True)

    log.debug(f"Cache miss for inventory user_id: {user_id}")
    # 2. Query Database
    inventory = []
    async with pool.acquire() as conn:
        results = await conn.fetch("""
            SELECT inv.item_key, inv.quantity, i.name, i.description, i.sell_price
            FROM user_inventory inv
            JOIN items i ON inv.item_key = i.item_key
            WHERE inv.user_id = $1
            ORDER BY i.name
        """, user_id)
        for row in results:
            inventory.append({
                "key": row['item_key'],
                "quantity": row['quantity'],
                "name": row['name'],
                "description": row['description'],
                "sell_price": row['sell_price']
            })

    # 3. Update Cache
    if redis_client:
        try:
            await redis_client.set(cache_key, json.dumps(inventory), ex=CACHE_DEFAULT_TTL)
        except Exception as e:
            log.warning(f"Redis SET failed for key {cache_key}: {e}", exc_info=True)

    return inventory

async def add_item_to_inventory(user_id: int, item_key: str, quantity: int = 1):
    """Adds an item to the user's inventory. Invalidates cache."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_INVENTORY_KEY.format(user_id=user_id)

    if quantity <= 0:
        log.warning(f"Attempted to add non-positive quantity ({quantity}) of item {item_key} for user {user_id}")
        return

    # Check if item exists (can use cached version)
    item_details = await get_item_details(item_key)
    if not item_details:
        log.error(f"Attempted to add non-existent item '{item_key}' to inventory for user {user_id}")
        return

    async with pool.acquire() as conn:
        # Ensure user exists in economy table
        await get_balance(user_id)
        # Use ON CONFLICT DO UPDATE for UPSERT behavior
        await conn.execute("""
            INSERT INTO user_inventory (user_id, item_key, quantity)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, item_key) DO UPDATE SET quantity = user_inventory.quantity + EXCLUDED.quantity
        """, user_id, item_key, quantity)
        log.debug(f"Added {quantity} of {item_key} to user {user_id}'s inventory.")

    # Invalidate Cache
    if redis_client:
        try:
            await redis_client.delete(cache_key)
            log.debug(f"Invalidated cache for inventory user_id: {user_id}")
        except Exception as e:
            log.warning(f"Redis DELETE failed for key {cache_key}: {e}", exc_info=True)

async def remove_item_from_inventory(user_id: int, item_key: str, quantity: int = 1) -> bool:
    """Removes an item from the user's inventory. Invalidates cache. Returns True if successful."""
    if not pool: raise ConnectionError("Database pool not initialized.")
    cache_key = CACHE_INVENTORY_KEY.format(user_id=user_id)

    if quantity <= 0:
        log.warning(f"Attempted to remove non-positive quantity ({quantity}) of item {item_key} for user {user_id}")
        return False

    success = False
    async with pool.acquire() as conn:
        # Use transaction for check-then-delete/update
        async with conn.transaction():
            current_quantity = await conn.fetchval(
                "SELECT quantity FROM user_inventory WHERE user_id = $1 AND item_key = $2 FOR UPDATE", # Lock row
                user_id, item_key
            )

            if current_quantity is None or current_quantity < quantity:
                log.debug(f"User {user_id} does not have enough {item_key} (needs {quantity}, has {current_quantity or 0})")
                success = False # Explicitly set success to False
                # No need to rollback explicitly, transaction context manager handles it
            else:
                if current_quantity == quantity:
                    await conn.execute("DELETE FROM user_inventory WHERE user_id = $1 AND item_key = $2", user_id, item_key)
                else:
                    await conn.execute("UPDATE user_inventory SET quantity = quantity - $1 WHERE user_id = $2 AND item_key = $3", quantity, user_id, item_key)
                log.debug(f"Removed {quantity} of {item_key} from user {user_id}'s inventory.")
                success = True # Set success to True only if operations succeed

    # Invalidate Cache only if removal was successful
    if success and redis_client:
        try:
            await redis_client.delete(cache_key)
            log.debug(f"Invalidated cache for inventory user_id: {user_id}")
        except Exception as e:
            log.warning(f"Redis DELETE failed for key {cache_key}: {e}", exc_info=True)

    return success

async def close_db():
    """Closes the PostgreSQL pool and Redis client."""
    global pool, redis_client
    if pool:
        await pool.close()
        pool = None
        log.info("PostgreSQL connection pool closed.")
    if redis_client:
        await redis_client.close()
        redis_client = None
        log.info("Redis client closed.")
