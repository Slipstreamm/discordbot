import os
import sys
import asyncio
import argparse
import gurt_bot

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Gurt Discord Bot.")
    parser.add_argument(
        '--minimal-prompt',
        action='store_true',
        help='Use a minimal system prompt suitable for fine-tuned models.'
    )
    args = parser.parse_args()

    try:
        # Pass the argument to the main function
        asyncio.run(gurt_bot.main(minimal_prompt=args.minimal_prompt))
    except KeyboardInterrupt:
        print("Gurt Bot stopped by user.")
    except Exception as e:
        print(f"An error occurred running Gurt Bot: {e}")
