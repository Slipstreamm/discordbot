import os
import subprocess
import sys
import time

def reload_script():
    """Restart the current Python script."""
    try:
        time.sleep(1)  # sleep to allow server response
        result = subprocess.run(["git", "pull"], check=True, text=True, capture_output=True)
        print(result.stdout)  # Print the output of the git pull command
    except subprocess.CalledProcessError as e:
        print(f"Error during git pull: {e.stderr}")
        return
    os.execv(sys.executable, [sys.executable] + sys.argv)
