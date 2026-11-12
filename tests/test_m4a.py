"""AAC .m4a files are added with the codes iTunes writes for them (audio_format 502,
extension 'M4A ', an "AAC audio file" kind); ALAC and other files are refused.
tests/data/silence*.m4a are generated silence (ffmpeg anullsrc) with made-up tags."""
import sqlite3
from pathlib import Path

import pytest

from ipodsync.artwork_writer import extract_embedded_cover
from ipodsync.importer import UnsupportedAudio, read_meta
from ipodsync.library import ItlpLibrary, TrackMeta
from test_cloned_fields import _make_itlp

DATA = Path(__file__).parent / "data"
MP3_EXT, M4A_EXT = 0x4D503320, 0x4D344120


def test_reads_aac_tags_and_format_codes():
    meta = read_meta(DATA / "silence.m4a")
    assert (meta["title"], meta["artist"], meta["album"], meta["album_artist"]) == (
        "The Quiet One", "The Test Band", "A Silent Album", "Various Testers")
    assert (meta["sort_artist"], meta["sort_title"]) == ("Test Band, The", "")
    assert (meta["track_number"], meta["year"], meta["genre"]) == (3, 2001, "Ambient")
    assert 900 < meta["total_time_ms"] < 1100 and meta["sample_rate"] == 44100
    assert (meta["ext"], meta["audio_format"], meta["extension"], meta["kind"]) == (
        ".m4a", 502, M4A_EXT, "AAC audio file")


def test_cover_art_is_found_in_an_m4a():
    assert extract_embedded_cover(DATA / "silence.m4a").startswith(b"\x89PNG")


def test_alac_is_refused():
    with pytest.raises(UnsupportedAudio, match="ALAC"):
        read_meta(DATA / "silence-alac.m4a")


@pytest.mark.parametrize("name", ["song.flac", "song.aac", "song.mp4", "song"])
def test_other_files_are_refused(tmp_path, name):
    (tmp_path / name).write_bytes(b"x")
    with pytest.raises(UnsupportedAudio):
        read_meta(tmp_path / name)


def _with_kinds(tmp_path, template_ext, template_kind):
    """The shared test library, plus iTunes' file-kind table (names are localized)
    and a location.kind_id; the template track is of the given type."""
    d = _make_itlp(tmp_path)
    lib = sqlite3.connect(d / "Library.itdb")
    lib.executescript("""
        CREATE TABLE location_kind_map (id INTEGER PRIMARY KEY, kind TEXT NOT NULL UNIQUE);
        INSERT INTO location_kind_map VALUES (1, 'MPEG-äänitiedosto'), (4, 'MPEG audio file'),
            (5, 'AAC-äänitiedosto');
        """)
    lib.commit()
    lib.close()
    loc = sqlite3.connect(d / "Locations.itdb")
    loc.execute("ALTER TABLE location ADD COLUMN kind_id INTEGER")
    loc.execute("UPDATE location SET extension=?, kind_id=?", (template_ext, template_kind))
    loc.commit()
    loc.close()
    return d


def _add(lib, n, ext, kind):
    return lib.add_track(TrackMeta(location=f"F00/T{n}{'.m4a' if ext == M4A_EXT else '.mp3'}",
                                   title=f"Song {n}", artist="Linkin Park", album="Meteora",
                                   extension=ext, kind=kind), date=0)


def _loc(lib, pid):
    return tuple(lib.cx["Locations.itdb"].execute(
        "SELECT extension, kind_id FROM location WHERE item_pid=?", (pid,)).fetchone())


def test_aac_track_uses_the_kind_itunes_used_for_aac(tmp_path):
    lib = ItlpLibrary(_with_kinds(tmp_path, M4A_EXT, 5))
    try:
        assert _loc(lib, _add(lib, 1, M4A_EXT, "AAC audio file")) == (M4A_EXT, 5)
    finally:
        lib.close()


def test_mp3_after_an_aac_template_doesnt_get_the_aac_kind(tmp_path):
    lib = ItlpLibrary(_with_kinds(tmp_path, M4A_EXT, 5))
    try:
        # no MP3 location yet: the kind is found by name
        assert _loc(lib, _add(lib, 1, MP3_EXT, "MPEG audio file")) == (MP3_EXT, 4)
    finally:
        lib.close()


def test_missing_kind_is_created_once(tmp_path):
    lib = ItlpLibrary(_with_kinds(tmp_path, MP3_EXT, 1))
    try:
        first = _loc(lib, _add(lib, 1, M4A_EXT, "AAC audio file"))
        second = _loc(lib, _add(lib, 2, M4A_EXT, "AAC audio file"))
        assert first == second == (M4A_EXT, 6)
        cx = lib.cx["Library.itdb"]
        assert cx.execute("SELECT kind FROM location_kind_map WHERE id=6").fetchone()[0] == \
            "AAC audio file"
        # the MP3 template keeps iTunes' most-used MP3 kind
        assert _loc(lib, _add(lib, 3, MP3_EXT, "MPEG audio file")) == (MP3_EXT, 1)
    finally:
        lib.close()
