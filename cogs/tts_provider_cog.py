import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import tempfile
import sys
import importlib.util

class TTSProviderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("TTSProviderCog initialized!")
        self.cleanup_old_files()

        # Schedule periodic cleanup
        self.cleanup_task = self.bot.loop.create_task(self.periodic_cleanup())

    async def periodic_cleanup(self):
        """Periodically clean up old TTS files."""
        import asyncio
        while not self.bot.is_closed():
            # Clean up every hour
            await asyncio.sleep(3600)  # 1 hour
            self.cleanup_old_files()

    def cog_unload(self):
        """Cancel the cleanup task when the cog is unloaded."""
        if hasattr(self, 'cleanup_task') and self.cleanup_task:
            self.cleanup_task.cancel()

    def cleanup_old_files(self):
        """Clean up old TTS files to prevent disk space issues."""
        try:
            import glob
            import time
            import os

            # Create the SOUND directory if it doesn't exist
            os.makedirs("./SOUND", exist_ok=True)

            # Get current time
            current_time = time.time()

            # Find all TTS files older than 1 hour
            old_files = []
            for pattern in ["./SOUND/tts_*.mp3", "./SOUND/tts_direct_*.mp3", "./SOUND/tts_test_*.mp3"]:
                for file in glob.glob(pattern):
                    if os.path.exists(file) and os.path.getmtime(file) < current_time - 3600:  # 1 hour = 3600 seconds
                        old_files.append(file)

            # Delete old files
            for file in old_files:
                try:
                    os.remove(file)
                    print(f"Cleaned up old TTS file: {file}")
                except Exception as e:
                    print(f"Error removing old TTS file {file}: {e}")

            print(f"Cleaned up {len(old_files)} old TTS files")
        except Exception as e:
            print(f"Error during cleanup: {e}")

    async def generate_tts_directly(self, provider, text, output_file=None):
        """Generate TTS audio directly without using a subprocess."""
        # Create a unique output file if none is provided
        if output_file is None:
            import uuid
            output_file = f"./SOUND/tts_direct_{uuid.uuid4().hex}.mp3"

        # Create output directory if it doesn't exist
        os.makedirs("./SOUND", exist_ok=True)

        # Check if the provider is available
        if provider == "gtts":
            # Check if gtts is available
            if importlib.util.find_spec("gtts") is None:
                return False, "Google TTS (gtts) is not installed. Run: pip install gtts"

            try:
                from gtts import gTTS
                tts = gTTS(text=text, lang='en')
                tts.save(output_file)
                return True, output_file
            except Exception as e:
                return False, f"Error with Google TTS: {str(e)}"

        elif provider == "pyttsx3":
            # Check if pyttsx3 is available
            if importlib.util.find_spec("pyttsx3") is None:
                return False, "pyttsx3 is not installed. Run: pip install pyttsx3"

            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.save_to_file(text, output_file)
                engine.runAndWait()
                return True, output_file
            except Exception as e:
                return False, f"Error with pyttsx3: {str(e)}"

        elif provider == "coqui":
            # Check if TTS is available
            if importlib.util.find_spec("TTS") is None:
                return False, "Coqui TTS is not installed. Run: pip install TTS"

            try:
                from TTS.api import TTS
                tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")
                tts.tts_to_file(text=text, file_path=output_file)
                return True, output_file
            except Exception as e:
                return False, f"Error with Coqui TTS: {str(e)}"

        elif provider == "espeak":
            # Check if we can run espeak-ng command
            import subprocess
            import platform

            try:
                # Check if espeak-ng is available
                if platform.system() == "Windows":
                    # On Windows, we'll check if the command exists
                    result = subprocess.run(["where", "espeak-ng"], capture_output=True, text=True)
                    espeak_available = result.returncode == 0
                else:
                    # On Linux/Mac, we'll use which
                    result = subprocess.run(["which", "espeak-ng"], capture_output=True, text=True)
                    espeak_available = result.returncode == 0

                if not espeak_available:
                    return False, "espeak-ng is not installed or not in PATH. Install espeak-ng and make sure it's in your PATH."

                # Create a WAV file first
                wav_file = output_file.replace(".mp3", ".wav")

                # Run espeak-ng to generate the audio
                cmd = ["espeak-ng", "-w", wav_file, text]
                process = subprocess.run(cmd, capture_output=True, text=True)

                if process.returncode != 0:
                    return False, f"Error running espeak-ng: {process.stderr}"

                # Convert WAV to MP3 if needed
                if output_file.endswith(".mp3"):
                    try:
                        # Try to use pydub for conversion
                        from pydub import AudioSegment
                        sound = AudioSegment.from_wav(wav_file)
                        sound.export(output_file, format="mp3")
                        # Remove the temporary WAV file
                        os.remove(wav_file)
                    except Exception as e:
                        # If pydub fails, just use the WAV file
                        print(f"Warning: Could not convert WAV to MP3: {e}")
                        output_file = wav_file
                else:
                    # If the output file doesn't end with .mp3, we're already using the WAV file
                    output_file = wav_file

                return True, output_file
            except Exception as e:
                return False, f"Error with espeak-ng: {str(e)}"

        else:
            return False, f"Unknown TTS provider: {provider}"

    @app_commands.command(name="ttsprovider", description="Test different TTS providers")
    @app_commands.describe(
        provider="Select the TTS provider to use",
        text="Text to be spoken"
    )
    @app_commands.choices(provider=[
        app_commands.Choice(name="Google TTS (Online)", value="gtts"),
        app_commands.Choice(name="pyttsx3 (Offline)", value="pyttsx3"),
        app_commands.Choice(name="Coqui TTS (AI Voice)", value="coqui"),
        app_commands.Choice(name="eSpeak-NG (Offline)", value="espeak")
    ])
    async def ttsprovider_slash(self, interaction: discord.Interaction,
                               provider: str,
                               text: str = "This is a test of text to speech"):
        """Test different TTS providers"""
        await interaction.response.defer(thinking=True)

        # Create a temporary script to test the TTS provider
        script_content = f"""
import importlib.util
import sys
import os
import traceback

# Print Python version and path for debugging
print(f"Python version: {{sys.version}}")
print(f"Python executable: {{sys.executable}}")
print(f"Current working directory: {{os.getcwd()}}")

# Check for TTS libraries
try:
    import pkg_resources
    installed_packages = [pkg.key for pkg in pkg_resources.working_set]
    print(f"Installed packages: {{installed_packages}}")
except Exception as e:
    print(f"Error getting installed packages: {{e}}")

# Check for specific TTS libraries
try:
    GTTS_AVAILABLE = importlib.util.find_spec("gtts") is not None
    print(f"GTTS_AVAILABLE: {{GTTS_AVAILABLE}}")
    if GTTS_AVAILABLE:
        import gtts
        print(f"gtts version: {{gtts.__version__}}")
except Exception as e:
    print(f"Error checking gtts: {{e}}")
    GTTS_AVAILABLE = False

try:
    PYTTSX3_AVAILABLE = importlib.util.find_spec("pyttsx3") is not None
    print(f"PYTTSX3_AVAILABLE: {{PYTTSX3_AVAILABLE}}")
    if PYTTSX3_AVAILABLE:
        import pyttsx3
        print("pyttsx3 imported successfully")
except Exception as e:
    print(f"Error checking pyttsx3: {{e}}")
    PYTTSX3_AVAILABLE = False

try:
    COQUI_AVAILABLE = importlib.util.find_spec("TTS") is not None
    print(f"COQUI_AVAILABLE: {{COQUI_AVAILABLE}}")
    if COQUI_AVAILABLE:
        import TTS
        print(f"TTS version: {{TTS.__version__}}")
except Exception as e:
    print(f"Error checking TTS: {{e}}")
    COQUI_AVAILABLE = False

# Check for espeak-ng
try:
    import subprocess
    import platform
    if platform.system() == "Windows":
        # On Windows, we'll check if the command exists
        result = subprocess.run(["where", "espeak-ng"], capture_output=True, text=True)
        ESPEAK_AVAILABLE = result.returncode == 0
    else:
        # On Linux/Mac, we'll use which
        result = subprocess.run(["which", "espeak-ng"], capture_output=True, text=True)
        ESPEAK_AVAILABLE = result.returncode == 0
    print(f"ESPEAK_AVAILABLE: {{ESPEAK_AVAILABLE}}")
    if ESPEAK_AVAILABLE:
        # Try to get version
        version_result = subprocess.run(["espeak-ng", "--version"], capture_output=True, text=True)
        if version_result.returncode == 0:
            print(f"espeak-ng version: {{version_result.stdout.strip()}}")
        else:
            print("espeak-ng found but couldn't get version")
except Exception as e:
    print(f"Error checking espeak-ng: {{e}}")
    ESPEAK_AVAILABLE = False

def generate_tts_audio(provider, text, output_file):
    print(f"Testing TTS provider: {{provider}}")
    print(f"Text: {{text}}")
    print(f"Output file: {{output_file}}")

    if provider == "gtts" and GTTS_AVAILABLE:
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang='en')
            tts.save(output_file)
            print(f"Google TTS audio saved to {{output_file}}")
            return True
        except Exception as e:
            print(f"Error with Google TTS: {{e}}")
            traceback.print_exc()
            return False
    elif provider == "pyttsx3" and PYTTSX3_AVAILABLE:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.save_to_file(text, output_file)
            engine.runAndWait()
            print(f"pyttsx3 audio saved to {{output_file}}")
            return True
        except Exception as e:
            print(f"Error with pyttsx3: {{e}}")
            traceback.print_exc()
            return False
    elif provider == "coqui" and COQUI_AVAILABLE:
        try:
            from TTS.api import TTS
            tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")
            tts.tts_to_file(text=text, file_path=output_file)
            print(f"Coqui TTS audio saved to {{output_file}}")
            return True
        except Exception as e:
            print(f"Error with Coqui TTS: {{e}}")
            traceback.print_exc()
            return False
    elif provider == "espeak" and ESPEAK_AVAILABLE:
        try:
            # Create a WAV file first
            wav_file = output_file.replace(".mp3", ".wav")

            # Run espeak-ng to generate the audio
            cmd = ["espeak-ng", "-w", wav_file, text]
            process = subprocess.run(cmd, capture_output=True, text=True)

            if process.returncode != 0:
                print(f"Error running espeak-ng: {{process.stderr}}")
                traceback.print_exc()
                return False

            # Convert WAV to MP3 if needed
            if output_file.endswith(".mp3"):
                try:
                    # Try to use pydub for conversion
                    from pydub import AudioSegment
                    sound = AudioSegment.from_wav(wav_file)
                    sound.export(output_file, format="mp3")
                    # Remove the temporary WAV file
                    os.remove(wav_file)
                    print(f"espeak-ng audio saved to {{output_file}}")
                except Exception as e:
                    # If pydub fails, just use the WAV file
                    print(f"Warning: Could not convert WAV to MP3: {{e}}")
                    print(f"Using WAV file instead: {{wav_file}}")
                    output_file = wav_file
            else:
                # If the output file doesn't end with .mp3, we're already using the WAV file
                output_file = wav_file
                print(f"espeak-ng audio saved to {{output_file}}")

            return True
        except Exception as e:
            print(f"Error with espeak-ng: {{e}}")
            traceback.print_exc()
            return False
    else:
        print(f"TTS provider {{provider}} not available.")
        return False

# Create output directory if it doesn't exist
os.makedirs("./SOUND", exist_ok=True)

# Generate a unique filename
import uuid
unique_id = uuid.uuid4().hex
output_file = f"./SOUND/tts_test_{{unique_id}}.mp3"
print(f"Using output file: {{output_file}}")

# Generate TTS audio
try:
    success = generate_tts_audio("{provider}", "{text}", output_file)
    print(f"TTS generation {{'' if success else 'un'}}successful")
except Exception as e:
    print(f"Unexpected error: {{e}}")
    traceback.print_exc()
    success = False

# Verify file exists and has content
if os.path.exists(output_file):
    file_size = os.path.getsize(output_file)
    print(f"Output file exists, size: {{file_size}} bytes")
else:
    print("Output file does not exist")
"""

        # Save the script to a temporary file
        script_path = os.path.join(tempfile.gettempdir(), "tts_test.py")
        with open(script_path, "w", encoding="utf8") as f:
            f.write(script_content)

        # Run the script
        process = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for the process to complete
        stdout, stderr = await process.communicate()

        # Get the output regardless of return code
        stdout_text = stdout.decode() if stdout else ""
        stderr_text = stderr.decode() if stderr else ""

        # Combine stdout and stderr for complete output
        full_output = f"STDOUT:\n{stdout_text}\n\nSTDERR:\n{stderr_text}"

        # Extract the output filename from the stdout
        output_filename = None
        for line in stdout_text.split('\n'):
            if line.startswith("Using output file:"):
                output_filename = line.split(":", 1)[1].strip()
                break

        # If we couldn't find the filename in the output, use a default pattern to search
        if not output_filename:
            # Look for any tts_test_*.mp3 files created in the last minute
            import glob
            import time
            current_time = time.time()
            tts_files = []
            for file in glob.glob("./SOUND/tts_test_*.mp3"):
                if os.path.exists(file) and os.path.getmtime(file) > current_time - 60:
                    tts_files.append(file)

            if tts_files:
                # Use the most recently created file
                output_filename = max(tts_files, key=os.path.getmtime)
            else:
                # Fallback to the old filename pattern
                output_filename = "./SOUND/tts_test.mp3"

        # Check if the TTS file was generated
        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 0:
            # Success! Send the audio file
            await interaction.followup.send(
                f"✅ Successfully tested TTS provider: {provider}\nText: {text}\nFile: {os.path.basename(output_filename)}",
                file=discord.File(output_filename)
            )
        else:
            # Failed to generate audio with subprocess, try direct method as fallback
            await interaction.followup.send(f"Subprocess method failed. Trying direct TTS generation with {provider}...")

            # Try the direct method
            success, result = await self.generate_tts_directly(provider, text)

            if success and os.path.exists(result) and os.path.getsize(result) > 0:
                # Direct method succeeded!
                await interaction.followup.send(
                    f"✅ Successfully generated TTS audio with {provider} (direct method)\nText: {text}",
                    file=discord.File(result)
                )
                return

            # Both methods failed, send detailed error information
            error_message = f"❌ Failed to generate TTS audio with provider: {provider}\n\n"

            # Check if the process failed
            if process.returncode != 0:
                error_message += f"Process returned error code: {process.returncode}\n\n"

            # Add direct method error
            if not success:
                error_message += f"Direct method error: {result}\n\n"

            # Create a summary of the most important information
            error_summary = "Error Summary:\n"

            # Extract key information from the output
            if f"{provider.upper()}_AVAILABLE: False" in full_output:
                error_summary += f"- The {provider} library is not available or not properly installed\n"

            if "Error with " + provider in full_output:
                # Extract the specific error message
                error_line = next((line for line in full_output.split('\n') if "Error with " + provider in line), "")
                if error_line:
                    error_summary += f"- {error_line}\n"

            # Add the error summary to the message
            error_message += error_summary + "\n"

            # Add instructions for fixing the issue
            error_message += "To fix this issue, try:\n"
            error_message += "1. Make sure the required packages are installed:\n"

            if provider == "gtts":
                error_message += "   - Run: pip install gtts\n"
            elif provider == "pyttsx3":
                error_message += "   - Run: pip install pyttsx3\n"
                error_message += "   - On Linux, you may need additional packages: sudo apt-get install espeak\n"
            elif provider == "coqui":
                error_message += "   - Run: pip install TTS\n"
                error_message += "   - This may require additional dependencies based on your system\n"

            error_message += "2. Restart the bot after installing the packages\n"

            # Add a note about the full output
            error_message += "\nFull diagnostic output is available but may be too long to display here."

            # Send the error message
            await interaction.followup.send(error_message)

            # If the output is not too long, send it as a separate message
            if len(full_output) <= 1900:  # Discord message limit is 2000 characters
                await interaction.followup.send(f"```\n{full_output}\n```")
            else:
                # Save the output to a file and send it
                output_file = os.path.join(tempfile.gettempdir(), "tts_error_log.txt")
                with open(output_file, "w", encoding="utf8") as f:
                    f.write(full_output)
                await interaction.followup.send("Detailed error log:", file=discord.File(output_file))

    @commands.command(name="ttscheck")
    async def tts_check(self, ctx):
        """Check if TTS libraries are installed and working."""
        await ctx.send("Checking TTS libraries...")

        # Check for gtts
        gtts_available = importlib.util.find_spec("gtts") is not None
        gtts_version = "Not installed"
        if gtts_available:
            try:
                import gtts
                gtts_version = getattr(gtts, "__version__", "Unknown version")
            except Exception as e:
                gtts_version = f"Error importing: {str(e)}"

        # Check for pyttsx3
        pyttsx3_available = importlib.util.find_spec("pyttsx3") is not None
        pyttsx3_version = "Not installed"
        if pyttsx3_available:
            try:
                import pyttsx3
                pyttsx3_version = "Installed (no version info available)"
            except Exception as e:
                pyttsx3_version = f"Error importing: {str(e)}"

        # Check for TTS (Coqui)
        coqui_available = importlib.util.find_spec("TTS") is not None
        coqui_version = "Not installed"
        if coqui_available:
            try:
                import TTS
                coqui_version = getattr(TTS, "__version__", "Unknown version")
            except Exception as e:
                coqui_version = f"Error importing: {str(e)}"

        # Check for espeak-ng
        espeak_version = "Not installed"
        try:
            import subprocess
            import platform
            if platform.system() == "Windows":
                # On Windows, we'll check if the command exists
                result = subprocess.run(["where", "espeak-ng"], capture_output=True, text=True)
                espeak_available = result.returncode == 0
            else:
                # On Linux/Mac, we'll use which
                result = subprocess.run(["which", "espeak-ng"], capture_output=True, text=True)
                espeak_available = result.returncode == 0

            if espeak_available:
                # Try to get version
                version_result = subprocess.run(["espeak-ng", "--version"], capture_output=True, text=True)
                if version_result.returncode == 0:
                    espeak_version = version_result.stdout.strip()
                else:
                    espeak_version = "Installed (version unknown)"
            else:
                espeak_version = "Not installed"
        except Exception as e:
            espeak_version = f"Error checking: {str(e)}"

        # Create a report
        report = "**TTS Libraries Status:**\n"
        report += f"- Google TTS (gtts): {gtts_version}\n"
        report += f"- pyttsx3: {pyttsx3_version}\n"
        report += f"- Coqui TTS: {coqui_version}\n"
        report += f"- eSpeak-NG: {espeak_version}\n\n"

        # Add installation instructions
        report += "**Installation Instructions:**\n"
        report += "- Google TTS: `pip install gtts`\n"
        report += "- pyttsx3: `pip install pyttsx3`\n"
        report += "- Coqui TTS: `pip install TTS`\n"
        report += "- eSpeak-NG: Install from https://github.com/espeak-ng/espeak-ng/releases\n\n"

        report += "After installing, restart the bot for the changes to take effect."

        await ctx.send(report)

async def setup(bot: commands.Bot):
    print("Loading TTSProviderCog...")
    await bot.add_cog(TTSProviderCog(bot))
    print("TTSProviderCog loaded successfully!")
