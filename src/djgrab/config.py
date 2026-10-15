from __future__ import annotations

import os
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


def load_config(path: Path | None = None) -> DownloadConfig:
    path = path or Path("djgrab.toml")
    if not path.is_file():
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
