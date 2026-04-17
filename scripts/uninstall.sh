#!/usr/bin/env bash
# Uninstall claude-auto-continue-macos.
#
# Usage:
#   ./scripts/uninstall.sh          # interactive — confirms before each step
#   ./scripts/uninstall.sh --force  # non-interactive — removes everything
#
# Handles all install methods: Homebrew, curl|bash, and manual.

set -euo pipefail

FORCE=false
[[ "${1:-}" == "--force" ]] && FORCE=true

info()  { printf '\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
skip()  { printf '\033[90m  skipped: %s\033[0m\n' "$*"; }

confirm() {
    if $FORCE; then return 0; fi
    printf '\033[1;34m==>\033[0m %s [y/N] ' "$1"
    read -r answer
    [[ "${answer:-n}" =~ ^[Yy]$ ]]
}

USER_ID=$(id -u)
PLIST_LABEL="com.$(whoami).claude-auto-continue"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
CURL_INSTALL_DIR="$HOME/.claude-auto-continue-macos"
DATA_DIR="$HOME/.claude-auto-continue"

info "claude-auto-continue uninstaller"
echo ""

# ---- 1. Stop LaunchAgent ---------------------------------------------------

if launchctl list 2>/dev/null | grep -q "claude-auto-continue"; then
    if confirm "Stop running LaunchAgent?"; then
        launchctl bootout "gui/$USER_ID" "$PLIST_PATH" 2>/dev/null || true
        ok "LaunchAgent stopped"
    fi
else
    skip "no running LaunchAgent found"
fi

# ---- 2. Remove LaunchAgent plist -------------------------------------------

if [[ -f "$PLIST_PATH" ]]; then
    if confirm "Remove LaunchAgent plist ($PLIST_PATH)?"; then
        rm "$PLIST_PATH"
        ok "Plist removed"
    fi
else
    skip "no plist at $PLIST_PATH"
fi

# ---- 3. Homebrew ------------------------------------------------------------

if command -v brew &>/dev/null && brew list claude-auto-continue &>/dev/null 2>&1; then
    if confirm "Uninstall Homebrew formula?"; then
        brew services stop claude-auto-continue 2>/dev/null || true
        brew uninstall claude-auto-continue
        ok "Homebrew formula uninstalled"
    fi
elif command -v brew &>/dev/null && brew list privatevictories-main/tap/claude-auto-continue &>/dev/null 2>&1; then
    if confirm "Uninstall Homebrew formula?"; then
        brew services stop privatevictories-main/tap/claude-auto-continue 2>/dev/null || true
        brew uninstall privatevictories-main/tap/claude-auto-continue
        ok "Homebrew formula uninstalled"
    fi
else
    skip "not installed via Homebrew"
fi

# ---- 4. curl|bash install dir ----------------------------------------------

if [[ -d "$CURL_INSTALL_DIR" ]]; then
    if confirm "Remove curl|bash install directory ($CURL_INSTALL_DIR)?"; then
        rm -rf "$CURL_INSTALL_DIR"
        ok "Install directory removed"
    fi
else
    skip "no curl|bash install at $CURL_INSTALL_DIR"
fi

# ---- 5. Shell alias ---------------------------------------------------------

for rc_file in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.config/fish/config.fish"; do
    if [[ -f "$rc_file" ]] && grep -q "claude-auto-continue" "$rc_file" 2>/dev/null; then
        if confirm "Remove alias from $rc_file?"; then
            # Remove the comment line and the alias line
            sed -i '' '/# claude-auto-continue/d' "$rc_file"
            sed -i '' '/claude-auto-continue/d' "$rc_file"
            ok "Alias removed from $rc_file"
        fi
    fi
done

# ---- 6. Data directory (logs, config, cache) --------------------------------

if [[ -d "$DATA_DIR" ]]; then
    if confirm "Remove data directory ($DATA_DIR)? Contains logs, config, and cache."; then
        rm -rf "$DATA_DIR"
        ok "Data directory removed"
    else
        skip "kept $DATA_DIR"
    fi
else
    skip "no data directory at $DATA_DIR"
fi

# ---- 7. Homebrew tap --------------------------------------------------------

if command -v brew &>/dev/null && brew tap 2>/dev/null | grep -q "privatevictories-main/tap"; then
    if confirm "Remove Homebrew tap (PrivateVictories-Main/tap)?"; then
        brew untap privatevictories-main/tap
        ok "Tap removed"
    fi
fi

echo ""
ok "Uninstall complete."
