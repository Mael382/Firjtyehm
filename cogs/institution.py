from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get


MAIN_FOLDER = Path(__file__).parent.parent.resolve()


class Institution(commands.Cog):
    """Discord cog for Firjtyehm containing commands related to the Lotus Library discord guild.

    :param bot: Discord bot
    """

    def __init__(self, bot: commands.Bot) -> None:
        """Constructor method
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """...
        """
        print("Institution cog loaded")

    @app_commands.command(name="presentation", description="Description de la Bibliothèque du Lotus")
    async def slash_presentation(self, interaction: discord.Interaction) -> None:
        """Gives a brief presentation of the Lotus Library institution.

        :param interaction: User-triggered slash command
        """
        with open(MAIN_FOLDER / "assets/texts/txt/desc-biblio-lotus.txt", mode="r", encoding="utf-8") as desc:
            presentation = desc.read()
        await interaction.response.send_message(presentation, ephemeral=True)

    @app_commands.command(name="codex", description="Accès au rôle Codex")
    @app_commands.guild_only()
    async def slash_codex(self, interaction: discord.Interaction, mantra: str) -> None:
        """Gives access to the `Codex` discord role in exchange for the mantra symbolizing the Codex of the Ancients.

        :param interaction: User-triggered slash command
        :param mantra: User-entered text in the slash command
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        role = get(member.guild.roles, name="Codex")
        if member in role.members:
            await interaction.followup.send(f"Tu as déjà le rôle {role.mention} !")
        elif " ".join(mantra.split()).casefold() == "codegam minada":
            await member.add_roles(role)
            await interaction.followup.send(f"Félicitations, tu obtiens le rôle {role.mention} !")
        else:
            await interaction.followup.send(
                "Non, il ne s'agit pas du mantra symbolisant le Codex de la Langue des Anciens.")


async def setup(bot: commands.Bot) -> None:
    """...
    """
    await bot.add_cog(Institution(bot))
