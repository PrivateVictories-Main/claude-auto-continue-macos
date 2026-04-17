"""
Low-level macOS Accessibility (AX) bindings.

This module talks directly to the C-level AXUIElement API exposed by the
ApplicationServices framework through pyobjc. We deliberately avoid wrapper
libraries like `atomacos` so the surface area stays tiny and auditable.

Key responsibilities:

* Locate the running Claude desktop app and return its AXUIElement.
* Programmatically enable Electron's AXManualAccessibility flag so the
  accessibility tree becomes readable (Electron apps disable AX by default).
* Walk windows and children, looking for the tool-use-limit "Continue" button.
* Press that button via the AXPress action.

All functions return simple Python values or `None` on failure and log
to a caller-provided logger rather than raising, so a transient AX error
does not crash the polling loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from ApplicationServices import (
    AXIsProcessTrustedWithOptions,
    AXUIElementCopyAttributeNames,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementPerformAction,
    AXUIElementSetAttributeValue,
    kAXChildrenAttribute,
    kAXDescriptionAttribute,
    kAXFocusedWindowAttribute,
    kAXHelpAttribute,
    kAXRoleAttribute,
    kAXTitleAttribute,
    kAXTrustedCheckOptionPrompt,
    kAXValueAttribute,
    kAXWindowsAttribute,
)
from Cocoa import NSWorkspace

# Context keywords that confirm a "Continue" button belongs to the tool-use
# limit pause and not some unrelated UI element. Matching is case-insensitive
# and substring-based.
TOOL_USE_CONTEXT_KEYWORDS = (
    "tool-use limit",
    "tool use limit",
    "tool-use",
    "tool use",
    "reached its limit",
    "reached the limit",
    "limit reached",
    "usage limit",
    "rate limit",
    "continue with tool",
    "continue using tools",
    "pause",
    "paused",
    "waiting for confirmation",
    "session paused",
    "generation paused",
    "conversation paused",
)

CONTINUE_LABELS = (
    "continue",
    "continue with tool use",
    "continue generation",
    "continue generating",
    "continue conversation",
    "continue session",
    "continue chat",
    "resume",
    "resume generation",
    "resume generating",
    "resume conversation",
    "resume session",
    "resume chat",
    "keep going",
    "proceed",
    "yes, continue",
    "yes continue",
    "confirm",
)

# Maximum tree depth we will traverse. Claude is an Electron app whose
# React DOM is reflected into the AX tree, so the Continue button sits
# around depth 17 with plenty of groups wrapping it. 40 is a safe cap
# that handles the real app with room to spare while still bounding work.
MAX_RECURSION_DEPTH = 40


@dataclass
class ClaudeApp:
    """Handle to a running Claude desktop app."""

    pid: int
    bundle_id: Optional[str]
    name: str
    element: object  # AXUIElementRef (opaque to Python)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def is_process_trusted(prompt: bool = False) -> bool:
    """Return True if this process has Accessibility permission.

    Pass ``prompt=True`` once to trigger the system prompt if not trusted;
    we default to False so we can present our own friendly guide first.
    """
    options = {kAXTrustedCheckOptionPrompt: bool(prompt)}
    return bool(AXIsProcessTrustedWithOptions(options))


# ---------------------------------------------------------------------------
# Finding the Claude app
# ---------------------------------------------------------------------------

# Bundle IDs we try in order. Anthropic has not published a single stable ID
# across channels, so we match by name as a fallback.
_CANDIDATE_BUNDLE_IDS = (
    "com.anthropic.claudefordesktop",
    "com.anthropic.claudedesktop",
    "com.anthropic.claude",
)
_CANDIDATE_NAMES = ("Claude",)


def find_claude_app() -> Optional[ClaudeApp]:
    """Locate the running Claude desktop app, or return None."""
    workspace = NSWorkspace.sharedWorkspace()
    running = workspace.runningApplications()

    # First pass: exact bundle ID match.
    for app in running:
        bid = app.bundleIdentifier()
        if bid and bid in _CANDIDATE_BUNDLE_IDS:
            return _build_claude_app(app)

    # Second pass: match by localized name.
    for app in running:
        name = app.localizedName()
        if name in _CANDIDATE_NAMES:
            return _build_claude_app(app)

    return None


def _build_claude_app(ns_app) -> ClaudeApp:
    pid = int(ns_app.processIdentifier())
    element = AXUIElementCreateApplication(pid)
    return ClaudeApp(
        pid=pid,
        bundle_id=ns_app.bundleIdentifier(),
        name=ns_app.localizedName() or "Claude",
        element=element,
    )


# ---------------------------------------------------------------------------
# Electron AXManualAccessibility enable
# ---------------------------------------------------------------------------


def enable_manual_accessibility(app: ClaudeApp) -> bool:
    """Set AXManualAccessibility=True on the app element.

    Electron disables accessibility by default. Setting this documented
    attribute flips it on so the AX tree populates. Returns True on success.
    Safe to call repeatedly; calling again after Claude restarts is required.
    """
    err = AXUIElementSetAttributeValue(app.element, "AXManualAccessibility", True)
    return err == 0


# ---------------------------------------------------------------------------
# Attribute reads and tree traversal
# ---------------------------------------------------------------------------


def _attr(element, name) -> object:
    """Read a single AX attribute. Returns None on any failure."""
    try:
        err, value = AXUIElementCopyAttributeValue(element, name, None)
    except Exception:
        return None
    if err != 0:
        return None
    return value


def attribute_names(element) -> tuple[str, ...]:
    """List every attribute an element exposes (used in --verbose mode)."""
    try:
        err, names = AXUIElementCopyAttributeNames(element, None)
    except Exception:
        return ()
    if err != 0 or not names:
        return ()
    return tuple(str(n) for n in names)


def get_windows(app: ClaudeApp) -> list:
    """Return the list of window elements for the app."""
    wins = _attr(app.element, kAXWindowsAttribute)
    if not wins:
        focused = _attr(app.element, kAXFocusedWindowAttribute)
        return [focused] if focused is not None else []
    return list(wins)


def walk(element, max_depth: int = MAX_RECURSION_DEPTH) -> Iterator[tuple[object, int]]:
    """Depth-first walk of an element and its descendants."""
    yield element, 0
    if max_depth <= 0:
        return
    stack: list[tuple[object, int]] = [(element, 0)]
    while stack:
        node, depth = stack.pop()
        if depth >= max_depth:
            continue
        children = _attr(node, kAXChildrenAttribute) or []
        for child in children:
            yield child, depth + 1
            stack.append((child, depth + 1))


# ---------------------------------------------------------------------------
# Button detection
# ---------------------------------------------------------------------------


@dataclass
class ButtonCandidate:
    element: object
    label: str
    role: str
    window_index: int


def _element_label(element) -> str:
    """Best-effort readable label for an element."""
    for attr in (kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute, kAXHelpAttribute):
        value = _attr(element, attr)
        if value:
            text = str(value).strip()
            if text:
                return text
    return ""


def _element_role(element) -> str:
    role = _attr(element, kAXRoleAttribute)
    return str(role) if role else ""


def _is_button(role: str) -> bool:
    return role in ("AXButton", "AXMenuItem", "AXRadioButton") or "Button" in role


def _looks_like_continue(label: str, extra_labels: tuple[str, ...] = ()) -> bool:
    if not label:
        return False
    lower = label.strip().lower()
    all_labels = CONTINUE_LABELS + extra_labels
    if lower in all_labels:
        return True
    for prefix in ("continue", "resume", "proceed", "keep going"):
        if lower.startswith(prefix) and len(lower) <= 50:
            tail = lower[len(prefix) :]
            if not tail or tail[0] == " ":
                return True
    return False


def find_continue_buttons(
    app: ClaudeApp,
    verbose_cb: Optional[Callable[[str], None]] = None,
    *,
    require_context: bool = True,
    extra_labels: tuple[str, ...] = (),
    extra_keywords: tuple[str, ...] = (),
) -> list[ButtonCandidate]:
    """Return every Continue-looking button in the app's windows.

    When ``require_context`` is True (browser scanner, safety guard),
    a window only yields matches if both a Continue button AND a
    tool-use-limit keyword are present. When False (Claude desktop
    app — the app itself IS the context), any Continue button in any
    window is returned directly.
    """
    found: list[ButtonCandidate] = []
    windows = get_windows(app)
    text_attrs = (kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute, kAXHelpAttribute)
    max_context_chars = 8000
    all_keywords = TOOL_USE_CONTEXT_KEYWORDS + extra_keywords

    for idx, window in enumerate(windows):
        if window is None:
            continue

        candidates_this_window: list[ButtonCandidate] = []
        context_chars = 0
        has_context = False
        node_count = 0

        for node, depth in walk(window):
            node_count += 1
            role = _element_role(node)

            if _is_button(role):
                label = _element_label(node)
                if verbose_cb:
                    verbose_cb(f"  button@d{depth} role={role!r} label={label!r}")
                if _looks_like_continue(label, extra_labels):
                    candidates_this_window.append(
                        ButtonCandidate(
                            element=node,
                            label=label,
                            role=role,
                            window_index=idx,
                        )
                    )

            if require_context and not has_context and context_chars < max_context_chars:
                for attr in text_attrs:
                    value = _attr(node, attr)
                    if value is None:
                        continue
                    text = str(value).strip()
                    if not text:
                        continue
                    context_chars += len(text)
                    lowered = text.lower()
                    if any(kw in lowered for kw in all_keywords):
                        has_context = True
                        break

        if verbose_cb:
            verbose_cb(
                f"window[{idx}] nodes={node_count} "
                f"continue_candidates={len(candidates_this_window)} "
                f"tool_use_context={'yes' if has_context else 'no'}"
            )

        if candidates_this_window:
            if not require_context or has_context:
                found.extend(candidates_this_window)
            elif verbose_cb:
                verbose_cb(
                    f"window[{idx}] found Continue button(s) but no "
                    "tool-use-limit context — skipping"
                )

    return found


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------


def press(element) -> bool:
    """Perform AXPress on an element. Returns True on success."""
    try:
        err = AXUIElementPerformAction(element, "AXPress")
    except Exception:
        return False
    return err == 0
