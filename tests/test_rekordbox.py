from xml.etree import ElementTree

from djgrab.rekordbox import write_rekordbox
from tests.support import write_wav


def test_rekordbox_xml_lists_each_genre(tmp_path):
    library = tmp_path / "djgrab"
    write_wav(library / "House" / "Ada - Fresh.wav", 0.1, 440)
    write_wav(library / "Pop" / "אודיה - פרפרים [SoundCloud].wav", 0.1, 440)

    count, dest = write_rekordbox(library, duration=lambda _path: 180)

    assert count == 2
    assert dest == library / "rekordbox.xml"
    root = ElementTree.parse(dest).getroot()
    tracks = {row.get("Genre"): row for row in root.find("COLLECTION")}
    assert root.find("COLLECTION").get("Entries") == "2"
    assert tracks["House"].get("Artist") == "Ada"
    assert tracks["House"].get("Name") == "Fresh"
    assert tracks["House"].get("TotalTime") == "180"
    assert tracks["House"].get("Location").startswith("file://localhost/")
    assert "Ada%20-%20Fresh.wav" in tracks["House"].get("Location")
    assert tracks["Pop"].get("Artist") == "אודיה"
    assert tracks["Pop"].get("Name") == "פרפרים"
    playlists = [
        node.get("Name")
        for node in root.find("PLAYLISTS").iter("NODE")
        if node.get("Type") == "1"
    ]
    assert playlists == ["House", "Pop"]
    assert [node.get("Key") for node in root.find("PLAYLISTS").iter("TRACK")] == ["1", "2"]
