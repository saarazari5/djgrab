from djgrab.acquire.webdl import WebCandidate
from djgrab.service import download_link, link_kind
from tests.support import FakeDL, cfg, db, paths

VIDEO = "https://www.youtube.com/watch?v=xxrss8LkPHs"
PLAYLIST = "https://www.youtube.com/playlist?list=PL123"
SETLIST = "https://soundcloud.com/artist/sets/night"


def test_link_kind_sorts_tracks_playlists_and_videos():
    assert link_kind("https://open.spotify.com/track/abc") == "spotify-track"
    assert link_kind("https://open.spotify.com/playlist/abc") == "playlist"
    assert link_kind(PLAYLIST) == "playlist"
    assert link_kind(SETLIST) == "playlist"
    assert link_kind(VIDEO) == "video"
    assert link_kind("https://open.spotify.com/album/78M0jtqcImmaJ2W9ebeMFs?si=abc") == "playlist"


def test_an_album_link_searches_songs_and_skips_yt_dlp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "djgrab.service.list_spotify_playlist",
        lambda url, **_kwargs: ([("Shtuby", "Dreamer", 627.0)], []),
    )

    class DL(FakeDL):
        def dump_info(self, url, dest_dir=None, comments=False):
            raise AssertionError("yt-dlp")

        def list_playlist(self, url):
            raise AssertionError("yt-dlp")

    downloader = DL()
    outcome = download_link(
        db(tmp_path),
        cfg(),
        paths(tmp_path),
        downloader,
        "https://open.spotify.com/album/78M0jtqcImmaJ2W9ebeMFs?si=abc",
    )
    assert downloader.searches == ["Shtuby Dreamer"]
    assert downloader.fetches == []
    assert outcome.status == "needs_review"


def test_a_described_set_searches_each_song(tmp_path):
    class DL(FakeDL):
        def dump_info(self, url, dest_dir=None, comments=False):
            return {"description": "DEKEL - Luna\nDEKEL - Bear Line\n", "duration": 100, "comments": []}

        def list_playlist(self, url):
            raise AssertionError("playlist")

    downloader = DL()
    outcome = download_link(db(tmp_path), cfg(), paths(tmp_path), downloader, VIDEO)
    assert sorted(downloader.searches) == ["DEKEL Bear Line", "DEKEL Luna"]
    assert downloader.fetches == []
    assert outcome.status == "needs_review"


def test_a_video_without_a_tracklist_downloads_that_file(tmp_path):
    class DL(FakeDL):
        def dump_info(self, url, dest_dir=None, comments=False):
            return {"description": "thanks for watching", "duration": 180, "comments": []}

    downloader = DL(entries=[WebCandidate("youtube", VIDEO, "Nova Ridge - Solar Drift", "Nova Ridge", 180)])
    outcome = download_link(db(tmp_path), cfg(), paths(tmp_path), downloader, VIDEO)
    assert downloader.searches == []
    assert downloader.fetches == [VIDEO]
    assert outcome.status == "acquired"


def test_a_set_review_can_drop_a_song(tmp_path):
    class DL(FakeDL):
        def dump_info(self, url, dest_dir=None, comments=False):
            return {"description": "DEKEL - Luna\nDEKEL - Bear Line\n", "duration": 100, "comments": []}

    downloader = DL(
        candidates=[
            WebCandidate("youtube", "https://example.test/luna", "DEKEL - Luna", "DEKEL", 180),
            WebCandidate("youtube", "https://example.test/bear", "DEKEL - Bear Line", "DEKEL", 180),
        ]
    )
    outcome = download_link(
        db(tmp_path),
        cfg(),
        paths(tmp_path),
        downloader,
        VIDEO,
        confirm=lambda labels: [0],
    )
    assert downloader.fetches == ["https://example.test/luna"]
    assert "Bear Line" in outcome.message
    assert "removed" in outcome.message


def test_a_playlist_link_downloads_each_entry(tmp_path):
    class DL(FakeDL):
        def dump_info(self, url, dest_dir=None, comments=False):
            raise AssertionError("video")

    entry = WebCandidate("youtube", "https://example.test/a", "Nova Ridge - Solar Drift", "Nova Ridge", 180)
    downloader = DL(entries=[entry])
    outcome = download_link(db(tmp_path), cfg(), paths(tmp_path), downloader, PLAYLIST)
    assert downloader.fetches == ["https://example.test/a"]
    assert outcome.status == "acquired"
