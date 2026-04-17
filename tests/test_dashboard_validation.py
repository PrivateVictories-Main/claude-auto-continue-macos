"""Tests for dashboard settings input validation."""

import pytest
from claude_auto_continue.config import Settings
from claude_auto_continue.dashboard import SharedState


class TestSettingsTypeValidation:
    def test_rejects_string_for_numeric_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"interval": "five"})
        assert applied == {}
        assert state.settings.interval == 1.5

    def test_rejects_string_for_bool_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"silent": "yes"})
        assert applied == {}
        assert state.settings.silent is False

    def test_rejects_int_for_bool_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"verbose": 1})
        assert applied == {}

    def test_rejects_bool_for_numeric_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"interval": True})
        assert applied == {}

    def test_accepts_int_for_numeric_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"cooldown": 10})
        assert applied == {"cooldown": 10}

    def test_accepts_float_for_numeric_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"interval": 3.0})
        assert applied == {"interval": 3.0}

    def test_accepts_bool_for_bool_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"silent": True})
        assert applied == {"silent": True}

    def test_rejects_non_list_for_tuple_field(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"terminal_patterns": "not a list"})
        assert applied == {}

    def test_tuple_field_filters_non_strings(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings(
            {"terminal_patterns": ["good", 123, None, "also good"]}
        )
        assert applied["terminal_patterns"] == ("good", "also good")

    def test_mixed_valid_and_invalid(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({
            "interval": 5.0,
            "silent": "nope",
            "verbose": True,
        })
        assert "interval" in applied
        assert "silent" not in applied
        assert "verbose" in applied
