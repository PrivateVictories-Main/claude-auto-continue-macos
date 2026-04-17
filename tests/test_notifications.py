"""Tests for notifications.py — sound and notification dispatch."""

from unittest.mock import MagicMock, patch

from claude_auto_continue.notifications import (
    Notifier,
    _try_afplay,
    _try_osascript,
    play_sound,
    send_notification,
)


class TestPlaySound:
    @patch("claude_auto_continue.notifications._try_nssound", return_value=True)
    def test_nssound_preferred(self, mock_ns):
        play_sound("Glass")
        mock_ns.assert_called_once_with("Glass")

    @patch("claude_auto_continue.notifications._try_nssound", return_value=False)
    @patch("claude_auto_continue.notifications._try_afplay", return_value=True)
    def test_falls_back_to_afplay(self, mock_af, mock_ns):
        play_sound("Glass")
        mock_af.assert_called_once_with("Glass")


class TestTryAfplay:
    @patch("claude_auto_continue.notifications.subprocess.Popen")
    def test_calls_afplay_with_path(self, mock_popen):
        result = _try_afplay("Basso")
        assert result is True
        args = mock_popen.call_args[0][0]
        assert args[0] == "/usr/bin/afplay"
        assert "Basso" in args[1]

    @patch("claude_auto_continue.notifications.subprocess.Popen", side_effect=OSError)
    def test_returns_false_on_error(self, mock_popen):
        assert _try_afplay() is False


class TestTryOsascript:
    @patch("claude_auto_continue.notifications.subprocess.Popen")
    def test_calls_osascript(self, mock_popen):
        result = _try_osascript("Title", "Body text")
        assert result is True
        args = mock_popen.call_args[0][0]
        assert args[0] == "/usr/bin/osascript"

    @patch("claude_auto_continue.notifications.subprocess.Popen", side_effect=OSError)
    def test_returns_false_on_error(self, mock_popen):
        assert _try_osascript("T", "B") is False

    @patch("claude_auto_continue.notifications.subprocess.Popen")
    def test_escapes_double_quotes(self, mock_popen):
        _try_osascript('He said "hello"', 'She said "goodbye"')
        script_arg = mock_popen.call_args[0][0][2]
        assert '\\"hello\\"' in script_arg
        assert '\\"goodbye\\"' in script_arg


class TestSendNotification:
    @patch("claude_auto_continue.notifications._try_usernotification", return_value=True)
    def test_prefers_nsnotification(self, mock_ns):
        send_notification("T", "B")
        mock_ns.assert_called_once_with("T", "B")

    @patch("claude_auto_continue.notifications._try_usernotification", return_value=False)
    @patch("claude_auto_continue.notifications._try_osascript", return_value=True)
    def test_falls_back_to_osascript(self, mock_osa, mock_ns):
        send_notification("T", "B")
        mock_osa.assert_called_once_with("T", "B")


class TestNotifier:
    def test_sound_enabled(self):
        n = Notifier(sound=True, notifications=False)
        with patch("claude_auto_continue.notifications.play_sound") as mock:
            n.announce_continue(1)
        mock.assert_called_once()

    def test_sound_disabled(self):
        n = Notifier(sound=False, notifications=False)
        with patch("claude_auto_continue.notifications.play_sound") as mock:
            n.announce_continue(1)
        mock.assert_not_called()

    def test_notification_enabled(self):
        n = Notifier(sound=False, notifications=True)
        with patch("claude_auto_continue.notifications.send_notification") as mock:
            n.announce_continue(3, label="Continue")
        mock.assert_called_once()
        body = mock.call_args[0][1]
        assert "Continue" in body
        assert "3" in body

    def test_notification_disabled(self):
        n = Notifier(sound=False, notifications=False)
        with patch("claude_auto_continue.notifications.send_notification") as mock:
            n.announce_continue(1)
        mock.assert_not_called()

    def test_custom_sound_name(self):
        n = Notifier(sound=True, notifications=False, sound_name="Basso")
        with patch("claude_auto_continue.notifications.play_sound") as mock:
            n.announce_continue(1)
        mock.assert_called_once_with("Basso")
