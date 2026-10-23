"""Exercise ZSession against a real game without Discord.
Usage: python -m tests.harness [games_dir]   (interactive: add -i)"""
import asyncio, sys, tempfile
from pathlib import Path
from bot.zsession import ZSession, list_games, split_for_discord


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
    print("\nALL TESTS PASSED"); return 0


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
