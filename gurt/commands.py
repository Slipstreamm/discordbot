import discord
from discord.ext import commands
import random
import os
from typing import TYPE_CHECKING

# Relative imports (assuming API functions are in api.py)
# We need access to the cog instance for state and methods like get_ai_response
# These commands will likely be added to the GurtCog instance dynamically in cog.py's setup

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting

# --- Command Implementations ---
# Note: These functions assume they will be registered as commands associated with a GurtCog instance.
#       The 'cog' parameter will be implicitly passed by discord.py when registered correctly.

@commands.command(name="gurt")
async def gurt_command(cog: 'GurtCog', ctx: commands.Context):
    """The main gurt command"""
    from .config import GURT_RESPONSES # Import here
    response = random.choice(GURT_RESPONSES)
    await ctx.send(response)

@commands.command(name="gurtai")
async def gurt_ai_command(cog: 'GurtCog', ctx: commands.Context, *, prompt: str):
    """Get a response from the AI"""
    from .api import get_ai_response # Import API function

    # Create a pseudo-message object or pass necessary info
    # For simplicity, we'll pass the context's message object,
    # but modify its content for the AI call.
    ai_message = ctx.message
    ai_message.content = prompt # Override content with the prompt argument

    try:
        # Show typing indicator
        async with ctx.typing():
            # Get AI response bundle
            response_bundle = await get_ai_response(cog, ai_message) # Pass cog and message

        # Check for errors or no response
        error_msg = response_bundle.get("error")
        initial_response = response_bundle.get("initial_response")
        final_response = response_bundle.get("final_response")
        response_to_use = final_response if final_response else initial_response

        if error_msg:
            print(f"Error in gurtai command: {error_msg}")
            await ctx.reply(f"Sorry, I'm having trouble thinking right now. Details: {error_msg}")
            return

        if not response_to_use or not response_to_use.get("should_respond", False):
            await ctx.reply("I don't have anything to say about that right now.")
            return

        response_text = response_to_use.get("content", "")
        if not response_text:
             await ctx.reply("I decided not to respond with text.")
             return

        # Handle long responses
        if len(response_text) > 1900:
            filepath = f'gurt_response_{ctx.author.id}.txt'
            try:
                with open(filepath, 'w', encoding='utf-8') as f: f.write(response_text)
                await ctx.send("Response too long, sending as file:", file=discord.File(filepath))
            except Exception as file_e: print(f"Error writing/sending long response file: {file_e}")
            finally:
                try: os.remove(filepath)
                except OSError as os_e: print(f"Error removing temp file {filepath}: {os_e}")
        else:
            await ctx.reply(response_text)

    except Exception as e:
        error_message = f"Error processing gurtai request: {str(e)}"
        print(f"Exception in gurt_ai_command: {error_message}")
        import traceback
        traceback.print_exc()
        await ctx.reply("Sorry, an unexpected error occurred.")

@commands.command(name="gurtmodel")
@commands.is_owner() # Keep owner check for sensitive commands
async def set_model_command(cog: 'GurtCog', ctx: commands.Context, *, model: str):
    """Set the AI model to use (Owner only)"""
    # Model setting might need to update config or cog state directly
    # For now, let's assume it updates a cog attribute.
    # Validation might be better handled in config loading or a dedicated setter.
    # if not model.endswith(":free"): # Example validation
    #     await ctx.reply("Error: Model name must end with `:free`. Setting not updated.")
    #     return

    cog.default_model = model # Update the cog's default model attribute
    # TODO: Consider if this needs to persist somewhere or update config dynamically.
    await ctx.reply(f"AI model temporarily set to: `{model}` for this session.")
    print(f"Gurt model changed to {model} by {ctx.author.name}")

