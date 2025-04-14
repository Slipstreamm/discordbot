import discord
from discord.ext import commands

async def handle_error(ctx_or_interaction, error):
    user_id = 452666956353503252  # Replace with the specific user ID
    error_message = f"An error occurred: {error}"

    if isinstance(ctx_or_interaction, commands.Context):
        if ctx_or_interaction.author.id == user_id:
            try:
                await ctx_or_interaction.send(content=error_message)
            except discord.Forbidden:
                await ctx_or_interaction.send("Unable to send you a DM with the error details.")
        else:
            await ctx_or_interaction.send("An error occurred while processing your command.")
    else:
        if ctx_or_interaction.user.id == user_id:
            await ctx_or_interaction.response.send_message(content=error_message, ephemeral=True)
        else:
            await ctx_or_interaction.response.send_message("An error occurred while processing your command.")