"""
Fetch pattern overrides from GitHub so new button labels, context keywords,
and terminal patterns can ship without a code update.

On startup the agent tries to download ``patterns.json`` from the repo's
default branch. If the fetch fails (no network, GitHub down, timeout), the
agent silently falls back to built-in patterns — remote is strictly additive.

The fetched data is cached to ``~/.claude-auto-continue/patterns_cache.json``
so subsequent starts within the TTL don't hit the network at all.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .logger import DEFAULT_HOME

REMOTE_URL = (
    "https://raw.githubusercontent.com/"
    "PrivateVictories-Main/claude-auto-continue-macos/main/patterns.json"
)

CACHE_PATH = DEFAULT_HOME / "patterns_cache.json"
CACHE_TTL_SECONDS = 3600 * 6  # 6 hours
FETCH_TIMEOUT_SECONDS = 4


@dataclass
class RemotePatterns:
    continue_labels: tuple[str, ...] = ()
    context_keywords: tuple[str, ...] = ()
    terminal_patterns: tuple[str, ...] = ()
    browser_hosts: tuple[str, ...] = ()
    claude_bundle_ids: tuple[str, ...] = ()
    browser_bundle_ids: tuple[str, ...] = ()
    browser_heuristic_tokens: tuple[str, ...] = ()
    source: str = "none"


def _parse(data: dict[str, Any]) -> RemotePatterns:
    def _tup(key: str) -> tuple[str, ...]:
        val = data.get(key)
        if isinstance(val, list):
            return tuple(str(v) for v in val if v)
        return ()

    return RemotePatterns(
        continue_labels=_tup("continue_labels"),
        context_keywords=_tup("context_keywords"),
        terminal_patterns=_tup("terminal_patterns"),
        browser_hosts=_tup("browser_hosts"),
        claude_bundle_ids=_tup("claude_bundle_ids"),
        browser_bundle_ids=_tup("browser_bundle_ids"),
        browser_heuristic_tokens=_tup("browser_heuristic_tokens"),
    )


def _read_cache() -> Optional[dict[str, Any]]:
    if not CACHE_PATH.is_file():
        return None
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        fetched_at = raw.get("_fetched_at", 0)
        if time.time() - fetched_at > CACHE_TTL_SECONDS:
            return None
        return raw
    except Exception:
        return None


def _write_cache(data: dict[str, Any]) -> None:
    try:
        DEFAULT_HOME.mkdir(parents=True, exist_ok=True)
        data["_fetched_at"] = time.time()
        CACHE_PATH.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 1.0


def _fetch_remote(verbose_cb=None) -> Optional[dict[str, Any]]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(REMOTE_URL, headers={"User-Agent": "claude-auto-continue"})
            with urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
                if resp.status != 200:
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, OSError, json.JSONDecodeError):
            if attempt < MAX_RETRIES:
                if verbose_cb:
                    verbose_cb(f"remote patterns: fetch attempt {attempt} failed, retrying")
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return None
        except Exception:
            return None
    return None


def fetch(verbose_cb=None) -> RemotePatterns:
    """Return merged remote patterns (cached or freshly fetched).

    Never raises — returns an empty RemotePatterns on any failure.
    """
    cached = _read_cache()
    if cached is not None:
        if verbose_cb:
            verbose_cb("remote patterns: using cache")
        rp = _parse(cached)
        rp.source = "cache"
        return rp

    if verbose_cb:
        verbose_cb(f"remote patterns: fetching from {REMOTE_URL}")
    data = _fetch_remote(verbose_cb=verbose_cb)
    if data is None:
        if verbose_cb:
            verbose_cb("remote patterns: fetch failed, using built-in only")
        return RemotePatterns(source="fetch-failed")

    _write_cache(data)
    rp = _parse(data)
    rp.source = "remote"
    if verbose_cb:
        verbose_cb(f"remote patterns: fetched v{data.get('version', '?')}")
    return rp
