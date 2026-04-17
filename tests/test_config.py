"""Tests for config module — Settings validation, TOML loading, merge logic."""

import pytest

from claude_auto_continue.config import Settings, load_file, merge


class TestSettingsValidation:
    def test_default_settings_valid(self):
        s = Settings()
        s.validate()

    def test_interval_too_low(self):
        s = Settings(interval=0.1)
        with pytest.raises(ValueError, match="interval"):
            s.validate()

    def test_interval_too_high(self):
        s = Settings(interval=60.0)
        with pytest.raises(ValueError, match="interval"):
            s.validate()

    def test_interval_boundary_low(self):
        s = Settings(interval=0.5)
        s.validate()

    def test_interval_boundary_high(self):
        s = Settings(interval=30.0)
        s.validate()

    def test_cooldown_negative(self):
        s = Settings(cooldown=-1)
        with pytest.raises(ValueError, match="cooldown"):
            s.validate()

    def test_cooldown_zero_valid(self):
        s = Settings(cooldown=0)
        s.validate()

    def test_max_continues_negative(self):
        s = Settings(max_continues=-1)
        with pytest.raises(ValueError, match="max-continues"):
            s.validate()

    def test_max_continues_zero_means_unlimited(self):
        s = Settings(max_continues=0)
        s.validate()


class TestMerge:
    def test_cli_overrides_file(self):
        cli = {"interval": 5.0}
        file = {"interval": 2.0}
        s = merge(cli, file)
        assert s.interval == 5.0

    def test_file_used_when_cli_is_none(self):
        cli = {"interval": None}
        file = {"interval": 2.0}
        s = merge(cli, file)
        assert s.interval == 2.0

    def test_unknown_keys_ignored(self):
        cli = {}
        file = {"nonexistent_key": True, "interval": 2.0}
        s = merge(cli, file)
        assert s.interval == 2.0

    def test_list_to_tuple_coercion(self):
        cli = {}
        file = {"terminal_patterns": ["pattern1", "pattern2"]}
        s = merge(cli, file)
        assert s.terminal_patterns == ("pattern1", "pattern2")

    def test_extra_labels_coercion(self):
        cli = {}
        file = {"extra_continue_labels": ["custom"]}
        s = merge(cli, file)
        assert s.extra_continue_labels == ("custom",)

    def test_empty_merge(self):
        s = merge({}, {})
        assert s.interval == 1.5
        assert s.cooldown == 5.0

    def test_validation_runs_on_merge(self):
        cli = {"interval": 0.01}
        with pytest.raises(ValueError):
            merge(cli, {})

    def test_all_bool_flags(self):
        cli = {
            "silent": True,
            "notifications": False,
            "log": False,
            "verbose": True,
            "dry_run": True,
            "scan_app": False,
            "scan_browsers": False,
            "scan_terminals": True,
        }
        s = merge(cli, {})
        assert s.silent is True
        assert s.notifications is False
        assert s.log is False
        assert s.verbose is True
        assert s.dry_run is True
        assert s.scan_app is False
        assert s.scan_browsers is False
        assert s.scan_terminals is True


class TestLoadFile:
    def test_missing_file_returns_empty(self, tmp_path):
        result = load_file(tmp_path / "nonexistent.toml")
        assert result == {}

    def test_valid_toml(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text("interval = 2.0\nsilent = true\n")
        result = load_file(f)
        assert result["interval"] == 2.0
        assert result["silent"] is True

    def test_invalid_toml_returns_empty(self, tmp_path):
        f = tmp_path / "bad.toml"
        f.write_text("this is not valid toml {{{")
        result = load_file(f)
        assert result == {}
