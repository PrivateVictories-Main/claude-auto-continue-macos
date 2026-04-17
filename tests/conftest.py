"""Shared pytest fixtures for claude-auto-continue tests."""

import pytest

from claude_auto_continue.config import Settings
from claude_auto_continue.logger import ActivityLog
from claude_auto_continue.notifications import Notifier
from claude_auto_continue.ui import TerminalUI


@pytest.fixture
def settings():
    """Default Settings instance."""
    return Settings()


@pytest.fixture
def ui():
    """TerminalUI with verbose off."""
    return TerminalUI(verbose=False)


@pytest.fixture
def notifier():
    """Silent notifier (no sound, no notifications)."""
    return Notifier(sound=False, notifications=False)


@pytest.fixture
def activity_log(tmp_path):
    """Enabled activity log writing to a temp directory."""
    log = ActivityLog(path=tmp_path / "activity.log", enabled=True)
    log.open()
    yield log
    log.close()
