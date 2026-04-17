"""Tests for CLI argument parsing and config merge flow."""

import pytest
from claude_auto_continue.cli import build_parser, _args_to_dict


class TestArgParser:
    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.dry_run is None
        assert args.interval is None
        assert args.cooldown is None
        assert args.silent is None
        assert args.verbose is None
        assert args.setup is False
        assert args.menu_bar is False
        assert args.dashboard is True
        assert args.dashboard_port == 8787

    def test_dry_run(self):
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_interval(self):
        parser = build_parser()
        args = parser.parse_args(["--interval", "5.0"])
        assert args.interval == 5.0

    def test_no_browsers(self):
        parser = build_parser()
        args = parser.parse_args(["--no-browsers"])
        assert args.scan_browsers is False

    def test_terminals(self):
        parser = build_parser()
        args = parser.parse_args(["--terminals"])
        assert args.scan_terminals is True

    def test_no_app(self):
        parser = build_parser()
        args = parser.parse_args(["--no-app"])
        assert args.scan_app is False

    def test_menu_bar(self):
        parser = build_parser()
        args = parser.parse_args(["--menu-bar"])
        assert args.menu_bar is True

    def test_no_dashboard(self):
        parser = build_parser()
        args = parser.parse_args(["--no-dashboard"])
        assert args.dashboard is False

    def test_dashboard_port(self):
        parser = build_parser()
        args = parser.parse_args(["--dashboard-port", "9000"])
        assert args.dashboard_port == 9000

    def test_dashboard_host(self):
        parser = build_parser()
        args = parser.parse_args(["--dashboard-host", "0.0.0.0"])
        assert args.dashboard_host == "0.0.0.0"

    def test_max_continues(self):
        parser = build_parser()
        args = parser.parse_args(["--max-continues", "10"])
        assert args.max_continues == 10

    def test_cooldown(self):
        parser = build_parser()
        args = parser.parse_args(["--cooldown", "3.0"])
        assert args.cooldown == 3.0

    def test_silent(self):
        parser = build_parser()
        args = parser.parse_args(["--silent"])
        assert args.silent is True

    def test_no_notifications(self):
        parser = build_parser()
        args = parser.parse_args(["--no-notifications"])
        assert args.notifications is False

    def test_no_log(self):
        parser = build_parser()
        args = parser.parse_args(["--no-log"])
        assert args.log is False


class TestArgsToDict:
    def test_all_none_by_default(self):
        parser = build_parser()
        args = parser.parse_args([])
        d = _args_to_dict(args)
        assert d["dry_run"] is None
        assert d["interval"] is None
        assert d["cooldown"] is None
        assert d["silent"] is None

    def test_set_values_preserved(self):
        parser = build_parser()
        args = parser.parse_args(["--dry-run", "--interval", "2.0"])
        d = _args_to_dict(args)
        assert d["dry_run"] is True
        assert d["interval"] == 2.0
