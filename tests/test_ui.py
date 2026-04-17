"""Tests for ui.py — Status dataclass and formatting helpers."""

import threading

from claude_auto_continue.ui import Status, TerminalUI, _fmt_elapsed, build_banner


class TestFmtElapsed:
    def test_seconds_only(self):
        assert _fmt_elapsed(45) == "45s"

    def test_minutes_and_seconds(self):
        assert _fmt_elapsed(125) == "2m 05s"

    def test_hours(self):
        assert _fmt_elapsed(3661) == "1h 01m 01s"

    def test_zero(self):
        assert _fmt_elapsed(0) == "0s"

    def test_negative_clamped(self):
        assert _fmt_elapsed(-10) == "0s"


class TestStatus:
    def test_defaults(self):
        s = Status()
        assert s.state == "Starting…"
        assert s.total_continues == 0
        assert s.last_continue_at is None
        assert s.claude_detected is False

    def test_uptime_positive(self):
        s = Status()
        assert s.uptime() >= 0

    def test_since_last_none(self):
        s = Status()
        assert s.since_last() is None

    def test_increment_continues(self):
        s = Status()
        n = s.increment_continues()
        assert n == 1
        assert s.total_continues == 1
        assert s.last_continue_at is not None

    def test_increment_continues_sequential(self):
        s = Status()
        s.increment_continues()
        s.increment_continues()
        n = s.increment_continues()
        assert n == 3

    def test_since_last_after_increment(self):
        s = Status()
        s.increment_continues()
        since = s.since_last()
        assert since is not None
        assert since < 1.0

    def test_thread_safe_increment(self):
        s = Status()
        results = []

        def inc():
            for _ in range(100):
                results.append(s.increment_continues())

        threads = [threading.Thread(target=inc) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert s.total_continues == 400
        assert len(set(results)) == 400


class TestBuildBanner:
    def test_returns_panel(self):
        from rich.panel import Panel

        banner = build_banner()
        assert isinstance(banner, Panel)


class TestTerminalUI:
    def test_create_ui(self):
        ui = TerminalUI(verbose=True)
        assert ui.verbose is True
        assert ui.status.total_continues == 0

    def test_non_verbose_heartbeat_silent(self):
        ui = TerminalUI(verbose=False)
        ui.heartbeat("test")

    def test_stop_dashboard_when_not_started(self):
        ui = TerminalUI()
        ui.stop_dashboard()
