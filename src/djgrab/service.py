from __future__ import annotations

import json
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from djgrab.acquire.spotify import (
    list_spotify_playlist,
    lookup_spotify,
    spotify_album_id,
    spotify_playlist_id,
    spotify_track_id,
)
from djgrab.acquire.webdl import DownloadError, WebCandidate, YtDlpDownloader, permanent_error
from djgrab.config import DownloadConfig, Paths
from djgrab.db import add_job, add_track, finish_job, get_track
from djgrab.identity.match import BIG_GAP_S, TrackQuery, choose, duration_gap, rejections, version_note
from djgrab.identity.normalize import parse_title, search_query
from djgrab.inbox import file_free, file_staged, filed_copy
from djgrab.media.cut import cut_segments, parse_timeline
from djgrab.media.setlist import tracklist_from_comments, tracklist_from_info


@dataclass
class Outcome:
    job_id: int
    status: str
    message: str


def _hard_fail(con, cfg: DownloadConfig, job_id: int, message: str) -> Outcome:
    if cfg.fallback_to_buylist:
        finish_job(con, job_id, "buylist", message, retryable=1)
        return Outcome(job_id, "buylist", message)
    finish_job(con, job_id, "failed", message, retryable=1)
    return Outcome(job_id, "failed", message)


def resolve_track_id(con, ident: int) -> int:
    if get_track(con, ident) is not None:
        return ident
    row = con.execute("SELECT track_id FROM jobs WHERE id = ?", (ident,)).fetchone()
    if row is not None and row["track_id"] is not None:
        return int(row["track_id"])
    raise LookupError(f"unknown track or job id {ident}")


def _query(track) -> TrackQuery:
    return TrackQuery(track["artist"], track["title"], track["mix"], float(track["duration_s"]))


def _enabled_block(con, cfg: DownloadConfig, job_id: int) -> Outcome | None:
    if cfg.enabled:
        return None
    message = "download.enabled is false"
    finish_job(con, job_id, "failed", message)
    return Outcome(job_id, "failed", message)


_soulseek = threading.Lock()


