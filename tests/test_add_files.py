"""`add` reads every file's tags before copying anything onto the iPod: a file
that can't be added is skipped, and if adding fails part-way the files copied so
far are removed again (the library isn't written, so they would be orphans)."""
from types import SimpleNamespace

import pytest

from ipodsync import cli


def _ipod(tmp_path):
    (tmp_path / "Music" / "F00").mkdir(parents=True)
    return SimpleNamespace(itunes_dir=tmp_path / "iTunes", control=tmp_path, root=tmp_path,
                           music_dir=tmp_path / "Music", sysinfo_extended=None, sysinfo=None)


def _args(*files):
    return SimpleNamespace(file=[str(f) for f in files], folder=None, title=None, artist=None,
                           album=None, backup=False, no_cover=True)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """No real library: the working copy and its write-back are no-ops; tags are
    read by a fake that fails for files named bad*; the database step is recorded."""
    monkeypatch.setattr(cli, "shutil", SimpleNamespace(copytree=lambda s, d: None,
                                                       copy2=lambda s, d: None))
    monkeypatch.setattr(cli, "read_firewire_guid", lambda *a, **k: b"guid")

    def read(path):
        if path.name.startswith("bad"):
            raise ValueError("can't sync to MPEG frame")
        return {"title": path.stem}

    monkeypatch.setattr(cli, "read_mp3_meta", read)
    added = []
    monkeypatch.setattr(cli, "add_mp3_to_library",
                        lambda work, location, src, size, guid, **kw: added.append(kw["meta"])
                        or len(added))
    src = tmp_path / "src"
    src.mkdir()
    for name in ("a.mp3", "bad.mp3", "c.mp3"):
        (src / name).write_bytes(b"audio")
    return SimpleNamespace(src=src, added=added)


def _on_ipod(tmp_path):
    return sorted(p.name for p in (tmp_path / "Music" / "F00").iterdir())


def test_unreadable_file_is_skipped_before_anything_is_copied(tmp_path, fake, capsys):
    cli.cmd_add(_ipod(tmp_path), _args(*(fake.src / n for n in ("a.mp3", "bad.mp3", "c.mp3"))))
    assert [m["title"] for m in fake.added] == ["a", "c"]
    assert len(_on_ipod(tmp_path)) == 2                  # bad.mp3 was never copied
    out = capsys.readouterr().out
    assert 'skipping "bad.mp3"' in out and "Skipped 1 file" in out


def test_nothing_readable_is_an_error(tmp_path, fake):
    with pytest.raises(SystemExit):
        cli.cmd_add(_ipod(tmp_path), _args(fake.src / "bad.mp3"))
    assert _on_ipod(tmp_path) == []


def test_failed_add_removes_the_copied_files(tmp_path, fake, monkeypatch):
    def fail_on_second(work, location, src, size, guid, **kw):
        if src.endswith("c.mp3"):
            raise RuntimeError("database error")
        return 1

    monkeypatch.setattr(cli, "add_mp3_to_library", fail_on_second)
    with pytest.raises(RuntimeError):
        cli.cmd_add(_ipod(tmp_path), _args(fake.src / "a.mp3", fake.src / "c.mp3"))
    assert _on_ipod(tmp_path) == []                      # a.mp3 removed again too
