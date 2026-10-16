import json
import urllib.parse
from pathlib import Path

from djgrab.acquire.spotify import (
    genre_for_artist,
    genre_from_embed,
    list_spotify_playlist,
    lookup_spotify,
    spotify_album_id,
    spotify_playlist_id,
    spotify_track_id,
    track_from_embed,
    tracks_from_playlist_embed,
)
from djgrab.acquire.webdl import DownloadError, parse_dump
from djgrab.service import grab_spotify
from tests.support import FakeDL, cfg, db, paths

URL = "https://open.spotify.com/track/1hu2s7qkm5bo03eODpRQO3?si=e9f94b82cf98471c"
EMBED = """
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"state":{"data":{"entity":{"type":"track","title":"Wanna Be Startin' Somethin'","artists":[{"name":"Michael Jackson","uri":"spotify:artist:3fMbdgg4jU18AjLCKBhRSm"}],"duration":363400}}}}}}</script>
"""
ARTIST_EMBED = """
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"state":{"data":{"entity":{"name":"Michael Jackson"}}}}}}</script>
"""


PLAYLIST = """
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"state":{"data":{"entity":{"type":"playlist","name":"80s Mix","trackList":[{"uri":"spotify:track:aaa","title":"Solar Drift","subtitle":"Nova Ridge","duration":180000},{"uri":"spotify:episode:bbb","title":"Talk","subtitle":"Show","duration":60000},{"uri":"spotify:track:ccc","title":"Night Bus","subtitle":"Low Tide","duration":200000}]}}}}}}</script>
"""


def test_spotify_playlist_id_ignores_track_urls():
    playlist = "https://open.spotify.com/playlist/37i9dQZF1EQqZlCxLOykhS?si=baf0d105ca8f404a"
    assert spotify_playlist_id(playlist) == "37i9dQZF1EQqZlCxLOykhS"
    assert spotify_playlist_id("https://open.spotify.com/intl-en/playlist/abc") == "abc"
    assert spotify_playlist_id("spotify:playlist:abc") == "abc"
    assert spotify_playlist_id(URL) is None


def test_album_url_reads_the_embed_track_list():
    album = "https://open.spotify.com/album/78M0jtqcImmaJ2W9ebeMFs?si=Ym3uY2TVRJejYMPaBxEr0Q"
    assert spotify_album_id(album) == "78M0jtqcImmaJ2W9ebeMFs"
    assert spotify_album_id("spotify:album:abc") == "abc"
    seen = []

    def transport(url, data=None, headers=None):
        seen.append(url)
        return PLAYLIST

    tracks, skipped = list_spotify_playlist(album, transport=transport)
    assert seen == ["https://open.spotify.com/embed/album/78M0jtqcImmaJ2W9ebeMFs"]
    assert tracks[0] == ("Nova Ridge", "Solar Drift", 180.0)
    assert skipped == ["Show - Talk"]


def test_playlist_embed_keeps_tracks_and_names_other_entries():
    tracks, skipped = tracks_from_playlist_embed(PLAYLIST)
    assert tracks == [("Nova Ridge", "Solar Drift", 180.0), ("Low Tide", "Night Bus", 200.0)]
    assert skipped == ["Show - Talk"]


def test_spotify_track_id_keeps_query():
    assert spotify_track_id(URL) == "1hu2s7qkm5bo03eODpRQO3"
    assert spotify_track_id("https://open.spotify.com/intl-en/track/abc123") == "abc123"
    assert spotify_track_id("https://open.spotify.com/playlist/abc") is None


def test_embed_parse_ignores_other_fields():
    assert track_from_embed(EMBED) == ("Michael Jackson", "Wanna Be Startin' Somethin'", 363.4)


def test_artist_embed_uses_first_genre():
    html = """
<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"state":{"data":{"entity":{"name":"Michael Jackson","genres":["dance pop","pop"]}}}}}}</script>
"""
    assert genre_from_embed(html) == "dance pop"
    assert genre_from_embed(EMBED) == ""


