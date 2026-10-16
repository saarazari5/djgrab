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


def reject_reason(track: TrackQuery, candidate: WebCandidate) -> str:
    """Why the candidate is not this track; empty when it is."""
    artist, title, mix = _parts(candidate)
    want_title = clean_tokens(track.title)
    want_artist = clean_tokens(track.artist)
    placeholder = track.artist.strip().casefold() == "unknown"
    if not want_title or (not placeholder and not want_artist):
        return "track has no title or artist"
    got_title = clean_tokens(title)
    if placeholder and got_title != want_title:
        return f"title {title!r}"
    if not placeholder:
        missing = want_title - got_title
        if missing:
            return f"title missing {' '.join(sorted(missing))}"
        if not want_artist <= clean_tokens(artist):
            return f"artist {artist!r}"
    if track.mix and normalize(mix) != normalize(track.mix):
        return f"mix {mix or 'none'!r}"
    if track.duration_s > 0 and abs(candidate.duration_s - track.duration_s) > 15:
        return f"duration {candidate.duration_s:.0f}s vs {track.duration_s:.0f}s"
    return ""


def passes(track: TrackQuery, candidate: WebCandidate) -> bool:
    return not reject_reason(track, candidate)


def rejections(track: TrackQuery, candidates: list[WebCandidate]) -> str:
    reasons = [reject_reason(track, candidate) for candidate in candidates]
    return ", ".join(f"{reason} x{reasons.count(reason)}" for reason in dict.fromkeys(reasons) if reason)


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
