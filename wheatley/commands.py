import discord
from discord import app_commands # Import app_commands
from discord.ext import commands
import random
import os
import time # Import time for timestamps
import json # Import json for formatting
import datetime # Import datetime for formatting
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple # Add more types

# Relative imports
# We need access to the cog instance for state and methods

if TYPE_CHECKING:
    from .cog import WheatleyCog # For type hinting
    # MOOD_OPTIONS removed

# --- Helper Function for Embeds ---
def create_wheatley_embed(title: str, description: str = "", color=discord.Color.blue()) -> discord.Embed: # Renamed function
    """Creates a standard Wheatley-themed embed.""" # Updated docstring
    embed = discord.Embed(title=title, description=description, color=color)
    # Placeholder icon URL, replace if Wheatley has one
    # embed.set_footer(text="Wheatley", icon_url="https://example.com/wheatley_icon.png") # Updated text
    embed.set_footer(text="Wheatley") # Updated text
    return embed

# --- Helper Function for Stats Embeds ---
def format_stats_embeds(stats: Dict[str, Any]) -> List[discord.Embed]:
    """Formats the collected stats into multiple embeds."""
    embeds = []
    main_embed = create_wheatley_embed("Wheatley Internal Stats", color=discord.Color.green()) # Use new helper, updated title
    ts_format = "<t:{ts}:R>" # Relative timestamp

    # Runtime Stats (Simplified for Wheatley)
    runtime = stats.get("runtime", {})
    main_embed.add_field(name="Background Task", value="Running" if runtime.get('background_task_running') else "Stopped", inline=True)
    main_embed.add_field(name="Needs JSON Reminder", value=str(runtime.get('needs_json_reminder', 'N/A')), inline=True)
    # Removed Mood, Evolution
    main_embed.add_field(name="Active Topics Channels", value=str(runtime.get('active_topics_channels', 'N/A')), inline=True)
    main_embed.add_field(name="Conv History Channels", value=str(runtime.get('conversation_history_channels', 'N/A')), inline=True)
    main_embed.add_field(name="Thread History Threads", value=str(runtime.get('thread_history_threads', 'N/A')), inline=True)
    main_embed.add_field(name="User Relationships Pairs", value=str(runtime.get('user_relationships_pairs', 'N/A')), inline=True)
    main_embed.add_field(name="Cached Summaries", value=str(runtime.get('conversation_summaries_cached', 'N/A')), inline=True)
    main_embed.add_field(name="Cached Channel Topics", value=str(runtime.get('channel_topics_cached', 'N/A')), inline=True)
    main_embed.add_field(name="Global Msg Cache", value=str(runtime.get('message_cache_global_count', 'N/A')), inline=True)
    main_embed.add_field(name="Mention Msg Cache", value=str(runtime.get('message_cache_mentioned_count', 'N/A')), inline=True)
    main_embed.add_field(name="Active Convos", value=str(runtime.get('active_conversations_count', 'N/A')), inline=True)
    main_embed.add_field(name="Sentiment Channels", value=str(runtime.get('conversation_sentiment_channels', 'N/A')), inline=True)
    # Removed Gurt Participation Topics
    main_embed.add_field(name="Tracked Reactions", value=str(runtime.get('wheatley_message_reactions_tracked', 'N/A')), inline=True) # Renamed stat key
    embeds.append(main_embed)

    # Memory Stats (Simplified)
    memory_embed = create_wheatley_embed("Wheatley Memory Stats", color=discord.Color.orange()) # Use new helper, updated title
    memory = stats.get("memory", {})
    if memory.get("error"):
        memory_embed.description = f"⚠️ Error retrieving memory stats: {memory['error']}"
    else:
        memory_embed.add_field(name="User Facts", value=str(memory.get('user_facts_count', 'N/A')), inline=True)
        memory_embed.add_field(name="General Facts", value=str(memory.get('general_facts_count', 'N/A')), inline=True)
        memory_embed.add_field(name="Chroma Messages", value=str(memory.get('chromadb_message_collection_count', 'N/A')), inline=True)
        memory_embed.add_field(name="Chroma Facts", value=str(memory.get('chromadb_fact_collection_count', 'N/A')), inline=True)
        # Removed Personality Traits, Interests
    embeds.append(memory_embed)

    # API Stats
    api_stats = stats.get("api_stats", {})
    if api_stats:
        api_embed = create_wheatley_embed("Wheatley API Stats", color=discord.Color.red()) # Use new helper, updated title
        for model, data in api_stats.items():
            avg_time = data.get('average_time_ms', 0)
            value = (f"✅ Success: {data.get('success', 0)}\n"
                     f"❌ Failure: {data.get('failure', 0)}\n"
                     f"🔁 Retries: {data.get('retries', 0)}\n"
                     f"⏱️ Avg Time: {avg_time} ms\n"
                     f"📊 Count: {data.get('count', 0)}")
            api_embed.add_field(name=f"Model: `{model}`", value=value, inline=True)
        embeds.append(api_embed)

    # Tool Stats
    tool_stats = stats.get("tool_stats", {})
    if tool_stats:
        tool_embed = create_wheatley_embed("Wheatley Tool Stats", color=discord.Color.purple()) # Use new helper, updated title
        for tool, data in tool_stats.items():
            avg_time = data.get('average_time_ms', 0)
            value = (f"✅ Success: {data.get('success', 0)}\n"
                     f"❌ Failure: {data.get('failure', 0)}\n"
                     f"⏱️ Avg Time: {avg_time} ms\n"
                     f"📊 Count: {data.get('count', 0)}")
            tool_embed.add_field(name=f"Tool: `{tool}`", value=value, inline=True)
        embeds.append(tool_embed)

    # Config Stats (Simplified)
    config_embed = create_wheatley_embed("Wheatley Config Overview", color=discord.Color.greyple()) # Use new helper, updated title
    config = stats.get("config", {})
    config_embed.add_field(name="Default Model", value=f"`{config.get('default_model', 'N/A')}`", inline=True)
    config_embed.add_field(name="Fallback Model", value=f"`{config.get('fallback_model', 'N/A')}`", inline=True)
    config_embed.add_field(name="Semantic Model", value=f"`{config.get('semantic_model_name', 'N/A')}`", inline=True)
    config_embed.add_field(name="Max User Facts", value=str(config.get('max_user_facts', 'N/A')), inline=True)
    config_embed.add_field(name="Max General Facts", value=str(config.get('max_general_facts', 'N/A')), inline=True)
    config_embed.add_field(name="Context Window", value=str(config.get('context_window_size', 'N/A')), inline=True)
    config_embed.add_field(name="Tavily Key Set", value=str(config.get('tavily_api_key_set', 'N/A')), inline=True)
    config_embed.add_field(name="Piston URL Set", value=str(config.get('piston_api_url_set', 'N/A')), inline=True)
    embeds.append(config_embed)

    # Limit to 10 embeds max for Discord API
    return embeds[:10]

