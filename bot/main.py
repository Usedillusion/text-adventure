from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from .config import Config
from .hints import default_db
from .zsession import ZSession, list_games, split_for_discord

log = logging.getLogger("textadv")
cfg = Config.from_env()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
hint_db = default_db()
sessions: dict[int, ZSession] = {}  # keyed by owner user id


async def post(ch: discord.abc.Messageable, text: str) -> None:
    for part in split_for_discord(text):
        await ch.send(part)


async def reply(inter: discord.Interaction, text: str) -> None:
    parts = split_for_discord(text)
    await inter.followup.send(parts[0])
    for p in parts[1:]:
        await inter.channel.send(p)


async def game_autocomplete(_: discord.Interaction, current: str):
    return [app_commands.Choice(name=n, value=n)
            for n in list_games(cfg.games_dir) if current.lower() in n][:25]


@tree.command(name="play", description="Start your own text adventure (in a new thread)")
@app_commands.describe(game="Game to play", resume="Restore your saved game for this title (default: yes if a save exists)")
@app_commands.autocomplete(game=game_autocomplete)
async def play(inter: discord.Interaction, game: str, resume: bool | None = None):
    games = list_games(cfg.games_dir)
    path = games.get(game.lower())
    if not path:
        await inter.response.send_message(
            f"Unknown game `{game}`. Try `/games`.", ephemeral=True); return
    uid = inter.user.id
    old = sessions.pop(uid, None)
    if old:
        await old.close()
    s = ZSession(path, Path(cfg.saves_dir) / str(uid), cfg.dfrotz_path,
                 cfg.read_idle, cfg.read_max)
    s.owner_id = uid
    target = inter.channel
    note = " (your previous game was closed)" if old else ""
    if cfg.use_threads and isinstance(inter.channel, discord.TextChannel):
        await inter.response.send_message(f"{inter.user.mention} is starting **{path.stem}**{note}…")
        msg = await inter.original_response()
        target = await msg.create_thread(name=f"{path.stem} – {inter.user.display_name}"[:90],
                                         auto_archive_duration=1440)
    else:
        await inter.response.defer()
    s.channel_id = target.id
    try:
        out = await s.start()
    except Exception as e:  # noqa: BLE001
        log.exception("start failed")
        await target.send(f"Failed to start game: {e}"); return
    sessions[uid] = s
    p = cfg.command_prefix
    hint = (f"{inter.user.mention}, this is your game. Only your messages "
            + (f"starting with `{p}` (e.g. `{p}look`)" if p else "") + " drive it.")
    if target is inter.channel:
        await inter.followup.send(hint)
    else:
        await target.send(hint)
    if s.has_save() and resume is not False:
        out = "[Restoring your saved game — use /restart to start fresh]\n" + await s.restore()
    elif s.has_save():
        out += "\n\n[You have a saved game for this title — use /restore to load it]"
    await post(target, out)


@tree.command(name="games", description="List available games")
async def games_cmd(inter: discord.Interaction):
    g = list_games(cfg.games_dir)
    d = Path(cfg.saves_dir) / str(inter.user.id)
    txt = "\n".join(f"• `{n}` ({p.suffix})" + (" 💾 saved" if (d / f"{n}.qzl").exists() else "")
                    for n, p in g.items()) or "No games found in GAMES_DIR."
    await inter.response.send_message(txt[:1990], ephemeral=True)


def _simple(name: str, desc: str, method: str):
    @tree.command(name=name, description=desc)
    async def _cmd(inter: discord.Interaction):
        s = sessions.get(inter.user.id)
        if not s:
            await inter.response.send_message("You have no game running. Start one with /play.",
                                              ephemeral=True); return
        await inter.response.defer()
        out = await getattr(s, method)()
        if inter.channel_id != s.channel_id:
            out = f"[{s.game_name}, in <#{s.channel_id}>]\n" + out
        await reply(inter, out)
    return _cmd


