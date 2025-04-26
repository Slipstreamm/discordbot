import discord
from discord.ext import commands, tasks
import asyncio
import random
import os
import json
import aiohttp
import requests # For bio update
import base64
import time
from typing import Optional, Dict, Any, List

# Assuming GurtCog is in the same directory level or accessible
# from .gurt_cog import GurtCog # This might cause circular import issues if GurtCog imports this.
# It's safer to get the cog instance via self.bot.get_cog('GurtCog')

class ProfileUpdaterCog(commands.Cog):
    """Cog for automatically updating Gurt's profile elements based on AI decisions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.gurt_cog: Optional[commands.Cog] = None # To store GurtCog instance
        self.bot_token = os.getenv("DISCORD_TOKEN_GURT") # Need the bot token for bio updates
        self.update_interval_hours = 3 # Default to every 3 hours, can be adjusted
        self.profile_update_task.change_interval(hours=self.update_interval_hours)
        self.last_update_time = 0 # Track last update time

    async def cog_load(self):
        """Initialize resources when the cog is loaded."""
        self.session = aiohttp.ClientSession()
        # Removed wait_until_ready and gurt_cog retrieval from here
        if not self.bot_token:
             print("WARNING: DISCORD_TOKEN_GURT environment variable not set. Bio updates will fail.")
        print(f"ProfileUpdaterCog loaded. Update interval: {self.update_interval_hours} hours.")
        self.profile_update_task.start()

    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        self.profile_update_task.cancel()
        if self.session:
            await self.session.close()
        print("ProfileUpdaterCog unloaded.")

    @tasks.loop(hours=3) # Default interval, adjusted in __init__
    async def profile_update_task(self):
        """Periodically considers and potentially updates Gurt's profile."""
        if not self.gurt_cog or not self.bot.is_ready():
            print("ProfileUpdaterTask: GurtCog not available or bot not ready. Skipping cycle.")
            return

        # Call the reusable update cycle logic
        await self.perform_update_cycle()

    @profile_update_task.before_loop
    async def before_profile_update_task(self):
        """Wait until the bot is ready and get GurtCog before starting the loop."""
        await self.bot.wait_until_ready()
        print("ProfileUpdaterTask: Bot ready, attempting to get GurtCog...")
        self.gurt_cog = self.bot.get_cog('GurtCog')
        if not self.gurt_cog:
            print("ERROR: ProfileUpdaterTask could not find GurtCog after bot is ready. AI features will not work.")
        else:
            print("ProfileUpdaterTask: GurtCog found. Starting loop.")

    async def perform_update_cycle(self):
        """Performs a single profile update check and potential update."""
        if not self.gurt_cog or not self.bot.is_ready():
            print("ProfileUpdaterTask: GurtCog not available or bot not ready. Skipping cycle.")
            return

        print(f"ProfileUpdaterTask: Starting update cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.last_update_time = time.time()

        try:
            # --- 1. Fetch Current State ---
            current_state = await self._get_current_profile_state()
            if not current_state:
                print("ProfileUpdaterTask: Failed to get current profile state. Skipping cycle.")
                return

            # --- 2. AI Decision Step ---
            decision = await self._ask_ai_for_updates(current_state)
            if not decision or not decision.get("should_update"):
                print("ProfileUpdaterTask: AI decided not to update profile this cycle.")
                return

            # --- 3. Conditional Execution ---
            updates_to_perform = decision.get("updates", {})
            print(f"ProfileUpdaterTask: AI requested updates: {updates_to_perform}")

            # All fields are required in the schema, but they might be null
            # Only call the update methods if the value is not None
            avatar_query = updates_to_perform.get("avatar_query")
            if avatar_query is not None:
                await self._update_avatar(avatar_query)

            new_bio = updates_to_perform.get("new_bio")
            if new_bio is not None:
                await self._update_bio(new_bio)

            role_theme = updates_to_perform.get("role_theme")
            if role_theme is not None:
                await self._update_roles(role_theme)

            # new_activity is always an object with type and text fields
            # The _update_activity method handles the case where both are null
            new_activity = updates_to_perform.get("new_activity")
            if new_activity is not None:
                await self._update_activity(new_activity)

            print("ProfileUpdaterTask: Update cycle finished.")

        except Exception as e:
            print(f"ERROR in perform_update_cycle: {e}")
            import traceback
            traceback.print_exc()

    async def _get_current_profile_state(self) -> Optional[Dict[str, Any]]:
        """Fetches the bot's current profile state."""
        if not self.bot.user:
            return None

        state = {
            "avatar_url": None,
            "avatar_image_data": None, # Base64 encoded image data
            "bio": None,
            "roles": {}, # guild_id: [role_names]
            "activity": None # {"type": str, "text": str}
        }

        # Avatar
        if self.bot.user.avatar:
            state["avatar_url"] = self.bot.user.avatar.url
            try:
                # Download avatar image data for AI analysis
                async with self.session.get(state["avatar_url"]) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
                        mime_type = resp.content_type or 'image/png' # Default mime type
                        state["avatar_image_data"] = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
                        print("ProfileUpdaterTask: Fetched current avatar image data.")
                    else:
                        print(f"ProfileUpdaterTask: Failed to download current avatar image (status: {resp.status}).")
            except Exception as e:
                print(f"ProfileUpdaterTask: Error downloading avatar image: {e}")

        # Bio (Requires authenticated API call)
        if self.bot_token:
            headers = {
                'Authorization': f'Bot {self.bot_token}',
                'User-Agent': 'GurtDiscordBot (ProfileUpdaterCog, v0.1)'
            }
            # Try both potential endpoints
            for url in ('https://discord.com/api/v9/users/@me', 'https://discord.com/api/v9/users/@me/profile'):
                try:
                    async with self.session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            state["bio"] = data.get('bio')
                            if state["bio"] is not None: # Found bio, stop checking endpoints
                                print(f"ProfileUpdaterTask: Fetched current bio (length: {len(state['bio']) if state['bio'] else 0}).")
                                break
                        else:
                            print(f"ProfileUpdaterTask: Failed to fetch bio from {url} (status: {resp.status}).")
                except Exception as e:
                    print(f"ProfileUpdaterTask: Error fetching bio from {url}: {e}")
            if state["bio"] is None:
                 print("ProfileUpdaterTask: Could not fetch current bio.")
        else:
            print("ProfileUpdaterTask: Cannot fetch bio, BOT_TOKEN not set.")


        # Roles and Activity (Per Guild)
        for guild in self.bot.guilds:
            member = guild.get_member(self.bot.user.id)
            if member:
                # Roles
                state["roles"][str(guild.id)] = [role.name for role in member.roles if role.name != "@everyone"]

                # Activity (Use the first guild's activity as representative)
                if not state["activity"] and member.activity:
                    activity_type = member.activity.type
                    activity_text = member.activity.name
                    # Map discord.ActivityType enum to string if needed
                    activity_type_str = activity_type.name if isinstance(activity_type, discord.ActivityType) else str(activity_type)
                    state["activity"] = {"type": activity_type_str, "text": activity_text}

        print(f"ProfileUpdaterTask: Fetched current roles for {len(state['roles'])} guilds.")
        if state["activity"]:
            print(f"ProfileUpdaterTask: Fetched current activity: {state['activity']}")
        else:
            print("ProfileUpdaterTask: No current activity detected.")

        return state

    async def _ask_ai_for_updates(self, current_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Asks the GurtCog AI if and how to update the profile."""
        if not self.gurt_cog:
            return None

        # Construct the prompt for the AI
        # Need to access GurtCog's mood and potentially facts/interests
        current_mood = getattr(self.gurt_cog, 'current_mood', 'neutral') # Get mood safely
        # TODO: Get interests/facts relevant to profile updates (e.g., Kasane Teto)
        # This might require adding a method to GurtCog or MemoryManager
        interests_str = "Kasane Teto, gooning (jerking off)" # Placeholder

        # Prepare current state string for the prompt, safely handling None bio
        bio_value = current_state.get('bio')
        bio_summary = 'Not set'
        if bio_value: # Check if bio_value is not None and not an empty string
            bio_summary = f"{bio_value[:100]}{'...' if len(bio_value) > 100 else ''}"

        state_summary = f"""
Current State:
- Avatar URL: {current_state.get('avatar_url', 'None')}
- Bio: {bio_summary}
- Roles (Sample): {list(current_state.get('roles', {}).values())[0][:5] if current_state.get('roles') else 'None'}
- Activity: {current_state.get('activity', 'None')}
"""
        # Include image data if available
        image_prompt_part = ""
        if current_state.get('avatar_image_data'):
             image_prompt_part = "\n(Current avatar image data is provided below)" # Text hint for the AI

        # Define the JSON schema for the AI's response content
        response_schema_json = {
            "type": "object",
            "properties": {
                "should_update": {
                    "type": "boolean",
                    "description": "True if you want to change anything, false otherwise"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Your reasoning for the decision and chosen updates (or lack thereof)."
                },
                "updates": {
                    "type": "object",
                    "properties": {
                        "avatar_query": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "Search query for a new avatar"
                        },
                        "new_bio": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "The new bio text, or null"
                        },
                        "role_theme": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "A theme for role selection, could be a specific name color role, interest, or theme, or null"
                        },
                        "new_activity": {
                            "type": "object",
                            "description": "Object containing the new activity details. Set type and text to null if no change is desired.",
                            "properties": {
                                "type": {
                                    "anyOf": [{"type": "string", "enum": ["playing", "watching", "listening", "competing"]}, {"type": "null"}],
                                    "description": "Activity type: 'playing', 'watching', 'listening', 'competing', or null."
                                },
                                "text": {
                                    "anyOf": [{"type": "string"}, {"type": "null"}],
                                    "description": "The activity text, or null."
                                }
                            },
                            "required": ["type", "text"],
                            "additionalProperties": False
                        }
                    },
                    "required": ["avatar_query", "new_bio", "role_theme", "new_activity"],
                    "additionalProperties": False
                }
            },
            "required": ["should_update", "reasoning", "updates"],
            "additionalProperties": False # Enforce strictness at schema level too
        }
        json_format_instruction = json.dumps(response_schema_json, indent=2) # For the prompt

        # Define the payload for the response_format parameter
        response_format_payload = {
            "type": "json_schema",
            "json_schema": {
                "name": "profile_update_decision",
                "strict": True, # Enforce strict adherence to the schema
                "schema": response_schema_json
            }
        }

        # Construct the full prompt message list for the AI
        prompt_messages = [
            {"role": "system", "content": f"You are Gurt. It's time to consider updating your Discord profile. Your current mood is: {current_mood}. Your known interests include: {interests_str}. Review your current profile state and decide if you want to make any changes. Be creative and in-character. **IMPORTANT: Your *entire* response MUST be a single JSON object, with no other text before or after it.**"}, # Added emphasis here
            {"role": "user", "content": [
                 # Added emphasis at start and end of the text prompt
                {"type": "text", "text": f"**Your entire response MUST be ONLY the JSON object described below. No introductory text, no explanations, just the JSON.**\n\n{state_summary}{image_prompt_part}\n\nReview your current profile state. Decide if you want to change your avatar, bio, roles, or activity status. If yes, specify the changes in the JSON. If not, set 'should_update' to false.\n\n**CRITICAL: Respond ONLY with a valid JSON object matching this exact structure:**\n```json\n{json_format_instruction}\n```\n**ABSOLUTELY NO TEXT BEFORE OR AFTER THE JSON OBJECT.**"}
            ]}
        ]

        # Add image data if available and model supports it
        if current_state.get('avatar_image_data'):
            # Assuming the user message content is a list when multimodal
            prompt_messages[-1]["content"].append({ # Add to the list in the last user message
                "type": "image_url",
                "image_url": {"url": current_state["avatar_image_data"]}
            })
            print("ProfileUpdaterTask: Added current avatar image to AI prompt.")


        try:
            # Need a way to call GurtCog's core AI logic directly
            # This might require refactoring GurtCog or adding a dedicated method
            # Call the internal AI method from GurtCog, specifying the model and structured output format
            result_json = await self.gurt_cog._get_internal_ai_json_response(
                prompt_messages=prompt_messages,
                model="openai/o4-mini-high", # Use the specified OpenAI model
                response_format=response_format_payload, # Enforce structured output
                task_description="Profile Update Decision",
                temperature=0.5, # Keep temperature for some creativity
                max_tokens=5000
            )

            if result_json and isinstance(result_json, dict):
                # Basic validation of the received structure (now includes reasoning)
                if "should_update" in result_json and "updates" in result_json and "reasoning" in result_json:
                    print(f"ProfileUpdaterTask: AI Reasoning: {result_json.get('reasoning', 'N/A')}") # Log the reasoning
                    return result_json
                else:
                    print(f"ProfileUpdaterTask: AI response missing required keys (should_update, updates, reasoning). Response: {result_json}")
                    return None
            else:
                 print(f"ProfileUpdaterTask: AI response was not a dictionary. Response: {result_json}")
                 return None

        except Exception as e:
            print(f"ProfileUpdaterTask: Error calling AI for profile update decision: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _update_avatar(self, search_query: str):
        """Updates the bot's avatar based on an AI-generated search query."""
        print(f"ProfileUpdaterTask: Attempting to update avatar with query: '{search_query}'")
        if not self.gurt_cog or not hasattr(self.gurt_cog, 'web_search') or not self.session:
            print("ProfileUpdaterTask: Cannot update avatar, GurtCog or web search tool not available.")
            return

        try:
            # Use GurtCog's web_search tool
            search_results_data = await self.gurt_cog.web_search(query=search_query)

            if search_results_data.get("error"):
                print(f"ProfileUpdaterTask: Web search failed: {search_results_data['error']}")
                return

            image_url = None
            results = search_results_data.get("results", [])
            # Find the first result with a plausible image URL
            for result in results:
                url = result.get("url")
                # Basic check for image file extensions or common image hosting domains
                if url and any(ext in url.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']) or \
                   any(domain in url.lower() for domain in ['imgur.com', 'pinimg.com', 'giphy.com']):
                    image_url = url
                    break

            if not image_url:
                print("ProfileUpdaterTask: No suitable image URL found in search results.")
                return

            print(f"ProfileUpdaterTask: Found image URL: {image_url}")

            # Download the image
            async with self.session.get(image_url) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                    # Check rate limits before editing (simple delay for now)
                    # Discord API limits avatar changes (e.g., 2 per hour?)
                    # A more robust solution would track the last change time.
                    await asyncio.sleep(5) # Basic delay
                    await self.bot.user.edit(avatar=image_bytes)
                    print("ProfileUpdaterTask: Avatar updated successfully.")
                else:
                    print(f"ProfileUpdaterTask: Failed to download image from {image_url} (status: {resp.status}).")

        except discord.errors.HTTPException as e:
             print(f"ProfileUpdaterTask: Discord API error updating avatar: {e.status} - {e.text}")
        except Exception as e:
            print(f"ProfileUpdaterTask: Error updating avatar: {e}")
            import traceback
            traceback.print_exc()

    async def _update_bio(self, new_bio: str):
        """Updates the bot's bio using the Discord API."""
        print(f"ProfileUpdaterTask: Attempting to update bio to: '{new_bio[:50]}...'")
        if not self.bot_token or not self.session:
            print("ProfileUpdaterTask: Cannot update bio, BOT_TOKEN or session not available.")
            return

        headers = {
            'Authorization': f'Bot {self.bot_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'GurtDiscordBot (ProfileUpdaterCog, v0.1)'
        }
        payload = {'bio': new_bio}
        url = 'https://discord.com/api/v9/users/@me' # Primary endpoint

        try:
            # Check rate limits (simple delay for now)
            await asyncio.sleep(2)
            async with self.session.patch(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    print("ProfileUpdaterTask: Bio updated successfully.")
                else:
                    # Try fallback endpoint if the first failed with specific errors (e.g., 404)
                    if resp.status == 404:
                         print(f"ProfileUpdaterTask: PATCH {url} failed (404), trying /profile endpoint...")
                         url_profile = 'https://discord.com/api/v9/users/@me/profile'
                         async with self.session.patch(url_profile, headers=headers, json=payload) as resp_profile:
                             if resp_profile.status == 200:
                                 print("ProfileUpdaterTask: Bio updated successfully via /profile endpoint.")
                             else:
                                 print(f"ProfileUpdaterTask: Failed to update bio via /profile endpoint (status: {resp_profile.status}). Response: {await resp_profile.text()}")
                    else:
                        print(f"ProfileUpdaterTask: Failed to update bio (status: {resp.status}). Response: {await resp.text()}")

        except Exception as e:
            print(f"ProfileUpdaterTask: Error updating bio: {e}")
            import traceback
            traceback.print_exc()

    async def _update_roles(self, role_theme: str):
        """Updates the bot's roles based on an AI-generated theme."""
        print(f"ProfileUpdaterTask: Attempting to update roles based on theme: '{role_theme}'")
        if not self.gurt_cog:
             print("ProfileUpdaterTask: Cannot update roles, GurtCog not available.")
             return

        # This requires iterating through guilds and potentially making another AI call
        # --- Implementation ---
        guild_update_tasks = []
        for guild in self.bot.guilds:
            guild_update_tasks.append(self._update_roles_for_guild(guild, role_theme))

        results = await asyncio.gather(*guild_update_tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"ProfileUpdaterTask: Error updating roles for guild {self.bot.guilds[i].id}: {result}")
            elif result: # If the helper returned True (success)
                 print(f"ProfileUpdaterTask: Successfully updated roles for guild {self.bot.guilds[i].id} based on theme '{role_theme}'.")
            # else: No update was needed or possible for this guild

    async def _update_roles_for_guild(self, guild: discord.Guild, role_theme: str) -> bool:
        """Helper to update roles for a specific guild."""
        member = guild.get_member(self.bot.user.id)
        if not member:
            print(f"ProfileUpdaterTask: Bot member not found in guild {guild.id}.")
            return False

        # Filter assignable roles
        assignable_roles = []
        bot_top_role_position = member.top_role.position
        for role in guild.roles:
            # Cannot assign roles higher than or equal to bot's top role
            # Cannot assign managed roles (integrations, bot roles)
            # Cannot assign @everyone role
            if not role.is_integration() and not role.is_bot_managed() and not role.is_default() and role.position < bot_top_role_position:
                 # Check if bot has manage_roles permission
                 if member.guild_permissions.manage_roles:
                     assignable_roles.append(role)
                 else:
                     # If no manage_roles perm, can only assign roles lower than bot's top role *if* they are unmanaged
                     # This check is already covered by the position check and managed role checks above.
                     # However, without manage_roles, the add/remove calls will fail anyway.
                     print(f"ProfileUpdaterTask: Bot lacks manage_roles permission in guild {guild.id}. Cannot update roles.")
                     return False # Cannot proceed without permission

        if not assignable_roles:
            print(f"ProfileUpdaterTask: No assignable roles found in guild {guild.id}.")
            return False

        assignable_role_names = [role.name for role in assignable_roles]
        current_role_names = [role.name for role in member.roles if role.name != "@everyone"]

        # Define the JSON schema for the role selection AI response
        role_selection_schema = {
            "type": "object",
            "properties": {
                "roles_to_add": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of role names to add (max 2)"
                },
                "roles_to_remove": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of role names to remove (max 2, only from current roles)"
                }
            },
            "required": ["roles_to_add", "roles_to_remove"],
            "additionalProperties": False
        }
        role_selection_format = json.dumps(role_selection_schema, indent=2)

        # Prepare prompt for the second AI call
        role_prompt_messages = [
            {"role": "system", "content": f"You are Gurt. Based on the theme '{role_theme}', select roles to add or remove from the available list for this server. Prioritize adding roles that fit the theme and removing roles that don't or conflict. You can add/remove up to 2 roles total."},
            {"role": "user", "content": f"Available assignable roles: {assignable_role_names}\nYour current roles: {current_role_names}\nTheme: '{role_theme}'\n\nSelect roles to add/remove based on the theme.\n\n**CRITICAL: Respond ONLY with a valid JSON object matching this structure:**\n```json\n{role_selection_format}\n```\n**Ensure nothing precedes or follows the JSON.**"}
        ]

        try:
            # Make the AI call to select roles
            # Define the payload for the response_format parameter
            role_selection_format_payload = {
                "type": "json_schema",
                "json_schema": {
                    "name": "role_selection_decision",
                    "strict": True,
                    "schema": role_selection_schema
                }
            }

            role_decision = await self.gurt_cog._get_internal_ai_json_response(
                prompt_messages=role_prompt_messages,
                model="openai/o4-mini-high", # Use the specified OpenAI model
                response_format=role_selection_format_payload, # Enforce structured output
                task_description=f"Role Selection for Guild {guild.id}",
                temperature=0.5 # More deterministic for role selection
            )

            if not role_decision or not isinstance(role_decision, dict):
                print(f"ProfileUpdaterTask: Failed to get valid role selection from AI for guild {guild.id}.")
                return False

            roles_to_add_names = role_decision.get("roles_to_add", [])
            roles_to_remove_names = role_decision.get("roles_to_remove", [])

            # Validate AI response
            if not isinstance(roles_to_add_names, list) or not isinstance(roles_to_remove_names, list):
                 print(f"ProfileUpdaterTask: Invalid format for roles_to_add/remove from AI for guild {guild.id}.")
                 return False

            # Limit changes
            roles_to_add_names = roles_to_add_names[:2]
            roles_to_remove_names = roles_to_remove_names[:2]

            # Find the actual Role objects
            roles_to_add = []
            for name in roles_to_add_names:
                role = discord.utils.get(assignable_roles, name=name)
                # Ensure it's not already assigned and is assignable
                if role and role not in member.roles:
                    roles_to_add.append(role)

            roles_to_remove = []
            for name in roles_to_remove_names:
                 # Can only remove roles the bot currently has
                role = discord.utils.get(member.roles, name=name)
                # Ensure it's not the @everyone role or managed roles (already filtered, but double check)
                if role and not role.is_default() and not role.is_integration() and not role.is_bot_managed():
                    roles_to_remove.append(role)

            # Apply changes if any
            changes_made = False
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason=f"ProfileUpdaterCog: Applying theme '{role_theme}'")
                    print(f"ProfileUpdaterTask: Removed roles {[r.name for r in roles_to_remove]} in guild {guild.id}.")
                    changes_made = True
                    await asyncio.sleep(1) # Small delay between actions
                except discord.Forbidden:
                    print(f"ProfileUpdaterTask: Permission error removing roles in guild {guild.id}.")
                except discord.HTTPException as e:
                    print(f"ProfileUpdaterTask: HTTP error removing roles in guild {guild.id}: {e}")

            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason=f"ProfileUpdaterCog: Applying theme '{role_theme}'")
                    print(f"ProfileUpdaterTask: Added roles {[r.name for r in roles_to_add]} in guild {guild.id}.")
                    changes_made = True
                except discord.Forbidden:
                    print(f"ProfileUpdaterTask: Permission error adding roles in guild {guild.id}.")
                except discord.HTTPException as e:
                    print(f"ProfileUpdaterTask: HTTP error adding roles in guild {guild.id}: {e}")

            return changes_made # Return True if any change was attempted/successful

        except Exception as e:
            print(f"ProfileUpdaterTask: Error during role update for guild {guild.id}: {e}")
            import traceback
            traceback.print_exc()
            return False


    async def _update_activity(self, activity_info: Dict[str, Optional[str]]):
        """Updates the bot's activity status."""
        activity_type_str = activity_info.get("type")
        activity_text = activity_info.get("text")

        # Check if both values are None - this means we should clear the activity
        if activity_type_str is None and activity_text is None:
            print("ProfileUpdaterTask: Clearing activity status.")
            try:
                await self.bot.change_presence(activity=None)
                print("ProfileUpdaterTask: Activity cleared successfully.")
                return
            except Exception as e:
                print(f"ProfileUpdaterTask: Error clearing activity: {e}")
                import traceback
                traceback.print_exc()
                return

        # If only one is None but not both, that's invalid
        if activity_type_str is None or activity_text is None:
            print("ProfileUpdaterTask: Invalid activity info received from AI - one field is null but not both.")
            return

        print(f"ProfileUpdaterTask: Attempting to set activity to {activity_type_str}: '{activity_text}'")

        # Map string type to discord.ActivityType enum
        activity_type_map = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing,
            # Add streaming later if needed (requires URL)
        }

        activity_type = activity_type_map.get(activity_type_str.lower())

        if activity_type is None:
            print(f"ProfileUpdaterTask: Unknown activity type '{activity_type_str}'. Defaulting to 'playing'.")
            activity_type = discord.ActivityType.playing

        activity = discord.Activity(type=activity_type, name=activity_text)

        try:
            await self.bot.change_presence(activity=activity)
            print("ProfileUpdaterTask: Activity updated successfully.")
        except Exception as e:
            print(f"ProfileUpdaterTask: Error updating activity: {e}")
            import traceback
            traceback.print_exc()


async def setup(bot: commands.Bot):
    """Adds the ProfileUpdaterCog to the bot."""
    await bot.add_cog(ProfileUpdaterCog(bot))
