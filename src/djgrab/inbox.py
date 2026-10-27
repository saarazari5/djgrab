from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from djgrab.acquire.spotify import genre_for_artist
from djgrab.config import DownloadConfig
from djgrab.identity.normalize import normalize

_UNSAFE = str.maketrans({"/": "-", ":": "-", "\x00": ""})
_COVER = {".m4a", ".mp4", ".mp3", ".flac", ".ogg", ".opus", ".aac"}


def _cover_next_to(src: Path) -> Path | None:
    for suffix in (".jpg", ".jpeg", ".png"):
        candidate = src.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def _run_ffmpeg(args: list[str]) -> None:
    try:
        proc = subprocess.run(args, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed; run djgrab doctor") from exc
    if proc.returncode != 0:
        lines = [line.strip() for line in (proc.stderr or "").splitlines() if line.strip()]
        raise RuntimeError(lines[-1] if lines else "ffmpeg failed while tagging")


def tagged_title(title: str, mix: str) -> str:
    mix = mix.strip()
    if not mix or mix.casefold() in title.casefold():
        return title
    return f"{title} ({mix})"


def tag_audio(src: Path, dest: Path, artist: str, title: str, genre: str = "", mix: str = "") -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = ["-metadata", f"artist={artist}", "-metadata", f"title={tagged_title(title, mix)}"]
    if genre.strip():
        meta.extend(["-metadata", f"genre={genre}"])
    meta.append(str(dest))
    cover = _cover_next_to(src)
    if cover and dest.suffix.casefold() in _COVER:
        try:
            _run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(src),
                    "-i",
                    str(cover),
                    "-map",
                    "0:a",
                    "-map",
                    "1:v",
                    "-c",
                    "copy",
                    "-disposition:v:0",
                    "attached_pic",
                    *meta,
                ]
            )
            return
        except RuntimeError:
            pass
    streams = ["-map", "0:a"] if dest.suffix.casefold() == ".wav" else ["-map", "0"]
    _run_ffmpeg(["ffmpeg", "-y", "-i", str(src), *streams, "-c", "copy", *meta])


def safe_name(value: str, fallback: str) -> str:
    cleaned = value.translate(_UNSAFE).strip().lstrip(".")
    if cleaned in ("", ".."):
        return fallback
    return cleaned


def genre_folder(genre: str, cfg: DownloadConfig) -> str:
    if not genre.strip():
        return safe_name(cfg.fallback_genre, "Unknown")
    mapped = cfg.genres.get(genre.casefold())
    return safe_name(mapped or genre, safe_name(cfg.fallback_genre, "Unknown"))


def library_dest(library: Path, track, suffix: str, cfg: DownloadConfig) -> Path:
    folder = genre_folder(track["genre"], cfg)
    stem = f"{safe_name(track['artist'], 'Unknown')} - {safe_name(track['title'], 'Untitled')}"
    dest = library / folder / f"{stem}{suffix}"
    if dest.exists():
        dest = library / folder / f"{stem} ({track['id']}){suffix}"
    return dest


def file_staged(
    con: sqlite3.Connection,
    staged: Path,
    track_id: int,
    *,
    via: str,
    quality: str,
    library: Path,
    job_id: int | None = None,
    tagger=tag_audio,
    cfg: DownloadConfig | None = None,
) -> Path:
    track = con.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
    if track is None:
        raise LookupError(f"unknown track {track_id}")
    cfg = cfg or DownloadConfig()
    if not str(track["genre"] or "").strip():
        found = genre_for_artist(track["artist"], cfg.spotify_client_id, cfg.spotify_client_secret)
        if found:
            con.execute("UPDATE tracks SET genre = ? WHERE id = ?", (found, track_id))
            con.commit()
            track = con.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
    dest = library_dest(library, track, staged.suffix, cfg)
    shown = genre_folder(track["genre"], cfg) if str(track["genre"] or "").strip() else ""
    tagger(staged, dest, track["artist"], track["title"], shown, track["mix"] or "")
    con.execute(
        "UPDATE tracks SET acquired_via = ?, quality = ? WHERE id = ?",
        (via, quality, track_id),
    )
    con.execute(
        """INSERT INTO inbox_files (path, matched_track_id, status, quality)
           VALUES (?, ?, 'filed', ?)""",
        (str(dest), track_id, quality),
    )
    if job_id is not None:
        con.execute(
            """UPDATE jobs
               SET status = 'acquired', error = '', retryable = 0
               WHERE id = ?""",
            (job_id,),
        )
    con.commit()
    return dest


def retag_file(path: Path, artist: str, title: str, genre: str = "", mix: str = "") -> None:
    temp = path.with_name(f".{path.stem}.retag{path.suffix}")
    try:
        tag_audio(path, temp, artist, title, genre, mix)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def retag_library(con: sqlite3.Connection, cfg: DownloadConfig) -> int:
    rows = con.execute(
        """SELECT f.path, t.id, t.artist, t.title, t.mix, t.genre
           FROM inbox_files f
           JOIN tracks t ON t.id = f.matched_track_id
           WHERE f.status = 'filed'"""
    )
    done = 0
    for row in rows:
        path = Path(row["path"])
        if not path.is_file():
            continue
        genre = str(row["genre"] or "").strip()
        if not genre:
            genre = genre_for_artist(row["artist"], cfg.spotify_client_id, cfg.spotify_client_secret)
            if genre:
                con.execute("UPDATE tracks SET genre = ? WHERE id = ?", (genre, row["id"]))
                con.commit()
        shown = genre_folder(genre, cfg) if genre else ""
        retag_file(path, row["artist"], row["title"], shown, row["mix"] or "")
        done += 1
    return done


def filed_copy(con: sqlite3.Connection, artist: str, title: str, mix: str = "") -> str:
    if artist.strip().casefold() == "unknown" or not title.strip():
        return ""
    want = (normalize(artist), normalize(title), normalize(mix))
    rows = con.execute(
        """SELECT t.artist, t.title, t.mix, f.path
           FROM inbox_files f
           JOIN tracks t ON t.id = f.matched_track_id
           WHERE f.status = 'filed'"""
    )
    for row in rows:
        got = (normalize(row["artist"]), normalize(row["title"]), normalize(row["mix"] or ""))
        if got != want:
            continue
        if Path(row["path"]).is_file():
            return row["path"]
    return ""


def file_free(
    con: sqlite3.Connection,
    track_id: int,
    library: Path,
    job_id: int | None = None,
    cfg: DownloadConfig | None = None,
) -> None:
    track = con.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
    if track is None:
        raise LookupError(f"unknown track {track_id}")
    local = Path(track["free_url"])
    if track["free_url"] and local.is_file():
        file_staged(
            con,
            local,
            track_id,
            via="free",
            quality="",
            library=library,
            job_id=job_id,
            cfg=cfg,
        )
        return
    con.execute(
        "UPDATE tracks SET acquired_via = 'free' WHERE id = ?",
        (track_id,),
    )
    con.execute(
        """INSERT INTO inbox_files (path, matched_track_id, status, quality)
           VALUES (?, ?, 'filed', '')""",
        (track["free_url"], track_id),
    )
    if job_id is not None:
        con.execute(
            "UPDATE jobs SET status = 'acquired', error = '', retryable = 0 WHERE id = ?",
            (job_id,),
        )
    con.commit()
