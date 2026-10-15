from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from djgrab.acquire.spotify import list_spotify_playlist, lookup_spotify, spotify_playlist_id
from djgrab.acquire.webdl import DownloadError, WebCandidate, YtDlpDownloader, permanent_error
from djgrab.config import DownloadConfig, Paths
from djgrab.db import add_job, add_track, finish_job, get_track
from djgrab.identity.match import TrackQuery, choose
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
    query = search_query(track["artist"], track["title"])
    _say(f"searching {query}")
    candidates: list[WebCandidate] = []
    search_error: DownloadError | None = None
    soulseek = getattr(downloader, "soulseek", None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        meta = pool.submit(downloader.search_meta, query, 5)
        soul = pool.submit(soulseek.search, query) if soulseek is not None else None
        try:
            candidates.extend(meta.result())
        except DownloadError as exc:
            search_error = exc
        if soul is not None:
            try:
                candidates.extend(soul.result())
            except DownloadError as exc:
                search_error = search_error or exc
    if not candidates:
        return _hard_fail(con, cfg, job_id, str(search_error or "no match"))
    kind, hits = choose(_query(track), candidates)
    if kind == "ambiguous":
        payload = json.dumps([asdict(hit) for hit in hits])
        finish_job(con, job_id, "needs_review", "ambiguous match", payload)
        return Outcome(job_id, "needs_review", "ambiguous match")
    if kind == "none":
        payload = json.dumps([asdict(item) for item in candidates])
        if cfg.fallback_to_buylist:
            finish_job(con, job_id, "buylist", "no match", payload)
            return Outcome(job_id, "buylist", "no match")
        finish_job(con, job_id, "needs_review", "no match", payload)
        return Outcome(job_id, "needs_review", "no match")
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
            if permanent_error(exc):
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


def _run_spotify_playlist(con, cfg: DownloadConfig, paths: Paths, downloader, url: str, listing) -> Outcome:
    job_id = add_job(con, None, "playlist")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    try:
        tracks, skipped = listing(url)
    except DownloadError as exc:
        return _hard_fail(con, cfg, job_id, str(exc))
    failed: list[str] = []
    not_acquired: list[str] = []
    filed = 0
    total = len(tracks) + len(skipped)
    _say(f"listed {total}")
    index = 0
    for label in skipped:
        index += 1
        _say(f"{index}/{total} skipped {label}")
    for artist, title, duration_s in tracks:
        index += 1
        label = f"{artist} - {title}"
        track_id = add_track(
            con,
            artist=artist,
            title=title,
            duration_s=duration_s,
            keeper=1,
        )
        _say(f"{index}/{total} {label}")
        outcome = grab(con, cfg, paths, downloader, track_id)
        if outcome.status == "acquired":
            filed += 1
            continue
        note = f"{label}: {outcome.message}"
        if outcome.status == "failed":
            failed.append(note)
        else:
            not_acquired.append(note)
        _say(f"{index}/{total} {outcome.status} {label}: {outcome.message}")
    return _playlist_outcome(con, job_id, filed, skipped, not_acquired, failed)


def run_playlist(
    con,
    cfg: DownloadConfig,
    paths: Paths,
    downloader,
    url: str,
    listing=list_spotify_playlist,
) -> Outcome:
    if spotify_playlist_id(url):
        return _run_spotify_playlist(con, cfg, paths, downloader, url, listing)
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


def split_set(con, cfg: DownloadConfig, paths: Paths, downloader, url: str) -> Outcome:
    job_id = add_job(con, None, "set")
    blocked = _enabled_block(con, cfg, job_id)
    if blocked:
        return blocked
    try:
        info = downloader.dump_info(url)
        songs = tracklist_from_info(info)
        if not songs:
            info = downloader.dump_info(url, paths.staging / f"set-{job_id}-info", comments=True)
            songs = tracklist_from_comments(info)
    except DownloadError as exc:
        return _hard_fail(con, cfg, job_id, str(exc))
    if not songs:
        finish_job(con, job_id, "failed", "video has no tracklist")
        raise DownloadError("video has no tracklist")
    failed: list[str] = []
    not_acquired: list[str] = []
    filed = 0
    total = len(songs)
    _say(f"listed {total}")
    for index, song in enumerate(songs, start=1):
        label = f"{song.artist} - {song.title}"
        track_id = add_track(
            con,
            artist=song.artist,
            title=song.title,
            mix=song.mix,
            duration_s=0,
        )
        _say(f"{index}/{total} {label}")
        outcome = grab(con, cfg, paths, downloader, track_id)
        if outcome.status == "acquired":
            filed += 1
            continue
        note = f"{label}: {outcome.message}"
        if outcome.status == "failed":
            failed.append(note)
        else:
            not_acquired.append(note)
        _say(f"{index}/{total} {outcome.status} {label}: {outcome.message}")
    return _playlist_outcome(con, job_id, filed, [], not_acquired, failed)


def make_downloader(cfg: DownloadConfig) -> YtDlpDownloader:
    downloader = YtDlpDownloader(cfg)
    if cfg.soulseek_username and cfg.soulseek_password:
        from djgrab.acquire.soulseek import SoulseekSource

        downloader.soulseek = SoulseekSource(cfg.soulseek_username, cfg.soulseek_password)
    return downloader
