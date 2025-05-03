import aiosqlite
import os
import datetime
import logging
from typing import Optional

# Configure logging
log = logging.getLogger(__name__)

# Database path (adjust relative path)
DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
DB_PATH = os.path.join(DB_DIR, 'economy.db')

# Ensure the data directory exists
os.makedirs(DB_DIR, exist_ok=True)

# --- Database Setup ---

async def init_db():
    """Initializes the database and creates tables if they don't exist."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Create economy table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0
                )
            """)
            log.info("Checked/created 'economy' table.")

            # Create command_cooldowns table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS command_cooldowns (
                    user_id INTEGER NOT NULL,
                    command_name TEXT NOT NULL,
                    last_used TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, command_name)
                )
            """)
            log.info("Checked/created 'command_cooldowns' table.")

            # Create user_jobs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_jobs (
                    user_id INTEGER PRIMARY KEY,
                    job_name TEXT,
                    job_level INTEGER NOT NULL DEFAULT 1,
                    job_xp INTEGER NOT NULL DEFAULT 0,
                    last_job_action TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES economy(user_id) ON DELETE CASCADE
                )
            """)
            log.info("Checked/created 'user_jobs' table.")

            # Create items table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    sell_price INTEGER NOT NULL DEFAULT 0
                )
            """)
            log.info("Checked/created 'items' table.")
            # --- Add some basic items ---
            initial_items = [
                ('raw_iron', 'Raw Iron Ore', 'Basic metal ore.', 5),
                ('coal', 'Coal', 'A lump of fossil fuel.', 3),
                ('shiny_gem', 'Shiny Gem', 'A pretty, potentially valuable gem.', 50),
                ('common_fish', 'Common Fish', 'A standard fish.', 4),
                ('rare_fish', 'Rare Fish', 'An uncommon fish.', 15),
                ('treasure_chest', 'Treasure Chest', 'Might contain goodies!', 0), # Sell price 0, opened via command?
                ('iron_ingot', 'Iron Ingot', 'Refined iron, ready for crafting.', 12),
                ('basic_tool', 'Basic Tool', 'A simple tool.', 25)
            ]
            await db.executemany("""
                INSERT OR IGNORE INTO items (item_key, name, description, sell_price)
                VALUES (?, ?, ?, ?)
            """, initial_items)
            log.info("Ensured initial items exist.")


            # Create user_inventory table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_inventory (
                    user_id INTEGER NOT NULL,
                    item_key TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (user_id, item_key),
                    FOREIGN KEY (user_id) REFERENCES economy(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (item_key) REFERENCES items(item_key) ON DELETE CASCADE
                )
            """)
            log.info("Checked/created 'user_inventory' table.")

            await db.commit()
            log.info(f"Economy database initialized successfully at {DB_PATH}")
    except Exception as e:
        log.error(f"Failed to initialize economy database at {DB_PATH}: {e}", exc_info=True)
        raise # Re-raise the exception

# --- Database Helper Functions ---

async def get_balance(user_id: int) -> int:
    """Gets the balance for a user, creating an entry if needed."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return result[0]
            else:
                try:
                    await db.execute("INSERT INTO economy (user_id, balance) VALUES (?, ?)", (user_id, 0))
                    await db.commit()
                    log.info(f"Created new economy entry for user_id: {user_id}")
                    return 0
                except aiosqlite.IntegrityError:
                    log.warning(f"Race condition handled for user_id: {user_id} during balance fetch.")
                    async with db.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,)) as cursor_retry:
                        result_retry = await cursor_retry.fetchone()
                        return result_retry[0] if result_retry else 0

async def update_balance(user_id: int, amount: int):
    """Updates a user's balance by adding the specified amount (can be negative)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Ensure user exists first by trying to get balance
        await get_balance(user_id)
        await db.execute("UPDATE economy SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        log.debug(f"Updated balance for user_id {user_id} by {amount}.")

async def check_cooldown(user_id: int, command_name: str) -> Optional[datetime.datetime]:
    """Checks if a command is on cooldown for a user. Returns the last used time if on cooldown, else None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_used FROM command_cooldowns WHERE user_id = ? AND command_name = ?", (user_id, command_name)) as cursor:
            result = await cursor.fetchone()
            if result:
                try:
                    # Timestamps are stored in ISO format
                    last_used_dt = datetime.datetime.fromisoformat(result[0])
                    # Ensure it's timezone-aware (UTC) if it's not already
                    if last_used_dt.tzinfo is None:
                         last_used_dt = last_used_dt.replace(tzinfo=datetime.timezone.utc)
                    return last_used_dt
                except ValueError:
                    log.error(f"Could not parse timestamp '{result[0]}' for user {user_id}, command {command_name}")
                    return None
            else:
                return None

async def set_cooldown(user_id: int, command_name: str):
    """Sets or updates the cooldown timestamp for a command."""
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO command_cooldowns (user_id, command_name, last_used)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, command_name) DO UPDATE SET last_used = excluded.last_used
        """, (user_id, command_name, now_iso))
        await db.commit()
        log.debug(f"Set cooldown for user_id {user_id}, command {command_name} to {now_iso}")

