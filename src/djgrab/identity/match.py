from __future__ import annotations

from dataclasses import dataclass

from djgrab.acquire.webdl import WebCandidate
from djgrab.identity.normalize import clean_tokens, parse_title, split_version, tokens, version_key

BIG_GAP_S = 30


@dataclass
class TrackQuery:
    artist: str
    title: str
    mix: str
    duration_s: float


def _want(track: TrackQuery) -> tuple[str, str]:
    base, version = split_version(track.title)
    return base, f"{version} {track.mix}".strip()


def _parts(candidate: WebCandidate) -> tuple[str, str, str]:
    artist, title, mix = parse_title(candidate.title)
    base, version = split_version(title)
    return artist or candidate.uploader, base, f"{version} {mix}".strip()


def reject_reason(track: TrackQuery, candidate: WebCandidate) -> str:
    """Why the candidate is not this song; empty when it is. Version and length are notes, not vetoes."""
    base, _version = _want(track)
    want_title = clean_tokens(base)
    want_artist = clean_tokens(track.artist)
    placeholder = track.artist.strip().casefold() == "unknown"
    if not want_title or (not placeholder and not want_artist):
        return "track has no title or artist"
    if placeholder:
        _artist, got_base, _version = _parts(candidate)
        if clean_tokens(got_base) != want_title:
            return f"title {got_base!r}"
    else:
        missing = want_title - clean_tokens(candidate.title)
        if missing:
            return f"title missing {' '.join(sorted(missing))}"
        if not want_artist <= tokens(candidate.title) | tokens(candidate.uploader):
            return f"artist {candidate.uploader or '?'!r}"
    # A full album, live set, or DJ mix also carries the artist and song name.
    if track.duration_s > 0 and not 0.5 <= candidate.duration_s / track.duration_s <= 2:
        return f"duration {candidate.duration_s:.0f}s vs {track.duration_s:.0f}s"
    return ""


def passes(track: TrackQuery, candidate: WebCandidate) -> bool:
    return not reject_reason(track, candidate)


def rejections(track: TrackQuery, candidates: list[WebCandidate]) -> str:
    reasons = [reject_reason(track, candidate) for candidate in candidates]
    return ", ".join(f"{reason} x{reasons.count(reason)}" for reason in dict.fromkeys(reasons) if reason)


def duration_gap(track: TrackQuery, candidate: WebCandidate) -> float:
    return abs(candidate.duration_s - track.duration_s) if track.duration_s > 0 else 0


def version_note(track: TrackQuery, candidate: WebCandidate) -> str:
    """Empty when the candidate is the wanted version, else e.g. "wanted 'Dusty Kid Remix', got 'Original Mix'"."""
    _base, want = _want(track)
    _artist, _base, got = _parts(candidate)
    if version_key(want) == version_key(got):
        return ""
    return f"wanted {want or 'original'!r}, got {got or 'original'!r}"


def choose(track: TrackQuery, candidates: list[WebCandidate]) -> tuple[str, list[WebCandidate]]:
    hits = [candidate for candidate in candidates if passes(track, candidate)]
    if not hits:
        return "none", []
    base, _version = _want(track)

    def rank(candidate: WebCandidate) -> tuple:
        artist, got_base, _version = _parts(candidate)
        gap = duration_gap(track, candidate)
        return (
            bool(version_note(track, candidate)),
            gap > BIG_GAP_S,
            not candidate.lossless,
            gap,
            len(clean_tokens(got_base) - clean_tokens(base)),
            clean_tokens(artist) != clean_tokens(track.artist),
        )

    hits.sort(key=rank)
    return "one", hits
