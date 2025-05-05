import discord
from discord.ext import commands
from discord import app_commands
import traceback
import command_customization

class SyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("SyncCog initialized!")

    @commands.command(name="forcesync")
    @commands.is_owner()
    async def force_sync(self, ctx):
        """Force sync all slash commands with verbose output"""
        await ctx.send("Starting verbose command sync...")

        try:
            # Get list of commands before sync
            commands_before = []
            for cmd in self.bot.tree.get_commands():
                cmd_info = {
                    "name": cmd.name,
                    "description": cmd.description,
                    "parameters": [p.name for p in cmd.parameters] if hasattr(cmd, "parameters") else []
                }
                commands_before.append(cmd_info)

            await ctx.send(f"Commands before sync: {len(commands_before)}")
            for cmd_data in commands_before:
                params_str = ", ".join(cmd_data["parameters"])
                await ctx.send(f"- {cmd_data['name']}: {len(cmd_data['parameters'])} params ({params_str})")

            # Skip global sync to avoid command duplication
            await ctx.send("Skipping global sync to avoid command duplication...")

            # Sync guild-specific commands with customizations
            await ctx.send("Syncing guild-specific command customizations...")
            guild_syncs = await command_customization.register_all_guild_commands(self.bot)

            total_guild_syncs = sum(len(cmds) for cmds in guild_syncs.values())
            await ctx.send(f"Synced commands for {len(guild_syncs)} guilds with a total of {total_guild_syncs} customized commands")

            # Get list of commands after sync
            commands_after = []
            for cmd in self.bot.tree.get_commands():
                cmd_info = {
                    "name": cmd.name,
                    "description": cmd.description,
                    "parameters": [p.name for p in cmd.parameters] if hasattr(cmd, "parameters") else []
                }
                commands_after.append(cmd_info)

            await ctx.send(f"Commands after sync: {len(commands_after)}")
            for cmd_data in commands_after:
                params_str = ", ".join(cmd_data["parameters"])
                await ctx.send(f"- {cmd_data['name']}: {len(cmd_data['parameters'])} params ({params_str})")

            # Check for webdrivertorso command specifically
            wd_cmd = next((cmd for cmd in self.bot.tree.get_commands() if cmd.name == "webdrivertorso"), None)
            if wd_cmd:
                await ctx.send("Webdrivertorso command details:")
                for param in wd_cmd.parameters:
                    await ctx.send(f"- Param: {param.name}, Type: {param.type}, Required: {param.required}")
                    if hasattr(param, "choices") and param.choices:
                        choices_str = ", ".join([c.name for c in param.choices])
                        await ctx.send(f"  Choices: {choices_str}")
            else:
                await ctx.send("Webdrivertorso command not found after sync!")

            await ctx.send(f"Synced {total_guild_syncs} command(s) successfully!")
        except Exception as e:
            await ctx.send(f"Error during sync: {str(e)}")
            await ctx.send(f"```{traceback.format_exc()}```")

async def setup(bot: commands.Bot):
    print("Loading SyncCog...")
    await bot.add_cog(SyncCog(bot))
    print("SyncCog loaded successfully!")
