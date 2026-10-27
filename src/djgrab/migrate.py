from __future__ import annotations

import json
import re
import shutil
import sqlite3
import unicodedata
from pathlib import Path

from djgrab.db import add_track
from djgrab.identity.normalize import parse_title
from djgrab.inbox import safe_name

_AUDIO = {".mp3", ".flac", ".m4a", ".wav", ".aiff", ".aif", ".ogg"}
_LOSSLESS = {".flac", ".wav", ".aiff", ".aif"}
_SKIP = {"_Duplicates", "_Zips", "DJ Set"}
_TAG = re.compile(r"\s*\[[^\]]*\]")


def song_identity(stem: str) -> str:
    # shortcut: same song with a different filename is not a duplicate, upgrade when tags are read
    stem = _TAG.sub("", stem)
    stem = unicodedata.normalize("NFKD", stem).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", stem, flags=re.UNICODE).split())


def offlinedj_folder() -> Path | None:
    settings = Path.home() / "Library" / "Application Support" / "OfflineDJ" / "offlinedj_settings.json"
    if settings.is_file():
        try:
            raw = json.loads(settings.read_text())
        except json.JSONDecodeError:
            raw = {}
        folder = raw.get("folder") if isinstance(raw, dict) else None
        if folder and Path(folder).is_dir():
            return Path(folder)
    fallback = Path.home() / "OfflineDJ" / "MusicDownloads"
    if fallback.is_dir():
        return fallback
    return None


def _songs(root: Path) -> list[Path]:
    songs = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in _AUDIO:
            continue
        if set(path.relative_to(root).parts) & _SKIP:
            continue
        songs.append(path)
    return songs


def _pick(songs: list[Path]) -> tuple[list[Path], int]:
    groups: dict[str, list[Path]] = {}
    for path in songs:
        groups.setdefault(song_identity(path.stem) or path.stem.casefold(), []).append(path)
    chosen = []
    dupes = 0
    for group in groups.values():
        group.sort(key=lambda path: path.suffix.casefold() not in _LOSSLESS)
        chosen.append(group[0])
        dupes += len(group) - 1
    return chosen, dupes


def _known(con: sqlite3.Connection, library: Path) -> set[str]:
    known = set()
    if library.is_dir():
        for path in library.rglob("*"):
            if path.is_file() and path.suffix.casefold() in _AUDIO:
                known.add(song_identity(path.stem) or path.stem.casefold())
    rows = con.execute(
        """SELECT t.artist, t.title, t.mix
           FROM inbox_files f
           JOIN tracks t ON t.id = f.matched_track_id
           WHERE f.status = 'filed'"""
    )
    for row in rows:
        label = f"{row['artist']} - {row['title']}"
        mix = (row["mix"] or "").strip()
        if mix:
            label = f"{label} ({mix})"
        known.add(song_identity(label) or label.casefold())
    return known


def _record(con: sqlite3.Connection, src: Path, dest: Path, folder: str) -> None:
    cleaned = _TAG.sub("", src.stem).strip()
    artist, title, mix = parse_title(cleaned)
    if not title:
        title = cleaned or src.stem
    quality = "lossless" if src.suffix.casefold() in _LOSSLESS else "lossy"
    track_id = add_track(con, artist=artist, title=title, mix=mix, keeper=1, genre=folder)
    con.execute("UPDATE tracks SET quality = ? WHERE id = ?", (quality, track_id))
    con.execute(
        """INSERT INTO inbox_files (path, matched_track_id, status, quality)
           VALUES (?, ?, 'filed', ?)""",
        (str(dest), track_id, quality),
    )
    con.commit()


def migrate_offlinedj(con: sqlite3.Connection, library: Path, source: Path) -> tuple[int, int, int]:
    chosen, dupes = _pick(_songs(source))
    known = _known(con, library)
    moved = skipped = 0
    for path in chosen:
        ident = song_identity(path.stem) or path.stem.casefold()
        if ident in known:
            skipped += 1
            continue
        parts = path.relative_to(source).parts
        folder = safe_name(parts[0] if len(parts) > 1 else "Unsorted", "Unsorted")
        dest = library / folder / f"{safe_name(path.stem, 'Untitled')}{path.suffix}"
        if dest.exists():
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(path, dest)
        _record(con, path, dest, folder)
        known.add(ident)
        moved += 1
    return moved, skipped, dupes
