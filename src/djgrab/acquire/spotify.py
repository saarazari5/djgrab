from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request

from djgrab.acquire.webdl import DownloadError
from djgrab.identity.normalize import normalize

_TRACK = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?track/|spotify:track:)([A-Za-z0-9]+)"
)
_PLAYLIST = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]{2}/)?playlist/|spotify:playlist:)([A-Za-z0-9]+)"
)
_NEXT = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def spotify_track_id(url: str) -> str | None:
    match = _TRACK.search(url.strip())
    return match.group(1) if match else None


def spotify_playlist_id(url: str) -> str | None:
    match = _PLAYLIST.search(url.strip())
    return match.group(1) if match else None


def tracks_from_playlist_embed(html: str) -> tuple[list[tuple[str, str, float]], list[str]]:
    # shortcut: embed trackList is one page, use the playlist tracks API when a list is cut off
    items = _entity(html).get("trackList") or []
    tracks: list[tuple[str, str, float]] = []
    skipped: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            skipped.append("entry")
            continue
        title = str(item.get("title") or "").strip()
        artist = str(item.get("subtitle") or "").strip() or "Unknown"
        label = f"{artist} - {title}" if title else str(item.get("uri") or "entry")
        uri = str(item.get("uri") or "")
        try:
            duration_s = float(item["duration"]) / 1000
        except (KeyError, TypeError, ValueError):
            duration_s = 0
        if not uri.startswith("spotify:track:") or not title or duration_s <= 0:
            skipped.append(label)
            continue
        tracks.append((artist, title, duration_s))
    return tracks, skipped


def track_from_embed(html: str) -> tuple[str, str, float]:
    entity = _entity(html)
    try:
        names = [artist["name"] for artist in entity["artists"] if artist.get("name")]
        artist = ", ".join(names) or "Unknown"
        title = entity.get("title") or entity["name"]
        duration_s = float(entity["duration"]) / 1000
    except (KeyError, TypeError, ValueError) as exc:
        raise DownloadError("spotify page had no track data") from exc
    if not title or duration_s <= 0:
        raise DownloadError("spotify page had no track data")
    return artist, title, duration_s


def artist_id_from_embed(html: str) -> str:
    artists = _entity(html).get("artists") or []
    if not artists:
        return ""
    artist = artists[0]
    if artist.get("id"):
        return str(artist["id"])
    uri = artist.get("uri") or ""
    if uri.startswith("spotify:artist:"):
        return uri.rsplit(":", 1)[-1]
    return ""


def first_genre(genres) -> str:
    if not genres:
        return ""
    first = genres[0]
    if isinstance(first, str):
        return first
    if isinstance(first, dict):
        return str(first.get("name") or "")
    return ""


def genre_from_embed(html: str) -> str:
    try:
        return first_genre(_entity(html).get("genres") or [])
    except DownloadError:
        return ""


def _entity(html: str) -> dict:
    found = _NEXT.search(html)
    if not found:
        raise DownloadError("spotify page had no track data")
    try:
        return json.loads(found.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DownloadError("spotify page had no track data") from exc


def _request(url: str, data: bytes | None = None, headers: dict | None = None) -> str:
    request = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode()
    except OSError as exc:
        raise DownloadError(f"spotify lookup failed: {exc}") from exc


def list_spotify_playlist(
    url: str,
    transport=_request,
) -> tuple[list[tuple[str, str, float]], list[str]]:
    playlist_id = spotify_playlist_id(url)
    if not playlist_id:
        raise DownloadError("not a spotify playlist url")
    html = transport(f"https://open.spotify.com/embed/playlist/{playlist_id}")
    return tracks_from_playlist_embed(html)


_tokens: dict[str, str] = {}
_artist_items: dict[str, list] = {}
_CREDIT = re.compile(r"\s*(?:,|&|\b(?:feat|ft|vs)\.?)(?:\s+|$)", re.IGNORECASE)


def _access_token(client_id: str, client_secret: str, transport) -> str:
    # shortcut: token is cached for the process, restart if Spotify returns 401
    cached = _tokens.get(client_id)
    if cached:
        return cached
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    token_body = transport(
        "https://accounts.spotify.com/api/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    token = json.loads(token_body)["access_token"]
    _tokens[client_id] = token
    return token


def _artist_queries(artist: str) -> list[str]:
    raw = artist.strip()
    if not raw or raw.casefold() == "unknown":
        return []
    queries = [raw]
    head = _CREDIT.split(raw, maxsplit=1)[0].strip()
    if head and head != raw:
        queries.append(head)
    return queries


def _search_items(query: str, client_id: str, client_secret: str, transport) -> list:
    key = normalize(query)
    if key in _artist_items:
        return _artist_items[key]
    try:
        token = _access_token(client_id, client_secret, transport)
        body = transport(
            "https://api.spotify.com/v1/search?q="
            + urllib.parse.quote(query)
            + "&type=artist&limit=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        items = json.loads(body).get("artists", {}).get("items") or []
    except (DownloadError, KeyError, TypeError, json.JSONDecodeError):
        items = []
    _artist_items[key] = items
    return items


def _exact_genre(query: str, items) -> str:
    wanted = normalize(query)
    for item in items:
        if not isinstance(item, dict):
            continue
        if normalize(str(item.get("name") or "")) == wanted:
            return first_genre(item.get("genres") or [])
    return ""


def _first_genre(items) -> str:
    for item in items:
        if isinstance(item, dict):
            genre = first_genre(item.get("genres") or [])
            if genre:
                return genre
    return ""


def genre_for_artist(
    artist: str,
    client_id: str,
    client_secret: str,
    transport=_request,
) -> str:
    if not client_id or not client_secret:
        return ""
    queries = _artist_queries(artist)
    if not queries:
        return ""
    items = _search_items(queries[0], client_id, client_secret, transport)
    exact = _exact_genre(queries[0], items)
    if exact:
        return exact
    if len(queries) > 1:
        more = _search_items(queries[1], client_id, client_secret, transport)
        return _exact_genre(queries[1], more) or _first_genre(more)
    return _first_genre(items)


def genre_from_artist_api(
    artist_id: str,
    client_id: str,
    client_secret: str,
    transport=_request,
) -> str:
    if not artist_id or not client_id or not client_secret:
        return ""
    try:
        token = _access_token(client_id, client_secret, transport)
        artist_body = transport(
            f"https://api.spotify.com/v1/artists/{artist_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return first_genre(json.loads(artist_body).get("genres") or [])
    except (DownloadError, KeyError, TypeError, json.JSONDecodeError):
        return ""


def lookup_spotify(
    url: str,
    client_id: str = "",
    client_secret: str = "",
    transport=_request,
) -> tuple[str, str, float, str]:
    track_id = spotify_track_id(url)
    if not track_id:
        raise DownloadError("not a spotify track url")
    html = transport(f"https://open.spotify.com/embed/track/{track_id}")
    artist, title, duration_s = track_from_embed(html)
    genre = ""
    artist_id = artist_id_from_embed(html)
    if artist_id:
        try:
            genre = genre_from_embed(transport(f"https://open.spotify.com/embed/artist/{artist_id}"))
        except DownloadError:
            genre = ""
    if not genre and artist_id:
        genre = genre_from_artist_api(artist_id, client_id, client_secret, transport)
    return artist, title, duration_s, genre
