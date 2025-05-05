import asyncpg
import redis.asyncio as redis
import os
import logging
import asyncio
from dotenv import load_dotenv
from typing import Dict

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# --- Configuration ---
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_DB = os.getenv("POSTGRES_SETTINGS_DB") # Use the new settings DB
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT", 6379)
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") # Optional

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DB}"
REDIS_URL = f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/0" # Use DB 0 for settings cache

# --- Global Connection Pools ---
pg_pool = None
redis_pool = None

# --- Logging ---
log = logging.getLogger(__name__)

# --- Connection Management ---
async def initialize_pools():
    """Initializes the PostgreSQL and Redis connection pools."""
    global pg_pool, redis_pool
    log.info("Initializing database and cache connection pools...")

    # Close existing pools if they exist
    if pg_pool:
        log.info("Closing existing PostgreSQL pool before reinitializing...")
        await pg_pool.close()
        pg_pool = None

    if redis_pool:
        log.info("Closing existing Redis pool before reinitializing...")
        await redis_pool.close()
        redis_pool = None

    # Initialize new pools
    try:
        # Create PostgreSQL pool with more conservative settings
        # Increase max_inactive_connection_lifetime to avoid connections being closed too quickly
        pg_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            max_inactive_connection_lifetime=60.0,  # 60 seconds (default is 10 minutes)
            command_timeout=30.0  # 30 seconds timeout for commands
        )
        log.info(f"PostgreSQL pool connected to {POSTGRES_HOST}/{POSTGRES_DB}")

        # Create Redis pool with connection_cls=None to avoid event loop issues
        # This creates a connection pool that doesn't bind to a specific event loop
        redis_pool = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            max_connections=20,  # Limit max connections
            socket_timeout=5.0,  # 5 second timeout for operations
            socket_connect_timeout=3.0,  # 3 second timeout for connections
            retry_on_timeout=True,  # Retry on timeout
            health_check_interval=30  # Check connection health every 30 seconds
        )

        # Test connection with a timeout
        try:
            await asyncio.wait_for(redis_pool.ping(), timeout=5.0)
            log.info(f"Redis pool connected to {REDIS_HOST}:{REDIS_PORT}")
        except asyncio.TimeoutError:
            log.error(f"Redis connection timeout when connecting to {REDIS_HOST}:{REDIS_PORT}")
            raise

        # Initialize database schema
        await initialize_database()  # Ensure tables exist

        # Run database migrations
        await run_migrations()  # Apply any necessary migrations

        return True  # Indicate successful initialization
    except Exception as e:
        log.exception(f"Failed to initialize connection pools: {e}")
        # Clean up any partially initialized resources
        if pg_pool:
            await pg_pool.close()
            pg_pool = None
        if redis_pool:
            await redis_pool.close()
            redis_pool = None
        # Raise the exception to be handled by the caller
        raise

async def close_pools():
    """Closes the PostgreSQL and Redis connection pools gracefully."""
    global pg_pool, redis_pool
    log.info("Closing database and cache connection pools...")
    if redis_pool:
        try:
            await redis_pool.close()
            log.info("Redis pool closed.")
        except Exception as e:
            log.exception(f"Error closing Redis pool: {e}")
        redis_pool = None # Ensure it's marked as closed

    if pg_pool:
        try:
            await pg_pool.close()
            log.info("PostgreSQL pool closed.")
        except Exception as e:
            log.exception(f"Error closing PostgreSQL pool: {e}")
        pg_pool = None # Ensure it's marked as closed


# --- Database Schema Initialization ---
async def run_migrations():
    """Run database migrations to update schema."""
    if not pg_pool:
        log.error("PostgreSQL pool not initialized. Cannot run migrations.")
        return

    log.info("Running database migrations...")
    try:
        async with pg_pool.acquire() as conn:
            # Check if custom_command_description column exists in command_customization table
            column_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'command_customization'
                    AND column_name = 'custom_command_description'
                );
            """)

            if not column_exists:
                log.info("Adding custom_command_description column to command_customization table...")
                await conn.execute("""
                    ALTER TABLE command_customization
                    ADD COLUMN custom_command_description TEXT;
                """)
                log.info("Added custom_command_description column successfully.")
            else:
                log.debug("custom_command_description column already exists in command_customization table.")

    except Exception as e:
        log.exception(f"Error running database migrations: {e}")


async def initialize_database():
    """Creates necessary tables in the PostgreSQL database if they don't exist."""
    if not pg_pool:
        log.error("PostgreSQL pool not initialized. Cannot initialize database.")
        return

    log.info("Initializing database schema...")
    async with pg_pool.acquire() as conn:
        async with conn.transaction():
            # Guilds table (to track known guilds, maybe store basic info later)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guilds (
                    guild_id BIGINT PRIMARY KEY
                );
            """)

            # Guild Settings table (key-value store for various settings)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id BIGINT NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT,
                    PRIMARY KEY (guild_id, setting_key),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)
            # Example setting_keys: 'prefix', 'welcome_channel_id', 'welcome_message', 'goodbye_channel_id', 'goodbye_message'

            # Enabled Cogs table - Stores the explicit enabled/disabled state
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS enabled_cogs (
                    guild_id BIGINT NOT NULL,
                    cog_name TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL,
                    PRIMARY KEY (guild_id, cog_name),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Enabled Commands table - Stores the explicit enabled/disabled state for individual commands
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS enabled_commands (
                    guild_id BIGINT NOT NULL,
                    command_name TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL,
                    PRIMARY KEY (guild_id, command_name),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Command Permissions table (simple role-based for now)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS command_permissions (
                    guild_id BIGINT NOT NULL,
                    command_name TEXT NOT NULL,
                    allowed_role_id BIGINT NOT NULL,
                    PRIMARY KEY (guild_id, command_name, allowed_role_id),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Command Customization table - Stores guild-specific command names and descriptions
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS command_customization (
                    guild_id BIGINT NOT NULL,
                    original_command_name TEXT NOT NULL,
                    custom_command_name TEXT NOT NULL,
                    custom_command_description TEXT,
                    PRIMARY KEY (guild_id, original_command_name),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Command Group Customization table - Stores guild-specific command group names
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS command_group_customization (
                    guild_id BIGINT NOT NULL,
                    original_group_name TEXT NOT NULL,
                    custom_group_name TEXT NOT NULL,
                    PRIMARY KEY (guild_id, original_group_name),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Command Aliases table - Stores additional aliases for commands
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS command_aliases (
                    guild_id BIGINT NOT NULL,
                    original_command_name TEXT NOT NULL,
                    alias_name TEXT NOT NULL,
                    PRIMARY KEY (guild_id, original_command_name, alias_name),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Starboard Settings table - Stores configuration for the starboard feature
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS starboard_settings (
                    guild_id BIGINT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    star_emoji TEXT NOT NULL DEFAULT '⭐',
                    threshold INTEGER NOT NULL DEFAULT 3,
                    starboard_channel_id BIGINT,
                    ignore_bots BOOLEAN NOT NULL DEFAULT TRUE,
                    self_star BOOLEAN NOT NULL DEFAULT FALSE,
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Starboard Entries table - Tracks which messages have been reposted to the starboard
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS starboard_entries (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    original_message_id BIGINT NOT NULL,
                    original_channel_id BIGINT NOT NULL,
                    starboard_message_id BIGINT NOT NULL,
                    author_id BIGINT NOT NULL,
                    star_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    UNIQUE(guild_id, original_message_id),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Starboard Reactions table - Tracks which users have starred which messages
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS starboard_reactions (
                    guild_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    PRIMARY KEY (guild_id, message_id, user_id),
                    FOREIGN KEY (guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
                );
            """)

            # Consider adding indexes later for performance on large tables
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_guild_settings_guild ON guild_settings (guild_id);")
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_enabled_cogs_guild ON enabled_cogs (guild_id);")
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_command_permissions_guild ON command_permissions (guild_id);")
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_command_customization_guild ON command_customization (guild_id);")
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_command_group_customization_guild ON command_group_customization (guild_id);")
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_command_aliases_guild ON command_aliases (guild_id);")
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_starboard_entries_guild ON starboard_entries (guild_id);")
            # await conn.execute("CREATE INDEX IF NOT EXISTS idx_starboard_reactions_guild ON starboard_reactions (guild_id);")

    log.info("Database schema initialization complete.")


