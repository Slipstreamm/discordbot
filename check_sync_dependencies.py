import importlib.util
import subprocess
import sys

def check_and_install_dependencies():
    """Check if required dependencies are installed and install them if not."""
    required_packages = ["fastapi", "uvicorn", "pydantic"]
    missing_packages = []
    
    for package in required_packages:
        if importlib.util.find_spec(package) is None:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"Installing missing dependencies for Discord sync: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            print("Dependencies installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error installing dependencies: {e}")
            print("Please install the following packages manually:")
            for package in missing_packages:
                print(f"  - {package}")
            return False
    
    return True

if __name__ == "__main__":
    check_and_install_dependencies()