@commands.command(name="gurtstatus")
async def gurt_status_command(cog: 'GurtCog', ctx: commands.Context):
    """Display the current status of Gurt Bot"""
    embed = discord.Embed(
        title="Gurt Bot Status",
        description="Current configuration and status",
        color=discord.Color.green()
    )
    embed.add_field(name="Current Model", value=f"`{cog.default_model}`", inline=False)
    embed.add_field(name="API Session", value="Active" if cog.session and not cog.session.closed else "Inactive", inline=True)
    # Add other relevant status info from the cog if needed
    # embed.add_field(name="Current Mood", value=cog.current_mood, inline=True)
    await ctx.send(embed=embed)

@commands.command(name="gurthelp")
async def gurt_help_command(cog: 'GurtCog', ctx: commands.Context):
    """Display help information for Gurt Bot"""
    from .config import TOOLS # Import TOOLS definition

    embed = discord.Embed(
        title="Gurt Bot Help",
        description="Gurt is an autonomous AI participant.",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="Commands",
        value=f"`{cog.bot.command_prefix}gurt` - Gurt!\n"
              f"`{cog.bot.command_prefix}gurtai <prompt>` - Ask Gurt AI directly\n"
              f"`{cog.bot.command_prefix}gurtstatus` - Show current status\n"
              f"`{cog.bot.command_prefix}gurthelp` - This help message\n"
              f"`{cog.bot.command_prefix}gurtmodel <model>` - Set AI model (Owner)\n"
              f"`{cog.bot.command_prefix}force_profile_update` - Trigger profile update (Owner)",
        inline=False
    )
    embed.add_field(
        name="Autonomous Behavior",
        value="Gurt listens and responds naturally based on conversation, mentions, and interests.",
        inline=False
    )
    # Dynamically list available tools from config
    tool_list = "\n".join([f"- `{tool['function']['name']}`: {tool['function']['description']}" for tool in TOOLS])
    embed.add_field(name="Available AI Tools", value=tool_list, inline=False)

    await ctx.send(embed=embed)

@commands.command(name="force_profile_update")
@commands.is_owner()
async def force_profile_update_command(cog: 'GurtCog', ctx: commands.Context):
    """Manually triggers the profile update cycle (Owner only)."""
    # This command interacts with another cog, which is complex after refactoring.
    # Option 1: Keep this command in a separate 'owner' cog that knows about other cogs.
    # Option 2: Use bot events/listeners for inter-cog communication.
    # Option 3: Access the other cog directly via self.bot.get_cog (simplest for now).
    profile_updater_cog = cog.bot.get_cog('ProfileUpdaterCog')
    if not profile_updater_cog:
        await ctx.reply("Error: ProfileUpdaterCog not found.")
        return

    if not hasattr(profile_updater_cog, 'perform_update_cycle') or not hasattr(profile_updater_cog, 'profile_update_task'):
        await ctx.reply("Error: ProfileUpdaterCog is missing required methods/tasks.")
        return

    try:
        await ctx.reply("Manually triggering profile update cycle...")
        await profile_updater_cog.perform_update_cycle()
        # Restarting the loop might be internal to that cog now
        if hasattr(profile_updater_cog.profile_update_task, 'restart'):
             profile_updater_cog.profile_update_task.restart()
             await ctx.reply("Profile update cycle triggered and timer reset.")
        else:
             await ctx.reply("Profile update cycle triggered (task restart mechanism not found).")
        print(f"Profile update cycle manually triggered by {ctx.author.name}.")
    except Exception as e:
        await ctx.reply(f"An error occurred while triggering the profile update: {e}")
        print(f"Error during manual profile update trigger: {e}")
        import traceback
        traceback.print_exc()

# Helper function to add these commands to the cog instance
def setup_commands(cog: 'GurtCog'):
    """Adds the commands defined in this file to the GurtCog."""
    # Add commands directly to the bot instance, associated with the cog
    cog.bot.add_command(gurt_command)
    cog.bot.add_command(gurt_ai_command)
    cog.bot.add_command(set_model_command)
    cog.bot.add_command(gurt_status_command)
    cog.bot.add_command(gurt_help_command)
    cog.bot.add_command(force_profile_update_command)
