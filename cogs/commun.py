import discord
from discord import app_commands
from discord.ext import commands


class Commun(commands.Cog):
    """Discord cog for Firjtyehm containing commands related to translation from a foreign language into `Commun`.

    :param bot: Discord bot
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Constructor method
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("Commun cog loaded")

    @app_commands.command(name="commun", description="Traduction Lynkr -> Commun")
    @app_commands.guild_only()
    async def commun_slash(self, interaction: discord.Interaction, texte: str) -> None:
        """Translates text from `Lynkr` to `Commun`.

        :param interaction: User-triggered slash command
        :param texte: User-entered text in the slash command
        """
        await interaction.response.send_message(":construction: Fonctionnalité encore en cours de développement. "
                                                ":construction:", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Commun(bot))