# --- Starboard Functions ---

async def get_starboard_settings(guild_id: int):
    """Gets the starboard settings for a guild."""
    if not pg_pool:
        log.warning(f"PostgreSQL pool not initialized, returning None for starboard settings.")
        return None

    try:
        async with pg_pool.acquire() as conn:
            # Check if the guild exists in the starboard_settings table
            settings = await conn.fetchrow(
                """
                SELECT * FROM starboard_settings WHERE guild_id = $1
                """,
                guild_id
            )

            if settings:
                return dict(settings)

            # If no settings exist, insert default settings
            await conn.execute(
                """
                INSERT INTO starboard_settings (guild_id)
                VALUES ($1)
                ON CONFLICT (guild_id) DO NOTHING;
                """,
                guild_id
            )

            # Fetch the newly inserted default settings
            settings = await conn.fetchrow(
                """
                SELECT * FROM starboard_settings WHERE guild_id = $1
                """,
                guild_id
            )

            return dict(settings) if settings else None
    except Exception as e:
        log.exception(f"Database error getting starboard settings for guild {guild_id}: {e}")
        return None

async def update_starboard_settings(guild_id: int, **kwargs):
    """Updates starboard settings for a guild.

    Args:
        guild_id: The ID of the guild to update settings for
        **kwargs: Key-value pairs of settings to update
            Possible keys: enabled, star_emoji, threshold, starboard_channel_id, ignore_bots, self_star

    Returns:
        bool: True if successful, False otherwise
    """
    if not pg_pool:
        log.error(f"PostgreSQL pool not initialized, cannot update starboard settings.")
        return False

    valid_keys = {'enabled', 'star_emoji', 'threshold', 'starboard_channel_id', 'ignore_bots', 'self_star'}
    update_dict = {k: v for k, v in kwargs.items() if k in valid_keys}

    if not update_dict:
        log.warning(f"No valid settings provided for starboard update for guild {guild_id}")
        return False

    # Use a timeout to prevent hanging on database operations
    try:
        # Acquire a connection with a timeout
        conn = None
        try:
            conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

            # Ensure guild exists
            try:
                await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            except Exception as e:
                if "another operation is in progress" in str(e) or "attached to a different loop" in str(e):
                    log.warning(f"Connection issue when inserting guild {guild_id}: {e}")
                    # Try to reset the connection
                    await conn.close()
                    conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)
                else:
                    raise

            # Build the SET clause for the UPDATE statement
            set_clause = ", ".join(f"{key} = ${i+2}" for i, key in enumerate(update_dict.keys()))
            values = [guild_id] + list(update_dict.values())

            # Update the settings
            try:
                await conn.execute(
                    f"""
                    INSERT INTO starboard_settings (guild_id)
                    VALUES ($1)
                    ON CONFLICT (guild_id) DO UPDATE SET {set_clause};
                    """,
                    *values
                )
            except Exception as e:
                if "another operation is in progress" in str(e) or "attached to a different loop" in str(e):
                    log.warning(f"Connection issue when updating starboard settings for guild {guild_id}: {e}")
                    # Try to reset the connection
                    await conn.close()
                    conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

                    # Try again with the new connection
                    await conn.execute(
                        f"""
                        INSERT INTO starboard_settings (guild_id)
                        VALUES ($1)
                        ON CONFLICT (guild_id) DO UPDATE SET {set_clause};
                        """,
                        *values
                    )
                else:
                    raise

            log.info(f"Updated starboard settings for guild {guild_id}: {update_dict}")
            return True
        finally:
            # Always release the connection back to the pool
            if conn:
                await pg_pool.release(conn)
    except asyncio.TimeoutError:
        log.error(f"Timeout acquiring database connection for starboard settings update (Guild: {guild_id})")
        return False
    except Exception as e:
        log.exception(f"Database error updating starboard settings for guild {guild_id}: {e}")
        return False

async def get_starboard_entry(guild_id: int, original_message_id: int):
    """Gets a starboard entry for a specific message."""
    if not pg_pool:
        log.warning(f"PostgreSQL pool not initialized, returning None for starboard entry.")
        return None

    try:
        async with pg_pool.acquire() as conn:
            entry = await conn.fetchrow(
                """
                SELECT * FROM starboard_entries
                WHERE guild_id = $1 AND original_message_id = $2
                """,
                guild_id, original_message_id
            )

            return dict(entry) if entry else None
    except Exception as e:
        log.exception(f"Database error getting starboard entry for message {original_message_id} in guild {guild_id}: {e}")
        return None

async def create_starboard_entry(guild_id: int, original_message_id: int, original_channel_id: int,
                                starboard_message_id: int, author_id: int, star_count: int = 1):
    """Creates a new starboard entry."""
    if not pg_pool:
        log.error(f"PostgreSQL pool not initialized, cannot create starboard entry.")
        return False

    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)

            # Create the entry
            await conn.execute(
                """
                INSERT INTO starboard_entries
                (guild_id, original_message_id, original_channel_id, starboard_message_id, author_id, star_count)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (guild_id, original_message_id) DO NOTHING;
                """,
                guild_id, original_message_id, original_channel_id, starboard_message_id, author_id, star_count
            )

            log.info(f"Created starboard entry for message {original_message_id} in guild {guild_id}")
            return True
    except Exception as e:
        log.exception(f"Database error creating starboard entry for message {original_message_id} in guild {guild_id}: {e}")
        return False

async def update_starboard_entry(guild_id: int, original_message_id: int, star_count: int):
    """Updates the star count for an existing starboard entry."""
    if not pg_pool:
        log.error(f"PostgreSQL pool not initialized, cannot update starboard entry.")
        return False

    try:
        # Acquire a connection with a timeout
        conn = None
        try:
            conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

            await conn.execute(
                """
                UPDATE starboard_entries
                SET star_count = $3
                WHERE guild_id = $1 AND original_message_id = $2
                """,
                guild_id, original_message_id, star_count
            )

            log.info(f"Updated star count to {star_count} for message {original_message_id} in guild {guild_id}")
            return True
        finally:
            # Always release the connection back to the pool
            if conn:
                await pg_pool.release(conn)
    except asyncio.TimeoutError:
        log.error(f"Timeout acquiring database connection for starboard entry update (Guild: {guild_id}, Message: {original_message_id})")
        return False
    except Exception as e:
        log.exception(f"Database error updating starboard entry for message {original_message_id} in guild {guild_id}: {e}")
        return False

async def delete_starboard_entry(guild_id: int, original_message_id: int):
    """Deletes a starboard entry."""
    if not pg_pool:
        log.error(f"PostgreSQL pool not initialized, cannot delete starboard entry.")
        return False

    try:
        # Acquire a connection with a timeout
        conn = None
        try:
            conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

            # Delete the entry
            await conn.execute(
                """
                DELETE FROM starboard_entries
                WHERE guild_id = $1 AND original_message_id = $2
                """,
                guild_id, original_message_id
            )

            # Also delete any reactions associated with this message
            await conn.execute(
                """
                DELETE FROM starboard_reactions
                WHERE guild_id = $1 AND message_id = $2
                """,
                guild_id, original_message_id
            )

            log.info(f"Deleted starboard entry for message {original_message_id} in guild {guild_id}")
            return True
        finally:
            # Always release the connection back to the pool
            if conn:
                await pg_pool.release(conn)
    except asyncio.TimeoutError:
        log.error(f"Timeout acquiring database connection for starboard entry deletion (Guild: {guild_id}, Message: {original_message_id})")
        return False
    except Exception as e:
        log.exception(f"Database error deleting starboard entry for message {original_message_id} in guild {guild_id}: {e}")
        return False

