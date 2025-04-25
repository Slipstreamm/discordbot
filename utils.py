import os
import subprocess
import sys
import time

def reload_script():
    """Restart the current Python script."""
    try:
        result = subprocess.run(["git", "pull"], check=True, text=True, capture_output=True)
        print(result.stdout)  # Print the output of the git pull command
    except subprocess.CalledProcessError as e:
        print(f"Error during git pull: {e.stderr}")
        return
    os.execv(sys.executable, [sys.executable] + sys.argv)
