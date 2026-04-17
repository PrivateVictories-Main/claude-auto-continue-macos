"""Tests for the activity log writer."""

import pytest
from claude_auto_continue.logger import ActivityLog


class TestActivityLog:
    def test_disabled_log_writes_nothing(self, tmp_path):
        log_file = tmp_path / "activity.log"
        log = ActivityLog(path=log_file, enabled=False)
        log.open()
        log.auto_continue(1)
        log.close()
        assert not log_file.exists()

    def test_enabled_log_writes(self, tmp_path):
        log_file = tmp_path / "activity.log"
        log = ActivityLog(path=log_file, enabled=True)
        log.open()
        log.session_start(pid=123, interval=1.5, dry_run=False)
        log.auto_continue(1, surface="desktop-app", source="Claude window 0")
        log.dry_run_hit(2, surface="browser", source="Chrome — claude.ai")
        log.note("test note")
        log.session_end(total=2, uptime_seconds=60.0)
        log.close()

        content = log_file.read_text()
        assert "session start" in content
        assert "pid=123" in content
        assert "Auto-continue #1" in content
        assert "surface=desktop-app" in content
        assert "DRY RUN" in content
        assert "test note" in content
        assert "session end" in content
        assert "total_continues=2" in content

    def test_double_close_safe(self, tmp_path):
        log_file = tmp_path / "activity.log"
        log = ActivityLog(path=log_file, enabled=True)
        log.open()
        log.close()
        log.close()

    def test_write_without_open_is_noop(self, tmp_path):
        log_file = tmp_path / "activity.log"
        log = ActivityLog(path=log_file, enabled=True)
        log.auto_continue(1)
        assert not log_file.exists()

    def test_creates_parent_directory(self, tmp_path):
        log_file = tmp_path / "subdir" / "deep" / "activity.log"
        log = ActivityLog(path=log_file, enabled=True)
        log.open()
        log.note("hello")
        log.close()
        assert log_file.exists()

    def test_surface_and_source_optional(self, tmp_path):
        log_file = tmp_path / "activity.log"
        log = ActivityLog(path=log_file, enabled=True)
        log.open()
        log.auto_continue(1)
        log.close()
        content = log_file.read_text()
        assert "Auto-continue #1 triggered" in content
        assert "surface=" not in content
