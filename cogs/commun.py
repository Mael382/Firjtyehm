import discord

from discord import app_commands
from discord.ext import commands


class LynkrToCommun(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(name = "communlynkr", description = "Traduit en Commun, un texte écrit en Lynkr")
    async def lynkr_to_commun_slash(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message("Cette fonctionnalité est en cours de développement, merci de bien vouloir patienter !", ephemeral = True)


async def setup(bot) -> None:
    await bot.add_cog(Commun(bot))
