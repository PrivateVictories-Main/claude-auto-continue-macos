"""
Localhost control dashboard.

A small threaded HTTP server embedded in the monitor process exposes:

    GET  /                 — single-page app (see dashboard_ui.html)
    GET  /api/state        — full status + settings snapshot
    GET  /api/events       — text/event-stream of live events
    POST /api/settings     — mutate any subset of the Settings dataclass

The server binds to 127.0.0.1 by default so it is never exposed to the
network. Everything is dependency-free (stdlib only).
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import asdict, fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .config import Settings

HTML_PATH = Path(__file__).resolve().parent / "dashboard_ui.html"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


# ---------------------------------------------------------------------------
# Event bus — broadcast logs / status changes to SSE subscribers
# ---------------------------------------------------------------------------

class EventBus:
    """Tiny pub/sub with a rolling backlog for late subscribers."""

    def __init__(self, backlog: int = 200) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._recent: deque = deque(maxlen=backlog)

    def publish(self, event: dict) -> None:
        event = {**event, "ts": time.time()}
        with self._lock:
            self._recent.append(event)
            dead: list[queue.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subscribers.append(q)
            for event in list(self._recent):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    break
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Shared state between the Monitor and the Dashboard
# ---------------------------------------------------------------------------

class SharedState:
    """Thread-safe bundle of live settings + latest status."""

    _SETTABLE_FIELDS = {f.name for f in fields(Settings)}

    def __init__(
        self,
        settings: Settings,
        *,
        on_settings_change: Optional[Callable[[Settings], None]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self.settings = settings
        self.status: dict[str, Any] = {
            "state": "Starting…",
            "state_style": "yellow",
            "started_at": time.time(),
            "claude_detected": False,
            "ax_enabled": False,
            "total_continues": 0,
            "last_continue_at": None,
            "browsers_found": 0,
            "terminals_found": 0,
        }
        self.bus = EventBus()
        self.on_settings_change = on_settings_change

    # --- status --------------------------------------------------------

    def set_status(self, **kwargs: Any) -> None:
        with self._lock:
            self.status.update(kwargs)
        self.bus.publish({"type": "status", "status": self.status_snapshot()})

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            snap = dict(self.status)
        snap["uptime"] = max(0.0, time.time() - snap["started_at"])
        return snap

    # --- settings ------------------------------------------------------

    def settings_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self.settings)

    _NUMERIC_FIELDS = {"interval", "cooldown", "max_continues"}
    _BOOL_FIELDS = {
        "silent", "notifications", "log", "verbose", "dry_run",
        "scan_app", "scan_browsers", "scan_terminals",
    }
    _TUPLE_FIELDS = {
        "terminal_patterns", "extra_continue_labels", "extra_context_keywords",
    }

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        applied: dict[str, Any] = {}
        with self._lock:
            new = Settings(**asdict(self.settings))
            for key, value in patch.items():
                if key not in self._SETTABLE_FIELDS:
                    continue
                if key in self._NUMERIC_FIELDS:
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                elif key in self._BOOL_FIELDS:
                    if not isinstance(value, bool):
                        continue
                elif key in self._TUPLE_FIELDS:
                    if isinstance(value, list):
                        value = tuple(str(v) for v in value if isinstance(v, str))
                    else:
                        continue
                setattr(new, key, value)
                applied[key] = value
            new.validate()
            for key, value in applied.items():
                setattr(self.settings, key, value)
        if applied and self.on_settings_change:
            try:
                self.on_settings_change(self.settings)
            except Exception:  # pragma: no cover - defensive
                pass
        self.bus.publish({"type": "settings", "settings": self.settings_snapshot()})
        return applied

    def full_snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status_snapshot(),
            "settings": self.settings_snapshot(),
        }

    # --- log helper ----------------------------------------------------

    def publish_log(self, level: str, message: str) -> None:
        self.bus.publish({"type": "log", "level": level, "message": message})


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    state: SharedState  # set on the bound subclass

    # Silence default access logging; we already have the activity log.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    # ----- routing -----------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._serve_html()
        elif path == "/api/state":
            self._serve_json(self.state.full_snapshot())
        elif path == "/api/events":
            self._serve_sse()
        elif path == "/favicon.ico":
            self._serve_svg_favicon()
        else:
            self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/settings":
            self.send_error(404, "not found")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length > 65_536:
            self.send_error(413, "request body too large (64KB max)")
            return
        raw = self.rfile.read(length) if length else b""
        try:
            patch = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            self.send_error(400, f"invalid json: {exc}")
            return
        if not isinstance(patch, dict):
            self.send_error(400, "expected a JSON object")
            return

        try:
            applied = self.state.update_settings(patch)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return

        self._serve_json({
            "applied": applied,
            **self.state.full_snapshot(),
        })

    # ----- response helpers -------------------------------------------

    def _serve_html(self) -> None:
        try:
            text = HTML_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.send_error(500, "dashboard_ui.html missing")
            return
        from . import __version__ as pkg_version
        text = text.replace('id="version">v…</span>',
                            f'id="version">v{pkg_version}</span>')
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self, data: dict) -> None:
        body = json.dumps(data, default=_json_fallback).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_svg_favicon(self) -> None:
        # Simple Claude-orange star/asterisk. Tiny SVG, inlined.
        svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            b'<circle cx="50" cy="50" r="48" fill="#1F1E1C"/>'
            b'<path fill="#D97757" d="M50 12 L56 44 L88 50 L56 56 L50 88 '
            b'L44 56 L12 50 L44 44 Z"/></svg>'
        )
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(svg)))
        self.end_headers()
        self.wfile.write(svg)

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q = self.state.bus.subscribe()
        try:
            snap = {
                "type": "snapshot",
                **self.state.full_snapshot(),
            }
            self._sse_write(snap)
            while True:
                try:
                    event = q.get(timeout=15)
                except queue.Empty:
                    try:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    continue
                try:
                    self._sse_write(event)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
        finally:
            self.state.bus.unsubscribe(q)

    def _sse_write(self, event: dict) -> None:
        payload = json.dumps(event, default=_json_fallback)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()


def _json_fallback(obj: Any) -> Any:
    if isinstance(obj, tuple):
        return list(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


# ---------------------------------------------------------------------------
# Dashboard (public API)
# ---------------------------------------------------------------------------

class Dashboard:
    def __init__(
        self,
        state: SharedState,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self.state = state
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        host = self.host if self.host != "0.0.0.0" else "127.0.0.1"
        return f"http://{host}:{self.port}"

    def start(self) -> str:
        BoundHandler = type(
            "BoundDashboardHandler",
            (_Handler,),
            {"state": self.state},
        )
        server = ThreadingHTTPServer((self.host, self.port), BoundHandler)
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="claude-auto-continue-dashboard",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None


def try_start(
    state: SharedState,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    port_range: Iterable[int] = (),
) -> tuple[Optional[Dashboard], Optional[str]]:
    """Bind and start, falling back to additional ports if the first is taken.

    Returns (dashboard, error_message). On success, error_message is None.
    """
    candidates = [port, *port_range]
    last_error: Optional[str] = None
    for candidate in candidates:
        dash = Dashboard(state, host=host, port=candidate)
        try:
            dash.start()
            return dash, None
        except OSError as exc:
            last_error = f"{exc.strerror or exc} (port {candidate})"
            continue
    return None, last_error
