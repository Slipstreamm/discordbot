import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import re
import os
import platform
import logging
from collections import defaultdict

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

        # Store persistent shell sessions
        self.owner_shell_sessions = defaultdict(lambda: {
            'cwd': os.getcwd(),
            'env': os.environ.copy()
        })

        # Store persistent docker shell sessions
        self.docker_shell_sessions = defaultdict(lambda: {
            'container_id': None,
            'created': False
        })

    async def _execute_command(self, command_str, session_id=None, use_docker=False):
        """
        Execute a shell command and return the output.
        If session_id is provided, use the persistent session.
        If use_docker is True, run the command in a Docker container.
        """
        # Check if command is allowed
        allowed, reason = is_command_allowed(command_str)
        if not allowed:
            return f"⛔ Command not allowed: {reason}"

        # Log the command execution
        logger.info(f"Executing {'docker ' if use_docker else ''}shell command: {command_str}")

        if use_docker:
            return await self._execute_docker_command(command_str, session_id)
        else:
            return await self._execute_local_command(command_str, session_id)


    async def _execute_local_command(self, command_str, session_id=None):
        """
        Execute a command locally with optional session persistence.
        Uses a synchronous subprocess in a thread for cross-platform compatibility.
        """
        import subprocess

        if session_id:
            session = self.owner_shell_sessions[session_id]
            cwd = session['cwd']
            env = session['env']
        else:
            cwd = os.getcwd()
            env = os.environ.copy()

        def run_subprocess():
            try:
                proc = subprocess.Popen(
                    command_str,
                    shell=True,
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                try:
                    stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    return (stdout, stderr, -1, True)
                return (stdout, stderr, proc.returncode, False)
            except Exception as e:
                return (b"", str(e).encode(), -1, False)

        stdout, stderr, returncode, timed_out = await asyncio.to_thread(run_subprocess)

        # Update session working directory if 'cd' command was used
        if session_id and command_str.strip().startswith('cd '):
            # Try to update session cwd (best effort, not robust for chained commands)
            new_dir = command_str.strip()[3:].strip()
            if os.path.isabs(new_dir):
                session['cwd'] = new_dir
            else:
                session['cwd'] = os.path.abspath(os.path.join(cwd, new_dir))

        stdout_str = stdout.decode('utf-8', errors='replace').strip()
        stderr_str = stderr.decode('utf-8', errors='replace').strip()

        result = []
        if timed_out:
            result.append(f"⏱️ Command timed out after {self.timeout_seconds} seconds.")

        if stdout_str:
            if len(stdout_str) > self.max_output_length:
                stdout_str = stdout_str[:self.max_output_length] + "... (output truncated)"
            result.append(f"📤 **STDOUT:**\n```\n{stdout_str}\n```")

        if stderr_str:
            if len(stderr_str) > self.max_output_length:
                stderr_str = stderr_str[:self.max_output_length] + "... (output truncated)"
            result.append(f"⚠️ **STDERR:**\n```\n{stderr_str}\n```")

        if returncode != 0 and not timed_out:
            result.append(f"❌ **Exit Code:** {returncode}")
        else:
            if not result:  # No output but successful
                result.append("✅ Command executed successfully (no output).")

        return "\n".join(result)

    async def _execute_docker_command(self, command_str, session_id):
        """
        Execute a command in a Docker container with session persistence.
        """
        # First, check if Docker is available
        docker_check_cmd = "docker --version"
        try:
            process = await asyncio.create_subprocess_shell(
                docker_check_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )

            # We don't need the output, just the return code
            await process.communicate()

            if process.returncode != 0:
                return f"❌ Docker is not available on this system. Please install Docker to use this command."
        except Exception as e:
            logger.error(f"Error checking Docker availability: {e}")
            return f"❌ Error checking Docker availability: {str(e)}"

        session = self.docker_shell_sessions[session_id]

        # Create a new container if one doesn't exist for this session
        if not session['created']:
            # Create a new container with a minimal Linux image
            create_container_cmd = "docker run -d --rm --name shell_" + session_id + " alpine:latest tail -f /dev/null"

            process = await asyncio.create_subprocess_shell(
                create_container_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace').strip()
                return f"❌ Failed to create Docker container: {error_msg}"

            container_id = stdout.decode('utf-8', errors='replace').strip()
            session['container_id'] = container_id
            session['created'] = True

            logger.info(f"Created Docker container with ID: {container_id} for session {session_id}")

        # Execute the command in the container
        # Escape double quotes in the command string
        escaped_cmd = command_str.replace('"', '\\"')
        docker_exec_cmd = f"docker exec shell_{session_id} sh -c \"{escaped_cmd}\""

        process = await asyncio.create_subprocess_shell(
            docker_exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )

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

    @commands.command(name="ownershell", help="Execute a shell command directly on the host (Owner only)")
    @commands.is_owner()
    async def ownershell_command(self, ctx, *, command_str):
        """Execute a shell command directly on the host (Owner only)."""
        # Get or create a session ID for this user
        session_id = str(ctx.author.id)

        async with ctx.typing():
            result = await self._execute_command(command_str, session_id=session_id, use_docker=False)

        # Split long messages if needed
        if len(result) > 2000:
            parts = [result[i:i+1990] for i in range(0, len(result), 1990)]
            for i, part in enumerate(parts):
                await ctx.reply(f"Part {i+1}/{len(parts)}:\n{part}")
        else:
            await ctx.reply(result)

    @commands.command(name="shell", help="Execute a shell command in a Docker container")
    async def shell_command(self, ctx, *, command_str):
        """Execute a shell command in a Docker container."""
        # Get or create a session ID for this user
        session_id = str(ctx.author.id)

        async with ctx.typing():
            result = await self._execute_command(command_str, session_id=session_id, use_docker=True)

        # Split long messages if needed
        if len(result) > 2000:
            parts = [result[i:i+1990] for i in range(0, len(result), 1990)]
            for i, part in enumerate(parts):
                await ctx.reply(f"Part {i+1}/{len(parts)}:\n{part}")
        else:
            await ctx.reply(result)

    @commands.command(name="newshell", help="Reset your shell session (Owner only)")
    @commands.is_owner()
    async def newshell_command(self, ctx, *, shell_type="docker"):
        """Reset a shell session (Owner only)."""
        session_id = str(ctx.author.id)

        if shell_type.lower() in ["docker", "container", "safe"]:
            # If there's an existing container, stop and remove it
            session = self.docker_shell_sessions[session_id]
            if session['created'] and session['container_id']:
                try:
                    # Stop the container
                    stop_cmd = f"docker stop shell_{session_id}"
                    process = await asyncio.create_subprocess_shell(
                        stop_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        shell=True
                    )
                    await process.communicate()
                except Exception as e:
                    logger.error(f"Error stopping Docker container: {e}")

            # Reset the session
            self.docker_shell_sessions[session_id] = {
                'container_id': None,
                'created': False
            }

            await ctx.reply("✅ Docker shell session has been reset.")
        elif shell_type.lower() in ["owner", "host", "local"]:
            # Reset the owner shell session
            self.owner_shell_sessions[session_id] = {
                'cwd': os.getcwd(),
                'env': os.environ.copy()
            }

            await ctx.reply("✅ Owner shell session has been reset.")
        else:
            await ctx.reply("❌ Invalid shell type. Use 'docker' or 'owner'.")

    @app_commands.command(name="ownershell", description="Execute a shell command directly on the host (Owner only)")
    @app_commands.describe(command="The shell command to execute")
    async def ownershell_slash(self, interaction: discord.Interaction, command: str):
        """Slash command version of ownershell command."""
        # Check if user is the bot owner
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command is restricted to the bot owner.", ephemeral=True)
            return

        # Get or create a session ID for this user
        session_id = str(interaction.user.id)

        # Defer the response as command execution might take time
        await interaction.response.defer()

        # Execute the command
        result = await self._execute_command(command, session_id=session_id, use_docker=False)

        # Send the result
        if len(result) > 2000:
            parts = [result[i:i+1990] for i in range(0, len(result), 1990)]
            await interaction.followup.send(f"Part 1/{len(parts)}:\n{parts[0]}")
            for i, part in enumerate(parts[1:], 2):
                await interaction.followup.send(f"Part {i}/{len(parts)}:\n{part}")
        else:
            await interaction.followup.send(result)

    @app_commands.command(name="shell", description="Execute a shell command in a Docker container (Owner only)")
    @app_commands.describe(command="The shell command to execute")
    async def shell_slash(self, interaction: discord.Interaction, command: str):
        """Slash command version of shell command."""
        # Check if user is the bot owner
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command is restricted to the bot owner.", ephemeral=True)
            return

        # Get or create a session ID for this user
        session_id = str(interaction.user.id)

        # Defer the response as command execution might take time
        await interaction.response.defer()

        # Execute the command
        result = await self._execute_command(command, session_id=session_id, use_docker=True)

        # Send the result
        if len(result) > 2000:
            parts = [result[i:i+1990] for i in range(0, len(result), 1990)]
            await interaction.followup.send(f"Part 1/{len(parts)}:\n{parts[0]}")
            for i, part in enumerate(parts[1:], 2):
                await interaction.followup.send(f"Part {i}/{len(parts)}:\n{part}")
        else:
            await interaction.followup.send(result)

    @app_commands.command(name="newshell", description="Reset your shell session (Owner only)")
    @app_commands.describe(shell_type="The type of shell to reset ('docker' or 'owner')")
    @app_commands.choices(shell_type=[
        app_commands.Choice(name="Docker Container Shell", value="docker"),
        app_commands.Choice(name="Owner Host Shell", value="owner")
    ])
    async def newshell_slash(self, interaction: discord.Interaction, shell_type: str = "docker"):
        """Slash command version of newshell command."""
        # Check if user is the bot owner
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("⛔ This command is restricted to the bot owner.", ephemeral=True)
            return

        session_id = str(interaction.user.id)

        if shell_type.lower() in ["docker", "container", "safe"]:
            # If there's an existing container, stop and remove it
            session = self.docker_shell_sessions[session_id]
            if session['created'] and session['container_id']:
                try:
                    # Stop the container
                    stop_cmd = f"docker stop shell_{session_id}"
                    process = await asyncio.create_subprocess_shell(
                        stop_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        shell=True
                    )
                    await process.communicate()
                except Exception as e:
                    logger.error(f"Error stopping Docker container: {e}")

            # Reset the session
            self.docker_shell_sessions[session_id] = {
                'container_id': None,
                'created': False
            }

            await interaction.response.send_message("✅ Docker shell session has been reset.")
        elif shell_type.lower() in ["owner", "host", "local"]:
            # Reset the owner shell session
            self.owner_shell_sessions[session_id] = {
                'cwd': os.getcwd(),
                'env': os.environ.copy()
            }

            await interaction.response.send_message("✅ Owner shell session has been reset.")
        else:
            await interaction.response.send_message("❌ Invalid shell type. Use 'docker' or 'owner'.")

    async def cog_unload(self):
        """Clean up resources when the cog is unloaded."""
        # Check if Docker is available before trying to stop containers
        docker_check_cmd = "docker --version"
        try:
            process = await asyncio.create_subprocess_shell(
                docker_check_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )

            # We don't need the output, just the return code
            await process.communicate()

            if process.returncode != 0:
                logger.warning("Docker is not available, skipping container cleanup.")
                return

            # Stop and remove all Docker containers
            for session_id, session in self.docker_shell_sessions.items():
                if session['created'] and session['container_id']:
                    try:
                        # Stop the container
                        stop_cmd = f"docker stop shell_{session_id}"
                        process = await asyncio.create_subprocess_shell(
                            stop_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            shell=True
                        )
                        await process.communicate()
                    except Exception as e:
                        logger.error(f"Error stopping Docker container during unload: {e}")
        except Exception as e:
            logger.error(f"Error checking Docker availability during unload: {e}")

async def setup(bot):
    try:
        logger.info("Attempting to load ShellCommandCog...")
        await bot.add_cog(ShellCommandCog(bot))
        logger.info("ShellCommandCog loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load ShellCommandCog: {e}")
        raise  # Re-raise the exception so the bot's error handling can catch it