async def clear_starboard_entries(guild_id: int):
    """Clears all starboard entries for a guild."""
    if not pg_pool:
        log.error(f"PostgreSQL pool not initialized, cannot clear starboard entries.")
        return False

    try:
        # Acquire a connection with a timeout
        conn = None
        try:
            conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

            # Get all starboard entries for this guild
            entries = await conn.fetch(
                """
                SELECT * FROM starboard_entries
                WHERE guild_id = $1
                """,
                guild_id
            )

            # Delete all entries
            await conn.execute(
                """
                DELETE FROM starboard_entries
                WHERE guild_id = $1
                """,
                guild_id
            )

            # Delete all reactions
            await conn.execute(
                """
                DELETE FROM starboard_reactions
                WHERE guild_id = $1
                """,
                guild_id
            )

            log.info(f"Cleared {len(entries)} starboard entries for guild {guild_id}")
            return entries
        finally:
            # Always release the connection back to the pool
            if conn:
                await pg_pool.release(conn)
    except asyncio.TimeoutError:
        log.error(f"Timeout acquiring database connection for clearing starboard entries (Guild: {guild_id})")
        return False
    except Exception as e:
        log.exception(f"Database error clearing starboard entries for guild {guild_id}: {e}")
        return False

async def add_starboard_reaction(guild_id: int, message_id: int, user_id: int):
    """Records a user's star reaction to a message."""
    if not pg_pool:
        log.error(f"PostgreSQL pool not initialized, cannot add starboard reaction.")
        return False

    # Use a timeout to prevent hanging on database operations
    try:
        # Acquire a connection with a timeout
        conn = None
        try:
            conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

            # Ensure guild exists
            try:
                await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            except Exception as e:
                if "another operation is in progress" in str(e) or "attached to a different loop" in str(e):
                    log.warning(f"Connection issue when inserting guild {guild_id}: {e}")
                    # Try to reset the connection
                    await conn.close()
                    conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)
                else:
                    raise

            # Add the reaction record
            try:
                await conn.execute(
                    """
                    INSERT INTO starboard_reactions (guild_id, message_id, user_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, message_id, user_id) DO NOTHING;
                    """,
                    guild_id, message_id, user_id
                )
            except Exception as e:
                if "another operation is in progress" in str(e) or "attached to a different loop" in str(e):
                    log.warning(f"Connection issue when adding reaction for message {message_id} in guild {guild_id}: {e}")
                    # Try to reset the connection
                    await conn.close()
                    conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

                    # Try again with the new connection
                    await conn.execute(
                        """
                        INSERT INTO starboard_reactions (guild_id, message_id, user_id)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (guild_id, message_id, user_id) DO NOTHING;
                        """,
                        guild_id, message_id, user_id
                    )
                else:
                    raise

            # Count total reactions for this message
            try:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM starboard_reactions
                    WHERE guild_id = $1 AND message_id = $2
                    """,
                    guild_id, message_id
                )
                return count
            except Exception as e:
                if "another operation is in progress" in str(e) or "attached to a different loop" in str(e):
                    log.warning(f"Connection issue when counting reactions for message {message_id} in guild {guild_id}: {e}")
                    # Try to reset the connection
                    await conn.close()
                    conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

                    # Try again with the new connection
                    count = await conn.fetchval(
                        """
                        SELECT COUNT(*) FROM starboard_reactions
                        WHERE guild_id = $1 AND message_id = $2
                        """,
                        guild_id, message_id
                    )
                    return count
                else:
                    raise
        finally:
            # Always release the connection back to the pool
            if conn:
                try:
                    await pg_pool.release(conn)
                except Exception as e:
                    log.warning(f"Error releasing connection: {e}")
    except asyncio.TimeoutError:
        log.error(f"Timeout acquiring database connection for adding starboard reaction (Guild: {guild_id}, Message: {message_id})")
        return False
    except Exception as e:
        log.exception(f"Database error adding starboard reaction for message {message_id} in guild {guild_id}: {e}")
        return False

async def remove_starboard_reaction(guild_id: int, message_id: int, user_id: int):
    """Removes a user's star reaction from a message."""
    if not pg_pool:
        log.error(f"PostgreSQL pool not initialized, cannot remove starboard reaction.")
        return False

    # Use a timeout to prevent hanging on database operations
    try:
        # Acquire a connection with a timeout
        conn = None
        try:
            conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

            # Remove the reaction record
            try:
                await conn.execute(
                    """
                    DELETE FROM starboard_reactions
                    WHERE guild_id = $1 AND message_id = $2 AND user_id = $3
                    """,
                    guild_id, message_id, user_id
                )
            except Exception as e:
                if "another operation is in progress" in str(e) or "attached to a different loop" in str(e):
                    log.warning(f"Connection issue when removing reaction for message {message_id} in guild {guild_id}: {e}")
                    # Try to reset the connection
                    await conn.close()
                    conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

                    # Try again with the new connection
                    await conn.execute(
                        """
                        DELETE FROM starboard_reactions
                        WHERE guild_id = $1 AND message_id = $2 AND user_id = $3
                        """,
                        guild_id, message_id, user_id
                    )
                else:
                    raise

            # Count remaining reactions for this message
            try:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM starboard_reactions
                    WHERE guild_id = $1 AND message_id = $2
                    """,
                    guild_id, message_id
                )
                return count
            except Exception as e:
                if "another operation is in progress" in str(e) or "attached to a different loop" in str(e):
                    log.warning(f"Connection issue when counting reactions for message {message_id} in guild {guild_id}: {e}")
                    # Try to reset the connection
                    await conn.close()
                    conn = await asyncio.wait_for(pg_pool.acquire(), timeout=5.0)

                    # Try again with the new connection
                    count = await conn.fetchval(
                        """
                        SELECT COUNT(*) FROM starboard_reactions
                        WHERE guild_id = $1 AND message_id = $2
                        """,
                        guild_id, message_id
                    )
                    return count
                else:
                    raise
        finally:
            # Always release the connection back to the pool
            if conn:
                try:
                    await pg_pool.release(conn)
                except Exception as e:
                    log.warning(f"Error releasing connection: {e}")
    except asyncio.TimeoutError:
        log.error(f"Timeout acquiring database connection for removing starboard reaction (Guild: {guild_id}, Message: {message_id})")
        return False
    except Exception as e:
        log.exception(f"Database error removing starboard reaction for message {message_id} in guild {guild_id}: {e}")
        return False

async def get_starboard_reaction_count(guild_id: int, message_id: int):
    """Gets the count of star reactions for a message."""
    if not pg_pool:
        log.warning(f"PostgreSQL pool not initialized, returning 0 for starboard reaction count.")
        return 0

    try:
        async with pg_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM starboard_reactions
                WHERE guild_id = $1 AND message_id = $2
                """,
                guild_id, message_id
            )

            return count
    except Exception as e:
        log.exception(f"Database error getting starboard reaction count for message {message_id} in guild {guild_id}: {e}")
        return 0

