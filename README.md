# claude-auto-continue-macos

> Automatically clicks "Continue" everywhere Claude pauses your session — the native macOS app, claude.ai in any browser, and Claude Code in your terminal. No extension required. Future-proof against UI changes.

A small, focused Python CLI that watches every place Claude might be
waiting for you and resumes the session automatically. Walk away from a
long agentic run and come back to finished work instead of a paused
screen.

---

## What it does

Claude pauses long tool-use sessions and asks you to click **Continue**
(or press Enter) before it keeps going. This tool watches three surfaces
at once and resumes whichever one is paused:

- **The native Claude desktop app** — AXPress on the Continue button.
  Context-free detection: the app itself is the context, so we don't
  need to match specific limit text. Immune to Anthropic rewording the
  pause message in future updates.
- **claude.ai in any browser** — Safari, Chrome, Brave, Arc, Dia, Edge,
  Opera, Vivaldi, Firefox, Atlas, and any other Chromium/WebKit/Gecko
  browser that ships on macOS (detected via bundle-ID heuristic, so
  brand-new forks work with no code update). Only `claude.ai` web-areas
  are scanned; other tabs and sites are ignored. Works across many open
  tabs — every `claude.ai` `AXWebArea` in every window is visited each
  tick. URL filtering scopes the scanner, so no context keywords are
  needed here either.
- **Claude Code CLI** (opt-in) — any terminal you put in front. We watch
  the frontmost app and send a single Return keystroke when a narrow
  tool-use-limit pattern appears. 28+ built-in patterns plus regex
  support cover current and future Claude Code prompt variations. Because
  the frontmost app is whoever receives the keystroke anyway, **every
  terminal works without an allowlist**: Warp, iTerm2, Ghostty,
  Terminal.app, Kitty, Alacritty, WezTerm, Hyper, Tabby, Rio, Wave,
  VS Code, Cursor, Windsurf — current or future. Browsers, Finder, Dock,
  system UI and the Claude desktop app are explicitly excluded.

### Future-proofing

All three scanners are designed to keep working when Anthropic ships UI
updates:

- **Desktop app + browser:** Detection is context-free — any button whose
  label starts with "continue", "resume", "proceed", or "keep going"
  (plus 18 exact-match labels) triggers a click. No fragile keyword
  matching against surrounding text.
- **Terminals:** 28+ pause patterns with regex fallbacks catch spacing
  changes, wording tweaks, and new prompt styles. Custom patterns can be
  added in the config file.
- **Remote patterns:** On startup, the agent fetches `patterns.json`
  from this GitHub repo and merges any new labels, keywords, or patterns
  with the built-in lists. If Anthropic changes a button label tomorrow,
  a one-line JSON edit ships the fix to every user — no code update
  needed. The fetch is cached for 6 hours and fails gracefully (4s
  timeout, fallback to built-in).
- **User overrides:** The config file supports `extra_continue_labels`,
  `extra_context_keywords`, and `terminal_patterns` for user-defined
  additions that merge with everything above.

## How it works

`claude-auto-continue` uses the macOS **Accessibility API** via `pyobjc`.
Every 1.5 seconds it reads Claude's UI element tree (the same tree
VoiceOver and other screen readers use) and looks for a Continue button.
When it finds one, it performs the standard `AXPress` accessibility action
on that button — the same thing a screen reader user would do.

After each click, a fast 0.4s follow-up scan catches back-to-back pauses
(consecutive tool-use limits) before falling back to the normal interval.

It does **not**:

- capture your screen or record anything
- use OCR or computer vision
- inject code into the Claude app
- read keystrokes, clipboard, or files

### The Electron accessibility caveat

The Claude app is an Electron app, and Electron disables the
accessibility tree by default. On startup (and on every Claude restart)
we programmatically set the documented `AXManualAccessibility` attribute
on the Claude process. This flips the tree on so we can read the UI.
This is a supported Electron feature, not a hack.

Equivalent pseudocode:

```
pid = NSRunningApplication for Claude
app = AXUIElementCreateApplication(pid)
AXUIElementSetAttributeValue(app, "AXManualAccessibility", true)
```

## Why not a browser extension?

