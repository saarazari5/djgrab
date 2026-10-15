from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
  id INTEGER PRIMARY KEY,
  artist TEXT NOT NULL,
  title TEXT NOT NULL,
  mix TEXT NOT NULL DEFAULT '',
  duration_s REAL NOT NULL DEFAULT 0,
  keeper INTEGER NOT NULL DEFAULT 0,
  free_url TEXT NOT NULL DEFAULT '',
  acquired_via TEXT NOT NULL DEFAULT 'inbox'
    CHECK (acquired_via IN ('inbox', 'free', 'web', 'purchase')),
  quality TEXT NOT NULL DEFAULT '',
  genre TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  track_id INTEGER,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT NOT NULL DEFAULT '',
  candidates TEXT NOT NULL DEFAULT '',
  retryable INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inbox_files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL,
  matched_track_id INTEGER,
  status TEXT NOT NULL,
  quality TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS spend (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    columns = {row[1] for row in con.execute("PRAGMA table_info(tracks)")}
    if "genre" not in columns:
        con.execute("ALTER TABLE tracks ADD COLUMN genre TEXT NOT NULL DEFAULT ''")
    return con


def clear_db(path: Path) -> None:
    for name in (path.name, f"{path.name}-wal", f"{path.name}-shm"):
        (path.parent / name).unlink(missing_ok=True)


def add_track(
    con: sqlite3.Connection,
    *,
    artist: str,
    title: str,
    mix: str = "",
    duration_s: float = 0,
    free_url: str = "",
    keeper: int = 0,
    genre: str = "",
) -> int:
    cur = con.execute(
        """INSERT INTO tracks (artist, title, mix, duration_s, free_url, keeper, genre)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (artist, title, mix, duration_s, free_url, keeper, genre),
    )
    con.commit()
    return int(cur.lastrowid)


def get_track(con: sqlite3.Connection, track_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()


def add_job(
    con: sqlite3.Connection,
    track_id: int | None,
    kind: str,
    status: str = "pending",
) -> int:
    cur = con.execute(
        "INSERT INTO jobs (track_id, kind, status) VALUES (?, ?, ?)",
        (track_id, kind, status),
    )
    con.commit()
    return int(cur.lastrowid)


def finish_job(
    con: sqlite3.Connection,
    job_id: int,
    status: str,
    error: str = "",
    candidates: str = "",
    retryable: int = 0,
) -> None:
    con.execute(
        """UPDATE jobs
           SET status = ?, error = ?, candidates = ?, retryable = ?
           WHERE id = ?""",
        (status, error, candidates, retryable, job_id),
    )
    con.commit()


def add_spend(con: sqlite3.Connection, day: date | None = None) -> None:
    day = day or date.today()
    con.execute(
        "INSERT INTO spend (provider, created_at) VALUES ('ytdlp', ?)",
        (f"{day.isoformat()}T00:00:00",),
    )
    con.commit()
