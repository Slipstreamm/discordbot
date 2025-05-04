import subprocess
import sys
import os

def install_dependencies():
    """Install the required dependencies for Stable Diffusion."""
    print("Installing Stable Diffusion dependencies...")
    
    # List of required packages
    packages = [
        "torch",
        "diffusers",
        "transformers",
        "accelerate"
    ]
    
    # Check if CUDA is available
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            cuda_version = torch.version.cuda
            print(f"CUDA is available (version {cuda_version})")
            print(f"GPU: {torch.cuda.get_device_name(0)}")
        else:
            print("CUDA is not available. Stable Diffusion will run on CPU (very slow).")
    except ImportError:
        print("PyTorch not installed yet. Will install with CUDA support.")
        cuda_available = False
    
    # Install each package
    for package in packages:
        print(f"Installing {package}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"Successfully installed {package}")
        except subprocess.CalledProcessError as e:
            print(f"Error installing {package}: {e}")
            return False
    
    print("\nAll dependencies installed successfully!")
    print("\nTo use the Stable Diffusion command:")
    print("1. Restart your bot")
    print("2. Use the /generate command with a text prompt")
    print("3. Wait for the image to be generated (this may take some time)")
    
    return True

if __name__ == "__main__":
    install_dependencies()
