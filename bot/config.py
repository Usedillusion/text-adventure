import os
from dataclasses import dataclass


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    token: str
    games_dir: str
    saves_dir: str
    command_prefix: str          # "" = every plain message is a game command
    guild_id: int | None
    dfrotz_path: str
    idle_timeout_min: int
    use_threads: bool
    read_idle: float
    read_max: float
    thread_delete_delay: int     # minutes; 0 = now, -1 = keep

    @classmethod
    def from_env(cls) -> "Config":
        gid = os.getenv("GUILD_ID", "").strip()
        return cls(
            token=os.getenv("DISCORD_TOKEN", ""),
            games_dir=os.getenv("GAMES_DIR", "/data/games"),
            saves_dir=os.getenv("SAVES_DIR", "/data/saves"),
            command_prefix=os.getenv("COMMAND_PREFIX", ">"),
            guild_id=int(gid) if gid else None,
            dfrotz_path=os.getenv("DFROTZ_PATH", "dfrotz"),
            idle_timeout_min=int(os.getenv("SESSION_IDLE_MINUTES", "30")),
            use_threads=_bool(os.getenv("USE_THREADS"), True),
            read_idle=float(os.getenv("READ_IDLE_SECONDS", "0.4")),
            read_max=float(os.getenv("READ_MAX_SECONDS", "8")),
            thread_delete_delay=int(os.getenv("THREAD_DELETE_DELAY_MINUTES", "5") or 5),
        )
