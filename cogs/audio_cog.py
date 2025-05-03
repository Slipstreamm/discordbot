import discord
from discord import ui # Added for views/buttons
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import yt_dlp as youtube_dl
import logging
from collections import deque
import math # For pagination calculation

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Suppress noisy yt-dlp logs unless debugging
youtube_dl.utils.bug_reports_message = lambda: ''

# --- yt-dlp Options ---
YDL_OPTS_BASE = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False, # Allow playlists by default, override per call if needed
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch', # Default to YouTube search
    'source_address': '0.0.0.0', # Bind to all IPs for better connectivity
    'cookiefile': 'cookies.txt'

}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn' # No video
}

class Song:
    """Represents a song to be played."""
    def __init__(self, source_url, title, webpage_url, duration, requested_by):
        self.source_url = source_url
        self.title = title
        self.webpage_url = webpage_url
        self.duration = duration
        self.requested_by = requested_by # User who requested the song

    def __str__(self):
        return f"**{self.title}** ({self.format_duration()})"

    def format_duration(self):
        """Formats duration in seconds to MM:SS or HH:MM:SS."""
        if not self.duration:
            return "N/A"
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

class AudioCog(commands.Cog, name="Audio"):
    """Cog for audio playback commands"""

    def __init__(self, bot):
        self.bot = bot
        self.queues = {} # Dictionary to hold queues per guild {guild_id: deque()}
        self.current_song = {} # Dictionary for current song per guild {guild_id: Song}
        self.voice_clients = {} # Dictionary for voice clients per guild {guild_id: discord.VoiceClient}

        # Create the main command group for this cog
        self.audio_group = app_commands.Group(
            name="audio",
            description="Audio playback commands"
        )

        # Create subgroups
        self.playback_group = app_commands.Group(
            name="playback",
            description="Playback control commands",
            parent=self.audio_group
        )

        self.queue_group = app_commands.Group(
            name="queue",
            description="Queue management commands",
            parent=self.audio_group
        )

        # Register commands
        self.register_commands()

        # Add command groups to the bot's tree
        self.bot.tree.add_command(self.audio_group)

        # Start the background task
        self.play_next_song.start()

    def get_queue(self, guild_id):
        """Gets the queue for a guild, creating it if it doesn't exist."""
        return self.queues.setdefault(guild_id, deque())

    def get_current_song(self, guild_id):
        """Gets the current song for a guild."""
        return self.current_song.get(guild_id)

    def cleanup(self, guild_id):
        """Cleans up resources for a guild."""
        if guild_id in self.queues:
            del self.queues[guild_id]
        if guild_id in self.current_song:
            del self.current_song[guild_id]
        if guild_id in self.voice_clients:
            vc = self.voice_clients.pop(guild_id)
            if vc and vc.is_connected():
                 # Use asyncio.create_task for fire-and-forget disconnect
                 asyncio.create_task(vc.disconnect(force=True))
            log.info(f"Cleaned up resources for guild {guild_id}")

    def register_commands(self):
        """Register all commands for this cog"""

        # --- Playback Group Commands ---
        # Play command
        play_command = app_commands.Command(
            name="play",
            description="Play a song or add it to the queue",
            callback=self.audio_play_callback,
            parent=self.playback_group
        )
        self.playback_group.add_command(play_command)

        # Pause command
        pause_command = app_commands.Command(
            name="pause",
            description="Pause the current playback",
            callback=self.audio_pause_callback,
            parent=self.playback_group
        )
        self.playback_group.add_command(pause_command)

        # Resume command
        resume_command = app_commands.Command(
            name="resume",
            description="Resume paused playback",
            callback=self.audio_resume_callback,
            parent=self.playback_group
        )
        self.playback_group.add_command(resume_command)

        # Skip command
        skip_command = app_commands.Command(
            name="skip",
            description="Skip the current song",
            callback=self.audio_skip_callback,
            parent=self.playback_group
        )
        self.playback_group.add_command(skip_command)

        # Stop command
        stop_command = app_commands.Command(
            name="stop",
            description="Stop playback and clear the queue",
            callback=self.audio_stop_callback,
            parent=self.playback_group
        )
        self.playback_group.add_command(stop_command)

        # --- Queue Group Commands ---
        # List command
        list_command = app_commands.Command(
            name="list",
            description="Display the current song queue",
            callback=self.audio_queue_list_callback,
            parent=self.queue_group
        )
        self.queue_group.add_command(list_command)

        # Clear command
        clear_command = app_commands.Command(
            name="clear",
            description="Clear the song queue",
            callback=self.audio_queue_clear_callback,
            parent=self.queue_group
        )
        self.queue_group.add_command(clear_command)

        # --- Main Audio Group Commands ---
        # Join command
        join_command = app_commands.Command(
            name="join",
            description="Join your voice channel",
            callback=self.audio_join_callback,
            parent=self.audio_group
        )
        self.audio_group.add_command(join_command)

        # Leave command
        leave_command = app_commands.Command(
            name="leave",
            description="Leave the voice channel",
            callback=self.audio_leave_callback,
            parent=self.audio_group
        )
        self.audio_group.add_command(leave_command)

        # Search command
        search_command = app_commands.Command(
            name="search",
            description="Search for songs on YouTube",
            callback=self.audio_search_callback,
            parent=self.audio_group
        )
        self.audio_group.add_command(search_command)

    async def cog_unload(self):
        """Cog unload cleanup."""
        self.play_next_song.cancel()
        for guild_id in list(self.voice_clients.keys()): # Iterate over keys copy
            self.cleanup(guild_id)

    @tasks.loop(seconds=1.0)
    async def play_next_song(self):
        """Background task to play the next song in the queue for each guild."""
        for guild_id, vc in list(self.voice_clients.items()): # Iterate over copy
            if not vc or not vc.is_connected():
                # If VC disconnected unexpectedly, clean up
                log.warning(f"VC for guild {guild_id} disconnected unexpectedly. Cleaning up.")
                self.cleanup(guild_id)
                continue

            queue = self.get_queue(guild_id)
            if not vc.is_playing() and not vc.is_paused() and queue:
                next_song = queue.popleft()
                self.current_song[guild_id] = next_song
                try:
                    log.info(f"Playing next song in guild {guild_id}: {next_song.title}")
                    source = discord.FFmpegPCMAudio(next_song.source_url, **FFMPEG_OPTIONS)
                    vc.play(source, after=lambda e: self.handle_after_play(e, guild_id))
                    # Optionally send a "Now Playing" message to the channel
                    # This requires storing the context or channel ID somewhere
                except Exception as e:
                    log.error(f"Error playing song {next_song.title} in guild {guild_id}: {e}")
                    self.current_song[guild_id] = None # Clear current song on error
                    # Try to play the next one if available
                    if queue:
                         log.info(f"Trying next song in queue for guild {guild_id}")
                         # Let the loop handle the next iteration naturally
                    else:
                         log.info(f"Queue empty for guild {guild_id} after error.")
                         # Consider leaving VC after inactivity?
            elif not vc.is_playing() and not vc.is_paused() and not queue:
                 # If nothing is playing and queue is empty, clear current song
                 if self.current_song.get(guild_id):
                     self.current_song[guild_id] = None
                     log.info(f"Queue empty and playback finished for guild {guild_id}. Current song cleared.")
                 # Add inactivity disconnect logic here if desired

    def handle_after_play(self, error, guild_id):
        """Callback function after a song finishes playing."""
        if error:
            log.error(f'Player error in guild {guild_id}: {error}')
        else:
            log.info(f"Song finished playing in guild {guild_id}.")
        # The loop will handle playing the next song

    @play_next_song.before_loop
    async def before_play_next_song(self):
        await self.bot.wait_until_ready()
        log.info("AudioCog background task started.")

    async def _extract_info(self, query):
        """Extracts info using yt-dlp. Handles URLs and search queries."""
        ydl_opts = YDL_OPTS_BASE.copy()
        is_search = not (query.startswith('http://') or query.startswith('https://'))

        if is_search:
            # For search, limit to 1 result and treat as single item
            ydl_opts['default_search'] = 'ytsearch1'
            ydl_opts['noplaylist'] = True # Explicitly search for single video
            log.info(f"Performing YouTube search for: {query}")
        else:
            # For URLs, let yt-dlp determine if it's a playlist or single video
            # Do not use extract_flat, get full info
            ydl_opts['noplaylist'] = False # Allow playlists
            log.info(f"Processing URL: {query}")

        try:
            # Extract full information
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)

            # Determine if it's a playlist *after* extraction
            is_playlist = info.get('_type') == 'playlist'

            if is_search and 'entries' in info and info['entries']:
                 # If search returned results, take the first one
                 info = info['entries'][0]
                 is_playlist = False # Search result is treated as single item
            elif is_search and ('entries' not in info or not info['entries']):
                 # Handle case where search yields no results directly
                 return None, False, True # Indicate no info found

            return info, is_playlist, is_search

        except youtube_dl.utils.DownloadError as e:
            # Handle specific errors if possible (e.g., video unavailable)
            error_msg = str(e)
            if 'video unavailable' in error_msg.lower():
                 raise commands.CommandError(f"The video '{query}' is unavailable.")
            elif 'playlist does not exist' in error_msg.lower():
                 raise commands.CommandError(f"The playlist '{query}' does not exist or is private.")
            log.error(f"yt-dlp download error for '{query}': {error_msg}")
            raise commands.CommandError(f"Could not process '{query}'. Is it a valid URL or search term?")
        except Exception as e:
            log.error(f"Unexpected yt-dlp error for '{query}': {e}")
            raise commands.CommandError("An unexpected error occurred while fetching video info.")

    async def _search_youtube(self, query: str, max_results: int = 15): # Increased max_results for pagination
        """Performs a YouTube search and returns multiple results."""
        # Clamp max_results to avoid excessively long searches if abused
        max_results = min(max(1, max_results), 25) # Limit between 1 and 25
        ydl_opts = YDL_OPTS_BASE.copy()
        # Use ytsearchN: query to get N results
        ydl_opts['default_search'] = f'ytsearch{max_results}'
        ydl_opts['noplaylist'] = True # Ensure only videos are searched
        log.info(f"Performing YouTube search for '{query}' (max {max_results} results)")

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                # Extract info without downloading
                info = ydl.extract_info(query, download=False)

            # Check if 'entries' exist and contain results
            if 'entries' in info and info['entries']:
                return info['entries'] # Return the list of video dictionaries
            else:
                log.info(f"No search results found for '{query}'")
                return [] # Return empty list if no results

        except youtube_dl.utils.DownloadError as e:
            log.error(f"yt-dlp search download error for '{query}': {e}")
            # Don't raise here, let the command handle empty results
            return []
        except Exception as e:
            log.error(f"Unexpected yt-dlp error during search for '{query}': {e}")
            # Don't raise here, let the command handle empty results
            return []

    async def _ensure_voice_connection(self, ctx_or_interaction):
        """Ensures the bot is connected to the user's voice channel. Accepts Context or Interaction."""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)

        if is_interaction:
            guild = ctx_or_interaction.guild
            author = ctx_or_interaction.user
            if not guild: raise commands.CommandError("Interaction must be in a guild.")
        else: # Is Context
            guild = ctx_or_interaction.guild
            author = ctx_or_interaction.author
            if not guild: raise commands.CommandError("Command must be used in a guild.")

        if not isinstance(author, discord.Member) or not author.voice or not author.voice.channel:
             raise commands.CommandError("You are not connected to a voice channel.")

        vc = self.voice_clients.get(guild.id)
        target_channel = author.voice.channel

        if not vc or not vc.is_connected():
            try:
                log.info(f"Connecting to voice channel {target_channel.name} in guild {guild.id}")
                vc = await target_channel.connect()
                self.voice_clients[guild.id] = vc
            except asyncio.TimeoutError:
                raise commands.CommandError(f"Connecting to {target_channel.name} timed out.")
            except discord.errors.ClientException as e:
                 raise commands.CommandError(f"Already connected to a voice channel? Error: {e}")
            except Exception as e:
                 log.error(f"Failed to connect to {target_channel.name}: {e}")
                 raise commands.CommandError(f"Failed to connect to the voice channel: {e}")
        elif vc.channel != target_channel:
            try:
                log.info(f"Moving to voice channel {target_channel.name} in guild {guild.id}")
                await vc.move_to(target_channel)
                self.voice_clients[guild.id] = vc # Ensure the instance is updated if move_to returns a new one
            except Exception as e:
                log.error(f"Failed to move to {target_channel.name}: {e}")
                raise commands.CommandError(f"Failed to move to your voice channel: {e}")

        return vc

    # --- Command Callbacks ---

    # Audio group callbacks
    async def audio_join_callback(self, interaction: discord.Interaction):
        """Callback for /audio join command"""
        try:
            await self._ensure_voice_connection(interaction)
            await interaction.response.send_message(f"Connected to **{interaction.user.voice.channel.name}**.")
        except commands.CommandError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        except Exception as e:
            log.error(f"Error in join command: {e}")
            await interaction.response.send_message("An unexpected error occurred while trying to join.", ephemeral=True)

    async def audio_leave_callback(self, interaction: discord.Interaction):
        """Callback for /audio leave command"""
        vc = self.voice_clients.get(interaction.guild.id)
        if not vc or not vc.is_connected():
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return

        log.info(f"Disconnecting from voice channel in guild {interaction.guild.id}")
        await interaction.response.send_message(f"Disconnecting from **{vc.channel.name}**.")
        self.cleanup(interaction.guild.id) # This handles the disconnect and queue clearing

    async def audio_search_callback(self, interaction: discord.Interaction, query: str, max_results: int = 10):
        """Callback for /audio search command"""
        # Defer the response since search might take time
        await interaction.response.defer(ephemeral=True)

        try:
            # Perform the search
            results = await self._search_youtube(query, max_results)

            if not results:
                await interaction.followup.send("No results found for your search query.", ephemeral=True)
                return

            # Create a formatted list of results
            result_list = []
            for i, result in enumerate(results):
                title = result.get('title', 'Unknown Title')
                duration = result.get('duration')
                duration_str = "N/A"
                if duration:
                    minutes, seconds = divmod(duration, 60)
                    hours, minutes = divmod(minutes, 60)
                    if hours > 0:
                        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        duration_str = f"{minutes:02d}:{seconds:02d}"

                result_list.append(f"**{i+1}.** {title} ({duration_str})")

            # Create an embed with the results
            embed = discord.Embed(
                title=f"Search Results for '{query}'",
                description="\n".join(result_list),
                color=discord.Color.blue()
            )

            # Create a view with buttons to select a result
            view = SearchResultsView(self, interaction.user, results)

            # Send the results
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            log.error(f"Error in search command: {e}")
            await interaction.followup.send(f"An error occurred while searching: {e}", ephemeral=True)

    # Playback group callbacks
    async def audio_play_callback(self, interaction: discord.Interaction, query: str):
        """Callback for /audio playback play command"""
        # Defer the response since this might take time
        await interaction.response.defer()

        try:
            vc = await self._ensure_voice_connection(interaction)
        except commands.CommandError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        except Exception as e:
            log.error(f"Error ensuring voice connection in play command: {e}")
            await interaction.followup.send("An unexpected error occurred before playing.", ephemeral=True)
            return

        queue = self.get_queue(interaction.guild.id)
        songs_added = 0
        playlist_title = None
        song_to_announce = None # Store the single song if added

        try:
            # info now contains full data for playlist or single video
            info, is_playlist, is_search = await self._extract_info(query)

            if not info:
                await interaction.followup.send("Could not find anything matching your query.", ephemeral=True)
                return

            if is_playlist:
                playlist_title = info.get('title', 'Unnamed Playlist')
                log.info(f"Adding playlist '{playlist_title}' to queue for guild {interaction.guild.id}")
                entries = info.get('entries', []) # Should contain full entry info now

                if not entries:
                    await interaction.followup.send(f"Playlist '{playlist_title}' seems to be empty or could not be loaded.", ephemeral=True)
                    return

                for entry in entries:
                    if not entry: continue
                    # Extract stream URL directly from the entry info
                    stream_url = entry.get('url') # yt-dlp often provides the best stream URL here
                    if not stream_url: # Fallback to formats if needed
                        formats = entry.get('formats', [])
                        for f in formats:
                            # Prioritize opus or known good audio codecs
                            if f.get('url') and f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or f.get('acodec') == 'opus'):
                                stream_url = f['url']
                                break
                        # Last resort fallback if still no URL
                        if not stream_url and formats:
                             for f in formats:
                                 if f.get('url') and f.get('acodec') != 'none':
                                     stream_url = f['url']
                                     break

                    if not stream_url:
                        log.warning(f"Could not find playable stream URL for playlist entry: {entry.get('title', entry.get('id'))}")
                        await interaction.followup.send(f"⚠️ Could not get audio for '{entry.get('title', 'an item')}' from playlist.", ephemeral=True)
                        continue

                    try:
                        song = Song(
                            source_url=stream_url,
                            title=entry.get('title', 'Unknown Title'),
                            webpage_url=entry.get('webpage_url', entry.get('original_url')), # Use original_url as fallback
                            duration=entry.get('duration'),
                            requested_by=interaction.user
                        )
                        queue.append(song)
                        songs_added += 1
                    except Exception as song_e:
                         log.error(f"Error creating Song object for entry {entry.get('title', entry.get('id'))}: {song_e}")
                         await interaction.followup.send(f"⚠️ Error processing metadata for '{entry.get('title', 'an item')}' from playlist.", ephemeral=True)

            else: # Single video or search result
                # 'info' should be the dictionary for the single video here
                stream_url = info.get('url')
                if not stream_url: # Fallback if 'url' isn't top-level
                     formats = info.get('formats', [])
                     for f in formats:
                         # Prioritize opus or known good audio codecs
                         if f.get('url') and f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or f.get('acodec') == 'opus'):
                             stream_url = f['url']
                             break
                     # Last resort fallback if still no URL
                     if not stream_url and formats:
                          for f in formats:
                              if f.get('url') and f.get('acodec') != 'none':
                                  stream_url = f['url']
                                  break
                if not stream_url:
                     await interaction.followup.send("Could not extract a playable audio stream for the video.", ephemeral=True)
                     return

                song = Song(
                    source_url=stream_url,
                    title=info.get('title', 'Unknown Title'),
                    webpage_url=info.get('webpage_url'),
                    duration=info.get('duration'),
                    requested_by=interaction.user
                )
                queue.append(song)
                songs_added = 1
                song_to_announce = song # Store for announcement
                log.info(f"Added song '{song.title}' to queue for guild {interaction.guild.id}")

        except commands.CommandError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        except Exception as e:
            log.exception(f"Error during song processing in play command: {e}") # Log full traceback
            await interaction.followup.send("An unexpected error occurred while processing your request.", ephemeral=True)
            return

        # --- Send confirmation message ---
        if songs_added > 0:
            if is_playlist:
                await interaction.followup.send(f"✅ Added **{songs_added}** songs from playlist **'{playlist_title}'** to the queue.")
            elif song_to_announce: # Check if a single song was added
                # For single adds, show position if queue was not empty before adding
                queue_pos = len(queue) # Position is the current length (after adding)
                if vc.is_playing() or vc.is_paused() or queue_pos > 1: # If something playing or queue had items before this add
                     await interaction.followup.send(f"✅ Added **{song_to_announce.title}** to the queue (position #{queue_pos}).")
                else:
                     # If nothing was playing and queue was empty, this song will play next
                     # The loop will handle the "Now Playing" implicitly, so just confirm add
                     await interaction.followup.send(f"✅ Added **{song_to_announce.title}** to the queue.")
                     # No need to explicitly start playback here, the loop handles it.
        else:
             # This case might happen if playlist extraction failed for all entries or search failed
             if not is_playlist and is_search:
                 # If it was a search and nothing was added, the earlier message handles it
                 pass # Already sent "Could not find anything..."
             else:
                 await interaction.followup.send("Could not add any songs from the provided source.", ephemeral=True)

    async def audio_pause_callback(self, interaction: discord.Interaction):
        """Callback for /audio playback pause command"""
        vc = self.voice_clients.get(interaction.guild.id)
        if not vc or not vc.is_playing():
            await interaction.response.send_message("I am not playing anything right now.", ephemeral=True)
            return
        if vc.is_paused():
            await interaction.response.send_message("Playback is already paused.", ephemeral=True)
            return

        vc.pause()
        await interaction.response.send_message("⏸️ Playback paused.")
        log.info(f"Playback paused in guild {interaction.guild.id}")

    async def audio_resume_callback(self, interaction: discord.Interaction):
        """Callback for /audio playback resume command"""
        vc = self.voice_clients.get(interaction.guild.id)
        if not vc or not vc.is_connected():
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return
        if not vc.is_paused():
            await interaction.response.send_message("Playback is not paused.", ephemeral=True)
            return

        vc.resume()
        await interaction.response.send_message("▶️ Playback resumed.")
        log.info(f"Playback resumed in guild {interaction.guild.id}")

    async def audio_skip_callback(self, interaction: discord.Interaction):
        """Callback for /audio playback skip command"""
        vc = self.voice_clients.get(interaction.guild.id)
        if not vc or not vc.is_playing():
            await interaction.response.send_message("I am not playing anything to skip.", ephemeral=True)
            return

        current = self.get_current_song(interaction.guild.id)
        await interaction.response.send_message(f"⏭️ Skipping **{current.title if current else 'the current song'}**...")
        vc.stop() # Triggers the 'after' callback, which lets the loop play the next song
        log.info(f"Song skipped in guild {interaction.guild.id} by {interaction.user}")
        # The loop will handle playing the next song

    async def audio_stop_callback(self, interaction: discord.Interaction):
        """Callback for /audio playback stop command"""
        vc = self.voice_clients.get(interaction.guild.id)
        if not vc or not vc.is_connected():
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return

        queue = self.get_queue(interaction.guild.id)
        queue.clear()
        self.current_song[interaction.guild.id] = None # Clear current song immediately

        if vc.is_playing() or vc.is_paused():
            vc.stop() # Stop playback
            await interaction.response.send_message("⏹️ Playback stopped and queue cleared.")
            log.info(f"Playback stopped and queue cleared in guild {interaction.guild.id} by {interaction.user}")
        else:
             await interaction.response.send_message("⏹️ Queue cleared.") # If nothing was playing, just confirm queue clear
             log.info(f"Queue cleared in guild {interaction.guild.id} by {interaction.user} (nothing was playing).")

    # Queue group callbacks
    async def audio_queue_list_callback(self, interaction: discord.Interaction):
        """Callback for /audio queue list command"""
        queue = self.get_queue(interaction.guild.id)
        current = self.get_current_song(interaction.guild.id)

        if not queue and not current:
            await interaction.response.send_message("The queue is empty and nothing is playing.", ephemeral=True)
            return

        # Create an embed for the queue
        embed = discord.Embed(
            title="Music Queue",
            color=discord.Color.blue()
        )

        # Add the current song
        if current:
            embed.add_field(
                name="Now Playing",
                value=f"{current} - Requested by {current.requested_by.mention}",
                inline=False
            )

        # Add the queue
        if queue:
            queue_text = ""
            for i, song in enumerate(queue):
                queue_text += f"**{i+1}.** {song} - Requested by {song.requested_by.mention}\n"

            embed.add_field(
                name="Queue",
                value=queue_text if queue_text else "The queue is empty.",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    async def audio_queue_clear_callback(self, interaction: discord.Interaction):
        """Callback for /audio queue clear command"""
        queue = self.get_queue(interaction.guild.id)

        if not queue:
            await interaction.response.send_message("The queue is already empty.", ephemeral=True)
            return

        queue.clear()
        await interaction.response.send_message("✅ Queue cleared.")
        log.info(f"Queue cleared in guild {interaction.guild.id} by {interaction.user}")

    # --- Legacy Commands ---

    @commands.command(name="join", aliases=['connect'])
    async def join(self, ctx: commands.Context):
        """Connects the bot to your current voice channel."""
        try:
            await self._ensure_voice_connection(ctx)
            await ctx.reply(f"Connected to **{ctx.author.voice.channel.name}**.")
        except commands.CommandError as e:
            await ctx.reply(str(e))
        except Exception as e:
            log.error(f"Error in join command: {e}")
            await ctx.reply("An unexpected error occurred while trying to join.")

    @commands.command(name="leave", aliases=['disconnect', 'dc'])
    async def leave(self, ctx: commands.Context):
        """Disconnects the bot from the voice channel."""
        vc = self.voice_clients.get(ctx.guild.id)
        if not vc or not vc.is_connected():
            await ctx.reply("I am not connected to a voice channel.")
            return

        log.info(f"Disconnecting from voice channel in guild {ctx.guild.id}")
        await ctx.reply(f"Disconnecting from **{vc.channel.name}**.")
        self.cleanup(ctx.guild.id) # This handles the disconnect and queue clearing

    @commands.command(name="play", aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str):
        """Plays a song or adds it/playlist to the queue. Accepts URL or search query."""
        try:
            vc = await self._ensure_voice_connection(ctx)
        except commands.CommandError as e:
            await ctx.reply(str(e))
            return
        except Exception as e:
            log.error(f"Error ensuring voice connection in play command: {e}")
            await ctx.reply("An unexpected error occurred before playing.")
            return

        queue = self.get_queue(ctx.guild.id)
        songs_added = 0
        playlist_title = None
        song_to_announce = None # Store the single song if added

        async with ctx.typing(): # Indicate processing
            try:
                # info now contains full data for playlist or single video
                info, is_playlist, is_search = await self._extract_info(query)

                if not info:
                    await ctx.reply("Could not find anything matching your query.")
                    return

                if is_playlist:
                    playlist_title = info.get('title', 'Unnamed Playlist')
                    log.info(f"Adding playlist '{playlist_title}' to queue for guild {ctx.guild.id}")
                    entries = info.get('entries', []) # Should contain full entry info now

                    if not entries:
                        await ctx.reply(f"Playlist '{playlist_title}' seems to be empty or could not be loaded.")
                        return

                    for entry in entries:
                        if not entry: continue
                        # Extract stream URL directly from the entry info
                        stream_url = entry.get('url') # yt-dlp often provides the best stream URL here
                        if not stream_url: # Fallback to formats if needed
                            formats = entry.get('formats', [])
                            for f in formats:
                                # Prioritize opus or known good audio codecs
                                if f.get('url') and f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or f.get('acodec') == 'opus'):
                                    stream_url = f['url']
                                    break
                            # Last resort fallback if still no URL
                            if not stream_url and formats:
                                 for f in formats:
                                     if f.get('url') and f.get('acodec') != 'none':
                                         stream_url = f['url']
                                         break

                        if not stream_url:
                            log.warning(f"Could not find playable stream URL for playlist entry: {entry.get('title', entry.get('id'))}")
                            await ctx.send(f"⚠️ Could not get audio for '{entry.get('title', 'an item')}' from playlist.", delete_after=15)
                            continue

                        try:
                            song = Song(
                                source_url=stream_url,
                                title=entry.get('title', 'Unknown Title'),
                                webpage_url=entry.get('webpage_url', entry.get('original_url')), # Use original_url as fallback
                                duration=entry.get('duration'),
                                requested_by=ctx.author
                            )
                            queue.append(song)
                            songs_added += 1
                        except Exception as song_e:
                             log.error(f"Error creating Song object for entry {entry.get('title', entry.get('id'))}: {song_e}")
                             await ctx.send(f"⚠️ Error processing metadata for '{entry.get('title', 'an item')}' from playlist.", delete_after=15)

                else: # Single video or search result
                    # 'info' should be the dictionary for the single video here
                    stream_url = info.get('url')
                    if not stream_url: # Fallback if 'url' isn't top-level
                         formats = info.get('formats', [])
                         for f in formats:
                             # Prioritize opus or known good audio codecs
                             if f.get('url') and f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or f.get('acodec') == 'opus'):
                                 stream_url = f['url']
                                 break
                         # Last resort fallback if still no URL
                         if not stream_url and formats:
                              for f in formats:
                                  if f.get('url') and f.get('acodec') != 'none':
                                      stream_url = f['url']
                                      break
                    if not stream_url:
                         await ctx.reply("Could not extract a playable audio stream for the video.")
                         return

                    song = Song(
                        source_url=stream_url,
                        title=info.get('title', 'Unknown Title'),
                        webpage_url=info.get('webpage_url'),
                        duration=info.get('duration'),
                        requested_by=ctx.author
                    )
                    queue.append(song)
                    songs_added = 1
                    song_to_announce = song # Store for announcement
                    log.info(f"Added song '{song.title}' to queue for guild {ctx.guild.id}")

            except commands.CommandError as e:
                await ctx.reply(str(e))
                return
            except Exception as e:
                log.exception(f"Error during song processing in play command: {e}") # Log full traceback
                await ctx.reply("An unexpected error occurred while processing your request.")
                return

        # --- Send confirmation message ---
        if songs_added > 0:
            if is_playlist:
                await ctx.reply(f"✅ Added **{songs_added}** songs from playlist **'{playlist_title}'** to the queue.")
            elif song_to_announce: # Check if a single song was added
                # For single adds, show position if queue was not empty before adding
                queue_pos = len(queue) # Position is the current length (after adding)
                if vc.is_playing() or vc.is_paused() or queue_pos > 1: # If something playing or queue had items before this add
                     await ctx.reply(f"✅ Added **{song_to_announce.title}** to the queue (position #{queue_pos}).")
                else:
                     # If nothing was playing and queue was empty, this song will play next
                     # The loop will handle the "Now Playing" implicitly, so just confirm add
                     await ctx.reply(f"✅ Added **{song_to_announce.title}** to the queue.")
                     # No need to explicitly start playback here, the loop handles it.
        else:
             # This case might happen if playlist extraction failed for all entries or search failed
             if not is_playlist and is_search:
                 # If it was a search and nothing was added, the earlier message handles it
                 pass # Already sent "Could not find anything..."
             else:
                 await ctx.reply("Could not add any songs from the provided source.")

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context):
        """Pauses the current playback."""
        vc = self.voice_clients.get(ctx.guild.id)
        if not vc or not vc.is_playing():
            await ctx.reply("I am not playing anything right now.")
            return
        if vc.is_paused():
            await ctx.reply("Playback is already paused.")
            return

        vc.pause()
        await ctx.reply("⏸️ Playback paused.")
        log.info(f"Playback paused in guild {ctx.guild.id}")

    @commands.command(name="resume")
    async def resume(self, ctx: commands.Context):
        """Resumes paused playback."""
        vc = self.voice_clients.get(ctx.guild.id)
        if not vc or not vc.is_connected():
            await ctx.reply("I am not connected to a voice channel.")
            return
        if not vc.is_paused():
            await ctx.reply("Playback is not paused.")
            return

        vc.resume()
        await ctx.reply("▶️ Playback resumed.")
        log.info(f"Playback resumed in guild {ctx.guild.id}")

    @commands.command(name="skip", aliases=['s'])
    async def skip(self, ctx: commands.Context):
        """Skips the current song."""
        vc = self.voice_clients.get(ctx.guild.id)
        if not vc or not vc.is_playing():
            await ctx.reply("I am not playing anything to skip.")
            return

        current = self.get_current_song(ctx.guild.id)
        await ctx.reply(f"⏭️ Skipping **{current.title if current else 'the current song'}**...")
        vc.stop() # Triggers the 'after' callback, which lets the loop play the next song
        log.info(f"Song skipped in guild {ctx.guild.id} by {ctx.author}")
        # The loop will handle playing the next song

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        """Stops playback and clears the queue."""
        vc = self.voice_clients.get(ctx.guild.id)
        if not vc or not vc.is_connected():
            await ctx.reply("I am not connected to a voice channel.")
            return

        queue = self.get_queue(ctx.guild.id)
        queue.clear()
        self.current_song[ctx.guild.id] = None # Clear current song immediately

        if vc.is_playing() or vc.is_paused():
            vc.stop() # Stop playback
            await ctx.reply("⏹️ Playback stopped and queue cleared.")
            log.info(f"Playback stopped and queue cleared in guild {ctx.guild.id} by {ctx.author}")
        else:
             await ctx.reply("⏹️ Queue cleared.") # If nothing was playing, just confirm queue clear
             log.info(f"Queue cleared in guild {ctx.guild.id} by {ctx.author} (nothing was playing).")

    @commands.command(name="queue", aliases=['q'])
    async def queue(self, ctx: commands.Context):
        """Displays the current song queue."""
        queue = self.get_queue(ctx.guild.id)
        current = self.get_current_song(ctx.guild.id)

        if not queue and not current:
            await ctx.reply("The queue is empty and nothing is playing.")
            return

        embed = discord.Embed(title="Music Queue", color=discord.Color.blue())
        if current:
             embed.add_field(name="Now Playing", value=f"[{current.title}]({current.webpage_url}) | `{current.format_duration()}` | Requested by {current.requested_by.mention}", inline=False)
        else:
             embed.add_field(name="Now Playing", value="Nothing currently playing.", inline=False)

        if queue:
            queue_list = []
            max_display = 10 # Limit display to avoid huge embeds
            for i, song in enumerate(list(queue)[:max_display]):
                queue_list.append(f"`{i+1}.` [{song.title}]({song.webpage_url}) | `{song.format_duration()}` | Req by {song.requested_by.mention}")

            if queue_list:
                 embed.add_field(name="Up Next", value="\n".join(queue_list), inline=False)

            if len(queue) > max_display:
                embed.set_footer(text=f"... and {len(queue) - max_display} more songs.")
        else:
            embed.add_field(name="Up Next", value="The queue is empty.", inline=False)

        await ctx.reply(embed=embed)

    @commands.command(name="nowplaying", aliases=['np', 'current'])
    async def nowplaying(self, ctx: commands.Context):
        """Shows the currently playing song."""
        current = self.get_current_song(ctx.guild.id)
        vc = self.voice_clients.get(ctx.guild.id)

        if not vc or not vc.is_connected():
             await ctx.reply("I'm not connected to a voice channel.")
             return

        if not current or not (vc.is_playing() or vc.is_paused()):
            await ctx.reply("Nothing is currently playing.")
            return

        embed = discord.Embed(title="Now Playing", description=f"[{current.title}]({current.webpage_url})", color=discord.Color.green())
        embed.add_field(name="Duration", value=f"`{current.format_duration()}`", inline=True)
        embed.add_field(name="Requested by", value=current.requested_by.mention, inline=True)
        # Add progress bar if possible (requires tracking start time)
        # progress = ...
        # embed.add_field(name="Progress", value=progress, inline=False)
        if hasattr(current, 'thumbnail') and current.thumbnail: # Check if thumbnail exists
             embed.set_thumbnail(url=current.thumbnail)

        await ctx.reply(embed=embed)

    # --- Search Command and View ---

    @commands.command(name="search")
    async def search(self, ctx: commands.Context, *, query: str):
        """Searches YouTube and displays results with selection buttons."""
        if not ctx.guild:
            await ctx.reply("This command can only be used in a server.")
            return

        # Store the initial message to edit later
        message = await ctx.reply(f"Searching for '{query}'...")

        async with ctx.typing(): # Keep typing indicator while searching
            try:
                # Fetch more results for pagination
                results = await self._search_youtube(query, max_results=15)
            except Exception as e:
                log.error(f"Error during YouTube search: {e}")
                await message.edit(content="An error occurred while searching.", view=None)
                return

            if not results:
                await message.edit(content=f"No results found for '{query}'.", view=None)
                return

        # Prepare data for the view
        search_results_data = []
        for entry in results:
            # Store necessary info for adding to queue later
             search_results_data.append({
                 'title': entry.get('title', 'Unknown Title'),
                 'webpage_url': entry.get('webpage_url'),
                 'duration': entry.get('duration'),
                 'id': entry.get('id'), # Need ID to re-fetch stream URL later
                 'uploader': entry.get('uploader', 'Unknown Uploader')
             })

        # Create the view with pagination
        view = PaginatedSearchResultView(ctx.author, search_results_data, self, query) # Pass query for title
        view.interaction_message = message # Store message reference in the view
        # Initial update of the message with the first page
        await view.update_message(interaction=None) # Use interaction=None for initial send/edit


    @staticmethod
    def format_duration_static(duration):
        """Static version of format_duration for use outside Song objects."""
        if not duration:
            return "N/A"
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    # Error Handling for Audio Cog specifically
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # Handle errors specific to this cog, prevents double messages if global handler exists
        if isinstance(error, commands.CommandError) and ctx.cog == self:
            # Check if the error is specific to commands in this cog
            # Avoid handling errors already handled locally in commands if possible
            # This basic check just prevents duplicate generic messages
            log.warning(f"Command error in AudioCog: {error}")
            # await ctx.reply(f"An error occurred: {error}") # Optional: Send specific cog errors
            # Return True or pass to prevent global handler if needed
            # pass # Let global handler take care of it unless specific handling is needed

