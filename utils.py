import sys
import importlib
import asyncio
import os
import traceback
import time # Added import
import discord
from discord.ext import commands as discord_commands

# Flag to indicate a reload is requested
_reload_pending = False

# Assuming commands.py and error_handler.py are in the root directory alongside utils.py
MODULES_TO_RELOAD = [
    'utils',        # Reload self first? Risky but might be needed.
    'error_handler',
    'commands'
]

COG_DIRECTORY = 'cogs'
AUDIO_COG_EXTENSION_NAME = 'cogs.audio_cog' # Assuming this is the correct name

async def reload_all_code(bot):
    """Unload cogs (except audio if connected), reload modules/cogs, load back."""
    print("--- Starting Full Code Reload ---")
    reloaded_modules = set()
    failed_modules = set()
    loaded_cogs = set()
    failed_cogs = set()
    skipped_cogs = set() # Keep track of skipped cogs

    # Check if bot is in any voice channel
    is_in_voice = any(vc.is_connected() for vc in bot.voice_clients)
    print(f"Bot is currently in a voice channel: {is_in_voice}")

    # 1. Unload existing cogs gracefully (skip audio if connected)
    print("Unloading existing cogs...")
    original_extensions = list(bot.extensions.keys()) # Store original extension names
    extensions_to_unload = list(original_extensions) # Copy to modify

    if is_in_voice and AUDIO_COG_EXTENSION_NAME in extensions_to_unload:
        print(f"  Skipping unload for {AUDIO_COG_EXTENSION_NAME} (bot is in voice).")
        extensions_to_unload.remove(AUDIO_COG_EXTENSION_NAME)
        skipped_cogs.add(AUDIO_COG_EXTENSION_NAME)

    for extension_name in extensions_to_unload:
        try:
            print(f"  Unloading extension: {extension_name}")
            await bot.unload_extension(extension_name)
        except Exception as e:
            print(f"  Error unloading extension {extension_name}: {e}")
            traceback.print_exc()
            failed_modules.add(extension_name) # Mark as failed if unload fails

    # Clear command caches (important after unloading)
    bot.all_commands.clear()
    bot.tree.clear_commands(guild=None) # Clear global app commands
    # Consider clearing guild-specific commands if used:
    # for guild_id in bot.guilds:
    #    bot.tree.clear_commands(guild=discord.Object(id=guild_id))

    print("Reloading core modules...")
    # 2. Reload core modules (utils, error_handler, commands)
    for module_name in MODULES_TO_RELOAD:
        try:
            if module_name in sys.modules:
                print(f"  Reloading module: {module_name}")
                importlib.reload(sys.modules[module_name])
                reloaded_modules.add(module_name)
            else:
                print(f"  Module not loaded, skipping reload: {module_name}")
        except Exception as e:
            print(f"  Error reloading module {module_name}: {e}")
            traceback.print_exc()
            failed_modules.add(module_name)

    print("Reloading core modules...")
    # 2. Reload core modules (utils, error_handler, commands) - This is generally safe
    for module_name in MODULES_TO_RELOAD:
        try:
            if module_name in sys.modules:
                print(f"  Reloading module: {module_name}")
                importlib.reload(sys.modules[module_name])
                reloaded_modules.add(module_name)
            else:
                print(f"  Module not loaded, skipping reload: {module_name}")
        except Exception as e:
            print(f"  Error reloading module {module_name}: {e}")
            traceback.print_exc()
            failed_modules.add(module_name)

    print("Reloading/Loading extensions...")
    # 3. Reload underlying cog modules and load extensions back
    # Use the original list to attempt loading everything that *should* be loaded
    for extension_name in original_extensions:
        # Skip audio cog if it was intentionally skipped during unload
        if extension_name in skipped_cogs:
            print(f"  Skipping reload/load for {extension_name} (was not unloaded).")
            # Attempt to reload the underlying module anyway? Risky. Let's skip for now.
            # try:
            #     if extension_name in sys.modules:
            #         print(f"    (Attempting module reload for skipped cog: {extension_name})")
            #         importlib.reload(sys.modules[extension_name])
            #         reloaded_modules.add(extension_name)
            # except Exception as e:
            #     print(f"    Error reloading module for skipped cog {extension_name}: {e}")
            #     failed_modules.add(extension_name) # Mark module reload as failed
            continue

        # Skip if unload failed previously
        if extension_name in failed_modules:
            print(f"  Skipping reload/load for previously failed unload: {extension_name}")
            continue
        try:
            # Reload the underlying module first (if it exists)
            # This handles changes within the cog file itself
            if extension_name in sys.modules:
                 print(f"  Reloading cog module: {extension_name}")
                 importlib.reload(sys.modules[extension_name])
                 reloaded_modules.add(extension_name)

            # Load the extension back into the bot
            print(f"  Loading extension: {extension_name}")
            await bot.load_extension(extension_name)
            loaded_cogs.add(extension_name)
            # If the module was previously marked as failed during reload, remove it now
            failed_modules.discard(extension_name) # Remove from failed set as it's now loaded
        except discord_commands.ExtensionAlreadyLoaded:
             print(f"  Extension already loaded (likely the skipped audio cog or error): {extension_name}")
             # This might happen if the audio cog wasn't properly skipped or another issue occurred
             if extension_name not in skipped_cogs:
                 failed_cogs.add(extension_name) # Mark as failed if it wasn't intentionally skipped
             pass
        except Exception as e:
            print(f"  Error reloading/loading extension {extension_name}: {e}")
            traceback.print_exc()
            failed_cogs.add(extension_name)
            failed_modules.add(extension_name) # Mark as failed

    # 4. Sync application commands (optional, but good practice after reload)
    try:
        print("Syncing application commands...")
        await bot.tree.sync()
        print("Application commands synced.")
    except Exception as e:
        print(f"Error syncing application commands: {e}")
        traceback.print_exc()

    # 5. Report Summary
    print("--- Reload Complete ---")
    print(f"Successfully reloaded modules: {reloaded_modules if reloaded_modules else 'None'}")
    print(f"Successfully loaded cogs: {loaded_cogs if loaded_cogs else 'None'}")
    if skipped_cogs:
        print(f"Skipped unload/load for cogs (due to voice connection): {skipped_cogs}")
    if failed_modules:
        print(f"Failed to reload/unload modules/extensions: {failed_modules - skipped_cogs}") # Exclude skipped from failures
    if failed_cogs:
         print(f"Failed to load cogs: {failed_cogs - skipped_cogs}") # Exclude skipped from failures
    print("-----------------------")

    success = not (failed_modules - skipped_cogs) and not (failed_cogs - skipped_cogs)
    message = "Deferred code reload completed."
    if not success:
        message += f" Errors occurred during reload. Check console logs. Failed modules/cogs: {failed_modules | failed_cogs}"

    return success, message

