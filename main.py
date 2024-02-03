import os
from dotenv import load_dotenv
from datetime import timedelta, datetime, time, timezone

import discord
from discord.ext import commands, tasks
from discord.utils import get


load_dotenv()


TOKEN = os.getenv("TOKEN")

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.message_content = True

OWNER_ID = int(os.getenv("OWNER_ID"))

TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID"))
MAIN_GUILD_ID = int(os.getenv("MAIN_GUILD_ID"))


class Firjtyehm(commands.Bot):
    """Discord bot for the Lotus Library on Herobrine.fr.

    :param testing: `True` if the bot is in debug mode, and `False` otherwise, defaults to `False`
    """

    def __init__(self, testing: bool = False) -> None:
        """Constructor method
        """
        super().__init__(command_prefix="!", intents=INTENTS)
        self.testing = testing

    async def setup_hook(self) -> None:
        # Cogs loading
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")
        # Commands syncing
        if self.testing:
            test_guild = discord.Object(id=TEST_GUILD_ID)
            self.tree.clear_commands(guild=test_guild)
            self.tree.copy_global_to(guild=test_guild)
            await self.tree.sync(guild=test_guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        """Sends status data to bot owner when bot get online.
        """
        print("Firjtyehm bot online")
        print("------")
        # Sending status data to the bot owner
        owner = get(self.users, id=OWNER_ID)
        embed = discord.Embed(title=self.user.name,
                              url="https://discord.com/channels/1056241840891887626/1056565691299405834",
                              description="Bot has started successfully !",
                              timestamp=datetime.today(),
                              color=discord.Color.dark_gold())
        embed.set_thumbnail(url=get(self.guilds, id=MAIN_GUILD_ID).icon.url)
        embed.add_field(name="Bot ID", value=self.user.id, inline=False)
        embed.add_field(name="Bot's servers", value="\n".join([guild.name for guild in self.guilds]), inline=False)
        embed.add_field(name="Servers' IDs", value="\n".join([str(guild.id) for guild in self.guilds]), inline=False)
        await owner.send(embed=embed)
        # Starting tasks loop
        self.is_running.start()

    @tasks.loop(time=time(tzinfo=timezone(timedelta(hours=1))))
    async def is_running(self) -> None:
        """Sends status data to bot owner every day at midnight (UTC+1).
        """
        owner = get(self.users, id=OWNER_ID)
        embed = discord.Embed(title=self.user.name,
                              url="https://discord.com/channels/1056241840891887626/1056565691299405834",
                              description="Bot is still running !",
                              timestamp=datetime.today(),
                              color=discord.Color.dark_gold())
        embed.set_thumbnail(url=get(self.guilds, id=MAIN_GUILD_ID).icon.url)
        embed.add_field(name="Bot ID", value=self.user.id, inline=False)
        embed.add_field(name="Bot's servers", value="\n".join([guild.name for guild in self.guilds]), inline=False)
        embed.add_field(name="Servers' IDs", value="\n".join([str(guild.id) for guild in self.guilds]), inline=False)
        await owner.send(embed=embed)


if __name__ == "__main__":
    bot = Firjtyehm()
    bot.run(TOKEN)
