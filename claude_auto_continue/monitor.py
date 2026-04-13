"""
The polling loop.

Every `interval` seconds:

1. Find the Claude app. If not running, set state=Waiting and keep polling.
2. If the pid changed since last scan, re-enable AXManualAccessibility.
3. Scan each window for a Continue button inside tool-use-limit context.
4. If a match is found and we're outside the cooldown window, press it
   (unless --dry-run), notify, log, and arm the cooldown.
5. Handle any AX error by logging and continuing — never crash the loop.

The loop is driven by cooperative checks against a ``stop`` callable so
the CLI signal handler can shut us down cleanly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import accessibility as ax
from .config import Settings
from .logger import ActivityLog
from .notifications import Notifier
from .ui import TerminalUI


@dataclass
class MonitorContext:
    settings: Settings
    ui: TerminalUI
    notifier: Notifier
    log: ActivityLog
    stop: Callable[[], bool]


class Monitor:
    def __init__(self, ctx: MonitorContext) -> None:
        self.ctx = ctx
        self._current_app: Optional[ax.ClaudeApp] = None
        self._current_pid: Optional[int] = None
        self._last_click_at: float = 0.0

    # ------------------------------------------------------------------

    def run(self) -> None:
        s = self.ctx.settings
        ui = self.ctx.ui
        ui.status.state = "Watching"
        ui.status.state_style = "green"
        ui.status.dry_run = s.dry_run

        while not self.ctx.stop():
            try:
                self._tick()
            except Exception as exc:  # never crash the loop
                ui.error(f"scan error: {exc!r}")

            ui.refresh()

            # Cap termination condition.
            if s.max_continues and ui.status.total_continues >= s.max_continues:
                ui.warn(
                    f"reached --max-continues cap of {s.max_continues}; "
                    "shutting down"
                )
                return

            self._sleep(s.interval)

    # ------------------------------------------------------------------

    def _tick(self) -> None:
        ui = self.ctx.ui
        app = ax.find_claude_app()

        if app is None:
            if self._current_app is not None:
                ui.warn("Claude app closed — waiting for it to return")
            self._current_app = None
            self._current_pid = None
            ui.status.claude_detected = False
            ui.status.ax_enabled = False
            ui.status.state = "Waiting for Claude"
            ui.status.state_style = "yellow"
            return

        # Fresh launch, or pid changed since last scan? Re-enable AX.
        if self._current_pid != app.pid:
            first_time = self._current_pid is None
            self._current_app = app
            self._current_pid = app.pid
            ui.status.claude_detected = True
            ui.status.state = "Watching"
            ui.status.state_style = "green"
            ok = ax.enable_manual_accessibility(app)
            ui.status.ax_enabled = ok
            if first_time:
                ui.info(f"Claude detected (pid {app.pid}) — AXManualAccessibility "
                        f"{'enabled' if ok else 'could not be enabled'}")
            else:
                ui.info(f"Claude restarted (pid {app.pid}) — re-enabled AX "
                        f"{'ok' if ok else 'FAILED'}")

        verbose_cb = ui.debug if ui.verbose else None
        candidates = ax.find_continue_buttons(app, verbose_cb=verbose_cb)

        if not candidates:
            ui.heartbeat(f"tick — pid={app.pid}, no Continue button")
            return

        # Cooldown gate — if we just clicked, don't fire again.
        now = time.monotonic()
        cooldown = self.ctx.settings.cooldown
        if cooldown > 0 and (now - self._last_click_at) < cooldown:
            remaining = cooldown - (now - self._last_click_at)
            ui.heartbeat(
                f"button found but cooldown holds ({remaining:.1f}s remaining)"
            )
            return

        # Click the first candidate (there's typically only one at a time).
        target = candidates[0]
        self._handle_click(target)

    # ------------------------------------------------------------------

    def _handle_click(self, candidate: ax.ButtonCandidate) -> None:
        ui = self.ctx.ui
        settings = self.ctx.settings

        if settings.dry_run:
            ui.status.total_continues += 1
            ui.status.last_continue_at = time.monotonic()
            self._last_click_at = time.monotonic()
            ui.warn(
                f"[DRY RUN] Would have clicked {candidate.label!r} "
                f"(window {candidate.window_index})"
            )
            self.ctx.log.dry_run_hit(ui.status.total_continues)
            return

        ok = ax.press(candidate.element)
        if not ok:
            ui.error(f"AXPress failed on {candidate.label!r}; will retry next tick")
            return

        ui.status.total_continues += 1
        ui.status.last_continue_at = time.monotonic()
        self._last_click_at = time.monotonic()
        total = ui.status.total_continues
        ui.success(
            f"auto-continued #{total} — pressed {candidate.label!r} "
            f"in window {candidate.window_index}"
        )
        self.ctx.log.auto_continue(total)
        self.ctx.notifier.announce_continue(total, label=candidate.label)

    # ------------------------------------------------------------------

    def _sleep(self, duration: float) -> None:
        """Sleep in small slices so Ctrl+C feels responsive."""
        deadline = time.monotonic() + duration
        while not self.ctx.stop():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.2, remaining))
