import discord

from discord import app_commands
from discord.ext import commands


class Commun(commands.Cog, name = "commun"):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(name = "commun", description = "Traduit en Commun, un texte écrit en Lynkr")
    async def commun_slash(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message("Cette fonctionnalité est en cours de développement, merci de bien vouloir patienter !", ephemeral = True)


async def setup(bot) -> None:
    await bot.add_cog(Commun(bot))
