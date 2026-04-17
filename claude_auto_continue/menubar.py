"""
macOS menu bar status icon for claude-auto-continue.

Shows a small coloured dot in the menu bar:
  - Green:  watching (Claude detected, scanning)
  - Yellow: waiting for Claude to appear
  - Red:    error or permissions issue

Clicking the icon opens a dropdown with live status, continue count,
uptime, and quick actions (open dashboard, toggle dry-run, quit).

The menu bar requires an NSApplication run loop on the main thread.
The monitor runs in a background thread and pushes state updates to
the menu bar via a thread-safe callback.
"""

from __future__ import annotations

import time
import webbrowser
from typing import Callable, Optional

import objc
from Cocoa import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSSize,
    NSStatusBar,
    NSTimer,
    NSVariableStatusItemLength,
)
from objc import python_method


def _make_dot_image(color: str) -> NSImage:
    """Create a tiny coloured circle as an NSImage for the status bar."""
    from AppKit import NSBezierPath, NSColor

    size = NSSize(18, 18)
    image = NSImage.alloc().initWithSize_(size)
    image.lockFocus()

    colors = {
        "green": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.25, 0.78, 0.45, 1.0),
        "yellow": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.75, 0.15, 1.0),
        "red": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.90, 0.25, 0.25, 1.0),
        "gray": NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.55, 0.55, 1.0),
    }
    fill = colors.get(color, colors["gray"])
    fill.setFill()

    circle = NSBezierPath.bezierPathWithOvalInRect_(((4, 4), (10, 10)))
    circle.fill()

    image.unlockFocus()
    image.setTemplate_(False)
    return image


def _format_uptime(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{hours}h {mins}m"


class MenuBarDelegate(NSObject):
    """Cocoa delegate that owns the NSStatusItem and refreshes it."""

    def init(self):
        self = objc.super(MenuBarDelegate, self).init()
        if self is None:
            return None
        self._status_item = None
        self._menu = None
        self._state_label = "Initializing..."
        self._color = "gray"
        self._continues = 0
        self._started_at = time.time()
        self._dashboard_url = None
        self._dry_run = False
        self._quit_callback = None
        self._dot_cache = {}
        return self

    @python_method
    def setup(self, quit_callback: Callable, dashboard_url: Optional[str] = None):
        self._quit_callback = quit_callback
        self._dashboard_url = dashboard_url

        status_bar = NSStatusBar.systemStatusBar()
        self._status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)

        self._dot_cache = {c: _make_dot_image(c) for c in ("green", "yellow", "red", "gray")}
        self._status_item.button().setImage_(self._dot_cache["gray"])
        self._status_item.button().setToolTip_("claude-auto-continue")

        self._build_menu()
        self._status_item.setMenu_(self._menu)

    @python_method
    def update_state(
        self,
        color: str,
        label: str,
        continues: int,
        dry_run: bool = False,
        dashboard_url: Optional[str] = None,
    ):
        self._color = color
        self._state_label = label
        self._continues = continues
        self._dry_run = dry_run
        if dashboard_url is not None:
            self._dashboard_url = dashboard_url

    def refreshMenu_(self, timer):
        if self._status_item is None:
            return
        img = self._dot_cache.get(self._color, self._dot_cache["gray"])
        self._status_item.button().setImage_(img)
        self._build_menu()
        self._status_item.setMenu_(self._menu)

    @python_method
    def _build_menu(self):
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        state_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Status: {self._state_label}", None, ""
        )
        state_item.setEnabled_(False)
        menu.addItem_(state_item)

        uptime = _format_uptime(time.time() - self._started_at)
        uptime_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Uptime: {uptime}", None, ""
        )
        uptime_item.setEnabled_(False)
        menu.addItem_(uptime_item)

        count_text = f"Continues: {self._continues}"
        if self._dry_run:
            count_text += " (dry run)"
        count_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(count_text, None, "")
        count_item.setEnabled_(False)
        menu.addItem_(count_item)

        menu.addItem_(NSMenuItem.separatorItem())

        if self._dashboard_url:
            dash_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Open Dashboard", "openDashboard:", ""
            )
            dash_item.setTarget_(self)
            menu.addItem_(dash_item)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit claude-auto-continue", "quitApp:", "q"
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._menu = menu

    def openDashboard_(self, sender):
        if self._dashboard_url:
            webbrowser.open(self._dashboard_url)

    def quitApp_(self, sender):
        if self._quit_callback:
            self._quit_callback()
        app = NSApplication.sharedApplication()
        app.terminate_(self)


class MenuBar:
    """High-level wrapper that starts the NSApp on the main thread.

    Usage::

        mb = MenuBar(quit_callback=request_stop)
        mb.set_dashboard_url("http://127.0.0.1:8787")
        # call from any thread:
        mb.update(color="green", label="Watching", continues=3)
        # blocks on main thread:
        mb.run()  # runs NSApp.run() — call from main thread
    """

    def __init__(self, quit_callback: Callable):
        self._quit_callback = quit_callback
        self._delegate = None
        self._dashboard_url = None
        self._app = None

    def set_dashboard_url(self, url: str) -> None:
        self._dashboard_url = url

    def update(self, color: str, label: str, continues: int, dry_run: bool = False) -> None:
        if self._delegate is not None:
            self._delegate.update_state(
                color=color,
                label=label,
                continues=continues,
                dry_run=dry_run,
                dashboard_url=self._dashboard_url,
            )

    def run(self) -> None:
        """Start the Cocoa event loop. Must be called from the main thread."""
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self._app = app

        delegate = MenuBarDelegate.alloc().init()
        delegate.setup(
            quit_callback=self._quit_callback,
            dashboard_url=self._dashboard_url,
        )
        self._delegate = delegate

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, delegate, "refreshMenu:", None, True
        )

        app.run()

    def stop(self) -> None:
        if self._app is not None:
            self._app.terminate_(None)
