"""
Code verifier store for the API service.

This module provides a simple in-memory store for code verifiers used in the OAuth flow.
It also includes a file-based backup to ensure code verifiers persist across restarts.
"""

import os
import json
import time
from typing import Dict, Optional, Any

# In-memory storage for code verifiers
code_verifiers: Dict[str, Dict[str, Any]] = {}

# File path for persistent storage
STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STORAGE_FILE = os.path.join(STORAGE_DIR, "code_verifiers.json")

# Ensure the storage directory exists
os.makedirs(STORAGE_DIR, exist_ok=True)

def _load_from_file() -> None:
    """Load code verifiers from file."""
    try:
        if os.path.exists(STORAGE_FILE):
            with open(STORAGE_FILE, 'r') as f:
                stored_data = json.load(f)

                # Filter out expired entries (older than 10 minutes)
                current_time = time.time()
                for state, data in stored_data.items():
                    if data.get("timestamp", 0) + 600 > current_time:  # 10 minutes = 600 seconds
                        code_verifiers[state] = data

                print(f"Loaded {len(code_verifiers)} valid code verifiers from file")
    except Exception as e:
        print(f"Error loading code verifiers from file: {e}")

def _save_to_file() -> None:
    """Save code verifiers to file."""
    try:
        with open(STORAGE_FILE, 'w') as f:
            json.dump(code_verifiers, f)
        print(f"Saved {len(code_verifiers)} code verifiers to file")
    except Exception as e:
        print(f"Error saving code verifiers to file: {e}")

# Load existing code verifiers on module import
_load_from_file()

def store_code_verifier(state: str, code_verifier: str) -> None:
    """Store a code verifier for a state."""
    # Store with timestamp for expiration
    code_verifiers[state] = {
        "code_verifier": code_verifier,
        "timestamp": time.time()
    }
    print(f"Stored code verifier for state {state}: {code_verifier[:10]}...")

    # Save to file for persistence
    _save_to_file()

def get_code_verifier(state: str) -> Optional[str]:
    """Get the code verifier for a state."""
    # Check if state exists and is not expired
    data = code_verifiers.get(state)
    if data:
        # Check if expired (older than 10 minutes)
        if data.get("timestamp", 0) + 600 > time.time():
            return data.get("code_verifier")
        else:
            # Remove expired entry
            remove_code_verifier(state)
            print(f"Code verifier for state {state} has expired")
    return None

def remove_code_verifier(state: str) -> None:
    """Remove a code verifier for a state."""
    if state in code_verifiers:
        del code_verifiers[state]
        print(f"Removed code verifier for state {state}")
        # Update the file
        _save_to_file()

def cleanup_expired() -> None:
    """Remove all expired code verifiers."""
    current_time = time.time()
    expired_states = []

    for state, data in code_verifiers.items():
        if data.get("timestamp", 0) + 600 <= current_time:  # 10 minutes = 600 seconds
            expired_states.append(state)

    for state in expired_states:
        del code_verifiers[state]

    if expired_states:
        print(f"Cleaned up {len(expired_states)} expired code verifiers")
        _save_to_file()
