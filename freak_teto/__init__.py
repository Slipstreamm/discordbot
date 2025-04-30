# This file makes the 'freak_teto' directory a Python package.
# It allows Python to properly import modules from this directory

# Export the setup function for discord.py extension loading
from .cog import setup

# This makes "from freak_teto import setup" work
__all__ = ['setup']
