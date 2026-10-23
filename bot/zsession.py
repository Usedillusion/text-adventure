"""dfrotz subprocess wrapper (no Discord dependency)."""
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

GAME_EXTS = (".z1", ".z2", ".z3", ".z4", ".z5", ".z6", ".z7", ".z8", ".zblorb", ".zlb")
_FILENAME_PROMPT = re.compile(r"(file ?name|filename).*[:>?]\s*$", re.I | re.S)


def list_games(games_dir: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    p = Path(games_dir)
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in GAME_EXTS:
                out.setdefault(f.stem.lower(), f)
    return out


class ZSession:
    def __init__(self, game: Path, save_dir: Path, dfrotz: str = "dfrotz",
                 read_idle: float = 0.4, read_max: float = 8.0, width: int = 80):
        self.game = Path(game)
        self.save_dir = Path(save_dir)
        self.game_name = self.game.stem.lower()
        self.save_name = f"{self.game_name}.qzl"
        self.owner_id: int | None = None
        self.channel_id: int | None = None
        self.dfrotz = dfrotz
        self.read_idle = read_idle
        self.read_max = read_max
        self.width = width
        self.proc: asyncio.subprocess.Process | None = None
        self.last_active = time.monotonic()
        self.lock = asyncio.Lock()

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> str:
        self.save_dir.mkdir(parents=True, exist_ok=True)
        # -m no MORE prompts, -p plain ASCII, -q quiet, -w width,
        # -R restrict file I/O to the save dir (cwd).
        args = [self.dfrotz, "-m", "-p", "-q", "-w", str(self.width),
                "-R", str(self.save_dir), str(self.game.resolve())]
        self.proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, cwd=str(self.save_dir))
        return await self._read()

    async def _read(self) -> str:
        assert self.proc and self.proc.stdout
        buf = bytearray()
        deadline = time.monotonic() + self.read_max
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                chunk = await asyncio.wait_for(self.proc.stdout.read(4096),
                                               timeout=min(self.read_idle, remaining))
            except asyncio.TimeoutError:
                if buf:
                    break  # idle after output -> assume prompt
                continue
            if not chunk:  # EOF -> process exited
                break
            buf += chunk
        self.last_active = time.monotonic()
        return clean(buf.decode("utf-8", "replace"))

    async def send(self, line: str) -> str:
        async with self.lock:
            if not self.alive:
                return "[game is not running]"
            assert self.proc and self.proc.stdin
            line = line.replace("\r", " ").replace("\n", " ")[:200]
            self.proc.stdin.write((line + "\n").encode())
            await self.proc.stdin.drain()
            out = await self._read()
            if not self.alive:
                out += "\n[game ended]"
            return out

    async def _file_cmd(self, cmd: str) -> str:
        out = await self.send(cmd)
        if _FILENAME_PROMPT.search(out[-200:]):
            out2 = await self.send(self.save_name)
            # restore/save may ask to overwrite
            if re.search(r"overwrite|\(y/n\)|yes or no", out2[-120:], re.I):
                out2 = await self.send("y")
            return out2
        return out

    @property
    def save_path(self) -> Path:
        return self.save_dir / self.save_name

    def has_save(self) -> bool:
        return self.save_path.exists()

    async def save(self) -> str:
        return await self._file_cmd("save")

    async def restore(self) -> str:
        if not self.has_save():
            return f"No saved game for {self.game_name} yet."
        return await self._file_cmd("restore")

    async def restart(self) -> str:
        out = await self.send("restart")
        if re.search(r"\?|y/n|yes", out[-120:], re.I):
            out = await self.send("y")
        return out

    async def close(self) -> None:
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass
            await self.proc.wait()


def clean(text: str) -> str:
    text = text.replace("\r", "")
    lines = [l.rstrip() for l in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines).strip("\n")


def split_for_discord(text: str, limit: int = 2000) -> list[str]:
    """Wrap text in ``` blocks, each message <= limit chars."""
    text = (text or "(no output)").replace("```", "'''")
    inner = limit - 8  # ```\n ... \n```
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > inner:
            if cur:
                chunks.append(cur); cur = ""
            chunks.append(line[:inner]); line = line[inner:]
        if len(cur) + len(line) + 1 > inner:
            chunks.append(cur); cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur or not chunks:
        chunks.append(cur)
    return [f"```\n{c}\n```" for c in chunks]
