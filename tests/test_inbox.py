import subprocess

from djgrab.db import add_track
from djgrab.inbox import file_staged
from tests.support import db, paths, write_wav


def test_blank_genre_uses_artist_search(tmp_path, monkeypatch):
    from djgrab.config import DownloadConfig

    monkeypatch.setattr("djgrab.inbox.genre_for_artist", lambda artist, client_id, client_secret: "psytrance")
    con = db(tmp_path)
    track_id = add_track(con, artist="Abstrakt", title="Pulse", duration_s=180)
    staged = tmp_path / "staged.wav"
    write_wav(staged, 0.2, 440)
    dest = file_staged(
        con,
        staged,
        track_id,
        via="web",
        quality="lossy",
        library=paths(tmp_path).library,
        cfg=DownloadConfig(spotify_client_id="id", spotify_client_secret="secret", genres={"psytrance": "Psy"}),
    )
    assert dest.parent.name == "Psy"
    assert con.execute("SELECT genre FROM tracks WHERE id = ?", (track_id,)).fetchone()["genre"] == "psytrance"


def test_preset_track_files_as_lossy_web(tmp_path):
    con = db(tmp_path)
    track_id = add_track(con, artist="Nova Ridge", title="Solar Drift", duration_s=180)
    staged = tmp_path / "staged.wav"
    write_wav(staged, 0.2, 440)
    dest = file_staged(
        con,
        staged,
        track_id,
        via="web",
        quality="lossy",
        library=paths(tmp_path).library,
    )
    assert dest == paths(tmp_path).library / "Unknown" / "Nova Ridge - Solar Drift.wav"
    track = con.execute("SELECT acquired_via, quality FROM tracks WHERE id = ?", (track_id,)).fetchone()
    inbox = con.execute("SELECT status, matched_track_id, quality FROM inbox_files").fetchone()
    assert track["acquired_via"] == "web"
    assert track["quality"] == "lossy"
    assert inbox["status"] == "filed"
    assert inbox["matched_track_id"] == track_id
    assert inbox["quality"] == "lossy"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=title", "-of", "default=nw=1", str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Solar Drift" in probe.stdout


def test_tag_audio_embeds_a_cover(tmp_path):
    from djgrab.inbox import tag_audio

    wav = tmp_path / "tone.wav"
    write_wav(wav, 0.2, 440)
    src = tmp_path / "audio.m4a"
    cover = tmp_path / "audio.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-c:a", "aac", str(src)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=16x16", "-frames:v", "1", str(cover)],
        check=True,
        capture_output=True,
    )
    dest = tmp_path / "library" / "DEKEL - Luna.m4a"
    tag_audio(src, dest, "DEKEL", "Luna")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream_disposition=attached_pic",
            "-of",
            "default=nw=1",
            str(dest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "attached_pic=1" in probe.stdout


def test_default_songs_folder_is_djgrab_at_root(monkeypatch):
    from pathlib import Path

    from djgrab.cli import _paths

    monkeypatch.delenv("DJGRAB_DATA", raising=False)
    assert _paths(None).library == Path.home() / "djgrab"
    assert _paths(Path("custom")).library == Path("custom") / "djgrab"


def test_clear_deletes_the_database(tmp_path):
    from djgrab.cli import main
    from djgrab.db import add_track, clear_db, connect

    db_path = tmp_path / "djgrab.sqlite"
    con = connect(db_path)
    add_track(con, artist="DEKEL", title="Luna", duration_s=180)
    con.close()
    (tmp_path / "djgrab.sqlite-wal").write_text("x")
    song = tmp_path / "djgrab" / "DEKEL - Luna.m4a"
    song.parent.mkdir()
    song.write_bytes(b"song")
    clear_db(db_path)
    assert not db_path.exists()
    assert not (tmp_path / "djgrab.sqlite-wal").exists()
    assert song.is_file()
    assert main(["clear", "--data", str(tmp_path)]) == 0
