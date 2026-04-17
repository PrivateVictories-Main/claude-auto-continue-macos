"""
Non-blocking version check against PyPI.

On startup, a background thread fetches the latest version from PyPI's
JSON API and calls a callback if a newer version is available.  The check
is best-effort: timeouts, network errors, and parse failures are silently
ignored so it never delays or disrupts the main flow.
"""

from __future__ import annotations

import json
import threading
from typing import Callable, Optional
from urllib.request import Request, urlopen

from . import __version__

PYPI_URL = "https://pypi.org/pypi/claude-auto-continue-macos/json"
TIMEOUT_SECONDS = 5


def _parse_version(s: str) -> tuple[int, ...]:
    parts: list[int] = []
    for seg in s.strip().split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            break
    return tuple(parts)


def _fetch_latest() -> Optional[str]:
    try:
        req = Request(PYPI_URL, headers={"User-Agent": "claude-auto-continue"})
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("info", {}).get("version")
    except Exception:
        return None


def check_async(callback: Callable[[str, str], None]) -> None:
    """Start a background thread that calls ``callback(current, latest)``
    if a newer version is available on PyPI.  If the check fails or the
    current version is up to date, the callback is never invoked."""

    def _run():
        latest = _fetch_latest()
        if latest is None:
            return
        current_t = _parse_version(__version__)
        latest_t = _parse_version(latest)
        if not current_t or not latest_t:
            return
        if latest_t > current_t:
            callback(__version__, latest)

    t = threading.Thread(target=_run, daemon=True, name="update-check")
    t.start()
