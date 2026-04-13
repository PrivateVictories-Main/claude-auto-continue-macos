"""
macOS Accessibility permission check + friendly setup guide.

The tool requires that the *terminal* running us has been granted
Accessibility permission in System Settings. If not, we print a clear,
step-by-step guide naming the exact terminal app, instead of crashing
with a cryptic "AXError -25204".
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

from .accessibility import is_process_trusted


# Map bundle IDs or process names to human-friendly terminal names. Keys are
# lowercased; we check env vars, the parent process, and common bundles.
_TERMINAL_BUNDLES: dict[str, str] = {
    "com.apple.terminal": "Terminal",
    "com.googlecode.iterm2": "iTerm",
    "net.kovidgoyal.kitty": "kitty",
    "io.alacritty": "Alacritty",
    "com.mitchellh.ghostty": "Ghostty",
    "dev.warp.warp-stable": "Warp",
    "dev.warp.warp": "Warp",
    "co.zeit.hyper": "Hyper",
    "com.github.wez.wezterm": "WezTerm",
    "com.microsoft.vscode": "Visual Studio Code",
    "com.microsoft.vscode.insiders": "Visual Studio Code - Insiders",
    "com.visualstudio.code.oss": "VS Code (OSS)",
    "com.todesktop.230313mzl4w4u92": "Cursor",
    "com.exafunction.windsurf": "Windsurf",
}


@dataclass
class TerminalInfo:
    name: str
    bundle_id: Optional[str]


def detect_terminal() -> TerminalInfo:
    """Guess which terminal app is hosting this Python process."""
    # __CFBundleIdentifier is set by macOS for GUI-launched apps; shells inherit it.
    bundle = os.environ.get("__CFBundleIdentifier", "").strip()
    if bundle:
        friendly = _TERMINAL_BUNDLES.get(bundle.lower())
        if friendly:
            return TerminalInfo(name=friendly, bundle_id=bundle)
        return TerminalInfo(name=bundle.split(".")[-1].title(), bundle_id=bundle)

    # Fall back to TERM_PROGRAM which most terminals set explicitly.
    term_program = os.environ.get("TERM_PROGRAM", "").strip()
    if term_program:
        return TerminalInfo(name=term_program, bundle_id=None)

    return TerminalInfo(name="your terminal app", bundle_id=None)


def has_permission() -> bool:
    """Without prompting, return True if we already have AX permission."""
    return is_process_trusted(prompt=False)


def setup_instructions(terminal: Optional[TerminalInfo] = None) -> str:
    """Return a multi-line, human-readable guide for granting permission."""
    term = terminal or detect_terminal()
    return (
        "This tool needs macOS Accessibility permission to read the Claude\n"
        "app's UI and click the Continue button. It does NOT read your screen,\n"
        "your files, your clipboard, or your conversation content — only UI\n"
        "element labels, the same way VoiceOver does.\n"
        "\n"
        "How to grant it:\n"
        "  1. Open  System Settings\n"
        "  2. Go to  Privacy & Security  →  Accessibility\n"
        "  3. Click the  +  button (you may need to unlock with your password)\n"
        f"  4. Add  {term.name}  to the list\n"
        f"  5. Make sure the toggle next to  {term.name}  is ON\n"
        "  6. Quit and reopen the terminal, then re-run claude-auto-continue\n"
        "\n"
        "Tip: if you use multiple terminals (Warp, iTerm, Terminal, Ghostty,\n"
        "etc.), each one needs its own permission grant.\n"
    )


def exit_with_guide(printer=print, code: int = 2) -> None:
    """Print the guide and exit cleanly (used by cli.py on permission fail)."""
    printer(setup_instructions())
    sys.exit(code)
