"""
Optional TOML config file at ~/.claude-auto-continue/config.toml.

All CLI flags can be defaulted here. CLI arguments always win.

Example config.toml:

    interval = 3
    silent = false
    notifications = true
    max_continues = 0          # 0 = unlimited
    log = true
    verbose = false
    dry_run = false
    cooldown = 5
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional

from .logger import DEFAULT_HOME

CONFIG_PATH = DEFAULT_HOME / "config.toml"


# ---------------------------------------------------------------------------
# Resolved settings dataclass
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    interval: float = 3.0
    cooldown: float = 5.0
    silent: bool = False
    notifications: bool = True
    max_continues: int = 0  # 0 means unlimited
    log: bool = True
    verbose: bool = False
    dry_run: bool = False

    def validate(self) -> None:
        if not (1.0 <= self.interval <= 30.0):
            raise ValueError(
                f"--interval must be between 1 and 30 seconds (got {self.interval})"
            )
        if self.cooldown < 0:
            raise ValueError(f"cooldown must be >= 0 (got {self.cooldown})")
        if self.max_continues < 0:
            raise ValueError(
                f"--max-continues must be >= 0 (got {self.max_continues})"
            )


# ---------------------------------------------------------------------------
# TOML loader with tomli fallback for Python 3.9/3.10
# ---------------------------------------------------------------------------

def _load_toml(path: Path) -> dict:
    if sys.version_info >= (3, 11):
        import tomllib  # type: ignore
        with path.open("rb") as f:
            return tomllib.load(f)
    try:
        import tomli  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Python < 3.11 requires the 'tomli' package to read config files. "
            "Install with:  pip install tomli"
        ) from exc
    with path.open("rb") as f:
        return tomli.load(f)


def load_file(path: Optional[Path] = None) -> dict[str, Any]:
    """Return the raw TOML contents as a dict, or {} if the file is absent."""
    target = Path(path) if path else CONFIG_PATH
    if not target.is_file():
        return {}
    try:
        return _load_toml(target)
    except Exception as exc:
        print(
            f"[claude-auto-continue] warning: failed to parse {target}: {exc}",
            file=sys.stderr,
        )
        return {}


# ---------------------------------------------------------------------------
# Merging: config file + CLI -> Settings
# ---------------------------------------------------------------------------

_FIELD_NAMES = {f.name for f in fields(Settings)}


def merge(cli_values: dict[str, Any], file_values: dict[str, Any]) -> Settings:
    """Build a Settings from a CLI dict and a file dict. CLI wins."""
    merged: dict[str, Any] = {}

    # File values first, but only for known keys — ignore typos / extras.
    for key, value in file_values.items():
        if key in _FIELD_NAMES:
            merged[key] = value

    # CLI values override, but only when actually provided (not None).
    for key, value in cli_values.items():
        if key in _FIELD_NAMES and value is not None:
            merged[key] = value

    settings = Settings(**merged)
    settings.validate()
    return settings
