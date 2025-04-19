import random
from PIL import Image, ImageDraw, ImageFont
import math
import wave
import struct
from pydub import AudioSegment
from gtts import gTTS
import os
import moviepy.video.io.ImageSequenceClip
import glob
import json
import numpy as np
import nltk
from nltk.corpus import words, wordnet

nltk.download('words')
nltk.download('wordnet')

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
tts_enabled = config_data.get("TTS_ENABLED", True)
tts_text = config_data.get("TTS_TEXT", "This is a default text for TTS.")
audio_wave_type = config_data.get("AUDIO_WAVE_TYPE", "sawtooth")  # Options: sawtooth, sine, square
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

# Vibe presets for wave sound
wave_vibes = {
    "calm": {"frequency": 200, "amplitude": 0.3, "modulation": 0.1},
    "eerie": {"frequency": 600, "amplitude": 0.5, "modulation": 0.7},
    "random": {},  # Randomized values will be generated
    "energetic": {"frequency": 800, "amplitude": 0.7, "modulation": 0.2},
    "dreamy": {"frequency": 400, "amplitude": 0.4, "modulation": 0.5},
    "chaotic": {"frequency": 1000, "amplitude": 1.0, "modulation": 1.0},
}

color_schemes = {
    "pastel": [(255, 182, 193), (176, 224, 230), (240, 230, 140), (221, 160, 221), (152, 251, 152)],
    "dark_gritty": [(47, 79, 79), (105, 105, 105), (0, 0, 0), (85, 107, 47), (139, 69, 19)],
    "nature": [(34, 139, 34), (107, 142, 35), (46, 139, 87), (32, 178, 170), (154, 205, 50)],
    "vibrant": [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)],
    "ocean": [(0, 105, 148), (72, 209, 204), (70, 130, 180), (135, 206, 250), (176, 224, 230)]
}

# Font scaling based on video size
font_size = max(w, h) // 40  # Scales font size to make it smaller and more readable
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

# Predefined word lists for specific topics
introspective_words = ["reflection", "thought", "solitude", "ponder", "meditation", "introspection", "awareness", "contemplation", "silence", "stillness"]
action_words = ["run", "jump", "climb", "race", "fight", "explore", "build", "create", "overcome", "achieve"]
nature_words = ["tree", "mountain", "river", "ocean", "flower", "forest", "animal", "sky", "valley", "meadow"]
technology_words = ["computer", "robot", "network", "data", "algorithm", "innovation", "digital", "machine", "software", "hardware"]

def generate_word(theme="random"):
    if theme == "introspective":
        return random.choice(introspective_words)
    elif theme == "action":
        return random.choice(action_words)
    elif theme == "nature":
        return random.choice(nature_words)
    elif theme == "technology":
        return random.choice(technology_words)
    elif theme == "random":
        return random.choice(words.words())
    else:
        return "unknown_theme"

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
        wave_sample = amplitude * math.sin(2 * math.pi * freq * (x / sample_rate))
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

# Generate TTS audio using gTTS
def generate_tts_audio(text, output_file):
    tts = gTTS(text=text, lang='en')
    tts.save(output_file)
    print(f"TTS audio saved to {output_file}")

if tts_enabled:
    tts_audio_file = "./SOUND/tts_output.mp3"
    generate_tts_audio(tts_text, tts_audio_file)

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
                color = tuple(int(solid_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

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
            elif shape_type == "star":
                points = []
                for j in range(5):
                    outer_x = x1 + int(x2 * math.cos(j * 2 * math.pi / 5))
                    outer_y = y1 + int(y2 * math.sin(j * 2 * math.pi / 5))
                    points.append((outer_x, outer_y))
                    inner_x = x1 + int(x2 / 2 * math.cos((j + 0.5) * 2 * math.pi / 5))
                    inner_y = y1 + int(y2 / 2 * math.sin((j + 0.5) * 2 * math.pi / 5))
                    points.append((inner_x, inner_y))
                img1.polygon(points, fill=color, outline=color)
            elif shape_type == "circle":
                radius = min(x2, y2) // 2
                img1.ellipse([(x1 - radius, y1 - radius), (x1 + radius, y1 + radius)], fill=color, outline=color)

        if top_left_text_enabled:
            if top_left_text_mode == "random":
                random_top_left_text = generate_string(30, charset="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:',.<>?/")
            elif top_left_text_mode == "word":
                random_top_left_text = generate_word(words_topic)
            else:
                random_top_left_text = ""
            img1.text((10, 10), random_top_left_text, font=fnt, fill="black")

        # Add video name to bottom-left corner
        video_name_text = f"{video_name}.mp4"
        video_name_width = img1.textlength(video_name_text, font=fnt)
        video_name_height = font_size
        img1.text((10, h - video_name_height - 10), video_name_text, font=fnt, fill="black")

        # Move slide info text to the top right corner
        slide_text = f"Slide {i}"
        text_width = img1.textlength(slide_text, font=fnt)
        text_height = font_size
        img1.text((w - text_width - 10, 10), slide_text, font=fnt, fill="black")

        img.save(f"./IMG/{str(i).zfill(4)}_{random.randint(1000, 9999)}.png")

    print("IMAGE GENERATION DONE")

    audio = []

    for i in range(LENGTH):
        append_wave(None, duration_milliseconds=slide_duration, volume=0.25)

    save_wav("./SOUND/output.wav")

    print("WAV GENERATED")

    wav_audio = AudioSegment.from_file("./SOUND/output.wav", format="wav")

    if tts_enabled:
        tts_audio = AudioSegment.from_file(tts_audio_file, format="mp3")
        combined_audio = wav_audio.overlay(tts_audio, position=0)
    else:
        combined_audio = wav_audio

    combined_audio.export("./SOUND/output.m4a", format="adts")

    print("MP3 GENERATED")

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
