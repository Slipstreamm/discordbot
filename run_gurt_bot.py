import os
import sys
import asyncio
import gurt_bot

if __name__ == "__main__":
    try:
        asyncio.run(gurt_bot.main())
    except KeyboardInterrupt:
        print("Gurt Bot stopped by user.")
    except Exception as e:
        print(f"An error occurred running Gurt Bot: {e}")
