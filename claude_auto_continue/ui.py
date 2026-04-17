"""
Terminal UI — welcome banner, color-coded log lines, and a live status
dashboard at the bottom of the terminal.

The dashboard is a `rich.live.Live` displaying a compact table; log lines
are printed above it via `Live.console.print` so they scroll naturally
while the dashboard stays pinned.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__

TAGLINE = (
    "Auto-clicks the 'Continue' button in the Claude macOS app when "
    "tool-use limits pause your session."
)


def build_banner() -> Panel:
    title = Text("claude-auto-continue", style="bold cyan")
    title.append(f"  v{__version__}", style="dim")
    subtitle = Text(TAGLINE, style="dim")
    body = Group(
        Align.center(title),
        Align.center(subtitle),
    )
    return Panel(
        body,
        border_style="cyan",
        padding=(1, 2),
        title="[dim]macOS Accessibility companion[/dim]",
        title_align="center",
    )


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _fmt_elapsed(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    td = timedelta(seconds=int(seconds))
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


@dataclass
class Status:
    state: str = "Starting…"
    state_style: str = "yellow"
    started_at: float = field(default_factory=time.monotonic)
    total_continues: int = 0
    last_continue_at: Optional[float] = None
    claude_detected: bool = False
    ax_enabled: bool = False
    dry_run: bool = False
    notes: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def uptime(self) -> float:
        return time.monotonic() - self.started_at

    def since_last(self) -> Optional[float]:
        if self.last_continue_at is None:
            return None
        return time.monotonic() - self.last_continue_at

    def increment_continues(self) -> int:
        with self._lock:
            self.total_continues += 1
            self.last_continue_at = time.monotonic()
            return self.total_continues


class TerminalUI:
    """Coordinates rich output — banner, log lines, and live dashboard."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.console = Console()
        self.verbose = verbose
        self.status = Status()
        self._live: Optional[Live] = None

    # ---- lifecycle ------------------------------------------------------

    def show_banner(self) -> None:
        self.console.print(build_banner())

    def start_dashboard(self) -> None:
        # Skip the live-updating dashboard when stdout is not a TTY
        # (e.g. running under launchd, piped to a file, or in CI). Log
        # lines still print normally via _print().
        if not self.console.is_terminal:
            return
        self._live = Live(
            self._render_dashboard(),
            console=self.console,
            refresh_per_second=4,
            transient=False,
            vertical_overflow="visible",
        )
        self._live.start()

    def stop_dashboard(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            finally:
                self._live = None

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render_dashboard())

    # ---- dashboard rendering -------------------------------------------

    def _render_dashboard(self) -> Panel:
        t = Table.grid(padding=(0, 2), expand=True)
        t.add_column(style="dim", no_wrap=True, justify="right")
        t.add_column(no_wrap=True)

        state_text = Text(self.status.state, style=self.status.state_style)
        if self.status.dry_run:
            state_text.append("  [DRY RUN]", style="yellow")
        t.add_row("State", state_text)

        claude = "detected" if self.status.claude_detected else "not running"
        claude_style = "green" if self.status.claude_detected else "yellow"
        t.add_row("Claude app", Text(claude, style=claude_style))

        ax = "enabled" if self.status.ax_enabled else "pending"
        ax_style = "green" if self.status.ax_enabled else "yellow"
        t.add_row("AX tree", Text(ax, style=ax_style))

        t.add_row("Continues", Text(str(self.status.total_continues), style="bold green"))

        since = self.status.since_last()
        since_text = "None yet" if since is None else _fmt_elapsed(since) + " ago"
        t.add_row("Last continue", since_text)

        t.add_row("Uptime", _fmt_elapsed(self.status.uptime()))

        if self.status.notes:
            t.add_row("Note", Text(self.status.notes, style="dim"))

        return Panel(
            t, title="[bold]claude-auto-continue[/bold]", border_style="cyan", padding=(0, 1)
        )

    # ---- log line helpers ----------------------------------------------

    def _print(self, message: str, style: str) -> None:
        line = Text(f"[{_timestamp()}] ", style="dim")
        line.append(message, style=style)
        if self._live is not None:
            self._live.console.print(line)
        else:
            self.console.print(line)

    def info(self, message: str) -> None:
        self._print(message, "cyan")

    def success(self, message: str) -> None:
        self._print(message, "green")

    def warn(self, message: str) -> None:
        self._print(message, "yellow")

    def error(self, message: str) -> None:
        self._print(message, "red")

    def heartbeat(self, message: str) -> None:
        # Dim line for idle polling ticks. Only shown when verbose to avoid
        # cluttering the terminal.
        if self.verbose:
            self._print(message, "bright_black")

    def debug(self, message: str) -> None:
        if self.verbose:
            self._print(message, "bright_black")

    # ---- summary --------------------------------------------------------

    def print_summary(self) -> None:
        uptime = _fmt_elapsed(self.status.uptime())
        total = self.status.total_continues

        summary = Table.grid(padding=(0, 2))
        summary.add_column(style="dim", justify="right")
        summary.add_column()
        summary.add_row("Runtime", uptime)
        summary.add_row("Auto-continues", Text(str(total), style="bold green"))
        summary.add_row("Thanks", Text("See you next session. 👋", style="cyan"))

        self.console.print()
        self.console.print(
            Panel(summary, title="Session summary", border_style="cyan", padding=(1, 2))
        )
