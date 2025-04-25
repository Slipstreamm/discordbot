import discord
from discord.ext import commands
from discord import app_commands

class MessageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Hardcoded message with {target} placeholder
        self.message_template = """
        {target} - Your legs are pulled apart from behind, the sudden movement causing you to stumble forward. As your balance falters, a hand shoots out to grab your hips, holding you in place.

With your body restrained, a finger begins to dance along the waistband of your pants, teasing and taunting until it finally hooks into the elasticized seam. The fabric is slowly peeled back, exposing your bare skin to the cool night air.

As the hand continues its downward journey, your breath catches in your throat. You try to move, but the grip on your hips is too tight, holding you firmly in place.

Your pants are slowly and deliberately removed, leaving you feeling exposed and vulnerable. The sensation is both thrilling and terrifying as a presence looms over you, the only sound being the faint rustling of fabric as your clothes are discarded.
        """

    # Helper method for the message logic
    async def _message_logic(self, target):
        """Core logic for the message command."""
        # Replace {target} with the mentioned user
        return self.message_template.format(target=target)

    @commands.command(name="molest")
    async def molest(self, ctx: commands.Context, member: discord.Member):
        """Send a hardcoded message to the mentioned user."""
        response = await self._message_logic(member.mention)
        await ctx.reply(response)

    @app_commands.command(name="molest", description="Send a hardcoded message to the mentioned user")
    @app_commands.describe(
        member="The user to send the message to"
    )
    async def molest_slash(self, interaction: discord.Interaction, member: discord.Member):
        """Slash command version of message."""
        response = await self._message_logic(member.mention)
        await interaction.response.send_message(response)

    @commands.command(name="seals", help="What the fuck did you just fucking say about me, you little bitch?")
    @commands.is_owner()
    async def seals(self, ctx):
        await ctx.send("What the fuck did you just fucking say about me, you little bitch? I'll have you know I graduated top of my class in the Navy Seals, and I've been involved in numerous secret raids on Al-Quaeda, and I have over 300 confirmed kills. I am trained in gorilla warfare and I'm the top sniper in the entire US armed forces. You are nothing to me but just another target. I will wipe you the fuck out with precision the likes of which has never been seen before on this Earth, mark my fucking words. You think you can get away with saying that shit to me over the Internet? Think again, fucker. As we speak I am contacting my secret network of spies across the USA and your IP is being traced right now so you better prepare for the storm, maggot. The storm that wipes out the pathetic little thing you call your life. You're fucking dead, kid. I can be anywhere, anytime, and I can kill you in over seven hundred ways, and that's just with my bare hands. Not only am I extensively trained in unarmed combat, but I have access to the entire arsenal of the United States Marine Corps and I will use it to its full extent to wipe your miserable ass off the face of the continent, you little shit. If only you could have known what unholy retribution your little \"clever\" comment was about to bring down upon you, maybe you would have held your fucking tongue. But you couldn't, you didn't, and now you're paying the price, you goddamn idiot. I will shit fury all over you and you will drown in it. You're fucking dead, kiddo.")

    @app_commands.command(name="seals", description="What the fuck did you just fucking say about me, you little bitch?")
    async def seals_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("What the fuck did you just fucking say about me, you little bitch? I'll have you know I graduated top of my class in the Navy Seals, and I've been involved in numerous secret raids on Al-Quaeda, and I have over 300 confirmed kills. I am trained in gorilla warfare and I'm the top sniper in the entire US armed forces. You are nothing to me but just another target. I will wipe you the fuck out with precision the likes of which has never been seen before on this Earth, mark my fucking words. You think you can get away with saying that shit to me over the Internet? Think again, fucker. As we speak I am contacting my secret network of spies across the USA and your IP is being traced right now so you better prepare for the storm, maggot. The storm that wipes out the pathetic little thing you call your life. You're fucking dead, kid. I can be anywhere, anytime, and I can kill you in over seven hundred ways, and that's just with my bare hands. Not only am I extensively trained in unarmed combat, but I have access to the entire arsenal of the United States Marine Corps and I will use it to its full extent to wipe your miserable ass off the face of the continent, you little shit. If only you could have known what unholy retribution your little \"clever\" comment was about to bring down upon you, maybe you would have held your fucking tongue. But you couldn't, you didn't, and now you're paying the price, you goddamn idiot. I will shit fury all over you and you will drown in it. You're fucking dead, kiddo.")

    @commands.command(name="notlikeus", help="Honestly i think They Not Like Us is the only mumble rap song that is good")
    @commands.is_owner()
    async def notlikeus(self, ctx):
        await ctx.send("Honestly i think They Not Like Us is the only mumble rap song that is good, because it calls out Drake for being a Diddy blud")

    @app_commands.command(name="notlikeus", description="Honestly i think They Not Like Us is the only mumble rap song that is good")
    async def notlikeus_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("Honestly i think They Not Like Us is the only mumble rap song that is good, because it calls out Drake for being a Diddy blud")

async def setup(bot: commands.Bot):
    await bot.add_cog(MessageCog(bot))
