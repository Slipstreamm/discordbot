# Import the MemoryManager from the parent directory
# Use a direct import path that doesn't rely on package structure
import os
import importlib.util

# Get the absolute path to gurt_memory.py
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gurt_memory_path = os.path.join(parent_dir, 'gurt_memory.py')

# Load the module dynamically
spec = importlib.util.spec_from_file_location('gurt_memory', gurt_memory_path)
gurt_memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gurt_memory)

# Import the MemoryManager class from the loaded module
MemoryManager = gurt_memory.MemoryManager

# Re-export the MemoryManager class
__all__ = ['MemoryManager']
