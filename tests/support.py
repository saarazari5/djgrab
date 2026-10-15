from __future__ import annotations

import math
import wave
from pathlib import Path

from djgrab.acquire.webdl import DownloadError, WebCandidate
from djgrab.config import DownloadConfig, Paths
from djgrab.db import connect


def paths(tmp: Path) -> Paths:
    return Paths(tmp)


def db(tmp: Path):
    return connect(tmp / "djgrab.sqlite")


def cfg(**kwargs) -> DownloadConfig:
    return DownloadConfig(**kwargs)


def write_wav(path: Path, seconds: float, hz: float, rate: int = 8000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = int(seconds * rate)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for i in range(count):
            sample = int(32767 * math.sin(2 * math.pi * hz * i / rate))
            frames += sample.to_bytes(2, "little", signed=True)
        handle.writeframes(frames)


class FakeDL:
    def __init__(self, candidates=None, entries=None, fail_search=False, fail_fetch=False):
        self.candidates = candidates or []
        self.entries = entries or []
        self.fail_search = fail_search
        self.fail_fetch = fail_fetch
        self.fetches: list[str] = []
        self.searches: list[str] = []

    def search_meta(self, query: str, limit: int = 5) -> list[WebCandidate]:
        self.searches.append(query)
        if self.fail_search:
            raise DownloadError("search failed")
        return list(self.candidates)

    def fetch_track(self, url: str, dest_dir: Path) -> Path:
        if self.fail_fetch:
            raise DownloadError("fetch failed")
        self.fetches.append(url)
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / "audio.wav"
        write_wav(path, 0.2, 440)
        return path

    def fetch_set_audio(self, url: str, dest: Path) -> Path:
        self.fetches.append(url)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / "set.wav"
        write_wav(path, 0.2, 440)
        return path

    def list_playlist(self, url: str) -> list[WebCandidate]:
        return list(self.entries)
