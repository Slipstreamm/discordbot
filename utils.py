import os
import sys

def reload_script():
    """Restart the current Python script."""
    os.execv(sys.executable, [sys.executable] + sys.argv)
