import os

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get

intents = discord.Intents().all()
bot = commands.Bot(command_prefix = "$", intents = intents)

intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents = intents)
tree = app_commands.CommandTree(client)

os.chdir("/home/Mael382/firjtyehm")



@bot.event
async def on_ready():

    print("Bot running with:")
    print("Username: ", bot.user.name)
    print("User ID: ", bot.user.id)

    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            if filename[:-3] not in ["view"]:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print("Cogs loaded")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")

    except Exception as e:
        print(e)


@bot.tree.command(name = "presentation", description = "Donne la description de l'institution")
async def presentation_slash(interaction: discord.Interaction):

    with open("assets/text/desc-biblio-lotus.txt", mode = "r",
              encoding = 'utf-8') as f:
        desc_biblio_lotus = f.read()

    await interaction.response.send_message(desc_biblio_lotus, ephemeral = True)

@bot.tree.command(name = "codex", description = "Donne accès au rôle 'Détenteur du Codex' en échange du mantra du Codex des Anciens")
async def codex_slash(interaction: discord.Interaction, mantra: str):
    await interaction.response.defer(ephemeral = True)
    member = interaction.user
    role = get(member.guild.roles, name = "Détenteur du Codex")

    if member in role.members:
        await interaction.followup.send("Tu fais déjà partie des merveilleux Détenteurs du Codex !")

    elif mantra.upper() == "CODEGAM MINADA":
        await member.add_roles(role)
        await interaction.followup.send("Félicitations, tu intègres désormais les merveilleux Détenteurs du Codex !")

    else:
        await interaction.followup.send("Pas de chance, c'est raté !")



# bot.run("ID")
