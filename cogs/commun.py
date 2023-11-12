import discord

from discord import app_commands
from discord.ext import commands

class Commun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name = "commun", description = "Traduit le texte en Commun")
    async def commun_slash(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message("Cette fonctionnalité n'est pas encore disponible, merci de bien vouloir patienter !", ephemeral = True)

async def setup(bot):
    await bot.add_cog(Commun(bot))