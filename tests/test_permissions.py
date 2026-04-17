"""Tests for permissions.py — terminal detection from environment."""

import os
from unittest.mock import patch

from claude_auto_continue.permissions import TerminalInfo, detect_terminal


class TestDetectTerminal:
    def test_known_bundle_id(self):
        with patch.dict(os.environ, {"__CFBundleIdentifier": "com.googlecode.iterm2"}):
            info = detect_terminal()
        assert info.name == "iTerm"
        assert info.bundle_id == "com.googlecode.iterm2"

    def test_unknown_bundle_id(self):
        with patch.dict(os.environ, {"__CFBundleIdentifier": "org.example.fancyterm"}):
            info = detect_terminal()
        assert info.name == "Fancyterm"
        assert info.bundle_id == "org.example.fancyterm"

    def test_warp_bundle(self):
        with patch.dict(os.environ, {"__CFBundleIdentifier": "dev.warp.warp-stable"}):
            info = detect_terminal()
        assert info.name == "Warp"

    def test_vscode_bundle(self):
        with patch.dict(os.environ, {"__CFBundleIdentifier": "com.microsoft.vscode"}):
            info = detect_terminal()
        assert info.name == "Visual Studio Code"

    def test_fallback_to_term_program(self):
        env = {"__CFBundleIdentifier": "", "TERM_PROGRAM": "Ghostty"}
        with patch.dict(os.environ, env, clear=False):
            info = detect_terminal()
        assert info.name == "Ghostty"
        assert info.bundle_id is None

    def test_fallback_generic(self):
        env = {"__CFBundleIdentifier": "", "TERM_PROGRAM": ""}
        with patch.dict(os.environ, env, clear=False):
            info = detect_terminal()
        assert info.name == "your terminal app"
        assert info.bundle_id is None

    def test_case_insensitive_bundle_lookup(self):
        with patch.dict(os.environ, {"__CFBundleIdentifier": "COM.APPLE.TERMINAL"}):
            info = detect_terminal()
        assert info.name == "Terminal"


class TestTerminalInfo:
    def test_dataclass_fields(self):
        info = TerminalInfo(name="Test", bundle_id="com.test")
        assert info.name == "Test"
        assert info.bundle_id == "com.test"

    def test_optional_bundle(self):
        info = TerminalInfo(name="Test", bundle_id=None)
        assert info.bundle_id is None
