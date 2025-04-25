import discord
from discord.ext import commands
from discord import app_commands
import time
import psutil
import platform
import GPUtil
from cpuinfo import get_cpu_info
import distro # Ensure this is installed
import subprocess

# Import wmi for Windows motherboard info
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

class SystemCheckCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _system_check_logic(self, context_or_interaction):
        """Return detailed bot and system information as a Discord embed."""
        # Bot information
        bot_user = self.bot.user
        guild_count = len(self.bot.guilds)
        # Efficiently count unique non-bot members across guilds
        user_ids = set()
        for guild in self.bot.guilds:
            try:
                # Fetch members if needed, handle potential exceptions
                async for member in guild.fetch_members(limit=None): # Fetch all members
                     if not member.bot:
                         user_ids.add(member.id)
            except discord.Forbidden:
                print(f"Missing permissions to fetch members in guild: {guild.name} ({guild.id})")
            except discord.HTTPException as e:
                print(f"HTTP error fetching members in guild {guild.name}: {e}")
            except Exception as e:
                 print(f"Unexpected error fetching members in guild {guild.name}: {e}")

        user_count = len(user_ids)


        # System information
        system = platform.system()
        os_info = f"{system} {platform.release()}"
        hostname = platform.node()
        distro_info_str = "" # Renamed variable
        if system == "Linux":
            try:
                # Use distro library for better Linux distribution detection
                distro_name = distro.name(pretty=True)
                distro_info_str = f"\n**Distro:** {distro_name}"
            except ImportError:
                distro_info_str = "\n**Distro:** (Install 'distro' package for details)"
            except Exception as e:
                distro_info_str = f"\n**Distro:** (Error getting info: {e})"
        elif system == "Windows":
             # Add Windows version details if possible
             try:
                 win_ver = platform.version() # e.g., '10.0.19041'
                 win_build = platform.win32_ver()[1] # e.g., '19041'
                 os_info = f"Windows {win_ver} (Build {win_build})"
             except Exception as e:
                 print(f"Could not get detailed Windows version: {e}")
                 # Keep the basic os_info

        uptime_seconds = time.time() - psutil.boot_time()
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = ""
        if days > 0:
            uptime_str += f"{int(days)}d "
        uptime_str += f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
        uptime = uptime_str.strip()

        # Hardware information
        cpu_usage = psutil.cpu_percent(interval=0.5) # Shorter interval might be okay
        try:
            cpu_info_dict = get_cpu_info() # Renamed variable
            cpu_name = cpu_info_dict.get('brand_raw', 'N/A')
        except Exception as e:
            print(f"Error getting CPU info: {e}")
            cpu_name = "N/A"

        # Get motherboard information
        motherboard_info = self._get_motherboard_info()

        memory = psutil.virtual_memory()
        ram_usage = f"{memory.used // (1024 ** 2)} MB / {memory.total // (1024 ** 2)} MB ({memory.percent}%)"

        # GPU Information (using GPUtil for cross-platform consistency if available)
        gpu_info_lines = []
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                for gpu in gpus:
                    gpu_info_lines.append(
                        f"{gpu.name} ({gpu.load*100:.1f}% Load, {gpu.memoryUsed:.0f}/{gpu.memoryTotal:.0f} MB VRAM)"
                    )
                gpu_info = "\n".join(gpu_info_lines)
            else:
                gpu_info = "No dedicated GPU detected by GPUtil."
        except ImportError:
             gpu_info = "GPUtil library not installed. Cannot get detailed GPU info."
        except Exception as e:
            print(f"Error getting GPU info via GPUtil: {e}")
            gpu_info = f"Error retrieving GPU info: {e}"

        # Determine user and avatar URL based on context type
        if isinstance(context_or_interaction, commands.Context):
            user = context_or_interaction.author
            avatar_url = user.display_avatar.url
        elif isinstance(context_or_interaction, discord.Interaction):
            user = context_or_interaction.user
            avatar_url = user.display_avatar.url
        else: # Fallback or handle error if needed
            user = self.bot.user # Or some default
            avatar_url = self.bot.user.display_avatar.url if self.bot.user else None

        # Create embed
        embed = discord.Embed(title="📊 System Status", color=discord.Color.blue())
        if bot_user:
            embed.set_thumbnail(url=bot_user.display_avatar.url)

        # Bot Info Field
        if bot_user:
            embed.add_field(
                name="🤖 Bot Information",
                value=f"**Name:** {bot_user.name}\n"
                      f"**ID:** {bot_user.id}\n"
                      f"**Servers:** {guild_count}\n"
                      f"**Unique Users:** {user_count}",
                inline=False
            )
        else:
             embed.add_field(
                name="🤖 Bot Information",
                value="Bot user information not available.",
                inline=False
            )

        # System Info Field
        embed.add_field(
            name="🖥️ System Information",
            value=f"**OS:** {os_info}{distro_info_str}\n" # Use renamed variable
                  f"**Hostname:** {hostname}\n"
                  f"**Uptime:** {uptime}",
            inline=False
        )

        # Hardware Info Field
        embed.add_field(
            name="⚙️ Hardware Information",
            value=f"**Device Model:** {motherboard_info}\n"
                  f"**CPU:** {cpu_name}\n"
                  f"**CPU Usage:** {cpu_usage}%\n"
                  f"**RAM Usage:** {ram_usage}\n"
                  f"**GPU Info:**\n{gpu_info}",
            inline=False
        )

        if user:
            embed.set_footer(text=f"Requested by: {user.display_name}", icon_url=avatar_url)
        embed.timestamp = discord.utils.utcnow()

        return embed

    # --- Prefix Command ---
    @commands.command(name="systemcheck")
    async def system_check(self, ctx: commands.Context):
        """Check the bot and system status."""
        embed = await self._system_check_logic(ctx) # Pass context
        await ctx.reply(embed=embed)

    # --- Slash Command ---
    @app_commands.command(name="systemcheck", description="Check the bot and system status")
    async def system_check_slash(self, interaction: discord.Interaction):
        """Slash command version of system check."""
        embed = await self._system_check_logic(interaction) # Pass interaction
        await interaction.response.send_message(embed=embed)

    def _get_motherboard_info(self):
        """Get motherboard information based on the operating system."""
        system = platform.system()
        try:
            if system == "Windows":
                if WMI_AVAILABLE:
                    w = wmi.WMI()
                    for board in w.Win32_BaseBoard():
                        return f"{board.Manufacturer} {board.Product}"
                return "WMI module not available"
            elif system == "Linux":
                # Read motherboard product name from sysfs
                try:
                    with open("/sys/devices/virtual/dmi/id/product_name", "r") as f:
                        product_name = f.read().strip()
                    return product_name if product_name else "Unknown motherboard"
                except FileNotFoundError:
                    return "/sys/devices/virtual/dmi/id/product_name not found"
                except Exception as e:
                    return f"Error reading motherboard info: {e}"
                except Exception as e:
                    return f"Error: {str(e)}"
            else:
                return f"Unsupported OS: {system}"
        except Exception as e:
            print(f"Error getting motherboard info: {e}")
            return "Error retrieving motherboard info"

async def setup(bot):
    await bot.add_cog(SystemCheckCog(bot))
