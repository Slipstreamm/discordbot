import discord
from discord import app_commands # Import app_commands
from discord.ext import commands
import random
import os
import time # Import time for timestamps
import json # Import json for formatting
import datetime # Import datetime for formatting
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple # Add more types

# Relative imports (assuming API functions are in api.py)
# We need access to the cog instance for state and methods like get_ai_response
# These commands will likely be added to the GurtCog instance dynamically in cog.py's setup

if TYPE_CHECKING:
    from .cog import GurtCog # For type hinting
    from .config import MOOD_OPTIONS # Import for choices

# --- Helper Function for Embeds ---
def create_gurt_embed(title: str, description: str = "", color=discord.Color.blue()) -> discord.Embed:
    """Creates a standard Gurt-themed embed."""
    embed = discord.Embed(title=title, description=description, color=color)
    # Placeholder icon URL, replace if Gurt has one
    # embed.set_footer(text="Gurt", icon_url="https://example.com/gurt_icon.png")
    embed.set_footer(text="Gurt")
    return embed

# --- Helper Function for Stats Embeds ---
def format_stats_embeds(stats: Dict[str, Any]) -> List[discord.Embed]:
    """Formats the collected stats into multiple embeds."""
    embeds = []
    main_embed = create_gurt_embed("Gurt Internal Stats", color=discord.Color.green())
    ts_format = "<t:{ts}:R>" # Relative timestamp

    # Runtime Stats
    runtime = stats.get("runtime", {})
    main_embed.add_field(name="Current Mood", value=f"{runtime.get('current_mood', 'N/A')} (Changed {ts_format.format(ts=int(runtime.get('last_mood_change_timestamp', 0)))})", inline=False)
    main_embed.add_field(name="Background Task", value="Running" if runtime.get('background_task_running') else "Stopped", inline=True)
    main_embed.add_field(name="Needs JSON Reminder", value=str(runtime.get('needs_json_reminder', 'N/A')), inline=True)
    main_embed.add_field(name="Last Evolution", value=ts_format.format(ts=int(runtime.get('last_evolution_update_timestamp', 0))), inline=True)
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
    main_embed.add_field(name="Gurt Participation Topics", value=str(runtime.get('gurt_participation_topics_count', 'N/A')), inline=True)
    main_embed.add_field(name="Tracked Reactions", value=str(runtime.get('gurt_message_reactions_tracked', 'N/A')), inline=True)
    embeds.append(main_embed)

    # Memory Stats
    memory_embed = create_gurt_embed("Gurt Memory Stats", color=discord.Color.orange())
    memory = stats.get("memory", {})
    if memory.get("error"):
        memory_embed.description = f"⚠️ Error retrieving memory stats: {memory['error']}"
    else:
        memory_embed.add_field(name="User Facts", value=str(memory.get('user_facts_count', 'N/A')), inline=True)
        memory_embed.add_field(name="General Facts", value=str(memory.get('general_facts_count', 'N/A')), inline=True)
        memory_embed.add_field(name="Chroma Messages", value=str(memory.get('chromadb_message_collection_count', 'N/A')), inline=True)
        memory_embed.add_field(name="Chroma Facts", value=str(memory.get('chromadb_fact_collection_count', 'N/A')), inline=True)

        personality = memory.get("personality_traits", {})
        if personality:
            p_items = [f"`{k}`: {v}" for k, v in personality.items()]
            memory_embed.add_field(name="Personality Traits", value="\n".join(p_items) if p_items else "None", inline=False)

        interests = memory.get("top_interests", [])
        if interests:
            i_items = [f"`{t}`: {l:.2f}" for t, l in interests]
            memory_embed.add_field(name="Top Interests", value="\n".join(i_items) if i_items else "None", inline=False)
    embeds.append(memory_embed)

    # API Stats
    api_stats = stats.get("api_stats", {})
    if api_stats:
        api_embed = create_gurt_embed("Gurt API Stats", color=discord.Color.red())
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
        tool_embed = create_gurt_embed("Gurt Tool Stats", color=discord.Color.purple())
        for tool, data in tool_stats.items():
            avg_time = data.get('average_time_ms', 0)
            value = (f"✅ Success: {data.get('success', 0)}\n"
                     f"❌ Failure: {data.get('failure', 0)}\n"
                     f"⏱️ Avg Time: {avg_time} ms\n"
                     f"📊 Count: {data.get('count', 0)}")
            tool_embed.add_field(name=f"Tool: `{tool}`", value=value, inline=True)
        embeds.append(tool_embed)

    # Config Stats (Less critical, maybe separate embed if needed)
    config_embed = create_gurt_embed("Gurt Config Overview", color=discord.Color.greyple())
    config = stats.get("config", {})
    config_embed.add_field(name="Default Model", value=f"`{config.get('default_model', 'N/A')}`", inline=True)
    config_embed.add_field(name="Fallback Model", value=f"`{config.get('fallback_model', 'N/A')}`", inline=True)
    config_embed.add_field(name="Semantic Model", value=f"`{config.get('semantic_model_name', 'N/A')}`", inline=True)
    config_embed.add_field(name="Max User Facts", value=str(config.get('max_user_facts', 'N/A')), inline=True)
    config_embed.add_field(name="Max General Facts", value=str(config.get('max_general_facts', 'N/A')), inline=True)
    config_embed.add_field(name="Context Window", value=str(config.get('context_window_size', 'N/A')), inline=True)
    config_embed.add_field(name="API Key Set", value=str(config.get('api_key_set', 'N/A')), inline=True)
    config_embed.add_field(name="Tavily Key Set", value=str(config.get('tavily_api_key_set', 'N/A')), inline=True)
    config_embed.add_field(name="Piston URL Set", value=str(config.get('piston_api_url_set', 'N/A')), inline=True)
    embeds.append(config_embed)


    # Limit to 10 embeds max for Discord API
    return embeds[:10]


