"""
OAuth cog for the Discord bot.

This cog provides commands for authenticating with Discord OAuth2,
managing tokens, and checking authentication status.
"""

import os
import secrets
import discord
from discord.ext import commands
import asyncio
import aiohttp
from typing import Dict, Optional, Any

# Import the OAuth modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import discord_oauth
import oauth_server

class OAuthCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending_auth = {}

        # Start the OAuth server
        asyncio.create_task(self.start_oauth_server())

    async def start_oauth_server(self):
        """Start the OAuth callback server if API OAuth is not enabled."""
        # Check if API OAuth is enabled
        api_oauth_enabled = os.getenv("API_OAUTH_ENABLED", "true").lower() in ("true", "1", "yes")

        if api_oauth_enabled:
            # If API OAuth is enabled, we don't need to start the local OAuth server
            api_url = os.getenv("API_URL", "https://slipstreamm.dev/api")
            redirect_uri = os.getenv("DISCORD_REDIRECT_URI", f"{api_url}/auth")
            print(f"Using API OAuth endpoint at {redirect_uri}")
            return

        # Otherwise, start the local OAuth server
        host = os.getenv("OAUTH_HOST", "localhost")
        port = int(os.getenv("OAUTH_PORT", "8080"))
        await oauth_server.start_server(host, port)
        print(f"OAuth callback server running at http://{host}:{port}")

    async def check_token_availability(self, user_id: str, channel_id: int, max_attempts: int = 15, delay: int = 3):
        """Check if a token is available for the user after API OAuth flow."""
        # Import the OAuth module
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import discord_oauth

        # Get the channel
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Could not find channel with ID {channel_id}")
            return

        # Wait for the token to become available
        for attempt in range(max_attempts):
            # Wait for a bit
            await asyncio.sleep(delay)
            print(f"Checking token availability for user {user_id}, attempt {attempt+1}/{max_attempts}")

            # Try to get the token
            try:
                # First try to get the token from the local storage
                token = await discord_oauth.get_token(user_id)
                if token:
                    # Token is available locally, send a success message
                    await channel.send(f"<@{user_id}> ✅ Authentication successful! You can now use the API.")
                    return

                # If not available locally, try to get it from the API service
                if discord_oauth.API_OAUTH_ENABLED:
                    print(f"Token not found locally, checking API service for user {user_id}")
                    try:
                        # Make a direct API call to check if the token exists in the API service
                        async with aiohttp.ClientSession() as session:
                            url = f"{discord_oauth.API_URL}/check_auth/{user_id}"
                            print(f"Checking auth status at: {url}")

                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    # User is authenticated in the API service
                                    data = await resp.json()
                                    print(f"API service auth check response: {data}")

                                    if data.get("authenticated", False):
                                        # Try to retrieve the token from the API service
                                        token_url = f"{discord_oauth.API_URL}/token/{user_id}"
                                        async with session.get(token_url) as token_resp:
                                            if token_resp.status == 200:
                                                token_data = await token_resp.json()
                                                # Save the token locally
                                                discord_oauth.save_token(user_id, token_data)
                                                await channel.send(f"<@{user_id}> ✅ Authentication successful! You can now use the API.")
                                                return
                    except Exception as e:
                        print(f"Error checking auth status with API service: {e}")
            except Exception as e:
                print(f"Error checking token availability: {e}")

        # If we get here, the token is not available after max_attempts
        await channel.send(f"<@{user_id}> ⚠️ Authentication may have failed. Please try again or check with the bot owner.")

    async def auth_callback(self, user_id: str, user_info: Dict[str, Any]):
        """Callback for successful authentication."""
        # Find the user in Discord
        discord_user = self.bot.get_user(int(user_id))
        if not discord_user:
            print(f"Could not find Discord user with ID {user_id}")
            return

        # Send a DM to the user
        try:
            await discord_user.send(
                f"✅ Authentication successful! You are now logged in as {user_info.get('username')}#{user_info.get('discriminator')}.\n"
                f"Your Discord bot is now authorized to access the API on your behalf."
            )
        except discord.errors.Forbidden:
            # If we can't send a DM, try to find the channel where the auth command was used
            channel_id = self.pending_auth.get(user_id)
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"<@{user_id}> ✅ Authentication successful!")

        # Remove the pending auth entry
        self.pending_auth.pop(user_id, None)

    @commands.command(name="auth")
    async def auth_command(self, ctx):
        """Authenticate with Discord to allow the bot to access the API on your behalf."""
        user_id = str(ctx.author.id)

        # Check if the user is already authenticated
        token = await discord_oauth.get_token(user_id)
        if token:
            # Validate the token
            is_valid, _ = await discord_oauth.validate_token(token)
            if is_valid:
                await ctx.send(
                    f"You are already authenticated. Use `!deauth` to revoke access or `!authstatus` to check your status."
                )
                return

        # Generate a state parameter for security
        state = secrets.token_urlsafe(32)

        # Generate a code verifier for PKCE
        code_verifier = discord_oauth.generate_code_verifier()

        # Get the authorization URL
        auth_url = discord_oauth.get_auth_url(state, code_verifier)

        # Check if API OAuth is enabled
        api_oauth_enabled = os.getenv("API_OAUTH_ENABLED", "true").lower() in ("true", "1", "yes")

        if not api_oauth_enabled:
            # If using local OAuth server, register the state and callback
            oauth_server.register_auth_state(state, self.auth_callback)
        else:
            # If using API OAuth, we'll need to handle the callback differently
            # Store the channel ID for the callback
            # We'll check for token availability periodically
            asyncio.create_task(self.check_token_availability(user_id, ctx.channel.id))

        # Store the channel ID for the callback
        self.pending_auth[user_id] = ctx.channel.id

        # Create an embed with the auth instructions
        embed = discord.Embed(
            title="Discord Authentication",
            description="Please click the link below to authenticate with Discord.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Instructions",
            value=(
                "1. Click the link below to open Discord's authorization page\n"
                "2. Authorize the application to access your Discord account\n"
                "3. You will be redirected to a confirmation page\n"
                "4. Return to Discord after seeing the confirmation"
            ),
            inline=False
        )
        embed.add_field(
            name="Authentication Link",
            value=f"[Click here to authenticate]({auth_url})",
            inline=False
        )

        # Add information about the redirect URI
        if api_oauth_enabled:
            api_url = os.getenv("API_URL", "https://slipstreamm.dev/api")
            embed.add_field(
                name="Note",
                value=f"You will be redirected to the API service at {api_url}/auth",
                inline=False
            )

        embed.set_footer(text="This link will expire in 10 minutes")

        # Send the embed as a DM to the user
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("📬 I've sent you a DM with authentication instructions!")
        except discord.errors.Forbidden:
            # If we can't send a DM, send the auth link in the channel
            await ctx.send(
                f"I couldn't send you a DM. Please click this link to authenticate: {auth_url}\n"
                f"This link will expire in 10 minutes."
            )

    @commands.command(name="deauth")
    async def deauth_command(self, ctx):
        """Revoke the bot's access to your Discord account."""
        user_id = str(ctx.author.id)

        # Delete the local token
        local_success = discord_oauth.delete_token(user_id)

        # If API OAuth is enabled, also delete the token from the API service
        api_success = False
        if discord_oauth.API_OAUTH_ENABLED:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{discord_oauth.API_URL}/token/{user_id}"
                    async with session.delete(url) as resp:
                        if resp.status == 200:
                            api_success = True
                            data = await resp.json()
                            print(f"API service token deletion response: {data}")
            except Exception as e:
                print(f"Error deleting token from API service: {e}")

        if local_success or api_success:
            if local_success and api_success:
                await ctx.send("✅ Authentication revoked from both local storage and API service.")
            elif local_success:
                await ctx.send("✅ Authentication revoked from local storage.")
            else:
                await ctx.send("✅ Authentication revoked from API service.")
        else:
            await ctx.send("❌ You are not currently authenticated.")

    @commands.command(name="authstatus")
    async def auth_status_command(self, ctx):
        """Check your authentication status."""
        user_id = str(ctx.author.id)

        # First check if the user has a token locally
        token = await discord_oauth.get_token(user_id)
        if token:
            # Validate the token
            is_valid, _ = await discord_oauth.validate_token(token)

            if is_valid:
                # Get user info
                try:
                    user_info = await discord_oauth.get_user_info(token)
                    username = user_info.get("username")
                    discriminator = user_info.get("discriminator")

                    await ctx.send(
                        f"✅ You are authenticated as {username}#{discriminator}.\n"
                        f"The bot can access the API on your behalf."
                    )
                    return
                except discord_oauth.OAuthError:
                    await ctx.send(
                        "⚠️ Your authentication is valid, but there was an error retrieving your user information."
                    )
                    return
            else:
                # Token is invalid, but we'll check the API service before giving up
                await ctx.send(
                    "⚠️ Your local token has expired. Checking with the API service..."
                )

        # If we get here, either there's no local token or it's invalid
        # Check with the API service if enabled
        if discord_oauth.API_OAUTH_ENABLED:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{discord_oauth.API_URL}/check_auth/{user_id}"
                    print(f"Checking auth status at: {url}")

                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"API service auth check response: {data}")

                            if data.get("authenticated", False):
                                # User is authenticated in the API service
                                # Try to retrieve the token
                                token_url = f"{discord_oauth.API_URL}/token/{user_id}"
                                async with session.get(token_url) as token_resp:
                                    if token_resp.status == 200:
                                        token_data = await token_resp.json()
                                        # Save the token locally
                                        discord_oauth.save_token(user_id, token_data)

                                        # Get user info with the new token
                                        try:
                                            access_token = token_data.get("access_token")
                                            user_info = await discord_oauth.get_user_info(access_token)
                                            username = user_info.get("username")
                                            discriminator = user_info.get("discriminator")

                                            await ctx.send(
                                                f"✅ You are authenticated as {username}#{discriminator}.\n"
                                                f"The bot can access the API on your behalf.\n"
                                                f"(Token retrieved from API service)"
                                            )
                                            return
                                        except Exception as e:
                                            print(f"Error getting user info with token from API service: {e}")
                                            await ctx.send(
                                                f"✅ You are authenticated according to the API service.\n"
                                                f"The token has been retrieved and saved locally."
                                            )
                                            return
            except Exception as e:
                print(f"Error checking auth status with API service: {e}")

        # If we get here, the user is not authenticated anywhere
        await ctx.send("❌ You are not currently authenticated. Use `!auth` to authenticate.")

    @commands.command(name="authhelp")
    async def auth_help_command(self, ctx):
        """Get help with authentication commands."""
        embed = discord.Embed(
            title="Authentication Help",
            description="Commands for managing Discord authentication",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="!auth",
            value="Authenticate with Discord to allow the bot to access the API on your behalf",
            inline=False
        )

        embed.add_field(
            name="!deauth",
            value="Revoke the bot's access to your Discord account",
            inline=False
        )

        embed.add_field(
            name="!authstatus",
            value="Check your authentication status",
            inline=False
        )

        embed.add_field(
            name="!authhelp",
            value="Show this help message",
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(OAuthCog(bot))
