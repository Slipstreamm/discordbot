import os
import sys
import time
import json
import threading
import asyncio
import multi_bot
import gurt_bot

def run_gurt_bot_in_thread():
    """Run the Gurt Bot in a separate thread"""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=lambda: loop.run_until_complete(gurt_bot.main()), daemon=True)
    thread.start()
    return thread

def main():
    """Main function to run all additional bots"""
    print("Starting additional bots (Neru, Miku, and Gurt)...")

    # Start all multi bots
    bot_threads = multi_bot.start_all_bots()

    # Start Gurt Bot
    gurt_thread = run_gurt_bot_in_thread()
    bot_threads.append(("gurt", gurt_thread))

    if not bot_threads:
        print("No bots were started. Check your configuration in data/multi_bot_config.json")
        return

    print(f"Started {len(bot_threads)} bots.")
    print("Bot IDs: " + ", ".join([bot_id for bot_id, _ in bot_threads]))

    try:
        # Keep the main thread alive
        while True:
            # Check if any threads have died
            for bot_id, thread in bot_threads[:]:
                if not thread.is_alive():
                    print(f"Thread for bot {bot_id} died, restarting...")
                    if bot_id == "gurt":
                        new_thread = run_gurt_bot_in_thread()
                    else:
                        new_thread = multi_bot.run_bot_in_thread(bot_id)
                    bot_threads.remove((bot_id, thread))
                    bot_threads.append((bot_id, new_thread))

            # Sleep to avoid high CPU usage
            time.sleep(60)
    except KeyboardInterrupt:
        print("Stopping all bots...")
        # The threads are daemon threads, so they will be terminated when the main thread exits
        print("Bots stopped.")

if __name__ == "__main__":
    main()
