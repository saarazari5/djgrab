from pathlib import Path

from djgrab.acquire.webdl import DownloadError, WebCandidate, parse_dump
from djgrab.db import add_spend, add_track, get_track
from djgrab.service import grab, keep
from tests.support import FakeDL, cfg, db, paths, write_wav
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "solar_drift.json"


class _Soul:
    def __init__(self, candidates):
        self.candidates = candidates
        self.fetches: list[str] = []

    def search(self, query: str):
        return list(self.candidates)

    def fetch(self, url: str, dest_dir: Path) -> Path:
        self.fetches.append(url)
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / "audio.wav"
        write_wav(path, 0.2, 440)
        return path


def _track(con, **kwargs):
    values = dict(artist="Nova Ridge", title="Solar Drift", mix="Original Mix", duration_s=180)
    values.update(kwargs)
    return add_track(con, **values)


def test_grab_files_best_match(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    right = parse_dump(FIXTURE.read_text(), "youtube")[0]
    downloader = FakeDL(candidates=[right])
    outcome = grab(con, cfg(), paths(tmp_path), downloader, track_id)
    assert outcome.status == "acquired"
    assert downloader.fetches == ["https://example.test/solar"]
    track = get_track(con, track_id)
    assert track["acquired_via"] == "web"
    assert track["quality"] == "lossy"


def test_grab_by_job_id(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    from djgrab.db import add_job

    job_id = add_job(con, track_id, "single")
    right = parse_dump(FIXTURE.read_text(), "youtube")[0]
    outcome = grab(con, cfg(), paths(tmp_path), FakeDL(candidates=[right]), job_id)
    assert outcome.status == "acquired"


def test_ambiguous_goes_to_review(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    found = parse_dump(FIXTURE.read_text(), "youtube")
    downloader = FakeDL(candidates=[found[0], found[2]])
    outcome = grab(con, cfg(), paths(tmp_path), downloader, track_id)
    assert outcome.status == "acquired"
    assert downloader.fetches == ["https://example.test/solar"]
    assert downloader.searches == ["Nova Ridge Solar Drift"]


def test_free_link_skips_search(tmp_path):
    con = db(tmp_path)
    track_id = _track(con, free_url="https://example.test/free")
    downloader = FakeDL()
    outcome = grab(con, cfg(), paths(tmp_path), downloader, track_id)
    assert outcome.status == "acquired"
    assert downloader.searches == []
    assert get_track(con, track_id)["acquired_via"] == "free"


def test_download_runs_after_earlier_spends(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    for _ in range(20):
        add_spend(con)
    right = parse_dump(FIXTURE.read_text(), "youtube")[0]
    downloader = FakeDL(candidates=[right])
    outcome = grab(con, cfg(), paths(tmp_path), downloader, track_id)
    assert outcome.status == "acquired"
    assert downloader.fetches == ["https://example.test/solar"]


def test_drm_falls_back_to_soulseek(tmp_path):
    con = db(tmp_path)
    track_id = _track(con, artist="Michael Jackson", title="Bad - 2012 Remaster", mix="", duration_s=247)
    youtube = WebCandidate(
        "youtube",
        "https://www.youtube.com/watch?v=bad",
        "Bad (2012 Remaster)",
        "Michael Jackson",
        247,
    )
    soul = WebCandidate(
        "soulseek",
        "peer\x1fBad.mp3",
        "Michael Jackson - Bad",
        "peer",
        247,
    )
    downloader = FakeDL(candidates=[youtube])

    def fail_drm(url, dest_dir):
        raise DownloadError("This video is DRM protected")

    downloader.fetch_track = fail_drm
    downloader.soulseek = _Soul([soul])
    outcome = grab(con, cfg(), paths(tmp_path), downloader, track_id)
    assert outcome.status == "acquired"
    assert downloader.soulseek.fetches == ["peer\x1fBad.mp3"]


def test_stalled_soulseek_tries_the_next_hit(tmp_path):
    con = db(tmp_path)
    track_id = _track(con, artist="Freedom Fighters", title="Better Future", mix="", duration_s=0)
    youtube = WebCandidate(
        "youtube",
        "https://www.youtube.com/watch?v=better",
        "Freedom Fighters & Sphera - Better Future",
        "Freedom Fighters",
        0,
    )
    soul = WebCandidate(
        "soulseek",
        "peer\x1fBetter Future.flac",
        "Sphera, Freedom Fighters - Better Future (Original Mix).flac",
        "peer",
        0,
        lossless=True,
    )
    downloader = FakeDL(candidates=[youtube])

    class _Stalled(_Soul):
        def fetch(self, url: str, dest_dir: Path) -> Path:
            self.fetches.append(url)
            raise DownloadError("soulseek peer did not start")

    downloader.soulseek = _Stalled([soul])
    outcome = grab(con, cfg(), paths(tmp_path), downloader, track_id)
    assert outcome.status == "acquired"
    assert downloader.soulseek.fetches == ["peer\x1fBetter Future.flac"]
    assert downloader.fetches == ["https://www.youtube.com/watch?v=better"]


def test_four_soulseek_queries_wait_once(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import djgrab.acquire.soulseek as soulseek_mod
    from djgrab.acquire.soulseek import SoulseekSource

    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)

    class Searches:
        async def search(self, query):
            return SimpleNamespace(results=[])

    monkeypatch.setattr(soulseek_mod.asyncio, "sleep", sleep)
    source = SoulseekSource("u", "p")
    source._client = SimpleNamespace(searches=Searches())
    asyncio.run(source._search_many(["a", "b", "c", "d"]))
    asyncio.run(source._search_many(["e"]))
    assert sleeps == [8, 8]


def test_soulseek_gives_up_when_the_peer_sends_nothing():
    from djgrab.acquire.soulseek import _idle_error

    idle = 0
    for _ in range(14):
        idle, reason = _idle_error("QUEUED", False, idle)
        assert reason == ""
    _idle, reason = _idle_error("QUEUED", False, idle)
    assert reason == "soulseek peer did not start"
    assert _idle_error("DOWNLOADING", True, 14) == (0, "")


def test_soulseek_result_keeps_the_file_name():
    from types import SimpleNamespace

    from djgrab.acquire.soulseek import candidates_from_results

    item = SimpleNamespace(
        filename=r"Music\Darco - We We We.flac",
        attributes=[SimpleNamespace(key=1, value=180)],
    )
    result = SimpleNamespace(username="peer", shared_items=[item])
    found = candidates_from_results([result])
    assert found[0].lossless is True
    assert found[0].duration_s == 180
    assert found[0].title == "Darco - We We We.flac"
    assert found[0].url == "peer\x1fMusic\\Darco - We We We.flac"


def test_drm_without_soulseek_is_buy_list(tmp_path):
    con = db(tmp_path)
    track_id = _track(con, artist="Michael Jackson", title="Bad", mix="", duration_s=247)
    youtube = WebCandidate("youtube", "https://www.youtube.com/watch?v=bad", "Bad", "Michael Jackson", 247)
    downloader = FakeDL(candidates=[youtube])

    def fail_drm(url, dest_dir):
        raise DownloadError("This video is DRM protected")

    downloader.fetch_track = fail_drm
    outcome = grab(con, cfg(), paths(tmp_path), downloader, track_id)
    assert outcome.status == "buylist"
    assert "DRM" in outcome.message


def test_disabled_names_enabled(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    downloader = FakeDL()
    outcome = grab(con, cfg(enabled=False), paths(tmp_path), downloader, track_id)
    assert outcome.status == "failed"
    assert "enabled" in outcome.message
    assert downloader.searches == []


def test_hard_failure_falls_back_to_buy_list(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    outcome = grab(con, cfg(), paths(tmp_path), FakeDL(fail_search=True), track_id)
    assert outcome.status == "buylist"
    row = con.execute("SELECT retryable FROM jobs WHERE id = ?", (outcome.job_id,)).fetchone()
    assert row["retryable"] == 1


def test_keep_downloads_when_auto(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    right = parse_dump(FIXTURE.read_text(), "youtube")[0]
    outcome = keep(con, cfg(), paths(tmp_path), FakeDL(candidates=[right]), track_id)
    assert outcome.status == "acquired"
    assert get_track(con, track_id)["keeper"] == 1


def test_keep_on_demand_does_not_download(tmp_path):
    con = db(tmp_path)
    track_id = _track(con)
    downloader = FakeDL()
    outcome = keep(con, cfg(singles="on_demand"), paths(tmp_path), downloader, track_id)
    assert outcome.status == "keeper"
    assert downloader.searches == []
    assert get_track(con, track_id)["keeper"] == 1


def test_grab_skips_a_song_already_filed(tmp_path):
    con = db(tmp_path)
    first = _track(con)
    right = parse_dump(FIXTURE.read_text(), "youtube")[0]
    downloader = FakeDL(candidates=[right])
    library = paths(tmp_path)
    assert grab(con, cfg(), library, downloader, first).status == "acquired"
    downloader.searches.clear()
    downloader.fetches.clear()
    second = _track(con)
    outcome = grab(con, cfg(), library, downloader, second)
    assert outcome.status == "acquired"
    assert outcome.message.startswith("already have ")
    assert downloader.searches == []
    assert downloader.fetches == []
    other = _track(con, title="Night Bus")
    assert grab(con, cfg(), library, downloader, other).status == "buylist"
    assert downloader.searches == ["Nova Ridge Night Bus"]
