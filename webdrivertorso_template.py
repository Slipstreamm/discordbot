import random
from PIL import Image, ImageDraw, ImageFont
import math
import wave
import struct
from pydub import AudioSegment
import os
import moviepy.video.io.ImageSequenceClip
import glob
import json
import numpy as np
import importlib.util
import sys

# Check for TTS libraries
GTTS_AVAILABLE = importlib.util.find_spec("gtts") is not None
PYTTSX3_AVAILABLE = importlib.util.find_spec("pyttsx3") is not None
COQUI_AVAILABLE = importlib.util.find_spec("TTS") is not None

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
except Exception as e:
    print(f"Error checking espeak-ng: {e}")
    ESPEAK_AVAILABLE = False

class JSON:
    def read(file):
        with open(f"{file}.json", "r", encoding="utf8") as file:
            data = json.load(file, strict=False)
        return data

    def dump(file, data):
        with open(f"{file}.json", "w", encoding="utf8") as file:
            json.dump(data, file, indent=4)

config_data = JSON.read("config")

# SETTINGS #
w = config_data["WIDTH"]
h = config_data["HEIGHT"]
maxW = config_data["MAX_WIDTH"]
maxH = config_data["MAX_HEIGHT"]
minW = config_data["MIN_WIDTH"]
minH = config_data["MIN_HEIGHT"]
LENGTH = config_data["SLIDES"]
AMOUNT = config_data["VIDEOS"]
min_shapes = config_data["MIN_SHAPES"]
max_shapes = config_data["MAX_SHAPES"]
sample_rate = config_data["SOUND_QUALITY"]
tts_enabled = config_data.get("TTS_ENABLED", False)
tts_text = config_data.get("TTS_TEXT", "This is a default text for TTS.")
tts_provider = config_data.get("TTS_PROVIDER", "gtts")  # Options: gtts, pyttsx3, coqui
audio_wave_type = config_data.get("AUDIO_WAVE_TYPE", "sawtooth")  # Options: sawtooth, sine, square, triangle, noise, pulse, harmonic
slide_duration = config_data.get("SLIDE_DURATION", 1000)  # Duration in milliseconds
deform_level = config_data.get("DEFORM_LEVEL", "none")  # Options: none, low, medium, high
color_mode = config_data.get("COLOR_MODE", "random")  # Options: random, scheme, solid
color_scheme = config_data.get("COLOR_SCHEME", "default")  # Placeholder for color schemes
solid_color = config_data.get("SOLID_COLOR", "#FFFFFF")  # Default solid color
allowed_shapes = config_data.get("ALLOWED_SHAPES", ["rectangle", "ellipse", "polygon", "triangle", "circle"])
wave_vibe = config_data.get("WAVE_VIBE", "calm")  # New config option for wave vibe
top_left_text_enabled = config_data.get("TOP_LEFT_TEXT_ENABLED", True)
top_left_text_mode = config_data.get("TOP_LEFT_TEXT_MODE", "random")  # Options: random, word
words_topic = config_data.get("WORDS_TOPIC", "random")  # Options: random, introspective, action, nature, technology
text_color = config_data.get("TEXT_COLOR", "#000000")
text_size = config_data.get("TEXT_SIZE", 0)  # 0 means auto-scale
text_position = config_data.get("TEXT_POSITION", "top-left")

# Get color schemes from config if available
color_schemes_data = config_data.get("COLOR_SCHEMES", {
    "pastel": [[255, 182, 193], [176, 224, 230], [240, 230, 140], [221, 160, 221], [152, 251, 152]],
    "dark_gritty": [[47, 79, 79], [105, 105, 105], [0, 0, 0], [85, 107, 47], [139, 69, 19]],
    "nature": [[34, 139, 34], [107, 142, 35], [46, 139, 87], [32, 178, 170], [154, 205, 50]],
    "vibrant": [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0], [255, 0, 255]],
    "ocean": [[0, 105, 148], [72, 209, 204], [70, 130, 180], [135, 206, 250], [176, 224, 230]]
})

# Convert color schemes from lists to tuples for PIL
color_schemes = {}
for scheme_name, colors in color_schemes_data.items():
    color_schemes[scheme_name] = [tuple(color) for color in colors]

# Default color scheme if the specified one doesn't exist
if color_scheme not in color_schemes:
    color_schemes[color_scheme] = [(128, 128, 128)]

# Vibe presets for wave sound
wave_vibes = config_data.get("WAVE_VIBES", {
    "calm": {"frequency": 200, "amplitude": 0.3, "modulation": 0.1},
    "eerie": {"frequency": 600, "amplitude": 0.5, "modulation": 0.7},
    "random": {},  # Randomized values will be generated
    "energetic": {"frequency": 800, "amplitude": 0.7, "modulation": 0.2},
    "dreamy": {"frequency": 400, "amplitude": 0.4, "modulation": 0.5},
    "chaotic": {"frequency": 1000, "amplitude": 1.0, "modulation": 1.0}
})

