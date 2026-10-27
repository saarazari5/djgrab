import sys

from djgrab.acquire.webdl import DownloadError, YtDlpDownloader, default_runner, doctor_report
from djgrab.config import DownloadConfig


def test_a_successful_download_does_not_print_yt_dlp_errors(capsys):
    out = default_runner(
        [sys.executable, "-c", "import sys; sys.stderr.write('ERROR: HTTP Error 403: Forbidden\\n'); print('ok')"],
        10,
    )
    assert out.strip() == "ok"
    assert "403" not in capsys.readouterr().err


def test_a_failed_download_keeps_the_yt_dlp_error():
    try:
        default_runner(
            [sys.executable, "-c", "import sys; sys.stderr.write('ERROR: HTTP Error 403: Forbidden\\n'); raise SystemExit(1)"],
            10,
        )
    except DownloadError as exc:
        assert "403" in str(exc)
    else:
        raise AssertionError("expected DownloadError")


def test_retries_then_returns_dump():
    calls = {"n": 0}

    def runner(args, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise DownloadError("nope")
        return '{"title": "Nova Ridge - Solar Drift", "webpage_url": "https://example.test/solar", "duration": 180}\n'

    downloader = YtDlpDownloader(
        DownloadConfig(sources=("youtube",)),
        runner=runner,
        sleeper=lambda _delay: None,
    )
    found = downloader.search_meta("Nova Ridge Solar Drift", 5)
    assert calls["n"] == 3
    assert found[0].url == "https://example.test/solar"


def test_permanent_error_is_not_retried():
    calls = {"n": 0}

    def runner(args, timeout):
        calls["n"] += 1
        raise DownloadError("This video is DRM protected")

    downloader = YtDlpDownloader(
        DownloadConfig(sources=("youtube",)),
        runner=runner,
        sleeper=lambda _delay: None,
    )
    try:
        downloader.search_meta("Nova Ridge", 5)
    except DownloadError as exc:
        assert "DRM" in str(exc)
    else:
        raise AssertionError("expected DownloadError")
    assert calls["n"] == 1


def test_search_queries_each_source():
    seen: list[str] = []

    def runner(args, timeout):
        seen.append(args)
        return '{"title": "Nova Ridge - Solar Drift", "webpage_url": "https://example.test/a", "duration": 180}\n'

    downloader = YtDlpDownloader(DownloadConfig(), runner=runner, sleeper=lambda _delay: None)
    found = downloader.search_meta("Nova Ridge", 5)
    assert {args[1] for args in seen} == {"ytsearch5:Nova Ridge", "scsearch5:Nova Ridge"}
    assert all("--flat-playlist" in args for args in seen)
    assert len(found) == 2


def test_youtube_and_soundcloud_search_together():
    import threading

    gate = threading.Barrier(2)

    def runner(args, timeout):
        gate.wait(timeout=1)
        return '{"title": "Nova Ridge - Solar Drift", "webpage_url": "https://example.test/a", "duration": 180}\n'

    downloader = YtDlpDownloader(DownloadConfig(), runner=runner, sleeper=lambda _delay: None)
    found = downloader.search_meta("Nova Ridge", 5)
    assert len(found) == 2


def test_fetch_track_keeps_the_audio_when_a_thumbnail_is_written(tmp_path):
    seen: list[str] = []

    def runner(args, timeout):
        seen.extend(args)
        (tmp_path / "audio.m4a").write_bytes(b"m4a")
        (tmp_path / "audio.jpg").write_bytes(b"jpg")
        return "DEKEL\tLuna\n"

    downloader = YtDlpDownloader(DownloadConfig(), runner=runner, sleeper=lambda _delay: None)
    path = downloader.fetch_track("https://example.test/luna", tmp_path)
    assert path.name == "audio.m4a"
    assert "--write-thumbnail" in seen
    assert "jpg" in seen


def test_doctor_requires_yt_dlp_and_reports_optional():
    def which(name):
        if name == "yt-dlp":
            return None
        if name == "flac":
            return None
        return f"/bin/{name}"

    text, code = doctor_report(which)
    assert code == 1
    assert "yt-dlp: missing (required)" in text
    assert "install yt-dlp" in text
    assert "flac: missing (optional)" in text

    text, code = doctor_report(lambda name: f"/bin/{name}")
    assert code == 0
    assert "ffmpeg: ok" in text
