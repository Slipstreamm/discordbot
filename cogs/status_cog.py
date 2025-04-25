import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal

class StatusCog(commands.Cog):
    """Commands for managing the bot's status"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    async def _set_status_logic(self, 
                               status_type: Literal["playing", "listening", "streaming", "watching", "competing"], 
                               status_text: str,
                               stream_url: Optional[str] = None) -> str:
        """Core logic for setting the bot's status"""
        
        # Map the status type to the appropriate ActivityType
        activity_types = {
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "streaming": discord.ActivityType.streaming,
            "watching": discord.ActivityType.watching,
            "competing": discord.ActivityType.competing
        }
        
        activity_type = activity_types.get(status_type.lower())
        
        if not activity_type:
            return f"Invalid status type: {status_type}. Valid types are: playing, listening, streaming, watching, competing."
        
        try:
            # For streaming status, we need a URL
            if status_type.lower() == "streaming" and stream_url:
                await self.bot.change_presence(activity=discord.Streaming(name=status_text, url=stream_url))
            else:
                await self.bot.change_presence(activity=discord.Activity(type=activity_type, name=status_text))
                
            return f"Status set to: {status_type.capitalize()} {status_text}"
        except Exception as e:
            return f"Error setting status: {str(e)}"
    
    # --- Prefix Command ---
    @commands.command(name="setstatus")
    @commands.is_owner()
    async def set_status(self, ctx: commands.Context, status_type: str, *, status_text: str):
        """Set the bot's status (Owner only)
        
        Valid status types:
        - playing
        - listening
        - streaming (requires a URL in the status text)
        - watching
        - competing
        
        Example:
        !setstatus playing Minecraft
        !setstatus listening to music
        !setstatus streaming https://twitch.tv/username Stream Title
        !setstatus watching YouTube
        !setstatus competing in a tournament
        """
        # For streaming status, extract the URL from the status text
        stream_url = None
        if status_type.lower() == "streaming":
            parts = status_text.split()
            if len(parts) >= 2 and (parts[0].startswith("http://") or parts[0].startswith("https://")):
                stream_url = parts[0]
                status_text = " ".join(parts[1:])
        
        response = await self._set_status_logic(status_type, status_text, stream_url)
        await ctx.reply(response)
    
    # --- Slash Command ---
    @app_commands.command(name="setstatus", description="Set the bot's status")
    @app_commands.describe(
        status_type="The type of status to set",
        status_text="The text to display in the status",
        stream_url="URL for streaming status (only required for streaming status)"
    )
    @app_commands.choices(status_type=[
        app_commands.Choice(name="Playing", value="playing"),
        app_commands.Choice(name="Listening", value="listening"),
        app_commands.Choice(name="Streaming", value="streaming"),
        app_commands.Choice(name="Watching", value="watching"),
        app_commands.Choice(name="Competing", value="competing")
    ])
    async def set_status_slash(self, 
                              interaction: discord.Interaction, 
                              status_type: str,
                              status_text: str,
                              stream_url: Optional[str] = None):
        """Slash command version of set_status."""
        # Check if user is the bot owner
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("This command can only be used by the bot owner.", ephemeral=True)
            return
            
        response = await self._set_status_logic(status_type, status_text, stream_url)
        await interaction.response.send_message(response)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatusCog(bot))
    print("StatusCog loaded successfully!")