# Word topics
word_topics = config_data.get("WORD_TOPICS", {
    "introspective": ["reflection", "thought", "solitude", "ponder", "meditation", "introspection", "awareness", "contemplation", "silence", "stillness"],
    "action": ["run", "jump", "climb", "race", "fight", "explore", "build", "create", "overcome", "achieve"],
    "nature": ["tree", "mountain", "river", "ocean", "flower", "forest", "animal", "sky", "valley", "meadow"],
    "technology": ["computer", "robot", "network", "data", "algorithm", "innovation", "digital", "machine", "software", "hardware"]
})

# Font scaling based on video size
if text_size <= 0:
    font_size = max(w, h) // 40  # Scales font size to make it smaller and more readable
else:
    font_size = text_size

fnt = ImageFont.truetype("./FONT/sys.ttf", font_size)

files = glob.glob('./IMG/*')
for f in files:
    os.remove(f)

print("REMOVED OLD FILES")

def generate_string(length, charset="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"):
    result = ""
    for i in range(length):
        result += random.choice(charset)
    return result

def generate_word(theme="random"):
    if theme == "random" or theme not in word_topics:
        if random.random() < 0.5 and len(word_topics) > 0:
            # 50% chance to use a word from a random topic
            random_topic = random.choice(list(word_topics.keys()))
            return random.choice(word_topics[random_topic])
        else:
            # Generate a random string
            return generate_string(random.randint(3, 10))
    else:
        # Use a word from the specified topic
        return random.choice(word_topics[theme])

def generate_wave_sample(x, freq, wave_type, amplitude=1.0):
    """Generate a sample for different wave types"""
    t = x / sample_rate

    if wave_type == "sine":
        return amplitude * math.sin(2 * math.pi * freq * t)
    elif wave_type == "square":
        return amplitude * (1 if math.sin(2 * math.pi * freq * t) > 0 else -1)
    elif wave_type == "triangle":
        return amplitude * (2 * abs(2 * (t * freq - math.floor(t * freq + 0.5))) - 1)
    elif wave_type == "sawtooth":
        return amplitude * (2 * (t * freq - math.floor(t * freq + 0.5)))
    elif wave_type == "noise":
        return amplitude * (random.random() * 2 - 1)
    elif wave_type == "pulse":
        return amplitude * (1 if math.sin(2 * math.pi * freq * t) > 0.7 else 0)
    elif wave_type == "harmonic":
        return amplitude * (
            math.sin(2 * math.pi * freq * t) * 0.6 +
            math.sin(2 * math.pi * freq * 2 * t) * 0.3 +
            math.sin(2 * math.pi * freq * 3 * t) * 0.1
        )
    else:  # Default to sawtooth
        return amplitude * (2 * (t * freq - math.floor(t * freq + 0.5)))

def append_wave(
        freq=None,
        duration_milliseconds=1000,
        volume=1.0):

    global audio

    vibe_params = wave_vibes.get(wave_vibe, wave_vibes["calm"])
    if wave_vibe == "random":
        freq = random.uniform(100, 1000) if freq is None else freq
        amplitude = random.uniform(0.1, 1.0)
        modulation = random.uniform(0.1, 1.0)
    else:
        base_freq = vibe_params["frequency"]
        freq = random.uniform(base_freq * 0.7, base_freq * 1.3) if freq is None else freq
        amplitude = vibe_params["amplitude"] * random.uniform(0.7, 1.3)
        modulation = vibe_params["modulation"] * random.uniform(0.6, 1.4)

    num_samples = duration_milliseconds * (sample_rate / 1000.0)

    for x in range(int(num_samples)):
        wave_sample = generate_wave_sample(x, freq, audio_wave_type, amplitude)
        modulated_sample = wave_sample * (1 + modulation * math.sin(2 * math.pi * 0.5 * x / sample_rate))
        audio.append(volume * modulated_sample)
    return

def save_wav(file_name):
    wav_file = wave.open(file_name, "w")

    nchannels = 1

    sampwidth = 2

    nframes = len(audio)
    comptype = "NONE"
    compname = "not compressed"
    wav_file.setparams((nchannels, sampwidth, sample_rate, nframes, comptype, compname))

    for sample in audio:
        wav_file.writeframes(struct.pack('h', int(sample * 32767.0)))

    wav_file.close()

    return