async def has_user_reacted(guild_id: int, message_id: int, user_id: int):
    """Checks if a user has already reacted to a message."""
    if not pg_pool:
        log.warning(f"PostgreSQL pool not initialized, returning False for user reaction check.")
        return False

    try:
        async with pg_pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM starboard_reactions
                    WHERE guild_id = $1 AND message_id = $2 AND user_id = $3
                )
                """,
                guild_id, message_id, user_id
            )

            return result
    except Exception as e:
        log.exception(f"Database error checking if user {user_id} reacted to message {message_id} in guild {guild_id}: {e}")
        return False


# --- Helper Functions ---
def _get_redis_key(guild_id: int, key_type: str, identifier: str = None) -> str:
    """Generates a standardized Redis key."""
    if identifier:
        return f"guild:{guild_id}:{key_type}:{identifier}"
    return f"guild:{guild_id}:{key_type}"

# --- Settings Access Functions (Placeholders with Cache Logic) ---

async def get_guild_prefix(guild_id: int, default_prefix: str) -> str:
    """Gets the command prefix for a guild, checking cache first."""
    if not pg_pool or not redis_pool:
        log.warning("Pools not initialized, returning default prefix.")
        return default_prefix

    cache_key = _get_redis_key(guild_id, "prefix")

    # Try to get from cache with timeout and error handling
    try:
        # Use a timeout to prevent hanging on Redis operations
        cached_prefix = await asyncio.wait_for(redis_pool.get(cache_key), timeout=2.0)
        if cached_prefix is not None:
            log.debug(f"Cache hit for prefix (Guild: {guild_id})")
            return cached_prefix
    except asyncio.TimeoutError:
        log.warning(f"Redis timeout getting prefix for guild {guild_id}, falling back to database")
    except RuntimeError as e:
        if "got Future" in str(e) and "attached to a different loop" in str(e):
            log.warning(f"Redis event loop error for guild {guild_id}, falling back to database: {e}")
        else:
            log.exception(f"Redis error getting prefix for guild {guild_id}: {e}")
    except Exception as e:
        log.exception(f"Redis error getting prefix for guild {guild_id}: {e}")

    # Cache miss or Redis error, get from database
    log.debug(f"Cache miss for prefix (Guild: {guild_id})")
    try:
        async with pg_pool.acquire() as conn:
            prefix = await conn.fetchval(
                "SELECT setting_value FROM guild_settings WHERE guild_id = $1 AND setting_key = 'prefix'",
                guild_id
            )

        final_prefix = prefix if prefix is not None else default_prefix

        # Try to cache the result with timeout and error handling
        try:
            # Use a timeout to prevent hanging on Redis operations
            await asyncio.wait_for(
                redis_pool.set(cache_key, final_prefix, ex=3600),  # Cache for 1 hour
                timeout=2.0
            )
        except asyncio.TimeoutError:
            log.warning(f"Redis timeout setting prefix for guild {guild_id}")
        except RuntimeError as e:
            if "got Future" in str(e) and "attached to a different loop" in str(e):
                log.warning(f"Redis event loop error setting prefix for guild {guild_id}: {e}")
            else:
                log.exception(f"Redis error setting prefix for guild {guild_id}: {e}")
        except Exception as e:
            log.exception(f"Redis error setting prefix for guild {guild_id}: {e}")

        return final_prefix
    except Exception as e:
        log.exception(f"Database error getting prefix for guild {guild_id}: {e}")
        return default_prefix  # Fall back to default on database error

async def set_guild_prefix(guild_id: int, prefix: str):
    """Sets the command prefix for a guild and updates the cache."""
    if not pg_pool or not redis_pool:
        log.error("Pools not initialized, cannot set prefix.")
        return False # Indicate failure

    cache_key = _get_redis_key(guild_id, "prefix")
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            # Upsert the setting
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, setting_key, setting_value)
                VALUES ($1, 'prefix', $2)
                ON CONFLICT (guild_id, setting_key) DO UPDATE SET setting_value = $2;
                """,
                guild_id, prefix
            )

        # Update cache
        await redis_pool.set(cache_key, prefix, ex=3600) # Cache for 1 hour
        log.info(f"Set prefix for guild {guild_id} to '{prefix}'")
        return True # Indicate success
    except Exception as e:
        log.exception(f"Database or Redis error setting prefix for guild {guild_id}: {e}")
        # Attempt to invalidate cache on error to prevent stale data
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
            log.exception(f"Failed to invalidate Redis cache for prefix (Guild: {guild_id}): {redis_err}")
        return False # Indicate failure

# --- Generic Settings Functions ---

async def get_setting(guild_id: int, key: str, default=None):
    """Gets a specific setting for a guild, checking cache first."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, returning default for setting '{key}'.")
        return default

    cache_key = _get_redis_key(guild_id, "setting", key)

    # Try to get from cache with timeout and error handling
    try:
        # Use a timeout to prevent hanging on Redis operations
        cached_value = await asyncio.wait_for(redis_pool.get(cache_key), timeout=2.0)
        if cached_value is not None:
            # Note: Redis stores everything as strings. Consider type conversion if needed.
            log.debug(f"Cache hit for setting '{key}' (Guild: {guild_id})")
            # Handle the None marker
            if cached_value == "__NONE__":
                return default
            return cached_value
    except asyncio.TimeoutError:
        log.warning(f"Redis timeout getting setting '{key}' for guild {guild_id}, falling back to database")
    except RuntimeError as e:
        if "got Future" in str(e) and "attached to a different loop" in str(e):
            log.warning(f"Redis event loop error for guild {guild_id}, falling back to database: {e}")
        else:
            log.exception(f"Redis error getting setting '{key}' for guild {guild_id}: {e}")
    except Exception as e:
        log.exception(f"Redis error getting setting '{key}' for guild {guild_id}: {e}")

    # Cache miss or Redis error, get from database
    log.debug(f"Cache miss for setting '{key}' (Guild: {guild_id})")
    try:
        async with pg_pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT setting_value FROM guild_settings WHERE guild_id = $1 AND setting_key = $2",
                guild_id, key
            )

        final_value = value if value is not None else default

        # Cache the result (even if None or default, cache the absence or default value)
        # Store None as a special marker, e.g., "None" string, or handle appropriately
        value_to_cache = final_value if final_value is not None else "__NONE__" # Marker for None

        # Try to cache the result with timeout and error handling
        try:
            # Use a timeout to prevent hanging on Redis operations
            await asyncio.wait_for(
                redis_pool.set(cache_key, value_to_cache, ex=3600),  # Cache for 1 hour
                timeout=2.0
            )
        except asyncio.TimeoutError:
            log.warning(f"Redis timeout setting cache for setting '{key}' for guild {guild_id}")
        except RuntimeError as e:
            if "got Future" in str(e) and "attached to a different loop" in str(e):
                log.warning(f"Redis event loop error setting cache for setting '{key}' for guild {guild_id}: {e}")
            else:
                log.exception(f"Redis error setting cache for setting '{key}' for guild {guild_id}: {e}")
        except Exception as e:
            log.exception(f"Redis error setting cache for setting '{key}' for guild {guild_id}: {e}")

        return final_value
    except Exception as e:
        log.exception(f"Database error getting setting '{key}' for guild {guild_id}: {e}")
        return default  # Fall back to default on database error


async def set_setting(guild_id: int, key: str, value: str | None):
    """Sets a specific setting for a guild and updates/invalidates the cache.
       Setting value to None effectively deletes the setting."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot set setting '{key}'.")
        return False

    cache_key = _get_redis_key(guild_id, "setting", key)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)

            if value is not None:
                # Upsert the setting
                await conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, setting_key, setting_value)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, setting_key) DO UPDATE SET setting_value = $3;
                    """,
                    guild_id, key, str(value) # Ensure value is string
                )
                # Update cache
                await redis_pool.set(cache_key, str(value), ex=3600)
                log.info(f"Set setting '{key}' for guild {guild_id}")
            else:
                # Delete the setting if value is None
                await conn.execute(
                    "DELETE FROM guild_settings WHERE guild_id = $1 AND setting_key = $2",
                    guild_id, key
                )
                # Invalidate cache
                await redis_pool.delete(cache_key)
                log.info(f"Deleted setting '{key}' for guild {guild_id}")

        return True
    except Exception as e:
        log.exception(f"Database or Redis error setting setting '{key}' for guild {guild_id}: {e}")
        # Attempt to invalidate cache on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
            log.exception(f"Failed to invalidate Redis cache for setting '{key}' (Guild: {guild_id}): {redis_err}")
        return False

# --- Cog Enablement Functions ---

async def is_cog_enabled(guild_id: int, cog_name: str, default_enabled: bool = True) -> bool:
    """Checks if a cog is enabled for a guild, checking cache first.
       Uses default_enabled if no specific setting is found."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, returning default for cog '{cog_name}'.")
        return default_enabled

    cache_key = _get_redis_key(guild_id, "cog_enabled", cog_name)

    # Try to get from cache with timeout and error handling
    try:
        # Use a timeout to prevent hanging on Redis operations
        cached_value = await asyncio.wait_for(redis_pool.get(cache_key), timeout=2.0)
        if cached_value is not None:
            log.debug(f"Cache hit for cog enabled status '{cog_name}' (Guild: {guild_id})")
            return cached_value == "True" # Redis stores strings
    except asyncio.TimeoutError:
        log.warning(f"Redis timeout getting cog enabled status for '{cog_name}' (Guild: {guild_id}), falling back to database")
    except RuntimeError as e:
        if "got Future" in str(e) and "attached to a different loop" in str(e):
            log.warning(f"Redis event loop error for guild {guild_id}, falling back to database: {e}")
        else:
            log.exception(f"Redis error getting cog enabled status for '{cog_name}' (Guild: {guild_id}): {e}")
    except Exception as e:
        log.exception(f"Redis error getting cog enabled status for '{cog_name}' (Guild: {guild_id}): {e}")

    # Cache miss or Redis error, get from database
    log.debug(f"Cache miss for cog enabled status '{cog_name}' (Guild: {guild_id})")
    db_enabled_status = None
    try:
        async with pg_pool.acquire() as conn:
            db_enabled_status = await conn.fetchval(
                "SELECT enabled FROM enabled_cogs WHERE guild_id = $1 AND cog_name = $2",
                guild_id, cog_name
            )

        final_status = db_enabled_status if db_enabled_status is not None else default_enabled

        # Try to cache the result with timeout and error handling
        try:
            # Use a timeout to prevent hanging on Redis operations
            await asyncio.wait_for(
                redis_pool.set(cache_key, str(final_status), ex=3600),  # Cache for 1 hour
                timeout=2.0
            )
        except asyncio.TimeoutError:
            log.warning(f"Redis timeout setting cache for cog enabled status '{cog_name}' (Guild: {guild_id})")
        except RuntimeError as e:
            if "got Future" in str(e) and "attached to a different loop" in str(e):
                log.warning(f"Redis event loop error setting cache for cog enabled status '{cog_name}' (Guild: {guild_id}): {e}")
            else:
                log.exception(f"Redis error setting cache for cog enabled status '{cog_name}' (Guild: {guild_id}): {e}")
        except Exception as e:
            log.exception(f"Redis error setting cache for cog enabled status '{cog_name}' (Guild: {guild_id}): {e}")

        return final_status
    except Exception as e:
        log.exception(f"Database error getting cog enabled status for '{cog_name}' (Guild: {guild_id}): {e}")
        # Fallback to default on DB error after cache miss
        return default_enabled


