"""
Activity log writer for ~/.claude-auto-continue/activity.log.

Only timestamps, event types, and counts are written. No conversation
content, no window titles, no UI text — ever.

Rotation: when the log exceeds MAX_LOG_BYTES, the current file is
renamed to activity.log.1 (overwriting any previous backup) and a
fresh file is opened. At most two files exist at any time.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

DEFAULT_HOME = Path.home() / ".claude-auto-continue"
DEFAULT_LOG = DEFAULT_HOME / "activity.log"
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB


class ActivityLog:
    """Append-only text log with simple rotation. No-op when disabled."""

    def __init__(
        self,
        path: Optional[Path] = None,
        *,
        enabled: bool = True,
        max_bytes: int = MAX_LOG_BYTES,
    ) -> None:
        self.path = Path(path) if path else DEFAULT_LOG
        self.enabled = enabled
        self.max_bytes = max_bytes
        self._fh: Optional[TextIO] = None

    # ---- lifecycle ------------------------------------------------------

    def open(self) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.enabled = False
            return
        self._fh = self.path.open("a", buffering=1, encoding="utf-8")

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            finally:
                self._fh = None

    # ---- rotation -------------------------------------------------------

    def _maybe_rotate(self) -> None:
        if self._fh is None or self.max_bytes <= 0:
            return
        try:
            if self.path.stat().st_size < self.max_bytes:
                return
        except OSError:
            return
        try:
            self._fh.flush()
            self._fh.close()
        except OSError:
            pass
        backup = self.path.with_suffix(".log.1")
        try:
            self.path.rename(backup)
        except OSError:
            pass
        self._fh = self.path.open("a", buffering=1, encoding="utf-8")

    # ---- writes ---------------------------------------------------------

    def _write(self, line: str) -> None:
        if not self.enabled or self._fh is None:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._fh.write(f"[{ts}] {line}\n")
        self._maybe_rotate()

    def session_start(self, *, pid: int, interval: float, dry_run: bool) -> None:
        self._write(f"=== session start (pid={pid}, interval={interval}s, dry_run={dry_run}) ===")

    def session_end(self, *, total: int, uptime_seconds: float) -> None:
        self._write(f"=== session end (total_continues={total}, uptime={uptime_seconds:.0f}s) ===")

    def auto_continue(self, count: int, *, surface: str = "", source: str = "") -> None:
        parts = [f"Auto-continue #{count} triggered"]
        if surface:
            parts.append(f"surface={surface}")
        if source:
            parts.append(f"source={source}")
        self._write(" | ".join(parts))

    def dry_run_hit(self, count: int, *, surface: str = "", source: str = "") -> None:
        parts = [f"[DRY RUN] Auto-continue #{count} would have triggered"]
        if surface:
            parts.append(f"surface={surface}")
        if source:
            parts.append(f"source={source}")
        self._write(" | ".join(parts))

    def note(self, message: str) -> None:
        self._write(message)