# Generate TTS audio using different providers
def generate_tts_audio(text, output_file):
    if tts_provider == "gtts" and GTTS_AVAILABLE:
        from gtts import gTTS
        tts = gTTS(text=text, lang='en')
        tts.save(output_file)
        print(f"Google TTS audio saved to {output_file}")
        return True
    elif tts_provider == "pyttsx3" and PYTTSX3_AVAILABLE:
        import pyttsx3
        engine = pyttsx3.init()
        engine.save_to_file(text, output_file)
        engine.runAndWait()
        print(f"pyttsx3 audio saved to {output_file}")
        return True
    elif tts_provider == "coqui" and COQUI_AVAILABLE:
        try:
            from TTS.api import TTS
            tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")
            tts.tts_to_file(text=text, file_path=output_file)
            print(f"Coqui TTS audio saved to {output_file}")
            return True
        except Exception as e:
            print(f"Error with Coqui TTS: {e}")
            return False
    elif tts_provider == "espeak" and ESPEAK_AVAILABLE:
        try:
            # Create a WAV file first
            wav_file = output_file.replace(".mp3", ".wav")

            # Run espeak-ng to generate the audio
            cmd = ["espeak-ng", "-w", wav_file, text]
            process = subprocess.run(cmd, capture_output=True, text=True)

            if process.returncode != 0:
                print(f"Error running espeak-ng: {process.stderr}")
                return False

            # Convert WAV to MP3 if needed
            if output_file.endswith(".mp3"):
                try:
                    # Try to use pydub for conversion
                    sound = AudioSegment.from_wav(wav_file)
                    sound.export(output_file, format="mp3")
                    # Remove the temporary WAV file
                    os.remove(wav_file)
                    print(f"espeak-ng audio saved to {output_file}")
                except Exception as e:
                    # If pydub fails, just use the WAV file
                    print(f"Warning: Could not convert WAV to MP3: {e}")
                    print(f"Using WAV file instead: {wav_file}")
                    output_file = wav_file
            else:
                # If the output file doesn't end with .mp3, we're already using the WAV file
                output_file = wav_file
                print(f"espeak-ng audio saved to {output_file}")

            return True
        except Exception as e:
            print(f"Error with espeak-ng: {e}")
            return False
    else:
        print(f"TTS provider {tts_provider} not available. Falling back to no TTS.")
        return False

if tts_enabled:
    tts_audio_file = "./SOUND/tts_output.mp3"
    tts_success = generate_tts_audio(tts_text, tts_audio_file)
    if not tts_success:
        tts_enabled = False

