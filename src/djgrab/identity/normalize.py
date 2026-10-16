from __future__ import annotations

import re
import unicodedata

_MIX = re.compile(r"\(([^)]+)\)\s*$")
_SPLIT = re.compile(r"\s+[-–—]\s+")
_NOISE = frozenset({"remaster", "remastered", "official", "audio", "video", "lyric", "lyrics", "hd", "hq"})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.lower().replace("—", " ").replace("–", " ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _noise(token: str) -> bool:
    return not token or token in _NOISE or (len(token) == 4 and token.isdigit())


def tokens(text: str) -> set[str]:
    return {part for part in normalize(text).split() if part}


def clean_tokens(text: str) -> set[str]:
    return {part for part in normalize(text).split() if not _noise(part)}


def search_query(artist: str, title: str) -> str:
    if artist.strip().casefold() == "unknown":
        artist = ""
    kept = []
    for word in f"{artist} {title}".split():
        if _noise(normalize(word)):
            continue
        kept.append(word)
    return " ".join(kept)


def split_version(title: str) -> tuple[str, str]:
    """'Recycled - Dusty Kid Remix' or 'Recycled (Dusty Kid Remix)' -> ('Recycled', 'Dusty Kid Remix')."""
    version = ""
    found = _MIX.search(title.strip())
    if found:
        version = found.group(1).strip()
        title = title[: found.start()]
    parts = _SPLIT.split(title.strip(), maxsplit=1)
    if len(parts) == 2:
        version = f"{parts[1].strip()} {version}".strip()
    return parts[0].strip(), version


def version_key(version: str) -> str:
    """'Original Mix', '' and '2012 Remaster' are all the plain release."""
    return " ".join(sorted(clean_tokens(version) - {"original", "mix"}))


def parse_title(raw: str) -> tuple[str, str, str]:
    mix = ""
    found = _MIX.search(raw.strip())
    if found:
        mix = found.group(1).strip()
        raw = raw[: found.start()].strip()
    parts = _SPLIT.split(raw, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip(), mix
    return "", raw.strip(), mix
