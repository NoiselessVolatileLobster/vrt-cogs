import asyncio
import logging
import math
import random
from datetime import datetime
from typing import Literal

import discord
from redbot.core import Config, bank, checks, commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import (
    bold,
    box,
    humanize_list,
    humanize_number,
    pagify,
)
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from redbot.core.utils.predicates import MessagePredicate

__version__ = "3.4.12"
log = logging.getLogger("red.vrt.bonging")


class Bonging(commands.Cog):
    """Bonging, it hunts birds and things that fly."""

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord", "owner", "user", "user_strict"],
        user_id: int,
    ):
        await self.config.user_from_id(user_id).clear()

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 2784481002, force_registration=True)

        self.animals = {
            "beer": ":beer: **_Clink!_**",
            "beers": ":beers: **_CHEERS!_**",
            "oregano": ":maple_leaf: **_*giggles_**",

        }
        self.in_game = set()

        self.next_bong = {}

        default_guild = {
            "hunt_interval_minimum": 900,
            "hunt_interval_maximum": 3600,
            "wait_for_bong_timeout": 20,
            "channels": [],
            "bong_time": False,
            "bong_words": True,
            "reward_range": [],
            "munchies": False,  # Lose credits for shooting
        }
        default_global = {
            "reward_range": [],  # For bots with global banks
        }
        default_user = {"score": {}, "total": 0}
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

    @commands.guild_only()
    @commands.group()
    async def bonging(self, ctx):
        """Bonging, it hunts birds and things that fly."""
        if ctx.invoked_subcommand is None:
            guild_data = await self.config.guild(ctx.guild).all()
            if not guild_data["channels"]:
                channel_names = ["No channels set."]
            else:
                channel_names = []
                for channel_id in guild_data["channels"]:
                    channel_obj = self.bot.get_channel(channel_id)
                    if channel_obj:
                        channel_names.append(channel_obj.name)

            bonging_mode = "Words" if guild_data["bong_words"] else "Reactions"
            reaction_time = "On" if guild_data["bong_time"] else "Off"

            msg = f"[Bonging in]:                 {humanize_list(channel_names)}\n"
            msg += f"[Bong timeout]:               {guild_data['wait_for_bong_timeout']} seconds\n"
            msg += f"[Hunt interval minimum]:      {guild_data['hunt_interval_minimum']} seconds\n"
            msg += f"[Hunt interval maximum]:      {guild_data['hunt_interval_maximum']} seconds\n"
            msg += f"[Bonging mode]:               {bonging_mode}\n"
            msg += f"[Bong response time message]: {reaction_time}\n"
            msg += f"[Munchies shoot punishment]:     {guild_data['munchies']}\n"

            if await bank.is_global():
                reward = await self.config.reward_range()
                if reward:
                    reward = f"{reward[0]} - {reward[1]}"
                msg += f"[Bonging reward range]:       {reward if reward else 'None'}\n"
            else:
                reward = guild_data["reward_range"]
                if reward:
                    reward = f"{reward[0]} - {reward[1]}"
                msg += f"[Bonging reward range]:       {reward if reward else 'None'}\n"

            for page in pagify(msg, delims=["\n"]):
                await ctx.send(box(page, lang="ini"))

    @bonging.command()
    @commands.bot_has_permissions(embed_links=True)
    async def leaderboard(self, ctx, global_leaderboard=False):
        """
        This will show the top 50 hunters for the server.
        Use True for the global_leaderboard variable to show the global leaderboard.
        """
        userinfo = await self.config.all_users()
        if not userinfo:
            return await ctx.send(bold("Please shoot something before you can brag about it."))

        async with ctx.typing():
            sorted_acc: list = sorted(userinfo.items(), key=lambda x: (x[1]["total"]), reverse=True)[:50]

        if not hasattr(ctx.guild, "members"):
            global_leaderboard = True

        # pound_len = len(str(len(sorted_acc)))
        score_len = 10
        header = "{score:{score_len}}{name:2}\n".format(
            score="# Birds Shot",
            score_len=score_len + 5,
            name="Name" if str(ctx.author.mobile_status) not in ["online", "idle", "dnd"] else "Name",
        )
        temp_msg = header
        for account in sorted_acc:
            if account[1]["total"] == 0:
                continue
            if global_leaderboard or (account[0] in [member.id for member in ctx.guild.members]):
                user_obj = self.bot.get_user(account[0]) or account[0]
            else:
                continue
            if isinstance(user_obj, discord.User) and len(str(user_obj)) > 28:
                user_name = f"{user_obj.name[:19]}...#{user_obj.discriminator}"
            else:
                user_name = str(user_obj)
            if user_obj == ctx.author:
                temp_msg += f"{humanize_number(account[1]['total']) + '   ': <{score_len + 4}} <<{user_name}>>\n"
            else:
                temp_msg += f"{humanize_number(account[1]['total']) + '   ': <{score_len + 4}} {user_name}\n"

        page_list = []
        pages = 1
        for page in pagify(temp_msg, delims=["\n"], page_length=800):
            if global_leaderboard:
                title = "Global Bonging Leaderboard"
            else:
                title = f"Bonging Leaderboard For {ctx.guild.name}"
            embed = discord.Embed(
                colour=await ctx.bot.get_embed_color(location=ctx.channel),
                description=box(title, lang="prolog") + (box(page, lang="md")),
            )
            embed.set_footer(text=f"Page {humanize_number(pages)}/{humanize_number(math.ceil(len(temp_msg) / 800))}")
            pages += 1
            page_list.append(embed)
        if len(page_list) == 1:
            await ctx.send(embed=page_list[0])
        else:
            await menu(ctx, page_list, DEFAULT_CONTROLS)

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def bongtime(self, ctx):
        """Toggle displaying the bong response time from users."""
        toggle = await self.config.guild(ctx.guild).bong_time()
        await self.config.guild(ctx.guild).bong_time.set(not toggle)
        toggle_text = "will not" if toggle else "will"
        await ctx.send(f"Bong reaction time {toggle_text} be shown.\n")

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def munchies(self, ctx):
        """Toggle whether shooting an munchies is bad."""
        toggle = await self.config.guild(ctx.guild).munchies()
        await self.config.guild(ctx.guild).munchies.set(not toggle)
        toggle_text = "**Okay**" if toggle else "**Bad**"
        await ctx.send(f"Shooting an munchies is now {toggle_text}")

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def mode(self, ctx):
        """Toggle whether the bot listens for 'bong' or a reaction."""
        toggle = await self.config.guild(ctx.guild).bong_words()
        await self.config.guild(ctx.guild).bong_words.set(not toggle)
        toggle_text = "Use the reaction" if toggle else "Type 'bong'"
        await ctx.send(f"{toggle_text} to react to the bong message when it appears.\n")

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def reward(self, ctx, min_reward: int = None, max_reward: int = None):
        """
        Set a credit reward range for successfully shooting a bird

        Leave the options blank to disable bong rewards
        """
        bank_is_global = await bank.is_global()
        if ctx.author.id not in self.bot.owner_ids and bank_is_global:
            return await ctx.send("Bank is global, only bot owner can set a reward range.")
        if not min_reward or not max_reward:
            if min_reward != 0 and not max_reward:  # Maybe they want users to sometimes not get rewarded
                if bank_is_global:
                    await self.config.reward_range.set([])
                else:
                    await self.config.guild(ctx.guild).reward_range.set([])
                msg = "Reward range reset to default(None)."
                return await ctx.send(msg)
        if min_reward > max_reward:
            return await ctx.send("Your minimum reward is greater than your max reward...")
        reward_range = [min_reward, max_reward]
        currency_name = await bank.get_currency_name(ctx.guild)
        if bank_is_global:
            await self.config.reward_range.set(reward_range)
        else:
            await self.config.guild(ctx.guild).reward_range.set(reward_range)
        msg = f"Users can now get {min_reward} to {max_reward} {currency_name} for shooting a bird."
        await ctx.send(msg)

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def next(self, ctx):
        """When will the next occurrence happen?"""
        gid = ctx.guild.id
        if gid not in self.next_bong:
            self.next_bong[gid] = datetime.now().timestamp()
        last = self.next_bong.get(gid)
        try:
            total_seconds = int(abs(datetime.now().timestamp() - last))
            hours, remainder = divmod(total_seconds, 60 * 60)
            minutes, seconds = divmod(remainder, 60)
            message = f"The next occurrence will be in {hours} hours and {minutes} minutes."
        except KeyError:
            message = "There is currently no hunt."
        await ctx.send(bold(message))

    @bonging.command(name="score")
    async def score(self, ctx, member: discord.Member = None):
        """This will show the score of a hunter."""
        if not member:
            member = ctx.author
        score = await self.config.user(member).score()
        total = 0
        kill_list = []
        message = "Something went wrong?"
        if not score:
            message = "Please shoot something before you can brag about it."

        for animal in score.items():
            total = total + animal[1]
            if animal[1] == 1 or animal[0][-1] == "s":
                kill_list.append(f"{animal[1]} {animal[0].capitalize()}")
            else:
                kill_list.append(f"{animal[1]} {animal[0].capitalize()}s")
            message = f"{member.name} shot a total of {total} animals ({humanize_list(kill_list)})"
        await ctx.send(bold(message))

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def start(self, ctx, channel: discord.TextChannel = commands.CurrentChannel):
        """Start the hunt."""

        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send(bold("I can't send messages in that channel!"))

        channel_list = await self.config.guild(ctx.guild).channels()
        if channel.id in channel_list:
            message = f"We're already bonging in {channel.mention}!"
        else:
            channel_list.append(channel.id)
            message = f"May the bonging begin in {channel.mention}. Good luck!"
            await self.config.guild(ctx.guild).channels.set(channel_list)

        await ctx.send(bold(message))

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def stop(self, ctx, channel: discord.TextChannel = commands.CurrentChannel):
        """Stop the hunt."""
        channel_list = await self.config.guild(ctx.guild).channels()

        if channel.id not in channel_list:
            message = f"We're not bonging in {channel.mention}!"
        else:
            channel_list.remove(channel.id)
            message = f"The bonging has stopped in {channel.mention}."
            await self.config.guild(ctx.guild).channels.set(channel_list)

        await ctx.send(bold(message))

    @checks.is_owner()
    @bonging.command()
    async def clearleaderboard(self, ctx):
        """
        Clear all the scores from the leaderboard.
        """
        warning_string = (
            "Are you sure you want to clear all the scores from the leaderboard?\n"
            "This is a global wipe and **cannot** be undone!\n"
            'Type "Yes" to confirm, or "No" to cancel.'
        )

        await ctx.send(warning_string)
        pred = MessagePredicate.yes_or_no(ctx)
        try:
            await self.bot.wait_for("message", check=pred, timeout=15)
            if pred.result is True:
                await self.config.clear_all_users()
                return await ctx.send("Done!")
            else:
                return await ctx.send("Alright, not clearing the leaderboard.")
        except asyncio.TimeoutError:
            return await ctx.send("Response timed out.")

    @checks.mod_or_permissions(manage_guild=True)
    @bonging.command()
    async def timing(
        self,
        ctx,
        interval_min: commands.positive_int,
        interval_max: commands.positive_int,
        bong_timeout: commands.positive_int,
    ):
        """
        Change the bonging timing.

        `interval_min` = Minimum time in seconds for a new bird. (60 min)
        `interval_max` = Maximum time in seconds for a new bird. (120 min)
        `bong_timeout` = Time in seconds for users to shoot a bird before it flies away. (10s min)
        """
        message = ""
        if interval_min > interval_max:
            return await ctx.send("`interval_min` needs to be lower than `interval_max`.")
        if interval_min < 60:
            interval_min = 60
            message += "Minimum interval set to minimum of 120s.\n"
        if interval_max < 120:
            interval_max = 120
            message += "Maximum interval set to minimum of 240s.\n"
        if bong_timeout < 10:
            bong_timeout = 10
            message += "Bong timeout set to minimum of 10s.\n"

        await self.config.guild(ctx.guild).hunt_interval_minimum.set(interval_min)
        await self.config.guild(ctx.guild).hunt_interval_maximum.set(interval_max)
        await self.config.guild(ctx.guild).wait_for_bong_timeout.set(bong_timeout)
        message += (
            f"Timing has been set:\nMin time {interval_min}s\nMax time {interval_max}s\nBong timeout {bong_timeout}s"
        )
        await ctx.send(bold(message))

    @bonging.command()
    async def version(self, ctx):
        """Show the cog version."""
        await ctx.send(f"Bonging version {__version__}.")

    async def add_score(self, author: discord.User, avian: str):
        user_data = await self.config.user(author).all()
        try:
            user_data["score"][avian] += 1
        except KeyError:
            user_data["score"][avian] = 1
        user_data["total"] += 1
        await self.config.user(author).set_raw(value=user_data)

    async def do_tha_bong(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        conf: dict,
        wait: int,
    ):
        try:
            await asyncio.sleep(wait)
            await self._wait_for_bong(guild, channel, conf)
        except Exception as e:
            log.error(f"Failed to wait for bong: {e}")
        finally:
            self.in_game.discard(channel.id)

    async def _wait_for_bong(self, guild: discord.Guild, channel: discord.TextChannel, conf: dict):
        def mcheck(m: discord.Message):
            if m.guild != guild:
                return False
            if m.channel != channel:
                return False
            if not m.content:
                return False
            res = m.content.lower().strip()
            return "bong" in res

        def rcheck(r: discord.Reaction, u: discord.Member):
            if u.bot:
                return False
            if r.message.guild != guild:
                return False
            if r.message.channel != channel:
                return False
            if not u:
                return False
            return str(r.emoji) == "💥"

        animal = random.choice(list(self.animals.keys()))

        animal_message = await channel.send(self.animals[animal])
        now = datetime.now().timestamp()
        timeout = conf["wait_for_bong_timeout"]

        if conf["bong_words"]:
            try:
                bong_msg = await self.bot.wait_for("message", check=mcheck, timeout=timeout)
            except asyncio.TimeoutError:
                return await channel.send(f"The {animal} got away!")
            author = bong_msg.author
        else:
            emoji = "\N{COLLISION SYMBOL}"
            await animal_message.add_reaction(emoji)
            try:
                reaction, author = await self.bot.wait_for("reaction_add", check=rcheck, timeout=timeout)
            except asyncio.TimeoutError:
                return await channel.send(f"The {animal} got away!")

        bong_now = datetime.now().timestamp()
        time_for_bong = round(bong_now - now, 1)
        bongtime = "" if not await self.config.guild(guild).bong_time() else f" in {time_for_bong}s"

        if random.randrange(0, 17) > 1:
            if conf["munchies"] and animal == "munchies":
                punish = await self.maybe_send_reward(guild, author, True)
                if punish:
                    cur_name = await bank.get_currency_name(guild)
                    msg = f"RUDE! {author.display_name} shot a munchies{bongtime} and paid {punish} {cur_name} in fines!"
                else:
                    msg = f"Oh no! {author.display_name} shot a munchies{bongtime}!"
            else:
                await self.add_score(author, animal)
                reward = await self.maybe_send_reward(guild, author)
                if reward:
                    cur_name = await bank.get_currency_name(guild)
                    msg = f"{author.display_name} shot a {animal}{bongtime} and earned {reward} {cur_name}!"
                else:
                    msg = f"{author.display_name} shot a {animal}{bongtime}!"
        else:
            msg = f"{author.display_name} missed the shot and the {animal} got away!"

        await channel.send(bold(msg))

    async def maybe_send_reward(self, guild, author, take: bool = False) -> int:
        if await bank.is_global():
            amounts = await self.config.reward_range()
        else:
            amounts = await self.config.guild(guild).reward_range()

        if amounts:
            to_give_take = random.randint(amounts[0], amounts[1] + 1)
        else:
            to_give_take = 0
        user_bal = await bank.get_balance(author)
        if take:
            if to_give_take > user_bal:
                to_give_take = user_bal
            await bank.withdraw_credits(author, to_give_take)
        else:
            max_bal = await bank.get_max_balance(guild)
            if to_give_take + user_bal > max_bal:
                to_give_take = max_bal - user_bal
            try:
                await bank.deposit_credits(author, to_give_take)
            except BalanceTooHigh as e:  # This shouldn't throw since we already compare to max bal
                await bank.set_balance(author, e.max_balance)
        return to_give_take

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild:
            return
        if message.author.bot:
            return
        if not message.channel.permissions_for(message.guild.me).send_messages:
            return
        if message.channel.id in self.in_game:
            return

        guild_data = await self.config.guild(message.guild).all()
        if not guild_data["channels"]:
            return
        if message.channel.id not in guild_data["channels"]:
            return

        wait_time = random.randint(
            guild_data["hunt_interval_minimum"],
            guild_data["hunt_interval_maximum"],
        )
        if message.guild.id not in self.next_bong:
            self.next_bong[message.guild.id] = datetime.now().timestamp() + wait_time
            return

        n = self.next_bong[message.guild.id]
        if datetime.now().timestamp() < n:
            return

        self.in_game.add(message.channel.id)
        self.next_bong[message.guild.id] = datetime.now().timestamp() + wait_time
        asyncio.create_task(self.do_tha_bong(message.guild, message.channel, guild_data, wait_time))
