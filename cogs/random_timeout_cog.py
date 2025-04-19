import discord
from discord.ext import commands
import random
import datetime
import logging

# Set up logging
logger = logging.getLogger(__name__)

class RandomTimeoutCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_user_id = 748405715520978965  # The specific user ID to target
        self.timeout_chance = 0.01  # 1% chance (0.01)
        self.timeout_duration = 60  # 1 minute in seconds
        self.log_channel_id = 1363007131980136600  # Channel ID to log all events
        logger.info(f"RandomTimeoutCog initialized with target user ID: {self.target_user_id}")

    async def create_log_embed(self, message, roll, was_timed_out):
        """Create an embed for logging the timeout event"""
        # Create the embed with appropriate color based on timeout status
        color = discord.Color.red() if was_timed_out else discord.Color.green()

        embed = discord.Embed(
            title=f"{'⚠️ TIMEOUT TRIGGERED' if was_timed_out else '✅ No Timeout'}",
            description=f"Message from <@{self.target_user_id}> was processed",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        # Add user information
        embed.add_field(
            name="👤 User Information",
            value=f"**User:** {message.author.mention}\n**User ID:** {message.author.id}",
            inline=False
        )

        # Add roll information
        embed.add_field(
            name="🎲 Roll Information",
            value=f"**Roll:** {roll:.6f}\n**Threshold:** {self.timeout_chance:.6f}\n**Chance:** {self.timeout_chance * 100:.2f}%\n**Result:** {'TIMEOUT' if was_timed_out else 'SAFE'}",
            inline=False
        )

        # Add message information
        embed.add_field(
            name="💬 Message Information",
            value=f"**Channel:** {message.channel.mention}\n**Message Link:** [Click Here]({message.jump_url})",
            inline=False
        )

        # Set footer
        embed.set_footer(text=f"Random Timeout System | {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Set author with user avatar
        embed.set_author(name=f"{message.author.name}#{message.author.discriminator}", icon_url=message.author.display_avatar.url)

        return embed

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Event listener for messages to randomly timeout the target user"""
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if the message author is the target user
        if message.author.id == self.target_user_id:
            # Generate a random number between 0 and 1
            roll = random.random()
            was_timed_out = False

            # If the roll is less than the timeout chance (1%), timeout the user
            if roll < self.timeout_chance:
                try:
                    # Calculate timeout until time (1 minute from now)
                    timeout_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=self.timeout_duration)

                    # Apply the timeout
                    await message.author.timeout(timeout_until, reason="Random 1% chance timeout")
                    was_timed_out = True

                    # Send a message to the channel
                    await message.channel.send(
                        f"🎲 Bad luck! {message.author.mention} rolled a {roll:.4f} and got timed out for 1 minute! (1% chance)",
                        delete_after=10  # Delete after 10 seconds
                    )

                    logger.info(f"User {message.author.id} was randomly timed out for 1 minute")
                except discord.Forbidden:
                    logger.warning(f"Bot doesn't have permission to timeout user {message.author.id}")
                except discord.HTTPException as e:
                    logger.error(f"Failed to timeout user {message.author.id}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error when timing out user {message.author.id}: {e}")

            # Log the event to the specified channel regardless of timeout result
            try:
                # Get the log channel
                log_channel = self.bot.get_channel(self.log_channel_id)
                if log_channel:
                    # Create and send the embed
                    embed = await self.create_log_embed(message, roll, was_timed_out)
                    await log_channel.send(embed=embed)
                else:
                    logger.warning(f"Log channel with ID {self.log_channel_id} not found")
            except Exception as e:
                logger.error(f"Error sending log message: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f'{self.__class__.__name__} cog has been loaded.')

async def setup(bot: commands.Bot):
    await bot.add_cog(RandomTimeoutCog(bot))
    print("RandomTimeoutCog loaded successfully!")
