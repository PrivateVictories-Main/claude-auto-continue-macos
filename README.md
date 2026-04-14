# claude-auto-continue-macos

> Automatically clicks "Continue" everywhere Claude paused your session — the native macOS app, claude.ai in any browser, and optionally Claude Code in your terminal. No extension required.

A small, focused Python CLI that watches every place Claude might be
waiting for you and resumes the session automatically. Walk away from a
long agentic run and come back to finished work instead of a paused
screen.

---

## What it does

Claude pauses long tool-use sessions and asks you to click **Continue**
(or press Enter) before it keeps going. This tool watches three places at
once and resumes whichever one is paused:

- **The native Claude desktop app** — AXPress on the tool-use-limit
  Continue button.
- **claude.ai in any browser** — Safari, Chrome, Brave, Arc, Dia, Edge,
  Opera, Vivaldi, Firefox, and ChatGPT Atlas. Only the claude.ai tab is
  scanned; other tabs and sites are ignored.
- **Claude Code CLI** (opt-in) — Warp, iTerm2, Ghostty, Terminal.app, VS
  Code, Cursor, Windsurf, Hyper, WezTerm, Kitty, and Alacritty. Sends a
  single Return keystroke only when a narrow tool-use-limit pattern is
  on screen.

It only ever acts in the correct context — it ignores unrelated
"Continue" buttons elsewhere in the UI.

## How it works

`claude-auto-continue` uses the macOS **Accessibility API** via `pyobjc`.
Every few seconds it reads Claude's UI element tree (the same tree
VoiceOver and other screen readers use) and looks for a Continue button
inside a window that also mentions the tool-use limit. When it finds one,
it performs the standard `AXPress` accessibility action on that button —
the same thing a screen reader user would do.

It does **not**:

- capture your screen or record anything
- use OCR or computer vision
- inject code into the Claude app
- read keystrokes, clipboard, or files
- make network requests of any kind

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
instead, which covers every surface a single install and one permission
grant. The older
[`claude-autocontinue`](https://github.com/timothy22000/claude-autocontinue)
Chrome/Firefox extension still works if you prefer that — they're not
mutually exclusive.

---

## Quick start

1. **Clone the repo**
   ```bash
   git clone https://github.com/PrivateVictories-Main/claude-auto-continue-macos.git
   cd claude-auto-continue-macos
   ```

2. **Install dependencies**
   ```bash
   pip install .
   # or, if you prefer not to install the package:
   pip install -r requirements.txt
   ```

3. **Run the one-time setup walkthrough**
   ```bash
   claude-auto-continue --setup
   ```

   This opens System Settings straight to the Accessibility pane, tells
   you the exact interpreter path to paste in, spins until the toggle
   flips on, optionally installs the background LaunchAgent, and runs a
   self-test against the Claude app. The whole thing takes under a
   minute.

   If you'd rather do it manually: open **System Settings → Privacy &
   Security → Accessibility**, click the `+`, and add either your
   terminal app (for one-shot CLI use) or the interpreter at
   `.venv/bin/python` (for the LaunchAgent). Either path prints below
   on the first failed run, so you don't need to remember it.

4. **Run it**
   ```bash
   claude-auto-continue
   # or:
   python -m claude_auto_continue
   ```

5. **Open Claude and start a long session.** The tool handles the rest.
   Press **Ctrl+C** any time to exit cleanly with a session summary.

---

## Usage

```text
claude-auto-continue [--setup]
                     [--dry-run] [--interval SECONDS] [--cooldown SECONDS]
                     [--silent] [--no-notifications]
                     [--max-continues N] [--no-log] [--verbose]
                     [--no-app] [--no-browsers] [--terminals]
                     [--config PATH] [--version]
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--setup` | — | One-time interactive walkthrough: opens System Settings, polls for Accessibility permission, offers LaunchAgent install, runs a self-test. Recommended for first-run. |
| `--dry-run` | off | Show when it *would* click without actually clicking. Prints `[DRY RUN] Would have clicked Continue` so you can build trust before letting it touch your UI. |
| `--interval SECONDS` | `3` | Polling interval in seconds. Range: **1 – 30**. |
| `--cooldown SECONDS` | `5` | Minimum wait between clicks to prevent rapid double-clicks if the UI is slow to update. |
| `--silent` | off | Disable the notification sound on auto-continue. |
| `--no-notifications` | off | Disable macOS Notification Center alerts. |
| `--max-continues N` | unlimited | Stop after N auto-continues and exit cleanly. |
| `--no-log` | off | Don't write to `~/.claude-auto-continue/activity.log`. |
| `--verbose` | off | Print AX tree scans and idle heartbeats. Use this to debug if Claude changes the button text. |
| `--no-app` | off | Don't scan the native Claude desktop app. |
| `--no-browsers` | off | Don't scan browsers for claude.ai tabs. |
| `--terminals` | off | **Also** scan terminal apps for Claude Code CLI pauses. Opt-in because this sends Return keystrokes. |
| `--config PATH` | `~/.claude-auto-continue/config.toml` | Use a custom TOML config file. |
| `--version` | — | Print version and exit. |
| `--help` | — | Full help menu. |

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

Every run now ships with a small, glassy, Claude-themed dashboard at
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

## Configuration file

Drop a TOML file at `~/.claude-auto-continue/config.toml` to set defaults
for any flag. CLI arguments always win.

```toml
# ~/.claude-auto-continue/config.toml
interval        = 3
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

# Extra text patterns that identify a Claude Code CLI pause.
# Matched as case-insensitive substrings against the focused terminal.
terminal_patterns = [
    # "press enter to resume",
    # "session paused, press any key",
]
```

Requires Python 3.11+ (stdlib `tomllib`) or the `tomli` package on older
Pythons — already pinned for you in `requirements.txt`.

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
- It performs at most two kinds of action, and only when a narrow
  tool-use-limit context is confirmed:
  - `AXPress` on a Continue-looking button (native app, or a claude.ai
    tab in a browser).
  - A single Return keystroke sent to a terminal process, **opt-in via
    `--terminals`**, only when an unambiguous Claude Code pause
    pattern is visible in that terminal's focused window.
- It makes **zero** network requests. It never phones home. It has no
  analytics, no telemetry, no update pings.
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

- If Anthropic changes the Continue button's label in a future release,
  the tool needs a one-line update. The `--verbose` flag helps diagnose
  this quickly — the tree walk prints every button it sees.
- This tool **cannot** touch `claude.ai` in a browser. Use the browser
  extension linked above for that.
- macOS pre-12 is not supported (`pyobjc` Accessibility features require
  a modern Foundation).
- macOS only. Windows / Linux are tracked in the roadmap.

---

## Roadmap

- [ ] Homebrew formula for one-command install
- [ ] Optional menu bar companion icon with status
- [ ] Windows support via UI Automation API
- [ ] User-configurable button-text patterns for future-proofing
- [ ] Optional auto-update check

---

## Contributing

PRs welcome. Please:

- Match the existing style — small, focused modules, docstrings at the
  top of each file, no new dependencies unless they pull their weight.
- File bugs via the [issue template](.github/ISSUE_TEMPLATE/bug_report.md)
  and include `--verbose` output where relevant.

---

## License

MIT — see [LICENSE](LICENSE).
