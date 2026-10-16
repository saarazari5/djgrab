from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from djgrab.acquire.webdl import DownloadError, doctor_report
from djgrab.config import Paths, config_path, load_config, set_config
from djgrab.db import clear_db, connect
from djgrab.service import download_link, make_downloader


def _import_legacy_database(root: Path) -> None:
    # shortcut: one copy from ./data, remove when that project database is gone
    marker = root / ".imported"
    target = root / "djgrab.sqlite"
    legacy = Path("data") / "djgrab.sqlite"
    if marker.exists() or target.exists() or not legacy.is_file():
        return
    root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, target)
    for suffix in ("-wal", "-shm"):
        extra = Path(f"{legacy}{suffix}")
        if extra.is_file():
            shutil.copy2(extra, Path(f"{target}{suffix}"))
    marker.write_text("data/djgrab.sqlite\n")


def _is_link(text: str) -> bool:
    lowered = text.strip().casefold()
    return lowered.startswith(("http://", "https://", "spotify:"))


def _paths(data: Path | None) -> Paths:
    if data is not None:
        return Paths(data)
    env = os.environ.get("DJGRAB_DATA")
    if env:
        return Paths(Path(env))
    return Paths(Path.home() / ".djgrab", songs=Path.home() / "djgrab")


def _exit_for(status: str) -> int:
    return 1 if status == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="djgrab", description="Download a song from a link into ~/djgrab")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("link", nargs="+")
    args = parser.parse_args(argv)

    if args.link == ["doctor"]:
        text, code = doctor_report()
        print(text)
        return code

    if args.link[0] == "config":
        if len(args.link) != 3:
            print("usage: djgrab config <section.key> <value>", file=sys.stderr)
            return 2
        path = args.config or config_path() or Path.home() / ".djgrab" / "djgrab.toml"
        try:
            set_config(path, args.link[1], args.link[2])
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"set {args.link[1]} in {path}")
        return 0

    paths = _paths(args.data)
    if args.link == ["clear"]:
        clear_db(paths.db)
        print(f"deleted {paths.db}")
        return 0

    refused = [url for url in args.link if not _is_link(url)]
    if refused:
        print(f"not a link: {refused[0]}", file=sys.stderr)
        return 2

    if args.data is None and not os.environ.get("DJGRAB_DATA"):
        _import_legacy_database(paths.root)
    cfg = load_config(args.config)
    con = connect(paths.db)
    downloader = make_downloader(cfg)
    worst = 0
    for url in args.link:
        try:
            outcome = download_link(con, cfg, paths, downloader, url)
        except DownloadError as exc:
            print(str(exc), file=sys.stderr)
            worst = 2
            continue
        print(f"{outcome.status}: {outcome.message}")
        worst = max(worst, _exit_for(outcome.status))
    return worst
