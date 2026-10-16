from djgrab.config import DownloadConfig, load_config
from djgrab.inbox import genre_folder, library_dest


def test_genre_map_and_fallback():
    cfg = DownloadConfig(fallback_genre="Unknown", genres={"dance pop": "Pop"})
    assert genre_folder("Dance Pop", cfg) == "Pop"
    assert genre_folder("", cfg) == "Unknown"
    assert genre_folder("jazz", cfg) == "jazz"


def test_toml_genre_map_is_case_insensitive(tmp_path):
    path = tmp_path / "djgrab.toml"
    path.write_text('[library]\nfallback_genre = "Other"\n\n[library.genres]\n"Dance Pop" = "Pop"\n')
    loaded = load_config(path)
    assert loaded.fallback_genre == "Other"
    assert genre_folder("dance pop", loaded) == "Pop"


def test_existing_file_adds_track_id(tmp_path):
    library = tmp_path / "library"
    track = {"id": 3, "artist": "Nova Ridge", "title": "Solar Drift", "genre": "pop"}
    dest = library_dest(library, track, ".m4a", DownloadConfig(genres={"pop": "Pop"}))
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"x")
    again = library_dest(library, track, ".m4a", DownloadConfig(genres={"pop": "Pop"}))
    assert again.name == "Nova Ridge - Solar Drift (3).m4a"
    assert again.parent.name == "Pop"


def test_config_in_the_home_folder_is_used_when_the_local_file_is_missing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".djgrab").mkdir(parents=True)
    (home / ".djgrab" / "djgrab.toml").write_text('[library]\nfallback_genre = "Home"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("djgrab.config.Path.home", lambda: home)
    assert load_config().fallback_genre == "Home"


def test_config_command_writes_credentials_and_keeps_the_rest(tmp_path, monkeypatch):
    from djgrab.cli import main

    home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("djgrab.config.Path.home", lambda: home)
    assert main(["config", "soulseek.username", "dj"]) == 0
    path = home / ".djgrab" / "djgrab.toml"
    path.write_text(path.read_text() + '\n[library]\nfallback_genre = "Other"\n\n[library.genres]\n"dance pop" = "Pop"\n')
    assert main(["config", "soulseek.password", 'p"w']) == 0
    loaded = load_config(path)
    assert (loaded.soulseek_username, loaded.soulseek_password) == ("dj", 'p"w')
    assert loaded.fallback_genre == "Other" and loaded.genres == {"dance pop": "Pop"}
    assert main(["config", "soulseek"]) == 2
    assert main(["config", "nodot", "x"]) == 2


def test_env_overrides_spotify_credentials(tmp_path, monkeypatch):
    path = tmp_path / "djgrab.toml"
    path.write_text('[spotify]\nclient_id = "file"\nclient_secret = "file-secret"\n')
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "from-env")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "env-secret")
    loaded = load_config(path)
    assert loaded.spotify_client_id == "from-env"
    assert loaded.spotify_client_secret == "env-secret"
