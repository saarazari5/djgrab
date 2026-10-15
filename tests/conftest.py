import pytest


@pytest.fixture(autouse=True)
def _no_live_genre_lookup(monkeypatch):
    # Filing tests stay offline. The genre tests call genre_for_artist directly.
    monkeypatch.setattr("djgrab.inbox.genre_for_artist", lambda *args, **kwargs: "")
