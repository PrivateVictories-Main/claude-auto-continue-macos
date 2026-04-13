"""
Activity log writer for ~/.claude-auto-continue/activity.log.

Only timestamps, event types, and counts are written. No conversation
content, no window titles, no UI text — ever.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO


DEFAULT_HOME = Path.home() / ".claude-auto-continue"
DEFAULT_LOG = DEFAULT_HOME / "activity.log"


class ActivityLog:
    """Append-only text log. No-op when disabled."""

    def __init__(self, path: Optional[Path] = None, *, enabled: bool = True) -> None:
        self.path = Path(path) if path else DEFAULT_LOG
        self.enabled = enabled
        self._fh: Optional[TextIO] = None

    # ---- lifecycle ------------------------------------------------------

    def open(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", buffering=1, encoding="utf-8")

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            finally:
                self._fh = None

    # ---- writes ---------------------------------------------------------

    def _write(self, line: str) -> None:
        if not self.enabled or self._fh is None:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._fh.write(f"[{ts}] {line}\n")

    def session_start(self, *, pid: int, interval: float, dry_run: bool) -> None:
        self._write(
            f"=== session start (pid={pid}, interval={interval}s, "
            f"dry_run={dry_run}) ==="
        )

    def session_end(self, *, total: int, uptime_seconds: float) -> None:
        self._write(
            f"=== session end (total_continues={total}, "
            f"uptime={uptime_seconds:.0f}s) ==="
        )

    def auto_continue(self, count: int) -> None:
        self._write(f"Auto-continue #{count} triggered")

    def dry_run_hit(self, count: int) -> None:
        self._write(f"[DRY RUN] Auto-continue #{count} would have triggered")

    def note(self, message: str) -> None:
        self._write(message)