def _candidates(downloader, query: str) -> tuple[list[WebCandidate], str]:
    found: list[WebCandidate] = []
    error = ""
    soulseek = getattr(downloader, "soulseek", None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        meta = pool.submit(downloader.search_meta, query, 5)
        soul = None
        if soulseek is not None:
            soul = pool.submit(_soulseek_search, soulseek, query)
        try:
            found.extend(meta.result())
        except DownloadError as exc:
            error = str(exc)
        if soul is not None:
            try:
                found.extend(soul.result())
            except DownloadError as exc:
                error = error or str(exc)
    return found, error


def _soulseek_search(soulseek, query: str):
    with _soulseek:
        return soulseek.search(query)


def _from_found(track, found, error: str) -> tuple[str, object]:
    if not found:
        return "none", (error or "no match", [])
    _kind, hits = choose(_query(track), found)
    if not hits:
        return "none", (f"no match ({rejections(_query(track), found)})", found)
    return "ready", hits


def _match_track(downloader, track) -> tuple[str, object]:
    found, error = _candidates(downloader, search_query(track["artist"], track["title"]))
    return _from_found(track, found, error)


def _web_found(downloader, track) -> tuple[list[WebCandidate], str]:
    try:
        return downloader.search_meta(search_query(track["artist"], track["title"]), 5), ""
    except DownloadError as exc:
        return [], str(exc)


def _soul_sets(soulseek, queries: list[str]) -> list[list[WebCandidate]]:
    try:
        return soulseek.search_batch(queries)
    except DownloadError:
        return [[] for _ in queries]


def ask(question: str) -> bool:
    if not sys.stdin.isatty():
        return False
    return input(f"{question} [y/N] ").strip().casefold() in ("y", "yes")


def _mmss(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _warnings(query: TrackQuery, label: str, hits) -> tuple[str, str]:
    best = hits[0]
    question = ""
    if duration_gap(query, best) > BIG_GAP_S:
        question = (
            f"{label}: best file is {_mmss(best.duration_s)}, expected {_mmss(query.duration_s)}. download anyway?"
        )
    return question, version_note(query, best)


def _shown_label(label: str) -> str:
    room = max(1, shutil.get_terminal_size(fallback=(80, 24)).columns - 6)
    if len(label) <= room:
        return label
    return label[: room - 1] + "…"


def _save_hits(con, cfg, paths, downloader, track_id, hits, job_id: int | None = None) -> Outcome:
    if job_id is None:
        job_id = add_job(con, track_id, "single")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    audio = None
    chosen = hits[0]
    last_error = ""
    for hit in hits:
        _say(f"downloading {hit.title or hit.url}")
        try:
            folder = paths.staging / f"job-{job_id}"
            if hit.source == "soulseek":
                audio = downloader.soulseek.fetch(hit.url, folder)
            else:
                audio = downloader.fetch_track(hit.url, folder)
            chosen = hit
            break
        except DownloadError as exc:
            last_error = str(exc)
            if permanent_error(exc) or hit.source == "soulseek":
                continue
            return _hard_fail(con, cfg, job_id, last_error)
    if audio is None:
        return _hard_fail(con, cfg, job_id, last_error or "no match")
    try:
        dest = file_staged(
            con,
            audio,
            track_id,
            via="web",
            quality="lossless" if chosen.lossless else "lossy",
            library=paths.library,
            job_id=job_id,
            cfg=cfg,
        )
    except RuntimeError as exc:
        finish_job(con, job_id, "failed", str(exc), retryable=1)
        return Outcome(job_id, "failed", str(exc))
    _say(f"filed {dest}")
    return Outcome(job_id, "acquired", "filed lossy web download")


def grab(con, cfg: DownloadConfig, paths: Paths, downloader, ident: int) -> Outcome:
    track_id = resolve_track_id(con, ident)
    track = get_track(con, track_id)
    job_id = add_job(con, track_id, "single")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    if track["free_url"]:
        _say(f"filing free link for {track['artist']} - {track['title']}")
        file_free(con, track_id, paths.library, job_id, cfg)
        return Outcome(job_id, "acquired", "filed free link")
    existing = filed_copy(con, track["artist"], track["title"], track["mix"] or "")
    if existing:
        _say(f"already have {existing}")
        finish_job(con, job_id, "acquired", f"already have {existing}")
        return Outcome(job_id, "acquired", f"already have {existing}")
    _say(f"searching {search_query(track['artist'], track['title'])}")
    status, payload = _match_track(downloader, track)
    if status == "ready":
        label = f"{track['artist']} - {track['title']}"
        question, note = _warnings(_query(track), label, payload)
        if question and not ask(_tone(question, "33")):
            best = payload[0]
            message = f"length {_mmss(best.duration_s)} vs {_mmss(_query(track).duration_s)}, declined"
            status, payload = "none", (message, payload)
        elif note:
            _say(_tone(f"note  {label}: {note}", "33"))
    if status == "none":
        message, found = payload
        if not found:
            return _hard_fail(con, cfg, job_id, message)
        dumped = json.dumps([asdict(item) for item in found])
        if cfg.fallback_to_buylist:
            finish_job(con, job_id, "buylist", message, dumped)
            return Outcome(job_id, "buylist", message)
        finish_job(con, job_id, "needs_review", message, dumped)
        return Outcome(job_id, "needs_review", message)
    return _save_hits(con, cfg, paths, downloader, track_id, payload, job_id)


def buy_list(con) -> list:
    rows = con.execute(
        """SELECT t.id, t.artist, t.title, t.mix
           FROM tracks t
           JOIN jobs j ON j.track_id = t.id
           WHERE j.status IN ('buylist', 'needs_review')
             AND j.id = (
               SELECT MAX(j2.id) FROM jobs j2
               WHERE j2.track_id = t.id AND j2.status IN ('buylist', 'needs_review')
             )
           ORDER BY t.artist, t.title"""
    ).fetchall()
    return [
        row
        for row in rows
        if not filed_copy(con, row["artist"], row["title"], row["mix"] or "")
    ]


def upgrade_library(con, cfg: DownloadConfig, paths: Paths, downloader, confirm=None) -> int:
    confirm = ask if confirm is None else confirm
    rows = con.execute(
        """SELECT t.id, t.artist, t.title, t.mix, t.duration_s, f.id AS file_id, f.path
           FROM tracks t
           JOIN inbox_files f ON f.matched_track_id = t.id AND f.status = 'filed'
           WHERE t.quality != 'lossless'"""
    ).fetchall()
    replaced = 0
    seen: set[int] = set()
    for row in rows:
        track_id = int(row["id"])
        if track_id in seen:
            continue
        old = Path(row["path"])
        if not old.is_file():
            continue
        seen.add(track_id)
        label = f"{row['artist']} - {row['title']}"
        status, payload = _match_track(downloader, row)
        if status != "ready" or not payload[0].lossless:
            _say(f"kept {label}")
            continue
        question, note = _warnings(_query(row), label, payload)
        if question and not confirm(_tone(question, "33")):
            _say(f"kept {label}")
            continue
        if note:
            _say(_tone(f"note  {label}: {note}", "33"))
        hits = [hit for hit in payload if hit.lossless]
        outcome = _save_hits(con, cfg, paths, downloader, track_id, hits)
        if outcome.status != "acquired":
            continue
        new = con.execute(
            """SELECT path FROM inbox_files
               WHERE matched_track_id = ? AND status = 'filed' AND id != ?
               ORDER BY id DESC LIMIT 1""",
            (track_id, row["file_id"]),
        ).fetchone()
        con.execute(
            "UPDATE inbox_files SET status = 'replaced' WHERE id = ?",
            (row["file_id"],),
        )
        con.execute("UPDATE tracks SET quality = 'lossless' WHERE id = ?", (track_id,))
        con.commit()
        if new is not None and old.is_file() and old != Path(new["path"]):
            old.unlink()
        replaced += 1
    return replaced


def grab_spotify(con, cfg: DownloadConfig, paths: Paths, downloader, url: str, lookup=lookup_spotify) -> Outcome:
    artist, title, duration_s, genre = lookup(
        url,
        cfg.spotify_client_id,
        cfg.spotify_client_secret,
    )
    track_id = add_track(
        con,
        artist=artist,
        title=title,
        duration_s=duration_s,
        keeper=1,
        genre=genre,
    )
    return grab(con, cfg, paths, downloader, track_id)


def keep(con, cfg: DownloadConfig, paths: Paths, downloader, track_id: int) -> Outcome:
    if get_track(con, track_id) is None:
        raise LookupError(f"unknown track or job id {track_id}")
    con.execute("UPDATE tracks SET keeper = 1 WHERE id = ?", (track_id,))
    con.commit()
    if cfg.singles != "auto_keepers":
        return Outcome(0, "keeper", "keeper set")
    return grab(con, cfg, paths, downloader, track_id)


def _say(message: str) -> None:
    print(message, flush=True)


def _tone(message: str, code: str) -> str:
    if not sys.stdout.isatty():
        return message
    return f"\x1b[{code}m{message}\x1b[0m"


def _choice_line(label: str, on: bool, current: bool) -> str:
    box = "x" if on else " "
    if current:
        return f"\x1b[1;36m> [{box}] {label}\x1b[0m"
    if on:
        return f"  \x1b[32m[{box}]\x1b[0m {label}"
    return f"  \x1b[2m[{box}] {label}\x1b[0m"


def _entry_label(entry: WebCandidate) -> str:
    if entry.title:
        if entry.uploader and not entry.title.casefold().startswith(entry.uploader.casefold()):
            return f"{entry.uploader} - {entry.title}"
        return entry.title
    return entry.url.rstrip("/").rsplit("/", 1)[-1] or entry.url


def _printed_name(label: str) -> tuple[str, str]:
    line = label.strip().splitlines()[-1] if label.strip() else ""
    if "\t" not in line:
        return "", ""
    artist, title = line.split("\t", 1)
    return artist.strip(), title.strip()


def _track_from_entry(con, entry: WebCandidate) -> int:
    artist, title, mix = parse_title(entry.title)
    if not artist:
        artist = entry.uploader or "Unknown"
    if not title:
        title = entry.title or "Untitled"
    return add_track(
        con,
        artist=artist,
        title=title,
        mix=mix,
        duration_s=entry.duration_s,
    )


def _playlist_outcome(
    con,
    job_id: int,
    filed: int,
    skipped: list[str],
    not_acquired: list[str],
    failed: list[str],
) -> Outcome:
    notes = [f"filed {filed}"]
    if skipped:
        notes.append("skipped: " + ", ".join(skipped))
    if not_acquired:
        notes.append("not acquired: " + "; ".join(not_acquired))
    if failed:
        notes.append("failed: " + "; ".join(failed))
    message = "; ".join(notes)
    if failed:
        finish_job(con, job_id, "failed", message, retryable=1)
        return Outcome(job_id, "failed", message)
    if skipped or not_acquired:
        finish_job(con, job_id, "needs_review", message)
        return Outcome(job_id, "needs_review", message)
    finish_job(con, job_id, "acquired", message)
    return Outcome(job_id, "acquired", message)


def _move(key: str, cursor: int, checked: list[bool]) -> tuple[int, bool]:
    if key == " ":
        checked[cursor] = not checked[cursor]
    elif key == "A" and cursor:
        cursor -= 1
    elif key == "B" and cursor + 1 < len(checked):
        cursor += 1
    elif key in "\r\n":
        return cursor, True
    return cursor, False


def checklist(labels: list[str], confirm=None) -> list[int]:
    if confirm is not None:
        return list(confirm(labels))
    if not labels or not sys.stdin.isatty():
        return list(range(len(labels)))
    return _tty_checklist(labels)


def _tty_checklist(labels: list[str]) -> list[int]:
    import termios
    import tty

    checked = [True] * len(labels)
    cursor = 0
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        _paint(labels, checked, cursor, False)
        while True:
            key = sys.stdin.read(1)
            if key == "\x1b" and sys.stdin.read(1) == "[":
                key = sys.stdin.read(1)
            cursor, done = _move(key, cursor, checked)
            if done:
                break
            _paint(labels, checked, cursor, True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\n")
    return [index for index, on in enumerate(checked) if on]


def _paint(labels: list[str], checked: list[bool], cursor: int, redraw: bool) -> None:
    if redraw:
        sys.stdout.write(f"\x1b[{len(labels) + 1}A")
    for index, label in enumerate(labels):
        sys.stdout.write(f"\r\x1b[2K{_choice_line(_shown_label(label), checked[index], index == cursor)}\n")
    sys.stdout.write(f"\r\x1b[2K{_tone('space toggles, enter downloads', '2')}\n")
    sys.stdout.flush()


def _review_rows(con, cfg, paths, downloader, job_id: int, rows, skipped: list[str], confirm=None) -> Outcome:
    pending = []
    for track_id, label in rows:
        track = get_track(con, track_id)
        if filed_copy(con, track["artist"], track["title"], track["mix"] or ""):
            _say(_tone(f"already have  {label}", "32"))
            skipped.append(f"{label}: already have")
            continue
        pending.append(
            (
                track_id,
                label,
                track["artist"],
                track["title"],
                track["mix"] or "",
                float(track["duration_s"]),
            )
        )
    offers = []
    if pending:
        _say(_tone(f"searching {len(pending)}", "2"))
        queries = [search_query(artist, title) for _track_id, _label, artist, title, _mix, _duration in pending]
        soulseek = getattr(downloader, "soulseek", None)

        def scan(item):
            track_id, label, artist, title, mix, duration_s = item
            track = {"artist": artist, "title": title, "mix": mix, "duration_s": duration_s}
            found, error = _web_found(downloader, track)
            return track_id, label, track, found, error

        soul_future = None
        soul_pool = ThreadPoolExecutor(max_workers=1) if soulseek is not None else None
        try:
            if soul_pool is not None:
                soul_future = soul_pool.submit(_soul_sets, soulseek, queries)
            with ThreadPoolExecutor(max_workers=4) as pool:
                scanned_web = list(pool.map(scan, pending))
            soul_sets = soul_future.result() if soul_future is not None else []
        finally:
            if soul_pool is not None:
                soul_pool.shutdown()
        scanned = []
        for index, (track_id, label, track, found, error) in enumerate(scanned_web):
            if index < len(soul_sets):
                found = [*found, *soul_sets[index]]
            status, payload = _from_found(track, found, error)
            scanned.append((track_id, label, _query(track), status, payload))
        misses = []
        ready = []
        for track_id, label, query, status, payload in scanned:
            if status != "ready":
                misses.append((payload[0], label))
                continue
            ready.append((track_id, label, query, payload, _warnings(query, label, payload)))
        for message, label in misses:
            _say(_tone(f"{message}  {label}", "33"))
            skipped.append(f"{label}: {message}")
        for track_id, label, _query_row, _payload, (question, note) in ready:
            if not question and note:
                _say(_tone(f"note  {label}: {note}", "33"))
        for _track_id, label, query, payload, (question, _note) in ready:
            if question:
                _say(_tone(question.removesuffix(" download anyway?"), "33"))
        for track_id, label, query, payload, (question, note) in ready:
            if question and not ask(_tone(question, "33")):
                best = payload[0]
                message = f"length {_mmss(best.duration_s)} vs {_mmss(query.duration_s)}, declined"
                skipped.append(f"{label}: {message}")
                continue
            if question and note:
                _say(_tone(f"note  {label}: {note}", "33"))
            offers.append((track_id, label, payload))
    filed = 0
    failed: list[str] = []
    not_acquired: list[str] = []
    if offers:
        picked = set(checklist([label for _track_id, label, _hits in offers], confirm))
        for index, (track_id, label, hits) in enumerate(offers):
            if index not in picked:
                _say(f"removed {label}")
                skipped.append(f"{label}: removed")
                continue
            outcome = _save_hits(con, cfg, paths, downloader, track_id, hits)
            if outcome.status == "acquired":
                filed += 1
            elif outcome.status == "failed":
                failed.append(f"{label}: {outcome.message}")
            else:
                not_acquired.append(f"{label}: {outcome.message}")
    return _playlist_outcome(con, job_id, filed, skipped, not_acquired, failed)


def _run_spotify_playlist(
    con, cfg: DownloadConfig, paths: Paths, downloader, url: str, listing, confirm=None
) -> Outcome:
    job_id = add_job(con, None, "playlist")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    try:
        tracks, skipped = listing(url)
    except DownloadError as exc:
        return _hard_fail(con, cfg, job_id, str(exc))
    total = len(tracks) + len(skipped)
    _say(f"listed {total}")
    for label in skipped:
        _say(f"skipped {label}")
    rows = []
    for artist, title, duration_s in tracks:
        rows.append(
            (
                add_track(con, artist=artist, title=title, duration_s=duration_s, keeper=1),
                f"{artist} - {title}",
            )
        )
    return _review_rows(con, cfg, paths, downloader, job_id, rows, list(skipped), confirm)


def run_playlist(
    con,
    cfg: DownloadConfig,
    paths: Paths,
    downloader,
    url: str,
    listing=None,
    confirm=None,
) -> Outcome:
    if listing is None:

        def listing(url):
            return list_spotify_playlist(
                url,
                client_id=cfg.spotify_client_id,
                client_secret=cfg.spotify_client_secret,
            )
    if spotify_playlist_id(url) or spotify_album_id(url):
        return _run_spotify_playlist(con, cfg, paths, downloader, url, listing, confirm)
    job_id = add_job(con, None, "playlist")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    try:
        entries = downloader.list_playlist(url)
    except DownloadError as exc:
        return _hard_fail(con, cfg, job_id, str(exc))
    skipped: list[str] = []
    failed: list[str] = []
    filed = 0
    total = len(entries)
    _say(f"listed {total}")
    for index, entry in enumerate(entries, start=1):
        label = _entry_label(entry)
        if not entry.url:
            skipped.append(label)
            _say(f"{index}/{total} skipped {label}")
            continue
        _say(f"{index}/{total} downloading {label}")
        track_id = _track_from_entry(con, entry)
        child = add_job(con, track_id, "playlist")
        try:
            audio = downloader.fetch_track(entry.url, paths.staging / f"job-{child}")
        except DownloadError as exc:
            finish_job(con, child, "failed", str(exc), retryable=1)
            failed.append(f"{label}: {exc}")
            _say(f"{index}/{total} failed {label}: {exc}")
            continue
        if not entry.title:
            artist, title = _printed_name(getattr(downloader, "last_label", ""))
            if title:
                con.execute(
                    "UPDATE tracks SET artist = ?, title = ? WHERE id = ?",
                    (artist or "Unknown", title, track_id),
                )
                con.commit()
                label = f"{artist or 'Unknown'} - {title}"
        try:
            dest = file_staged(
                con,
                audio,
                track_id,
                via="web",
                quality="lossy",
                library=paths.library,
                job_id=child,
                cfg=cfg,
            )
        except RuntimeError as exc:
            finish_job(con, child, "failed", str(exc), retryable=1)
            failed.append(f"{label}: {exc}")
            _say(f"{index}/{total} failed {label}: {exc}")
            continue
        filed += 1
        _say(f"{index}/{total} filed {label} -> {dest}")
    notes = []
    if skipped:
        notes.append("skipped: " + ", ".join(skipped))
    if failed:
        notes.append("failed: " + "; ".join(failed))
    message = "; ".join(notes) if notes else f"filed {filed}"
    if failed:
        finish_job(con, job_id, "failed", message, retryable=1)
        return Outcome(job_id, "failed", message)
    if skipped:
        finish_job(con, job_id, "needs_review", message)
        return Outcome(job_id, "needs_review", message)
    finish_job(con, job_id, "acquired", message)
    return Outcome(job_id, "acquired", message)


def cut_set(
    con,
    cfg: DownloadConfig,
    paths: Paths,
    downloader,
    set_url: str,
    timeline: Path,
) -> Outcome:
    job_id = add_job(con, None, "set")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    try:
        audio = downloader.fetch_set_audio(set_url, paths.staging / f"set-{job_id}")
    except DownloadError as exc:
        return _hard_fail(con, cfg, job_id, str(exc))
    segments = parse_timeline(timeline.read_text())
    cuts = cut_segments(
        audio,
        segments,
        paths.staging / f"set-{job_id}-cuts",
        trim_s=cfg.trim_s,
        bitrate=cfg.bitrate,
    )
    problems: list[str] = []
    saved = 0
    for cut in cuts:
        if cut.path is None:
            problems.append(f"{cut.track_id}: {cut.error}")
            continue
        try:
            if cut.id_clip:
                dest = paths.library / "ids" / cut.path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(cut.path.read_bytes())
                con.execute(
                    """INSERT INTO inbox_files (path, matched_track_id, status, quality)
                       VALUES (?, ?, 'filed', 'lossy')""",
                    (str(dest), cut.track_id),
                )
                con.commit()
            else:
                file_staged(
                    con,
                    cut.path,
                    cut.track_id,
                    via="web",
                    quality="lossy",
                    library=paths.library,
                    cfg=cfg,
                )
        except (LookupError, RuntimeError) as exc:
            problems.append(f"{cut.track_id}: {exc}")
            continue
        saved += 1
    message = f"filed {saved}"
    status = "acquired" if saved else "failed"
    if problems:
        message = message + "; " + "; ".join(problems)
    finish_job(con, job_id, status, message)
    return Outcome(job_id, status, message)


def songs_for_video(downloader, url: str, comment_dir: Path):
    info = downloader.dump_info(url)
    songs = tracklist_from_info(info)
    if songs:
        return songs
    try:
        info = downloader.dump_info(url, comment_dir, comments=True)
    except DownloadError:
        return []
    return tracklist_from_comments(info)


def _grab_named_songs(con, cfg, paths, downloader, job_id: int, songs, confirm=None) -> Outcome:
    _say(f"listed {len(songs)}")
    rows = []
    for song in songs:
        rows.append(
            (
                add_track(
                    con,
                    artist=song.artist,
                    title=song.title,
                    mix=song.mix,
                    duration_s=0,
                ),
                f"{song.artist} - {song.title}",
            )
        )
    return _review_rows(con, cfg, paths, downloader, job_id, rows, [], confirm)


def split_set(con, cfg: DownloadConfig, paths: Paths, downloader, url: str, confirm=None) -> Outcome:
    job_id = add_job(con, None, "set")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    try:
        songs = songs_for_video(downloader, url, paths.staging / f"set-{job_id}-info")
    except DownloadError as exc:
        return _hard_fail(con, cfg, job_id, str(exc))
    if not songs:
        finish_job(con, job_id, "failed", "video has no tracklist")
        raise DownloadError("video has no tracklist")
    return _grab_named_songs(con, cfg, paths, downloader, job_id, songs, confirm)


def link_kind(url: str) -> str:
    if spotify_track_id(url):
        return "spotify-track"
    lowered = url.casefold()
    playlist = spotify_playlist_id(url) or spotify_album_id(url) or (
        "watch?" not in lowered
        and "youtu.be/" not in lowered
        and ("list=" in lowered or "/sets/" in lowered or "/playlist" in lowered)
    )
    return "playlist" if playlist else "video"


def download_link(con, cfg: DownloadConfig, paths: Paths, downloader, url: str, confirm=None) -> Outcome:
    kind = link_kind(url)
    if kind == "spotify-track":
        return grab_spotify(con, cfg, paths, downloader, url)
    if kind == "playlist":
        return run_playlist(con, cfg, paths, downloader, url, confirm=confirm)
    songs = songs_for_video(downloader, url, paths.staging / "link-info")
    if not songs:
        return run_playlist(con, cfg, paths, downloader, url, confirm=confirm)
    job_id = add_job(con, None, "set")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    return _grab_named_songs(con, cfg, paths, downloader, job_id, songs, confirm)


def make_downloader(cfg: DownloadConfig) -> YtDlpDownloader:
    downloader = YtDlpDownloader(cfg)
    if cfg.soulseek_username and cfg.soulseek_password:
        from djgrab.acquire.soulseek import SoulseekSource

        downloader.soulseek = SoulseekSource(cfg.soulseek_username, cfg.soulseek_password)
    return downloader
