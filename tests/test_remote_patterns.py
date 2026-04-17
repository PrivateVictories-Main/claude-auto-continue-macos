"""Tests for remote_patterns module — parsing, caching, fallback."""

import json
import time

import pytest
from claude_auto_continue.remote_patterns import (
    CACHE_TTL_SECONDS,
    RemotePatterns,
    _parse,
    _read_cache,
    _write_cache,
    fetch,
)


# --- _parse -----------------------------------------------------------------

class TestParse:
    def test_parses_all_fields(self):
        data = {
            "version": 2,
            "continue_labels": ["go ahead", "do it"],
            "context_keywords": ["new keyword"],
            "terminal_patterns": ["new pattern"],
            "browser_hosts": ["newclaude.ai"],
            "claude_bundle_ids": ["com.new.claude"],
            "browser_bundle_ids": ["com.new.browser"],
            "browser_heuristic_tokens": ["newbrowser"],
        }
        rp = _parse(data)
        assert rp.continue_labels == ("go ahead", "do it")
        assert rp.context_keywords == ("new keyword",)
        assert rp.terminal_patterns == ("new pattern",)
        assert rp.browser_hosts == ("newclaude.ai",)
        assert rp.claude_bundle_ids == ("com.new.claude",)
        assert rp.browser_bundle_ids == ("com.new.browser",)
        assert rp.browser_heuristic_tokens == ("newbrowser",)

    def test_empty_data_returns_empty_tuples(self):
        rp = _parse({})
        assert rp.continue_labels == ()
        assert rp.context_keywords == ()
        assert rp.terminal_patterns == ()

    def test_non_list_values_ignored(self):
        rp = _parse({"continue_labels": "not a list"})
        assert rp.continue_labels == ()

    def test_falsy_values_filtered(self):
        rp = _parse({"continue_labels": ["good", "", None, "also good"]})
        assert rp.continue_labels == ("good", "also good")

    def test_numeric_values_stringified(self):
        rp = _parse({"continue_labels": [42, 3.14]})
        assert rp.continue_labels == ("42", "3.14")


# --- Cache round-trip -------------------------------------------------------

class TestCache:
    def test_write_then_read(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.CACHE_PATH", cache_file
        )
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.DEFAULT_HOME", tmp_path
        )

        data = {"version": 1, "continue_labels": ["test"]}
        _write_cache(data)
        assert cache_file.is_file()

        result = _read_cache()
        assert result is not None
        assert result["continue_labels"] == ["test"]

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.CACHE_PATH", cache_file
        )

        data = {
            "version": 1,
            "_fetched_at": time.time() - CACHE_TTL_SECONDS - 100,
        }
        cache_file.write_text(json.dumps(data))
        assert _read_cache() is None

    def test_missing_cache_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.CACHE_PATH",
            tmp_path / "nonexistent.json",
        )
        assert _read_cache() is None

    def test_corrupt_cache_returns_none(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not valid json {{{")
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.CACHE_PATH", cache_file
        )
        assert _read_cache() is None


# --- fetch() fallback -------------------------------------------------------

class TestFetch:
    def test_fetch_fails_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.CACHE_PATH",
            tmp_path / "cache.json",
        )
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.REMOTE_URL",
            "http://localhost:1/nonexistent",
        )
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.FETCH_TIMEOUT_SECONDS", 1,
        )
        rp = fetch()
        assert isinstance(rp, RemotePatterns)
        assert rp.source == "fetch-failed"
        assert rp.continue_labels == ()

    def test_fetch_uses_cache_when_available(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(
            "claude_auto_continue.remote_patterns.CACHE_PATH", cache_file
        )
        data = {
            "version": 1,
            "_fetched_at": time.time(),
            "continue_labels": ["cached label"],
        }
        cache_file.write_text(json.dumps(data))

        rp = fetch()
        assert rp.source == "cache"
        assert rp.continue_labels == ("cached label",)


# --- RemotePatterns defaults ------------------------------------------------

class TestDefaults:
    def test_default_empty(self):
        rp = RemotePatterns()
        assert rp.continue_labels == ()
        assert rp.source == "none"
