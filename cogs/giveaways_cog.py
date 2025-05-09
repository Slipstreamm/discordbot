import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import random
import re # For parsing duration

class GiveawaysCog(commands.Cog, name="Giveaways"):
    """Cog for managing giveaways"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_giveaways = []  # List to store active giveaway details
        # Each entry could be a dict:
        # {
        #     "message_id": int,
        #     "channel_id": int,
        #     "guild_id": int,
        #     "prize": str,
        #     "end_time": datetime.datetime,
        #     "num_winners": int,
        #     "reaction_emoji": str, # e.g., "🎉"
        #     "creator_id": int,
        #     "participants": set() # Store user_ids of participants
        # }
        self.check_giveaways_loop.start()

    def cog_unload(self):
        self.check_giveaways_loop.cancel()

    def parse_duration(self, duration_str: str) -> datetime.timedelta | None:
        """Parses a duration string (e.g., "1d", "3h", "30m", "1w") into a timedelta."""
        match = re.fullmatch(r"(\d+)([smhdw])", duration_str.lower())
        if not match:
            return None
        
        value, unit = int(match.group(1)), match.group(2)
        
        if unit == 's':
            return datetime.timedelta(seconds=value)
        elif unit == 'm':
            return datetime.timedelta(minutes=value)
        elif unit == 'h':
            return datetime.timedelta(hours=value)
        elif unit == 'd':
            return datetime.timedelta(days=value)
        elif unit == 'w':
            return datetime.timedelta(weeks=value)
        return None

    @app_commands.command(name="gcreate", description="Create a new giveaway.")
    @app_commands.describe(
        prize="What is the prize?",
        duration="How long should the giveaway last? (e.g., 10m, 1h, 2d, 1w)",
        winners="How many winners? (default: 1)"
    )
    @app_commands.checks.has_permissions(manage_guild=True) # Example permission
    async def create_giveaway_slash(self, interaction: discord.Interaction, prize: str, duration: str, winners: int = 1):
        """Slash command to create a giveaway."""
        parsed_duration = self.parse_duration(duration)
        if not parsed_duration:
            await interaction.response.send_message(
                "Invalid duration format. Use s, m, h, d, w (e.g., 10m, 1h, 2d).",
                ephemeral=True
            )
            return

        if winners < 1:
            await interaction.response.send_message("Number of winners must be at least 1.", ephemeral=True)
            return

        end_time = datetime.datetime.now(datetime.timezone.utc) + parsed_duration
        reaction_emoji = "🎉"

        embed = discord.Embed(
            title=f"🎉 Giveaway: {prize} 🎉",
            description=f"React with {reaction_emoji} to enter!\n"
                        f"Ends: {discord.utils.format_dt(end_time, style='R')} ({discord.utils.format_dt(end_time, style='F')})\n"
                        f"Winners: {winners}",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Giveaway started by {interaction.user.display_name}")
        
        # Send the message and get the message object
        # We need to use follow up if we responded ephemerally before, but here we send a new message.
        # If interaction.response.is_done() is false, we can use send_message.
        # Otherwise, we must use followup.send.
        # For simplicity, let's assume we always send a new message for the giveaway.
        
        await interaction.response.send_message("Creating giveaway...", ephemeral=True) # Acknowledge interaction
        giveaway_message = await interaction.channel.send(embed=embed)
        await giveaway_message.add_reaction(reaction_emoji)

        giveaway_data = {
            "message_id": giveaway_message.id,
            "channel_id": interaction.channel.id,
            "guild_id": interaction.guild.id,
            "prize": prize,
            "end_time": end_time,
            "num_winners": winners,
            "reaction_emoji": reaction_emoji,
            "creator_id": interaction.user.id,
            "participants": set() # Will be populated by on_raw_reaction_add
        }
        self.active_giveaways.append(giveaway_data)
        
        await interaction.followup.send(f"Giveaway for '{prize}' created successfully!", ephemeral=True)


    @tasks.loop(seconds=30) # Check every 30 seconds
    async def check_giveaways_loop(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        ended_giveaways_indices = []

        for i, giveaway in enumerate(self.active_giveaways):
            if now >= giveaway["end_time"]:
                ended_giveaways_indices.append(i)
                
                channel = self.bot.get_channel(giveaway["channel_id"])
                if not channel:
                    print(f"Error: Could not find channel {giveaway['channel_id']} for giveaway {giveaway['message_id']}")
                    continue # Or remove from active_giveaways if channel is permanently gone

                try:
                    message = await channel.fetch_message(giveaway["message_id"])
                except discord.NotFound:
                    print(f"Error: Could not find message {giveaway['message_id']} in channel {channel.id}")
                    # Giveaway message was deleted, consider it ended/cancelled.
                    continue 
                except discord.Forbidden:
                    print(f"Error: Bot lacks permissions to fetch message {giveaway['message_id']} in channel {channel.id}")
                    continue


                # Fetch users who reacted
                entrants = set()
                for reaction in message.reactions:
                    if str(reaction.emoji) == giveaway["reaction_emoji"]:
                        async for user in reaction.users():
                            if not user.bot: # Don't include bots
                                entrants.add(user)
                        break
                
                winners_list = []
                if entrants:
                    if len(entrants) <= giveaway["num_winners"]:
                        winners_list = list(entrants)
                    else:
                        winners_list = random.sample(list(entrants), giveaway["num_winners"])

                # Announce winners
                if winners_list:
                    winner_mentions = ", ".join(w.mention for w in winners_list)
                    await channel.send(f"Congratulations {winner_mentions}! You won **{giveaway['prize']}**!")
                else:
                    await channel.send(f"The giveaway for **{giveaway['prize']}** has ended, but there were no eligible participants.")

                # Update original giveaway message
                new_embed = message.embeds[0]
                new_embed.description = f"Giveaway ended!\nWinners: {', '.join(w.mention for w in winners_list) if winners_list else 'None'}"
                new_embed.color = discord.Color.dark_grey()
                new_embed.set_footer(text="Giveaway has concluded.")
                try:
                    await message.edit(embed=new_embed)
                    await message.clear_reactions() # Optional: clear reactions
                except discord.Forbidden:
                    print(f"Error: Bot lacks permissions to edit message or clear reactions for {giveaway['message_id']}")
                except discord.HTTPException as e:
                    print(f"Error editing giveaway message {giveaway['message_id']}: {e}")


        # Remove ended giveaways from active list (iterate in reverse to avoid index issues)
        for i in sorted(ended_giveaways_indices, reverse=True):
            del self.active_giveaways[i]

    @check_giveaways_loop.before_loop
    async def before_check_giveaways_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # This listener is basic and doesn't store participants in self.active_giveaways yet.
        # For a full implementation, we'd find the giveaway by message_id and add payload.user_id.
        # This is also where you might check if the user is eligible (e.g. not a bot, specific roles).
        if payload.user_id == self.bot.user.id:
            return

        for giveaway in self.active_giveaways:
            if payload.message_id == giveaway["message_id"] and str(payload.emoji) == giveaway["reaction_emoji"]:
                # Here you could add payload.user_id to giveaway["participants"] if you want to track them
                # For this version, the winner selection fetches all reactors at the end.
                # print(f"User {payload.user_id} reacted to giveaway {giveaway['message_id']}")
                break
    
    # Placeholder for other commands like !greroll, !gend, !glist
    # @app_commands.command(name="greroll", description="Reroll a winner for a giveaway.")
    # @app_commands.checks.has_permissions(manage_guild=True)
    # async def reroll_giveaway_slash(self, interaction: discord.Interaction, message_id: str):
    #     pass

    # @app_commands.command(name="gend", description="End a giveaway immediately.")
    # @app_commands.checks.has_permissions(manage_guild=True)
    # async def end_giveaway_slash(self, interaction: discord.Interaction, message_id: str):
    #     pass

    # @app_commands.command(name="glist", description="List active giveaways.")
    # async def list_giveaways_slash(self, interaction: discord.Interaction):
    #     pass

    @app_commands.command(name="grollmanual", description="Manually roll a winner from reactions on a specific message.")
    @app_commands.describe(
        message_id="The ID of the message to get reactions from.",
        winners="How many winners to pick? (default: 1)",
        emoji="Which emoji should be considered for entry? (default: 🎉)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def manual_roll_giveaway_slash(self, interaction: discord.Interaction, message_id: str, winners: int = 1, emoji: str = "🎉"):
        """Manually picks winner(s) from reactions on a given message."""
        if winners < 1:
            await interaction.response.send_message("Number of winners must be at least 1.", ephemeral=True)
            return

        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid Message ID format. It should be a number.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True) # Acknowledge interaction

        try:
            # Try to fetch the message from the current channel first, then any channel in the guild
            message_to_roll = None
            try:
                message_to_roll = await interaction.channel.fetch_message(msg_id)
            except discord.NotFound:
                # If not in current channel, search all text channels in the guild
                for channel in interaction.guild.text_channels:
                    try:
                        message_to_roll = await channel.fetch_message(msg_id)
                        if message_to_roll:
                            break # Found the message
                    except discord.NotFound:
                        continue # Not in this channel
                    except discord.Forbidden:
                        await interaction.followup.send(f"I don't have permissions to read messages in {channel.mention}. Cannot fetch message {msg_id}.", ephemeral=True)
                        return
            
            if not message_to_roll:
                await interaction.followup.send(f"Could not find message with ID `{msg_id}` in this server.", ephemeral=True)
                return

        except discord.Forbidden:
            await interaction.followup.send(f"I don't have permissions to read message history in {interaction.channel.mention} to find message `{msg_id}`.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred while fetching the message: {e}", ephemeral=True)
            return

        entrants = set()
        reaction_found = False
        for reaction in message_to_roll.reactions:
            if str(reaction.emoji) == emoji:
                reaction_found = True
                async for user in reaction.users():
                    if not user.bot:
                        entrants.add(user)
                break
        
        if not reaction_found:
            await interaction.followup.send(f"No reactions found with the emoji {emoji} on message `{msg_id}`.", ephemeral=True)
            return

        if not entrants:
            await interaction.followup.send(f"No valid (non-bot) users reacted with {emoji} on message `{msg_id}`.", ephemeral=True)
            return

        winners_list = []
        if len(entrants) <= winners:
            winners_list = list(entrants)
        else:
            winners_list = random.sample(list(entrants), winners)

        if winners_list:
            winner_mentions = ", ".join(w.mention for w in winners_list)
            # Announce in the channel where command was used, not necessarily message_to_roll.channel
            await interaction.followup.send(f"Congratulations {winner_mentions}! You've been manually selected as winner(s) from message `{msg_id}` in {message_to_roll.channel.mention}!", ephemeral=False)
            
            # Optionally, also send to the original message's channel if different and bot has perms
            if interaction.channel.id != message_to_roll.channel.id:
                try:
                    await message_to_roll.channel.send(f"Manual roll for message {message_to_roll.jump_url} concluded. Winner(s): {winner_mentions}")
                except discord.Forbidden:
                    await interaction.followup.send(f"(Note: I couldn't announce the winner in {message_to_roll.channel.mention} due to missing permissions there.)", ephemeral=True)
                except discord.HTTPException:
                     await interaction.followup.send(f"(Note: An error occurred trying to announce the winner in {message_to_roll.channel.mention}.)", ephemeral=True)

        else: # Should not happen if entrants is not empty, but as a safeguard
            await interaction.followup.send(f"Could not select any winners from the reactions on message `{msg_id}`.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawaysCog(bot))
