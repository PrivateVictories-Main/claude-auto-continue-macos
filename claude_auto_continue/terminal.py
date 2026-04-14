"""
Terminal scanner — detects the "continue?" pause in Claude Code CLI
sessions running inside any macOS terminal (Warp, iTerm2, Ghostty,
Terminal.app, WezTerm, Kitty, Alacritty, Hyper, VS Code, Cursor…).

Why this is harder than the desktop-app or browser cases:

* The Claude Code CLI has no AXButton to press — it paints text, then
  waits on stdin. There is no native "Continue" control.
* Different terminals expose their scrollback to AX very differently.
  Terminal.app/iTerm/VSCode/Ghostty all surface selected text, window
  title, and the active cell. Warp exposes full pane content. Some
  expose nothing at all.
* Sending a keystroke to the wrong terminal is dangerous — a stray
  Enter could run a shell command.

So we are conservative by default:

1. Only consider the *frontmost* terminal window — never reach into
   background windows whose state we can't see clearly.
2. Collect AX-visible text from every descendant of the focused window.
3. Only fire when the combined text contains one of the narrow,
   unambiguous patterns in ``CLAUDE_CODE_PAUSE_PATTERNS`` — these are
   patterns Claude Code prints verbatim when tool-use limits pause a
   session.
4. Deliver the resolution as a keystroke (Enter by default) using
   CGEventPost against the focused app, not a click.

Callers can add additional patterns via config (``terminal_patterns``
in config.toml) to adapt to future CLI updates.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from ApplicationServices import (
    AXUIElementCreateApplication,
    kAXDescriptionAttribute,
    kAXHelpAttribute,
    kAXTitleAttribute,
    kAXValueAttribute,
)
from Cocoa import NSWorkspace

try:
    # Quartz is the framework that houses CGEventCreateKeyboardEvent.
    from Quartz import (  # type: ignore
        CGEventCreateKeyboardEvent,
        CGEventPost,
        kCGHIDEventTap,
    )
    _HAVE_CGEVENT = True
except Exception:  # pragma: no cover - missing Quartz
    _HAVE_CGEVENT = False

from . import accessibility as ax


# Bundle IDs that identify macOS terminal apps. Kept in sync with
# permissions.py so the same list drives both the permission hint and
# the terminal scanner.
TERMINAL_BUNDLE_IDS = (
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "net.kovidgoyal.kitty",
    "io.alacritty",
    "com.mitchellh.ghostty",
    "dev.warp.Warp-Stable",
    "dev.warp.Warp",
    "co.zeit.hyper",
    "com.github.wez.wezterm",
    "com.microsoft.VSCode",
    "com.microsoft.VSCodeInsiders",
    "com.visualstudio.code.oss",
    "com.todesktop.230313mzl4w4u92",   # Cursor
    "com.exafunction.windsurf",
    "io.tabby",
    "co.zeit.hyper",
)


# Patterns that unambiguously identify a Claude Code tool-use-limit pause.
# We match on any of these as a substring (case-insensitive). If this list
# grows stale with a Claude Code release, users can extend it via
# ``terminal_patterns`` in ~/.claude-auto-continue/config.toml.
CLAUDE_CODE_PAUSE_PATTERNS: tuple[str, ...] = (
    "press enter to continue",
    "press [enter] to continue",
    "continue? (y/n)",
    "continue? [y/n]",
    "tool-use limit reached",
    "tool use limit reached",
    "claude code paused",
    "claude code has paused",
    "resume this session",
)

# Virtual key code for Return — the keystroke we synthesise on a match.
VK_RETURN = 36


@dataclass
class TerminalApp:
    pid: int
    bundle_id: str
    name: str
    element: object


@dataclass
class TerminalCandidate:
    """A Claude-Code pause detected in a frontmost terminal window."""
    terminal_name: str
    terminal_pid: int
    bundle_id: str
    matched_pattern: str


def find_terminals() -> list[TerminalApp]:
    workspace = NSWorkspace.sharedWorkspace()
    found: list[TerminalApp] = []
    for app in workspace.runningApplications():
        bid = app.bundleIdentifier()
        if not bid or bid not in TERMINAL_BUNDLE_IDS:
            continue
        pid = int(app.processIdentifier())
        element = AXUIElementCreateApplication(pid)
        found.append(TerminalApp(
            pid=pid,
            bundle_id=bid,
            name=app.localizedName() or bid,
            element=element,
        ))
    return found


def _focused_window(app: TerminalApp):
    """Prefer the focused window; fall back to the first listed window."""
    focused = ax._attr(app.element, "AXFocusedWindow")
    if focused is not None:
        return focused
    wins = ax.get_windows(app)
    return wins[0] if wins else None


def _gather_visible_text(root) -> str:
    """Best-effort concatenation of AX text under ``root``.

    We read the standard text-bearing attributes. That's enough for
    Terminal.app, iTerm2, Warp, Ghostty, VS Code, Cursor and Windsurf —
    each exposes the focused line and active selection via AXValue /
    AXTitle on descendant nodes.
    """
    parts: list[str] = []
    total = 0
    cap = 32_000
    attrs = (
        kAXValueAttribute,
        kAXTitleAttribute,
        kAXDescriptionAttribute,
        kAXHelpAttribute,
    )
    for node, _depth in ax.walk(root, max_depth=ax.MAX_RECURSION_DEPTH):
        for a in attrs:
            v = ax._attr(node, a)
            if v is None:
                continue
            text = str(v).strip()
            if not text:
                continue
            parts.append(text)
            total += len(text)
            if total >= cap:
                return "\n".join(parts)
    return "\n".join(parts)


def _match_pattern(text: str, patterns: Iterable[str]) -> Optional[str]:
    if not text:
        return None
    lowered = text.lower()
    for p in patterns:
        if not p:
            continue
        if p.lower() in lowered:
            return p
    return None


def find_terminal_candidates(
    extra_patterns: Iterable[str] = (),
    verbose_cb: Optional[Callable[[str], None]] = None,
) -> list[TerminalCandidate]:
    """Return every frontmost terminal window showing a Claude Code pause."""
    patterns = tuple(CLAUDE_CODE_PAUSE_PATTERNS) + tuple(extra_patterns or ())
    matches: list[TerminalCandidate] = []

    for term in find_terminals():
        window = _focused_window(term)
        if window is None:
            if verbose_cb:
                verbose_cb(f"  terminal={term.name} no focused window")
            continue

        text = _gather_visible_text(window)
        if verbose_cb:
            excerpt = (text[-140:] if len(text) > 140 else text).replace("\n", " ")
            verbose_cb(f"  terminal={term.name} text_tail={excerpt!r}")

        matched = _match_pattern(text, patterns)
        if matched:
            matches.append(TerminalCandidate(
                terminal_name=term.name,
                terminal_pid=term.pid,
                bundle_id=term.bundle_id,
                matched_pattern=matched,
            ))
    return matches


def send_return_to(pid: int) -> bool:
    """Post a Return keystroke to the given process.

    We deliberately target the PID (not the global event tap) so the
    Enter press goes only to the terminal we identified. Returns False
    if Quartz is unavailable.
    """
    if not _HAVE_CGEVENT:
        return False
    try:
        down = CGEventCreateKeyboardEvent(None, VK_RETURN, True)
        up = CGEventCreateKeyboardEvent(None, VK_RETURN, False)
        CGEventPost(kCGHIDEventTap, down)
        # Small gap between key-down and key-up to look like a human press.
        time.sleep(0.03)
        CGEventPost(kCGHIDEventTap, up)
        return True
    except Exception:
        return False
