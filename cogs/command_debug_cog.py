import discord
from discord.ext import commands
from discord import app_commands
import inspect
import json

class CommandDebugCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("CommandDebugCog initialized!")

    @commands.command(name="checkcommand")
    @commands.is_owner()
    async def check_command(self, ctx, command_name: str = "webdrivertorso"):
        """Check details of a specific slash command"""
        await ctx.send(f"Checking details for slash command: {command_name}")
        
        # Find the command in the command tree
        command = None
        for cmd in self.bot.tree.get_commands():
            if cmd.name == command_name:
                command = cmd
                break
        
        if not command:
            await ctx.send(f"Command '{command_name}' not found in the command tree.")
            return
        
        # Get basic command info
        await ctx.send(f"Command found: {command.name}")
        await ctx.send(f"Description: {command.description}")
        await ctx.send(f"Parameter count: {len(command.parameters)}")
        
        # Get parameter details
        for i, param in enumerate(command.parameters):
            param_info = f"Parameter {i+1}: {param.name}"
            param_info += f"\n  Type: {type(param.type).__name__}"
            param_info += f"\n  Required: {param.required}"
            
            # Check for choices
            if hasattr(param, 'choices') and param.choices:
                choices = [f"{c.name} ({c.value})" for c in param.choices]
                param_info += f"\n  Choices: {', '.join(choices)}"
            
            # Check for tts_provider specifically
            if param.name == "tts_provider":
                param_info += "\n  THIS IS THE TTS PROVIDER PARAMETER WE'RE LOOKING FOR!"
                
                # Get the actual implementation
                cog_instance = None
                for cog in self.bot.cogs.values():
                    for command_obj in cog.get_app_commands():
                        if command_obj.name == command_name:
                            cog_instance = cog
                            break
                    if cog_instance:
                        break
                
                if cog_instance:
                    param_info += f"\n  Found in cog: {cog_instance.__class__.__name__}"
                    
                    # Try to get the actual method
                    method = None
                    for name, method_obj in inspect.getmembers(cog_instance, predicate=inspect.ismethod):
                        if hasattr(method_obj, "callback") and getattr(method_obj, "callback", None) == command:
                            method = method_obj
                            break
                        elif hasattr(method_obj, "__name__") and method_obj.__name__ == f"{command_name}_slash":
                            method = method_obj
                            break
                    
                    if method:
                        param_info += f"\n  Method: {method.__name__}"
                        param_info += f"\n  Signature: {str(inspect.signature(method))}"
            
            await ctx.send(param_info)
        
        # Check for the actual implementation in the cogs
        await ctx.send("Checking implementation in cogs...")
        for cog_name, cog in self.bot.cogs.items():
            for cmd in cog.get_app_commands():
                if cmd.name == command_name:
                    await ctx.send(f"Command implemented in cog: {cog_name}")
                    
                    # Try to get the method
                    for name, method in inspect.getmembers(cog, predicate=inspect.ismethod):
                        if name.startswith(command_name) or name.endswith("_slash"):
                            await ctx.send(f"Possible implementing method: {name}")
                            sig = inspect.signature(method)
                            await ctx.send(f"Method signature: {sig}")
                            
                            # Check if tts_provider is in the parameters
                            if "tts_provider" in [p for p in sig.parameters]:
                                await ctx.send("✅ tts_provider parameter found in method signature!")
                            else:
                                await ctx.send("❌ tts_provider parameter NOT found in method signature!")

async def setup(bot: commands.Bot):
    print("Loading CommandDebugCog...")
    await bot.add_cog(CommandDebugCog(bot))
    print("CommandDebugCog loaded successfully!")
