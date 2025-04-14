import os
import discord
from discord.ext import commands
from discord import app_commands
import random as random_module
import typing # Need this for Optional

# Cache to store uploaded file URLs (local to this cog)
file_url_cache = {}

class RandomCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Updated _random_logic
    async def _random_logic(self, interaction_or_ctx, hidden: bool = False) -> typing.Optional[str]:
        """Core logic for the random command. Returns an error message string or None if successful."""
        # NSFW Check
        is_nsfw_channel = False
        channel = interaction_or_ctx.channel
        if isinstance(channel, discord.TextChannel) and channel.is_nsfw():
            is_nsfw_channel = True
        elif isinstance(channel, discord.DMChannel): # DMs are considered NSFW for this purpose
            is_nsfw_channel = True

        if not is_nsfw_channel:
            # Return error message directly, ephemeral handled by caller
            return 'This command can only be used in age-restricted (NSFW) channels or DMs.'

        directory = os.getenv('UPLOAD_DIRECTORY')
        if not directory:
            return 'UPLOAD_DIRECTORY is not set in the .env file.'
        if not os.path.isdir(directory):
            return 'The specified UPLOAD_DIRECTORY does not exist or is not a directory.'

        files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
        if not files:
            return 'The specified directory is empty.'

        # Attempt to send a random file, handling potential size issues
        original_files = list(files) # Copy for checking if all files failed
        while files:
            chosen_file_name = random_module.choice(files)
            file_path = os.path.join(directory, chosen_file_name)

            # Check cache first
            if chosen_file_name in file_url_cache:
                # For interactions, defer if not already done, using the hidden flag
                if not isinstance(interaction_or_ctx, commands.Context) and not interaction_or_ctx.response.is_done():
                     await interaction_or_ctx.response.defer(ephemeral=hidden) # Defer before sending cached URL
                # Send cached URL
                if isinstance(interaction_or_ctx, commands.Context):
                    await interaction_or_ctx.reply(file_url_cache[chosen_file_name]) # Prefix commands can't be ephemeral
                else:
                    await interaction_or_ctx.followup.send(file_url_cache[chosen_file_name], ephemeral=hidden)
                return None # Indicate success

            try:
                # Determine how to send the file based on context/interaction
                if isinstance(interaction_or_ctx, commands.Context):
                    message = await interaction_or_ctx.reply(file=discord.File(file_path)) # Use reply for context
                else: # It's an interaction
                    # Interactions need followup for files after defer()
                    if not interaction_or_ctx.response.is_done():
                        await interaction_or_ctx.response.defer(ephemeral=hidden) # Defer before sending file
                    # Send file ephemerally if hidden is True
                    message = await interaction_or_ctx.followup.send(file=discord.File(file_path), ephemeral=hidden)

                # Cache the URL if successfully sent
                if message and message.attachments:
                    file_url_cache[chosen_file_name] = message.attachments[0].url
                    # Success, no further message needed
                    return None
                else:
                     # Should not happen if send succeeded, but handle defensively
                     files.remove(chosen_file_name)
                     print(f"Warning: File {chosen_file_name} sent but no attachment URL found.") # Log warning
                     continue

            except discord.HTTPException as e:
                if e.code == 40005:  # Request entity too large
                    print(f"File too large: {chosen_file_name}")
                    files.remove(chosen_file_name)
                    continue # Try another file
                else:
                    print(f"HTTP Error sending file: {e}")
                    # Return error message directly, ephemeral handled by caller
                    return f'Failed to upload the file due to an HTTP error: {e}'
            except Exception as e:
                print(f"Generic Error sending file: {e}")
                # Return error message directly, ephemeral handled by caller
                return f'An unexpected error occurred while uploading the file: {e}'

        # If loop finishes without returning/sending, all files were too large
        # Return error message directly, ephemeral handled by caller
        return 'All files in the directory were too large to upload.'

    # --- Prefix Command ---
    @commands.command(name="random")
    async def random(self, ctx: commands.Context):
        """Upload a random NSFW image from the configured directory."""
        # Call _random_logic, hidden is False by default and irrelevant for prefix
        response = await self._random_logic(ctx)
        if response is not None:
            await ctx.reply(response)

    # --- Slash Command ---
    # Updated signature and logic
    @app_commands.command(name="random", description="Upload a random NSFW image from the configured directory")
    @app_commands.describe(hidden="Set to True to make the response visible only to you (default: False)")
    async def random_slash(self, interaction: discord.Interaction, hidden: bool = False):
        """Slash command version of random."""
        # Pass hidden parameter to logic
        response = await self._random_logic(interaction, hidden=hidden)
        # If response is None, the logic already sent the file via followup/deferral

        if response is not None: # An error occurred
            # Ensure interaction hasn't already been responded to or deferred
            if not interaction.response.is_done():
                # Send error message ephemerally if hidden is True OR if it's the NSFW channel error
                ephemeral_error = hidden or response.startswith('This command can only be used')
                await interaction.response.send_message(response, ephemeral=ephemeral_error)
            else:
                # If deferred, use followup. Send ephemerally based on hidden flag.
                await interaction.followup.send(response, ephemeral=hidden)

async def setup(bot):
    await bot.add_cog(RandomCog(bot))