async def set_cog_enabled(guild_id: int, cog_name: str, enabled: bool):
    """Sets the enabled status for a cog in a guild and updates the cache."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot set cog enabled status for '{cog_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cog_enabled", cog_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            # Upsert the enabled status
            await conn.execute(
                """
                INSERT INTO enabled_cogs (guild_id, cog_name, enabled)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, cog_name) DO UPDATE SET enabled = $3;
                """,
                guild_id, cog_name, enabled
            )

        # Update cache
        await redis_pool.set(cache_key, str(enabled), ex=3600)
        log.info(f"Set cog '{cog_name}' enabled status to {enabled} for guild {guild_id}")
        return True
    except Exception as e:
        log.exception(f"Database or Redis error setting cog enabled status for '{cog_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
             log.exception(f"Failed to invalidate Redis cache for cog enabled status '{cog_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def is_command_enabled(guild_id: int, command_name: str, default_enabled: bool = True) -> bool:
    """Checks if a command is enabled for a guild, checking cache first.
       Uses default_enabled if no specific setting is found."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, returning default for command '{command_name}'.")
        return default_enabled

    cache_key = _get_redis_key(guild_id, "cmd_enabled", command_name)

    # Try to get from cache with timeout and error handling
    try:
        # Use a timeout to prevent hanging on Redis operations
        cached_value = await asyncio.wait_for(redis_pool.get(cache_key), timeout=2.0)
        if cached_value is not None:
            log.debug(f"Cache hit for command enabled status '{command_name}' (Guild: {guild_id})")
            return cached_value == "True" # Redis stores strings
    except asyncio.TimeoutError:
        log.warning(f"Redis timeout getting command enabled status for '{command_name}' (Guild: {guild_id}), falling back to database")
    except RuntimeError as e:
        if "got Future" in str(e) and "attached to a different loop" in str(e):
            log.warning(f"Redis event loop error for guild {guild_id}, falling back to database: {e}")
        else:
            log.exception(f"Redis error getting command enabled status for '{command_name}' (Guild: {guild_id}): {e}")
    except Exception as e:
        log.exception(f"Redis error getting command enabled status for '{command_name}' (Guild: {guild_id}): {e}")

    # Cache miss or Redis error, get from database
    log.debug(f"Cache miss for command enabled status '{command_name}' (Guild: {guild_id})")
    db_enabled_status = None
    try:
        async with pg_pool.acquire() as conn:
            db_enabled_status = await conn.fetchval(
                "SELECT enabled FROM enabled_commands WHERE guild_id = $1 AND command_name = $2",
                guild_id, command_name
            )

        final_status = db_enabled_status if db_enabled_status is not None else default_enabled

        # Try to cache the result with timeout and error handling
        try:
            # Use a timeout to prevent hanging on Redis operations
            await asyncio.wait_for(
                redis_pool.set(cache_key, str(final_status), ex=3600),  # Cache for 1 hour
                timeout=2.0
            )
        except asyncio.TimeoutError:
            log.warning(f"Redis timeout setting cache for command enabled status '{command_name}' (Guild: {guild_id})")
        except RuntimeError as e:
            if "got Future" in str(e) and "attached to a different loop" in str(e):
                log.warning(f"Redis event loop error setting cache for command enabled status '{command_name}' (Guild: {guild_id}): {e}")
            else:
                log.exception(f"Redis error setting cache for command enabled status '{command_name}' (Guild: {guild_id}): {e}")
        except Exception as e:
            log.exception(f"Redis error setting cache for command enabled status '{command_name}' (Guild: {guild_id}): {e}")

        return final_status
    except Exception as e:
        log.exception(f"Database error getting command enabled status for '{command_name}' (Guild: {guild_id}): {e}")
        # Fallback to default on DB error after cache miss
        return default_enabled


