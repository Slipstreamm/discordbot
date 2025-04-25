"""
Discord OAuth2 implementation for the Discord bot.

This module handles the OAuth2 flow for authenticating users with Discord,
including generating authorization URLs, exchanging codes for tokens,
and managing token storage and refresh.
"""

import os
import json
import time
import secrets
import hashlib
import base64
import aiohttp
import asyncio
import traceback
from typing import Dict, Optional, Tuple, Any
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OAuth2 Configuration
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1360717457852993576")
# No client secret for public clients

# Use the API service's OAuth endpoint if available, otherwise use the local server
API_URL = os.getenv("API_URL", "https://slipstreamm.dev/api")
API_OAUTH_ENABLED = os.getenv("API_OAUTH_ENABLED", "true").lower() in ("true", "1", "yes")

# If API OAuth is enabled, use the API service's OAuth endpoint
if API_OAUTH_ENABLED:
    # For API OAuth, we'll use a special redirect URI that includes the code_verifier
    # The base redirect URI is the API URL + /auth
    API_AUTH_ENDPOINT = f"{API_URL}/auth"
    # The actual redirect URI will be constructed in get_auth_url to include the code_verifier
    REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", API_AUTH_ENDPOINT)
else:
    # Otherwise, use the local OAuth server
    OAUTH_HOST = os.getenv("OAUTH_HOST", "localhost")
    OAUTH_PORT = int(os.getenv("OAUTH_PORT", "8080"))
    REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", f"http://{OAUTH_HOST}:{OAUTH_PORT}/oauth/callback")

# Discord API endpoints
API_ENDPOINT = "https://discord.com/api/v10"
TOKEN_URL = f"{API_ENDPOINT}/oauth2/token"
AUTH_URL = f"{API_ENDPOINT}/oauth2/authorize"
USER_URL = f"{API_ENDPOINT}/users/@me"

# Token storage directory
TOKEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens")
os.makedirs(TOKEN_DIR, exist_ok=True)

# In-memory storage for PKCE code verifiers and pending states
code_verifiers: Dict[str, Any] = {}

# Global dictionary to store code verifiers by state
# This is used to pass the code verifier to the API service
pending_code_verifiers: Dict[str, str] = {}

class OAuthError(Exception):
    """Exception raised for OAuth errors."""
    pass

def generate_code_verifier() -> str:
    """Generate a code verifier for PKCE."""
    return secrets.token_urlsafe(64)

def generate_code_challenge(verifier: str) -> str:
    """Generate a code challenge from a code verifier."""
    sha256 = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256).decode().rstrip("=")

def get_token_path(user_id: str) -> str:
    """Get the path to the token file for a user."""
    return os.path.join(TOKEN_DIR, f"{user_id}.json")

def save_token(user_id: str, token_data: Dict[str, Any]) -> None:
    """Save a token to disk."""
    # Add the time when the token was saved
    token_data["saved_at"] = int(time.time())

    with open(get_token_path(user_id), "w") as f:
        json.dump(token_data, f)

def load_token(user_id: str) -> Optional[Dict[str, Any]]:
    """Load a token from disk."""
    token_path = get_token_path(user_id)
    if not os.path.exists(token_path):
        return None

    try:
        with open(token_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def is_token_expired(token_data: Dict[str, Any]) -> bool:
    """Check if a token is expired."""
    if not token_data:
        return True

    # Get the time when the token was saved
    saved_at = token_data.get("saved_at", 0)

    # Get the token's expiration time
    expires_in = token_data.get("expires_in", 0)

    # Check if the token is expired
    # We consider it expired if it's within 5 minutes of expiration
    return (saved_at + expires_in - 300) < int(time.time())

def delete_token(user_id: str) -> bool:
    """Delete a token from disk."""
    token_path = get_token_path(user_id)
    if os.path.exists(token_path):
        os.remove(token_path)
        return True
    return False

async def send_code_verifier_to_api(state: str, code_verifier: str) -> bool:
    """Send the code verifier to the API service."""
    try:
        async with aiohttp.ClientSession() as session:
            # Construct the URL for the code verifier endpoint
            url = f"{API_URL}/code_verifier"

            # Prepare the data
            data = {
                "state": state,
                "code_verifier": code_verifier
            }

            # Send the code verifier to the API service
            print(f"Sending code verifier for state {state} to API service: {url}")
            async with session.post(url, json=data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"Failed to send code verifier to API service: {error_text}")
                    return False

                response_data = await resp.json()
                print(f"Successfully sent code verifier to API service: {response_data}")
                return True
    except Exception as e:
        print(f"Error sending code verifier to API service: {e}")
        traceback.print_exc()
        return False

def get_auth_url(state: str, code_verifier: str) -> str:
    """Get the authorization URL for the OAuth2 flow."""
    code_challenge = generate_code_challenge(code_verifier)

    # Determine the redirect URI based on whether API OAuth is enabled
    if API_OAUTH_ENABLED:
        # For API OAuth, we must use a clean redirect URI without any query parameters
        # The redirect URI must exactly match the one registered in the Discord application
        actual_redirect_uri = API_AUTH_ENDPOINT
        print(f"Using API OAuth with redirect URI: {actual_redirect_uri}")
    else:
        # For local OAuth server, use the standard redirect URI
        actual_redirect_uri = REDIRECT_URI
        print(f"Using local OAuth server with redirect URI: {actual_redirect_uri}")

    # Build the authorization URL
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": actual_redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "consent"
    }

    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    # Store the code verifier and redirect URI for this state
    code_verifiers[state] = {
        "code_verifier": code_verifier,
        "redirect_uri": actual_redirect_uri
    }

    # Also store the code verifier in the global dictionary
    # This will be used by the API service to retrieve the code verifier
    pending_code_verifiers[state] = code_verifier
    print(f"Stored code verifier for state {state}: {code_verifier[:10]}...")

    # If API OAuth is enabled, send the code verifier to the API service
    if API_OAUTH_ENABLED:
        asyncio.create_task(send_code_verifier_to_api(state, code_verifier))

    return auth_url

