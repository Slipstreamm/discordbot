import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import json
import tempfile
import glob
import sys
import importlib.util

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

    async def _generate_video_logic(self, ctx_or_interaction, width=None, height=None, max_width=None, max_height=None,
                                min_width=None, min_height=None, slides=None, videos=None, min_shapes=None, max_shapes=None,
                                sound_quality=None, tts_enabled=None, tts_text=None, tts_provider=None, audio_wave_type=None, slide_duration=None,
                                deform_level=None, color_mode=None, color_scheme=None, solid_color=None, allowed_shapes=None,
                                wave_vibe=None, top_left_text_enabled=None, top_left_text_mode=None, words_topic=None,
                                text_color=None, text_size=None, text_position=None, already_deferred=False):
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
            if width is not None:
                config_data["WIDTH"] = width
            if height is not None:
                config_data["HEIGHT"] = height
            if max_width is not None:
                config_data["MAX_WIDTH"] = max_width
            if max_height is not None:
                config_data["MAX_HEIGHT"] = max_height
            if min_width is not None:
                config_data["MIN_WIDTH"] = min_width
            if min_height is not None:
                config_data["MIN_HEIGHT"] = min_height
            if slides is not None:
                config_data["SLIDES"] = slides
            if videos is not None:
                config_data["VIDEOS"] = videos
            if min_shapes is not None:
                config_data["MIN_SHAPES"] = min_shapes
            if max_shapes is not None:
                config_data["MAX_SHAPES"] = max_shapes
            if sound_quality is not None:
                config_data["SOUND_QUALITY"] = sound_quality
            if tts_enabled is not None:
                config_data["TTS_ENABLED"] = tts_enabled
            if tts_text is not None:
                config_data["TTS_TEXT"] = tts_text
                if tts_enabled is None:  # Only set to True if not explicitly set to False
                    config_data["TTS_ENABLED"] = True
            if tts_provider is not None:
                config_data["TTS_PROVIDER"] = tts_provider
            if audio_wave_type is not None:
                config_data["AUDIO_WAVE_TYPE"] = audio_wave_type
            if slide_duration is not None:
                config_data["SLIDE_DURATION"] = slide_duration
            if deform_level is not None:
                config_data["DEFORM_LEVEL"] = deform_level
            if color_mode is not None:
                config_data["COLOR_MODE"] = color_mode
            if color_scheme is not None:
                config_data["COLOR_SCHEME"] = color_scheme
            if solid_color is not None:
                config_data["SOLID_COLOR"] = solid_color
            if allowed_shapes is not None:
                config_data["ALLOWED_SHAPES"] = allowed_shapes
            if wave_vibe is not None:
                config_data["WAVE_VIBE"] = wave_vibe
            if top_left_text_enabled is not None:
                config_data["TOP_LEFT_TEXT_ENABLED"] = top_left_text_enabled
            if top_left_text_mode is not None:
                config_data["TOP_LEFT_TEXT_MODE"] = top_left_text_mode
            if words_topic is not None:
                config_data["WORDS_TOPIC"] = words_topic
            if text_color is not None:
                config_data["TEXT_COLOR"] = text_color
            if text_size is not None:
                config_data["TEXT_SIZE"] = text_size
            if text_position is not None:
                config_data["TEXT_POSITION"] = text_position

            # Save the updated config
            JSON.dump(self.config_file, config_data)

            # Clean directories
            for directory in ["IMG", "SOUND"]:
                for file in glob.glob(f'./{directory}/*'):
                    try:
                        os.remove(file)
                    except Exception as e:
                        print(f"Error removing file {file}: {e}")

            # Create a temporary script file
            script_path = os.path.join(tempfile.gettempdir(), "webdrivertorso_temp.py")

            # Use our enhanced template instead of EXAMPLE.py
            if os.path.exists("webdrivertorso_template.py"):
                with open("webdrivertorso_template.py", "r", encoding="utf8") as f:
                    script_content = f.read()
            else:
                with open("EXAMPLE.py", "r", encoding="utf8") as f:
                    script_content = f.read()

            with open(script_path, "w", encoding="utf8") as f:
                f.write(script_content)

            # Send initial message
            if isinstance(ctx_or_interaction, commands.Context):
                await ctx_or_interaction.reply("🎬 Generating Webdriver Torso style video... This may take a minute.")
            elif not already_deferred:  # It's an Interaction and not deferred yet
                await ctx_or_interaction.response.defer(thinking=True)

            # Run the script as a subprocess
            process = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for the process to complete
            _, stderr = await process.communicate()

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
    async def webdrivertorso(self, ctx, *, options: str = ""):
        """Generate a Webdriver Torso style test video.

        Usage: !webdrivertorso [option1=value1] [option2=value2] ...

        Available options:
        - width: Video width in pixels (default: 640)
        - height: Video height in pixels (default: 480)
        - max_width: Maximum shape width (default: 200)
        - max_height: Maximum shape height (default: 200)
        - min_width: Minimum shape width (default: 20)
        - min_height: Minimum shape height (default: 20)
        - slides: Number of slides in the video (default: 10)
        - videos: Number of videos to generate (default: 1)
        - min_shapes: Minimum number of shapes per slide (default: 5)
        - max_shapes: Maximum number of shapes per slide (default: 15)
        - sound_quality: Audio sample rate (default: 44100)
        - tts_enabled: Enable text-to-speech (true/false)
        - tts_provider: TTS provider to use (gtts, pyttsx3, coqui)
        - tts_text: Text to be spoken in the video
        - audio_wave_type: Type of audio wave (sawtooth, sine, square, triangle, noise, pulse, harmonic)
        - slide_duration: Duration of each slide in milliseconds (default: 1000)
        - deform_level: Level of shape deformation (none, low, medium, high)
        - color_mode: Color mode for shapes (random, scheme, solid)
        - color_scheme: Color scheme to use (pastel, dark_gritty, nature, vibrant, ocean, neon, monochrome, autumn, cyberpunk, retro)
        - solid_color: Hex color code for solid color mode (#RRGGBB)
        - wave_vibe: Audio wave vibe (calm, eerie, random, energetic, dreamy, chaotic, glitchy, underwater, mechanical, ethereal, pulsating)
        - top_left_text_enabled: Show text in top-left corner (true/false)
        - top_left_text_mode: Mode for top-left text (random, word)
        - words_topic: Topic for word generation (random, introspective, action, nature, technology, space, ocean, fantasy, science, art, music, food, emotions, colors, abstract)
        - text_color: Color of text (hex code or name)
        - text_size: Size of text (default: auto-scaled)
        - text_position: Position of text (top-left, top-right, bottom-left, bottom-right, center, random)
        """
        # Parse options from the string
        params = {}
        if options:
            option_pairs = options.split()
            for pair in option_pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    # Convert string values to appropriate types
                    if value.lower() == 'true':
                        params[key] = True
                    elif value.lower() == 'false':
                        params[key] = False
                    elif value.isdigit():
                        params[key] = int(value)
                    elif key == 'allowed_shapes' and value.startswith('[') and value.endswith(']'):
                        # Parse list of shapes
                        shapes_list = value[1:-1].split(',')
                        params[key] = [shape.strip() for shape in shapes_list]
                    else:
                        params[key] = value

        async with ctx.typing():
            result = await self._generate_video_logic(ctx, **params)

        if isinstance(result, str):
            await ctx.reply(result)

    # --- Slash Command ---
    @app_commands.command(name="webdrivertorso", description="Generate a Webdriver Torso style test video")
    @app_commands.describe(
        # Video structure
        slides="Number of slides in the video (default: 10)",
        videos="Number of videos to generate (default: 1)",
        slide_duration="Duration of each slide in milliseconds (default: 1000)",

        # Video dimensions
        width="Video width in pixels (default: 640)",
        height="Video height in pixels (default: 480)",
        max_width="Maximum shape width (default: 200)",
        max_height="Maximum shape height (default: 200)",
        min_width="Minimum shape width (default: 20)",
        min_height="Minimum shape height (default: 20)",

        # Shapes
        min_shapes="Minimum number of shapes per slide (default: 5)",
        max_shapes="Maximum number of shapes per slide (default: 15)",
        deform_level="Level of shape deformation (none, low, medium, high)",
        shape_types="Types of shapes to include (comma-separated list)",

        # Colors
        color_mode="Color mode for shapes (random, scheme, solid)",
        color_scheme="Color scheme to use (pastel, dark_gritty, nature, vibrant, ocean)",
        solid_color="Hex color code for solid color mode (#RRGGBB)",

        # Audio
        sound_quality="Audio sample rate (default: 44100)",
        audio_wave_type="Type of audio wave (sawtooth, sine, square)",
        wave_vibe="Audio wave vibe (calm, eerie, random, energetic, dreamy, chaotic)",
        tts_enabled="Enable text-to-speech (default: false)",
        tts_provider="TTS provider to use (gtts, pyttsx3, coqui)",
        tts_text="Text to be spoken in the video",

        # Text
        top_left_text_enabled="Show text in top-left corner (default: true)",
        top_left_text_mode="Mode for top-left text (random, word)",
        words_topic="Topic for word generation (random, introspective, action, nature, technology, etc.)",
        text_color="Color of text (hex code or name)",
        text_size="Size of text (default: auto-scaled)",
        text_position="Position of text (top-left, top-right, bottom-left, bottom-right, center)"
    )
    @app_commands.choices(deform_level=[
        app_commands.Choice(name="None", value="none"),
        app_commands.Choice(name="Low", value="low"),
        app_commands.Choice(name="Medium", value="medium"),
        app_commands.Choice(name="High", value="high")
    ])
    @app_commands.choices(color_mode=[
        app_commands.Choice(name="Random", value="random"),
        app_commands.Choice(name="Color Scheme", value="scheme"),
        app_commands.Choice(name="Solid Color", value="solid")
    ])
    @app_commands.choices(color_scheme=[
        app_commands.Choice(name="Pastel", value="pastel"),
        app_commands.Choice(name="Dark Gritty", value="dark_gritty"),
        app_commands.Choice(name="Nature", value="nature"),
        app_commands.Choice(name="Vibrant", value="vibrant"),
        app_commands.Choice(name="Ocean", value="ocean"),
        # Additional color schemes
        app_commands.Choice(name="Neon", value="neon"),
        app_commands.Choice(name="Monochrome", value="monochrome"),
        app_commands.Choice(name="Autumn", value="autumn"),
        app_commands.Choice(name="Cyberpunk", value="cyberpunk"),
        app_commands.Choice(name="Retro", value="retro")
    ])
    @app_commands.choices(audio_wave_type=[
        app_commands.Choice(name="Sawtooth", value="sawtooth"),
        app_commands.Choice(name="Sine", value="sine"),
        app_commands.Choice(name="Square", value="square"),
        # Additional wave types
        app_commands.Choice(name="Triangle", value="triangle"),
        app_commands.Choice(name="Noise", value="noise"),
        app_commands.Choice(name="Pulse", value="pulse"),
        app_commands.Choice(name="Harmonic", value="harmonic")
    ])
    @app_commands.choices(tts_provider=[
        app_commands.Choice(name="Google TTS", value="gtts"),
        app_commands.Choice(name="pyttsx3 (Offline TTS)", value="pyttsx3"),
        app_commands.Choice(name="Coqui TTS (AI Voice)", value="coqui")
    ])
    @app_commands.choices(wave_vibe=[
        app_commands.Choice(name="Calm", value="calm"),
        app_commands.Choice(name="Eerie", value="eerie"),
        app_commands.Choice(name="Random", value="random"),
        app_commands.Choice(name="Energetic", value="energetic"),
        app_commands.Choice(name="Dreamy", value="dreamy"),
        app_commands.Choice(name="Chaotic", value="chaotic"),
        # Additional wave vibes
        app_commands.Choice(name="Glitchy", value="glitchy"),
        app_commands.Choice(name="Underwater", value="underwater"),
        app_commands.Choice(name="Mechanical", value="mechanical"),
        app_commands.Choice(name="Ethereal", value="ethereal"),
        app_commands.Choice(name="Pulsating", value="pulsating")
    ])
    @app_commands.choices(top_left_text_mode=[
        app_commands.Choice(name="Random", value="random"),
        app_commands.Choice(name="Word", value="word")
    ])
    @app_commands.choices(words_topic=[
        app_commands.Choice(name="Random", value="random"),
        app_commands.Choice(name="Introspective", value="introspective"),
        app_commands.Choice(name="Action", value="action"),
        app_commands.Choice(name="Nature", value="nature"),
        app_commands.Choice(name="Technology", value="technology"),
        # Additional word topics
        app_commands.Choice(name="Space", value="space"),
        app_commands.Choice(name="Ocean", value="ocean"),
        app_commands.Choice(name="Fantasy", value="fantasy"),
        app_commands.Choice(name="Science", value="science"),
        app_commands.Choice(name="Art", value="art"),
        app_commands.Choice(name="Music", value="music"),
        app_commands.Choice(name="Food", value="food"),
        app_commands.Choice(name="Emotions", value="emotions"),
        app_commands.Choice(name="Colors", value="colors"),
        app_commands.Choice(name="Abstract", value="abstract")
    ])
    @app_commands.choices(text_position=[
        app_commands.Choice(name="Top Left", value="top-left"),
        app_commands.Choice(name="Top Right", value="top-right"),
        app_commands.Choice(name="Bottom Left", value="bottom-left"),
        app_commands.Choice(name="Bottom Right", value="bottom-right"),
        app_commands.Choice(name="Center", value="center"),
        app_commands.Choice(name="Random", value="random")
    ])
    async def webdrivertorso_slash(self, interaction: discord.Interaction,
                                  # Video structure
                                  slides: int = None,
                                  videos: int = None,
                                  slide_duration: int = None,

                                  # Video dimensions
                                  width: int = None,
                                  height: int = None,
                                  max_width: int = None,
                                  max_height: int = None,
                                  min_width: int = None,
                                  min_height: int = None,

                                  # Shapes
                                  min_shapes: int = None,
                                  max_shapes: int = None,
                                  deform_level: str = None,
                                  shape_types: str = None,

                                  # Colors
                                  color_mode: str = None,
                                  color_scheme: str = None,
                                  solid_color: str = None,

                                  # Audio
                                  sound_quality: int = None,
                                  audio_wave_type: str = None,
                                  wave_vibe: str = None,
                                  tts_enabled: bool = None,
                                  tts_provider: str = None,
                                  tts_text: str = None,

                                  # Text
                                  top_left_text_enabled: bool = None,
                                  top_left_text_mode: str = None,
                                  words_topic: str = None,
                                  text_color: str = None,
                                  text_size: int = None,
                                  text_position: str = None):
        """Slash command version of webdrivertorso."""
        await interaction.response.defer(thinking=True)
        result = await self._generate_video_logic(
            interaction,
            # Video structure
            slides=slides,
            videos=videos,
            slide_duration=slide_duration,

            # Video dimensions
            width=width,
            height=height,
            max_width=max_width,
            max_height=max_height,
            min_width=min_width,
            min_height=min_height,

            # Shapes
            min_shapes=min_shapes,
            max_shapes=max_shapes,
            deform_level=deform_level,
            allowed_shapes=shape_types.split(',') if shape_types else None,

            # Colors
            color_mode=color_mode,
            color_scheme=color_scheme,
            solid_color=solid_color,

            # Audio
            sound_quality=sound_quality,
            audio_wave_type=audio_wave_type,
            wave_vibe=wave_vibe,
            tts_enabled=tts_enabled,
            tts_provider=tts_provider,
            tts_text=tts_text,

            # Text
            top_left_text_enabled=top_left_text_enabled,
            top_left_text_mode=top_left_text_mode,
            words_topic=words_topic,
            text_color=text_color,
            text_size=text_size,
            text_position=text_position,

            already_deferred=True
        )

        if isinstance(result, str):
            await interaction.followup.send(result)

async def setup(bot: commands.Bot):
    await bot.add_cog(WebdriverTorsoCog(bot))
