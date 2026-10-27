from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

from djgrab.identity.normalize import parse_title

_AUDIO = {".mp3", ".flac", ".m4a", ".wav", ".aiff", ".aif", ".ogg"}
_KIND = {
    ".mp3": "MP3 File",
    ".flac": "FLAC File",
    ".wav": "WAV File",
    ".aiff": "AIFF File",
    ".aif": "AIFF File",
    ".m4a": "M4A File",
    ".ogg": "OGG File",
}
_TAG = re.compile(r"\s*\[[^\]]*\]")


def _duration(path: Path) -> int:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0
    try:
        return max(0, int(float(proc.stdout.strip())))
    except ValueError:
        return 0


def _songs(library: Path) -> list[tuple[str, Path]]:
    found = []
    if not library.is_dir():
        return found
    for path in library.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in _AUDIO:
            continue
        parts = path.relative_to(library).parts
        folder = parts[0] if len(parts) > 1 else "Unsorted"
        found.append((folder, path))
    found.sort(key=lambda item: (item[0].casefold(), item[1].name.casefold()))
    return found


def _track_name(path: Path) -> tuple[str, str]:
    cleaned = _TAG.sub("", path.stem).strip()
    artist, title, mix = parse_title(cleaned)
    if not artist:
        return "", cleaned or path.stem
    name = f"{title} ({mix})" if mix else title
    return artist, name or cleaned or path.stem


def write_rekordbox(library: Path, duration=None) -> tuple[int, Path]:
    duration = duration or _duration
    songs = _songs(library)
    groups: dict[str, list[tuple[int, Path]]] = {}
    root = ElementTree.Element("DJ_PLAYLISTS", Version="1.0.0")
    root.append(ElementTree.Element("PRODUCT", Name="rekordbox", Version="6.0.0", Company="AlphaTheta"))
    collection = ElementTree.SubElement(root, "COLLECTION", Entries=str(len(songs)))
    for index, (folder, path) in enumerate(songs, start=1):
        artist, name = _track_name(path)
        ElementTree.SubElement(
            collection,
            "TRACK",
            TrackID=str(index),
            Name=name,
            Artist=artist,
            Genre=folder,
            Kind=_KIND.get(path.suffix.casefold(), "Audio File"),
            TotalTime=str(duration(path)),
            Location="file://localhost" + quote(path.resolve().as_posix(), safe="/"),
        )
        groups.setdefault(folder, []).append((index, path))
    playlists = ElementTree.SubElement(root, "PLAYLISTS")
    top = ElementTree.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="1")
    grab = ElementTree.SubElement(top, "NODE", Type="0", Name="djgrab", Count="1")
    by_genre = ElementTree.SubElement(grab, "NODE", Type="0", Name="By Genre", Count=str(len(groups)))
    for folder, tracks in groups.items():
        node = ElementTree.SubElement(
            by_genre,
            "NODE",
            Name=folder,
            Type="1",
            KeyType="0",
            Entries=str(len(tracks)),
        )
        for track_id, _path in tracks:
            ElementTree.SubElement(node, "TRACK", Key=str(track_id))
    library.mkdir(parents=True, exist_ok=True)
    dest = library / "rekordbox.xml"
    ElementTree.ElementTree(root).write(dest, encoding="UTF-8", xml_declaration=True)
    return len(songs), dest