async def setup(bot):
    """Set up the AudioCog with the bot."""
    print("Setting up AudioCog...")
    cog = AudioCog(bot)
    await bot.add_cog(cog)
    print(f"AudioCog setup complete with command groups: {[cmd.name for cmd in bot.tree.get_commands() if cmd.name == 'audio']}")
    print(f"Available subgroups: {[group.name for group in cog.audio_group.walk_commands() if isinstance(group, app_commands.Group)]}")
    log.info("AudioCog loaded successfully.")

# --- Paginated Search Result View ---

class PaginatedSearchResultView(ui.View):
    RESULTS_PER_PAGE = 5

    def __init__(self, author: discord.Member, results: list, cog: AudioCog, query: str, timeout=180.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.results = results
        self.cog = cog
        self.query = query # Store original query for embed title
        self.current_page = 0
        self.total_pages = math.ceil(len(self.results) / self.RESULTS_PER_PAGE)
        self.interaction_message: discord.Message = None # To disable view later

        self.update_buttons() # Initial button setup

    def update_buttons(self):
        """Clears and adds buttons based on the current page and total results."""
        self.clear_items()
        start_index = self.current_page * self.RESULTS_PER_PAGE
        end_index = min(start_index + self.RESULTS_PER_PAGE, len(self.results))

        # Add result selection buttons for the current page
        for i in range(start_index, end_index):
            result = self.results[i]
            button = ui.Button(
                label=f"{i+1}", # Overall result number
                style=discord.ButtonStyle.secondary,
                custom_id=f"search_select_{i}",
                row= (i - start_index) // 5 # Arrange buttons neatly if more than 5 per page (though we limit to 5)
            )
            # Use lambda to capture the correct index 'i'
            button.callback = lambda interaction, index=i: self.select_button_callback(interaction, index)
            self.add_item(button)

        # Add navigation buttons (Previous/Next) - ensure they are on the last row
        nav_row = math.ceil(self.RESULTS_PER_PAGE / 5) # Calculate row for nav buttons
        if self.total_pages > 1:
            prev_button = ui.Button(label="◀ Previous", style=discord.ButtonStyle.primary, custom_id="search_prev", disabled=self.current_page == 0, row=nav_row)
            prev_button.callback = self.prev_button_callback
            self.add_item(prev_button)

            next_button = ui.Button(label="Next ▶", style=discord.ButtonStyle.primary, custom_id="search_next", disabled=self.current_page == self.total_pages - 1, row=nav_row)
            next_button.callback = self.next_button_callback
            self.add_item(next_button)

    def create_embed(self) -> discord.Embed:
        """Creates the embed for the current page."""
        embed = discord.Embed(
            title=f"Search Results for '{self.query}' (Page {self.current_page + 1}/{self.total_pages})",
            description="Click a button below to add the song to the queue.",
            color=discord.Color.purple()
        )

        start_index = self.current_page * self.RESULTS_PER_PAGE
        end_index = min(start_index + self.RESULTS_PER_PAGE, len(self.results))

        if start_index >= len(self.results): # Should not happen with proper page clamping
             embed.description = "No results on this page."
             return embed

        for i in range(start_index, end_index):
            entry = self.results[i]
            title = entry.get('title', 'Unknown Title')
            url = entry.get('webpage_url')
            duration_sec = entry.get('duration')
            duration_fmt = self.cog.format_duration_static(duration_sec) if duration_sec else "N/A" # Use cog's static method
            uploader = entry.get('uploader', 'Unknown Uploader')

            embed.add_field(
                name=f"{i+1}. {title}", # Use overall index + 1 for label
                value=f"[{uploader}]({url}) | `{duration_fmt}`",
                inline=False
            )

        embed.set_footer(text=f"Showing results {start_index + 1}-{end_index} of {len(self.results)}")
        return embed

    async def update_message(self, interaction: discord.Interaction = None):
        """Updates the message with the current page's embed and buttons."""
        self.update_buttons()
        embed = self.create_embed()
        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.interaction_message: # For initial send/edit
             await self.interaction_message.edit(content=None, embed=embed, view=self) # Remove "Searching..." text

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the original command author to interact
        if interaction.user != self.author:
            await interaction.response.send_message("Only the person who started the search can interact with this.", ephemeral=True)
            return False
        return True

    async def select_button_callback(self, interaction: discord.Interaction, index: int):
        """Callback when a result selection button is pressed."""
        if not interaction.guild: return

        selected_result = self.results[index]
        log.info(f"Search result {index+1} ('{selected_result['title']}') selected by {interaction.user} in guild {interaction.guild.id}")

        # Defer the interaction
        await interaction.response.defer()

        # Disable all buttons in the view after selection
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        # Update the original message to show disabled buttons and confirmation
        final_embed = self.create_embed() # Get current embed state
        final_embed.description = f"Selected: **{selected_result['title']}**. Adding to queue..."
        final_embed.color = discord.Color.green()
        await interaction.edit_original_response(embed=final_embed, view=self)
        self.stop() # Stop the view from listening further

        # --- Add the selected song to the queue ---
        try:
            # Ensure bot is connected to voice (use interaction here)
            vc = await self.cog._ensure_voice_connection(interaction)
            if not vc:
                 log.error("Failed to ensure voice connection in search callback.")
                 await interaction.followup.send("Could not connect to voice channel.", ephemeral=True)
                 return

            queue = self.cog.get_queue(interaction.guild.id)

            # Re-fetch the stream URL
            try:
                 query_for_stream = selected_result.get('webpage_url') or selected_result.get('id')
                 if not query_for_stream:
                     raise commands.CommandError("Missing video identifier for selected result.")

                 info, _, _ = await self.cog._extract_info(query_for_stream)
                 if not info:
                     raise commands.CommandError("Could not retrieve details for the selected video.")

                 stream_url = info.get('url')
                 if not stream_url:
                     formats = info.get('formats', [])
                     for f in formats:
                         if f.get('url') and f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or f.get('acodec') == 'opus'):
                             stream_url = f['url']
                             break
                     if not stream_url and formats:
                         for f in formats:
                             if f.get('url') and f.get('acodec') != 'none':
                                 stream_url = f['url']
                                 break
                 if not stream_url:
                     raise commands.CommandError("Could not extract a playable audio stream.")

                 song = Song(
                     source_url=stream_url,
                     title=info.get('title', selected_result.get('title', 'Unknown Title')),
                     webpage_url=info.get('webpage_url', selected_result.get('webpage_url')),
                     duration=info.get('duration', selected_result.get('duration')),
                     requested_by=interaction.user
                 )
                 queue.append(song)
                 log.info(f"Added search result '{song.title}' to queue for guild {interaction.guild.id}")

                 # Send confirmation followup
                 queue_pos = len(queue)
                 if vc.is_playing() or vc.is_paused() or queue_pos > 1:
                     await interaction.followup.send(f"✅ Added **{song.title}** to the queue (position #{queue_pos}).")
                 else:
                     await interaction.followup.send(f"✅ Added **{song.title}** to the queue.")

            except commands.CommandError as e:
                 log.error(f"Error adding search result to queue: {e}")
                 await interaction.followup.send(f"Error adding song: {e}", ephemeral=True)
            except Exception as e:
                 log.exception(f"Unexpected error adding search result to queue: {e}")
                 await interaction.followup.send("An unexpected error occurred while adding the song.", ephemeral=True)

        except commands.CommandError as e:
             await interaction.followup.send(str(e), ephemeral=True)
        except Exception as e:
             log.exception(f"Unexpected error in search select callback: {e}")
             await interaction.followup.send("An unexpected error occurred.", ephemeral=True)

    async def prev_button_callback(self, interaction: discord.Interaction):
        """Callback for the previous page button."""
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)

    async def next_button_callback(self, interaction: discord.Interaction):
        """Callback for the next page button."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)

    async def on_timeout(self):
        # Disable buttons on timeout
        log.info(f"Paginated search view timed out for user {self.author.id}")
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        # Try to edit the original message
        if self.interaction_message:
            try:
                # Keep the last viewed embed but indicate timeout
                timeout_embed = self.create_embed()
                timeout_embed.description = "Search selection timed out."
                timeout_embed.color = discord.Color.default() # Reset color
                await self.interaction_message.edit(embed=timeout_embed, view=self)
            except discord.NotFound:
                log.warning("Original search message not found on timeout.")
            except discord.Forbidden:
                 log.warning("Missing permissions to edit search message on timeout.")
            except Exception as e:
                 log.error(f"Error editing search message on timeout: {e}")

    # Override on_error if specific error handling for the view is needed
    # async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
    #     log.error(f"Error in PaginatedSearchResultView interaction: {error}")
    #     await interaction.response.send_message("An error occurred with this interaction.", ephemeral=True)
