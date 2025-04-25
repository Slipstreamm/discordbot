import os
import asyncio
import discord
from discord.ext import commands

async def load_all_cogs(bot: commands.Bot):
    """Loads all cogs from the 'cogs' directory."""
    cogs_dir = "cogs"
    loaded_cogs = []
    failed_cogs = []

    for filename in os.listdir(cogs_dir):
        if filename.endswith(".py") and not filename.startswith("__") and not filename.startswith("gurt"):
            cog_name = f"{cogs_dir}.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                print(f"Successfully loaded cog: {cog_name}")
                loaded_cogs.append(cog_name)
            except commands.ExtensionAlreadyLoaded:
                print(f"Cog already loaded: {cog_name}")
                # Optionally reload if needed: await bot.reload_extension(cog_name)
            except commands.ExtensionNotFound:
                print(f"Error: Cog not found: {cog_name}")
                failed_cogs.append(cog_name)
            except commands.NoEntryPointError:
                print(f"Error: Cog {cog_name} has no setup function.")
                failed_cogs.append(cog_name)
            except commands.ExtensionFailed as e:
                print(f"Error: Cog {cog_name} failed to load.")
                print(f"  Reason: {e.original}") # Print the original exception
                failed_cogs.append(cog_name)
            except Exception as e:
                print(f"An unexpected error occurred loading cog {cog_name}: {e}")
                failed_cogs.append(cog_name)

    print("-" * 20)
    if loaded_cogs:
        print(f"Loaded {len(loaded_cogs)} cogs successfully.")
    if failed_cogs:
        print(f"Failed to load {len(failed_cogs)} cogs: {', '.join(failed_cogs)}")
    print("-" * 20)

# You might want a similar function for unloading or reloading
async def unload_all_cogs(bot: commands.Bot):
    """Unloads all currently loaded cogs from the 'cogs' directory."""
    unloaded_cogs = []
    failed_unload = []
    # Get loaded cogs that are likely from our directory
    loaded_extensions = list(bot.extensions.keys())
    for extension in loaded_extensions:
        if extension.startswith("cogs."):
            try:
                await bot.unload_extension(extension)
                print(f"Successfully unloaded cog: {extension}")
                unloaded_cogs.append(extension)
            except Exception as e:
                print(f"Failed to unload cog {extension}: {e}")
                failed_unload.append(extension)
    return unloaded_cogs, failed_unload

async def reload_all_cogs(bot: commands.Bot):
    """Reloads all currently loaded cogs from the 'cogs' directory."""
    reloaded_cogs = []
    failed_reload = []
    loaded_extensions = list(bot.extensions.keys())
    for extension in loaded_extensions:
         if extension.startswith("cogs."):
            try:
                await bot.reload_extension(extension)
                print(f"Successfully reloaded cog: {extension}")
                reloaded_cogs.append(extension)
            except commands.ExtensionNotLoaded:
                 print(f"Cog {extension} was not loaded, attempting to load instead.")
                 try:
                     await bot.load_extension(extension)
                     print(f"Successfully loaded cog: {extension}")
                     reloaded_cogs.append(extension) # Count as reloaded for simplicity
                 except Exception as load_e:
                     print(f"Failed to load cog {extension} during reload attempt: {load_e}")
                     failed_reload.append(extension)
            except Exception as e:
                print(f"Failed to reload cog {extension}: {e}")
                # Attempt to unload if reload fails badly? Maybe too complex here.
                failed_reload.append(extension)
    return reloaded_cogs, failed_reload
