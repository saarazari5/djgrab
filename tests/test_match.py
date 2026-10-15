from pathlib import Path

from djgrab.acquire.webdl import WebCandidate, parse_dump
from djgrab.identity.match import TrackQuery, choose
from djgrab.identity.normalize import search_query

FIXTURE = Path(__file__).parent / "fixtures" / "solar_drift.json"
TRACK = TrackQuery("Nova Ridge", "Solar Drift", "Original Mix", 180)


def candidates():
    return parse_dump(FIXTURE.read_text(), "youtube")


def test_right_version():
    kind, hits = choose(TRACK, [candidates()[0]])
    assert kind == "one"
    assert hits[0].url == "https://example.test/solar"


def test_wrong_version():
    kind, hits = choose(TRACK, [candidates()[1]])
    assert kind == "none"
    assert hits == []


def test_ambiguous():
    kind, hits = choose(TRACK, [candidates()[0], candidates()[2]])
    assert kind == "one"
    assert hits[0].url == "https://example.test/solar"


def test_remaster_title_picks_the_closer_file():
    track = TrackQuery("Michael Jackson", "Bad - 2012 Remaster", "", 247)
    hits = [
        WebCandidate("youtube", "https://example.test/long", "Bad", "Michael Jackson", 260),
        WebCandidate("youtube", "https://example.test/remaster", "Bad (2012 Remaster)", "Michael Jackson", 247),
    ]
    kind, chosen = choose(track, hits)
    assert kind == "one"
    assert chosen[0].url == "https://example.test/remaster"


def test_same_length_returns_one():
    track = TrackQuery("Mötley Crüe", "Kickstart My Heart", "", 283)
    hits = [
        WebCandidate("youtube", "https://example.test/plain", "Kickstart My Heart", "Mötley Crüe", 283),
        WebCandidate(
            "youtube",
            "https://example.test/remaster",
            "Kickstart My Heart (2024 Remaster)",
            "Mötley Crüe",
            283,
        ),
    ]
    kind, chosen = choose(track, hits)
    assert kind == "one"
    assert chosen[0].url == "https://example.test/plain"


def test_unknown_duration_matches_full_length():
    track = TrackQuery("Nova Ridge", "Solar Drift", "", 0)
    hits = [
        WebCandidate("youtube", "https://example.test/full", "Solar Drift", "Nova Ridge", 180),
        WebCandidate("youtube", "https://example.test/short", "Solar Drift", "Nova Ridge", 20),
    ]
    kind, chosen = choose(track, hits)
    assert kind == "one"
    assert chosen[0].url == "https://example.test/full"


def test_placeholder_artist_rejects_a_longer_title():
    track = TrackQuery("Unknown", "Luna", "", 0)
    hit = WebCandidate(
        "soulseek",
        "slsk://bad",
        "God Unknown Records - Singles Club - Luna Milk Orb.flac",
        "someone",
        400,
        lossless=True,
    )
    kind, hits = choose(track, [hit])
    assert kind == "none"
    assert hits == []


def test_search_query_drops_noise_words():
    assert search_query("Michael Jackson", "Bad - 2012 Remaster") == "Michael Jackson Bad"
    assert search_query("Nova Ridge", "Solar Drift") == "Nova Ridge Solar Drift"
    assert search_query("Unknown", "Luna") == "Luna"
