import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import tempfile
import sys

class TTSProviderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("TTSProviderCog initialized!")

    @app_commands.command(name="ttsprovider", description="Test different TTS providers")
    @app_commands.describe(
        provider="Select the TTS provider to use",
        text="Text to be spoken"
    )
    @app_commands.choices(provider=[
        app_commands.Choice(name="Google TTS (Online)", value="gtts"),
        app_commands.Choice(name="pyttsx3 (Offline)", value="pyttsx3"),
        app_commands.Choice(name="Coqui TTS (AI Voice)", value="coqui")
    ])
    async def ttsprovider_slash(self, interaction: discord.Interaction, 
                               provider: str,
                               text: str = "This is a test of text to speech"):
        """Test different TTS providers"""
        await interaction.response.defer(thinking=True)
        
        # Create a temporary script to test the TTS provider
        script_content = f"""
import importlib.util

# Check for TTS libraries
GTTS_AVAILABLE = importlib.util.find_spec("gtts") is not None
PYTTSX3_AVAILABLE = importlib.util.find_spec("pyttsx3") is not None
COQUI_AVAILABLE = importlib.util.find_spec("TTS") is not None

def generate_tts_audio(provider, text, output_file):
    print(f"Testing TTS provider: {{provider}}")
    print(f"Text: {{text}}")
    print(f"Output file: {{output_file}}")
    
    if provider == "gtts" and GTTS_AVAILABLE:
        from gtts import gTTS
        tts = gTTS(text=text, lang='en')
        tts.save(output_file)
        print(f"Google TTS audio saved to {{output_file}}")
        return True
    elif provider == "pyttsx3" and PYTTSX3_AVAILABLE:
        import pyttsx3
        engine = pyttsx3.init()
        engine.save_to_file(text, output_file)
        engine.runAndWait()
        print(f"pyttsx3 audio saved to {{output_file}}")
        return True
    elif provider == "coqui" and COQUI_AVAILABLE:
        try:
            from TTS.api import TTS
            tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")
            tts.tts_to_file(text=text, file_path=output_file)
            print(f"Coqui TTS audio saved to {{output_file}}")
            return True
        except Exception as e:
            print(f"Error with Coqui TTS: {{e}}")
            return False
    else:
        print(f"TTS provider {{provider}} not available.")
        return False

# Create output directory if it doesn't exist
import os
os.makedirs("./SOUND", exist_ok=True)

# Generate TTS audio
output_file = "./SOUND/tts_test.mp3"
success = generate_tts_audio("{provider}", "{text}", output_file)
print(f"TTS generation {'successful' if success else 'failed'}")
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
        
        # Check if the process was successful
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            await interaction.followup.send(f"❌ Error testing TTS provider: {error_msg}")
            return
        
        # Get the output
        output = stdout.decode()
        
        # Check if the TTS file was generated
        if os.path.exists("./SOUND/tts_test.mp3"):
            await interaction.followup.send(
                f"✅ Successfully tested TTS provider: {provider}\nText: {text}",
                file=discord.File("./SOUND/tts_test.mp3")
            )
        else:
            await interaction.followup.send(
                f"❌ Failed to generate TTS audio with provider: {provider}\nOutput: {output}"
            )

async def setup(bot: commands.Bot):
    print("Loading TTSProviderCog...")
    await bot.add_cog(TTSProviderCog(bot))
    print("TTSProviderCog loaded successfully!")
