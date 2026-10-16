from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class DownloadConfig:
    enabled: bool = True
    sources: tuple[str, ...] = ("youtube", "soundcloud")
    format: str = "m4a"
    bitrate: str = "256k"
    trim_s: int = 2
    singles: str = "auto_keepers"
    fallback_to_buylist: bool = True
    fallback_genre: str = "Unknown"
    genres: dict[str, str] = field(default_factory=dict)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    soulseek_username: str = ""
    soulseek_password: str = ""


@dataclass
class Paths:
    root: Path
    songs: Path | None = None

    @property
    def db(self) -> Path:
        return self.root / "djgrab.sqlite"

    @property
    def staging(self) -> Path:
        return self.root / "staging"

    @property
    def library(self) -> Path:
        return self.songs if self.songs is not None else self.root / "djgrab"


def _spotify_credentials(raw: dict) -> tuple[str, str]:
    spotify = raw.get("spotify") or {}
    client_id = os.environ.get("SPOTIFY_CLIENT_ID") or str(spotify.get("client_id") or "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or str(spotify.get("client_secret") or "")
    return client_id, client_secret


def config_path() -> Path | None:
    local = Path("djgrab.toml")
    home = Path.home() / ".djgrab" / "djgrab.toml"
    if local.is_file():
        return local
    if home.is_file():
        return home
    return None


def _dump_toml(raw: dict, prefix: str = "") -> str:
    # shortcut: comments are dropped and values are re-serialized, upgrade to tomli-w if that bites
    def key(name: str) -> str:
        return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)

    lines = [f"{key(k)} = {json.dumps(v)}" for k, v in raw.items() if not isinstance(v, dict)]
    if lines and prefix:
        lines.insert(0, f"[{prefix.rstrip('.')}]")
    text = "\n".join(lines) + "\n" if lines else ""
    for k, v in raw.items():
        if isinstance(v, dict):
            text += "\n" + _dump_toml(v, f"{prefix}{k}.")
    return text


def set_config(path: Path, dotted_key: str, value: str) -> None:
    section, _, name = dotted_key.rpartition(".")
    if not section or not name:
        raise ValueError(f"key must be section.name, got {dotted_key!r}")
    raw = tomllib.loads(path.read_text()) if path.is_file() else {}
    table = raw
    for part in section.split("."):
        table = table.setdefault(part, {})
    table[name] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml(raw).lstrip("\n"))


def load_config(path: Path | None = None) -> DownloadConfig:
    if path is None:
        path = config_path()
    if path is None or not path.is_file():
        client_id, client_secret = _spotify_credentials({})
        return DownloadConfig(spotify_client_id=client_id, spotify_client_secret=client_secret)
    raw = tomllib.loads(path.read_text())
    data = raw.get("download", raw)
    library = raw.get("library") or {}
    genre_map = library.get("genres") or {}
    if not isinstance(genre_map, dict):
        genre_map = {}
    sources = tuple(data.get("sources", ("youtube", "soundcloud")))
    client_id, client_secret = _spotify_credentials(raw)
    soulseek = raw.get("soulseek") or {}
    return DownloadConfig(
        enabled=bool(data.get("enabled", True)),
        sources=sources,
        format=str(data.get("format", "m4a")),
        bitrate=str(data.get("bitrate", "256k")),
        trim_s=int(data.get("trim_s", 2)),
        singles=str(data.get("singles", "auto_keepers")),
        fallback_to_buylist=bool(data.get("fallback_to_buylist", True)),
        fallback_genre=str(library.get("fallback_genre", "Unknown")),
        genres={str(key).casefold(): str(value) for key, value in genre_map.items()},
        spotify_client_id=client_id,
        spotify_client_secret=client_secret,
        soulseek_username=str(soulseek.get("username") or ""),
        soulseek_password=str(soulseek.get("password") or ""),
    )
