# Discord Text Adventure Bot

Play Z-machine (Infocom-style) games in Discord. Each game runs in its own `dfrotz`
subprocess, one session per channel/thread. Python 3.12 + discord.py 2.x.

## Commands
Games are **per user**: each user has at most one active game, running in its own thread.
Only the owner's (prefixed) messages in that thread drive it; everyone else's are ignored.

| Command | What it does |
|---|---|
| `/play <game> [resume]` | Starts your game in a new thread (closes any game you already had). If you have a save for that title it is restored automatically; pass `resume:False` to start fresh |
| `/games` | Lists games in `GAMES_DIR`, marking ones you have a save for (only you see it) |
| `/save` | Saves your current game to `SAVES_DIR/<user id>/<game>.qzl` (one slot per game, overwritten each time) |
| `/restore` | Loads your save for the game you're playing |
| `/hint` | Hint for the room you are in, visible only to you. **More hint** reveals stronger hints, ending with the spoilered solution. Falls back to general game hints |
| `/restart` / `/quit` | Restart / end **your** game. These work from any channel |
| `>look` | Game input from the owner, in the game's thread. The prefix is `COMMAND_PREFIX` (default `>`); set it empty to use plain messages |

Saves are tied to your Discord user ID, not the channel. You can save in one server, then `/play` the
same game in another channel or server and carry on. Idle games are autosaved and closed after `SESSION_IDLE_MINUTES`.

**Thread cleanup:** a thread the bot created is deleted when its game ends. That covers `/quit`, the idle
timeout (after the autosave), the game finishing on its own (death, win, or `quit` typed in the game), and
replacing the game with a new `/play`. The bot first posts "This thread will be deleted in N minutes" and deletes
it after `THREAD_DELETE_DELAY_MINUTES` (default 5; `0` = immediately; `-1` = keep threads). Running `/play`
in that thread before the timer runs out cancels the deletion. Threads not created by the bot are never touched.
Without the **Manage Threads** permission the bot logs a warning and archives and locks the thread instead.
Pending deletions are held in memory, so a container restart forgets them; delete any leftover threads by hand.

### Hints
Hint files are `hints/<game>.yaml`, where `<game>` is the game file's name without the extension (e.g. `zork1`).
The bundled files cover Zork I in depth, Zork II, Zork III and Adventure more lightly, all with
original text. The current room comes from the game's status line in the latest output; if that's
missing, the bot sends a silent `look`. Room names are matched case-insensitively, and a leading "The"
and any ", in the boat"-style suffix are ignored. To add or override hints, set `HINTS_DIR`
(e.g. mount `/mnt/<pool>/text-adventure/hints` to `/data/hints`). Files there take priority over the
bundled ones.
```yaml
game: Zork I
aliases: {dam lobby: maintenance room}   # extra room names that share another room's hints
general: [ "nudge used when the room has no entry" ]
rooms:
  troll room:
    - gentle nudge
    - stronger hint
    - full solution          # the last level is shown inside ||spoilers||
```

## 1. Create the Discord bot
1. https://discord.com/developers/applications → **New Application**.
2. **Bot** tab → **Reset Token** → copy it into `DISCORD_TOKEN`.
3. Same tab → **Privileged Gateway Intents** → enable **Message Content Intent** (required to read game input).
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; permissions:
   View Channels, Send Messages, Send Messages in Threads, Create Public Threads, Manage Threads, Read Message History.
   Or use directly (replace CLIENT_ID):
   `https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot+applications.commands&permissions=326417583104`
5. Optional: enable Developer Mode in Discord, right-click your server → Copy Server ID → `GUILD_ID`
   (global commands can take up to an hour to appear; guild commands are instant).

## 2. Get games
```sh
./scripts/fetch_games.sh /mnt/<pool>/text-adventure/games
```
Downloads Zork I–III (MIT-licensed by Microsoft, github.com/historicalsource) and Adventure
(`advent.z5`, freeware, IF Archive). Any other `.z5/.z8/.zblorb` you're allowed to use can be dropped in;
the filename (without extension) is the game name. Nothing copyrighted is bundled in the image.

## 3. Publish the image (GitHub Actions → GHCR)
1. Create an empty GitHub repo `Usedillusion/text-adventure` (no README/licence, so the first push is clean).
2. Push this project (commands below). `.github/workflows/docker.yml` builds `linux/amd64` and pushes
   `ghcr.io/usedillusion/text-adventure` tagged `latest` (main), `X.Y.Z`/`X.Y`/`X` (tags `vX.Y.Z`) and `sha-…`.
   Check the **Actions** tab.
3. Make the image pullable:
   - **Public (simplest):** GitHub profile → **Packages** → `text-adventure` → **Package settings** →
     *Danger Zone* → **Change visibility** → Public.
   - **Or keep it private:** create a classic PAT with `read:packages`, then in TrueNAS go to
     **Apps → Configuration → Manage Container Image Registries → Add** (URI `ghcr.io`, user
     `Usedillusion`, password = PAT). On older versions without that screen, run in the TrueNAS shell:
     `sudo docker login ghcr.io -u Usedillusion` with the PAT as the password.

```sh
cd discord-text-adventure
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/Usedillusion/text-adventure.git
git push -u origin main
# release: git tag v1.0.0 && git push origin v1.0.0
```

## 4. Deploy on TrueNAS SCALE (24.10+ / Docker-based apps)
1. Create `/mnt/<pool>/text-adventure/{games,saves}` and give them to the apps user:
   `chown -R 568:568 /mnt/<pool>/text-adventure`
2. Fetch games into `.../games` (step 2) from the TrueNAS shell.
3. Apps → Discover Apps → ⋮ → **Install via YAML**, paste `docker-compose.yaml`, replace `<pool>` and
   the token, save. The logs should show `Logged in as ...`.

**Updating:** push to `main` (or a `v*` tag) and wait for the Action to finish, then in TrueNAS open the app
and **Update** (or Stop then Start). `pull_policy: always` fetches the new `latest` image. For automatic
updates, see the commented Watchtower note in the compose file. To pin a version, use `:1.0.0` instead of `:latest`.

A UID/GID other than 568 needs a rebuild with `--build-arg UID=… --build-arg GID=…` (or edit the Dockerfile defaults),
and a matching change to `user:`.

## Local dev / testing (no Discord needed)
```sh
sudo apt install frotz        # provides dfrotz
pip install -r requirements.txt
./scripts/fetch_games.sh games
python -m tests.harness games          # scripted test: start, commands, two users saving the same game independently, cross-session restore, per-game slots, restart, splitting
python -m tests.harness games -i zork1 # play in the terminal through the same wrapper
DISCORD_TOKEN=... GAMES_DIR=games SAVES_DIR=saves python -m bot.main
```

## Notes
- Output is read until the game is idle for `READ_IDLE_SECONDS` (cap `READ_MAX_SECONDS`); long
  outputs are split into ≤2000-char code blocks.
- `dfrotz -R <savedir>` restricts game file access to the channel's save directory.
- Sessions live in memory; a container restart ends running games (saves persist).
