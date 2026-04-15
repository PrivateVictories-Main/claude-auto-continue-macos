"""
The polling loop.

We scan three kinds of targets every ``interval`` seconds and press
Continue on whichever one is paused:

1. The native Claude desktop app  (AXPress on a Continue button).
2. Any running browser showing a claude.ai tab  (AXPress, same as above).
3. Any frontmost terminal running Claude Code  (synthesised Return).

Each hit goes through the same cooldown so a browser click and an app
click can't double-fire within the same second. Errors in any one
subsystem never crash the loop — they log and we continue.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import accessibility as ax
from . import browser as br
from . import terminal as term
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
    state: Optional[object] = None  # dashboard.SharedState, optional


class Monitor:
    def __init__(self, ctx: MonitorContext) -> None:
        self.ctx = ctx
        self._current_app: Optional[ax.ClaudeApp] = None
        self._current_pid: Optional[int] = None
        self._last_click_at: float = 0.0
        self._seen_browser_pids: set[int] = set()
        # When True, the next sleep collapses to the fast follow-up
        # interval — used to catch back-to-back pauses without waiting a
        # full polling interval and to re-scan immediately after Claude
        # restarts (the freshly-launched AX tree may not be populated on
        # the very same tick we detect the new pid).
        self._fast_followup: bool = False

    # ---- shared-state helpers (dashboard) -----------------------------

    def _emit(self, level: str, message: str) -> None:
        state = self.ctx.state
        if state is not None:
            try:
                state.publish_log(level, message)
            except Exception:
                pass

    def _sync_status(self, **overrides) -> None:
        state = self.ctx.state
        if state is None:
            return
        ui_status = self.ctx.ui.status
        payload = {
            "state": ui_status.state,
            "state_style": ui_status.state_style,
            "claude_detected": ui_status.claude_detected,
            "ax_enabled": ui_status.ax_enabled,
            "total_continues": ui_status.total_continues,
            "last_continue_at": (
                None
                if ui_status.last_continue_at is None
                else time.time() - (time.monotonic() - ui_status.last_continue_at)
            ),
            "started_at": time.time() - ui_status.uptime(),
            "dry_run": ui_status.dry_run,
        }
        payload.update(overrides)
        try:
            state.set_status(**payload)
        except Exception:
            pass

    # ------------------------------------------------------------------

    def run(self) -> None:
        s = self.ctx.settings
        ui = self.ctx.ui
        ui.status.state = "Watching"
        ui.status.state_style = "green"
        ui.status.dry_run = s.dry_run
        self._sync_status()

        while not self.ctx.stop():
            try:
                self._tick()
            except Exception as exc:  # never crash the loop
                ui.error(f"scan error: {exc!r}")
                self._emit("error", f"scan error: {exc!r}")

            ui.refresh()
            self._sync_status()

            if s.max_continues and ui.status.total_continues >= s.max_continues:
                msg = (
                    f"reached --max-continues cap of {s.max_continues}; "
                    "shutting down"
                )
                ui.warn(msg)
                self._emit("warn", msg)
                return

            # Live-reload settings each iteration — dashboard mutations apply.
            # After a click or a Claude restart, drop to a tight 0.4s
            # follow-up so back-to-back pauses or freshly-loaded AX trees
            # are caught fast instead of waiting a full poll interval.
            if self._fast_followup:
                self._fast_followup = False
                self._sleep(0.4)
            else:
                self._sleep(self.ctx.settings.interval)

    # ------------------------------------------------------------------

    def _tick(self) -> None:
        s = self.ctx.settings

        app_hit = self._scan_app() if s.scan_app else False
        if app_hit:
            return

        if s.scan_browsers:
            if self._scan_browsers():
                return

        if s.scan_terminals:
            self._scan_terminals()

    # ---- target: native Claude desktop app ---------------------------

    def _scan_app(self) -> bool:
        ui = self.ctx.ui
        app = ax.find_claude_app()

        if app is None:
            if self._current_app is not None:
                msg = "Claude app closed — waiting for it to return"
                ui.warn(msg)
                self._emit("warn", msg)
            self._current_app = None
            self._current_pid = None
            ui.status.claude_detected = False
            ui.status.ax_enabled = False
            ui.status.state = "Waiting for Claude"
            ui.status.state_style = "yellow"
            return False

        if self._current_pid != app.pid:
            first_time = self._current_pid is None
            self._current_app = app
            self._current_pid = app.pid
            ui.status.claude_detected = True
            ui.status.state = "Watching"
            ui.status.state_style = "green"
            ok = ax.enable_manual_accessibility(app)
            ui.status.ax_enabled = ok
            verb = "detected" if first_time else "restarted"
            msg = (
                f"Claude {verb} (pid {app.pid}) — AXManualAccessibility "
                f"{'enabled' if ok else 'FAILED'}"
            )
            ui.info(msg)
            self._emit("info", msg)
            # The freshly-launched Electron tree often isn't fully
            # populated yet — schedule a fast follow-up so we don't wait
            # a whole interval before the first useful scan.
            self._fast_followup = True

        verbose_cb = ui.debug if ui.verbose else None
        candidates = ax.find_continue_buttons(app, verbose_cb=verbose_cb)
        if not candidates:
            ui.heartbeat(f"tick — pid={app.pid}, no Continue button")
            return False

        if self._in_cooldown(ui):
            return False

        target = candidates[0]
        self._handle_ax_click(
            element=target.element,
            label=target.label,
            source=f"Claude app window {target.window_index}",
        )
        return True

    # ---- target: browsers (claude.ai tab) ----------------------------

    def _scan_browsers(self) -> bool:
        ui = self.ctx.ui
        browsers = br.find_browsers()

        # Seed AX-enhanced mode once per pid — saves a noisy write on every tick.
        current_pids = {b.pid for b in browsers}
        for b in browsers:
            if b.pid not in self._seen_browser_pids:
                ok = br.enable_enhanced_ax(b)
                if ui.verbose:
                    ui.debug(
                        f"browser {b.name} (pid {b.pid}) AX enable={'ok' if ok else 'fail'}"
                    )
                self._seen_browser_pids.add(b.pid)
        # Drop pids that have quit so a relaunched browser gets re-seeded.
        self._seen_browser_pids &= current_pids

        verbose_cb = ui.debug if ui.verbose else None
        for b in browsers:
            try:
                candidates = br.find_browser_continue_buttons(
                    b, verbose_cb=verbose_cb
                )
            except Exception as exc:
                ui.error(f"browser scan error ({b.name}): {exc!r}")
                continue
            if not candidates:
                continue
            if self._in_cooldown(ui):
                return True
            target = candidates[0]
            self._handle_ax_click(
                element=target.element,
                label=target.label,
                source=f"{target.browser_name} — {target.url}",
            )
            return True
        return False

    # ---- target: terminals (Claude Code CLI) -------------------------

    def _scan_terminals(self) -> bool:
        ui = self.ctx.ui
        s = self.ctx.settings
        verbose_cb = ui.debug if ui.verbose else None
        try:
            candidates = term.find_terminal_candidates(
                extra_patterns=s.terminal_patterns or (),
                verbose_cb=verbose_cb,
            )
        except Exception as exc:
            ui.error(f"terminal scan error: {exc!r}")
            return False

        if not candidates:
            return False

        if self._in_cooldown(ui):
            return True

        target = candidates[0]
        source = (
            f"{target.terminal_name} — matched {target.matched_pattern!r}"
        )

        if s.dry_run:
            ui.status.total_continues += 1
            ui.status.last_continue_at = time.monotonic()
            self._last_click_at = time.monotonic()
            msg = f"[DRY RUN] Would have sent Return to {source}"
            ui.warn(msg)
            self._emit("warn", msg)
            self.ctx.log.dry_run_hit(ui.status.total_continues)
            return True

        ok = term.send_return_to(target.terminal_pid)
        if not ok:
            msg = f"failed to send Return to {source}; will retry next tick"
            ui.error(msg)
            self._emit("error", msg)
            return True

        ui.status.total_continues += 1
        ui.status.last_continue_at = time.monotonic()
        self._last_click_at = time.monotonic()
        total = ui.status.total_continues
        msg = f"auto-continued #{total} — sent Return to {source}"
        ui.success(msg)
        self._emit("success", msg)
        self.ctx.log.auto_continue(total)
        self.ctx.notifier.announce_continue(total, label=target.matched_pattern)
        self._fast_followup = True
        return True

    # ---- shared helpers ----------------------------------------------

    def _in_cooldown(self, ui: TerminalUI) -> bool:
        cooldown = self.ctx.settings.cooldown
        if cooldown <= 0:
            return False
        elapsed = time.monotonic() - self._last_click_at
        if elapsed < cooldown:
            ui.heartbeat(
                f"candidate found but cooldown holds ({cooldown - elapsed:.1f}s)"
            )
            return True
        return False

    def _handle_ax_click(
        self,
        *,
        element,
        label: str,
        source: str,
    ) -> None:
        ui = self.ctx.ui
        settings = self.ctx.settings

        if settings.dry_run:
            ui.status.total_continues += 1
            ui.status.last_continue_at = time.monotonic()
            self._last_click_at = time.monotonic()
            msg = f"[DRY RUN] Would have clicked {label!r} in {source}"
            ui.warn(msg)
            self._emit("warn", msg)
            self.ctx.log.dry_run_hit(ui.status.total_continues)
            return

        ok = ax.press(element)
        if not ok:
            msg = f"AXPress failed on {label!r} in {source}; will retry"
            ui.error(msg)
            self._emit("error", msg)
            return

        ui.status.total_continues += 1
        ui.status.last_continue_at = time.monotonic()
        self._last_click_at = time.monotonic()
        total = ui.status.total_continues
        msg = f"auto-continued #{total} — pressed {label!r} in {source}"
        ui.success(msg)
        self._emit("success", msg)
        self.ctx.log.auto_continue(total)
        self.ctx.notifier.announce_continue(total, label=label)
        # Some flows surface a second Continue immediately after the
        # first (consecutive tool-use limits). Re-scan fast.
        self._fast_followup = True

    # ------------------------------------------------------------------

    def _sleep(self, duration: float) -> None:
        """Sleep in small slices so Ctrl+C feels responsive."""
        deadline = time.monotonic() + duration
        while not self.ctx.stop():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.2, remaining))