async def check_and_reload_hook(ctx: discord_commands.Context):
    """before_invoke hook to check if a reload is pending and execute it."""
    global _reload_pending
    if _reload_pending:
        bot = ctx.bot
        print(f"--- Reload triggered before command '{ctx.command}' by {ctx.author} ---")
        # Prevent triggering reload again immediately
        _reload_pending = False
        # Reset the trigger file timestamp *before* reload to avoid race conditions
        # where the file watcher triggers again during the reload process.
        reload_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reload_trigger.txt')
        try:
            current_time = time.time()
            os.utime(reload_file, (current_time, current_time)) # Update access and modified time
            print(f"Updated timestamp for {reload_file} to prevent immediate re-trigger.")
        except Exception as e:
            print(f"Warning: Could not update timestamp for {reload_file}: {e}")

        # Perform the reload
        success, message = await reload_all_code(bot)
        print(message) # Log completion message

        # Optionally notify the user who triggered the command that a reload happened
        # try:
        #     await ctx.send(f"Bot code reloaded before executing your command. {message}", ephemeral=True)
        # except discord.HTTPException:
        #     pass # Ignore if we can't send

        # Update the trigger file content *after* reload attempt
        try:
            with open(reload_file, 'w') as f:
                f.write('Edit and save this file to trigger a deferred reload before the next command.\n')
                f.write(f'Last deferred reload attempt: {time.strftime("%Y-%m-%d %H:%M:%S")} (Success: {success})\n')
        except Exception as e:
             print(f"Error updating reload trigger file content after reload: {e}")

# Keep the bot instance logic

# Store a reference to the bot instance
_bot_instance = None
import os
import time

def set_bot_instance(bot):
    """Store a reference to the bot instance for reloading."""
    global _bot_instance
    _bot_instance = bot
    
    # Create reload trigger file if it doesn't exist
    reload_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reload_trigger.txt')
    if not os.path.exists(reload_file):
        with open(reload_file, 'w') as f:
            f.write('Edit and save this file to trigger a reload of the bot commands.\n')
            f.write(f'Last reload: Never\n')

def listen_for_reload():
    """Monitor the reload_trigger.txt file for changes to trigger a reload."""
    reload_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reload_trigger.txt')
    
    # Get initial modification time
    last_modified = os.path.getmtime(reload_file) if os.path.exists(reload_file) else 0
    print(f"Monitoring {reload_file} for changes to trigger reloads...")
    
    try:
        while True:
            # Check if file exists and if it has been modified
            if os.path.exists(reload_file):
                current_modified = os.path.getmtime(reload_file)
                
                # If the file was modified since we last checked
                if current_modified > last_modified:
                    print("Reload trigger file modified. Flagging for deferred reload.")
                    global _reload_pending
                    _reload_pending = True

                    # Update the last modified time immediately to prevent multiple triggers
                    # Update the last modified time immediately to prevent multiple triggers
                    # from the *same* save event within this loop.
                    # The hook will handle updating the file content later.
                    last_modified = current_modified

            # Add a short delay to prevent high CPU usage
            time.sleep(1) # Check every second
    except KeyboardInterrupt:
        print("Reload monitoring stopped.")
    except Exception as e:
        print(f"Error in reload monitor: {str(e)}")
