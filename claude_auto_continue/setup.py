"""
Interactive first-run walkthrough: `claude-auto-continue --setup`.

New users — especially those who just cloned the repo from GitHub — rarely
know that Accessibility permission has to be granted to the *Python
interpreter* when running under a LaunchAgent. This module walks them
through it end to end: opens the right System Settings pane, spins while
polling for the grant, optionally installs the LaunchAgent, and runs a
self-test against the Claude app.

Designed to be run interactively; if stdout is not a TTY, `run_setup`
degrades to a concise plain-text script so CI / headless use still works.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Confirm
from rich.status import Status
from rich.table import Table
from rich.text import Text

from . import __version__
from . import accessibility as ax
from .permissions import detect_terminal

ACCESSIBILITY_PANE_URL = (
    "x-apple.systempreferences:com.apple.preference.security?"
    "Privacy_Accessibility"
)


def _repo_root() -> Path:
    """Repo root so we can invoke scripts/install-launchagent.sh."""
    return Path(__file__).resolve().parent.parent


def _python_path() -> str:
    return sys.executable


def _launch_agent_label() -> str:
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "user"
    return f"com.{user}.claude-auto-continue"


def _open_accessibility_pane() -> bool:
    """Pop System Settings directly to the Accessibility list."""
    try:
        subprocess.run(
            ["open", ACCESSIBILITY_PANE_URL],
            check=False,
            capture_output=True,
            timeout=5,
        )
        return True
    except Exception:
        return False


def _is_launch_agent_loaded() -> bool:
    label = _launch_agent_label()
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{label}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run_install_script(console: Console) -> bool:
    script = _repo_root() / "scripts" / "install-launchagent.sh"
    if not script.is_file():
        console.print(
            Text(f"install script not found at {script}", style="red")
        )
        return False
    console.print(Text(f"running {script}", style="dim"))
    proc = subprocess.run([str(script)], capture_output=True, text=True)
    if proc.stdout:
        console.print(Text(proc.stdout.rstrip(), style="dim"))
    if proc.returncode != 0:
        if proc.stderr:
            console.print(Text(proc.stderr.rstrip(), style="red"))
        return False
    return True


def _step_header(console: Console, n: int, total: int, title: str) -> None:
    bar = Text(f"  Step {n} of {total}  ", style="bold white on cyan")
    heading = Text(f"  {title}", style="bold cyan")
    console.print()
    console.print(bar, heading)


def _welcome_panel() -> Panel:
    title = Text("claude-auto-continue", style="bold cyan")
    title.append(f"  v{__version__}", style="dim")
    body = Group(
        Align.center(title),
        Align.center(Text("First-run setup", style="dim")),
        Text(""),
        Text(
            "This wizard grants macOS Accessibility permission to the\n"
            "Python interpreter that runs this tool, then optionally\n"
            "installs it as a background service so you never have to\n"
            "remember to start it again.",
            style="white",
        ),
        Text(""),
        Text(
            "What this tool can and cannot do with that permission:",
            style="bold",
        ),
        Text("  • read UI element labels (the same thing VoiceOver sees)"),
        Text("  • click the Continue button on tool-use-limit prompts"),
        Text(
            "  • nothing else — no screen capture, no keystrokes, no files,",
            style="dim",
        ),
        Text("    no clipboard, no network requests, no telemetry.", style="dim"),
    )
    return Panel(
        body,
        border_style="cyan",
        padding=(1, 2),
        title="[dim]welcome[/dim]",
        title_align="center",
    )


def _permission_panel(python_path: str) -> Panel:
    body = Group(
        Text(
            "macOS won't let us read the Claude app's buttons until you\n"
            "grant Accessibility permission to the Python interpreter\n"
            "below. This is a one-time step.",
            style="white",
        ),
        Text(""),
        Text("Interpreter path (copy this):", style="bold"),
        Panel(Text(python_path, style="bold green"), border_style="green",
              padding=(0, 1)),
        Text(""),
        Text("Instructions:", style="bold"),
        Text("  1. System Settings should have just opened at the"),
        Text("     Privacy & Security → Accessibility pane."),
        Text("  2. Click the  +  button at the bottom of the app list."),
        Text("     (You may need to unlock with Touch ID or password.)"),
        Text("  3. Press  Cmd + Shift + G  to get the \"Go to Folder\" field."),
        Text("  4. Paste the interpreter path above and press Enter."),
        Text("  5. Click  Open , then flip the toggle to ON."),
        Text(""),
        Text(
            "macOS resolves the venv symlink to the real Python binary —\n"
            "the entry will read something like \"python3.14\". That's\n"
            "expected and correct.",
            style="dim",
        ),
    )
    return Panel(
        body,
        border_style="yellow",
        padding=(1, 2),
        title="[bold yellow]accessibility permission needed[/bold yellow]",
        title_align="left",
    )


def _wait_for_permission(console: Console, timeout: int = 300) -> bool:
    """Spin while polling; return True the moment permission flips on."""
    deadline = time.monotonic() + timeout
    message = "waiting for the Accessibility toggle to flip on…"
    with Status(message, console=console, spinner="dots") as status:
        while time.monotonic() < deadline:
            if ax.is_process_trusted(prompt=False):
                return True
            remaining = int(deadline - time.monotonic())
            mins, secs = divmod(remaining, 60)
            status.update(f"{message}  ({mins:02d}:{secs:02d} remaining)")
            time.sleep(1)
    return ax.is_process_trusted(prompt=False)


def _self_test(console: Console) -> tuple[bool, str]:
    """Try to locate Claude and flip AXManualAccessibility on it."""
    app = ax.find_claude_app()
    if app is None:
        return False, (
            "Claude app is not running. Open it and the tool will pick it "
            "up automatically — no action needed here."
        )
    ok = ax.enable_manual_accessibility(app)
    if not ok:
        return False, (
            f"Detected Claude (pid {app.pid}) but failed to enable its "
            "accessibility tree. This usually means permission is not yet "
            "granted to the running interpreter."
        )
    return True, f"Detected Claude (pid {app.pid}) and enabled its AX tree."


def _finale_panel(
    service_installed: bool,
    self_test_msg: str,
    self_test_ok: bool,
) -> Panel:
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right", no_wrap=True)
    rows.add_column()

    rows.add_row(
        "Permission",
        Text("granted", style="bold green"),
    )
    rows.add_row(
        "Claude self-test",
        Text(
            self_test_msg,
            style="green" if self_test_ok else "yellow",
        ),
    )
    rows.add_row(
        "Background service",
        Text(
            "installed and running" if service_installed else "not installed",
            style="green" if service_installed else "dim",
        ),
    )

    commands = Table.grid(padding=(0, 2))
    commands.add_column(style="bold cyan", no_wrap=True)
    commands.add_column(style="dim")
    commands.add_row("claude-auto-continue", "run once in this terminal")
    commands.add_row("claude-auto-continue --dry-run", "preview without clicking")
    commands.add_row("./scripts/status.sh", "check the background service")
    commands.add_row(
        "tail -f ~/.claude-auto-continue/launchd.out.log",
        "follow live logs",
    )
    commands.add_row(
        "./scripts/uninstall-launchagent.sh",
        "remove the background service",
    )

    body = Group(
        rows,
        Text(""),
        Text("Handy commands:", style="bold"),
        commands,
        Text(""),
        Text(
            "You're all set. Walk away from a long Claude session and come\n"
            "back to finished work instead of a paused screen.",
            style="green",
        ),
    )

    return Panel(
        body,
        border_style="green",
        padding=(1, 2),
        title="[bold green]setup complete[/bold green]",
        title_align="left",
    )


def _headless_setup(console: Console) -> int:
    """Plain-text fallback for non-TTY environments."""
    console.print("claude-auto-continue setup (non-interactive)")
    console.print(f"  python interpreter: {_python_path()}")
    console.print(f"  launch agent label: {_launch_agent_label()}")
    console.print(
        "  grant Accessibility to the interpreter above in:"
    )
    console.print(
        "    System Settings -> Privacy & Security -> Accessibility"
    )
    console.print(
        "  then run  ./scripts/install-launchagent.sh  to install the"
        " background service."
    )
    return 0


def run_setup() -> int:
    """Interactive walkthrough. Returns process exit code."""
    console = Console()

    if not console.is_terminal:
        return _headless_setup(console)

    console.print()
    console.print(_welcome_panel())

    total_steps = 3
    python_path = _python_path()

    # -------- Step 1: Accessibility permission ------------------------------
    _step_header(console, 1, total_steps, "Grant Accessibility permission")

    if ax.is_process_trusted(prompt=False):
        console.print(
            Text(
                "✓ permission already granted to this interpreter — skipping.",
                style="green",
            )
        )
    else:
        console.print(_permission_panel(python_path))
        console.print()
        opened = _open_accessibility_pane()
        if opened:
            console.print(
                Text(
                    "→ opened System Settings to the Accessibility pane.",
                    style="dim",
                )
            )
        else:
            console.print(
                Text(
                    "couldn't open System Settings automatically. Open it "
                    "yourself: Privacy & Security → Accessibility.",
                    style="yellow",
                )
            )

        console.print()
        granted = _wait_for_permission(console, timeout=600)
        if not granted:
            console.print(
                Panel(
                    Text(
                        "Timed out waiting for the toggle to flip on.\n"
                        "That's fine — grant permission whenever you're "
                        "ready and re-run `claude-auto-continue --setup`.",
                        style="yellow",
                    ),
                    border_style="yellow",
                    padding=(1, 2),
                    title="[yellow]paused[/yellow]",
                )
            )
            return 2

        console.print(
            Text("✓ permission granted.", style="bold green")
        )

    # -------- Step 2: LaunchAgent -------------------------------------------
    _step_header(console, 2, total_steps, "Install as a background service")

    already_loaded = _is_launch_agent_loaded()
    if already_loaded:
        console.print(
            Text(
                "✓ LaunchAgent is already loaded. Reinstalling would restart "
                "it with fresh code.",
                style="green",
            )
        )
        want_install = Confirm.ask(
            "Reinstall and restart the service now?",
            default=False,
            console=console,
        )
    else:
        console.print(
            Text(
                "The background service auto-starts at login, survives\n"
                "reboots, and auto-restarts if it ever crashes. You can\n"
                "uninstall it any time with ./scripts/uninstall-launchagent.sh.",
                style="white",
            )
        )
        want_install = Confirm.ask(
            "Install the background service?",
            default=True,
            console=console,
        )

    service_installed = already_loaded
    if want_install:
        ok = _run_install_script(console)
        service_installed = ok
        if ok:
            console.print(Text("✓ service installed.", style="bold green"))
        else:
            console.print(
                Text(
                    "service install failed — see output above. You can "
                    "still run the CLI directly.",
                    style="yellow",
                )
            )

    # -------- Step 3: self-test ---------------------------------------------
    _step_header(console, 3, total_steps, "Self-test against the Claude app")
    self_test_ok, self_test_msg = _self_test(console)
    style = "green" if self_test_ok else "yellow"
    console.print(Text(self_test_msg, style=style))

    # -------- Finale --------------------------------------------------------
    console.print()
    console.print(
        _finale_panel(
            service_installed=service_installed,
            self_test_msg=self_test_msg,
            self_test_ok=self_test_ok,
        )
    )
    return 0
