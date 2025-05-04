import os
import sys
import requests
import json
import zipfile
import shutil
import argparse
from tqdm import tqdm
import time
import subprocess
import huggingface_hub

# Illustrious XL model information
MODEL_ID = 795765
MODEL_NAME = "Illustrious XL"
MODEL_VERSION = 1  # Version 1.0
MODEL_URL = "https://civitai.com/api/download/models/795765"
MODEL_INFO_URL = f"https://civitai.com/api/v1/models/{MODEL_ID}"

# Base SDXL model from HuggingFace (we'll use this as a base and replace the unet)
SDXL_BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"

def download_file(url, destination, filename=None):
    """Download a file with progress bar"""
    if filename is None:
        local_filename = os.path.join(destination, url.split('/')[-1])
    else:
        local_filename = os.path.join(destination, filename)

    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        total_size = int(r.headers.get('content-length', 0))

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(local_filename), exist_ok=True)

        with open(local_filename, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=f"Downloading {os.path.basename(local_filename)}") as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

    return local_filename

def download_from_huggingface(repo_id, local_dir, component=None):
    """Download a model from HuggingFace"""
    try:
        # Use huggingface_hub to download the model
        if component:
            print(f"Downloading {component} from {repo_id}...")
            huggingface_hub.snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                local_dir_use_symlinks=False,
                allow_patterns=f"{component}/*"
            )
        else:
            print(f"Downloading full model from {repo_id}...")
            huggingface_hub.snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                local_dir_use_symlinks=False
            )
        return True
    except Exception as e:
        print(f"Error downloading from HuggingFace: {e}")
        return False

