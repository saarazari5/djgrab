import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from djgrab.media.cut import Segment, cut_segments


def _tone(seconds: float, hz: float, rate: int) -> bytes:
    samples = np.arange(int(seconds * rate)) / rate
    pcm = (np.sin(2 * np.pi * hz * samples) * 32767).astype(np.int16)
    return pcm.tobytes()


def _write_set(path: Path) -> None:
    rate = 22050
    pcm = _tone(64, 440, rate) + _tone(64, 550, rate) + _tone(10, 660, rate)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)


def _duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def _dominant_hz(path: Path) -> float:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "8000", "pipe:1"],
        check=True,
        capture_output=True,
    )
    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    rate = 8000
    mid = len(samples) // 2
    window = samples[max(0, mid - rate) : mid + rate]
    spectrum = np.abs(np.fft.rfft(window))
    spectrum[0] = 0
    return float(np.fft.rfftfreq(len(window), 1 / rate)[int(spectrum.argmax())])


def test_golden_set_cuts_tones(tmp_path):
    audio = tmp_path / "set.wav"
    _write_set(audio)
    results = cut_segments(
        audio,
        [
            Segment(1, 0, 64),
            Segment(2, 64, 128),
            Segment(3, 128, 138),
            Segment(1, 0, 12, id_clip=True),
        ],
        tmp_path / "cuts",
        trim_s=2,
        bitrate="128k",
    )
    kept = [item for item in results if item.path is not None]
    skipped = [item for item in results if item.error == "under 60s"]
    assert len(kept) == 3
    assert len(skipped) == 1
    by_name = {item.path.name: item.path for item in kept}
    assert _duration(by_name["1.m4a"]) == pytest.approx(60, abs=1.5)
    assert _duration(by_name["2.m4a"]) == pytest.approx(60, abs=1.5)
    assert _duration(by_name["1.id.m4a"]) == pytest.approx(12, abs=1.5)
    assert _dominant_hz(by_name["1.m4a"]) == pytest.approx(440, abs=15)
    assert _dominant_hz(by_name["2.m4a"]) == pytest.approx(550, abs=15)
    assert _dominant_hz(by_name["1.id.m4a"]) == pytest.approx(440, abs=15)
