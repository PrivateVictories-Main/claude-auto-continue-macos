# Changelog

All notable changes to claude-auto-continue are documented here.

## [0.7.2] - 2026-04-17

### Fixed
- Dashboard: Content-Length validation now rejects negative and non-numeric values
- Dashboard: CORS origin matching expanded to include `localhost` and port variants
- Dashboard: `_serve_html` catches `PermissionError`/`OSError`, not just `FileNotFoundError`

### Improved
- Terminal scanner: regex patterns compiled once via `lru_cache` instead of every tick
- Dashboard: Content-Security-Policy header on HTML responses
- Dashboard: aria-live regions on live-updating stats for screen readers
- Dashboard: toggle cards are keyboard-accessible (`role="switch"`, `tabindex`, Enter/Space)
- Monitor: replaced `# type: ignore` on `RemotePatterns` with proper `Optional` annotation

## [0.7.1] - 2026-04-17

### Added
- 5 new test files (CLI, config, dashboard, dashboard validation, logger) — 273 total tests
- Troubleshooting section in README

### Fixed
- False positive: file names like `RESUME_MAIN_NEW.zip` matched by prefix logic — now requires space after prefix word
- Thread-safe counter: `Status.increment_continues()` uses a lock to prevent race conditions between monitor and sync threads

### Hardened
- Dashboard settings API validates types (rejects string for number, int for bool, etc.)
- Dashboard POST body limited to 64KB
- CORS headers on dashboard responses
- Remote pattern fetch retries up to 2 times with 1s delay

## [0.7.0] - 2026-04-17

### Added
- Menu bar status icon (`--menu-bar`) with live state, continue count, and quick actions
- Uninstall script for all install methods (LaunchAgent, Homebrew, curl|bash)
- Activity log surface tracking — logs now record `surface=desktop-app|browser|terminal`
- GitHub Actions CI on macOS with Python 3.10/3.12/3.13

## [0.6.0] - 2026-04-16

### Added
- Browser scanner: detects Continue buttons in claude.ai tabs across 38+ browsers
- Terminal scanner: detects Claude Code pauses via 28+ patterns (substring + regex)
- Remote pattern overrides via `patterns.json` on GitHub (6h cache, graceful fallback)
- 18 Continue button labels with prefix matching
- 17 tool-use context keywords
- User-configurable extra labels, keywords, and terminal patterns
- Localhost dashboard at `http://127.0.0.1:8787` with SSE live events
- TOML config file support (`~/.claude-auto-continue/config.toml`)
- Homebrew formula: `brew install PrivateVictories-Main/tap/claude-auto-continue`
- One-liner install: `curl -fsSL .../install.sh | bash`
- `brew services start` for LaunchAgent management
- 48 unit tests across 4 test files

### Fixed
- Removed "retry"/"try again" from button matching — different semantics than Continue

## [0.5.0] - 2026-04-15

### Added
- Initial release
- Native Claude desktop app monitoring via AXPress
- LaunchAgent for auto-start on login
- `--setup` interactive walkthrough
- `--dry-run` mode
- macOS Notification Center alerts
- Activity logging to `~/.claude-auto-continue/activity.log`
