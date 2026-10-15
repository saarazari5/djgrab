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


def test_a_described_set_searches_each_song(tmp_path):
    class DL(FakeDL):
        def dump_info(self, url, dest_dir=None, comments=False):
            return {"description": "DEKEL - Luna\nDEKEL - Bear Line\n", "duration": 100, "comments": []}

        def list_playlist(self, url):
            raise AssertionError("playlist")

    downloader = DL()
    outcome = download_link(db(tmp_path), cfg(), paths(tmp_path), downloader, VIDEO)
    assert downloader.searches == ["DEKEL Luna", "DEKEL Bear Line"]
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


def test_a_playlist_link_downloads_each_entry(tmp_path):
    class DL(FakeDL):
        def dump_info(self, url, dest_dir=None, comments=False):
            raise AssertionError("video")

    entry = WebCandidate("youtube", "https://example.test/a", "Nova Ridge - Solar Drift", "Nova Ridge", 180)
    downloader = DL(entries=[entry])
    outcome = download_link(db(tmp_path), cfg(), paths(tmp_path), downloader, PLAYLIST)
    assert downloader.fetches == ["https://example.test/a"]
    assert outcome.status == "acquired"
