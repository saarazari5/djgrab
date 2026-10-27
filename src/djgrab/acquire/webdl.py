from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from djgrab.config import DownloadConfig

SEARCH_TIMEOUT = 30
FETCH_TIMEOUT = 180
Runner = Callable[[list[str], float], str]


_AUDIO = {".m4a", ".mp3", ".flac", ".wav", ".ogg", ".opus", ".aac", ".aiff", ".aif", ".webm"}


def _audio_file(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.suffix.casefold() in _AUDIO:
            return path
    return None


class DownloadError(RuntimeError):
    pass


def permanent_error(exc: DownloadError) -> bool:
    text = str(exc).casefold()
    return "drm" in text or "unavailable" in text or "private" in text


@dataclass
class WebCandidate:
    source: str
    url: str
    title: str
    uploader: str
    duration_s: int
    lossless: bool = False


def entry_url(obj: dict) -> str:
    for key in ("webpage_url", "original_url", "url"):
        value = obj.get(key) or ""
        if value.startswith("http://") or value.startswith("https://"):
            return value
    return ""


def parse_dump(stdout: str, source: str) -> list[WebCandidate]:
    found: list[WebCandidate] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        obj = json.loads(line)
        duration = obj.get("duration") or 0
        found.append(
            WebCandidate(
                source=source,
                url=entry_url(obj),
                title=obj.get("title") or "",
                uploader=obj.get("uploader") or obj.get("channel") or "",
                duration_s=int(round(float(duration))),
            )
        )
    return found


def default_runner(args: list[str], timeout: float) -> str:
    try:
        proc = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise DownloadError("yt-dlp is not installed; run djgrab doctor") from exc
    except subprocess.TimeoutExpired as exc:
        raise DownloadError("yt-dlp timed out") from exc
    if proc.returncode != 0:
        lines = [line.strip() for line in (proc.stderr or "").splitlines() if line.strip()]
        detail = lines[-1] if lines else (proc.stdout or "").strip()
        raise DownloadError(detail or f"yt-dlp exited {proc.returncode}")
    return proc.stdout


class YtDlpDownloader:
    """One yt-dlp process at a time. Three tries, then DownloadError."""

    def __init__(
        self,
        cfg: DownloadConfig,
        runner: Runner = default_runner,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.cfg = cfg
        self._runner = runner
        self._sleep = sleeper
        self._lock = threading.Lock()
        self.last_label = ""

    def _attempt(self, args: list[str], timeout: float) -> str:
        delay = 0.5
        last: DownloadError | None = None
        for attempt in range(3):
            try:
                return self._runner(args, timeout)
            except DownloadError as exc:
                last = exc
                if permanent_error(exc):
                    raise
            if attempt < 2:
                self._sleep(delay)
                delay *= 2
        assert last is not None
        raise last

    def _try(self, args: list[str], timeout: float) -> str:
        with self._lock:
            return self._attempt(args, timeout)

    def _search_source(self, source: str, query: str, limit: int) -> list[WebCandidate]:
        prefix = "ytsearch" if source == "youtube" else "scsearch"
        stdout = self._attempt(
            ["yt-dlp", f"{prefix}{limit}:{query}", "--flat-playlist", "--dump-json", "--no-warnings"],
            SEARCH_TIMEOUT,
        )
        return parse_dump(stdout, source)

    def search_meta(self, query: str, limit: int = 5) -> list[WebCandidate]:
        sources = list(self.cfg.sources)
        if len(sources) <= 1:
            return self._search_source(sources[0], query, limit) if sources else []
        found: list[WebCandidate] = []
        errors: list[DownloadError] = []
        with ThreadPoolExecutor(max_workers=len(sources)) as pool:
            futures = [pool.submit(self._search_source, source, query, limit) for source in sources]
            for future in futures:
                try:
                    found.extend(future.result())
                except DownloadError as exc:
                    errors.append(exc)
        if not found and errors:
            raise errors[0]
        return found

    def _download(self, args: list[str], folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        before = {path for path in folder.iterdir()}
        self.last_label = self._try(args, FETCH_TIMEOUT).strip()
        new = [path for path in folder.iterdir() if path not in before and path.is_file()]
        audio = _audio_file(new)
        if audio is None:
            raise DownloadError("yt-dlp wrote no file")
        return audio

    def dump_info(self, url: str, dest_dir: Path | None = None, comments: bool = False) -> dict:
        args = ["yt-dlp", "--dump-json", "--skip-download", "--no-warnings", "--no-playlist"]
        if comments:
            folder = dest_dir or Path(".")
            folder.mkdir(parents=True, exist_ok=True)
            args.extend(
                [
                    "--write-comments",
                    "--extractor-args",
                    "youtube:max_comments=100",
                    "-o",
                    str(folder / "info.%(ext)s"),
                ]
            )
        args.append(url)
        stdout = self._attempt(args, 60 if comments else SEARCH_TIMEOUT)
        text = stdout.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            line = next((item for item in reversed(text.splitlines()) if item.startswith("{")), "")
            if not line:
                raise DownloadError("yt-dlp returned no video info")
            data = json.loads(line)
        if isinstance(data, list):
            data = data[0] if data else {}
        return data

    def fetch_track(self, url: str, dest_dir: Path) -> Path:
        return self._download(
            [
                "yt-dlp",
                "-f",
                "bestaudio",
                "-x",
                "--audio-format",
                self.cfg.format,
                "--audio-quality",
                self.cfg.bitrate,
                "--no-playlist",
                "--no-warnings",
                "--concurrent-fragments",
                "4",
                "--write-thumbnail",
                "--convert-thumbnails",
                "jpg",
                "--print",
                "after_move:%(uploader)s\t%(title)s",
                "-o",
                str(dest_dir / "audio.%(ext)s"),
                url,
            ],
            dest_dir,
        )

    def fetch_set_audio(self, url: str, dest: Path) -> Path:
        folder = dest if dest.suffix == "" else dest.parent
        template = str(folder / "set.%(ext)s")
        return self._download(
            ["yt-dlp", "-f", "bestaudio", "--no-playlist", "--no-warnings", "-o", template, url],
            folder,
        )

    def list_playlist(self, url: str) -> list[WebCandidate]:
        source = "soundcloud" if "soundcloud" in url else "youtube"
        stdout = self._try(
            ["yt-dlp", "--flat-playlist", "--dump-json", "--no-warnings", url],
            SEARCH_TIMEOUT,
        )
        return parse_dump(stdout, source)


def doctor_report(which: Callable[[str], str | None] = shutil.which) -> tuple[str, int]:
    hints = {
        "yt-dlp": "install yt-dlp (https://github.com/yt-dlp/yt-dlp#installation)",
        "ffmpeg": "install ffmpeg",
        "flac": "install flac",
        "fpcalc": "install chromaprint (fpcalc)",
    }
    lines: list[str] = []
    missing_required = False
    for name in ("yt-dlp", "ffmpeg", "flac", "fpcalc"):
        found = which(name)
        if found:
            lines.append(f"{name}: ok ({found})")
            continue
        role = "required" if name in ("yt-dlp", "ffmpeg") else "optional"
        lines.append(f"{name}: missing ({role}); {hints[name]}")
        if role == "required":
            missing_required = True
    return "\n".join(lines), 1 if missing_required else 0
