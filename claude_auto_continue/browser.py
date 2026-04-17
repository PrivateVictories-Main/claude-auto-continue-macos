"""
Browser scanner — finds Continue-on-tool-use-limit buttons inside claude.ai
tabs of any running browser, without requiring a browser extension.

Approach:
* Enumerate running apps whose bundle id matches a known browser.
* For each, flip AXEnhancedUserInterface on (Chromium hides the DOM from AX
  by default, similar to Electron's AXManualAccessibility). Safari exposes
  its DOM when "Allow apps to control this computer using accessibility
  features" is on, which Accessibility permission provides.
* Walk windows → tabs. For each web-content subtree, collect its URL from
  the `AXURL` attribute on an AXWebArea-like node. Skip subtrees whose URL
  is not a claude.ai origin.
* Within a claude.ai subtree, reuse the Continue-button heuristic from
  `accessibility.py`. No context-keyword gate — the URL filter already
  scopes to Claude pages, making detection immune to UI text changes.

We press found buttons via AXPress, same as the native-app path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional
from urllib.parse import urlparse

from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
)
from Cocoa import NSWorkspace

from . import accessibility as ax

CLAUDE_HOSTS = (
    "claude.ai",
    "www.claude.ai",
    "claude.anthropic.com",
)


# Known browser bundle IDs. Kept explicit for the fast path; a heuristic
# below catches unknown browsers (new forks, dev channels we haven't
# hard-coded) so we don't need updates every time a new Chromium fork
# ships.
BROWSER_BUNDLE_IDS = (
    "com.google.Chrome",
    "com.google.Chrome.beta",
    "com.google.Chrome.dev",
    "com.google.Chrome.canary",
    "com.apple.Safari",
    "com.apple.SafariTechnologyPreview",
    "com.brave.Browser",
    "com.brave.Browser.beta",
    "com.brave.Browser.nightly",
    "company.thebrowser.Browser",  # Arc
    "company.thebrowser.dia",  # Dia by The Browser Company
    "com.openai.atlas",  # ChatGPT Atlas
    "org.mozilla.firefox",
    "org.mozilla.firefoxdeveloperedition",
    "org.mozilla.nightly",
    "org.mozilla.librewolf",
    "net.waterfox.waterfox",
    "com.microsoft.edgemac",
    "com.microsoft.edgemac.Beta",
    "com.microsoft.edgemac.Dev",
    "com.microsoft.edgemac.Canary",
    "com.operasoftware.Opera",
    "com.operasoftware.OperaGX",
    "com.operasoftware.OperaNeon",
    "com.vivaldi.Vivaldi",
    "org.chromium.Chromium",
    "com.naver.Whale",
    "com.kagi.kagimacOS",  # Orion
    "com.kagi.Orion",
    "com.sidekick.Sidekick",
    "io.sigmaos.SigmaOS",
    "com.mighty.app",
    "com.epicbrowser.Epic",
    "com.maxthon.Maxthon",
    "com.yandex.desktop.browser",
    "com.duckduckgo.macos.browser",
)


# Strings that identify a browser bundle even if we don't know it by
# name. Checked as case-insensitive substrings. The check is only used
# when the exact bundle ID is not in BROWSER_BUNDLE_IDS, so false
# positives for non-browser apps that happen to contain "browser" in
# their id are fine — we'll still only click a Continue button inside
# a claude.ai AXWebArea.
_BROWSER_HEURISTIC_TOKENS = (
    "browser",
    "chrome",
    "chromium",
    "firefox",
    "safari",
    "webkit",
    "opera",
    "edge",
    "brave",
    "vivaldi",
    "arc",
    "duckduckgo",
    "orion",
    "whale",
)


def looks_like_browser(bundle_id: str) -> bool:
    lowered = (bundle_id or "").lower()
    if not lowered:
        return False
    return any(tok in lowered for tok in _BROWSER_HEURISTIC_TOKENS)


@dataclass
class BrowserApp:
    pid: int
    bundle_id: str
    name: str
    element: object  # AXUIElementRef


@dataclass
class BrowserCandidate:
    """A Continue button found inside a claude.ai web-view subtree."""

    element: object
    label: str
    browser_name: str
    browser_pid: int
    url: str


def find_browsers() -> list[BrowserApp]:
    """Return every running browser we recognise.

    We match in two ways: (1) exact bundle ID in ``BROWSER_BUNDLE_IDS``
    (the fast path for known browsers), and (2) the heuristic in
    ``looks_like_browser`` which catches brand-new forks or dev channels
    that ship after this list was last updated. Either match is enough —
    we only ever press Continue inside a claude.ai ``AXWebArea`` subtree,
    so a false positive is harmless.
    """
    workspace = NSWorkspace.sharedWorkspace()
    running = workspace.runningApplications()
    found: list[BrowserApp] = []
    for app in running:
        bid = app.bundleIdentifier()
        if not bid:
            continue
        if bid not in BROWSER_BUNDLE_IDS and not looks_like_browser(bid):
            continue
        # Skip helper / agent / accessory processes; they never host a
        # user-facing tab. ActivationPolicy 0 == NSApplicationActivationPolicyRegular.
        try:
            policy = int(app.activationPolicy())
        except Exception:
            policy = 0
        if policy != 0:
            continue
        pid = int(app.processIdentifier())
        element = AXUIElementCreateApplication(pid)
        found.append(
            BrowserApp(
                pid=pid,
                bundle_id=bid,
                name=app.localizedName() or bid,
                element=element,
            )
        )
    return found


def enable_enhanced_ax(browser: BrowserApp) -> bool:
    """Chromium/Firefox/Safari expose AX best when enhanced mode is on.

    Writing the attribute is idempotent and safe to retry on every scan.
    Returns True if either AXEnhancedUserInterface or AXManualAccessibility
    was set successfully — one or the other is right depending on browser.
    """
    ok_any = False
    for attr in ("AXEnhancedUserInterface", "AXManualAccessibility"):
        try:
            err = AXUIElementSetAttributeValue(browser.element, attr, True)
        except Exception:
            continue
        if err == 0:
            ok_any = True
    return ok_any


def _is_claude_url(url: str) -> bool:
    return _is_claude_url_ext(url, CLAUDE_HOSTS)


def _is_claude_url_ext(url: str, hosts: tuple[str, ...]) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


def _read_url(element) -> Optional[str]:
    """Pull a URL off an AX node (AXWebArea exposes AXURL)."""
    for attr in ("AXURL", "AXDocument"):
        value = ax._attr(element, attr)
        if value is None:
            continue
        # AXURL comes through as NSURL; str() on it gives the absolute URL.
        text = str(value).strip()
        if text.startswith(("http://", "https://")):
            return text
    return None


def _iter_web_subtrees(root) -> Iterable[tuple[object, str]]:
    """Yield (subtree_root, url) pairs for every web view under ``root``.

    We descend via the normal AX walk but stop recursing into a node once
    we've claimed it as a web subtree — the url applies to everything
    inside. This keeps each claude.ai tab self-contained and lets us skip
    non-Claude tabs cheaply.
    """
    for node, _depth in ax.walk(root, max_depth=ax.MAX_RECURSION_DEPTH):
        role = ax._element_role(node)
        if role in ("AXWebArea", "AXWebAreaRole"):
            url = _read_url(node) or ""
            yield node, url


def find_browser_continue_buttons(
    browser: BrowserApp,
    verbose_cb: Optional[Callable[[str], None]] = None,
    *,
    extra_labels: tuple[str, ...] = (),
    extra_hosts: tuple[str, ...] = (),
) -> list[BrowserCandidate]:
    """Return Continue candidates inside claude.ai tabs of this browser.

    No context-keyword gate — the URL filter already scopes to Claude
    pages, making detection immune to Anthropic rewording limit text.
    """
    all_hosts = CLAUDE_HOSTS + extra_hosts
    found: list[BrowserCandidate] = []
    windows = ax.get_windows(browser)

    for win_idx, window in enumerate(windows):
        if window is None:
            continue

        web_roots = list(_iter_web_subtrees(window))
        if verbose_cb:
            verbose_cb(f"  browser={browser.name} window[{win_idx}] web_areas={len(web_roots)}")
        if not web_roots:
            continue

        for web_root, url in web_roots:
            if not url or not _is_claude_url_ext(url, all_hosts):
                if verbose_cb and url:
                    verbose_cb(f"    skip non-claude tab: {url}")
                continue

            if verbose_cb:
                verbose_cb(f"    scan claude tab: {url}")

            for node, _depth in ax.walk(web_root, max_depth=ax.MAX_RECURSION_DEPTH):
                role = ax._element_role(node)
                label = ax._element_label(node)

                if ax._is_button(role) and ax._looks_like_continue(label, extra_labels):
                    found.append(
                        BrowserCandidate(
                            element=node,
                            label=label,
                            browser_name=browser.name,
                            browser_pid=browser.pid,
                            url=url,
                        )
                    )

    return found
