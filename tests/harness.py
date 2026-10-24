"""Exercise ZSession against a real game without Discord.
Usage: python -m tests.harness [games_dir]   (interactive: add -i)"""
import asyncio, sys, tempfile
from pathlib import Path
from bot.hints import HintDB, BUNDLED, norm
from bot.zsession import detect_room, ZSession, list_games, split_for_discord


async def scripted(games_dir: str) -> int:
    games = list_games(games_dir)
    print("games:", list(games))
    assert "zork1" in games, "run scripts/fetch_games.sh first"
    root = Path(tempfile.mkdtemp())          # stands in for SAVES_DIR
    alice, bob = 111, 222
    mk = lambda uid, g: ZSession(games[g], root / str(uid))

    # Alice: take leaflet, save. Bob: go north, save. Same game, separate slots.
    a = mk(alice, "zork1"); await a.start()
    await a.send("open mailbox"); await a.send("take leaflet")
    print("ALICE SAVE:", await a.save())
    b = mk(bob, "zork1"); await b.start()
    assert "North of House" in await b.send("north")
    print("BOB SAVE:", await b.save())
    assert (root / "111" / "zork1.qzl").exists() and (root / "222" / "zork1.qzl").exists()
    await a.close(); await b.close()

    # New sessions (as if /play in a different channel/server) -> restore per user.
    a2 = mk(alice, "zork1"); await a2.start(); print("ALICE RESTORE:", await a2.restore())
    inv = await a2.send("inventory"); print(inv); assert "leaflet" in inv
    assert "West of House" in await a2.send("look")
    b2 = mk(bob, "zork1"); await b2.start(); await b2.restore()
    lb = await b2.send("look"); print(lb); assert "North of House" in lb
    assert "leaflet" not in await b2.send("inventory")

    # Per-game slots: Alice's zork2 has no save; zork1 slot untouched.
    z2 = mk(alice, "zork2"); await z2.start()
    assert "No saved game" in await z2.restore(); await z2.close()

    out = await a2.restart(); assert "West of House" in out
    await a2.close(); await b2.close(); assert not a2.alive
    print("save files:", sorted(str(p.relative_to(root)) for p in root.rglob("*.qzl")))

    parts = split_for_discord("x" * 5000 + "\n" + "line\n" * 800)
    assert all(len(p) <= 2000 for p in parts) and len(parts) >= 3
    if "advent" in games:
        v = mk(alice, "advent"); await v.start()
        assert "building" in (await v.send("enter building")).lower(); await v.close()
    await hint_tests(games, root)
    # process-exit detection: quitting inside the game ends the session
    q = mk(alice, "zork1"); await q.start()
    o1 = await q.send("quit"); print("QUIT:", o1)
    o2 = await q.send("y"); print("CONFIRM:", o2)
    assert not q.alive and "[game ended]" in o2, (q.alive, o2)
    assert await q.send("look") == "[game is not running]"
    # death also ends it eventually? (only checked if game exits) - covered by quit path
    await delete_logic_tests()
    print("\nALL TESTS PASSED"); return 0


