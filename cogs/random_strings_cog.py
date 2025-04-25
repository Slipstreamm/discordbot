import discord
from discord.ext import commands
from discord import app_commands
import random

class PackGodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.string_list = [
        "google chrome garden gnome",
        "flip phone disowned",
        "ice cream cone metronome",
        "final chrome student loan",
        "underground flintstone chicken bone",
        "grandma went to the corner store and got her dentures thrown out the door",
        "baby face aint got no place tripped on my shoelace",
        "fortnite birth night",
        "doom zoom room full of gloom",
        "sentient bean saw a dream on a trampoline",
        "wifi sci-fi alibi from a samurai",
        "pickle jar avatar with a VCR",
        "garage band on demand ran off with a rubber band",
        "dizzy lizzy in a blizzard with a kazoo",
        "moonlight gaslight bug bite fight night",
        "toothpaste suitcase in a high-speed footrace",
        "donut warzone with a saxophone ringtone",
        "angsty toaster posted up like a rollercoaster",
        "spork fork stork on the New York sidewalk",
        "quantum raccoon stole my macaroon at high noon",
        "algebra grandma in a panorama wearing pajamas",
        "cactus cactus got a TikTok practice",
        "eggplant overlord on a hoverboard discord",
        "fridge magnet prophet dropped an omelet in the cockpit",
        "mystery meat got beat by a spreadsheet",
        "lava lamp champ with a tax refund stamp",
        "hologram scam on a traffic cam jam",
        "pogo stick picnic turned into a cryptic mythic",
        "sock puppet summit on a budget with a trumpet",
        "noodle crusade in a lemonade braid parade",
        "neon platypus doing calculus on a school bus",
        "hamster vigilante with a coffee-stained affidavit",
        "microwave rave in a medieval cave",
        "sidewalk chalk talk got hacked by a squawk",
        "yoga mat diplomat in a laundromat",
        "banana phone cyclone in a monotone zone",
        "jukebox paradox at a paradox detox",
        "laundry day melee with a broken bidet",
        "emoji samurai with a ramen supply and a laser eye",
        "grandpa hologram doing taxes on a banana stand",
        "bubble wrap trap",
        "waffle iron tyrant on a silent siren diet",
        "paperclip spaceship with a midlife crisis playlist",
        "marshmallow diplomat moonwalking into a courtroom spat",
        "gummy bear heir in an electric chair of despair",
        "fax machine dream team with a tambourine scheme",
        "soda cannon with a canon",
        "pretzel twist anarchist on a solar-powered tryst",
        "unicycle oracle at a discount popsicle miracle",
        "jousting mouse in a chainmail blouse with a holy spouse",
        "ye olde scroll turned into a cinnamon roll at the wizard patrol",
        "bard with a debit card locked in a tower of lard",
        "court jester investor lost a duel to a molester",
        "squire on fire writing poetry to a liar for hire",
        "archery mishap caused by a gremlin with a Snapchat app",
        "knight with stage fright performing Hamlet in moonlight"
        ]

        self.start_text = "shut yo"
        self.end_text = "ahh up"
        
    async def _packgod_logic(self):
        """Core logic for the packgod command."""
        # Randomly select 3 strings from the list
        selected_strings = random.sample(self.string_list, 3)
        
        # Format the message
        message = f"{self.start_text} "
        message += ", ".join(selected_strings)
        message += f" {self.end_text}"
        
        return message

    # --- Prefix Command ---
    @commands.command(name="packgod")
    async def packgod(self, ctx: commands.Context):
        """Send a message with hardcoded text and 3 random strings."""
        response = await self._packgod_logic()
        await ctx.reply(response)

    # --- Slash Command ---
    @app_commands.command(name="packgod", description="Send a message with hardcoded text and 3 random strings")
    async def packgod_slash(self, interaction: discord.Interaction):
        """Slash command version of packgod."""
        response = await self._packgod_logic()
        await interaction.response.send_message(response)

async def setup(bot: commands.Bot):
    await bot.add_cog(PackGodCog(bot))
