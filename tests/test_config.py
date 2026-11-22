"""Settings file ~/.config/ipodsync/env fills unset IPODSYNC_* variables."""
from __future__ import annotations

import os

import pytest

from ipodsync import config

KEYS = ("IPODSYNC_BACKUP_DIR", "IPODSYNC_MOUNT", "IPODSYNC_FIREWIRE_GUID", "OTHER_SETTING")


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    yield h
    for k in KEYS:  # load_config writes to os.environ directly
        os.environ.pop(k, None)


def write_env(home, text):
    p = home / ".config" / "ipodsync" / "env"
    p.parent.mkdir(parents=True)
    p.write_text(text)
    return p


def test_value_from_the_file_is_used(home):
    write_env(home, "IPODSYNC_BACKUP_DIR=/srv/bk\n")
    config.load_config()
    assert os.environ["IPODSYNC_BACKUP_DIR"] == "/srv/bk"


def test_environment_wins_over_the_file(home, monkeypatch):
    write_env(home, "IPODSYNC_MOUNT=/from/file\n")
    monkeypatch.setenv("IPODSYNC_MOUNT", "/from/env")
    config.load_config()
    assert os.environ["IPODSYNC_MOUNT"] == "/from/env"


def test_missing_file_is_fine(home):
    config.load_config()
    assert "IPODSYNC_BACKUP_DIR" not in os.environ


def test_comments_blanks_quotes_and_tilde(home):
    write_env(home, '# a comment\n\n  IPODSYNC_BACKUP_DIR = "~/my backups"  \n'
                    "IPODSYNC_FIREWIRE_GUID='0123456789ABCDEF'\n")
    config.load_config()
    assert os.environ["IPODSYNC_BACKUP_DIR"] == str(home / "my backups")
    assert os.environ["IPODSYNC_FIREWIRE_GUID"] == "0123456789ABCDEF"


def test_home_variable_is_expanded(home):
    write_env(home, "IPODSYNC_BACKUP_DIR=$HOME/bk\n")
    config.load_config()
    assert os.environ["IPODSYNC_BACKUP_DIR"] == f"{home}/bk"


def test_other_names_and_broken_lines_are_ignored(home):
    write_env(home, "OTHER_SETTING=x\nnot a setting\nIPODSYNC_MOUNT=/m\n")
    config.load_config()
    assert "OTHER_SETTING" not in os.environ
    assert os.environ["IPODSYNC_MOUNT"] == "/m"


def test_xdg_config_home_is_respected(home, tmp_path, monkeypatch):
    xdg = tmp_path / "xdg"
    (xdg / "ipodsync").mkdir(parents=True)
    (xdg / "ipodsync" / "env").write_text("IPODSYNC_BACKUP_DIR=/xdg/bk\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert config.config_path() == xdg / "ipodsync" / "env"
    config.load_config()
    assert os.environ["IPODSYNC_BACKUP_DIR"] == "/xdg/bk"
