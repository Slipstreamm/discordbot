import asyncpg
import logging
import asyncio
from typing import Optional, List, Tuple

log = logging.getLogger(__name__)

async def create_connection_with_retry(pool: asyncpg.Pool, max_retries: int = 3) -> Tuple[Optional[asyncpg.Connection], bool]:
    """
    Creates a database connection with retry logic.

    Args:
        pool: The connection pool to acquire a connection from
        max_retries: Maximum number of retry attempts

    Returns:
        Tuple containing (connection, success_flag)
    """
    retry_count = 0
    retry_delay = 0.5  # Start with 500ms delay

    while retry_count < max_retries:
        try:
            connection = await pool.acquire()
            return connection, True
        except (asyncpg.exceptions.ConnectionDoesNotExistError,
                asyncpg.exceptions.InterfaceError) as e:
            retry_count += 1
            if retry_count < max_retries:
                log.warning(f"Connection error when acquiring connection (attempt {retry_count}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                log.exception(f"Failed to acquire connection after {max_retries} attempts: {e}")
                return None, False
        except Exception as e:
            log.exception(f"Unexpected error acquiring connection: {e}")
            return None, False

    return None, False

async def setup_moderation_log_table(pool: asyncpg.Pool):
    """
    Ensures the moderation_logs table and its indexes exist in the database.
    """
    # Get a connection with retry logic
    connection, success = await create_connection_with_retry(pool)
    if not success or not connection:
        log.error("Failed to acquire database connection for setting up moderation_logs table")
        raise RuntimeError("Failed to acquire database connection for table setup")

    try:
        # Use a transaction to ensure all schema changes are atomic
        async with connection.transaction():
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS moderation_logs (
                    case_id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    moderator_id BIGINT NOT NULL,
                    target_user_id BIGINT NOT NULL,
                    action_type VARCHAR(50) NOT NULL,
                    reason TEXT,
                    duration_seconds INTEGER NULL,
                    log_message_id BIGINT NULL,
                    log_channel_id BIGINT NULL
                );
            """)

            # Create indexes if they don't exist
            await connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_moderation_logs_guild_id ON moderation_logs (guild_id);
            """)
            await connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_moderation_logs_target_user_id ON moderation_logs (target_user_id);
            """)
            await connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_moderation_logs_moderator_id ON moderation_logs (moderator_id);
            """)
            log.info("Successfully ensured moderation_logs table and indexes exist.")
    except Exception as e:
        log.exception(f"Error setting up moderation_logs table: {e}")
        raise # Re-raise the exception to indicate setup failure
    finally:
        # Always release the connection back to the pool
        try:
            await pool.release(connection)
        except Exception as e:
            log.warning(f"Error releasing connection back to pool: {e}")

# --- Placeholder functions (to be implemented next) ---

async def add_mod_log(pool: asyncpg.Pool, guild_id: int, moderator_id: int, target_user_id: int, action_type: str, reason: Optional[str], duration_seconds: Optional[int] = None) -> Optional[int]:
    """Adds a new moderation log entry and returns the case_id."""
    query = """
        INSERT INTO moderation_logs (guild_id, moderator_id, target_user_id, action_type, reason, duration_seconds)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING case_id;
    """
    # Get a connection with retry logic
    connection, success = await create_connection_with_retry(pool)
    if not success or not connection:
        log.error(f"Failed to acquire database connection for adding mod log entry for guild {guild_id}")
        return None

    try:
        # Use a transaction to ensure atomicity
        async with connection.transaction():
            result = await connection.fetchrow(query, guild_id, moderator_id, target_user_id, action_type, reason, duration_seconds)
            if result:
                log.info(f"Added mod log entry for guild {guild_id}, action {action_type}. Case ID: {result['case_id']}")
                return result['case_id']
            else:
                log.error(f"Failed to add mod log entry for guild {guild_id}, action {action_type} - No case_id returned.")
                return None
    except Exception as e:
        log.exception(f"Error adding mod log entry: {e}")
        return None
    finally:
        # Always release the connection back to the pool
        try:
            await pool.release(connection)
        except Exception as e:
            log.warning(f"Error releasing connection back to pool: {e}")
            # Continue execution even if we can't release the connection

