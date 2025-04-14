import asyncio
import subprocess
import os
import sys

async def check_for_updates(interval=15):
    while True:
        await asyncio.sleep(interval)
        try:
            subprocess.run(["git", "fetch"], check=True)
            status = subprocess.check_output(["git", "status", "-uno"]).decode()

            if "Your branch is behind" in status:
                print("Update detected. Pulling changes and restarting bot...")
                subprocess.run(["git", "pull"], check=True)

                # Restart the bot
                os.execv(sys.executable, [sys.executable] + sys.argv)

        except subprocess.CalledProcessError as e:
            print(f"Git command failed: {e}")

# Example usage in your bot script:
# import discord
# from discord.ext import commands

# bot = commands.Bot(command_prefix="!")

# @bot.event
# async def on_ready():
#     print(f"Logged in as {bot.user}")
#     bot.loop.create_task(check_for_updates())

# bot.run("YOUR_TOKEN")
