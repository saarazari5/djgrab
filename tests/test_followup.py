from djgrab.acquire.webdl import WebCandidate
from djgrab.cli import main
from djgrab.db import add_job, add_track, finish_job
from djgrab.service import Outcome, upgrade_library
from tests.support import FakeDL, cfg, db, paths, write_wav


def test_buylist_prints_open_tracks_and_retry_grabs(tmp_path, monkeypatch, capsys):
    assert main(["buylist", "--data", str(tmp_path)]) == 0
    assert "buy list empty" in capsys.readouterr().out

    con = db(tmp_path)
    open_id = add_track(con, artist="Ada", title="Fresh", keeper=1)
    finish_job(con, add_job(con, open_id, "single"), "buylist", "no match")
    review_id = add_track(con, artist="Cara", title="Later", keeper=1)
    finish_job(con, add_job(con, review_id, "single"), "needs_review", "no match")
    kept_id = add_track(con, artist="Bea", title="Kept", keeper=1)
    finish_job(con, add_job(con, kept_id, "single"), "buylist", "no match")
    kept = tmp_path / "djgrab" / "House" / "Bea - Kept.wav"
    write_wav(kept, 0.1, 440)
    con.execute(
        """INSERT INTO inbox_files (path, matched_track_id, status, quality)
           VALUES (?, ?, 'filed', 'lossy')""",
        (str(kept), kept_id),
    )
    con.commit()

    assert main(["buylist", "--data", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "buylist: Ada - Fresh" in out
    assert "buylist: Cara - Later" in out
    assert "Bea" not in out
    assert "2 on the buy list" in out

    seen = []

    def fake_grab(_con, _cfg, _paths, _downloader, ident):
        seen.append(ident)
        return Outcome(0, "buylist", "no match")

    monkeypatch.setattr("djgrab.cli.grab", fake_grab)
    assert main(["buylist", "retry", "--data", str(tmp_path)]) == 0
    assert seen == [open_id, review_id]


def _lossy_file(con, library):
    track_id = add_track(con, artist="Nova Ridge", title="Solar Drift", duration_s=180, genre="House")
    con.execute("UPDATE tracks SET quality = 'lossy' WHERE id = ?", (track_id,))
    path = library / "House" / "Nova Ridge - Solar Drift.mp3"
    write_wav(path, 0.1, 440)
    con.execute(
        """INSERT INTO inbox_files (path, matched_track_id, status, quality)
           VALUES (?, ?, 'filed', 'lossy')""",
        (str(path), track_id),
    )
    con.commit()
    return track_id, path


def test_upgrade_replaces_a_lossy_file_with_a_lossless_hit(tmp_path):
    con = db(tmp_path)
    library = paths(tmp_path).library
    track_id, old = _lossy_file(con, library)
    hit = WebCandidate(
        "youtube",
        "https://example.test/flac",
        "Nova Ridge - Solar Drift",
        "Nova Ridge",
        180,
        lossless=True,
    )
    replaced = upgrade_library(con, cfg(), paths(tmp_path), FakeDL(candidates=[hit]))
    assert replaced == 1
    assert not old.is_file()
    assert (library / "House" / "Nova Ridge - Solar Drift.wav").is_file()
    assert con.execute("SELECT quality FROM tracks WHERE id = ?", (track_id,)).fetchone()["quality"] == "lossless"
    status = con.execute(
        "SELECT status FROM inbox_files WHERE path = ?",
        (str(old),),
    ).fetchone()["status"]
    assert status == "replaced"


def test_upgrade_leaves_a_file_when_the_hit_is_lossy(tmp_path):
    con = db(tmp_path)
    library = paths(tmp_path).library
    track_id, old = _lossy_file(con, library)
    hit = WebCandidate(
        "youtube",
        "https://example.test/solar",
        "Nova Ridge - Solar Drift",
        "Nova Ridge",
        180,
    )
    downloader = FakeDL(candidates=[hit])
    assert upgrade_library(con, cfg(), paths(tmp_path), downloader) == 0
    assert old.is_file()
    assert downloader.fetches == []
    assert con.execute("SELECT quality FROM tracks WHERE id = ?", (track_id,)).fetchone()["quality"] == "lossy"