def test_grab_spotify_searches_with_embed_metadata(tmp_path):
    con = db(tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "solar_drift.json"
    right = parse_dump(fixture.read_text(), "youtube")[0]
    downloader = FakeDL(candidates=[right])

    def lookup(_url, _client_id="", _client_secret=""):
        return ("Nova Ridge", "Solar Drift", 180.0, "dance pop")

    outcome = grab_spotify(con, cfg(), paths(tmp_path), downloader, URL, lookup=lookup)
    assert outcome.status == "acquired"
    assert downloader.searches == ["Nova Ridge Solar Drift"]
    assert downloader.fetches == ["https://example.test/solar"]
    track = con.execute("SELECT artist, title, keeper, acquired_via, genre FROM tracks").fetchone()
    assert track["artist"] == "Nova Ridge"
    assert track["keeper"] == 1
    assert track["acquired_via"] == "web"
    assert track["genre"] == "dance pop"
    filed = con.execute("SELECT path FROM inbox_files").fetchone()
    assert filed["path"].endswith("dance pop/Nova Ridge - Solar Drift.wav")


def _pages(url, data=None, headers=None):
    if "embed/track" in url:
        return EMBED
    if "embed/artist" in url:
        return ARTIST_EMBED
    if data is not None:
        return '{"access_token":"tok"}'
    return '{"genres":["pop","rock"]}'


def test_no_credentials_leave_genre_blank():
    seen = []

    def transport(url, data=None, headers=None):
        seen.append(url)
        return _pages(url, data, headers)

    _artist, _title, _duration, genre = lookup_spotify(URL, transport=transport)
    assert genre == ""
    assert not any("api.spotify.com" in url or "accounts.spotify.com" in url for url in seen)


def test_artist_search_maps_genre():
    pages = {
        "Abstrakt": [
            {"name": "Pulse", "genres": ["edm"]},
            {"name": "Abstrakt", "genres": ["psytrance"]},
        ],
        "Abstrkat": [{"name": "Abstrakt", "genres": ["psytrance"]}],
        "Gorovich feat. Nova": [{"name": "Someone", "genres": ["pop"]}],
        "Gorovich": [{"name": "Gorovich", "genres": ["progressive psytrance"]}],
    }

    def transport(url, data=None, headers=None):
        if data is not None:
            return '{"access_token":"tok"}'
        for name, items in pages.items():
            if urllib.parse.quote(name) in url:
                return json.dumps({"artists": {"items": items}})
        raise AssertionError(url)

    assert genre_for_artist("Abstrakt", "id", "secret", transport) == "psytrance"
    assert genre_for_artist("Abstrkat", "id", "secret", transport) == "psytrance"
    assert genre_for_artist("Gorovich feat. Nova", "id", "secret", transport) == "progressive psytrance"


def test_itunes_supplies_genre_when_spotify_has_none():
    def transport(url, data=None, headers=None):
        if urllib.parse.quote("DEKEL & SHTUBY") in url:
            return json.dumps({"results": [{"artistName": "Other", "primaryGenreName": "Pop"}]})
        if "DEKEL" in url:
            return json.dumps({
                "results": [
                    {"artistName": "DEKEL", "primaryGenreName": "Trance"},
                    {"artistName": "Dekel", "primaryGenreName": "Pop"},
                ]
            })
        raise AssertionError(url)

    assert genre_for_artist("DEKEL", "", "", transport) == "Trance"
    assert genre_for_artist("DEKEL & SHTUBY", "", "", transport) == "Trance"


def test_itunes_retries_when_apple_is_busy():
    calls = {"n": 0}

    def transport(url, data=None, headers=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise DownloadError("spotify lookup failed: HTTP Error 429: Too Many Requests")
        return json.dumps({"results": [{"artistName": "Night Bus", "primaryGenreName": "Trance"}]})

    assert genre_for_artist("Night Bus", "", "", transport) == "Trance"


def test_artist_api_uses_first_genre():
    _artist, _title, _duration, genre = lookup_spotify(
        URL,
        client_id="id",
        client_secret="secret",
        transport=_pages,
    )
    assert genre == "pop"
