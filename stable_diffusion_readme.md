# Stable Diffusion Discord Bot Command

This feature adds a Stable Diffusion image generation command to your Discord bot, running locally on your GPU.

## Installation

1. Run the installation script to install the required dependencies:
   ```
   python install_stable_diffusion.py
   ```

2. Make sure you have a compatible GPU with CUDA support. The command will work on CPU but will be extremely slow.

3. Restart your bot after installing the dependencies.

## Commands

### `/generate`
Generate an image using Stable Diffusion running locally on your GPU.

**Parameters:**
- `prompt` (required): The text prompt to generate an image from
- `negative_prompt` (optional): Things to avoid in the generated image
- `steps` (optional, default: 30): Number of inference steps (higher = better quality but slower)
- `guidance_scale` (optional, default: 7.5): How closely to follow the prompt (higher = more faithful but less creative)
- `width` (optional, default: 512): Image width (must be a multiple of 8)
- `height` (optional, default: 512): Image height (must be a multiple of 8)
- `seed` (optional): Random seed for reproducible results (leave empty for random)
- `hidden` (optional, default: false): Whether to make the response visible only to you

### `/sd_models`
List available Stable Diffusion models or change the current model (owner only).

**Parameters:**
- `model` (optional): The model to switch to (leave empty to just list available models)

## Available Models

- Stable Diffusion 1.5 (`runwayml/stable-diffusion-v1-5`)
- Stable Diffusion 2.1 (`stabilityai/stable-diffusion-2-1`)
- Stable Diffusion XL (`stabilityai/stable-diffusion-xl-base-1.0`)

## Requirements

- CUDA-compatible GPU with at least 4GB VRAM (8GB+ recommended for larger images)
- Python 3.8+
- PyTorch with CUDA support
- diffusers library
- transformers library
- accelerate library

## Troubleshooting

- If you encounter CUDA out-of-memory errors, try reducing the image dimensions or using a smaller model.
- The first generation might take longer as the model needs to be loaded into memory.
- If you're getting "CUDA not available" errors, make sure your GPU drivers are up to date and PyTorch is installed with CUDA support.
