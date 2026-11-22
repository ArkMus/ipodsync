"""-b backups go to $IPODSYNC_BACKUP_DIR if set, else ~/ipod-backups."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ipodsync import cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv("IPODSYNC_BACKUP_DIR", raising=False)
    return h


@pytest.fixture
def itlp(tmp_path):
    d = tmp_path / "iTunes Library.itlp"
    d.mkdir()
    (d / "Library.itdb").write_bytes(b"db")
    return d


def test_default_is_ipod_backups_in_home(home, itlp):
    dst = cli._backup_library(itlp, "stamp")
    assert dst == home / "ipod-backups" / "itlp-stamp"
    assert (dst / "Library.itdb").read_bytes() == b"db"


def test_env_var_picks_the_folder_and_creates_it(home, itlp, tmp_path, monkeypatch):
    target = tmp_path / "elsewhere" / "nested"
    monkeypatch.setenv("IPODSYNC_BACKUP_DIR", str(target))
    dst = cli._backup_library(itlp, "stamp")
    assert dst == target / "itlp-stamp"
    assert (dst / "Library.itdb").exists()
    assert not (home / "ipod-backups").exists()


def test_tilde_and_relative_paths_become_absolute(home, tmp_path, monkeypatch):
    monkeypatch.setenv("IPODSYNC_BACKUP_DIR", "~/bk")
    assert cli._backup_dir() == home / "bk"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IPODSYNC_BACKUP_DIR", "rel")
    assert cli._backup_dir() == tmp_path / "rel"


def test_artwork_goes_to_the_same_folder(home, tmp_path, monkeypatch):
    target = tmp_path / "bk"
    monkeypatch.setenv("IPODSYNC_BACKUP_DIR", str(target))
    control = tmp_path / "iPod_Control"
    (control / "Artwork").mkdir(parents=True)
    (control / "Artwork" / "ArtworkDB").write_bytes(b"art")
    cli._backup_artwork(SimpleNamespace(control=control), "stamp")
    assert (target / "Artwork-stamp" / "ArtworkDB").read_bytes() == b"art"
