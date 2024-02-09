import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta, datetime, time, timezone

import discord
from discord.ext import commands, tasks
from discord.utils import get


MAIN_FOLDER = Path(__file__).parent.resolve()

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.message_content = True


class Firjtyehm(commands.Bot):
    """Discord bot for the Lotus Library on Herobrine.fr.
    """

    def __init__(self) -> None:
        """Constructor method
        """
        super().__init__(command_prefix="!", intents=INTENTS)

    async def setup_hook(self) -> None:
        """...
        """
        # Loading cogs
        for filename in os.listdir(MAIN_FOLDER / "cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")

        # Syncing commands
        await self.tree.sync()

    async def on_ready(self) -> None:
        """Sends status data to bot owner when bot get online.
        """
        print("Firjtyehm bot online")
        print("------")

        # Sending status data to bot owner
        if OWNER_ID:
            owner = get(self.users, id=OWNER_ID)
            embed = discord.Embed(title=self.user.name,
                                  url=MAIN_CHANNEL_URL,
                                  description="Bot has started successfully !",
                                  timestamp=datetime.today(),
                                  color=discord.Color.dark_gold())
            if MAIN_GUILD_ID:
                embed.set_thumbnail(url=get(self.guilds, id=MAIN_GUILD_ID).icon.url)
            embed.add_field(name="Bot's ID", value=self.user.id, inline=False)
            embed.add_field(name="Bot's servers", value="\n".join([guild.name for guild in self.guilds]), inline=False)
            embed.add_field(name="Servers' IDs", value="\n".join([str(guild.id) for guild in self.guilds]),
                            inline=False)
            await owner.send(embed=embed)

        # Starting tasks loop
        self.is_running.start()

    @tasks.loop(time=time(tzinfo=timezone(timedelta(hours=1))))
    async def is_running(self) -> None:
        """Sends status data to bot owner every day at midnight (UTC+1).
        """
        if OWNER_ID:
            owner = get(self.users, id=OWNER_ID)
            embed = discord.Embed(title=self.user.name,
                                  url=MAIN_CHANNEL_URL,
                                  description="Bot is still running !",
                                  timestamp=datetime.today(),
                                  color=discord.Color.dark_gold())
            if MAIN_GUILD_ID:
                embed.set_thumbnail(url=get(self.guilds, id=MAIN_GUILD_ID).icon.url)
            embed.add_field(name="Bot's ID", value=self.user.id, inline=False)
            embed.add_field(name="Bot's servers", value="\n".join([guild.name for guild in self.guilds]), inline=False)
            embed.add_field(name="Servers' IDs", value="\n".join([str(guild.id) for guild in self.guilds]),
                            inline=False)
            await owner.send(embed=embed)


if __name__ == "__main__":
    load_dotenv()

    TOKEN = os.getenv("TOKEN")
    if TOKEN is None:
        raise ValueError("TOKEN is not defined")

    OWNER_ID = int(os.getenv("OWNER_ID"))
    MAIN_GUILD_ID = int(os.getenv("MAIN_GUILD_ID"))
    MAIN_CHANNEL_URL = os.getenv("MAIN_CHANNEL_URL")

    bot = Firjtyehm()
    bot.run(TOKEN)
