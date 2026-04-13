#!/usr/bin/env bash
# Stop and remove the claude-auto-continue LaunchAgent.
set -euo pipefail

LABEL="com.${USER}.claude-auto-continue"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_N="$(id -u)"

launchctl bootout "gui/${UID_N}/${LABEL}" 2>/dev/null && echo "stopped." || echo "(not running)"

if [[ -f "$PLIST" ]]; then
    rm "$PLIST"
    echo "removed:    $PLIST"
else
    echo "(no plist at $PLIST)"
fi

echo
echo "logs at \$HOME/.claude-auto-continue/ are kept. Remove with:"
echo "  rm -rf \$HOME/.claude-auto-continue"
