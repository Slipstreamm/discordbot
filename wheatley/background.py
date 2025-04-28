import asyncio
import time
import traceback
import os
import json
import aiohttp
from typing import TYPE_CHECKING

# Relative imports
from .config import (
    STATS_PUSH_INTERVAL # Only keep stats interval
)
# Removed analysis imports

if TYPE_CHECKING:
    from .cog import WheatleyCog # Updated type hint

# --- Background Task ---

async def background_processing_task(cog: 'WheatleyCog'): # Updated type hint
    """Background task that periodically pushes stats.""" # Simplified docstring
    # Get API details from environment for stats pushing
    api_internal_url = os.getenv("API_INTERNAL_URL")
    # Use a generic secret name or a Wheatley-specific one if desired
    stats_push_secret = os.getenv("WHEATLEY_STATS_PUSH_SECRET", os.getenv("GURT_STATS_PUSH_SECRET")) # Fallback to GURT secret if needed

    if not api_internal_url:
        print("WARNING: API_INTERNAL_URL not set. Wheatley stats will not be pushed.") # Updated text
    if not stats_push_secret:
        print("WARNING: WHEATLEY_STATS_PUSH_SECRET (or GURT_STATS_PUSH_SECRET) not set. Stats push endpoint is insecure and likely won't work.") # Updated text

    try:
        while True:
            await asyncio.sleep(STATS_PUSH_INTERVAL) # Use the stats interval directly
            now = time.time()

            # --- Push Stats ---
            if api_internal_url and stats_push_secret: # Removed check for last push time, rely on sleep interval
                print("Pushing Wheatley stats to API server...") # Updated text
                try:
                    stats_data = await cog.get_wheatley_stats() # Updated method call
                    headers = {
                        "Authorization": f"Bearer {stats_push_secret}",
                        "Content-Type": "application/json"
                    }
                    # Use the cog's session, ensure it's created
                    if cog.session:
                        # Set a reasonable timeout for the stats push
                        push_timeout = aiohttp.ClientTimeout(total=10) # 10 seconds total timeout
                        async with cog.session.post(api_internal_url, json=stats_data, headers=headers, timeout=push_timeout, ssl=True) as response: # Explicitly enable SSL verification
                            if response.status == 200:
                                print(f"Successfully pushed Wheatley stats (Status: {response.status})") # Updated text
                            else:
                                error_text = await response.text()
                                print(f"Failed to push Wheatley stats (Status: {response.status}): {error_text[:200]}") # Updated text, Log only first 200 chars
                    else:
                        print("Error pushing stats: WheatleyCog session not initialized.") # Updated text
                    # Removed updating cog.last_stats_push as we rely on sleep interval
                except aiohttp.ClientConnectorSSLError as ssl_err:
                     print(f"SSL Error pushing Wheatley stats: {ssl_err}. Ensure the API server's certificate is valid and trusted, or check network configuration.") # Updated text
                     print("If using a self-signed certificate for development, the bot process might need to trust it.")
                except aiohttp.ClientError as client_err:
                    print(f"HTTP Client Error pushing Wheatley stats: {client_err}") # Updated text
                except asyncio.TimeoutError:
                    print("Timeout error pushing Wheatley stats.") # Updated text
                except Exception as e:
                    print(f"Unexpected error pushing Wheatley stats: {e}") # Updated text
                    traceback.print_exc()

            # --- Removed Learning Analysis ---
            # --- Removed Evolve Personality ---
            # --- Removed Update Interests ---
            # --- Removed Memory Reflection ---
            # --- Removed Goal Decomposition ---
            # --- Removed Goal Execution ---
            # --- Removed Automatic Mood Change ---

    except asyncio.CancelledError:
        print("Wheatley background processing task cancelled") # Updated text
    except Exception as e:
        print(f"Error in Wheatley background processing task: {e}") # Updated text
        traceback.print_exc()
        await asyncio.sleep(300) # Wait 5 minutes before retrying after an error

# --- Removed Automatic Mood Change Logic ---
# --- Removed Interest Update Logic ---
