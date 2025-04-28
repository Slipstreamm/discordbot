import os
import sys
import asyncio
import wheatley_bot # Changed import from gurt_bot

if __name__ == "__main__":
    try:
        asyncio.run(wheatley_bot.main()) # Changed function call
    except KeyboardInterrupt:
        print("Wheatley Bot stopped by user.") # Changed print statement
    except Exception as e:
        print(f"An error occurred running Wheatley Bot: {e}") # Changed print statement
