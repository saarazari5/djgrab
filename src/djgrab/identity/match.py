from __future__ import annotations

from dataclasses import dataclass

from djgrab.acquire.webdl import WebCandidate
from djgrab.identity.normalize import clean_tokens, normalize, parse_title


@dataclass
class TrackQuery:
    artist: str
    title: str
    mix: str
    duration_s: float


def _parts(candidate: WebCandidate) -> tuple[str, str, str]:
    artist, title, mix = parse_title(candidate.title)
    if not artist:
        artist = candidate.uploader
    return artist, title, mix


def passes(track: TrackQuery, candidate: WebCandidate) -> bool:
    artist, title, mix = _parts(candidate)
    want_title = clean_tokens(track.title)
    want_artist = clean_tokens(track.artist)
    placeholder = track.artist.strip().casefold() == "unknown"
    if not want_title or (not placeholder and not want_artist):
        return False
    got_title = clean_tokens(title)
    if placeholder:
        if got_title != want_title:
            return False
    elif not want_title <= got_title or not want_artist <= clean_tokens(artist):
        return False
    if track.mix and normalize(mix) != normalize(track.mix):
        return False
    if track.duration_s <= 0:
        return True
    return abs(candidate.duration_s - track.duration_s) <= 15


def choose(track: TrackQuery, candidates: list[WebCandidate]) -> tuple[str, list[WebCandidate]]:
    hits = [candidate for candidate in candidates if passes(track, candidate)]
    if not hits:
        return "none", []

    def rank(candidate: WebCandidate) -> tuple:
        artist, title, _mix = _parts(candidate)
        extra = len(clean_tokens(title) - clean_tokens(track.title))
        same_uploader = normalize(artist) != normalize(track.artist)
        delta = abs(candidate.duration_s - track.duration_s) if track.duration_s > 0 else 0
        return (
            0 if candidate.lossless else 1,
            delta,
            extra,
            same_uploader,
        )

    hits.sort(key=rank)
    return "one", hits
