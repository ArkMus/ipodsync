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
    config._from_file.clear()
    yield h
    for k in KEYS:  # load_config writes to os.environ directly
        os.environ.pop(k, None)
    config._from_file.clear()


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


# --- ipodsync config / config set / config unset ---------------------------------

def run(*argv):
    from ipodsync import cli
    return cli.cmd_config(cli_args(*argv))


def cli_args(*argv):
    from types import SimpleNamespace
    action = argv[0] if argv else None
    return SimpleNamespace(action=action, name=argv[1] if len(argv) > 1 else None,
                           value=argv[2] if len(argv) > 2 else None)


def env_file(home):
    return home / ".config" / "ipodsync" / "env"


def test_set_creates_the_folder_and_file(home):
    assert run("set", "backup-dir", "/srv/bk") == 0
    assert env_file(home).read_text() == "IPODSYNC_BACKUP_DIR=/srv/bk\n"


def test_set_replaces_the_line_and_keeps_the_rest(home):
    write_env(home, "# mine\nIPODSYNC_MOUNT=/m\nIPODSYNC_BACKUP_DIR=/old\n"
                    "IPODSYNC_BACKUP_DIR=/dupe\n")
    assert run("set", "IPODSYNC_BACKUP_DIR", "/new") == 0
    assert env_file(home).read_text() == "# mine\nIPODSYNC_MOUNT=/m\nIPODSYNC_BACKUP_DIR=/new\n"


def test_unset_removes_the_line(home, capsys):
    write_env(home, "# mine\nIPODSYNC_BACKUP_DIR=/old\nIPODSYNC_MOUNT=/m\n")
    assert run("unset", "backup-dir") == 0
    assert env_file(home).read_text() == "# mine\nIPODSYNC_MOUNT=/m\n"
    assert run("unset", "backup-dir") == 0
    assert "nothing to remove" in capsys.readouterr().out


def test_unset_without_a_file_is_fine(home, capsys):
    assert run("unset", "mount") == 0
    assert "nothing to remove" in capsys.readouterr().out
    assert not env_file(home).exists()


def test_unknown_name_and_bad_guid_are_refused(home, capsys):
    write_env(home, "IPODSYNC_MOUNT=/m\n")
    assert run("set", "backup_folder", "/x") == 1
    assert run("set", "firewire-guid", "1234") == 1
    assert run("set", "backup-dir", "  ") == 1
    out = capsys.readouterr().out
    assert "mount, firewire-guid, backup-dir" in out and "16 hex digits" in out
    assert env_file(home).read_text() == "IPODSYNC_MOUNT=/m\n"
    assert run("set", "firewire-guid", "0123456789abcdef") == 0


def test_show_tells_where_each_value_comes_from(home, monkeypatch, capsys):
    write_env(home, "IPODSYNC_BACKUP_DIR=~/bk\nIPODSYNC_MOUNT=/from/file\n")
    monkeypatch.setenv("IPODSYNC_MOUNT", "/from/env")
    config.load_config()
    assert run() == 0
    out = capsys.readouterr().out
    assert "mount          /from/env   (from environment)" in out
    assert "backup-dir     ~/bk   (from file)" in out
    assert "firewire-guid  (not set: read from the device)" in out


def test_set_warns_when_the_shell_value_wins(home, monkeypatch, capsys):
    monkeypatch.setenv("IPODSYNC_BACKUP_DIR", "/from/env")
    assert run("set", "backup-dir", "/srv/bk") == 0
    assert "also set in this shell" in capsys.readouterr().out
