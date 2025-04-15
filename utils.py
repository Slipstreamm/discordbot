import os
import subprocess
import sys

def reload_script():
    """Restart the current Python script."""
    subprocess.run(["git", "pull"], check=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)
