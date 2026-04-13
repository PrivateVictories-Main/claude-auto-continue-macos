"""
CLI entry point — argparse, config loading, signal handlers, and wiring
of every subsystem (UI, monitor, logger, notifier, permissions).
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .config import CONFIG_PATH, Settings, load_file, merge
from .logger import ActivityLog, DEFAULT_HOME
from .monitor import Monitor, MonitorContext
from .notifications import Notifier
from .permissions import detect_terminal, has_permission, setup_instructions
from .ui import TerminalUI


EXAMPLES = """\
examples:
  claude-auto-continue                          # default 3-second polling
  claude-auto-continue --dry-run                # test without clicking
  claude-auto-continue --silent --no-notifications
  claude-auto-continue --interval 5             # slower polling
  claude-auto-continue --max-continues 10       # stop after 10 continues
  claude-auto-continue --verbose                # show tree scans

config file (optional): ~/.claude-auto-continue/config.toml
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-auto-continue",
        description=(
            "Automatically click the 'Continue' button in the Claude macOS "
            "desktop app when tool-use limits pause your session."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=None,
        help="Show when a click would happen without actually clicking.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        metavar="SECONDS",
        default=None,
        help="Polling interval in seconds (default 3, min 1, max 30).",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        metavar="SECONDS",
        default=None,
        help="Minimum seconds between clicks (default 5).",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        default=None,
        help="Disable the notification sound on auto-continue.",
    )
    parser.add_argument(
        "--no-notifications",
        dest="notifications",
        action="store_false",
        default=None,
        help="Disable macOS Notification Center alerts.",
    )
    parser.add_argument(
        "--max-continues",
        type=int,
        metavar="N",
        default=None,
        help="Stop after this many auto-continues (default: unlimited).",
    )
    parser.add_argument(
        "--no-log",
        dest="log",
        action="store_false",
        default=None,
        help="Disable writing to ~/.claude-auto-continue/activity.log.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=None,
        help="Print AX tree scans and heartbeat ticks.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        default=None,
        help=f"Path to TOML config (default: {CONFIG_PATH}).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _first_run_notice(ui: TerminalUI) -> None:
    """Create ~/.claude-auto-continue/ on first run and print a short note."""
    if DEFAULT_HOME.exists():
        return
    DEFAULT_HOME.mkdir(parents=True, exist_ok=True)
    ui.info(f"first run — created {DEFAULT_HOME} for logs and config")
    ui.info(f"to set defaults, create {CONFIG_PATH}")


def _args_to_dict(args: argparse.Namespace) -> dict:
    """Translate argparse Namespace into a dict for config.merge().

    argparse defaults are None so we can distinguish 'not provided' from
    'explicitly set to False'.
    """
    return {
        "dry_run": args.dry_run,
        "interval": args.interval,
        "cooldown": args.cooldown,
        "silent": args.silent,
        "notifications": args.notifications,
        "max_continues": args.max_continues,
        "log": args.log,
        "verbose": args.verbose,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load TOML first so CLI can override it.
    file_values = load_file(args.config) if args.config else load_file()
    try:
        settings = merge(_args_to_dict(args), file_values)
    except ValueError as exc:
        parser.error(str(exc))

    ui = TerminalUI(verbose=settings.verbose)

    # Permission gate — print friendly guide and exit if missing.
    if not has_permission():
        terminal = detect_terminal()
        if ui.console.is_terminal:
            # Interactive terminal: full banner + step-by-step guide.
            ui.show_banner()
            _first_run_notice(ui)
            ui.warn(
                f"Accessibility permission is not granted for {terminal.name}."
            )
            ui.console.print()
            ui.console.print(setup_instructions(terminal))
        else:
            # Headless (launchd / pipe / CI): one concise line so log stays
            # readable even when KeepAlive restarts us every 10 seconds.
            import sys
            python_path = sys.executable
            ui.error(
                "Accessibility permission missing. Grant it to the Python "
                f"interpreter: {python_path}  "
                "(System Settings -> Privacy & Security -> Accessibility)"
            )
        return 2

    ui.show_banner()
    _first_run_notice(ui)

    notifier = Notifier(
        sound=not settings.silent,
        notifications=settings.notifications,
    )
    log = ActivityLog(enabled=settings.log)
    log.open()

    stopped = {"value": False}

    def _request_stop(signum, frame):  # signal handler
        stopped["value"] = True

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    ui.start_dashboard()

    ctx = MonitorContext(
        settings=settings,
        ui=ui,
        notifier=notifier,
        log=log,
        stop=lambda: stopped["value"],
    )
    monitor = Monitor(ctx)

    # Mirror the session-start line into the log.
    log.session_start(
        pid=0,  # Claude pid (0 until we find it)
        interval=settings.interval,
        dry_run=settings.dry_run,
    )

    try:
        monitor.run()
    finally:
        ui.stop_dashboard()
        log.session_end(
            total=ui.status.total_continues,
            uptime_seconds=ui.status.uptime(),
        )
        log.close()
        ui.print_summary()

    return 0


if __name__ == "__main__":
    sys.exit(main())
