from djgrab.cli import main
from djgrab.db import add_track, connect
from djgrab.migrate import migrate_offlinedj
from tests.support import write_wav


def test_migrate_moves_missing_songs_and_skips_dupes(tmp_path, monkeypatch, capsys):
    library = tmp_path / "library"
    write_wav(library / "House" / "Ada - Kept.wav", 0.1, 440)
    source = tmp_path / "offline"
    write_wav(source / "Tech House" / "Ada - Kept [SoundCloud].mp3", 0.1, 440)
    write_wav(source / "Tech House" / "Ada - Fresh.wav", 0.1, 440)
    write_wav(source / "Tech House" / "Ada - Fresh.mp3", 0.1, 330)
    write_wav(source / "Pop" / "אודיה - פרפרים.wav", 0.1, 520)
    write_wav(source / "_Duplicates" / "Ada - Fresh.flac", 0.1, 100)
    write_wav(source / "House" / "Bea - Onlydb.mp3", 0.1, 200)
    con = connect(tmp_path / "djgrab.sqlite")
    track_id = add_track(con, artist="Bea", title="Onlydb", keeper=1)
    con.execute(
        """INSERT INTO inbox_files (path, matched_track_id, status, quality)
           VALUES (?, ?, 'filed', 'lossy')""",
        (str(library / "House" / "gone.mp3"), track_id),
    )
    con.commit()

    moved, skipped, dupes = migrate_offlinedj(con, library, source)

    assert (moved, skipped, dupes) == (2, 2, 1)
    assert (library / "Tech House" / "Ada - Fresh.wav").is_file()
    assert (library / "Pop" / "אודיה - פרפרים.wav").is_file()
    assert (source / "Tech House" / "Ada - Fresh.mp3").is_file()
    assert (source / "Tech House" / "Ada - Kept [SoundCloud].mp3").is_file()
    assert (source / "House" / "Bea - Onlydb.mp3").is_file()
    assert (source / "_Duplicates" / "Ada - Fresh.flac").is_file()
    got = {
        (row["artist"], row["title"], row["quality"], row["genre"])
        for row in con.execute("SELECT artist, title, quality, genre FROM tracks")
    }
    assert got == {
        ("Bea", "Onlydb", "", ""),
        ("Ada", "Fresh", "lossless", "Tech House"),
        ("אודיה", "פרפרים", "lossless", "Pop"),
    }
    filed = {row["path"] for row in con.execute("SELECT path FROM inbox_files WHERE status = 'filed'")}
    assert str(library / "Tech House" / "Ada - Fresh.wav") in filed

    monkeypatch.setattr("djgrab.cli.offlinedj_folder", lambda: None)
    assert main(["migrate", "--data", str(tmp_path / "missing")]) == 2
    assert "offlineDJ library not found" in capsys.readouterr().err
