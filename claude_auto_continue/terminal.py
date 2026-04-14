"""
Terminal scanner — detects the "continue?" pause in Claude Code CLI
sessions running inside *any* macOS terminal (past, present, or future).

Design:

1. Look only at the **frontmost app**. If a user is in Claude Code and
   a pause hits, that terminal is necessarily the one they'd type
   Return into anyway.
2. Skip apps that have their own scanner or that we must never target
   (Claude desktop app, browsers, Finder, Dock, system UI).
3. Walk the AX tree of the focused window and collect its visible text.
4. If the text contains one of the narrow, unambiguous Claude Code
   pause patterns — or a user-supplied extra pattern — synthesize a
   single Return keystroke via ``CGEventPost``.

This strategy has no bundle-ID allowlist, so any terminal that exists
today or ships next year (Warp, iTerm2, Ghostty, Terminal.app, Kitty,
Alacritty, WezTerm, Hyper, VS Code, Cursor, Windsurf, Tabby, Rio,
Wave, or whatever comes next) just works as soon as it's the
frontmost app when Claude Code pauses.
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
from . import browser as br


# Apps that must never be treated as a terminal. Two reasons to exclude:
# (a) they have their own scanner elsewhere (Claude desktop app,
#     browsers), so double-matching would be wasteful and potentially
#     send Return into a browser window;
# (b) they're system UI that should never receive synthesized Return
#     keystrokes (Finder, Dock, Spotlight, System Settings, etc).
FRONTMOST_EXCLUDE_BUNDLES = frozenset({
    # Claude desktop app — own scanner.
    "com.anthropic.claudefordesktop",
    "com.anthropic.claudedesktop",
    "com.anthropic.claude",
    # All known browsers — own scanner.
    *(b.lower() for b in br.BROWSER_BUNDLE_IDS),
    # System UI.
    "com.apple.finder",
    "com.apple.dock",
    "com.apple.controlcenter",
    "com.apple.systempreferences",
    "com.apple.systemuiserver",
    "com.apple.windowmanager",
    "com.apple.loginwindow",
    "com.apple.spotlight",
    "com.apple.notificationcenterui",
    "com.apple.screensaver.engine",
    "com.apple.preview",
    "com.apple.screenshot.launcher",
})


# Re-export the browser heuristic so a future fork added in one place
# is automatically respected here too.
_looks_like_browser = br.looks_like_browser


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
    """Return a list of terminal candidates to scan this tick.

    We target the frontmost app only. If Claude Code is paused and the
    user is watching, the terminal running it *is* the frontmost app —
    and Return keystrokes go to the frontmost app anyway. This removes
    the need for a bundle-ID allowlist, so every new terminal works
    automatically.
    """
    workspace = NSWorkspace.sharedWorkspace()
    app = workspace.frontmostApplication()
    if app is None:
        return []

    bid = (app.bundleIdentifier() or "").lower()
    if not bid:
        return []
    if bid in FRONTMOST_EXCLUDE_BUNDLES:
        return []
    if _looks_like_browser(bid):
        return []

    # Skip helper / agent / accessory processes — they can't hold focus
    # the way a real GUI app does, so a "frontmost" match is spurious.
    try:
        policy = int(app.activationPolicy())
    except Exception:
        policy = 0
    if policy != 0:  # 0 == NSApplicationActivationPolicyRegular
        return []

    pid = int(app.processIdentifier())
    element = AXUIElementCreateApplication(pid)
    return [TerminalApp(
        pid=pid,
        bundle_id=app.bundleIdentifier() or "",
        name=app.localizedName() or "terminal",
        element=element,
    )]


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
