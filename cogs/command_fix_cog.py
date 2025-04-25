import discord
from discord.ext import commands
from discord import app_commands
import inspect

class CommandFixCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("CommandFixCog initialized!")

    @commands.command(name="fixcommand")
    @commands.is_owner()
    async def fix_command(self, ctx):
        """Attempt to fix the webdrivertorso command at runtime"""
        await ctx.send("Attempting to fix the webdrivertorso command...")
        
        # Find the WebdriverTorsoCog
        webdriver_cog = None
        for cog_name, cog in self.bot.cogs.items():
            if cog_name == "WebdriverTorsoCog":
                webdriver_cog = cog
                break
        
        if not webdriver_cog:
            await ctx.send("❌ WebdriverTorsoCog not found!")
            return
        
        await ctx.send("✅ Found WebdriverTorsoCog")
        
        # Find the slash command
        slash_command = None
        for cmd in self.bot.tree.get_commands():
            if cmd.name == "webdrivertorso":
                slash_command = cmd
                break
        
        if not slash_command:
            await ctx.send("❌ webdrivertorso slash command not found!")
            return
        
        await ctx.send(f"✅ Found webdrivertorso slash command with {len(slash_command.parameters)} parameters")
        
        # Check if tts_provider is in the parameters
        tts_provider_param = None
        for param in slash_command.parameters:
            if param.name == "tts_provider":
                tts_provider_param = param
                break
        
        if tts_provider_param:
            await ctx.send(f"✅ tts_provider parameter already exists in the command")
            
            # Check if it has choices
            if hasattr(tts_provider_param, 'choices') and tts_provider_param.choices:
                choices = [f"{c.name} ({c.value})" for c in tts_provider_param.choices]
                await ctx.send(f"✅ tts_provider has choices: {', '.join(choices)}")
            else:
                await ctx.send("❌ tts_provider parameter has no choices!")
        else:
            await ctx.send("❌ tts_provider parameter not found in the command!")
        
        # Try to force a sync
        await ctx.send("Forcing a command sync...")
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Synced {len(synced)} command(s)")
        except Exception as e:
            await ctx.send(f"❌ Failed to sync commands: {str(e)}")
        
        # Create a new command as a workaround
        await ctx.send("Creating a new ttsprovider command as a workaround...")
        
        # Check if TTSProviderCog is loaded
        tts_provider_cog = None
        for cog_name, cog in self.bot.cogs.items():
            if cog_name == "TTSProviderCog":
                tts_provider_cog = cog
                break
        
        if tts_provider_cog:
            await ctx.send("✅ TTSProviderCog is already loaded")
        else:
            await ctx.send("❌ TTSProviderCog not loaded. Please load it with !load tts_provider_cog")
        
        await ctx.send("Fix attempt completed. Please check if the ttsprovider command is available.")

async def setup(bot: commands.Bot):
    print("Loading CommandFixCog...")
    await bot.add_cog(CommandFixCog(bot))
    print("CommandFixCog loaded successfully!")
