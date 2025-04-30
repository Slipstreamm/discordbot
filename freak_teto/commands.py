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
# These commands will likely be added to the FreakTetoCog instance dynamically in cog.py's setup # Updated name

if TYPE_CHECKING:
    from .cog import FreakTetoCog # For type hinting - Updated
    from .config import MOOD_OPTIONS # Import for choices

# --- Helper Function for Embeds ---
def create_freak_teto_embed(title: str, description: str = "", color=discord.Color.magenta()) -> discord.Embed: # Renamed function, changed color
    """Creates a standard Freak Teto-themed embed.""" # Updated docstring
    embed = discord.Embed(title=title, description=description, color=color)
    # Placeholder icon URL, replace if Freak Teto has one
    # embed.set_footer(text="Freak Teto", icon_url="https://example.com/freak_teto_icon.png")
    embed.set_footer(text="Freak Teto") # Updated footer text
    return embed

# --- Helper Function for Stats Embeds ---
def format_stats_embeds(stats: Dict[str, Any]) -> List[discord.Embed]:
    """Formats the collected stats into multiple embeds."""
    embeds = []
    main_embed = create_freak_teto_embed("Freak Teto Internal Stats", color=discord.Color.green()) # Use new helper, updated title
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
    # TODO: Ensure these runtime stats variables are updated if needed in cog.py's get_stats method
    main_embed.add_field(name="Freak Teto Participation Topics", value=str(runtime.get('freak_teto_participation_topics_count', 'N/A')), inline=True) # Updated name
    main_embed.add_field(name="Tracked Reactions", value=str(runtime.get('freak_teto_message_reactions_tracked', 'N/A')), inline=True) # Updated name
    embeds.append(main_embed)

    # Memory Stats
    memory_embed = create_freak_teto_embed("Freak Teto Memory Stats", color=discord.Color.orange()) # Use new helper, updated title
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
        api_embed = create_freak_teto_embed("Freak Teto API Stats", color=discord.Color.red()) # Use new helper, updated title
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
        tool_embed = create_freak_teto_embed("Freak Teto Tool Stats", color=discord.Color.purple()) # Use new helper, updated title
        for tool, data in tool_stats.items():
            avg_time = data.get('average_time_ms', 0)
            value = (f"✅ Success: {data.get('success', 0)}\n"
                     f"❌ Failure: {data.get('failure', 0)}\n"
                     f"⏱️ Avg Time: {avg_time} ms\n"
                     f"📊 Count: {data.get('count', 0)}")
            tool_embed.add_field(name=f"Tool: `{tool}`", value=value, inline=True)
        embeds.append(tool_embed)

    # Config Stats (Less critical, maybe separate embed if needed)
    config_embed = create_freak_teto_embed("Freak Teto Config Overview", color=discord.Color.greyple()) # Use new helper, updated title
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
# This function will be called from FreakTetoCog's setup method
def setup_commands(cog: 'FreakTetoCog'): # Updated type hint
    """Adds Freak Teto-specific commands to the cog.""" # Updated docstring

    # Create a list to store command functions for proper registration
    command_functions = []

    # --- Freak Teto Mood Command ---
    @cog.bot.tree.command(name="freaktetomood", description="Check or set Freak Teto's current mood.") # Renamed command, updated description
    @app_commands.describe(mood="Optional: Set Freak Teto's mood to one of the available options.") # Updated description
    @app_commands.choices(mood=[
        app_commands.Choice(name=m, value=m) for m in cog.MOOD_OPTIONS # Use cog's MOOD_OPTIONS (should be Teto's moods)
    ])
    async def freaktetomood(interaction: discord.Interaction, mood: Optional[app_commands.Choice[str]] = None): # Renamed function
        """Handles the /freaktetomood command.""" # Updated docstring
        # Check if user is the bot owner for mood setting
        if mood and interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can change Freak Teto's mood.", ephemeral=True) # Updated message
            return

        if mood:
            cog.current_mood = mood.value
            cog.last_mood_change = time.time()
            await interaction.response.send_message(f"Freak Teto's mood set to: {mood.value}, Master!", ephemeral=True) # Updated message
        else:
            time_since_change = time.time() - cog.last_mood_change
            await interaction.response.send_message(f"Freak Teto's current mood is: {cog.current_mood} (Set {int(time_since_change // 60)} minutes ago)", ephemeral=True) # Updated message

    command_functions.append(freaktetomood) # Add renamed function

    # --- Freak Teto Memory Command ---
    @cog.bot.tree.command(name="freaktetomemory", description="Interact with Freak Teto's memory.") # Renamed command, updated description
    @app_commands.describe(
        action="Choose an action: add_user, add_general, get_user, get_general",
        user="The user for user-specific actions (mention or ID).",
        fact="The fact to add (for add actions).",
        query="A keyword to search for (for get_general)."
    )
    @app_commands.choices(action=[ # Keep actions, logic relies on MemoryManager which is shared but uses different DB paths
        app_commands.Choice(name="Add User Fact", value="add_user"),
        app_commands.Choice(name="Add General Fact", value="add_general"),
        app_commands.Choice(name="Get User Facts", value="get_user"),
        app_commands.Choice(name="Get General Facts", value="get_general"),
    ])
    async def freaktetomemory(interaction: discord.Interaction, action: app_commands.Choice[str], user: Optional[discord.User] = None, fact: Optional[str] = None, query: Optional[str] = None): # Renamed function
        """Handles the /freaktetomemory command.""" # Updated docstring
        await interaction.response.defer(ephemeral=True) # Defer for potentially slow DB operations

        target_user_id = str(user.id) if user else None
        action_value = action.value

        # Check if user is the bot owner for modification actions
        if (action_value in ["add_user", "add_general"]) and interaction.user.id != cog.bot.owner_id:
            await interaction.followup.send("⛔ Only Master can add facts to Freak Teto's memory.", ephemeral=True) # Updated message
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
                await interaction.followup.send(f"I don't seem to remember anything about {user.display_name}, Master.", ephemeral=True) # Updated message

        elif action_value == "get_general":
            facts = await cog.memory_manager.get_general_facts(query=query, limit=10) # Get newest/filtered
            if facts:
                facts_str = "\n- ".join(facts)
                # Conditionally construct the title
                if query:
                    title = f"**General Facts matching \"{query}\":**"
                else:
                    title = "**General Facts:**"
                await interaction.followup.send(f"{title}\n- {facts_str}", ephemeral=True)
            else:
                # Conditionally construct the message
                if query:
                    message = f"I couldn't find any general facts matching \"{query}\", Master." # Updated message
                else:
                    message = "I don't have any general facts stored right now, Master." # Updated message
                await interaction.followup.send(message, ephemeral=True)

        else:
            await interaction.followup.send("Invalid action specified.", ephemeral=True)

    command_functions.append(freaktetomemory) # Add renamed function

    # --- Freak Teto Stats Command ---
    @cog.bot.tree.command(name="freaktetostats", description="Display Freak Teto's internal statistics. (Owner only)") # Renamed command, updated description
    async def freaktetostats(interaction: discord.Interaction): # Renamed function
        """Handles the /freaktetostats command.""" # Updated docstring
        if interaction.user.id != cog.bot.owner_id: # Added owner check
            await interaction.response.send_message("⛔ Only Master can view my internal stats.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True) # Defer as stats collection might take time
        try:
            stats_data = await cog.get_freak_teto_stats() # Call renamed stats method
            embeds = format_stats_embeds(stats_data) # Use the same formatter, but it uses the renamed embed helper
            await interaction.followup.send(embeds=embeds, ephemeral=True)
        except Exception as e:
            print(f"Error in /freaktetostats command: {e}") # Updated log
            import traceback
            traceback.print_exc()
            await interaction.followup.send("An error occurred while fetching Freak Teto's stats.", ephemeral=True) # Updated message

    command_functions.append(freaktetostats) # Add renamed function

    # --- Sync Freak Teto Commands (Owner Only) ---
    @cog.bot.tree.command(name="freaktetosync", description="Sync Freak Teto commands with Discord (Owner only)") # Renamed command, updated description
    async def freaktetosync(interaction: discord.Interaction): # Renamed function
        """Handles the /freaktetosync command to force sync commands.""" # Updated docstring
        # Check if user is the bot owner
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can sync my commands.", ephemeral=True) # Updated message
            return

        await interaction.response.defer(ephemeral=True)
        try:
            # Sync commands associated with this cog/bot instance
            # Note: Syncing all commands via bot.tree.sync() might be necessary depending on setup
            synced = await cog.bot.tree.sync() # Sync all commands for simplicity

            # Get list of commands after sync, filtering for freak_teto
            commands_after = []
            for cmd in cog.bot.tree.get_commands():
                # Adjust filter if commands aren't prefixed
                if cmd.name.startswith("freakteto"):
                    commands_after.append(cmd.name)

            await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands!\nFreak Teto commands: {', '.join(commands_after)}", ephemeral=True) # Updated message
        except Exception as e:
            print(f"Error in /freaktetosync command: {e}") # Updated log
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error syncing commands: {str(e)}", ephemeral=True)

    command_functions.append(freaktetosync) # Add renamed function

    # --- Freak Teto Forget Command ---
    @cog.bot.tree.command(name="freaktetoforget", description="Make Freak Teto forget a specific fact.") # Renamed command, updated description
    @app_commands.describe(
        scope="Choose the scope: user (for facts about a specific user) or general.",
        fact="The exact fact text Freak Teto should forget.", # Updated description
        user="The user to forget a fact about (only if scope is 'user')."
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="User Fact", value="user"),
        app_commands.Choice(name="General Fact", value="general"),
    ])
    async def freaktetoforget(interaction: discord.Interaction, scope: app_commands.Choice[str], fact: str, user: Optional[discord.User] = None): # Renamed function
        """Handles the /freaktetoforget command.""" # Updated docstring
        await interaction.response.defer(ephemeral=True)

        scope_value = scope.value
        target_user_id = str(user.id) if user else None

        # Permissions Check: Allow users to forget facts about themselves, owner (Master) can forget anything.
        can_forget = False
        if scope_value == "user":
            if target_user_id == str(interaction.user.id): # User forgetting their own fact
                can_forget = True
            elif interaction.user.id == cog.bot.owner_id: # Owner forgetting any user fact
                can_forget = True
            elif not target_user_id:
                 await interaction.followup.send("❌ Please specify a user when forgetting a user fact, Master.", ephemeral=True) # Updated message
                 return
        elif scope_value == "general":
            if interaction.user.id == cog.bot.owner_id: # Only owner can forget general facts
                can_forget = True

        if not can_forget:
            await interaction.followup.send("⛔ You don't have permission to make me forget this fact, Master.", ephemeral=True) # Updated message
            return

        if not fact:
            await interaction.followup.send("❌ Please provide the exact fact text for me to forget, Master.", ephemeral=True) # Updated message
            return

        result = None
        if scope_value == "user":
            if not target_user_id: # Should be caught above, but double-check
                 await interaction.followup.send("❌ User is required for scope 'user'.", ephemeral=True)
                 return
            result = await cog.memory_manager.delete_user_fact(target_user_id, fact)
            if result.get("status") == "deleted":
                await interaction.followup.send(f"✅ Understood, Master. I've forgotten the fact '{fact}' about {user.display_name}.", ephemeral=True) # Updated message
            elif result.get("status") == "not_found":
                await interaction.followup.send(f"❓ I couldn't find that exact fact ('{fact}') stored for {user.display_name}, Master.", ephemeral=True) # Updated message
            else:
                await interaction.followup.send(f"⚠️ Error forgetting user fact: {result.get('error', 'Unknown error')}", ephemeral=True)

        elif scope_value == "general":
            result = await cog.memory_manager.delete_general_fact(fact)
            if result.get("status") == "deleted":
                await interaction.followup.send(f"✅ Understood, Master. I've forgotten the general fact: '{fact}'.", ephemeral=True) # Updated message
            elif result.get("status") == "not_found":
                await interaction.followup.send(f"❓ I couldn't find that exact general fact: '{fact}', Master.", ephemeral=True) # Updated message
            else:
                await interaction.followup.send(f"⚠️ Error forgetting general fact: {result.get('error', 'Unknown error')}", ephemeral=True)

    command_functions.append(freaktetoforget) # Add renamed function

    # --- Freak Teto Force Autonomous Action Command (Owner Only) ---
    @cog.bot.tree.command(name="freaktetoforceauto", description="Force Freak Teto to execute an autonomous action immediately. (Owner only)") # Renamed command, updated description
    async def freaktetoforceauto(interaction: discord.Interaction): # Renamed function
        """Handles the /freaktetoforceauto command.""" # Updated docstring
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can force my autonomous actions.", ephemeral=True) # Updated message
            return
        await interaction.response.defer(ephemeral=True)
        try:
            result = await cog.force_autonomous_action() # Assumes cog method is generic or refactored
            summary = (
                f"**Autonomous Action Forced (Freak Teto):**\n" # Updated title
                f"**Tool:** {result.get('tool')}\n"
                f"**Args:** `{result.get('args')}`\n"
                f"**Reasoning:** {result.get('reasoning')}\n"
                f"**Result:** {result.get('result')}"
            )
            await interaction.followup.send(summary, ephemeral=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error forcing autonomous action: {e}", ephemeral=True)

    command_functions.append(freaktetoforceauto) # Add renamed function

    # --- Freak Teto Clear Action History Command (Owner Only) ---
    @cog.bot.tree.command(name="freaktetoclearhistory", description="Clear Freak Teto's internal autonomous action history. (Owner only)") # Renamed command, updated description
    async def freaktetoclearhistory(interaction: discord.Interaction): # Renamed function
        """Handles the /freaktetoclearhistory command.""" # Updated docstring
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can clear my action history.", ephemeral=True) # Updated message
            return
        await interaction.response.defer(ephemeral=True)
        try:
            result = await cog.memory_manager.clear_internal_action_logs() # Assumes MemoryManager method is generic
            if "error" in result:
                await interaction.followup.send(f"⚠️ Error clearing action history: {result['error']}", ephemeral=True)
            else:
                await interaction.followup.send("✅ Freak Teto's autonomous action history has been cleared, Master.", ephemeral=True) # Updated message
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ An unexpected error occurred while clearing history: {e}", ephemeral=True)

    command_functions.append(freaktetoclearhistory) # Add renamed function

    # --- Freak Teto Goal Command Group ---
    freaktetogoal_group = app_commands.Group(name="freaktetogoal", description="Manage Freak Teto's long-term goals (Owner only)") # Renamed group variable and updated name/description

    @freaktetogoal_group.command(name="add", description="Add a new goal for Freak Teto.") # Updated description
    @app_commands.describe(
        description="The description of the goal.",
        priority="Priority (1=highest, 10=lowest, default=5).",
        details_json="Optional JSON string for goal details (e.g., sub-tasks)."
    )
    async def freaktetogoal_add(interaction: discord.Interaction, description: str, priority: Optional[int] = 5, details_json: Optional[str] = None): # Renamed function
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can add goals for me.", ephemeral=True) # Updated message
            return
        await interaction.response.defer(ephemeral=True)
        details = None
        if details_json:
            try:
                details = json.loads(details_json)
            except json.JSONDecodeError:
                await interaction.followup.send("❌ Invalid JSON format for details.", ephemeral=True)
                return

        # Capture context from interaction
        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        channel_id = str(interaction.channel_id) if interaction.channel_id else None
        user_id = str(interaction.user.id) if interaction.user else None

        result = await cog.memory_manager.add_goal(
            description,
            priority,
            details,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id
        )
        if result.get("status") == "added":
            await interaction.followup.send(f"✅ Goal added for Freak Teto (ID: {result.get('goal_id')}): '{description}'", ephemeral=True) # Updated message
        elif result.get("status") == "duplicate":
             await interaction.followup.send(f"⚠️ Goal '{description}' already exists for me (ID: {result.get('goal_id')}).", ephemeral=True) # Updated message
        else:
            await interaction.followup.send(f"⚠️ Error adding goal: {result.get('error', 'Unknown error')}", ephemeral=True)

    @freaktetogoal_group.command(name="list", description="List Freak Teto's current goals.") # Updated description
    @app_commands.describe(status="Filter goals by status (e.g., pending, active).", limit="Maximum goals to show (default 10).")
    @app_commands.choices(status=[
        app_commands.Choice(name="Pending", value="pending"),
        app_commands.Choice(name="Active", value="active"),
        app_commands.Choice(name="Completed", value="completed"),
        app_commands.Choice(name="Failed", value="failed"),
    ])
    async def freaktetogoal_list(interaction: discord.Interaction, status: Optional[app_commands.Choice[str]] = None, limit: Optional[int] = 10): # Renamed function
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can list my goals.", ephemeral=True) # Updated message
            return
        await interaction.response.defer(ephemeral=True)
        status_value = status.value if status else None
        limit_value = max(1, min(limit or 10, 25)) # Clamp limit
        goals = await cog.memory_manager.get_goals(status=status_value, limit=limit_value)
        if not goals:
            await interaction.followup.send(f"I have no goals found matching the criteria (Status: {status_value or 'any'}), Master.", ephemeral=True) # Updated message
            return

        embed = create_freak_teto_embed(f"Freak Teto Goals (Status: {status_value or 'All'})", color=discord.Color.purple()) # Use new helper, updated title
        for goal in goals:
            details_str = f"\n   Details: `{json.dumps(goal.get('details'))}`" if goal.get('details') else ""
            created_ts = int(goal.get('created_timestamp', 0))
            updated_ts = int(goal.get('last_updated', 0))
            embed.add_field(
                name=f"ID: {goal.get('goal_id')} | P: {goal.get('priority', '?')} | Status: {goal.get('status', '?')}",
                value=f"> {goal.get('description', 'N/A')}{details_str}\n"
                      f"> Created: <t:{created_ts}:R> | Updated: <t:{updated_ts}:R>",
                inline=False
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @freaktetogoal_group.command(name="update", description="Update a goal's status, priority, or details.") # Use renamed group variable
    @app_commands.describe(
        goal_id="The ID of the goal to update.",
        status="New status for the goal.",
        priority="New priority (1=highest, 10=lowest).",
        details_json="Optional: New JSON string for goal details (replaces existing)."
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="Pending", value="pending"),
        app_commands.Choice(name="Active", value="active"),
        app_commands.Choice(name="Completed", value="completed"),
        app_commands.Choice(name="Failed", value="failed"),
    ])
    async def freaktetogoal_update(interaction: discord.Interaction, goal_id: int, status: Optional[app_commands.Choice[str]] = None, priority: Optional[int] = None, details_json: Optional[str] = None): # Renamed function
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can update my goals.", ephemeral=True) # Updated message
            return
        await interaction.response.defer(ephemeral=True)

        status_value = status.value if status else None
        details = None
        if details_json:
            try:
                details = json.loads(details_json)
            except json.JSONDecodeError:
                await interaction.followup.send("❌ Invalid JSON format for details.", ephemeral=True)
                return

        if not any([status_value, priority is not None, details is not None]):
             await interaction.followup.send("❌ You must provide at least one field to update (status, priority, or details_json).", ephemeral=True)
             return

        result = await cog.memory_manager.update_goal(goal_id, status=status_value, priority=priority, details=details)
        if result.get("status") == "updated":
            await interaction.followup.send(f"✅ Goal ID {goal_id} updated.", ephemeral=True)
        elif result.get("status") == "not_found":
            await interaction.followup.send(f"❓ Goal ID {goal_id} not found, Master.", ephemeral=True) # Updated message
        else:
            await interaction.followup.send(f"⚠️ Error updating goal: {result.get('error', 'Unknown error')}", ephemeral=True)

    @freaktetogoal_group.command(name="delete", description="Delete a goal.") # Use renamed group variable
    @app_commands.describe(goal_id="The ID of the goal to delete.")
    async def freaktetogoal_delete(interaction: discord.Interaction, goal_id: int): # Renamed function
        if interaction.user.id != cog.bot.owner_id:
            await interaction.response.send_message("⛔ Only Master can delete my goals.", ephemeral=True) # Updated message
            return
        await interaction.response.defer(ephemeral=True)
        result = await cog.memory_manager.delete_goal(goal_id)
        if result.get("status") == "deleted":
            await interaction.followup.send(f"✅ Goal ID {goal_id} deleted, Master.", ephemeral=True) # Updated message
        elif result.get("status") == "not_found":
            await interaction.followup.send(f"❓ Goal ID {goal_id} not found, Master.", ephemeral=True) # Updated message
        else:
            await interaction.followup.send(f"⚠️ Error deleting goal: {result.get('error', 'Unknown error')}", ephemeral=True)

    # Add the command group to the bot's tree
    cog.bot.tree.add_command(freaktetogoal_group) # Use renamed group variable
    # Add group command functions to the list for tracking (optional, but good practice)
    command_functions.extend([freaktetogoal_add, freaktetogoal_list, freaktetogoal_update, freaktetogoal_delete]) # Use renamed functions


    # Get command names safely - Command objects don't have __name__ attribute
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

    print(f"Freak Teto commands setup in cog: {command_names}") # Updated log

    # Return the command functions for proper registration
    return command_functions