Extensions only see one browser at a time and can't touch the native
desktop app or the terminal. This tool uses the macOS Accessibility API
instead, which covers every surface with a single install and one
permission grant. The older
[`claude-autocontinue`](https://github.com/timothy22000/claude-autocontinue)
Chrome/Firefox extension still works if you prefer that — they're not
mutually exclusive.

---

## Quick start

### Option A: Homebrew (recommended)

```bash
brew install PrivateVictories-Main/tap/claude-auto-continue
claude-auto-continue --setup
```

That's it. Two commands. The setup wizard grants Accessibility permission
and optionally installs a background service. To run forever as a
LaunchAgent:

```bash
brew services start claude-auto-continue
```

### Option B: One-liner install script

```bash
curl -fsSL https://raw.githubusercontent.com/PrivateVictories-Main/claude-auto-continue-macos/main/scripts/install.sh | bash
```

Finds Python 3.9+, clones the repo to `~/.claude-auto-continue-macos/`,
creates a virtualenv, installs everything, adds a shell alias, and
offers to run `--setup` at the end. Nothing touches system Python or
`/usr/local`.

### Option C: Manual install

```bash
git clone https://github.com/PrivateVictories-Main/claude-auto-continue-macos.git
cd claude-auto-continue-macos
pip install .
claude-auto-continue --setup
```

The setup wizard opens System Settings straight to the Accessibility pane,
tells you the exact interpreter path to paste in, spins until the toggle
flips on, optionally installs the background LaunchAgent, and runs a
self-test against the Claude app. The whole thing takes under a minute.

### Then just run it

```bash
claude-auto-continue
```

Open Claude and start a long session. The tool handles the rest.
Press **Ctrl+C** any time to exit cleanly with a session summary.

---

## Usage

```text
claude-auto-continue [--setup]
                     [--dry-run] [--interval SECONDS] [--cooldown SECONDS]
                     [--silent] [--no-notifications]
                     [--max-continues N] [--no-log] [--verbose]
                     [--no-app] [--no-browsers] [--terminals]
                     [--menu-bar]
                     [--no-dashboard] [--dashboard-port PORT]
                     [--config PATH] [--version]
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--setup` | — | One-time interactive walkthrough: opens System Settings, polls for Accessibility permission, offers LaunchAgent install, runs a self-test. Recommended for first-run. |
| `--dry-run` | off | Show when it *would* click without actually clicking. Prints `[DRY RUN] Would have clicked Continue` so you can build trust before letting it touch your UI. |
| `--interval SECONDS` | `1.5` | Polling interval in seconds. Range: **0.5 – 30**. After each click or Claude restart, the next scan runs in 0.4s regardless. |
| `--cooldown SECONDS` | `5` | Minimum wait between clicks to prevent rapid double-clicks if the UI is slow to update. |
| `--silent` | off | Disable the notification sound on auto-continue. |
| `--no-notifications` | off | Disable macOS Notification Center alerts. |
| `--max-continues N` | unlimited | Stop after N auto-continues and exit cleanly. |
| `--no-log` | off | Don't write to `~/.claude-auto-continue/activity.log`. |
| `--verbose` | off | Print AX tree scans and idle heartbeats. Use this to debug if Claude changes the button text. |
| `--no-app` | off | Don't scan the native Claude desktop app. |
| `--no-browsers` | off | Don't scan browsers for claude.ai tabs. |
| `--terminals` | off | **Also** scan terminal apps for Claude Code CLI pauses. Opt-in because this sends Return keystrokes. |
| `--menu-bar` | off | Show a status icon in the macOS menu bar (green/yellow/red dot) with live state, continue count, and quick actions. |
| `--no-dashboard` | off | Disable the localhost control dashboard. |
| `--dashboard-port PORT` | `8787` | Port for the dashboard (127.0.0.1 only). |
| `--config PATH` | `~/.claude-auto-continue/config.toml` | Use a custom TOML config file. |
| `--version` | — | Print version and exit. |

### Common recipes

```bash
# Basic — just run it. Watches the desktop app + claude.ai in browsers.
claude-auto-continue

# First time? Get a guided setup wizard.
claude-auto-continue --setup

# Cover everything, including Claude Code CLI in your terminal.
claude-auto-continue --terminals

# Only the native desktop app.
claude-auto-continue --no-browsers

# Trust-building dry run: show what would happen without clicking.
claude-auto-continue --dry-run

# Quiet mode — no sound, no notifications.
claude-auto-continue --silent --no-notifications

# Slow poll (for older/low-power Macs).
claude-auto-continue --interval 5

# Safety cap — exit after 10 clicks.
claude-auto-continue --max-continues 10

# Debugging a button-text change in a new Claude release.
claude-auto-continue --verbose --dry-run
```

---

## Localhost control dashboard

Every run ships with a small, glassy, Claude-themed dashboard at
**`http://127.0.0.1:8787`**. Toggle any of the three scanners on or off
live, tune the polling interval and cooldown, enable dry-run, and watch
events stream in from the running monitor. The dashboard talks to the
same process that's doing the clicking — changes apply immediately, no
restart required.

It binds only to `127.0.0.1`, so it's never exposed to the network.
Disable with `--no-dashboard` or move it with
`--dashboard-port 9000` / `--dashboard-host 127.0.0.1`. If the default
port is busy, we automatically try the next five.

```bash
# Just run it — the dashboard is on by default.
claude-auto-continue
# → dashboard running at http://127.0.0.1:8787

# Or disable it entirely.
claude-auto-continue --no-dashboard

# Pick a custom port.
claude-auto-continue --dashboard-port 9001
```

### Closed the tab? Reopen it without thinking

```bash
./scripts/open-dashboard.sh
```

Probes `127.0.0.1:8787` through `8792` (the fallback range the
dashboard rolls through when the primary port is already taken), finds
the first one that responds, and opens it. Pass `--print` to just echo
the URL. The script only considers a port "ours" if `/api/state`
returns the expected payload, so it won't open some unrelated localhost
you had running.

---

## Menu bar status icon

```bash
claude-auto-continue --menu-bar
```

Adds a small coloured dot to your macOS menu bar:

- **Green** — watching (Claude detected, scanning)
- **Yellow** — waiting for Claude to appear
- **Red** — error or permissions issue
- **Gray** — initializing

Click the dot for a dropdown showing live status, uptime, continue count,
and quick actions (open dashboard, quit). The menu bar icon runs alongside
the normal CLI output and dashboard — all three work together.

---

## Run it as a background service (LaunchAgent)

If you want the tool to run 24/7 — auto-start on login, survive reboots,
auto-restart on crash, no terminal window required — install it as a
macOS LaunchAgent:

```bash
./scripts/install-launchagent.sh
```

That script generates a user-specific plist at
`~/Library/LaunchAgents/com.<user>.claude-auto-continue.plist`, loads it
via `launchctl`, and sends stdout/stderr to
`~/.claude-auto-continue/launchd.{out,err}.log`.

### One extra permission step for LaunchAgents

A LaunchAgent has **no terminal parent** to inherit Accessibility
permission from, so the Python binary itself needs to be in the
Accessibility list. Open `System Settings → Privacy & Security →
Accessibility`, click `+`, press `Cmd+Shift+G`, and paste:

```
<repo>/.venv/bin/python
```

macOS resolves the symlink and grants permission to the real
`python3.14` (or whatever your version is). Once the toggle is on, the
agent picks up the new permission on its next restart — typically
within ten seconds thanks to `KeepAlive` + `ThrottleInterval=10`.

### Handy commands

```bash
# Status + recent logs
./scripts/status.sh

# Follow logs live
tail -f ~/.claude-auto-continue/launchd.out.log

# Stop + uninstall
./scripts/uninstall-launchagent.sh
```

---

## Uninstalling

```bash
# Interactive — confirms before each step
./scripts/uninstall.sh

# Non-interactive — removes everything
./scripts/uninstall.sh --force
```

Handles all install methods (Homebrew, curl|bash, manual). Removes the
LaunchAgent, Homebrew formula, shell aliases, and optionally the data
directory (`~/.claude-auto-continue/` with logs, config, and cache).

Or if you installed via Homebrew only:

```bash
brew services stop claude-auto-continue
brew uninstall claude-auto-continue
brew untap PrivateVictories-Main/tap  # optional
```

---

## Configuration file

Drop a TOML file at `~/.claude-auto-continue/config.toml` to set defaults
for any flag. CLI arguments always win.

```toml
# ~/.claude-auto-continue/config.toml
interval        = 1.5
cooldown        = 5
silent          = false
notifications   = true
max_continues   = 0       # 0 = unlimited
log             = true
verbose         = false
dry_run         = false

# Scan targets
scan_app        = true    # native Claude desktop app
scan_browsers   = true    # claude.ai in any running browser
scan_terminals  = false   # opt in — sends Return keystrokes

# Extra button labels to recognise (merged with built-in + remote lists)
extra_continue_labels = [
    # "go ahead",
    # "keep generating",
]

# Extra context keywords (used only when require_context is True)
extra_context_keywords = [
    # "custom pause text",
]

# Extra text patterns that identify a Claude Code CLI pause.
# Plain strings are matched as case-insensitive substrings.
# Prefix with "re:" for regex matching: "re:custom\s+pause\s+\d+"
terminal_patterns = [
    # "press enter to resume",
    # "re:session\\s+paused",
]
```

Requires Python 3.11+ (stdlib `tomllib`) or the `tomli` package on older
Pythons — already pinned for you in `requirements.txt`.

---

## Remote patterns (`patterns.json`)

The repo root contains a `patterns.json` file that the agent fetches from
GitHub on startup. This is the zero-code-update escape hatch: if Anthropic
renames a button or changes a terminal prompt, a one-line edit to
`patterns.json` ships the fix to every running instance within 6 hours
(the cache TTL).

The file supports these keys — all are additive (merged with built-in
lists, never replace):

```json
{
  "version": 1,
  "continue_labels": [],
  "context_keywords": [],
  "terminal_patterns": [],
  "browser_hosts": [],
  "claude_bundle_ids": [],
  "browser_bundle_ids": [],
  "browser_heuristic_tokens": []
}
```

The fetch runs once at startup (4s timeout), caches to
`~/.claude-auto-continue/patterns_cache.json`, and fails gracefully —
if GitHub is unreachable, the agent runs on built-in patterns only.

---

## Tests

202 unit tests cover the core matching logic:

```bash
pip install pytest
pytest tests/ -v
```

Tests cover:
- Button label matching (exact, prefix, case, whitespace, false positives)
- Terminal pause patterns (substring, regex, edge cases)
- Remote patterns (parsing, cache round-trip, expiry, corruption, fallback)
- Browser URL matching (valid/invalid URLs, subdomains, extra hosts)
- Browser heuristic detection (known/unknown bundle IDs)

---

## Security and transparency

Trust matters here — this tool has Accessibility permission. Here's
exactly what that means and what it does.

- The tool uses the same macOS Accessibility permission that window
  managers (Rectangle, Magnet), automation tools (Keyboard Maestro,
  Hammerspoon), and screen readers (VoiceOver) use.
- With that permission, it can **only** read UI element metadata —
  button labels, window titles, roles. It **cannot** read your
  conversation content, keystrokes, clipboard, files, or anything else.
- It performs at most two kinds of action:
  - `AXPress` on a Continue-looking button (native app, or a claude.ai
    tab in a browser).
  - A single Return keystroke sent to a terminal process, **opt-in via
    `--terminals`**, only when an unambiguous Claude Code pause
    pattern is visible in that terminal's focused window.
- On startup it makes **one** HTTPS request to fetch `patterns.json`
  from this GitHub repo (cached 6h, 4s timeout, fails silently). No
  other network requests. No analytics, no telemetry, no update pings.
- It is fully open source. Read every file yourself — the whole thing is
  a few hundred lines of straightforward Python. The accessibility code
  lives in `claude_auto_continue/accessibility.py` and uses nothing
  beyond pyobjc.
- The activity log at `~/.claude-auto-continue/activity.log` only
  records timestamps, event types, and a running count. No conversation
  content, no UI text, no window titles.

---

## Compatibility

- **macOS:** 12 Monterey and newer (13 Ventura, 14 Sonoma, 15 Sequoia tested)
- **Python:** 3.9+
- **Architecture:** Apple Silicon (M1/M2/M3/M4) and Intel
- **Terminals:** Works with any terminal — Terminal, iTerm2, Ghostty, Warp,
  Kitty, Alacritty, WezTerm, Hyper, VS Code, Cursor, Windsurf, etc.
  Each terminal needs its own Accessibility grant.

---

## Limitations

Honesty section:

- If Anthropic changes the Continue button's label *and* none of the
  18 exact labels or 4 prefix patterns match, the tool needs a
  `patterns.json` update (no code change). The `--verbose` flag helps
  diagnose — the tree walk prints every button it sees.
- **Background tabs in Chromium browsers** can have their renderer AX
  tree briefly suspended to save CPU. In practice we still pick up the
  Continue button because `AXEnhancedUserInterface` keeps the tree
  populated, but if a tab has been inert for hours and a pause arrives
  that exact moment, one tick may miss it. The next tick finds it.
- macOS pre-12 is not supported (`pyobjc` Accessibility features require
  a modern Foundation).
- macOS only. Windows / Linux are tracked in the roadmap.

---

## Roadmap

- [x] Context-free desktop app detection (v0.5.0)
- [x] Context-free browser detection (v0.6.0)
- [x] Remote-fetched patterns for zero-code-update fixes (v0.6.0)
- [x] Regex terminal patterns (v0.6.0)
- [x] 202 unit tests (v0.6.0)
- [x] User-configurable button-text patterns (v0.6.0)
- [x] Homebrew formula — `brew install PrivateVictories-Main/tap/claude-auto-continue` (v0.6.0)
- [x] One-liner install script — `curl | bash` (v0.6.0)
- [x] `brew services start` for LaunchAgent management (v0.6.0)
- [x] Menu bar status icon with `--menu-bar` (v0.7.0)
- [x] Uninstall script for all install methods (v0.7.0)
- [x] Activity log surface tracking — desktop-app/browser/terminal (v0.7.0)
- [x] GitHub Actions CI (v0.7.0)
- [ ] Windows support via UI Automation API
- [ ] Optional auto-update check

---

## Contributing

PRs welcome. Please:

- Match the existing style — small, focused modules, docstrings at the
  top of each file, no new dependencies unless they pull their weight.
- Run `pytest tests/ -v` and confirm all tests pass before submitting.
- File bugs via the [issue template](.github/ISSUE_TEMPLATE/bug_report.md)
  and include `--verbose` output where relevant.

---

## License

MIT — see [LICENSE](LICENSE).