for xyz in range(AMOUNT):
    video_name = generate_string(6)  # Generate a consistent video name

    for i in range(LENGTH):
        img = Image.new("RGB", (w, h))

        img1 = ImageDraw.Draw(img)

        img1.rectangle([(0, 0), (w, h)], fill="white", outline="white")

        num_shapes = random.randint(min_shapes, max_shapes)
        for _ in range(num_shapes):
            shape_type = random.choice(allowed_shapes)
            x1, y1 = random.randint(0, w), random.randint(0, h)

            if deform_level == "none":
                x2, y2 = minW + (maxW - minW) // 2, minH + (maxH - minH) // 2
            elif deform_level == "low":
                x2 = random.randint(minW, minW + (maxW - minW) // 4)
                y2 = random.randint(minH, minH + (maxH - minH) // 4)
            elif deform_level == "medium":
                x2 = random.randint(minW, minW + (maxW - minW) // 2)
                y2 = random.randint(minH, minH + (maxH - minH) // 2)
            elif deform_level == "high":
                x2 = random.randint(minW, maxW)
                y2 = random.randint(minH, maxH)

            if color_mode == "random":
                color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            elif color_mode == "scheme":
                scheme_colors = color_schemes.get(color_scheme, [(128, 128, 128)])
                color = random.choice(scheme_colors)
            elif color_mode == "solid":
                try:
                    color = tuple(int(solid_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
                except:
                    color = (255, 255, 255)  # Default to white if invalid hex

            if shape_type == "rectangle":
                img1.rectangle([(x1, y1), (x1 + x2, y1 + y2)], fill=color, outline=color)
            elif shape_type == "ellipse":
                img1.ellipse([(x1, y1), (x1 + x2, y1 + y2)], fill=color, outline=color)
            elif shape_type == "polygon":
                num_points = random.randint(3, 6)
                points = [(random.randint(0, w), random.randint(0, h)) for _ in range(num_points)]
                img1.polygon(points, fill=color, outline=color)
            elif shape_type == "triangle":
                points = [
                    (x1, y1),
                    (x1 + random.randint(-x2, x2), y1 + y2),
                    (x1 + x2, y1 + random.randint(-y2, y2))
                ]
                img1.polygon(points, fill=color, outline=color)
            elif shape_type == "circle":
                radius = min(x2, y2) // 2
                img1.ellipse([(x1 - radius, y1 - radius), (x1 + radius, y1 + radius)], fill=color, outline=color)

        # Parse text color
        try:
            if text_color.startswith("#"):
                parsed_text_color = tuple(int(text_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            else:
                # Named colors (basic support)
                color_map = {
                    "black": (0, 0, 0),
                    "white": (255, 255, 255),
                    "red": (255, 0, 0),
                    "green": (0, 255, 0),
                    "blue": (0, 0, 255),
                    "yellow": (255, 255, 0),
                    "purple": (128, 0, 128),
                    "orange": (255, 165, 0),
                    "gray": (128, 128, 128)
                }
                parsed_text_color = color_map.get(text_color.lower(), (0, 0, 0))
        except:
            parsed_text_color = (0, 0, 0)  # Default to black

        if top_left_text_enabled:
            if top_left_text_mode == "random":
                random_top_left_text = generate_string(30, charset="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:',.<>?/")
            elif top_left_text_mode == "word":
                random_top_left_text = generate_word(words_topic)
            else:
                random_top_left_text = ""

            # Position text based on text_position setting
            if text_position == "top-left" or text_position == "random" and random.random() < 0.2:
                img1.text((10, 10), random_top_left_text, font=fnt, fill=parsed_text_color)
            elif text_position == "top-right" or text_position == "random" and random.random() < 0.2:
                text_width = img1.textlength(random_top_left_text, font=fnt)
                img1.text((w - text_width - 10, 10), random_top_left_text, font=fnt, fill=parsed_text_color)
            elif text_position == "bottom-left" or text_position == "random" and random.random() < 0.2:
                img1.text((10, h - font_size - 10), random_top_left_text, font=fnt, fill=parsed_text_color)
            elif text_position == "bottom-right" or text_position == "random" and random.random() < 0.2:
                text_width = img1.textlength(random_top_left_text, font=fnt)
                img1.text((w - text_width - 10, h - font_size - 10), random_top_left_text, font=fnt, fill=parsed_text_color)
            elif text_position == "center" or text_position == "random":
                text_width = img1.textlength(random_top_left_text, font=fnt)
                img1.text((w//2 - text_width//2, h//2 - font_size//2), random_top_left_text, font=fnt, fill=parsed_text_color)

        # Add video name to bottom-left corner
        video_name_text = f"{video_name}.mp4"
        video_name_width = img1.textlength(video_name_text, font=fnt)
        video_name_height = font_size
        img1.text((10, h - video_name_height - 10), video_name_text, font=fnt, fill=parsed_text_color)

        # Move slide info text to the top right corner
        slide_text = f"Slide {i}"
        text_width = img1.textlength(slide_text, font=fnt)
        text_height = font_size
        img1.text((w - text_width - 10, 10), slide_text, font=fnt, fill=parsed_text_color)

        img.save(f"./IMG/{str(i).zfill(4)}_{random.randint(1000, 9999)}.png")

    print("IMAGE GENERATION DONE")

    audio = []

    for i in range(LENGTH):
        append_wave(None, duration_milliseconds=slide_duration, volume=0.25)

    save_wav("./SOUND/output.wav")

    print("WAV GENERATED")

    wav_audio = AudioSegment.from_file("./SOUND/output.wav", format="wav")

    if tts_enabled:
        try:
            tts_audio = AudioSegment.from_file(tts_audio_file, format="mp3")
            combined_audio = wav_audio.overlay(tts_audio, position=0)
        except Exception as e:
            print(f"Error overlaying TTS audio: {e}")
            combined_audio = wav_audio
    else:
        combined_audio = wav_audio

    combined_audio.export("./SOUND/output.m4a", format="adts")

    print("AUDIO GENERATED")

    image_folder = './IMG'
    fps = 1000 / slide_duration  # Ensure fps is precise to handle timing discrepancies

    image_files = sorted([f for f in glob.glob(f"{image_folder}/*.png")], key=lambda x: int(os.path.basename(x).split('_')[0]))

    # Ensure all frames have the same dimensions
    frames = []
    first_frame = np.array(Image.open(image_files[0]))
    for idx, file in enumerate(image_files):
        frame = np.array(Image.open(file))
        if frame.shape != first_frame.shape:
            print(f"Frame {idx} has inconsistent dimensions: {frame.shape} vs {first_frame.shape}")
            frame = np.resize(frame, first_frame.shape)  # Resize if necessary
        frames.append(frame)

    print("Starting video compilation...")
    clip = moviepy.video.io.ImageSequenceClip.ImageSequenceClip(
        frames, fps=fps
    )
    clip.write_videofile(
        f'./OUTPUT/{video_name}.mp4',
        audio="./SOUND/output.m4a",
        codec="libx264",
        audio_codec="aac"
    )

    print("Video compilation finished successfully!")