async def set_command_enabled(guild_id: int, command_name: str, enabled: bool):
    """Sets the enabled status for a command in a guild and updates the cache."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot set command enabled status for '{command_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cmd_enabled", command_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            # Upsert the enabled status
            await conn.execute(
                """
                INSERT INTO enabled_commands (guild_id, command_name, enabled)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, command_name) DO UPDATE SET enabled = $3;
                """,
                guild_id, command_name, enabled
            )

        # Update cache
        await redis_pool.set(cache_key, str(enabled), ex=3600)
        log.info(f"Set command '{command_name}' enabled status to {enabled} for guild {guild_id}")
        return True
    except Exception as e:
        log.exception(f"Database or Redis error setting command enabled status for '{command_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
             log.exception(f"Failed to invalidate Redis cache for command enabled status '{command_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def get_all_enabled_commands(guild_id: int) -> Dict[str, bool]:
    """Gets all command enabled statuses for a guild.
       Returns a dictionary of command_name -> enabled status."""
    if not pg_pool:
        log.error(f"Database pool not initialized, cannot get command enabled statuses for guild {guild_id}.")
        return {}

    try:
        async with pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT command_name, enabled FROM enabled_commands WHERE guild_id = $1",
                guild_id
            )
            return {record['command_name']: record['enabled'] for record in records}
    except Exception as e:
        log.exception(f"Database error getting command enabled statuses for guild {guild_id}: {e}")
        return {}


async def get_all_enabled_cogs(guild_id: int) -> Dict[str, bool]:
    """Gets all cog enabled statuses for a guild.
       Returns a dictionary of cog_name -> enabled status."""
    if not pg_pool:
        log.error(f"Database pool not initialized, cannot get cog enabled statuses for guild {guild_id}.")
        return {}

    try:
        async with pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT cog_name, enabled FROM enabled_cogs WHERE guild_id = $1",
                guild_id
            )
            return {record['cog_name']: record['enabled'] for record in records}
    except Exception as e:
        log.exception(f"Database error getting cog enabled statuses for guild {guild_id}: {e}")
        return {}

# --- Command Permission Functions ---

async def add_command_permission(guild_id: int, command_name: str, role_id: int) -> bool:
    """Adds permission for a role to use a command and invalidates cache."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot add permission for command '{command_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cmd_perms", command_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            # Add the permission rule
            await conn.execute(
                """
                INSERT INTO command_permissions (guild_id, command_name, allowed_role_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, command_name, allowed_role_id) DO NOTHING;
                """,
                guild_id, command_name, role_id
            )

        # Invalidate cache after DB operation succeeds
        await redis_pool.delete(cache_key)
        log.info(f"Added permission for role {role_id} to use command '{command_name}' in guild {guild_id}")
        return True
    except Exception as e:
        log.exception(f"Database or Redis error adding permission for command '{command_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache even on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
             log.exception(f"Failed to invalidate Redis cache for command permissions '{command_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def remove_command_permission(guild_id: int, command_name: str, role_id: int) -> bool:
    """Removes permission for a role to use a command and invalidates cache."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot remove permission for command '{command_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cmd_perms", command_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists (though unlikely to be needed for delete)
            # await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            # Remove the permission rule
            await conn.execute(
                """
                DELETE FROM command_permissions
                WHERE guild_id = $1 AND command_name = $2 AND allowed_role_id = $3;
                """,
                guild_id, command_name, role_id
            )

        # Invalidate cache after DB operation succeeds
        await redis_pool.delete(cache_key)
        log.info(f"Removed permission for role {role_id} to use command '{command_name}' in guild {guild_id}")
        return True
    except Exception as e:
        log.exception(f"Database or Redis error removing permission for command '{command_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache even on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
             log.exception(f"Failed to invalidate Redis cache for command permissions '{command_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def check_command_permission(guild_id: int, command_name: str, member_roles_ids: list[int]) -> bool:
    """Checks if any of the member's roles have permission for the command.
       Returns True if allowed, False otherwise.
       If no permissions are set for the command in the DB, it defaults to allowed by this check.
    """
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, defaulting to allowed for command '{command_name}'.")
        return True # Default to allowed if system isn't ready

    cache_key = _get_redis_key(guild_id, "cmd_perms", command_name)
    allowed_role_ids_str = set()

    try:
        # Check cache first - stores a set of allowed role IDs as strings
        if await redis_pool.exists(cache_key):
            cached_roles = await redis_pool.smembers(cache_key)
            # Handle the empty set marker
            if cached_roles == {"__EMPTY_SET__"}:
                 log.debug(f"Cache hit (empty set) for cmd perms '{command_name}' (Guild: {guild_id}). Command allowed by default.")
                 return True # No specific restrictions found
            allowed_role_ids_str = cached_roles
            log.debug(f"Cache hit for cmd perms '{command_name}' (Guild: {guild_id})")
        else:
            # Cache miss - fetch from DB
            log.debug(f"Cache miss for cmd perms '{command_name}' (Guild: {guild_id})")
            async with pg_pool.acquire() as conn:
                records = await conn.fetch(
                    "SELECT allowed_role_id FROM command_permissions WHERE guild_id = $1 AND command_name = $2",
                    guild_id, command_name
                )
            # Convert fetched role IDs (BIGINT) to strings for Redis set
            allowed_role_ids_str = {str(record['allowed_role_id']) for record in records}

            # Cache the result (even if empty)
            try:
                async with redis_pool.pipeline(transaction=True) as pipe:
                    pipe.delete(cache_key) # Ensure clean state
                    if allowed_role_ids_str:
                        pipe.sadd(cache_key, *allowed_role_ids_str)
                    else:
                        pipe.sadd(cache_key, "__EMPTY_SET__") # Marker for empty set
                    pipe.expire(cache_key, 3600) # Cache for 1 hour
                    await pipe.execute()
            except Exception as e:
                log.exception(f"Redis error setting cache for cmd perms '{command_name}' (Guild: {guild_id}): {e}")

    except Exception as e:
        log.exception(f"Error checking command permission for '{command_name}' (Guild: {guild_id}): {e}")
        return True # Default to allowed on error

    # --- Permission Check Logic ---
    if not allowed_role_ids_str or allowed_role_ids_str == {"__EMPTY_SET__"}:
        # If no permissions are defined in our system for this command, allow it.
        # Other checks (like @commands.is_owner()) might still apply.
        return True
    else:
        # Check if any of the member's roles intersect with the allowed roles
        member_roles_ids_str = {str(role_id) for role_id in member_roles_ids}
        if member_roles_ids_str.intersection(allowed_role_ids_str):
            log.debug(f"Permission granted for '{command_name}' (Guild: {guild_id}) via role intersection.")
            return True # Member has at least one allowed role
        else:
            log.debug(f"Permission denied for '{command_name}' (Guild: {guild_id}). Member roles {member_roles_ids_str} not in allowed roles {allowed_role_ids_str}.")
            return False # Member has none of the specifically allowed roles


async def get_command_permissions(guild_id: int, command_name: str) -> set[int] | None:
    """Gets the set of allowed role IDs for a specific command, checking cache first. Returns None on error."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, cannot get permissions for command '{command_name}'.")
        return None

    cache_key = _get_redis_key(guild_id, "cmd_perms", command_name)
    try:
        # Check cache first
        if await redis_pool.exists(cache_key):
            cached_roles_str = await redis_pool.smembers(cache_key)
            if cached_roles_str == {"__EMPTY_SET__"}:
                log.debug(f"Cache hit (empty set) for cmd perms '{command_name}' (Guild: {guild_id}).")
                return set() # Return empty set if explicitly empty
            allowed_role_ids = {int(role_id) for role_id in cached_roles_str}
            log.debug(f"Cache hit for cmd perms '{command_name}' (Guild: {guild_id})")
            return allowed_role_ids
    except Exception as e:
        log.exception(f"Redis error getting cmd perms for '{command_name}' (Guild: {guild_id}): {e}")
        # Fall through to DB query on Redis error

    log.debug(f"Cache miss for cmd perms '{command_name}' (Guild: {guild_id})")
    try:
        async with pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT allowed_role_id FROM command_permissions WHERE guild_id = $1 AND command_name = $2",
                guild_id, command_name
            )
        allowed_role_ids = {record['allowed_role_id'] for record in records}

        # Cache the result
        try:
            allowed_role_ids_str = {str(role_id) for role_id in allowed_role_ids}
            async with redis_pool.pipeline(transaction=True) as pipe:
                pipe.delete(cache_key) # Ensure clean state
                if allowed_role_ids_str:
                    pipe.sadd(cache_key, *allowed_role_ids_str)
                else:
                    pipe.sadd(cache_key, "__EMPTY_SET__") # Marker for empty set
                pipe.expire(cache_key, 3600) # Cache for 1 hour
                await pipe.execute()
        except Exception as e:
            log.exception(f"Redis error setting cache for cmd perms '{command_name}' (Guild: {guild_id}): {e}")

        return allowed_role_ids
    except Exception as e:
        log.exception(f"Database error getting cmd perms for '{command_name}' (Guild: {guild_id}): {e}")
        return None # Indicate error


# --- Bot Guild Information ---

async def get_bot_guild_ids() -> set[int] | None:
    """Gets the set of all guild IDs known to the bot from the guilds table. Returns None on error."""
    global pg_pool
    if not pg_pool:
        log.error("Pools not initialized, cannot get bot guild IDs.")
        return None

    # Create a new connection for this specific operation to avoid event loop conflicts
    try:
        # Create a temporary connection just for this operation
        # This ensures we're using the current event loop
        temp_conn = await asyncpg.connect(DATABASE_URL)
        try:
            records = await temp_conn.fetch("SELECT guild_id FROM guilds")
            guild_ids = {record['guild_id'] for record in records}
            log.debug(f"Fetched {len(guild_ids)} guild IDs from database.")
            return guild_ids
        finally:
            # Always close the temporary connection
            await temp_conn.close()
    except asyncpg.exceptions.PostgresError as e:
        log.exception(f"PostgreSQL error fetching bot guild IDs: {e}")
        return None
    except Exception as e:
        log.exception(f"Unexpected error fetching bot guild IDs: {e}")
        return None


