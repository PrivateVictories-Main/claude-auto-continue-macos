"""Tests for update_check.py — version comparison and PyPI fetch."""

import json
import threading
from unittest.mock import MagicMock, patch

from claude_auto_continue.update_check import (
    _fetch_latest,
    _parse_version,
    check_async,
)


class TestParseVersion:
    def test_simple(self):
        assert _parse_version("0.7.2") == (0, 7, 2)

    def test_two_part(self):
        assert _parse_version("1.0") == (1, 0)

    def test_trailing_text(self):
        assert _parse_version("1.2.3rc1") == (1, 2)

    def test_empty(self):
        assert _parse_version("") == ()

    def test_whitespace(self):
        assert _parse_version("  1.0.0  ") == (1, 0, 0)


class TestFetchLatest:
    @patch("claude_auto_continue.update_check.urlopen")
    def test_returns_version(self, mock_urlopen):
        body = json.dumps({"info": {"version": "9.9.9"}}).encode()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        assert _fetch_latest() == "9.9.9"

    @patch("claude_auto_continue.update_check.urlopen", side_effect=OSError)
    def test_returns_none_on_error(self, mock_urlopen):
        assert _fetch_latest() is None

    @patch("claude_auto_continue.update_check.urlopen")
    def test_returns_none_on_bad_status(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        assert _fetch_latest() is None


class TestCheckAsync:
    @patch("claude_auto_continue.update_check._fetch_latest", return_value="99.0.0")
    def test_calls_back_when_newer(self, mock_fetch):
        called = threading.Event()
        result = {}

        def cb(current, latest):
            result["current"] = current
            result["latest"] = latest
            called.set()

        check_async(cb)
        called.wait(timeout=2)
        assert called.is_set()
        assert result["latest"] == "99.0.0"

    @patch("claude_auto_continue.update_check._fetch_latest", return_value="0.0.1")
    def test_no_callback_when_older(self, mock_fetch):
        called = threading.Event()
        check_async(lambda c, l: called.set())
        called.wait(timeout=0.5)
        assert not called.is_set()

    @patch("claude_auto_continue.update_check._fetch_latest", return_value=None)
    def test_no_callback_on_fetch_fail(self, mock_fetch):
        called = threading.Event()
        check_async(lambda c, l: called.set())
        called.wait(timeout=0.5)
        assert not called.is_set()
