import discord
from discord.ext import commands
from discord import app_commands
import torch
from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline, DPMSolverMultistepScheduler
import os
import io
import time
import asyncio
import json
from typing import Optional, Literal, Dict, Any, Union

class StableDiffusionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Set up model directories
        self.models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
        self.illustrious_dir = os.path.join(self.models_dir, "illustrious_xl")

        # Create directories if they don't exist
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.illustrious_dir, exist_ok=True)

        # Default to Illustrious XL if available, otherwise fallback to SD 1.5
        self.model_id = self.illustrious_dir if os.path.exists(os.path.join(self.illustrious_dir, "model_index.json")) else "runwayml/stable-diffusion-v1-5"
        self.model_type = "sdxl" if self.model_id == self.illustrious_dir else "sd"
        self.is_generating = False

        print(f"StableDiffusionCog initialized! Using device: {self.device}")
        print(f"Default model: {self.model_id} (Type: {self.model_type})")

        # Check if Illustrious XL is available
        if self.model_id != self.illustrious_dir:
            print("Illustrious XL model not found. Using default model instead.")
            print(f"To download Illustrious XL, run the download_illustrious.py script.")

    async def load_model(self):
        """Load the Stable Diffusion model asynchronously"""
        if self.model is not None:
            return True

        # This could take some time, so we run it in a thread pool
        loop = asyncio.get_event_loop()
        try:
            # Check if we're loading a local model or a HuggingFace model
            if os.path.isdir(self.model_id):
                # Local model (like Illustrious XL)
                if self.model_type == "sdxl":
                    print(f"Loading local SDXL model from {self.model_id}...")
                    self.model = await loop.run_in_executor(
                        None,
                        lambda: StableDiffusionXLPipeline.from_pretrained(
                            self.model_id,
                            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                            use_safetensors=True,
                            variant="fp16" if self.device == "cuda" else None
                        ).to(self.device)
                    )
                else:
                    print(f"Loading local SD model from {self.model_id}...")
                    self.model = await loop.run_in_executor(
                        None,
                        lambda: StableDiffusionPipeline.from_pretrained(
                            self.model_id,
                            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                            use_safetensors=True,
                            variant="fp16" if self.device == "cuda" else None
                        ).to(self.device)
                    )
            else:
                # HuggingFace model
                if "xl" in self.model_id.lower():
                    self.model_type = "sdxl"
                    print(f"Loading SDXL model from HuggingFace: {self.model_id}...")
                    self.model = await loop.run_in_executor(
                        None,
                        lambda: StableDiffusionXLPipeline.from_pretrained(
                            self.model_id,
                            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                            use_safetensors=True,
                            variant="fp16" if self.device == "cuda" else None
                        ).to(self.device)
                    )
                else:
                    self.model_type = "sd"
                    print(f"Loading SD model from HuggingFace: {self.model_id}...")
                    self.model = await loop.run_in_executor(
                        None,
                        lambda: StableDiffusionPipeline.from_pretrained(
                            self.model_id,
                            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                        ).to(self.device)
                    )

            # Use DPM++ 2M Karras scheduler for better quality
            self.model.scheduler = DPMSolverMultistepScheduler.from_config(
                self.model.scheduler.config,
                algorithm_type="dpmsolver++",
                use_karras_sigmas=True
            )

            # Enable attention slicing for lower memory usage
            if hasattr(self.model, "enable_attention_slicing"):
                self.model.enable_attention_slicing()

            # Enable memory efficient attention if available (for SDXL)
            if hasattr(self.model, "enable_xformers_memory_efficient_attention"):
                try:
                    self.model.enable_xformers_memory_efficient_attention()
                    print("Enabled xformers memory efficient attention")
                except Exception as e:
                    print(f"Could not enable xformers: {e}")

            return True
        except Exception as e:
            print(f"Error loading Stable Diffusion model: {e}")
            import traceback
            traceback.print_exc()
            return False

    @app_commands.command(
        name="generate",
        description="Generate an image using Stable Diffusion running locally on GPU"
    )
    @app_commands.describe(
        prompt="The text prompt to generate an image from",
        negative_prompt="Things to avoid in the generated image",
        steps="Number of inference steps (higher = better quality but slower)",
        guidance_scale="How closely to follow the prompt (higher = more faithful but less creative)",
        width="Image width (must be a multiple of 8)",
        height="Image height (must be a multiple of 8)",
        seed="Random seed for reproducible results (leave empty for random)",
        hidden="Whether to make the response visible only to you"
    )
    async def generate_image(
        self,
        interaction: discord.Interaction,
        prompt: str,
        negative_prompt: Optional[str] = None,
        steps: Optional[int] = 30,
        guidance_scale: Optional[float] = 7.5,
        width: Optional[int] = 1024,
        height: Optional[int] = 1024,
        seed: Optional[int] = None,
        hidden: Optional[bool] = False
    ):
        """Generate an image using Stable Diffusion running locally on GPU"""
        # Check if already generating an image
        if self.is_generating:
            await interaction.response.send_message(
                "⚠️ I'm already generating an image. Please wait until the current generation is complete.",
                ephemeral=True
            )
            return

        # Validate parameters
        if steps < 1 or steps > 150:
            await interaction.response.send_message(
                "⚠️ Steps must be between 1 and 150.",
                ephemeral=True
            )
            return

        if guidance_scale < 1 or guidance_scale > 20:
            await interaction.response.send_message(
                "⚠️ Guidance scale must be between 1 and 20.",
                ephemeral=True
            )
            return

        if width % 8 != 0 or height % 8 != 0:
            await interaction.response.send_message(
                "⚠️ Width and height must be multiples of 8.",
                ephemeral=True
            )
            return

        # Different size limits for SDXL vs regular SD
        max_size = 1536 if self.model_type == "sdxl" else 1024
        min_size = 512 if self.model_type == "sdxl" else 256

        if width < min_size or width > max_size or height < min_size or height > max_size:
            await interaction.response.send_message(
                f"⚠️ Width and height must be between {min_size} and {max_size} for the current model type ({self.model_type.upper()}).",
                ephemeral=True
            )
            return

        # Defer the response since this will take some time
        await interaction.response.defer(ephemeral=hidden)

        # Set the flag to indicate we're generating
        self.is_generating = True

        try:
            # Load the model if not already loaded
            if not await self.load_model():
                await interaction.followup.send(
                    "❌ Failed to load the Stable Diffusion model. Check the logs for details.",
                    ephemeral=hidden
                )
                self.is_generating = False
                return

            # Generate a random seed if none provided
            if seed is None:
                seed = int(time.time())

            # Set the generator for reproducibility
            generator = torch.Generator(device=self.device).manual_seed(seed)

            # Create a status message
            model_name = "Illustrious XL" if self.model_id == self.illustrious_dir else self.model_id
            status_message = f"🖌️ Generating image with {model_name}\n"
            status_message += f"🔤 Prompt: `{prompt}`\n"
            status_message += f"📊 Parameters: Steps={steps}, CFG={guidance_scale}, Size={width}x{height}, Seed={seed}"
            if negative_prompt:
                status_message += f"\n🚫 Negative prompt: `{negative_prompt}`"
            status_message += "\n\n⏳ Please wait, this may take a minute..."

            status = await interaction.followup.send(status_message, ephemeral=hidden)

            # Run the generation in a thread pool to not block the bot
            loop = asyncio.get_event_loop()

            # Different generation parameters for SDXL vs regular SD
            if self.model_type == "sdxl":
                # For SDXL models
                image = await loop.run_in_executor(
                    None,
                    lambda: self.model(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_inference_steps=steps,
                        guidance_scale=guidance_scale,
                        width=width,
                        height=height,
                        generator=generator
                    ).images[0]
                )
            else:
                # For regular SD models
                image = await loop.run_in_executor(
                    None,
                    lambda: self.model(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_inference_steps=steps,
                        guidance_scale=guidance_scale,
                        width=width,
                        height=height,
                        generator=generator
                    ).images[0]
                )

            # Convert the image to bytes for Discord upload
            image_binary = io.BytesIO()
            image.save(image_binary, format="PNG")
            image_binary.seek(0)

            # Create a file to send
            file = discord.File(fp=image_binary, filename="stable_diffusion_image.png")

            # Create an embed with the image and details
            embed = discord.Embed(
                title="🖼️ Stable Diffusion Image",
                description=f"**Prompt:** {prompt}",
                color=0x9C84EF
            )
            if negative_prompt:
                embed.add_field(name="Negative Prompt", value=negative_prompt, inline=False)

            # Add model info to the embed
            model_info = f"Model: {model_name}\nType: {self.model_type.upper()}"
            embed.add_field(name="Model", value=model_info, inline=False)

            # Add generation parameters
            embed.add_field(
                name="Parameters",
                value=f"Steps: {steps}\nGuidance Scale: {guidance_scale}\nSize: {width}x{height}\nSeed: {seed}",
                inline=False
            )

            embed.set_image(url="attachment://stable_diffusion_image.png")
            embed.set_footer(text=f"Generated by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

            # Send the image
            await interaction.followup.send(file=file, embed=embed, ephemeral=hidden)

            # Try to delete the status message
            try:
                await status.delete()
            except:
                pass

        except Exception as e:
            await interaction.followup.send(
                f"❌ Error generating image: {str(e)}",
                ephemeral=hidden
            )
            import traceback
            traceback.print_exc()
        finally:
            # Reset the flag
            self.is_generating = False

    @app_commands.command(
        name="sd_models",
        description="List available Stable Diffusion models or change the current model"
    )
    @app_commands.describe(
        model="The model to switch to (leave empty to just list available models)",
    )
    @app_commands.choices(model=[
        app_commands.Choice(name="Illustrious XL (Local)", value="illustrious_xl"),
        app_commands.Choice(name="Stable Diffusion 1.5", value="runwayml/stable-diffusion-v1-5"),
        app_commands.Choice(name="Stable Diffusion 2.1", value="stabilityai/stable-diffusion-2-1"),
        app_commands.Choice(name="Stable Diffusion XL", value="stabilityai/stable-diffusion-xl-base-1.0")
    ])
    @commands.is_owner()
    async def sd_models(
        self,
        interaction: discord.Interaction,
        model: Optional[app_commands.Choice[str]] = None
    ):
        """List available Stable Diffusion models or change the current model"""
        # Check if user is the bot owner
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message(
                "⛔ Only the bot owner can use this command.",
                ephemeral=True
            )
            return

        if model is None:
            # Just list the available models
            current_model = "Illustrious XL (Local)" if self.model_id == self.illustrious_dir else self.model_id

            embed = discord.Embed(
                title="🤖 Available Stable Diffusion Models",
                description=f"**Current model:** `{current_model}`\n**Type:** `{self.model_type.upper()}`",
                color=0x9C84EF
            )

            # Check if Illustrious XL is available
            illustrious_status = "✅ Installed" if os.path.exists(os.path.join(self.illustrious_dir, "model_index.json")) else "❌ Not installed"

            embed.add_field(
                name="Available Models",
                value=(
                    f"• `Illustrious XL` - {illustrious_status}\n"
                    "• `runwayml/stable-diffusion-v1-5` - Stable Diffusion 1.5\n"
                    "• `stabilityai/stable-diffusion-2-1` - Stable Diffusion 2.1\n"
                    "• `stabilityai/stable-diffusion-xl-base-1.0` - Stable Diffusion XL"
                ),
                inline=False
            )

            # Add download instructions if Illustrious XL is not installed
            if illustrious_status == "❌ Not installed":
                embed.add_field(
                    name="Download Illustrious XL",
                    value=(
                        "To download Illustrious XL, run the `download_illustrious.py` script.\n"
                        "This will download the model from Civitai and set it up for use."
                    ),
                    inline=False
                )

            embed.add_field(
                name="GPU Status",
                value=f"Using device: `{self.device}`\nCUDA available: `{torch.cuda.is_available()}`",
                inline=False
            )
            if torch.cuda.is_available():
                embed.add_field(
                    name="GPU Info",
                    value=f"GPU: `{torch.cuda.get_device_name(0)}`\nMemory: `{torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB`",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Change the model
        await interaction.response.defer(ephemeral=True)

        # Check if we're currently generating
        if self.is_generating:
            await interaction.followup.send(
                "⚠️ Can't change model while generating an image. Please try again later.",
                ephemeral=True
            )
            return

        # Unload the current model to free up VRAM
        if self.model is not None:
            self.model = None
            torch.cuda.empty_cache()

        # Set the new model ID
        if model.value == "illustrious_xl":
            # Check if Illustrious XL is installed
            if not os.path.exists(os.path.join(self.illustrious_dir, "model_index.json")):
                await interaction.followup.send(
                    "❌ Illustrious XL model is not installed. Please run the `download_illustrious.py` script first.",
                    ephemeral=True
                )
                return

            self.model_id = self.illustrious_dir
            self.model_type = "sdxl"
        else:
            self.model_id = model.value
            self.model_type = "sdxl" if "xl" in model.value.lower() else "sd"

        await interaction.followup.send(
            f"✅ Model changed to `{model.name}`. The model will be loaded on the next generation.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(StableDiffusionCog(bot))
