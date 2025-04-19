import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import random
import json
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont
import math
import wave
import struct
import glob
import shutil
import sys

class JSON:
    def read(file):
        with open(f"{file}.json", "r", encoding="utf8") as file:
            data = json.load(file, strict=False)
        return data

    def dump(file, data):
        with open(f"{file}.json", "w", encoding="utf8") as file:
            json.dump(data, file, indent=4)

class WebdriverTorsoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = "config"
        self.is_processing = False
        
        # Create directories if they don't exist
        for directory in ["IMG", "SOUND", "OUTPUT", "FONT"]:
            os.makedirs(directory, exist_ok=True)

    async def _generate_video_logic(self, ctx_or_interaction, slides=None, shapes=None, duration=None, tts_text=None):
        """Core logic for the webdrivertorso command."""
        # Check if already processing a video
        if self.is_processing:
            return "⚠️ Already processing a video. Please wait for the current process to complete."
        
        self.is_processing = True
        
        try:
            # Load config
            try:
                config_data = JSON.read(self.config_file)
            except Exception as e:
                return f"❌ Error loading config: {str(e)}"
            
            # Override config with parameters if provided
            if slides is not None:
                config_data["SLIDES"] = slides
            if shapes is not None:
                config_data["MIN_SHAPES"] = shapes
                config_data["MAX_SHAPES"] = shapes + 5
            if duration is not None:
                config_data["SLIDE_DURATION"] = duration
            if tts_text is not None:
                config_data["TTS_TEXT"] = tts_text
                config_data["TTS_ENABLED"] = True
            
            # Clean directories
            for directory in ["IMG", "SOUND"]:
                for file in glob.glob(f'./{directory}/*'):
                    try:
                        os.remove(file)
                    except Exception as e:
                        print(f"Error removing file {file}: {e}")
            
            # Create a temporary script file
            script_path = os.path.join(tempfile.gettempdir(), "webdrivertorso_temp.py")
            with open("EXAMPLE.py", "r", encoding="utf8") as f:
                script_content = f.read()
            
            with open(script_path, "w", encoding="utf8") as f:
                f.write(script_content)
            
            # Run the script as a subprocess
            process = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send initial message
            if isinstance(ctx_or_interaction, commands.Context):
                message = await ctx_or_interaction.reply("🎬 Generating Webdriver Torso style video... This may take a minute.")
            else:  # It's an Interaction
                await ctx_or_interaction.response.send_message("🎬 Generating Webdriver Torso style video... This may take a minute.")
                message = await ctx_or_interaction.original_response()
            
            # Wait for the process to complete
            stdout, stderr = await process.communicate()
            
            # Check if the process was successful
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                return f"❌ Error generating video: {error_msg}"
            
            # Find the generated video file
            video_files = glob.glob('./OUTPUT/*.mp4')
            if not video_files:
                return "❌ No video files were generated."
            
            # Get the most recent video file
            video_file = max(video_files, key=os.path.getctime)
            
            # Send the video file
            if isinstance(ctx_or_interaction, commands.Context):
                await ctx_or_interaction.reply(file=discord.File(video_file))
            else:  # It's an Interaction
                await ctx_or_interaction.followup.send(file=discord.File(video_file))
            
            return f"✅ Video generated successfully: {os.path.basename(video_file)}"
            
        except Exception as e:
            return f"❌ An error occurred: {str(e)}"
        finally:
            self.is_processing = False

    # --- Prefix Command ---
    @commands.command(name="webdrivertorso")
    async def webdrivertorso(self, ctx, slides: int = None, shapes: int = None, duration: int = None, *, tts_text: str = None):
        """Generate a Webdriver Torso style test video.
        
        Parameters:
        - slides: Number of slides in the video (default: 10)
        - shapes: Minimum number of shapes per slide (default: 5)
        - duration: Duration of each slide in milliseconds (default: 1000)
        - tts_text: Text to be spoken in the video (default: None)
        """
        async with ctx.typing():
            result = await self._generate_video_logic(ctx, slides, shapes, duration, tts_text)
        
        if isinstance(result, str):
            await ctx.reply(result)

    # --- Slash Command ---
    @app_commands.command(name="webdrivertorso", description="Generate a Webdriver Torso style test video")
    @app_commands.describe(
        slides="Number of slides in the video (default: 10)",
        shapes="Minimum number of shapes per slide (default: 5)",
        duration="Duration of each slide in milliseconds (default: 1000)",
        tts_text="Text to be spoken in the video"
    )
    async def webdrivertorso_slash(self, interaction: discord.Interaction, 
                                  slides: int = None, 
                                  shapes: int = None, 
                                  duration: int = None, 
                                  tts_text: str = None):
        """Slash command version of webdrivertorso."""
        await interaction.response.defer()
        result = await self._generate_video_logic(interaction, slides, shapes, duration, tts_text)
        
        if isinstance(result, str):
            await interaction.followup.send(result)

async def setup(bot: commands.Bot):
    await bot.add_cog(WebdriverTorsoCog(bot))