async def update_mod_log_reason(pool: asyncpg.Pool, case_id: int, new_reason: str):
    """Updates the reason for a specific moderation log entry."""
    query = """
        UPDATE moderation_logs
        SET reason = $1
        WHERE case_id = $2;
    """
    # Get a connection with retry logic
    connection, success = await create_connection_with_retry(pool)
    if not success or not connection:
        log.error(f"Failed to acquire database connection for updating reason for case_id {case_id}")
        return False

    try:
        # Use a transaction to ensure atomicity
        async with connection.transaction():
            result = await connection.execute(query, new_reason, case_id)
            if result == "UPDATE 1":
                log.info(f"Updated reason for case_id {case_id}")
                return True
            else:
                log.warning(f"Could not update reason for case_id {case_id}. Case might not exist or no change made.")
                return False
    except Exception as e:
        log.exception(f"Error updating mod log reason for case_id {case_id}: {e}")
        return False
    finally:
        # Always release the connection back to the pool
        try:
            await pool.release(connection)
        except Exception as e:
            log.warning(f"Error releasing connection back to pool: {e}")
            # Continue execution even if we can't release the connection

async def update_mod_log_message_details(pool: asyncpg.Pool, case_id: int, message_id: int, channel_id: int):
    """Updates the log_message_id and log_channel_id for a specific case."""
    query = """
        UPDATE moderation_logs
        SET log_message_id = $1, log_channel_id = $2
        WHERE case_id = $3;
    """
    # Get a connection with retry logic
    connection, success = await create_connection_with_retry(pool)
    if not success or not connection:
        log.error(f"Failed to acquire database connection for updating message details for case_id {case_id}")
        return False

    try:
        # Use a transaction to ensure atomicity
        async with connection.transaction():
            result = await connection.execute(query, message_id, channel_id, case_id)
            if result == "UPDATE 1":
                log.info(f"Updated message details for case_id {case_id}")
                return True
            else:
                log.warning(f"Could not update message details for case_id {case_id}. Case might not exist or no change made.")
                return False
    except Exception as e:
        log.exception(f"Error updating mod log message details for case_id {case_id}: {e}")
        return False
    finally:
        # Always release the connection back to the pool
        try:
            await pool.release(connection)
        except Exception as e:
            log.warning(f"Error releasing connection back to pool: {e}")
            # Continue execution even if we can't release the connection

async def get_mod_log(pool: asyncpg.Pool, case_id: int) -> Optional[asyncpg.Record]:
    """Retrieves a specific moderation log entry by case_id."""
    query = "SELECT * FROM moderation_logs WHERE case_id = $1;"

    # Get a connection with retry logic
    connection, success = await create_connection_with_retry(pool)
    if not success or not connection:
        log.error(f"Failed to acquire database connection for retrieving mod log for case_id {case_id}")
        return None

    try:
        record = await connection.fetchrow(query, case_id)
        return record
    except Exception as e:
        log.exception(f"Error retrieving mod log for case_id {case_id}: {e}")
        return None
    finally:
        # Always release the connection back to the pool
        try:
            await pool.release(connection)
        except Exception as e:
            log.warning(f"Error releasing connection back to pool: {e}")

async def get_user_mod_logs(pool: asyncpg.Pool, guild_id: int, target_user_id: int, limit: int = 50) -> List[asyncpg.Record]:
    """Retrieves moderation logs for a specific user in a guild, ordered by timestamp descending."""
    query = """
        SELECT * FROM moderation_logs
        WHERE guild_id = $1 AND target_user_id = $2
        ORDER BY timestamp DESC
        LIMIT $3;
    """
    # Get a connection with retry logic
    connection, success = await create_connection_with_retry(pool)
    if not success or not connection:
        log.error(f"Failed to acquire database connection for retrieving user mod logs for user {target_user_id} in guild {guild_id}")
        return []

    try:
        records = await connection.fetch(query, guild_id, target_user_id, limit)
        return records
    except Exception as e:
        log.exception(f"Error retrieving user mod logs for user {target_user_id} in guild {guild_id}: {e}")
        return []
    finally:
        # Always release the connection back to the pool
        try:
            await pool.release(connection)
        except Exception as e:
            log.warning(f"Error releasing connection back to pool: {e}")

async def get_guild_mod_logs(pool: asyncpg.Pool, guild_id: int, limit: int = 50) -> List[asyncpg.Record]:
    """Retrieves the latest moderation logs for a guild, ordered by timestamp descending."""
    query = """
        SELECT * FROM moderation_logs
        WHERE guild_id = $1
        ORDER BY timestamp DESC
        LIMIT $2;
    """
    # Get a connection with retry logic
    connection, success = await create_connection_with_retry(pool)
    if not success or not connection:
        log.error(f"Failed to acquire database connection for retrieving guild mod logs for guild {guild_id}")
        return []

    try:
        records = await connection.fetch(query, guild_id, limit)
        return records
    except Exception as e:
        log.exception(f"Error retrieving guild mod logs for guild {guild_id}: {e}")
        return []
    finally:
        # Always release the connection back to the pool
        try:
            await pool.release(connection)
        except Exception as e:
            log.warning(f"Error releasing connection back to pool: {e}")
