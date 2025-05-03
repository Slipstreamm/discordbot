"""
Code verifier store for the API service.

This module provides a simple in-memory store for code verifiers used in the OAuth flow.
"""

from typing import Dict, Optional

# In-memory storage for code verifiers
code_verifiers: Dict[str, str] = {}

def store_code_verifier(state: str, code_verifier: str) -> None:
    """Store a code verifier for a state."""
    code_verifiers[state] = code_verifier
    print(f"Stored code verifier for state {state}: {code_verifier[:10]}...")

def get_code_verifier(state: str) -> Optional[str]:
    """Get the code verifier for a state."""
    return code_verifiers.get(state)

def remove_code_verifier(state: str) -> None:
    """Remove a code verifier for a state."""
    if state in code_verifiers:
        del code_verifiers[state]
        print(f"Removed code verifier for state {state}")
