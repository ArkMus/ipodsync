"""Optional settings file: ~/.config/ipodsync/env (or $XDG_CONFIG_HOME/ipodsync/env).

One IPODSYNC_* setting per line, the same names as the environment variables:

    # ipodsync settings
    IPODSYNC_BACKUP_DIR=~/ipod-backups

Variables already set in the environment win over the file. Lines starting with #,
blank lines, lines without "=" and names not starting with IPODSYNC_ are ignored.
Quotes around a value are stripped; ~ and $VARS in a value are expanded.
`ipodsync config set/unset` edits the file; it can also be written by hand.
"""
from __future__ import annotations

import os
from pathlib import Path

PREFIX = "IPODSYNC_"

# short name -> (environment variable, what happens when it's not set)
SETTINGS = {
    "mount": ("IPODSYNC_MOUNT", "found automatically"),
    "firewire-guid": ("IPODSYNC_FIREWIRE_GUID", "read from the device"),
    "backup-dir": ("IPODSYNC_BACKUP_DIR", "~/ipod-backups"),
}

_from_file: set[str] = set()  # variables load_config() filled in (vs. set in the shell)


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ipodsync" / "env"


def _parse(line: str) -> tuple[str, str] | None:
    """(KEY, value) for an IPODSYNC_* line, quotes stripped; None for anything else."""
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, value = (s.strip() for s in line.split("=", 1))
    if not key.startswith(PREFIX):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return key, value


def read_config(path: Path | None = None) -> dict[str, str]:
    """The file's IPODSYNC_* settings as written (not expanded); {} if there's no file."""
    try:
        text = (path or config_path()).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return dict(kv for kv in map(_parse, text.splitlines()) if kv)


def load_config(path: Path | None = None) -> None:
    """Fill unset IPODSYNC_* environment variables from the settings file, if it exists."""
    for key, value in read_config(path).items():
        if key not in os.environ:
            os.environ[key] = os.path.expanduser(os.path.expandvars(value))
            _from_file.add(key)


def set_in_shell(key: str) -> bool:
    """True if the variable comes from the environment rather than the settings file."""
    return key in os.environ and key not in _from_file


def env_name(name: str) -> str:
    """'backup-dir' or 'IPODSYNC_BACKUP_DIR' -> 'IPODSYNC_BACKUP_DIR'; ValueError otherwise."""
    if name in SETTINGS:
        return SETTINGS[name][0]
    if name.upper() in (env for env, _ in SETTINGS.values()):
        return name.upper()
    raise ValueError(f"unknown setting {name!r}; use one of: {', '.join(SETTINGS)}")


def set_value(name: str, value: str, path: Path | None = None) -> str:
    """Write KEY=value to the settings file (replacing an existing line); returns KEY."""
    from ipodsync.sysinfo import _clean_hex

    key = env_name(name)
    value = value.strip()
    if not value:
        raise ValueError("empty value; use `ipodsync config unset` to remove a setting")
    if key == "IPODSYNC_FIREWIRE_GUID" and not _clean_hex(value):
        raise ValueError(f"{value!r} is not 16 hex digits (e.g. 0123456789ABCDEF)")
    path = path or config_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], False
    for line in lines:
        kv = _parse(line)
        if kv and kv[0] == key:
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue  # drop duplicates of the same key
        out.append(line)
    if not done:
        out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return key


def unset_value(name: str, path: Path | None = None) -> tuple[str, bool]:
    """Remove KEY from the settings file; returns (KEY, whether it was there)."""
    key = env_name(name)
    path = path or config_path()
    if not path.exists():
        return key, False
    lines = path.read_text(encoding="utf-8").splitlines()
    out = [ln for ln in lines if (_parse(ln) or ("",))[0] != key]
    if len(out) == len(lines):
        return key, False
    path.write_text("".join(ln + "\n" for ln in out), encoding="utf-8")
    return key, True