_simple("save", "Save your game (one slot per game, follows you across servers)", "save")
_simple("restore", "Restore your saved game for the title you're playing", "restore")
_simple("restart", "Restart your current game", "restart")


def _fmt_hint(heading: str, levels: list[str], i: int) -> str:
    body = levels[i]
    last = i == len(levels) - 1
    if last and "||" not in body and len(levels) > 1:
        body = f"||{body}||"
    tag = "Solution" if last and len(levels) > 1 else f"Hint {i + 1}/{len(levels)}"
    return f"**{heading}**\n{tag}: {body}"[:1990]


class HintView(discord.ui.View):
    def __init__(self, owner: int, heading: str, levels: list[str]):
        super().__init__(timeout=600)
        self.owner, self.heading, self.levels, self.i = owner, heading, levels, 0
        self.more.disabled = len(levels) <= 1

    @discord.ui.button(label="More hint", style=discord.ButtonStyle.primary)
    async def more(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.owner:
            await inter.response.send_message("Use /hint for your own game.", ephemeral=True); return
        self.i = min(self.i + 1, len(self.levels) - 1)
        if self.i == len(self.levels) - 1:
            button.disabled = True
            button.label = "That's everything"
        await inter.response.edit_message(content=_fmt_hint(self.heading, self.levels, self.i), view=self)


@tree.command(name="hint", description="Get a progressive hint for the room you're in (only you see it)")
async def hint_cmd(inter: discord.Interaction):
    s = sessions.get(inter.user.id)
    if not s:
        await inter.response.send_message("You have no game running. Start one with /play.", ephemeral=True); return
    await inter.response.defer(ephemeral=True, thinking=True)
    room = await s.current_room()
    heading, levels, _ = hint_db.lookup(s.game_name, room)
    await inter.followup.send(_fmt_hint(heading, levels, 0),
                              view=HintView(inter.user.id, heading, levels), ephemeral=True)


@tree.command(name="quit", description="End your game")
async def quit_cmd(inter: discord.Interaction):
    s = sessions.pop(inter.user.id, None)
    if not s:
        await inter.response.send_message("You have no game running.", ephemeral=True); return
    await s.close()
    await inter.response.send_message(f"Ended your **{s.game_name}** game. (Use /save before /quit to keep progress.)")


@client.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return
    s = sessions.get(msg.author.id)
    if not s or s.channel_id != msg.channel.id:
        return  # not this user's game channel -> ignore
    content = msg.content.strip()
    p = cfg.command_prefix
    if p:
        if not content.startswith(p):
            return
        content = content[len(p):].strip()
    if not content:
        return
    async with msg.channel.typing():
        out = await s.send(content)
    await post(msg.channel, out)
    if not s.alive:
        sessions.pop(msg.author.id, None)


@tasks.loop(minutes=1)
async def reaper():
    limit = cfg.idle_timeout_min * 60
    for cid, s in list(sessions.items()):
        if not s.alive or time.monotonic() - s.last_active > limit:
            sessions.pop(cid, None)
            try:
                if s.alive:
                    await s.save()  # autosave before cleanup
            except Exception:  # noqa: BLE001
                pass
            await s.close()
            ch = client.get_channel(s.channel_id)
            if ch:
                try:
                    await ch.send(f"<@{cid}> your {s.game_name} session closed due to inactivity (autosaved; /play {s.game_name} resumes it).")
                except discord.HTTPException:
                    pass


@client.event
async def on_ready():
    if cfg.guild_id:
        g = discord.Object(id=cfg.guild_id)
        tree.copy_global_to(guild=g)
        await tree.sync(guild=g)
    else:
        await tree.sync()
    if not reaper.is_running():
        reaper.start()
    log.info("Logged in as %s; games: %s", client.user, ", ".join(list_games(cfg.games_dir)))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not cfg.token:
        raise SystemExit("DISCORD_TOKEN is not set")
    client.run(cfg.token, log_handler=None)


if __name__ == "__main__":
    main()
