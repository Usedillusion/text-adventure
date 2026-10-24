"""Progressive hint lookup from hints/<game>.yaml files."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

BUNDLED = Path(__file__).resolve().parent.parent / "hints"


def norm(room: str | None) -> str:
    if not room:
        return ""
    r = room.split(",")[0]  # "Frigid River, in the magic boat" -> "Frigid River"
    r = " ".join(r.lower().split())
    return r[4:] if r.startswith("the ") else r  # "The Troll Room" == "Troll Room"


class HintDB:
    def __init__(self, *dirs: str | Path | None):
        self.dirs = [Path(d) for d in dirs if d]
        self._cache: dict[str, dict] = {}

    def _load(self, game: str) -> dict:
        game = game.lower()
        if game in self._cache:
            return self._cache[game]
        data: dict = {}
        for d in self.dirs:  # first dir wins (HINTS_DIR overrides bundled)
            for ext in (".yaml", ".yml"):
                f = d / f"{game}{ext}"
                if f.is_file():
                    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                    break
            if data:
                break
        rooms = {norm(k): [str(h) for h in (v or [])] for k, v in (data.get("rooms") or {}).items()}
        data = {"title": data.get("game", game), "rooms": rooms,
                "aliases": {norm(k): norm(v) for k, v in (data.get("aliases") or {}).items()},
                "general": [str(h) for h in data.get("general") or []]}
        self._cache[game] = data
        return data

    def lookup(self, game: str, room: str | None) -> tuple[str, list[str], bool]:
        """Return (heading, levels, is_room_specific)."""
        d = self._load(game)
        key = norm(room)
        key = d["aliases"].get(key, key)
        if key and key in d["rooms"] and d["rooms"][key]:
            return f"{d['title']} — {room}", d["rooms"][key], True
        gen = d["general"] or ["No hints available for this game yet. Try EXAMINE, READ, and every exit."]
        where = f" (no specific hints for {room})" if room else ""
        return f"{d['title']} — general hints{where}", gen, False


def default_db() -> HintDB:
    return HintDB(os.getenv("HINTS_DIR") or None, BUNDLED)
