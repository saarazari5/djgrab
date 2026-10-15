from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from djgrab.acquire.spotify import spotify_track_id
from djgrab.acquire.webdl import DownloadError, doctor_report
from djgrab.config import Paths, load_config
from djgrab.db import add_track, clear_db, connect
from djgrab.service import cut_set, grab, grab_spotify, keep, make_downloader, run_playlist, split_set


def _paths(data: Path | None) -> Paths:
    if data is not None:
        return Paths(data)
    env = os.environ.get("DJGRAB_DATA")
    if env:
        return Paths(Path(env))
    return Paths(Path("data"), songs=Path.home() / "djgrab")


def _exit_for(status: str) -> int:
    return 1 if status == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path)
    common.add_argument("--data", type=Path)

    parser = argparse.ArgumentParser(prog="djgrab")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", parents=[common])

    add = sub.add_parser("add", parents=[common])
    add.add_argument("--artist", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--mix", default="")
    add.add_argument("--duration", type=float, required=True)
    add.add_argument("--free-url", default="")
    add.add_argument("--genre", default="")

    keep_cmd = sub.add_parser("keep", parents=[common])
    keep_cmd.add_argument("track_id", type=int)

    grab_cmd = sub.add_parser("grab", parents=[common])
    grab_cmd.add_argument("ident")

    playlist = sub.add_parser("playlist", parents=[common])
    playlist.add_argument("url")

    cut = sub.add_parser("cut", parents=[common])
    cut.add_argument("set_url")
    cut.add_argument("timeline", type=Path)

    set_cmd = sub.add_parser("set", parents=[common])
    set_cmd.add_argument("url")

    sub.add_parser("clear", parents=[common])

    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        text, code = doctor_report()
        print(text)
        return code

    paths = _paths(args.data)
    if args.cmd == "clear":
        clear_db(paths.db)
        print(f"deleted {paths.db}")
        return 0

    cfg = load_config(args.config)
    con = connect(paths.db)
    downloader = make_downloader(cfg)
    try:
        if args.cmd == "add":
            track_id = add_track(
                con,
                artist=args.artist,
                title=args.title,
                mix=args.mix,
                duration_s=args.duration,
                free_url=args.free_url,
                genre=args.genre,
            )
            print(track_id)
            return 0
        if args.cmd == "keep":
            outcome = keep(con, cfg, paths, downloader, args.track_id)
        elif args.cmd == "grab":
            if spotify_track_id(args.ident):
                outcome = grab_spotify(con, cfg, paths, downloader, args.ident)
            else:
                outcome = grab(con, cfg, paths, downloader, int(args.ident))
        elif args.cmd == "playlist":
            outcome = run_playlist(con, cfg, paths, downloader, args.url)
        elif args.cmd == "set":
            outcome = split_set(con, cfg, paths, downloader, args.url)
        else:
            outcome = cut_set(con, cfg, paths, downloader, args.set_url, args.timeline)
    except (LookupError, DownloadError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError:
        print("grab expects a track id or a spotify track url", file=sys.stderr)
        return 2
    print(f"{outcome.status}: {outcome.message}")
    return _exit_for(outcome.status)
