# discordbot/global_bot_accessor.py
"""
This module provides a global accessor for the bot instance.
It helps to avoid circular dependencies when other modules need access
to the bot instance, especially its shared resources like connection pools.
"""

_bot_instance = None

def set_bot_instance(bot_instance_ref):
    """
    Sets the global bot instance. Should be called once from main.py
    after the bot object is created.
    """
    global _bot_instance
    if _bot_instance is not None and _bot_instance != bot_instance_ref :
        # This might indicate an issue if called multiple times with different instances
        print(f"WARNING: Global bot instance is being overwritten. Old ID: {id(_bot_instance)}, New ID: {id(bot_instance_ref)}")
    _bot_instance = bot_instance_ref

def get_bot_instance():
    """
    Retrieves the global bot instance.
    Returns None if set_bot_instance has not been called.
    """
    return _bot_instance
