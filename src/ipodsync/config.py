"""Optional settings file: ~/.config/ipodsync/env (or $XDG_CONFIG_HOME/ipodsync/env).

One IPODSYNC_* setting per line, the same names as the environment variables:

    # ipodsync settings
    IPODSYNC_BACKUP_DIR=~/ipod-backups

Variables already set in the environment win over the file. Lines starting with #,
blank lines, lines without "=" and names not starting with IPODSYNC_ are ignored.
Quotes around a value are stripped; ~ and $VARS in a value are expanded.
"""
from __future__ import annotations

import os
from pathlib import Path

PREFIX = "IPODSYNC_"


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ipodsync" / "env"


def load_config(path: Path | None = None) -> None:
    """Fill unset IPODSYNC_* environment variables from the settings file, if it exists."""
    path = path or config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (s.strip() for s in line.split("=", 1))
        if not key.startswith(PREFIX) or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = os.path.expanduser(os.path.expandvars(value))
