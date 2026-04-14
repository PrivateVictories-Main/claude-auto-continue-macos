#!/usr/bin/env bash
# Find the running claude-auto-continue dashboard and open it in the
# default browser. Probes the default port first, then the fallback
# range the dashboard itself rolls through when the primary port is
# already taken.
#
# Usage: ./scripts/open-dashboard.sh [--print]
#   --print   Print the URL instead of opening it.
set -euo pipefail

HOST="${CLAUDE_AUTO_CONTINUE_DASHBOARD_HOST:-127.0.0.1}"
PRIMARY_PORT="${CLAUDE_AUTO_CONTINUE_DASHBOARD_PORT:-8787}"
PORTS=("$PRIMARY_PORT" 8788 8789 8790 8791 8792)

PRINT_ONLY=false
if [ "${1:-}" = "--print" ]; then
    PRINT_ONLY=true
fi

probe() {
    # The dashboard advertises itself via /api/state. A 200 OK with
    # "started_at" in the body is a strong signal it's ours and not
    # some other service squatting on the port.
    local url="$1"
    curl --silent --show-error --max-time 1.2 "$url/api/state" 2>/dev/null \
        | grep -q '"started_at"' && return 0 || return 1
}

for port in "${PORTS[@]}"; do
    url="http://${HOST}:${port}"
    if probe "$url"; then
        if [ "$PRINT_ONLY" = true ]; then
            echo "$url"
        else
            echo "Opening $url"
            open "$url"
        fi
        exit 0
    fi
done

echo "No dashboard responding on ${HOST}:${PORTS[*]}." >&2
echo "Start it with: claude-auto-continue" >&2
exit 1
