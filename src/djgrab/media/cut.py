from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    track_id: int
    start_s: float
    end_s: float
    id_clip: bool = False


@dataclass
class CutResult:
    track_id: int
    path: Path | None
    id_clip: bool
    error: str = ""


def parse_timeline(text: str) -> list[Segment]:
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("timeline must be a list")
    segments: list[Segment] = []
    for item in data:
        start = float(item["start_s"])
        segments.append(
            Segment(
                track_id=int(item["track_id"]),
                start_s=start,
                end_s=float(item.get("end_s", start + 12)),
                id_clip=bool(item.get("id_clip", False)),
            )
        )
    return segments


def _ffmpeg(args: list[str]) -> None:
    try:
        proc = subprocess.run(args, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed; run djgrab doctor") from exc
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg failed while cutting")


def cut_segments(
    audio: Path,
    segments: list[Segment],
    dest_dir: Path,
    *,
    trim_s: int,
    bitrate: str,
) -> list[CutResult]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[CutResult] = []
    for segment in segments:
        if segment.id_clip:
            path = dest_dir / f"{segment.track_id}.id.m4a"
            try:
                _ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        str(segment.start_s),
                        "-t",
                        "12",
                        "-i",
                        str(audio),
                        "-c:a",
                        "aac",
                        "-b:a",
                        bitrate,
                        str(path),
                    ]
                )
            except RuntimeError as exc:
                results.append(CutResult(segment.track_id, None, True, str(exc)))
                continue
            results.append(CutResult(segment.track_id, path, True))
            continue
        start = segment.start_s + trim_s
        end = segment.end_s - trim_s
        if end - start < 60:
            results.append(CutResult(segment.track_id, None, False, "under 60s"))
            continue
        path = dest_dir / f"{segment.track_id}.m4a"
        try:
            _ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(start),
                    "-to",
                    str(end),
                    "-i",
                    str(audio),
                    "-c:a",
                    "aac",
                    "-b:a",
                    bitrate,
                    str(path),
                ]
            )
        except RuntimeError as exc:
            results.append(CutResult(segment.track_id, None, False, str(exc)))
            continue
        results.append(CutResult(segment.track_id, path, False))
    return results