# --- Command Customization Functions ---

async def get_custom_command_name(guild_id: int, original_command_name: str) -> str | None:
    """Gets the custom command name for a guild, checking cache first.
       Returns None if no custom name is set."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, returning None for custom command name '{original_command_name}'.")
        return None

    cache_key = _get_redis_key(guild_id, "cmd_custom", original_command_name)
    try:
        cached_value = await redis_pool.get(cache_key)
        if cached_value is not None:
            log.debug(f"Cache hit for custom command name '{original_command_name}' (Guild: {guild_id})")
            return None if cached_value == "__NONE__" else cached_value
    except Exception as e:
        log.exception(f"Redis error getting custom command name for '{original_command_name}' (Guild: {guild_id}): {e}")

    log.debug(f"Cache miss for custom command name '{original_command_name}' (Guild: {guild_id})")
    async with pg_pool.acquire() as conn:
        custom_name = await conn.fetchval(
            "SELECT custom_command_name FROM command_customization WHERE guild_id = $1 AND original_command_name = $2",
            guild_id, original_command_name
        )

    # Cache the result (even if None)
    try:
        value_to_cache = custom_name if custom_name is not None else "__NONE__"
        await redis_pool.set(cache_key, value_to_cache, ex=3600)  # Cache for 1 hour
    except Exception as e:
        log.exception(f"Redis error setting cache for custom command name '{original_command_name}' (Guild: {guild_id}): {e}")

    return custom_name


async def get_custom_command_description(guild_id: int, original_command_name: str) -> str | None:
    """Gets the custom command description for a guild, checking cache first.
       Returns None if no custom description is set."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, returning None for custom command description '{original_command_name}'.")
        return None

    cache_key = _get_redis_key(guild_id, "cmd_desc", original_command_name)
    try:
        cached_value = await redis_pool.get(cache_key)
        if cached_value is not None:
            log.debug(f"Cache hit for custom command description '{original_command_name}' (Guild: {guild_id})")
            return None if cached_value == "__NONE__" else cached_value
    except Exception as e:
        log.exception(f"Redis error getting custom command description for '{original_command_name}' (Guild: {guild_id}): {e}")

    log.debug(f"Cache miss for custom command description '{original_command_name}' (Guild: {guild_id})")
    async with pg_pool.acquire() as conn:
        custom_desc = await conn.fetchval(
            "SELECT custom_command_description FROM command_customization WHERE guild_id = $1 AND original_command_name = $2",
            guild_id, original_command_name
        )

    # Cache the result (even if None)
    try:
        value_to_cache = custom_desc if custom_desc is not None else "__NONE__"
        await redis_pool.set(cache_key, value_to_cache, ex=3600)  # Cache for 1 hour
    except Exception as e:
        log.exception(f"Redis error setting cache for custom command description '{original_command_name}' (Guild: {guild_id}): {e}")

    return custom_desc


