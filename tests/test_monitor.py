"""Tests for monitor.py — cooldown logic, tick coordination, emit helpers."""

import time
from unittest.mock import MagicMock, patch

from claude_auto_continue.config import Settings
from claude_auto_continue.logger import ActivityLog
from claude_auto_continue.monitor import Monitor, MonitorContext
from claude_auto_continue.notifications import Notifier
from claude_auto_continue.ui import TerminalUI


def _make_ctx(**overrides) -> MonitorContext:
    defaults = dict(
        settings=Settings(),
        ui=TerminalUI(verbose=False),
        notifier=Notifier(sound=False, notifications=False),
        log=ActivityLog(enabled=False),
        stop=lambda: False,
        state=None,
        remote=None,
    )
    defaults.update(overrides)
    return MonitorContext(**defaults)


class TestCooldown:
    def test_no_cooldown_when_zero(self):
        ctx = _make_ctx(settings=Settings(cooldown=0))
        mon = Monitor(ctx)
        assert mon._in_cooldown(ctx.ui) is False

    def test_in_cooldown_after_click(self):
        ctx = _make_ctx(settings=Settings(cooldown=5.0))
        mon = Monitor(ctx)
        mon._last_click_at = time.monotonic()
        assert mon._in_cooldown(ctx.ui) is True

    def test_cooldown_expired(self):
        ctx = _make_ctx(settings=Settings(cooldown=0.01))
        mon = Monitor(ctx)
        mon._last_click_at = time.monotonic() - 1.0
        assert mon._in_cooldown(ctx.ui) is False


class TestEmit:
    def test_emit_with_no_state(self):
        ctx = _make_ctx(state=None)
        mon = Monitor(ctx)
        mon._emit("info", "test")

    def test_emit_with_state(self):
        state = MagicMock()
        ctx = _make_ctx(state=state)
        mon = Monitor(ctx)
        mon._emit("info", "hello")
        state.publish_log.assert_called_once_with("info", "hello")

    def test_emit_swallows_exception(self):
        state = MagicMock()
        state.publish_log.side_effect = RuntimeError("boom")
        ctx = _make_ctx(state=state)
        mon = Monitor(ctx)
        mon._emit("error", "test")


class TestSyncStatus:
    def test_sync_with_no_state(self):
        ctx = _make_ctx(state=None)
        mon = Monitor(ctx)
        mon._sync_status()

    def test_sync_sends_status(self):
        state = MagicMock()
        ctx = _make_ctx(state=state)
        mon = Monitor(ctx)
        mon._sync_status()
        state.set_status.assert_called_once()
        kwargs = state.set_status.call_args[1]
        assert "state" in kwargs
        assert "total_continues" in kwargs


class TestTickCoordination:
    """Test that _tick respects scan_app/scan_browsers/scan_terminals flags."""

    def test_tick_skips_browsers_when_disabled(self):
        ctx = _make_ctx(
            settings=Settings(scan_app=False, scan_browsers=False, scan_terminals=False)
        )
        mon = Monitor(ctx)
        with (
            patch.object(mon, "_scan_app") as mock_app,
            patch.object(mon, "_scan_browsers") as mock_br,
            patch.object(mon, "_scan_terminals") as mock_term,
        ):
            mon._tick()
        mock_app.assert_not_called()
        mock_br.assert_not_called()
        mock_term.assert_not_called()

    def test_tick_app_hit_skips_rest(self):
        ctx = _make_ctx(settings=Settings(scan_app=True, scan_browsers=True, scan_terminals=True))
        mon = Monitor(ctx)
        with (
            patch.object(mon, "_scan_app", return_value=True) as mock_app,
            patch.object(mon, "_scan_browsers") as mock_br,
            patch.object(mon, "_scan_terminals") as mock_term,
        ):
            mon._tick()
        mock_app.assert_called_once()
        mock_br.assert_not_called()
        mock_term.assert_not_called()

    def test_tick_browser_hit_skips_terminals(self):
        ctx = _make_ctx(settings=Settings(scan_app=False, scan_browsers=True, scan_terminals=True))
        mon = Monitor(ctx)
        with (
            patch.object(mon, "_scan_browsers", return_value=True) as mock_br,
            patch.object(mon, "_scan_terminals") as mock_term,
        ):
            mon._tick()
        mock_br.assert_called_once()
        mock_term.assert_not_called()

    def test_tick_falls_through_to_terminals(self):
        ctx = _make_ctx(settings=Settings(scan_app=False, scan_browsers=True, scan_terminals=True))
        mon = Monitor(ctx)
        with (
            patch.object(mon, "_scan_browsers", return_value=False) as mock_br,
            patch.object(mon, "_scan_terminals") as mock_term,
        ):
            mon._tick()
        mock_br.assert_called_once()
        mock_term.assert_called_once()


class TestDiag:
    def test_diag_writes_to_stderr(self, capsys):
        ctx = _make_ctx()
        mon = Monitor(ctx)
        mon._tick_count = 42
        mon._diag("test message")
        err = capsys.readouterr().err
        assert "DIAG" in err
        assert "tick#42" in err
        assert "test message" in err
