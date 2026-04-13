# claude-auto-continue-macos

> Automatically clicks "Continue" in the Claude macOS desktop app when tool-use limits pause your session.

A small, focused Python CLI that watches the native Claude app and presses
the tool-use-limit **Continue** button for you. Walk away from a long
agentic session and come back to finished work instead of a paused screen.

---

## What it does

The Claude macOS desktop app will pause long tool-use sessions and ask you
to click a **Continue** button to proceed. This tool monitors the Claude
app for that specific pause and clicks Continue for you automatically. It
only ever clicks in the correct context — it ignores unrelated
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

## Why not the browser extension?

The excellent [`claude-autocontinue`](https://github.com/timothy22000/claude-autocontinue)
extension handles `claude.ai` in Chrome/Firefox. This tool exists for the
**native macOS desktop app**, which doesn't run browser extensions.

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

3. **Grant Accessibility permission to your terminal**

   Open **System Settings → Privacy & Security → Accessibility**, click the
   `+`, add your terminal app (Terminal, iTerm, Ghostty, Warp, …), and make
   sure the toggle is **ON**. Quit and reopen the terminal afterward.

   If you skip this step the tool will detect it and print a step-by-step
   guide naming your specific terminal app — it won't crash.

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
claude-auto-continue [--dry-run] [--interval SECONDS] [--cooldown SECONDS]
                     [--silent] [--no-notifications]
                     [--max-continues N] [--no-log] [--verbose]
                     [--config PATH] [--version]
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | off | Show when it *would* click without actually clicking. Prints `[DRY RUN] Would have clicked Continue` so you can build trust before letting it touch your UI. |
| `--interval SECONDS` | `3` | Polling interval in seconds. Range: **1 – 30**. |
| `--cooldown SECONDS` | `5` | Minimum wait between clicks to prevent rapid double-clicks if the UI is slow to update. |
| `--silent` | off | Disable the notification sound on auto-continue. |
| `--no-notifications` | off | Disable macOS Notification Center alerts. |
| `--max-continues N` | unlimited | Stop after N auto-continues and exit cleanly. |
| `--no-log` | off | Don't write to `~/.claude-auto-continue/activity.log`. |
| `--verbose` | off | Print AX tree scans and idle heartbeats. Use this to debug if Claude changes the button text. |
| `--config PATH` | `~/.claude-auto-continue/config.toml` | Use a custom TOML config file. |
| `--version` | — | Print version and exit. |
| `--help` | — | Full help menu. |

### Common recipes

```bash
# Basic — just run it.
claude-auto-continue

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

## Configuration file

Drop a TOML file at `~/.claude-auto-continue/config.toml` to set defaults
for any flag. CLI arguments always win.

```toml
# ~/.claude-auto-continue/config.toml
interval       = 3
cooldown       = 5
silent         = false
notifications  = true
max_continues  = 0       # 0 = unlimited
log            = true
verbose        = false
dry_run        = false
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
- It performs **exactly one** action: the `AXPress` accessibility action
  on a button whose label looks like "Continue" and whose window
  contains tool-use-limit text. That's it.
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
