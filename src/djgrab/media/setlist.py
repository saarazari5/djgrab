from __future__ import annotations

import re
from dataclasses import dataclass

from djgrab.identity.normalize import parse_title

_STAMP = re.compile(r"^\s*\[?(?:(\d+):)?(\d{1,3}):(\d{2})\]?\s+(.+)$")
_BRACKET = re.compile(r"\[[^\]]*\]")


@dataclass
class SetSong:
    artist: str
    title: str
    mix: str
    start_s: float
    end_s: float


def _seconds(hours: str | None, minutes: str, seconds: str) -> float:
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def _named(label: str) -> tuple[str, str, str]:
    label = _BRACKET.sub(" ", label).strip()
    artist, title, mix = parse_title(label.strip(" -"))
    if mix:
        title = f"{title} {mix}".strip()
        mix = ""
    if not artist:
        artist = "Unknown"
    if not title:
        title = label.strip() or "Untitled"
    return artist, title, mix


def lines_to_songs(text: str, duration: float) -> list[SetSong]:
    found: list[tuple[float, str, str, str]] = []
    for line in text.splitlines():
        match = _STAMP.match(line.strip())
        if not match:
            continue
        start = _seconds(match.group(1), match.group(2), match.group(3))
        artist, title, mix = _named(match.group(4))
        found.append((start, artist, title, mix))
    if len(found) < 2:
        return []
    found.sort(key=lambda row: row[0])
    songs: list[SetSong] = []
    for index, (start, artist, title, mix) in enumerate(found):
        end = found[index + 1][0] if index + 1 < len(found) else duration
        if end <= start:
            continue
        songs.append(SetSong(artist, title, mix, start, end))
    return songs


def songs_from_chapters(chapters: list[dict], duration: float) -> list[SetSong]:
    songs: list[SetSong] = []
    for index, chapter in enumerate(chapters):
        start = float(chapter.get("start_time") or 0)
        if chapter.get("end_time") is not None:
            end = float(chapter["end_time"])
        elif index + 1 < len(chapters):
            end = float(chapters[index + 1].get("start_time") or start)
        else:
            end = duration
        if end <= start:
            continue
        artist, title, mix = _named(str(chapter.get("title") or ""))
        songs.append(SetSong(artist, title, mix, start, end))
    return songs


def credit_lines(text: str) -> list[SetSong]:
    songs: list[SetSong] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "://" in line or _STAMP.match(line):
            continue
        if not re.search(r"\s[-–—]\s", line):
            continue
        artist, title, mix = _named(line)
        if artist == "Unknown" or not title:
            continue
        songs.append(SetSong(artist, title, mix, 0, 0))
    if len(songs) < 2:
        return []
    return songs


def tracklist_from_info(info: dict) -> list[SetSong]:
    duration = float(info.get("duration") or 0)
    chapters = info.get("chapters") or []
    if isinstance(chapters, list) and chapters:
        return songs_from_chapters(chapters, duration)
    description = info.get("description") or ""
    stamped = lines_to_songs(description, duration)
    if stamped:
        return stamped
    return credit_lines(description)


def tracklist_from_comments(info: dict) -> list[SetSong]:
    duration = float(info.get("duration") or 0)
    for comment in info.get("comments") or []:
        songs = lines_to_songs(comment.get("text") or "", duration)
        if len(songs) >= 2:
            return songs
    return []
