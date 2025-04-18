import discord
from discord.ext import commands
from discord import app_commands
import subprocess
import asyncio
import re
import os
import platform
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# Comprehensive list of banned commands and patterns
BANNED_COMMANDS = [
    # # System modification commands
    # "rm", "rmdir", "del", "format", "fdisk", "mkfs", "fsck", "dd", "shred",
    
    # # File permission/ownership changes
    # "chmod", "chown", "icacls", "takeown", "attrib",
    
    # # User management
    # "useradd", "userdel", "adduser", "deluser", "passwd", "usermod", "net user",
    
    # # Process control that could affect the bot
    # "kill", "pkill", "taskkill", "killall",
    
    # # Package management
    # "apt", "apt-get", "yum", "dnf", "pacman", "brew", "pip", "npm", "gem", "cargo",
    
    # # Network configuration
    # "ifconfig", "ip", "route", "iptables", "firewall-cmd", "ufw", "netsh",
    
    # # System control
    # "shutdown", "reboot", "halt", "poweroff", "init", "systemctl",
    
    # # Potentially dangerous utilities
    # "wget", "curl", "nc", "ncat", "telnet", "ssh", "scp", "ftp", "sftp",
    
    # # Shell escapes or command chaining that could bypass restrictions
    # "bash", "sh", "cmd", "powershell", "pwsh", "python", "perl", "ruby", "php", "node",
    
    # # Git commands that could modify repositories
    # "git push", "git commit", "git config", "git remote",
    
    # # Windows specific dangerous commands
    # "reg", "regedit", "wmic", "diskpart", "sfc", "dism",
    
    # # Miscellaneous dangerous commands
    # "eval", "exec", "source", ">", ">>", "|", "&", "&&", ";", "||"
]

# Regular expression patterns for more complex matching
BANNED_PATTERNS = [
    # r"rm\s+(-[rf]\s+)*[/\\]",  # rm with path starting from root
    # r">\s*[/\\]",              # redirect output to root path
    # r">\s*~",                  # redirect output to home directory
    # r">\s*\.",                 # redirect output to current directory
    # r">\s*\.\.",               # redirect output to parent directory
    # r">\s*[a-zA-Z]:",          # redirect output to drive letter (Windows)
    # r";\s*rm",                 # command chaining with rm
    # r"&&\s*rm",                # command chaining with rm
    # r"\|\|\s*rm",              # command chaining with rm
    # r";\s*del",                # command chaining with del
    # r"&&\s*del",               # command chaining with del
    # r"\|\|\s*del",             # command chaining with del
]

def is_command_allowed(command):
    """
    Check if the command is allowed to run.
    Returns (allowed, reason) tuple.
    """
    # Check against banned commands
    for banned in BANNED_COMMANDS:
        if banned in command.lower():
            return False, f"Command contains banned term: `{banned}`"
    
    # Check against banned patterns
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, command):
            return False, f"Command matches banned pattern: `{pattern}`"
    
    return True, None

class ShellCommandCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.max_output_length = 1900  # Discord message limit is 2000 chars
        self.timeout_seconds = 30      # Maximum time a command can run
    
    async def _execute_command(self, command_str):
        """
        Execute a shell command and return the output.
        """
        # Check if command is allowed
        allowed, reason = is_command_allowed(command_str)
        if not allowed:
            return f"⛔ Command not allowed: {reason}"
        
        # Log the command execution
        logger.info(f"Executing shell command: {command_str}")
        
        try:
            # Determine the shell to use based on platform
            shell = True
            if platform.system() == "Windows":
                process = await asyncio.create_subprocess_shell(
                    command_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=shell
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=shell
                )
            
            # Run the command with a timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                # Try to terminate the process if it times out
                try:
                    process.terminate()
                    await asyncio.sleep(0.5)
                    if process.returncode is None:
                        process.kill()
                except Exception as e:
                    logger.error(f"Error terminating process: {e}")
                
                return f"⏱️ Command timed out after {self.timeout_seconds} seconds."
            
            # Decode the output
            stdout_str = stdout.decode('utf-8', errors='replace').strip()
            stderr_str = stderr.decode('utf-8', errors='replace').strip()
            
            # Prepare the result message
            result = []
            if stdout_str:
                if len(stdout_str) > self.max_output_length:
                    stdout_str = stdout_str[:self.max_output_length] + "... (output truncated)"
                result.append(f"📤 **STDOUT:**\n```\n{stdout_str}\n```")
            
            if stderr_str:
                if len(stderr_str) > self.max_output_length:
                    stderr_str = stderr_str[:self.max_output_length] + "... (output truncated)"
                result.append(f"⚠️ **STDERR:**\n```\n{stderr_str}\n```")
            
            if process.returncode != 0:
                result.append(f"❌ **Exit Code:** {process.returncode}")
            else:
                if not result:  # No output but successful
                    result.append("✅ Command executed successfully (no output).")
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return f"❌ Error executing command: {str(e)}"
    
    @commands.command(name="shell", help="Execute a shell command (Owner only)")
    @commands.is_owner()
    async def shell_command(self, ctx, *, command_str):
        """Execute a shell command and return the output (Owner only)."""
        async with ctx.typing():
            result = await self._execute_command(command_str)
        
        # Split long messages if needed
        if len(result) > 2000:
            parts = [result[i:i+1990] for i in range(0, len(result), 1990)]
            for i, part in enumerate(parts):
                await ctx.reply(f"Part {i+1}/{len(parts)}:\n{part}")
        else:
            await ctx.reply(result)
    
    @app_commands.command(name="shell", description="Execute a shell command (Owner only)")
    @app_commands.describe(command="The shell command to execute")
    async def shell_slash(self, interaction: discord.Interaction, command: str):
        """Slash command version of shell command."""
        # Check if user is the bot owner
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command is restricted to the bot owner.", ephemeral=True)
            return
        
        # Defer the response as command execution might take time
        await interaction.response.defer()
        
        # Execute the command
        result = await self._execute_command(command)
        
        # Send the result
        if len(result) > 2000:
            parts = [result[i:i+1990] for i in range(0, len(result), 1990)]
            await interaction.followup.send(f"Part 1/{len(parts)}:\n{parts[0]}")
            for i, part in enumerate(parts[1:], 2):
                await interaction.followup.send(f"Part {i}/{len(parts)}:\n{part}")
        else:
            await interaction.followup.send(result)

async def setup(bot):
    await bot.add_cog(ShellCommandCog(bot))
    logger.info("ShellCommandCog loaded successfully.")
