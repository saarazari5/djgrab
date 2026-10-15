import pytest
from pathlib import Path

from djgrab.acquire.webdl import DownloadError, parse_dump
from djgrab.media.setlist import lines_to_songs, tracklist_from_comments, tracklist_from_info
from djgrab.service import split_set
from tests.support import FakeDL, cfg, db, paths


def test_description_timestamps_set_lengths():
    text = "0:00 Nova Ridge - Solar Drift\n1:10 Other - Night Bus\n"
    songs = lines_to_songs(text, 180)
    assert [(song.artist, song.title, song.start_s, song.end_s) for song in songs] == [
        ("Nova Ridge", "Solar Drift", 0, 70),
        ("Other", "Night Bus", 70, 180),
    ]
    hour = lines_to_songs("0:00 A - One\n1:02:03 B - Two\n", 4000)
    assert hour[1].start_s == 3723


def test_chapters_win_over_description():
    info = {
        "duration": 180,
        "description": "0:00 Wrong - Name\n1:00 Also - Wrong\n",
        "chapters": [
            {"start_time": 0, "end_time": 90, "title": "Nova Ridge - Solar Drift"},
            {"start_time": 90, "end_time": 180, "title": "Low Tide - Night Bus"},
        ],
    }
    songs = tracklist_from_info(info)
    assert [(song.title, song.end_s) for song in songs] == [("Solar Drift", 90), ("Night Bus", 180)]


def test_description_credit_lines_without_times():
    info = {
        "duration": 8998,
        "description": "Tracklist:\n\nDEKEL - Luna\nDEKEL - Mud [ Unreleased ]\nFollow DEKEL:\nhttps://example.test\n",
        "chapters": None,
    }
    songs = tracklist_from_info(info)
    assert [(song.artist, song.title, song.mix) for song in songs] == [
        ("DEKEL", "Luna", ""),
        ("DEKEL", "Mud", ""),
    ]
    info = {
        "duration": 180,
        "description": "great set",
        "comments": [
            {"text": "nice"},
            {"text": "0:00 Nova Ridge - Solar Drift\n2:00 Low Tide - Night Bus"},
        ],
    }
    songs = tracklist_from_comments(info)
    assert len(songs) == 2
    assert songs[0].artist == "Nova Ridge"
    assert songs[1].start_s == 120


def test_set_searches_each_song_and_skips_set_audio(tmp_path):
    solar = parse_dump(
        (Path(__file__).parent / "fixtures" / "solar_drift.json").read_text(),
        "youtube",
    )[0]

    class DL(FakeDL):
        def __init__(self):
            super().__init__(candidates=[solar])
            self.set_audio = False

        def dump_info(self, url, dest_dir=None, comments=False):
            return {
                "description": "0:00 Nova Ridge - Solar Drift\n1:10 Low Tide - Night Bus\n",
                "duration": 180,
                "chapters": None,
            }

        def fetch_set_audio(self, url, dest):
            self.set_audio = True
            raise AssertionError("set audio")

    downloader = DL()
    outcome = split_set(db(tmp_path), cfg(), paths(tmp_path), downloader, "https://example.test/set")
    assert downloader.searches == ["Nova Ridge Solar Drift", "Low Tide Night Bus"]
    assert downloader.fetches == ["https://example.test/solar"]
    assert downloader.set_audio is False
    assert outcome.status == "needs_review"


def test_no_tracklist_does_not_download(tmp_path):
    class DL:
        def __init__(self):
            self.fetched = False
            self.searched = False
            self.comments = 0

        def dump_info(self, url, dest_dir=None, comments=False):
            if comments:
                self.comments += 1
            return {"description": "great set", "duration": 3600, "chapters": None, "comments": []}

        def search_meta(self, query, limit=5):
            self.searched = True
            raise AssertionError("search")

        def fetch_set_audio(self, url, dest):
            self.fetched = True
            raise AssertionError("audio")

    downloader = DL()
    with pytest.raises(DownloadError, match="no tracklist"):
        split_set(db(tmp_path), cfg(), paths(tmp_path), downloader, "https://example.test/set")
    assert downloader.fetched is False
    assert downloader.searched is False
    assert downloader.comments == 1