async def set_custom_command_name(guild_id: int, original_command_name: str, custom_command_name: str | None) -> bool:
    """Sets a custom command name for a guild and updates the cache.
       Setting custom_command_name to None removes the customization."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot set custom command name for '{original_command_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cmd_custom", original_command_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)

            if custom_command_name is not None:
                # Upsert the custom name
                await conn.execute(
                    """
                    INSERT INTO command_customization (guild_id, original_command_name, custom_command_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, original_command_name) DO UPDATE SET custom_command_name = $3;
                    """,
                    guild_id, original_command_name, custom_command_name
                )
                # Update cache
                await redis_pool.set(cache_key, custom_command_name, ex=3600)
                log.info(f"Set custom command name for '{original_command_name}' to '{custom_command_name}' for guild {guild_id}")
            else:
                # Delete the customization if value is None
                await conn.execute(
                    "DELETE FROM command_customization WHERE guild_id = $1 AND original_command_name = $2",
                    guild_id, original_command_name
                )
                # Update cache to indicate no customization
                await redis_pool.set(cache_key, "__NONE__", ex=3600)
                log.info(f"Removed custom command name for '{original_command_name}' for guild {guild_id}")

        return True
    except Exception as e:
        log.exception(f"Database or Redis error setting custom command name for '{original_command_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
            log.exception(f"Failed to invalidate Redis cache for custom command name '{original_command_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def set_custom_command_description(guild_id: int, original_command_name: str, custom_command_description: str | None) -> bool:
    """Sets a custom command description for a guild and updates the cache.
       Setting custom_command_description to None removes the description."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot set custom command description for '{original_command_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cmd_desc", original_command_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)

            # Check if the command customization exists
            exists = await conn.fetchval(
                "SELECT 1 FROM command_customization WHERE guild_id = $1 AND original_command_name = $2",
                guild_id, original_command_name
            )

            if custom_command_description is not None:
                if exists:
                    # Update the existing record
                    await conn.execute(
                        """
                        UPDATE command_customization
                        SET custom_command_description = $3
                        WHERE guild_id = $1 AND original_command_name = $2;
                        """,
                        guild_id, original_command_name, custom_command_description
                    )
                else:
                    # Insert a new record with default custom_command_name (same as original)
                    await conn.execute(
                        """
                        INSERT INTO command_customization (guild_id, original_command_name, custom_command_name, custom_command_description)
                        VALUES ($1, $2, $2, $3);
                        """,
                        guild_id, original_command_name, custom_command_description
                    )
                # Update cache
                await redis_pool.set(cache_key, custom_command_description, ex=3600)
                log.info(f"Set custom command description for '{original_command_name}' for guild {guild_id}")
            else:
                if exists:
                    # Update the existing record to remove the description
                    await conn.execute(
                        """
                        UPDATE command_customization
                        SET custom_command_description = NULL
                        WHERE guild_id = $1 AND original_command_name = $2;
                        """,
                        guild_id, original_command_name
                    )
                    # Update cache to indicate no description
                    await redis_pool.set(cache_key, "__NONE__", ex=3600)
                    log.info(f"Removed custom command description for '{original_command_name}' for guild {guild_id}")

        return True
    except Exception as e:
        log.exception(f"Database or Redis error setting custom command description for '{original_command_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
            log.exception(f"Failed to invalidate Redis cache for custom command description '{original_command_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def get_custom_group_name(guild_id: int, original_group_name: str) -> str | None:
    """Gets the custom command group name for a guild, checking cache first.
       Returns None if no custom name is set."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, returning None for custom group name '{original_group_name}'.")
        return None

    cache_key = _get_redis_key(guild_id, "group_custom", original_group_name)
    try:
        cached_value = await redis_pool.get(cache_key)
        if cached_value is not None:
            log.debug(f"Cache hit for custom group name '{original_group_name}' (Guild: {guild_id})")
            return None if cached_value == "__NONE__" else cached_value
    except Exception as e:
        log.exception(f"Redis error getting custom group name for '{original_group_name}' (Guild: {guild_id}): {e}")

    log.debug(f"Cache miss for custom group name '{original_group_name}' (Guild: {guild_id})")
    async with pg_pool.acquire() as conn:
        custom_name = await conn.fetchval(
            "SELECT custom_group_name FROM command_group_customization WHERE guild_id = $1 AND original_group_name = $2",
            guild_id, original_group_name
        )

    # Cache the result (even if None)
    try:
        value_to_cache = custom_name if custom_name is not None else "__NONE__"
        await redis_pool.set(cache_key, value_to_cache, ex=3600)  # Cache for 1 hour
    except Exception as e:
        log.exception(f"Redis error setting cache for custom group name '{original_group_name}' (Guild: {guild_id}): {e}")

    return custom_name


async def set_custom_group_name(guild_id: int, original_group_name: str, custom_group_name: str | None) -> bool:
    """Sets a custom command group name for a guild and updates the cache.
       Setting custom_group_name to None removes the customization."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot set custom group name for '{original_group_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "group_custom", original_group_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)

            if custom_group_name is not None:
                # Upsert the custom name
                await conn.execute(
                    """
                    INSERT INTO command_group_customization (guild_id, original_group_name, custom_group_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id, original_group_name) DO UPDATE SET custom_group_name = $3;
                    """,
                    guild_id, original_group_name, custom_group_name
                )
                # Update cache
                await redis_pool.set(cache_key, custom_group_name, ex=3600)
                log.info(f"Set custom group name for '{original_group_name}' to '{custom_group_name}' for guild {guild_id}")
            else:
                # Delete the customization if value is None
                await conn.execute(
                    "DELETE FROM command_group_customization WHERE guild_id = $1 AND original_group_name = $2",
                    guild_id, original_group_name
                )
                # Update cache to indicate no customization
                await redis_pool.set(cache_key, "__NONE__", ex=3600)
                log.info(f"Removed custom group name for '{original_group_name}' for guild {guild_id}")

        return True
    except Exception as e:
        log.exception(f"Database or Redis error setting custom group name for '{original_group_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
            log.exception(f"Failed to invalidate Redis cache for custom group name '{original_group_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def add_command_alias(guild_id: int, original_command_name: str, alias_name: str) -> bool:
    """Adds an alias for a command in a guild and invalidates cache."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot add alias for command '{original_command_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cmd_aliases", original_command_name)
    try:
        async with pg_pool.acquire() as conn:
            # Ensure guild exists
            await conn.execute("INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING;", guild_id)
            # Add the alias
            await conn.execute(
                """
                INSERT INTO command_aliases (guild_id, original_command_name, alias_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, original_command_name, alias_name) DO NOTHING;
                """,
                guild_id, original_command_name, alias_name
            )

        # Invalidate cache after DB operation succeeds
        await redis_pool.delete(cache_key)
        log.info(f"Added alias '{alias_name}' for command '{original_command_name}' in guild {guild_id}")
        return True
    except Exception as e:
        log.exception(f"Database or Redis error adding alias for command '{original_command_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache even on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
            log.exception(f"Failed to invalidate Redis cache for command aliases '{original_command_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def remove_command_alias(guild_id: int, original_command_name: str, alias_name: str) -> bool:
    """Removes an alias for a command in a guild and invalidates cache."""
    if not pg_pool or not redis_pool:
        log.error(f"Pools not initialized, cannot remove alias for command '{original_command_name}'.")
        return False

    cache_key = _get_redis_key(guild_id, "cmd_aliases", original_command_name)
    try:
        async with pg_pool.acquire() as conn:
            # Remove the alias
            await conn.execute(
                """
                DELETE FROM command_aliases
                WHERE guild_id = $1 AND original_command_name = $2 AND alias_name = $3;
                """,
                guild_id, original_command_name, alias_name
            )

        # Invalidate cache after DB operation succeeds
        await redis_pool.delete(cache_key)
        log.info(f"Removed alias '{alias_name}' for command '{original_command_name}' in guild {guild_id}")
        return True
    except Exception as e:
        log.exception(f"Database or Redis error removing alias for command '{original_command_name}' in guild {guild_id}: {e}")
        # Attempt to invalidate cache even on error
        try:
            await redis_pool.delete(cache_key)
        except Exception as redis_err:
            log.exception(f"Failed to invalidate Redis cache for command aliases '{original_command_name}' (Guild: {guild_id}): {redis_err}")
        return False


async def get_command_aliases(guild_id: int, original_command_name: str) -> list[str] | None:
    """Gets the list of aliases for a command in a guild, checking cache first.
       Returns empty list if no aliases are set, None on error."""
    if not pg_pool or not redis_pool:
        log.warning(f"Pools not initialized, returning None for command aliases '{original_command_name}'.")
        return None

    cache_key = _get_redis_key(guild_id, "cmd_aliases", original_command_name)
    try:
        # Check cache first
        cached_aliases = await redis_pool.lrange(cache_key, 0, -1)
        if cached_aliases is not None:
            if len(cached_aliases) == 1 and cached_aliases[0] == "__EMPTY_LIST__":
                log.debug(f"Cache hit (empty list) for command aliases '{original_command_name}' (Guild: {guild_id}).")
                return []
            log.debug(f"Cache hit for command aliases '{original_command_name}' (Guild: {guild_id})")
            return cached_aliases
    except Exception as e:
        log.exception(f"Redis error getting command aliases for '{original_command_name}' (Guild: {guild_id}): {e}")
        # Fall through to DB query on Redis error

    log.debug(f"Cache miss for command aliases '{original_command_name}' (Guild: {guild_id})")
    try:
        async with pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT alias_name FROM command_aliases WHERE guild_id = $1 AND original_command_name = $2",
                guild_id, original_command_name
            )
        aliases = [record['alias_name'] for record in records]

        # Cache the result
        try:
            async with redis_pool.pipeline(transaction=True) as pipe:
                pipe.delete(cache_key)  # Ensure clean state
                if aliases:
                    pipe.rpush(cache_key, *aliases)
                else:
                    pipe.rpush(cache_key, "__EMPTY_LIST__")  # Marker for empty list
                pipe.expire(cache_key, 3600)  # Cache for 1 hour
                await pipe.execute()
        except Exception as e:
            log.exception(f"Redis error setting cache for command aliases '{original_command_name}' (Guild: {guild_id}): {e}")

        return aliases
    except Exception as e:
        log.exception(f"Database error getting command aliases for '{original_command_name}' (Guild: {guild_id}): {e}")
        return None  # Indicate error


async def get_all_command_customizations(guild_id: int) -> dict[str, dict[str, str]] | None:
    """Gets all command customizations for a guild.
       Returns a dictionary mapping original command names to a dict with 'name' and 'description' keys,
       or None on error."""
    if not pg_pool:
        log.error("Pools not initialized, cannot get command customizations.")
        return None
    try:
        async with pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT original_command_name, custom_command_name, custom_command_description FROM command_customization WHERE guild_id = $1",
                guild_id
            )
        customizations = {}
        for record in records:
            cmd_name = record['original_command_name']
            customizations[cmd_name] = {
                'name': record['custom_command_name'],
                'description': record['custom_command_description']
            }
        log.debug(f"Fetched {len(customizations)} command customizations for guild {guild_id}.")
        return customizations
    except Exception as e:
        log.exception(f"Database error fetching command customizations for guild {guild_id}: {e}")
        return None


async def get_all_group_customizations(guild_id: int) -> dict[str, str] | None:
    """Gets all command group customizations for a guild.
       Returns a dictionary mapping original group names to custom names, or None on error."""
    if not pg_pool:
        log.error("Pools not initialized, cannot get group customizations.")
        return None
    try:
        async with pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT original_group_name, custom_group_name FROM command_group_customization WHERE guild_id = $1",
                guild_id
            )
        customizations = {record['original_group_name']: record['custom_group_name'] for record in records}
        log.debug(f"Fetched {len(customizations)} group customizations for guild {guild_id}.")
        return customizations
    except Exception as e:
        log.exception(f"Database error fetching group customizations for guild {guild_id}: {e}")
        return None


async def get_all_command_aliases(guild_id: int) -> dict[str, list[str]] | None:
    """Gets all command aliases for a guild.
       Returns a dictionary mapping original command names to lists of aliases, or None on error."""
    if not pg_pool:
        log.error("Pools not initialized, cannot get command aliases.")
        return None
    try:
        async with pg_pool.acquire() as conn:
            records = await conn.fetch(
                "SELECT original_command_name, alias_name FROM command_aliases WHERE guild_id = $1",
                guild_id
            )

        # Group by original_command_name
        aliases_dict = {}
        for record in records:
            cmd_name = record['original_command_name']
            alias = record['alias_name']
            if cmd_name not in aliases_dict:
                aliases_dict[cmd_name] = []
            aliases_dict[cmd_name].append(alias)

        log.debug(f"Fetched aliases for {len(aliases_dict)} commands for guild {guild_id}.")
        return aliases_dict
    except Exception as e:
        log.exception(f"Database error fetching command aliases for guild {guild_id}: {e}")
        return None
