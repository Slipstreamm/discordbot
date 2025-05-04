# Manual Download Instructions for Illustrious XL

If the automatic download script fails, you can manually download and set up the Illustrious XL model by following these steps:

## Step 1: Download the Model Files

1. Download the Illustrious XL model from Civitai:
   - Go to: https://civitai.com/models/795765/illustrious-xl
   - Click the "Download" button to download the model file
   - Save the file as `illustrious_xl.safetensors`

2. Download the base SDXL model components from Hugging Face:
   - Go to: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
   - Download the following files/folders:
     - `vae` folder
     - `text_encoder` folder
     - `text_encoder_2` folder
     - `tokenizer` folder
     - `tokenizer_2` folder
     - `scheduler` folder

## Step 2: Set Up the Directory Structure

1. Create the following directory structure in your Discord bot folder:
   ```
   discordbot/
   └── models/
       └── illustrious_xl/
           ├── unet/
           ├── vae/
           ├── text_encoder/
           ├── text_encoder_2/
           ├── tokenizer/
           └── tokenizer_2/
   ```

2. Place the downloaded files in the appropriate directories:
   - Move `illustrious_xl.safetensors` to `discordbot/models/illustrious_xl/unet/` and rename it to `diffusion_pytorch_model.safetensors`
   - Copy the contents of the downloaded `vae` folder to `discordbot/models/illustrious_xl/vae/`
   - Copy the contents of the downloaded `text_encoder` folder to `discordbot/models/illustrious_xl/text_encoder/`
   - Copy the contents of the downloaded `text_encoder_2` folder to `discordbot/models/illustrious_xl/text_encoder_2/`
   - Copy the contents of the downloaded `tokenizer` folder to `discordbot/models/illustrious_xl/tokenizer/`
   - Copy the contents of the downloaded `tokenizer_2` folder to `discordbot/models/illustrious_xl/tokenizer_2/`

## Step 3: Create the Model Index File

Create a file named `model_index.json` in the `discordbot/models/illustrious_xl/` directory with the following content:

```json
{
  "_class_name": "StableDiffusionXLPipeline",
  "_diffusers_version": "0.21.4",
  "force_zeros_for_empty_prompt": true,
  "scheduler": {
    "_class_name": "DPMSolverMultistepScheduler",
    "_diffusers_version": "0.21.4",
    "beta_end": 0.012,
    "beta_schedule": "scaled_linear",
    "beta_start": 0.00085,
    "num_train_timesteps": 1000,
    "prediction_type": "epsilon",
    "solver_order": 2,
    "solver_type": "midpoint",
    "thresholding": false,
    "timestep_spacing": "leading",
    "trained_betas": null,
    "use_karras_sigmas": true
  },
  "text_encoder": [
    {
      "_class_name": "CLIPTextModel",
      "_diffusers_version": "0.21.4"
    },
    {
      "_class_name": "CLIPTextModelWithProjection",
      "_diffusers_version": "0.21.4"
    }
  ],
  "tokenizer": [
    {
      "_class_name": "CLIPTokenizer",
      "_diffusers_version": "0.21.4"
    },
    {
      "_class_name": "CLIPTokenizer",
      "_diffusers_version": "0.21.4"
    }
  ],
  "unet": {
    "_class_name": "UNet2DConditionModel",
    "_diffusers_version": "0.21.4"
  },
  "vae": {
    "_class_name": "AutoencoderKL",
    "_diffusers_version": "0.21.4"
  }
}
```

## Step 4: Verify the Installation

1. Check that the directory structure is correct and all files are in place
2. Make sure the `diffusion_pytorch_model.safetensors` file in the `unet` directory is large (should be several GB)
3. Restart your Discord bot
4. Use the `/generate` command to test if the model works correctly

## Troubleshooting

- If you get errors about missing files, make sure all the required components are downloaded and placed in the correct directories
- If you get CUDA out-of-memory errors, try reducing the image dimensions (e.g., 768x768 instead of 1024x1024)
- If the model is not showing up in the `/sd_models` command, make sure the directory structure and file names are exactly as specified above
