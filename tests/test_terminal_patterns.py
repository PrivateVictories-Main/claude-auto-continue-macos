"""Tests for terminal pause pattern matching including regex support."""

import pytest

from claude_auto_continue.terminal import (
    CLAUDE_CODE_PAUSE_PATTERNS,
    _match_pattern,
)

# --- Substring matching (plain patterns) ------------------------------------


class TestSubstringPatterns:
    @pytest.mark.parametrize(
        "text",
        [
            "Press Enter to continue",
            "press enter to continue",
            "PRESS ENTER TO CONTINUE",
            ">>> Press [Enter] to continue <<<",
            "Press Return to continue",
            "Hit enter to continue",
            "Hit Return to continue",
        ],
    )
    def test_enter_return_prompts(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "Continue? (Y/N)",
            "continue? [y/n]",
            "Continue? (y)",
            "Continue? [Y]",
            "Do you want to continue",
            "Would you like to continue",
        ],
    )
    def test_confirmation_prompts(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "Tool-use limit reached",
            "Tool use limit reached",
            "tool-use limit",
            "Tool Use Limit",
            "Reached its limit",
            "Reached the limit",
            "Usage limit",
        ],
    )
    def test_limit_phrasing(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "Claude Code paused",
            "Claude Code has paused",
            "Resume this session",
            "Session paused",
            "Waiting for confirmation",
        ],
    )
    def test_pause_resume_phrasing(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None


# --- Regex matching (re: prefix) --------------------------------------------


class TestRegexPatterns:
    @pytest.mark.parametrize(
        "text",
        [
            "Press  Enter  to  continue",
            "press [enter] to continue",
            "Press [Return] to continue",
            "press  [enter]  to  continue",
        ],
    )
    def test_flexible_enter_regex(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "continue? (y",
            "Continue?  [N",
            "continue? ( y",
        ],
    )
    def test_flexible_yn_regex(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "tool use limit",
            "tool-use limit",
            "Tool Use  Limit",
        ],
    )
    def test_flexible_tool_use_regex(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "paused — press continue to proceed",
            "waiting for you to continue",
            "paused, click continue",
        ],
    )
    def test_paused_waiting_continue_regex(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is not None


# --- No match (false positives) ---------------------------------------------


class TestNoMatch:
    @pytest.mark.parametrize(
        "text",
        [
            "Hello, how can I help you?",
            "I'll continue working on this task",
            "The function continues to the next line",
            "Press Escape to cancel",
            "Click OK to proceed",
            "",
            "   ",
        ],
    )
    def test_irrelevant_text_rejected(self, text):
        assert _match_pattern(text, CLAUDE_CODE_PAUSE_PATTERNS) is None


# --- Custom / extra patterns ------------------------------------------------


class TestExtraPatterns:
    def test_custom_plain_pattern(self):
        extras = ("my custom pause",)
        all_patterns = CLAUDE_CODE_PAUSE_PATTERNS + extras
        assert _match_pattern("my custom pause detected", all_patterns) is not None

    def test_custom_regex_pattern(self):
        extras = (r"re:custom\s+pause\s+\d+",)
        all_patterns = CLAUDE_CODE_PAUSE_PATTERNS + extras
        assert _match_pattern("custom pause 42", all_patterns) is not None
        assert _match_pattern("custom  pause  99", all_patterns) is not None

    def test_invalid_regex_skipped(self):
        extras = (r"re:[invalid(regex",)
        assert _match_pattern("anything", extras) is None


# --- Edge cases -------------------------------------------------------------


class TestEdgeCases:
    def test_none_text(self):
        assert _match_pattern("", CLAUDE_CODE_PAUSE_PATTERNS) is None

    def test_empty_patterns(self):
        assert _match_pattern("press enter to continue", ()) is None

    def test_empty_string_pattern_skipped(self):
        assert _match_pattern("anything", ("",)) is None

    def test_pattern_embedded_in_long_text(self):
        long_text = "x" * 5000 + " press enter to continue " + "x" * 5000
        assert _match_pattern(long_text, CLAUDE_CODE_PAUSE_PATTERNS) is not None


class TestRegexCaching:
    """Verify that compiled regex patterns are reused across calls."""

    def test_cached_regex_matches_consistently(self):
        pattern = ("re:press\\s+enter",)
        assert _match_pattern("press  enter to continue", pattern) is not None
        assert _match_pattern("press  enter to continue", pattern) is not None

    def test_invalid_regex_cached_as_none(self):
        from claude_auto_continue.terminal import _compile_regex

        assert _compile_regex("[invalid") is None
        assert _compile_regex("[invalid") is None
