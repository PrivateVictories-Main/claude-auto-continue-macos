"""Tests for browser URL matching and heuristic detection."""

import pytest

from claude_auto_continue.browser import (
    BROWSER_BUNDLE_IDS,
    CLAUDE_HOSTS,
    _is_claude_url,
    _is_claude_url_ext,
    looks_like_browser,
)

# --- _is_claude_url ---------------------------------------------------------


class TestIsClaudeUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://claude.ai/chat/abc123",
            "https://www.claude.ai/chat",
            "https://claude.anthropic.com/chat",
            "https://claude.ai/",
            "https://CLAUDE.AI/chat",
            "https://claude.ai/code",
        ],
    )
    def test_valid_claude_urls(self, url):
        assert _is_claude_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://google.com",
            "https://notclaude.ai",
            "https://evil-claude.ai.attacker.com/phish",
            "https://fakeclaude.ai",
            "https://chatgpt.com",
            "",
            "not-a-url",
            "javascript:alert(1)",
        ],
    )
    def test_non_claude_urls_rejected(self, url):
        assert not _is_claude_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://subdomain.claude.ai/chat",
            "https://api.claude.ai/v1",
        ],
    )
    def test_subdomains_accepted(self, url):
        assert _is_claude_url(url)


# --- _is_claude_url_ext with extra hosts ------------------------------------


class TestIsClaudeUrlExt:
    def test_extra_hosts_accepted(self):
        extra = ("newclaude.example.com",)
        assert _is_claude_url_ext("https://newclaude.example.com/chat", CLAUDE_HOSTS + extra)

    def test_builtin_hosts_still_work(self):
        assert _is_claude_url_ext("https://claude.ai/chat", CLAUDE_HOSTS + ("extra.com",))


# --- looks_like_browser -----------------------------------------------------


class TestLooksLikeBrowser:
    @pytest.mark.parametrize(
        "bundle_id",
        [
            "com.example.mybrowser",
            "org.chromium.something",
            "com.example.Chrome.helper",
            "org.example.firefox.nightly",
            "com.example.SafariExtension",
            "com.example.webkit.view",
            "com.example.BraveSoftware",
        ],
    )
    def test_heuristic_matches(self, bundle_id):
        assert looks_like_browser(bundle_id)

    @pytest.mark.parametrize(
        "bundle_id",
        [
            "com.anthropic.claude",
            "com.apple.finder",
            "com.apple.mail",
            "com.example.texteditor",
            "com.microsoft.word",
            "",
        ],
    )
    def test_non_browser_rejected(self, bundle_id):
        assert not looks_like_browser(bundle_id)

    def test_none_handled(self):
        assert not looks_like_browser(None)


# --- Known bundle IDs are comprehensive -------------------------------------


class TestKnownBundleIds:
    @pytest.mark.parametrize(
        "bundle_id",
        [
            "com.google.Chrome",
            "com.apple.Safari",
            "com.brave.Browser",
            "company.thebrowser.Browser",
            "org.mozilla.firefox",
            "com.microsoft.edgemac",
            "com.vivaldi.Vivaldi",
            "com.duckduckgo.macos.browser",
        ],
    )
    def test_major_browsers_in_list(self, bundle_id):
        assert bundle_id in BROWSER_BUNDLE_IDS