# --- Command Setup Function ---
# This function will be called from GurtCog's setup method
def setup_commands(cog: 'GurtCog'):
    """Adds Gurt-specific commands to the cog."""

    # Create a list to store command functions for proper registration
    command_functions = []

    # --- Gurt Mood Command ---
    @cog.bot.tree.command(name="gurtmood", description="Check or set Gurt's current mood.")
    @app_commands.describe(mood="Optional: Set Gurt's mood to one of the available options.")
    @app_commands.choices(mood=[
        app_commands.Choice(name=m, value=m) for m in cog.MOOD_OPTIONS # Use cog's MOOD_OPTIONS
    ])
    async def gurtmood(interaction: discord.Interaction, mood: Optional[app_commands.Choice[str]] = None):
        """Handles the /gurtmood command."""
        # Check if user is the bot owner for mood setting
        if mood and interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only the bot owner can change Gurt's mood.", ephemeral=True)
            return

        if mood:
            cog.current_mood = mood.value
            cog.last_mood_change = time.time()
            await interaction.response.send_message(f"Gurt's mood set to: {mood.value}", ephemeral=True)
        else:
            time_since_change = time.time() - cog.last_mood_change
            await interaction.response.send_message(f"Gurt's current mood is: {cog.current_mood} (Set {int(time_since_change // 60)} minutes ago)", ephemeral=True)

    command_functions.append(gurtmood)

    # --- Gurt Memory Command ---
    @cog.bot.tree.command(name="gurtmemory", description="Interact with Gurt's memory.")
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
    async def gurtmemory(interaction: discord.Interaction, action: app_commands.Choice[str], user: Optional[discord.User] = None, fact: Optional[str] = None, query: Optional[str] = None):
        """Handles the /gurtmemory command."""
        await interaction.response.defer(ephemeral=True) # Defer for potentially slow DB operations

        target_user_id = str(user.id) if user else None
        action_value = action.value

        # Check if user is the bot owner for modification actions
        if (action_value in ["add_user", "add_general"]) and interaction.user.id != cog.bot.owner_id:
            await interaction.followup.send("⛔ Only the bot owner can add facts to Gurt's memory.", ephemeral=True)
            return

        if action_value == "add_user":
            if not target_user_id or not fact:
                await interaction.followup.send("Please provide both a user and a fact to add.", ephemeral=True)
                return
            result = await cog.memory_manager.add_user_fact(target_user_id, fact)
            await interaction.followup.send(f"Add User Fact Result: `{json.dumps(result)}`", ephemeral=True)

        elif action_value == "add_general":
            if not fact:
                await interaction.followup.send("Please provide a fact to add.", ephemeral=True)
                return
            result = await cog.memory_manager.add_general_fact(fact)
            await interaction.followup.send(f"Add General Fact Result: `{json.dumps(result)}`", ephemeral=True)

        elif action_value == "get_user":
            if not target_user_id:
                await interaction.followup.send("Please provide a user to get facts for.", ephemeral=True)
                return
            facts = await cog.memory_manager.get_user_facts(target_user_id) # Get newest by default
            if facts:
                facts_str = "\n- ".join(facts)
                await interaction.followup.send(f"**Facts for {user.display_name}:**\n- {facts_str}", ephemeral=True)
            else:
                await interaction.followup.send(f"No facts found for {user.display_name}.", ephemeral=True)

        elif action_value == "get_general":
            facts = await cog.memory_manager.get_general_facts(query=query, limit=10) # Get newest/filtered
            if facts:
                facts_str = "\n- ".join(facts)
                # Conditionally construct the title to avoid nested f-string issues
                if query:
                    title = f"**General Facts matching \"{query}\":**"
                else:
                    title = "**General Facts:**"
                await interaction.followup.send(f"{title}\n- {facts_str}", ephemeral=True)
            else:
                # Conditionally construct the message for the same reason
                if query:
                    message = f"No general facts found matching \"{query}\"."
                else:
                    message = "No general facts found."
                await interaction.followup.send(message, ephemeral=True)

        else:
            await interaction.followup.send("Invalid action specified.", ephemeral=True)

    command_functions.append(gurtmemory)

    # --- Gurt Stats Command ---
    @cog.bot.tree.command(name="gurtstats", description="Display Gurt's internal statistics. (Owner only)")
    async def gurtstats(interaction: discord.Interaction):
        """Handles the /gurtstats command."""
        # Check if user is the bot owner
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only the bot owner can view detailed stats.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True) # Defer as stats collection might take time
        try:
            stats_data = await cog.get_gurt_stats()
            embeds = format_stats_embeds(stats_data)
            await interaction.followup.send(embeds=embeds, ephemeral=True)
        except Exception as e:
            print(f"Error in /gurtstats command: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send("An error occurred while fetching Gurt's stats.", ephemeral=True)

    command_functions.append(gurtstats)

    # --- Sync Gurt Commands (Owner Only) ---
    @cog.bot.tree.command(name="gurtsync", description="Sync Gurt commands with Discord (Owner only)")
    async def gurtsync(interaction: discord.Interaction):
        """Handles the /gurtsync command to force sync commands."""
        # Check if user is the bot owner
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only the bot owner can sync commands.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            # Sync commands
            synced = await cog.bot.tree.sync()

            # Get list of commands after sync
            commands_after = []
            for cmd in cog.bot.tree.get_commands():
                if cmd.name.startswith("gurt"):
                    commands_after.append(cmd.name)

            await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands!\nGurt commands: {', '.join(commands_after)}", ephemeral=True)
        except Exception as e:
            print(f"Error in /gurtsync command: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error syncing commands: {str(e)}", ephemeral=True)

    command_functions.append(gurtsync)

    print(f"Gurt commands setup in cog: {[func.__name__ for func in command_functions]}")

    # Return the command functions for proper registration
    return command_functions
