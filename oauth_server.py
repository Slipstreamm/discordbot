"""
OAuth2 callback server for the Discord bot.

This module provides a simple web server to handle OAuth2 callbacks
from Discord. It uses aiohttp to create an asynchronous web server
that can run alongside the Discord bot.
"""

import os
import asyncio
import aiohttp
from aiohttp import web
import discord_oauth
from typing import Dict, Optional, Set, Callable

# Set of pending authorization states
pending_states: Set[str] = set()

# Callbacks for successful authorization
auth_callbacks: Dict[str, Callable] = {}

async def handle_oauth_callback(request: web.Request) -> web.Response:
    """Handle OAuth2 callback from Discord."""
    # Get the authorization code and state from the request
    code = request.query.get("code")
    state = request.query.get("state")
    
    if not code or not state:
        return web.Response(text="Missing code or state parameter", status=400)
    
    # Check if the state is valid
    if state not in pending_states:
        return web.Response(text="Invalid state parameter", status=400)
    
    # Remove the state from pending states
    pending_states.remove(state)
    
    try:
        # Exchange the code for a token
        token_data = await discord_oauth.exchange_code(code, state)
        
        # Get the user's information
        access_token = token_data.get("access_token")
        if not access_token:
            return web.Response(text="Failed to get access token", status=500)
        
        user_info = await discord_oauth.get_user_info(access_token)
        user_id = user_info.get("id")
        
        if not user_id:
            return web.Response(text="Failed to get user ID", status=500)
        
        # Save the token
        discord_oauth.save_token(user_id, token_data)
        
        # Call the callback for this state if it exists
        callback = auth_callbacks.pop(state, None)
        if callback:
            asyncio.create_task(callback(user_id, user_info))
        
        # Return a success message
        return web.Response(
            text=f"""
            <html>
                <head>
                    <title>Authentication Successful</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                        .success {{ color: green; }}
                        .info {{ margin-top: 20px; }}
                    </style>
                </head>
                <body>
                    <h1 class="success">Authentication Successful!</h1>
                    <p>You have successfully authenticated with Discord.</p>
                    <div class="info">
                        <p>You can now close this window and return to Discord.</p>
                        <p>Your Discord bot is now authorized to access the API on your behalf.</p>
                    </div>
                </body>
            </html>
            """,
            content_type="text/html"
        )
    except discord_oauth.OAuthError as e:
        return web.Response(text=f"OAuth error: {str(e)}", status=500)
    except Exception as e:
        return web.Response(text=f"Error: {str(e)}", status=500)

async def handle_root(request: web.Request) -> web.Response:
    """Handle requests to the root path."""
    return web.Response(
        text="""
        <html>
            <head>
                <title>Discord Bot OAuth Server</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                </style>
            </head>
            <body>
                <h1>Discord Bot OAuth Server</h1>
                <p>This server handles OAuth callbacks for the Discord bot.</p>
                <p>You should not access this page directly.</p>
            </body>
        </html>
        """,
        content_type="text/html"
    )

def create_app() -> web.Application:
    """Create the web application."""
    app = web.Application()
    app.add_routes([
        web.get("/", handle_root),
        web.get("/oauth/callback", handle_oauth_callback)
    ])
    return app

async def start_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the OAuth callback server."""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"OAuth callback server running at http://{host}:{port}")

def register_auth_state(state: str, callback: Optional[Callable] = None) -> None:
    """Register a pending authorization state."""
    pending_states.add(state)
    if callback:
        auth_callbacks[state] = callback

if __name__ == "__main__":
    # For testing the server standalone
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_server())
    loop.run_forever()