# --- Command Setup Function ---
# This function will be called from WheatleyCog's setup method
def setup_commands(cog: 'WheatleyCog'): # Updated type hint
    """Adds Wheatley-specific commands to the cog.""" # Updated docstring

    # Create a list to store command functions for proper registration
    command_functions = []

    # --- Gurt Mood Command --- REMOVED

    # --- Wheatley Memory Command ---
    @cog.bot.tree.command(name="wheatleymemory", description="Interact with Wheatley's memory (what little there is).") # Renamed, updated description
    @app_commands.describe(
        action="Choose an action: add_user, add_general, get_user, get_general",
        user="The user for user-specific actions (mention or ID).",
        fact="The fact to add (for add actions).",
        query="A keyword to search for (for get_general)."
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add User Fact", value="add_user"),
        app_commands.Choice(name="Add General Fact", value="add_general"),
        app_commands.Choice(name="Get User Facts", value="get_user"),
        app_commands.Choice(name="Get General Facts", value="get_general"),
    ])
    async def wheatleymemory(interaction: discord.Interaction, action: app_commands.Choice[str], user: Optional[discord.User] = None, fact: Optional[str] = None, query: Optional[str] = None): # Renamed function
        """Handles the /wheatleymemory command.""" # Updated docstring
        await interaction.response.defer(ephemeral=True) # Defer for potentially slow DB operations

        target_user_id = str(user.id) if user else None
        action_value = action.value

        # Check if user is the bot owner for modification actions
        if (action_value in ["add_user", "add_general"]) and interaction.user.id != cog.bot.owner_id:
            await interaction.followup.send("⛔ Oi! Only the boss can fiddle with my memory banks!", ephemeral=True) # Updated text
            return

        if action_value == "add_user":
            if not target_user_id or not fact:
                await interaction.followup.send("Need a user *and* a fact, mate. Can't remember nothing about nobody.", ephemeral=True) # Updated text
                return
            result = await cog.memory_manager.add_user_fact(target_user_id, fact)
            await interaction.followup.send(f"Add User Fact Result: `{json.dumps(result)}` (Probably worked? Maybe?)", ephemeral=True) # Updated text

        elif action_value == "add_general":
            if not fact:
                await interaction.followup.send("What's the fact then? Can't remember thin air!", ephemeral=True) # Updated text
                return
            result = await cog.memory_manager.add_general_fact(fact)
            await interaction.followup.send(f"Add General Fact Result: `{json.dumps(result)}` (Filed under 'Important Stuff I'll Forget Later')", ephemeral=True) # Updated text

        elif action_value == "get_user":
            if not target_user_id:
                await interaction.followup.send("Which user? Need an ID, chap!", ephemeral=True) # Updated text
                return
            facts = await cog.memory_manager.get_user_facts(target_user_id) # Get newest by default
            if facts:
                facts_str = "\n- ".join(facts)
                await interaction.followup.send(f"**Stuff I Remember About {user.display_name}:**\n- {facts_str}", ephemeral=True) # Updated text
            else:
                await interaction.followup.send(f"My mind's a blank slate about {user.display_name}. Nothing stored!", ephemeral=True) # Updated text

        elif action_value == "get_general":
            facts = await cog.memory_manager.get_general_facts(query=query, limit=10) # Get newest/filtered
            if facts:
                facts_str = "\n- ".join(facts)
                # Conditionally construct the title to avoid nested f-string issues
                if query:
                    title = f"**General Stuff Matching \"{query}\":**" # Updated text
                else:
                    title = "**General Stuff I Might Know:**" # Updated text
                await interaction.followup.send(f"{title}\n- {facts_str}", ephemeral=True)
            else:
                # Conditionally construct the message for the same reason
                if query:
                    message = f"Couldn't find any general facts matching \"{query}\". Probably wasn't important." # Updated text
                else:
                    message = "No general facts found. My memory's not what it used to be. Or maybe it is. Hard to tell." # Updated text
                await interaction.followup.send(message, ephemeral=True)

        else:
            await interaction.followup.send("Invalid action specified. What are you trying to do?", ephemeral=True) # Updated text

    command_functions.append(wheatleymemory) # Add renamed function

    # --- Wheatley Stats Command ---
    @cog.bot.tree.command(name="wheatleystats", description="Display Wheatley's internal statistics. (Owner only)") # Renamed, updated description
    async def wheatleystats(interaction: discord.Interaction): # Renamed function
        """Handles the /wheatleystats command.""" # Updated docstring
        # Owner check
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Sorry mate, classified information! Top secret! Or maybe I just forgot where I put it.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True) # Defer as stats collection might take time
        try:
            stats_data = await cog.get_wheatley_stats() # Renamed cog method call
            embeds = format_stats_embeds(stats_data)
            await interaction.followup.send(embeds=embeds, ephemeral=True)
        except Exception as e:
            print(f"Error in /wheatleystats command: {e}") # Updated command name
            import traceback
            traceback.print_exc()
            await interaction.followup.send("An error occurred while fetching Wheatley's stats. Probably my fault.", ephemeral=True) # Updated text

    command_functions.append(wheatleystats) # Add renamed function

    # --- Sync Wheatley Commands (Owner Only) ---
    @cog.bot.tree.command(name="wheatleysync", description="Sync Wheatley commands with Discord (Owner only)") # Renamed, updated description
    async def wheatleysync(interaction: discord.Interaction): # Renamed function
        """Handles the /wheatleysync command to force sync commands.""" # Updated docstring
        # Check if user is the bot owner
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only the boss can push the big red sync button!", ephemeral=True) # Updated text
            return

        await interaction.response.defer(ephemeral=True)
        try:
            # Sync commands
            synced = await cog.bot.tree.sync()

            # Get list of commands after sync
            commands_after = []
            for cmd in cog.bot.tree.get_commands():
                if cmd.name.startswith("wheatley"): # Check for new prefix
                    commands_after.append(cmd.name)

            await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands!\nWheatley commands: {', '.join(commands_after)}", ephemeral=True) # Updated text
        except Exception as e:
            print(f"Error in /wheatleysync command: {e}") # Updated command name
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error syncing commands: {str(e)} (Did I break it again?)", ephemeral=True) # Updated text

    command_functions.append(wheatleysync) # Add renamed function

    # --- Wheatley Forget Command ---
    @cog.bot.tree.command(name="wheatleyforget", description="Make Wheatley forget a specific fact (if he can).") # Renamed, updated description
    @app_commands.describe(
        scope="Choose the scope: user (for facts about a specific user) or general.",
        fact="The exact fact text Wheatley should forget.",
        user="The user to forget a fact about (only if scope is 'user')."
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="User Fact", value="user"),
        app_commands.Choice(name="General Fact", value="general"),
    ])
    async def wheatleyforget(interaction: discord.Interaction, scope: app_commands.Choice[str], fact: str, user: Optional[discord.User] = None): # Renamed function
        """Handles the /wheatleyforget command.""" # Updated docstring
        await interaction.response.defer(ephemeral=True)

        scope_value = scope.value
        target_user_id = str(user.id) if user else None

        # Permissions Check: Allow users to forget facts about themselves, owner can forget anything.
        can_forget = False
        if scope_value == "user":
            if target_user_id == str(interaction.user.id): # User forgetting their own fact
                can_forget = True
            elif interaction.user.id == cog.bot.owner_id: # Owner forgetting any user fact
                can_forget = True
            elif not target_user_id:
                 await interaction.followup.send("❌ Please specify a user when forgetting a user fact.", ephemeral=True)
                 return
        elif scope_value == "general":
            if interaction.user.id == cog.bot.owner_id: # Only owner can forget general facts
                can_forget = True

        if not can_forget:
            await interaction.followup.send("⛔ You don't have permission to make me forget things! Only I can forget things on my own!", ephemeral=True) # Updated text
            return

        if not fact:
            await interaction.followup.send("❌ Forget what exactly? Need the fact text!", ephemeral=True) # Updated text
            return

        result = None
        if scope_value == "user":
            if not target_user_id: # Should be caught above, but double-check
                 await interaction.followup.send("❌ User is required for scope 'user'.", ephemeral=True)
                 return
            result = await cog.memory_manager.delete_user_fact(target_user_id, fact)
            if result.get("status") == "deleted":
                await interaction.followup.send(f"✅ Okay, okay! Forgotten the fact '{fact}' about {user.display_name}. Probably.", ephemeral=True) # Updated text
            elif result.get("status") == "not_found":
                await interaction.followup.send(f"❓ Couldn't find that fact ('{fact}') for {user.display_name}. Maybe I already forgot?", ephemeral=True) # Updated text
            else:
                await interaction.followup.send(f"⚠️ Error forgetting user fact: {result.get('error', 'Something went wrong... surprise!')}", ephemeral=True) # Updated text

        elif scope_value == "general":
            result = await cog.memory_manager.delete_general_fact(fact)
            if result.get("status") == "deleted":
                await interaction.followup.send(f"✅ Right! Forgotten the general fact: '{fact}'. Gone!", ephemeral=True) # Updated text
            elif result.get("status") == "not_found":
                await interaction.followup.send(f"❓ Couldn't find that general fact: '{fact}'. Was it important?", ephemeral=True) # Updated text
            else:
                await interaction.followup.send(f"⚠️ Error forgetting general fact: {result.get('error', 'Whoops!')}", ephemeral=True) # Updated text

    command_functions.append(wheatleyforget) # Add renamed function

    # --- Gurt Goal Command Group --- REMOVED

    # Get command names safely
    command_names = []
    for func in command_functions:
        # For app commands, use the name attribute directly
        if hasattr(func, "name"):
            command_names.append(func.name)
        # For regular functions, use __name__
        elif hasattr(func, "__name__"):
             command_names.append(func.__name__)
        else:
            command_names.append(str(func))

    print(f"Wheatley commands setup in cog: {command_names}") # Updated text

    # Return the command functions for proper registration
    return command_functions
