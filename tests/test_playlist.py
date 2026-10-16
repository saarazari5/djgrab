from pathlib import Path

from djgrab.acquire.webdl import DownloadError, WebCandidate, parse_dump
from djgrab.db import add_track, get_track
from djgrab.service import _move, grab, run_playlist
from tests.support import FakeDL, cfg, db, paths

FIXTURE = Path(__file__).parent / "fixtures" / "playlist.json"


def test_playlist_downloads_entries_and_records_skips(tmp_path, capsys):
    con = db(tmp_path)
    entries = parse_dump(FIXTURE.read_text(), "youtube")
    downloader = FakeDL(entries=entries)
    outcome = run_playlist(con, cfg(), paths(tmp_path), downloader, "https://example.test/list")
    out = capsys.readouterr().out
    assert "listed 2" in out
    assert "1/2 downloading Nova Ridge - Solar Drift" in out
    assert "1/2 filed Nova Ridge - Solar Drift ->" in out
    assert "2/2 skipped Nova Ridge - No Link Track" in out
    assert outcome.status == "needs_review"
    assert "No Link Track" in outcome.message
    assert downloader.searches == []
    assert downloader.fetches == ["https://example.test/solar"]
    tracks = con.execute("SELECT * FROM tracks").fetchall()
    assert len(tracks) == 1
    assert tracks[0]["acquired_via"] == "web"
    assert tracks[0]["quality"] == "lossy"
    assert get_track(con, tracks[0]["id"])["title"] == "Solar Drift"


class _FailFirst(FakeDL):
    def fetch_track(self, url: str, dest):
        if url.endswith("/solar"):
            raise DownloadError("fetch failed")
        return super().fetch_track(url, dest)


def test_spotify_playlist_continues_after_a_failed_download(tmp_path):
    con = db(tmp_path)
    downloader = _FailFirst(
        candidates=[
            WebCandidate("youtube", "https://example.test/solar", "Nova Ridge - Solar Drift", "", 180),
            WebCandidate("youtube", "https://example.test/night", "Low Tide - Night Bus", "", 200),
        ]
    )

    def listing(_url):
        return (
            [("Nova Ridge", "Solar Drift", 180.0), ("Low Tide", "Night Bus", 200.0)],
            ["Show - Talk"],
        )

    outcome = run_playlist(
        con,
        cfg(fallback_to_buylist=False),
        paths(tmp_path),
        downloader,
        "https://open.spotify.com/playlist/37i9dQZF1EQqZlCxLOykhS",
        listing=listing,
    )
    assert outcome.status == "failed"
    assert "filed 1" in outcome.message
    assert "Show - Talk" in outcome.message
    assert "fetch failed" in outcome.message
    assert sorted(downloader.searches) == ["Low Tide Night Bus", "Nova Ridge Solar Drift"]
    assert downloader.fetches == ["https://example.test/night"]
    rows = con.execute(
        "SELECT artist, title, keeper, genre, acquired_via FROM tracks ORDER BY id"
    ).fetchall()
    assert [(row["title"], row["acquired_via"], row["genre"], row["keeper"]) for row in rows] == [
        ("Solar Drift", "inbox", "", 1),
        ("Night Bus", "web", "", 1),
    ]


def test_playlist_names_untitled_entry_from_download(tmp_path, capsys):
    con = db(tmp_path)
    entry = WebCandidate("soundcloud", "https://api-v2.soundcloud.com/tracks/1821750795", "", "", 0)
    downloader = FakeDL(entries=[entry])
    downloader.last_label = "DJ Nova\tNight Drive"
    outcome = run_playlist(con, cfg(), paths(tmp_path), downloader, "https://soundcloud.com/sets/x")
    assert outcome.status == "acquired"
    track = con.execute("SELECT artist, title FROM tracks").fetchone()
    assert track["artist"] == "DJ Nova"
    assert track["title"] == "Night Drive"
    out = capsys.readouterr().out
    assert "1/1 downloading 1821750795" in out
    assert "filed DJ Nova - Night Drive ->" in out


def _listing(tracks):
    def listing(_url):
        return (tracks, [])

    return listing


SPOTIFY = "https://open.spotify.com/playlist/37i9dQZF1EQqZlCxLOykhS"


def test_unchecked_song_is_not_fetched(tmp_path):
    con = db(tmp_path)
    solar = WebCandidate("youtube", "https://example.test/solar", "Nova Ridge - Solar Drift", "", 180)
    night = WebCandidate("youtube", "https://example.test/night", "Low Tide - Night Bus", "", 200)
    downloader = FakeDL(candidates=[solar, night])
    outcome = run_playlist(
        con,
        cfg(),
        paths(tmp_path),
        downloader,
        SPOTIFY,
        listing=_listing(
            [("Nova Ridge", "Solar Drift", 180.0), ("Low Tide", "Night Bus", 200.0)]
        ),
        confirm=lambda labels: [0],
    )
    assert downloader.fetches == ["https://example.test/solar"]
    assert "removed" in outcome.message
    assert "Night Bus" in outcome.message


def test_enter_keeps_every_song(tmp_path):
    checked = [True, True]
    _cursor, done = _move("\n", 0, checked)
    assert done
    assert checked == [True, True]
    con = db(tmp_path)
    solar = WebCandidate("youtube", "https://example.test/solar", "Nova Ridge - Solar Drift", "", 180)
    night = WebCandidate("youtube", "https://example.test/night", "Low Tide - Night Bus", "", 200)
    downloader = FakeDL(candidates=[solar, night])
    outcome = run_playlist(
        con,
        cfg(),
        paths(tmp_path),
        downloader,
        SPOTIFY,
        listing=_listing(
            [("Nova Ridge", "Solar Drift", 180.0), ("Low Tide", "Night Bus", 200.0)]
        ),
        confirm=lambda labels: list(range(len(labels))),
    )
    assert outcome.status == "acquired"
    assert sorted(downloader.fetches) == ["https://example.test/night", "https://example.test/solar"]


def test_space_unchecks_the_highlighted_song():
    checked = [True, True]
    cursor, done = _move("B", 0, checked)
    assert cursor == 1
    assert done is False
    _move(" ", cursor, checked)
    assert checked == [True, False]


def test_filed_and_unmatched_songs_stay_off_the_list(tmp_path):
    con = db(tmp_path)
    library = paths(tmp_path)
    solar = WebCandidate("youtube", "https://example.test/solar", "Nova Ridge - Solar Drift", "", 180)
    night = WebCandidate("youtube", "https://example.test/night", "Low Tide - Night Bus", "", 200)
    filed = add_track(con, artist="Nova Ridge", title="Solar Drift", duration_s=180, keeper=1)
    assert grab(con, cfg(), library, FakeDL(candidates=[solar]), filed).status == "acquired"
    seen = []

    def confirm(labels):
        seen.extend(labels)
        return list(range(len(labels)))

    downloader = FakeDL(candidates=[solar, night])
    outcome = run_playlist(
        con,
        cfg(),
        library,
        downloader,
        SPOTIFY,
        listing=_listing(
            [
                ("Nova Ridge", "Solar Drift", 180.0),
                ("Low Tide", "Night Bus", 200.0),
                ("Nobody", "Missing", 190.0),
            ]
        ),
        confirm=confirm,
    )
    assert seen == ["Low Tide - Night Bus"]
    assert sorted(downloader.searches) == ["Low Tide Night Bus", "Nobody Missing"]
    assert downloader.fetches == ["https://example.test/night"]
    assert "already have" in outcome.message
    assert "no match" in outcome.message
