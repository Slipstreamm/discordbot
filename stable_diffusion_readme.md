# Stable Diffusion Discord Bot Command

This feature adds a Stable Diffusion image generation command to your Discord bot, running locally on your GPU. It includes support for the Illustrious XL model from Civitai.

## Installation

1. Run the installation script to install the required dependencies:
   ```
   python install_stable_diffusion.py
   ```

2. Download the Illustrious XL model from Civitai:
   ```
   python download_illustrious.py
   ```

3. Make sure you have a compatible GPU with CUDA support. The command will work on CPU but will be extremely slow.

4. Restart your bot after installing the dependencies and downloading the model.

## Commands

### `/generate`
Generate an image using Stable Diffusion running locally on your GPU.

**Parameters:**
- `prompt` (required): The text prompt to generate an image from
- `negative_prompt` (optional): Things to avoid in the generated image
- `steps` (optional, default: 30): Number of inference steps (higher = better quality but slower)
- `guidance_scale` (optional, default: 7.5): How closely to follow the prompt (higher = more faithful but less creative)
- `width` (optional, default: 1024): Image width (must be a multiple of 8)
- `height` (optional, default: 1024): Image height (must be a multiple of 8)
- `seed` (optional): Random seed for reproducible results (leave empty for random)
- `hidden` (optional, default: false): Whether to make the response visible only to you

### `/sd_models`
List available Stable Diffusion models or change the current model (owner only).

**Parameters:**
- `model` (optional): The model to switch to (leave empty to just list available models)

## Available Models

- **Illustrious XL** (Local) - A high-quality SDXL model from Civitai
- Stable Diffusion 1.5 (`runwayml/stable-diffusion-v1-5`)
- Stable Diffusion 2.1 (`stabilityai/stable-diffusion-2-1`)
- Stable Diffusion XL (`stabilityai/stable-diffusion-xl-base-1.0`)

## About Illustrious XL

Illustrious XL is a high-quality SDXL model from Civitai that produces excellent results for a wide range of prompts. It's particularly good at:

- Detailed illustrations
- Realistic images
- Fantasy and sci-fi scenes
- Character portraits
- Landscapes and environments

The model is automatically downloaded and set up by the `download_illustrious.py` script. You can find more information about the model at [Civitai](https://civitai.com/models/795765/illustrious-xl).

## Requirements

- CUDA-compatible GPU with at least 8GB VRAM (12GB+ recommended for SDXL models at 1024x1024)
- Python 3.8+
- PyTorch with CUDA support
- diffusers library
- transformers library
- accelerate library
- safetensors library
- xformers library (optional, for memory efficiency)

## Troubleshooting

- If you encounter CUDA out-of-memory errors, try:
  - Reducing the image dimensions (e.g., 768x768 instead of 1024x1024)
  - Switching to a smaller model (SD 1.5 instead of SDXL)
  - Closing other applications that use GPU memory
  - Using the `--enable_attention_slicing` option when loading the model

- The first generation might take longer as the model needs to be downloaded and loaded into memory.

- If you're getting "CUDA not available" errors, make sure your GPU drivers are up to date and PyTorch is installed with CUDA support.

- If the Illustrious XL model fails to download, you can try downloading it manually from [Civitai](https://civitai.com/models/795765/illustrious-xl) and placing it in the `discordbot/models/illustrious_xl/unet` directory as `diffusion_pytorch_model.safetensors`.
