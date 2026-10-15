import sqlite3
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from djgrab.cli import main
from tests.support import write_wav


def test_cli_downloads_a_local_file(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    write_wav(site / "solar.wav", 0.3, 440)
    handler = partial(SimpleHTTPRequestHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    data = tmp_path / "data"
    url = f"http://127.0.0.1:{server.server_address[1]}/solar.wav"
    config = Path(__file__).parents[1] / "djgrab.example.toml"
    try:
        code = main([url, "--data", str(data), "--config", str(config)])
    finally:
        server.shutdown()
        server.server_close()
    assert code == 0
    audio = [
        path
        for path in (data / "djgrab").rglob("*")
        if path.suffix.casefold() in {".m4a", ".mp3", ".wav", ".flac"}
    ]
    assert len(audio) == 1
    con = sqlite3.connect(data / "djgrab.sqlite")
    row = con.execute("SELECT path FROM inbox_files").fetchone()
    assert row[0] == str(audio[0])
    assert Path(row[0]).is_file()