async def get_leaderboard(count: int = 10) -> list[tuple[int, int]]:
    """Retrieves the top users by balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, balance FROM economy ORDER BY balance DESC LIMIT ?", (count,)) as cursor:
            results = await cursor.fetchall()
            return results if results else []

# --- Job Functions ---

async def get_user_job(user_id: int) -> Optional[dict]:
    """Gets the user's job details (name, level, xp, last_action). Creates entry if needed."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Ensure user exists in economy table first
        await get_balance(user_id)
        # Try to fetch job
        async with db.execute("SELECT job_name, job_level, job_xp, last_job_action FROM user_jobs WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result:
                last_action = None
                if result[3]:
                    try:
                        last_action = datetime.datetime.fromisoformat(result[3])
                        if last_action.tzinfo is None:
                            last_action = last_action.replace(tzinfo=datetime.timezone.utc)
                    except ValueError:
                        log.error(f"Could not parse job timestamp '{result[3]}' for user {user_id}")
                return {"name": result[0], "level": result[1], "xp": result[2], "last_action": last_action}
            else:
                # Create job entry if it doesn't exist (defaults to no job)
                try:
                    await db.execute("INSERT INTO user_jobs (user_id, job_name, job_level, job_xp, last_job_action) VALUES (?, NULL, 1, 0, NULL)", (user_id,))
                    await db.commit()
                    log.info(f"Created default job entry for user_id: {user_id}")
                    return {"name": None, "level": 1, "xp": 0, "last_action": None}
                except aiosqlite.IntegrityError:
                    log.warning(f"Race condition handled for user_id: {user_id} during job fetch.")
                    # Retry fetch
                    async with db.execute("SELECT job_name, job_level, job_xp, last_job_action FROM user_jobs WHERE user_id = ?", (user_id,)) as cursor_retry:
                         result_retry = await cursor_retry.fetchone()
                         if result_retry:
                            last_action_retry = None
                            if result_retry[3]:
                                try:
                                    last_action_retry = datetime.datetime.fromisoformat(result_retry[3])
                                    if last_action_retry.tzinfo is None:
                                        last_action_retry = last_action_retry.replace(tzinfo=datetime.timezone.utc)
                                except ValueError: pass
                            return {"name": result_retry[0], "level": result_retry[1], "xp": result_retry[2], "last_action": last_action_retry}
                         else: # Should not happen after insert attempt, but handle defensively
                             return {"name": None, "level": 1, "xp": 0, "last_action": None}


async def set_user_job(user_id: int, job_name: Optional[str]):
    """Sets or clears a user's job. Resets level/xp if changing/leaving."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Ensure job entry exists
        await get_user_job(user_id)
        # Update job, resetting level/xp
        await db.execute("UPDATE user_jobs SET job_name = ?, job_level = 1, job_xp = 0 WHERE user_id = ?", (job_name, user_id))
        await db.commit()
        log.info(f"Set job for user_id {user_id} to {job_name}. Level/XP reset.")

async def add_job_xp(user_id: int, xp_amount: int) -> tuple[int, int, bool]:
    """Adds XP to the user's job, handles level ups. Returns (new_level, new_xp, did_level_up)."""
    async with aiosqlite.connect(DB_PATH) as db:
        job_info = await get_user_job(user_id)
        if not job_info or not job_info.get("name"):
            log.warning(f"Attempted to add XP to user {user_id} with no job.")
            return (1, 0, False) # Return default values if no job

        current_level = job_info["level"]
        current_xp = job_info["xp"]
        new_xp = current_xp + xp_amount
        did_level_up = False

        # --- Leveling Logic ---
        xp_needed = current_level * 100 # Example: Level 1 needs 100 XP, Level 2 needs 200 XP

        while new_xp >= xp_needed:
            new_xp -= xp_needed
            current_level += 1
            xp_needed = current_level * 100 # Update for next potential level
            did_level_up = True
            log.info(f"User {user_id} leveled up their job to {current_level}!")

        # Update database
        await db.execute("UPDATE user_jobs SET job_level = ?, job_xp = ? WHERE user_id = ?", (current_level, new_xp, user_id))
        await db.commit()
        log.debug(f"Updated job XP for user {user_id}. New Level: {current_level}, New XP: {new_xp}")
        return (current_level, new_xp, did_level_up)

async def set_job_cooldown(user_id: int):
    """Sets the job cooldown timestamp."""
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE user_jobs SET last_job_action = ? WHERE user_id = ?", (now_iso, user_id))
        await db.commit()
        log.debug(f"Set job cooldown for user_id {user_id} to {now_iso}")

# --- Item/Inventory Functions ---

async def get_item_details(item_key: str) -> Optional[dict]:
    """Gets details for a specific item."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name, description, sell_price FROM items WHERE item_key = ?", (item_key,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return {"key": item_key, "name": result[0], "description": result[1], "sell_price": result[2]}
            else:
                return None

async def get_inventory(user_id: int) -> list[dict]:
    """Gets a user's inventory."""
    inventory = []
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT inv.item_key, inv.quantity, i.name, i.description, i.sell_price
            FROM user_inventory inv
            JOIN items i ON inv.item_key = i.item_key
            WHERE inv.user_id = ?
            ORDER BY i.name
        """, (user_id,)) as cursor:
            results = await cursor.fetchall()
            for row in results:
                inventory.append({
                    "key": row[0],
                    "quantity": row[1],
                    "name": row[2],
                    "description": row[3],
                    "sell_price": row[4]
                })
    return inventory

async def add_item_to_inventory(user_id: int, item_key: str, quantity: int = 1):
    """Adds an item to the user's inventory."""
    if quantity <= 0:
        log.warning(f"Attempted to add non-positive quantity ({quantity}) of item {item_key} for user {user_id}")
        return
    # Check if item exists
    item_details = await get_item_details(item_key)
    if not item_details:
        log.error(f"Attempted to add non-existent item '{item_key}' to inventory for user {user_id}")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Ensure user exists in economy table
        await get_balance(user_id)
        await db.execute("""
            INSERT INTO user_inventory (user_id, item_key, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, item_key) DO UPDATE SET quantity = quantity + excluded.quantity
        """, (user_id, item_key, quantity))
        await db.commit()
        log.debug(f"Added {quantity} of {item_key} to user {user_id}'s inventory.")

async def remove_item_from_inventory(user_id: int, item_key: str, quantity: int = 1) -> bool:
    """Removes an item from the user's inventory. Returns True if successful, False otherwise."""
    if quantity <= 0:
        log.warning(f"Attempted to remove non-positive quantity ({quantity}) of item {item_key} for user {user_id}")
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        # Check current quantity first
        async with db.execute("SELECT quantity FROM user_inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key)) as cursor:
            result = await cursor.fetchone()
            if not result or result[0] < quantity:
                log.debug(f"User {user_id} does not have enough {item_key} (needs {quantity}, has {result[0] if result else 0})")
                return False # Not enough items

            current_quantity = result[0]
            if current_quantity == quantity:
                # Delete the row if quantity becomes zero
                await db.execute("DELETE FROM user_inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
            else:
                # Otherwise, just decrease the quantity
                await db.execute("UPDATE user_inventory SET quantity = quantity - ? WHERE user_id = ? AND item_key = ?", (quantity, user_id, item_key))

            await db.commit()
            log.debug(f"Removed {quantity} of {item_key} from user {user_id}'s inventory.")
            return True
