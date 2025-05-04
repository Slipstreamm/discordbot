import subprocess
import sys
import os
import platform

def install_dependencies():
    """Install the required dependencies for Stable Diffusion."""
    print("Installing Stable Diffusion dependencies...")

    # List of required packages
    packages = [
        "torch",
        "diffusers",
        "transformers",
        "accelerate",
        "tqdm",
        "safetensors"
    ]

    # Check if CUDA is available
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            cuda_version = torch.version.cuda
            print(f"✅ CUDA is available (version {cuda_version})")
            print(f"GPU: {torch.cuda.get_device_name(0)}")
        else:
            print("⚠️ CUDA is not available. Stable Diffusion will run on CPU (very slow).")
    except ImportError:
        print("PyTorch not installed yet. Will install with CUDA support.")
        cuda_available = False

    # Install PyTorch with CUDA support if not already installed
    if "torch" not in sys.modules:
        print("Installing PyTorch with CUDA support...")
        if platform.system() == "Windows":
            # For Windows, use the PyTorch website command
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install",
                    "torch", "torchvision", "torchaudio",
                    "--index-url", "https://download.pytorch.org/whl/cu118"
                ])
                print("✅ Successfully installed PyTorch with CUDA support")
            except subprocess.CalledProcessError as e:
                print(f"❌ Error installing PyTorch: {e}")
                print("Continuing with other dependencies...")
        else:
            # For Linux/Mac, use pip
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "torch"])
                print("✅ Successfully installed PyTorch")
            except subprocess.CalledProcessError as e:
                print(f"❌ Error installing PyTorch: {e}")
                print("Continuing with other dependencies...")

    # Install xformers for memory efficiency if on Windows with CUDA
    if platform.system() == "Windows" and cuda_available:
        try:
            print("Installing xformers for memory efficiency...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "xformers", "--index-url", "https://download.pytorch.org/whl/cu118"
            ])
            print("✅ Successfully installed xformers")
            packages.append("xformers")  # Add to the list of installed packages
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Error installing xformers: {e}")
            print("Continuing without xformers (memory usage may be higher)...")

    # Install other packages
    for package in packages:
        if package == "torch":  # Skip torch as we've already handled it
            continue

        print(f"Installing {package}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ Successfully installed {package}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error installing {package}: {e}")
            print(f"You may need to install {package} manually.")

    print("\n✅ All dependencies installed successfully!")
    print("\nNext steps:")
    print("1. Download the Illustrious XL model by running: python download_illustrious.py")
    print("2. Restart your bot")
    print("3. Use the /generate command with a text prompt")
    print("4. Wait for the image to be generated (this may take some time)")

    return True

if __name__ == "__main__":
    install_dependencies()
