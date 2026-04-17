"""
Sound + Notification Center alerts for auto-continue events.

We try modern UNUserNotificationCenter first (macOS 10.14+) and fall back to
the deprecated NSUserNotification if the newer API is not usable from our
context (UN notifications require an app bundle identity in some macOS
versions, and plain Python scripts don't always have one).

Every function is best-effort: failures are silent because notifications
are a nice-to-have, not a correctness requirement.
"""

from __future__ import annotations

import subprocess
from typing import Optional


def _try_nssound(name: str = "Glass") -> bool:
    try:
        from AppKit import NSSound  # type: ignore
    except Exception:
        return False
    try:
        sound = NSSound.soundNamed_(name)
        if sound is None:
            return False
        sound.play()
        return True
    except Exception:
        return False


def _try_afplay(name: str = "Glass") -> bool:
    """Fallback: play the system sound via /usr/bin/afplay."""
    path = f"/System/Library/Sounds/{name}.aiff"
    try:
        subprocess.Popen(
            ["/usr/bin/afplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def play_sound(name: str = "Glass") -> None:
    """Play a named macOS system sound. Silent on failure."""
    if _try_nssound(name):
        return
    _try_afplay(name)


def _try_usernotification(title: str, body: str) -> bool:
    """Deprecated NSUserNotification path. Works from scripts without a bundle."""
    try:
        from Foundation import NSUserNotification, NSUserNotificationCenter  # type: ignore
    except Exception:
        return False
    try:
        note = NSUserNotification.alloc().init()
        note.setTitle_(title)
        note.setInformativeText_(body)
        center = NSUserNotificationCenter.defaultUserNotificationCenter()
        center.deliverNotification_(note)
        return True
    except Exception:
        return False


def _try_osascript(title: str, body: str) -> bool:
    """Final fallback: osascript `display notification`."""
    try:
        safe_title = title.replace('"', '\\"')
        safe_body = body.replace('"', '\\"')
        script = f'display notification "{safe_body}" with title "{safe_title}"'
        subprocess.Popen(
            ["/usr/bin/osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def send_notification(title: str, body: str) -> None:
    """Post a Notification Center alert. Silent on failure."""
    if _try_usernotification(title, body):
        return
    _try_osascript(title, body)


class Notifier:
    """Convenience wrapper that respects --silent and --no-notifications."""

    def __init__(
        self, *, sound: bool = True, notifications: bool = True, sound_name: str = "Glass"
    ) -> None:
        self.sound = sound
        self.notifications = notifications
        self.sound_name = sound_name

    def announce_continue(self, total: int, *, label: Optional[str] = None) -> None:
        if self.sound:
            play_sound(self.sound_name)
        if self.notifications:
            title = "Claude auto-continue"
            body = f"Auto-continued Claude — {total} total this session."
            if label:
                body = f"Clicked {label!r} — {total} total this session."
            send_notification(title, body)