def download_illustrious_xl():
    """Download and set up the Illustrious XL model"""
    # Set up directories
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(script_dir, "models")
    illustrious_dir = os.path.join(models_dir, "illustrious_xl")
    temp_dir = os.path.join(models_dir, "temp")

    # Create directories if they don't exist
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    # Check if model already exists
    if os.path.exists(os.path.join(illustrious_dir, "unet", "diffusion_pytorch_model.safetensors")) and \
       os.path.getsize(os.path.join(illustrious_dir, "unet", "diffusion_pytorch_model.safetensors")) > 100000000:  # Check if file is larger than 100MB
        print(f"⚠️ {MODEL_NAME} model already exists at {illustrious_dir}")
        choice = input("Do you want to re-download and reinstall the model? (y/n): ")
        if choice.lower() != 'y':
            print("Download cancelled.")
            return

        # Remove existing model
        print(f"Removing existing {MODEL_NAME} model...")
        shutil.rmtree(illustrious_dir, ignore_errors=True)

    # Create illustrious directory
    os.makedirs(illustrious_dir, exist_ok=True)

    # Get model info from Civitai API
    print(f"Fetching information about {MODEL_NAME} from Civitai...")
    try:
        response = requests.get(MODEL_INFO_URL)
        response.raise_for_status()
        model_info = response.json()

        # Save model info for reference
        with open(os.path.join(illustrious_dir, "model_info.json"), "w") as f:
            json.dump(model_info, f, indent=2)

        print(f"Model: {model_info['name']} by {model_info['creator']['username']}")
        if 'description' in model_info:
            print(f"Description: {model_info['description'][:100]}...")

    except Exception as e:
        print(f"⚠️ Failed to fetch model info: {e}")
        print("Continuing with download anyway...")

    # First, download the base SDXL model from HuggingFace
    print(f"Step 1: Downloading base SDXL model from HuggingFace...")
    print("This will download the VAE, text encoders, and tokenizers needed for the model.")
    print("This may take a while (several GB of data)...")

    # Download each component separately to avoid downloading the full model
    components = ["vae", "text_encoder", "text_encoder_2", "tokenizer", "tokenizer_2", "scheduler"]
    for component in components:
        success = download_from_huggingface(SDXL_BASE_MODEL, illustrious_dir, component)
        if not success:
            print(f"Failed to download {component} from HuggingFace.")
            print("Trying alternative method...")

            # Try using diffusers to download the model
            try:
                print(f"Installing diffusers if not already installed...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "diffusers"])

                # Use Python to download the model components
                from diffusers import StableDiffusionXLPipeline
                print(f"Downloading {component} using diffusers...")

                # Create a temporary directory for the download
                temp_model_dir = os.path.join(temp_dir, "sdxl_base")
                os.makedirs(temp_model_dir, exist_ok=True)

                # Download only the specified components
                StableDiffusionXLPipeline.from_pretrained(
                    SDXL_BASE_MODEL,
                    torch_dtype="float16",
                    variant="fp16",
                    use_safetensors=True,
                    cache_dir=temp_model_dir
                )

                # Copy the component to the illustrious directory
                component_dir = os.path.join(temp_model_dir, component)
                if os.path.exists(component_dir):
                    shutil.copytree(component_dir, os.path.join(illustrious_dir, component), dirs_exist_ok=True)
                    print(f"Successfully copied {component} to {illustrious_dir}")
                else:
                    print(f"Could not find {component} in downloaded model.")

            except Exception as e:
                print(f"Error using diffusers to download {component}: {e}")
                print("You may need to manually download the SDXL base model and copy the components.")

    # Now download the Illustrious XL model from Civitai
    print(f"\nStep 2: Downloading {MODEL_NAME} from Civitai...")
    try:
        # Download to temp directory
        model_file = download_file(MODEL_URL, temp_dir, "illustrious_xl.safetensors")

        # Create the unet directory if it doesn't exist
        os.makedirs(os.path.join(illustrious_dir, "unet"), exist_ok=True)

        # Move the model file to the unet directory
        print(f"Moving {MODEL_NAME} model to the unet directory...")
        shutil.move(model_file, os.path.join(illustrious_dir, "unet", "diffusion_pytorch_model.safetensors"))

        # Create a model_index.json file
        print("Creating model_index.json file...")
        model_index = {
            "_class_name": "StableDiffusionXLPipeline",
            "_diffusers_version": "0.21.4",
            "force_zeros_for_empty_prompt": True,
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
                "thresholding": False,
                "timestep_spacing": "leading",
                "trained_betas": None,
                "use_karras_sigmas": True
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

        with open(os.path.join(illustrious_dir, "model_index.json"), "w") as f:
            json.dump(model_index, f, indent=2)

        # Create a README.md file with information about the model
        with open(os.path.join(illustrious_dir, "README.md"), "w") as f:
            f.write(f"# {MODEL_NAME}\n\n")
            f.write(f"Downloaded from Civitai: https://civitai.com/models/{MODEL_ID}\n\n")
            f.write("This model requires the diffusers library to use.\n")
            f.write("Use the /generate command in the Discord bot to generate images with this model.\n")

        # Check if the model file is large enough (should be several GB)
        unet_file = os.path.join(illustrious_dir, "unet", "diffusion_pytorch_model.safetensors")
        if os.path.exists(unet_file):
            file_size_gb = os.path.getsize(unet_file) / (1024 * 1024 * 1024)
            print(f"Model file size: {file_size_gb:.2f} GB")

            if file_size_gb < 1.0:
                print(f"⚠️ Warning: Model file seems too small ({file_size_gb:.2f} GB). It may not be complete.")
                print("The download might have been interrupted or the model might not be the full version.")
                print("You may want to try downloading again with the --force flag.")

        print(f"\n✅ {MODEL_NAME} model has been downloaded and set up successfully!")
        print(f"Model location: {illustrious_dir}")
        print("You can now use the model with the /generate command in the Discord bot.")

    except Exception as e:
        print(f"❌ Error downloading or setting up the model: {e}")
        import traceback
        traceback.print_exc()

        # Clean up
        print("Cleaning up...")
        shutil.rmtree(illustrious_dir, ignore_errors=True)
        shutil.rmtree(temp_dir, ignore_errors=True)

        print("Download failed. Please try again later.")
        return False

    # Clean up temp directory
    shutil.rmtree(temp_dir, ignore_errors=True)

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"Download and set up the {MODEL_NAME} model from Civitai")
    parser.add_argument("--force", action="store_true", help="Force download even if the model already exists")
    args = parser.parse_args()

    if args.force:
        # Remove existing model if it exists
        script_dir = os.path.dirname(os.path.abspath(__file__))
        illustrious_dir = os.path.join(script_dir, "models", "illustrious_xl")
        if os.path.exists(illustrious_dir):
            print(f"Removing existing {MODEL_NAME} model...")
            shutil.rmtree(illustrious_dir, ignore_errors=True)

    download_illustrious_xl()