async def hint_tests(games, root) -> None:
    db = HintDB(None, BUNDLED)
    s = ZSession(games["zork1"], root / "hint")
    await s.start(); assert s.room == "West of House", s.room
    walk = [("north", "North of House"), ("east", "Behind House"), ("open window", "Behind House"),
            ("west", "Kitchen"), ("west", "Living Room"), ("take lamp", "Living Room"),
            ("move rug", "Living Room"), ("open trap door", "Living Room"), ("turn on lamp", "Living Room"),
            ("down", "Cellar"), ("north", "Troll Room")]
    for cmd, want in walk:
        await s.send(cmd)
        assert norm(s.room) == norm(want), (cmd, s.room, want)
        head, levels, specific = db.lookup("zork1", s.room)
        assert specific and len(levels) >= 1, (s.room, head)
        print(f"  {cmd:15s} -> room={s.room!r:18} hints={len(levels)}  first: {levels[0][:60]}")
    await s.close()
    # silent-look fallback when room unknown
    s = ZSession(games["zork1"], root / "hint"); await s.start(); s.room = None
    assert await s.current_room() == "West of House"; await s.close()
    # alias, boat suffix, unknown room -> general
    assert db.lookup("zork1", "Reservoir North")[2]
    assert db.lookup("zork1", "Frigid River, in the magic boat")[2]
    h, lv, sp = db.lookup("zork1", "Nowhere Special"); assert not sp and lv and "general" in h
    assert not db.lookup("nosuchgame", "x")[2]
    for g in sorted(f.stem for f in BUNDLED.glob("*.yaml")):
        d = db._load(g); assert d["general"], g
        for k, v in d["aliases"].items(): assert v in d["rooms"], (g, k, v)
        print(f"  {g}: {len(d['rooms'])} rooms, {len(d['general'])} general hints")
    if "advent" in games:
        a = ZSession(games["advent"], root / "hint"); await a.start(); await a.send("enter building")
        assert a.room == "Inside Building", a.room
        assert db.lookup("advent", a.room)[2]; await a.close()
    assert detect_room(" Kitchen                       Score: 10       Moves: 5\n\nKitchen") == "Kitchen"


async def delete_logic_tests() -> None:
    """Exercise thread-deletion scheduling with fake Discord objects."""
    import os
    os.environ.setdefault("GAMES_DIR", "games")
    import discord
    import bot.main as m

    class FakeThread(discord.Thread):
        def __init__(self, tid, owner, forbid=False):
            self.id, self.owner_id, self.forbid = tid, owner, forbid
            self.sent, self.deleted, self.edits = [], False, []
        async def send(self, t): self.sent.append(t)
        async def delete(self):
            if self.forbid:
                raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "no perms")
            self.deleted = True
        async def edit(self, **kw): self.edits.append(kw)

    me = 999
    threads = {}
    m.client._connection.user = type("U", (), {"id": me})()
    m.client.get_channel = lambda cid: threads.get(cid)
    m.sessions.clear()

    def mkcfg(delay):
        object.__setattr__(m.cfg, "thread_delete_delay", delay)

    # 0 = immediate delete of a bot-created thread
    mkcfg(0); threads[1] = FakeThread(1, me); m.bot_threads.add(1)
    await m.schedule_thread_delete(1); await asyncio.sleep(0.05)
    assert threads[1].deleted and "now" in threads[1].sent[0] and 1 not in m.pending_deletes
    # thread not created by bot -> untouched
    threads[2] = FakeThread(2, 12345)
    await m.schedule_thread_delete(2); assert not threads[2].sent and 2 not in m.pending_deletes
    # -1 = keep
    mkcfg(-1); threads[3] = FakeThread(3, me); m.bot_threads.add(3)
    await m.schedule_thread_delete(3); assert not threads[3].sent
    # delayed delete then cancelled (owner restarted a game there)
    mkcfg(5); threads[4] = FakeThread(4, me); m.bot_threads.add(4)
    await m.schedule_thread_delete(4)
    assert 4 in m.pending_deletes and "5 minutes" in threads[4].sent[0]
    m.cancel_delete(4); await asyncio.sleep(0.05)
    assert 4 not in m.pending_deletes and not threads[4].deleted
    # missing Manage Threads -> archive + lock
    mkcfg(0); threads[5] = FakeThread(5, me, forbid=True); m.bot_threads.add(5)
    await m.schedule_thread_delete(5); await asyncio.sleep(0.05)
    assert not threads[5].deleted and threads[5].edits == [{"archived": True, "locked": True}]
    print("  thread-deletion logic: immediate, foreign-thread, keep(-1), cancel, no-permission fallback OK")


async def interactive(games_dir: str, name: str):
    s = ZSession(list_games(games_dir)[name], Path(tempfile.mkdtemp()))
    print(await s.start())
    while s.alive:
        line = await asyncio.to_thread(input, "> ")
        print(await s.send(line))


if __name__ == "__main__":
    a = sys.argv[1:]
    if "-i" in a:
        a.remove("-i"); asyncio.run(interactive(a[0] if a else "games", a[1] if len(a) > 1 else "zork1"))
    else:
        sys.exit(asyncio.run(scripted(a[0] if a else "games")))
