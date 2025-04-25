import discord
from discord.ext import commands
from discord import app_commands
import datetime
import os
from typing import Optional, List, Dict, Any

# Try to import the Discord sync API
try:
    from discord_bot_sync_api import (
        user_conversations, save_discord_conversation,
        load_conversations, SyncedConversation, SyncedMessage
    )
    SYNC_API_AVAILABLE = True
except ImportError:
    print("Discord sync API not available in sync cog. Sync features will be disabled.")
    SYNC_API_AVAILABLE = False

class DiscordSyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("DiscordSyncCog initialized!")

        # Load conversations if API is available
        if SYNC_API_AVAILABLE:
            load_conversations()

    @commands.command(name="syncstatus")
    async def sync_status(self, ctx: commands.Context):
        """Check the status of the Discord sync API"""
        if not SYNC_API_AVAILABLE:
            await ctx.reply("❌ Discord sync API is not available. Please make sure the required dependencies are installed.")
            return

        # Count total synced conversations
        total_conversations = sum(len(convs) for convs in user_conversations.values())
        total_users = len(user_conversations)

        # Check if the user has any synced conversations
        user_id = str(ctx.author.id)
        user_conv_count = len(user_conversations.get(user_id, []))

        embed = discord.Embed(
            title="Discord Sync Status",
            description="Status of the Discord sync API for Flutter app integration",
            color=discord.Color.green()
        )

        embed.add_field(
            name="API Status",
            value="✅ Running",
            inline=False
        )

        embed.add_field(
            name="Total Synced Conversations",
            value=f"{total_conversations} conversations from {total_users} users",
            inline=False
        )

        embed.add_field(
            name="Your Synced Conversations",
            value=f"{user_conv_count} conversations",
            inline=False
        )

        embed.add_field(
            name="API Endpoint",
            value="https://slipstreamm.dev/discordapi",
            inline=False
        )

        embed.add_field(
            name="Setup Instructions",
            value="Use `!synchelp` for setup instructions",
            inline=False
        )

        embed.set_footer(text=f"Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await ctx.reply(embed=embed)

    @commands.command(name="synchelp")
    async def sync_help(self, ctx: commands.Context):
        """Get help with setting up the Discord sync integration"""
        embed = discord.Embed(
            title="Discord Sync Integration Help",
            description="How to set up the Discord sync integration with the Flutter app",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="1. Discord Developer Portal Setup",
            value=(
                "1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)\n"
                "2. Click 'New Application' and give it a name\n"
                "3. Go to the 'OAuth2' section\n"
                "4. Add a redirect URL: `openroutergui://auth`\n"
                "5. Copy the 'Client ID' for the Flutter app"
            ),
            inline=False
        )

        embed.add_field(
            name="2. Flutter App Setup",
            value=(
                "1. Open the Flutter app settings\n"
                "2. Go to 'Discord Integration'\n"
                "3. Enter the Client ID from the Discord Developer Portal\n"
                "4. Enter the Bot API URL: `https://slipstreamm.dev/discordapi`\n"
                "5. Click 'Save'"
            ),
            inline=False
        )

        embed.add_field(
            name="3. Usage",
            value=(
                "1. Click 'Login with Discord' in the Flutter app\n"
                "2. Authorize the app to access your Discord account\n"
                "3. Use the 'Sync Conversations' button to sync conversations\n"
                "4. Use the 'Import from Discord' button to import conversations"
            ),
            inline=False
        )

        embed.add_field(
            name="4. Troubleshooting",
            value=(
                "• Make sure the bot is running and accessible from the internet\n"
                "• Check that the Client ID is correct\n"
                "• Verify that the redirect URL is properly configured\n"
                "• Use `!syncstatus` to check the API status"
            ),
            inline=False
        )

        await ctx.reply(embed=embed)

    @commands.command(name="syncclear")
    async def sync_clear(self, ctx: commands.Context):
        """Clear your synced conversations"""
        if not SYNC_API_AVAILABLE:
            await ctx.reply("❌ Discord sync API is not available. Please make sure the required dependencies are installed.")
            return

        user_id = str(ctx.author.id)
        if user_id not in user_conversations or not user_conversations[user_id]:
            await ctx.reply("You don't have any synced conversations to clear.")
            return

        # Count conversations before clearing
        conv_count = len(user_conversations[user_id])

        # Clear the user's conversations
        user_conversations[user_id] = []

        # Save the updated conversations
        from discord_bot_sync_api import save_conversations
        save_conversations()

        await ctx.reply(f"✅ Cleared {conv_count} synced conversations.")

    @commands.command(name="synclist")
    async def sync_list(self, ctx: commands.Context):
        """List your synced conversations"""
        if not SYNC_API_AVAILABLE:
            await ctx.reply("❌ Discord sync API is not available. Please make sure the required dependencies are installed.")
            return

        user_id = str(ctx.author.id)
        if user_id not in user_conversations or not user_conversations[user_id]:
            await ctx.reply("You don't have any synced conversations.")
            return

        # Create an embed to display the conversations
        embed = discord.Embed(
            title="Your Synced Conversations",
            description=f"You have {len(user_conversations[user_id])} synced conversations",
            color=discord.Color.blue()
        )

        # Add each conversation to the embed
        for i, conv in enumerate(user_conversations[user_id], 1):
            # Get the first few messages for context
            preview = ""
            for msg in conv.messages[:3]:  # Show first 3 messages
                if len(preview) < 100:  # Keep preview short
                    preview += f"{msg.role}: {msg.content[:30]}...\n"

            # Add field for this conversation
            embed.add_field(
                name=f"{i}. {conv.title} ({conv.model_id})",
                value=(
                    f"ID: {conv.id}\n"
                    f"Created: {conv.created_at.strftime('%Y-%m-%d')}\n"
                    f"Messages: {len(conv.messages)}\n"
                    f"Preview: {preview[:100]}..."
                ),
                inline=False
            )

            # Discord embeds have a limit of 25 fields
            if i >= 10:
                embed.add_field(
                    name="Note",
                    value=f"Showing 10/{len(user_conversations[user_id])} conversations. Use the Flutter app to view all.",
                    inline=False
                )
                break

        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(DiscordSyncCog(bot))
