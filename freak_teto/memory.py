# Import the MemoryManager from the parent directory
# Use a direct import path that doesn't rely on package structure
import os
import importlib.util

# Get the absolute path to the shared gurt_memory.py (this path remains correct)
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
shared_memory_path = os.path.join(parent_dir, 'gurt_memory.py') # Renamed variable for clarity

# Load the module dynamically
spec = importlib.util.spec_from_file_location('gurt_memory', shared_memory_path) # Module name 'gurt_memory' must match the filename
shared_memory_module = importlib.util.module_from_spec(spec) # Renamed variable
spec.loader.exec_module(shared_memory_module)

# Import the MemoryManager class from the loaded module
MemoryManager = shared_memory_module.MemoryManager

# Re-export the MemoryManager class
__all__ = ['MemoryManager']
