import discord
import traceback
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

    # --- Prefix Command for Listing Servers ---
    @commands.command(name="listservers")
    @commands.is_owner()
    async def list_servers(self, ctx: commands.Context):
        """Lists all servers the bot is in (Owner only)"""
        await self._send_server_list(ctx.reply)

    # --- Slash Command for Listing Servers ---
    @app_commands.command(name="listservers", description="Lists all servers the bot is in (Owner only)")
    async def list_servers_slash(self, interaction: discord.Interaction):
        """Slash command version of list_servers."""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("This command can only be used by the bot owner.", ephemeral=True)
            return
        # Defer response as gathering info might take time
        await interaction.response.defer(ephemeral=True)
        await self._send_server_list(interaction.followup.send)

    async def _send_server_list(self, send_func):
        """Helper function to gather server info and send the list."""
        guilds = self.bot.guilds
        server_list_text = []
        max_embed_desc_length = 4096 # Discord embed description limit
        current_length = 0

        embeds = []

        for guild in guilds:
            invite_link = "N/A"
            try:
                # Try system channel first
                if guild.system_channel and guild.system_channel.permissions_for(guild.me).create_instant_invite:
                    invite = await guild.system_channel.create_invite(max_age=3600, max_uses=1, unique=True, reason="Owner server list request")
                    invite_link = invite.url
                else:
                    # Fallback to the first channel the bot can create an invite in
                    for channel in guild.text_channels:
                        if channel.permissions_for(guild.me).create_instant_invite:
                            invite = await channel.create_invite(max_age=3600, max_uses=1, unique=True, reason="Owner server list request")
                            invite_link = invite.url
                            break
                    else: # No suitable channel found
                        invite_link = "No invite permission"
            except discord.Forbidden:
                invite_link = "No invite permission"
            except Exception as e:
                invite_link = f"Error: {type(e).__name__}"
                print(f"Error creating invite for guild {guild.id} ({guild.name}):")
                traceback.print_exc()

            owner_info = f"{guild.owner} ({guild.owner_id})" if guild.owner else f"ID: {guild.owner_id}"
            server_info = (
                f"**{guild.name}** (ID: {guild.id})\n"
                f"- Members: {guild.member_count}\n"
                f"- Owner: {owner_info}\n"
                f"- Invite (1h/1use): {invite_link}\n\n"
            )

            # Check if adding this server exceeds the limit for the current embed
            if current_length + len(server_info) > max_embed_desc_length:
                # Finalize the current embed
                embed = discord.Embed(title=f"Server List (Part {len(embeds) + 1})", description="".join(server_list_text), color=discord.Color.blue())
                embeds.append(embed)
                # Start a new embed description
                server_list_text = [server_info]
                current_length = len(server_info)
            else:
                server_list_text.append(server_info)
                current_length += len(server_info)

        # Add the last embed if there's remaining text
        if server_list_text:
            embed = discord.Embed(title=f"Server List (Part {len(embeds) + 1})", description="".join(server_list_text), color=discord.Color.blue())
            embeds.append(embed)

        if not embeds:
            await send_func("Bot is not in any servers.", ephemeral=True)
            return

        # Send the embeds
        first = True
        for embed in embeds:
            if first:
                await send_func(embed=embed, ephemeral=True)
                first = False
            else:
                # Subsequent embeds need to be sent differently depending on context
                # For prefix commands, just send another message
                # For interactions, use followup.send
                # This implementation assumes send_func handles this correctly (ctx.reply vs interaction.followup.send)
                 await send_func(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    # Ensure owner_id is set, needed for slash command check
    # This might already be handled when the bot is initialized, but good to be sure
    if not bot.owner_id:
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id
        print(f"Fetched and set bot owner ID: {bot.owner_id}")

    await bot.add_cog(StatusCog(bot))
    print("StatusCog loaded successfully!")