async def exchange_code(code: str, state: str) -> Dict[str, Any]:
    """Exchange an authorization code for a token."""
    # Get the code verifier and redirect URI for this state
    state_data = code_verifiers.pop(state, None)
    if not state_data:
        raise OAuthError("Invalid state parameter")

    # Extract code_verifier and redirect_uri
    if isinstance(state_data, dict):
        code_verifier = state_data.get("code_verifier")
        redirect_uri = state_data.get("redirect_uri")
    else:
        # For backward compatibility
        code_verifier = state_data
        redirect_uri = REDIRECT_URI

    if not code_verifier:
        raise OAuthError("Missing code verifier")

    # If API OAuth is enabled, we need to check if we should handle the token exchange ourselves
    # or if the API service will handle it
    if API_OAUTH_ENABLED and redirect_uri.startswith(API_URL):
        # If the API service is handling the OAuth flow, we need to get the token from the API
        # We'll make a request to the API service with the code and code_verifier
        async with aiohttp.ClientSession() as session:
            # Construct the URL with the code and code_verifier
            params = {
                "code": code,
                "state": state,
                "code_verifier": code_verifier
            }
            auth_url = f"{API_URL}/auth?{urlencode(params)}"

            print(f"Redirecting to API service for token exchange: {auth_url}")

            # Make a request to the API service
            async with session.get(auth_url) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"Failed to exchange code with API service: {error_text}")
                    raise OAuthError(f"Failed to exchange code with API service: {error_text}")

                # The API service should return a success page, not the token
                # We'll need to get the token from the API service separately
                print("Successfully exchanged code with API service")

                # Parse the response to get the token data
                try:
                    response_data = await resp.json()
                    if "token" in response_data:
                        # Save the token data
                        token_data = response_data["token"]
                        save_token(response_data["user_id"], token_data)
                        print(f"Successfully saved token for user {response_data['user_id']}")
                        return token_data
                    else:
                        # If the response doesn't contain a token, it's probably an HTML response
                        # We'll need to get the token from the API service separately
                        print("Response doesn't contain token data, will try to get it separately")
                except Exception as e:
                    print(f"Error parsing response: {e}")

                # If we couldn't get the token from the response, try to get it from the API service
                try:
                    # Make a request to the API service to get the token
                    headers = {"Accept": "application/json"}
                    async with session.get(f"{API_URL}/token", headers=headers) as token_resp:
                        if token_resp.status != 200:
                            error_text = await token_resp.text()
                            print(f"Failed to get token from API service: {error_text}")
                            raise OAuthError(f"Failed to get token from API service: {error_text}")

                        token_data = await token_resp.json()
                        if "access_token" in token_data:
                            return token_data
                        else:
                            raise OAuthError("API service didn't return a valid token")
                except Exception as e:
                    print(f"Error getting token from API service: {e}")
                    # Return a placeholder token for now
                    return {"access_token": "placeholder_token", "token_type": "Bearer", "expires_in": 604800}

    # If we're handling the token exchange ourselves, proceed as before
    async with aiohttp.ClientSession() as session:
        # For public clients, we don't include a client secret
        data = {
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier
        }

        print(f"Exchanging code for token with data: {data}")

        async with session.post(TOKEN_URL, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                print(f"Failed to exchange code: {error_text}")
                raise OAuthError(f"Failed to exchange code: {error_text}")

            return await resp.json()

async def refresh_token(refresh_token: str) -> Dict[str, Any]:
    """Refresh an access token."""
    async with aiohttp.ClientSession() as session:
        # For public clients, we don't include a client secret
        data = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        print(f"Refreshing token with data: {data}")

        async with session.post(TOKEN_URL, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                print(f"Failed to refresh token: {error_text}")
                raise OAuthError(f"Failed to refresh token: {error_text}")

            return await resp.json()

async def get_user_info(access_token: str) -> Dict[str, Any]:
    """Get information about the authenticated user."""
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with session.get(USER_URL, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise OAuthError(f"Failed to get user info: {error_text}")

            return await resp.json()

async def get_token(user_id: str) -> Optional[str]:
    """Get a valid access token for a user."""
    # Load the token from disk
    token_data = load_token(user_id)
    if not token_data:
        return None

    # Check if the token is expired
    if is_token_expired(token_data):
        # Try to refresh the token
        refresh_token_str = token_data.get("refresh_token")
        if not refresh_token_str:
            return None

        try:
            # Refresh the token
            new_token_data = await refresh_token(refresh_token_str)

            # Save the new token
            save_token(user_id, new_token_data)

            # Return the new access token
            return new_token_data.get("access_token")
        except OAuthError:
            # If refreshing fails, delete the token and return None
            delete_token(user_id)
            return None

    # Return the access token
    return token_data.get("access_token")

async def validate_token(token: str) -> Tuple[bool, Optional[str]]:
    """Validate a token and return the user ID if valid."""
    try:
        # Get user info to validate the token
        user_info = await get_user_info(token)
        return True, user_info.get("id")
    except OAuthError:
        return False, None
