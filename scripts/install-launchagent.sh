#!/usr/bin/env bash
#
# Install claude-auto-continue as a macOS LaunchAgent so it runs
# persistently in the background and auto-starts on login.
#
# Prerequisites:
#   1. pip install -r requirements.txt  (or: pip install .)
#   2. A virtualenv at <repo>/.venv  (preferred) OR an on-PATH python3
#   3. Accessibility permission granted to that python binary:
#        System Settings -> Privacy & Security -> Accessibility
#        + the binary at .venv/bin/python  (macOS resolves the symlink).
#
# Usage:
#   ./scripts/install-launchagent.sh              # install and start
#   ./scripts/install-launchagent.sh --reload     # reload an existing one
#
set -euo pipefail

LABEL="com.${USER}.claude-auto-continue"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/.claude-auto-continue"
UID_N="$(id -u)"

# Pick a python: prefer the repo's venv, fall back to python3 on PATH.
if [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
    PYTHON="$REPO_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
else
    echo "error: no python found. Create a venv with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>-u</string>
        <string>-m</string>
        <string>claude_auto_continue</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>ProcessType</key>
    <string>Background</string>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd.out.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>LANG</key>
        <string>en_US.UTF-8</string>
        <key>LC_ALL</key>
        <string>en_US.UTF-8</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
EOF

plutil -lint "$PLIST" >/dev/null

# Unload existing instance (ignore "no such process") then load fresh.
launchctl bootout "gui/${UID_N}/${LABEL}" 2>/dev/null || true

# Truncate old logs so the user sees a clean run.
: > "$LOG_DIR/launchd.out.log"
: > "$LOG_DIR/launchd.err.log"

launchctl bootstrap "gui/${UID_N}" "$PLIST"

echo "installed:  $PLIST"
echo "python:     $PYTHON"
echo "logs:       $LOG_DIR/launchd.{out,err}.log"
echo
echo "check status:   launchctl print gui/${UID_N}/${LABEL} | head -40"
echo "tail logs:      tail -f $LOG_DIR/launchd.out.log"
echo "uninstall:      ./scripts/uninstall-launchagent.sh"
