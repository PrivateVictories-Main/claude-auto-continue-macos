#!/usr/bin/env bash
# Quick status report for the LaunchAgent.
set -euo pipefail

LABEL="com.${USER}.claude-auto-continue"
LOG_DIR="$HOME/.claude-auto-continue"
UID_N="$(id -u)"

echo "=== process ==="
ps aux | grep -v grep | grep "claude_auto_continue" || echo "(not running)"

echo
echo "=== launchctl ==="
launchctl print "gui/${UID_N}/${LABEL}" 2>/dev/null \
    | grep -E "(state|runs|last exit code|pid|active count)" \
    || echo "(agent not loaded)"

echo
echo "=== recent stdout ==="
tail -n 20 "$LOG_DIR/launchd.out.log" 2>/dev/null || echo "(no log)"

echo
echo "=== recent activity ==="
tail -n 10 "$LOG_DIR/activity.log" 2>/dev/null || echo "(no activity log)"
