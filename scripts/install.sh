#!/usr/bin/env bash
# One-command installer for claude-auto-continue-macos.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/PrivateVictories-Main/claude-auto-continue-macos/main/scripts/install.sh | bash
#
# What it does:
#   1. Checks for Python 3.9+
#   2. Clones the repo (or pulls if it already exists)
#   3. Creates a virtualenv and installs dependencies
#   4. Offers to run --setup (Accessibility permission + LaunchAgent)
#
# Everything installs to ~/.claude-auto-continue-macos/ — nothing touches
# /usr/local or system Python. Uninstall by deleting that directory.

set -euo pipefail

REPO_URL="https://github.com/PrivateVictories-Main/claude-auto-continue-macos.git"
INSTALL_DIR="$HOME/.claude-auto-continue-macos"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=9

# ---- helpers ---------------------------------------------------------------

info()  { printf '\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31m✗\033[0m %s\n' "$*"; exit 1; }

# ---- find a suitable Python ------------------------------------------------

find_python() {
    for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$candidate" &>/dev/null; then
            local ver
            ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
            local major minor
            major=${ver%%.*}
            minor=${ver##*.}
            if [[ "$major" -ge "$MIN_PYTHON_MAJOR" && "$minor" -ge "$MIN_PYTHON_MINOR" ]]; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

# ---- pre-flight checks ----------------------------------------------------

info "Checking requirements..."

if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "This tool is macOS-only (it uses the macOS Accessibility API)."
fi

PYTHON=$(find_python) || fail "Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ is required. Install it with: brew install python@3.12"
PYTHON_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Found $PYTHON (Python $PYTHON_VER)"

if ! command -v git &>/dev/null; then
    fail "git is required. Install with: xcode-select --install"
fi
ok "git found"

# ---- clone or update -------------------------------------------------------

if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating existing installation..."
    git -C "$INSTALL_DIR" pull --ff-only origin main 2>/dev/null || true
    ok "Repository updated"
else
    info "Cloning claude-auto-continue-macos..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Cloned to $INSTALL_DIR"
fi

# ---- virtualenv + install --------------------------------------------------

info "Setting up Python environment..."

VENV="$INSTALL_DIR/.venv"
if [[ ! -d "$VENV" ]]; then
    "$PYTHON" -m venv "$VENV"
fi

"$VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
"$VENV/bin/pip" install --quiet -e "$INSTALL_DIR"
ok "Dependencies installed"

# ---- verify it runs --------------------------------------------------------

VERSION=$("$VENV/bin/claude-auto-continue" --version 2>/dev/null) || fail "Installation failed — could not run claude-auto-continue"
ok "Installed: $VERSION"

# ---- shell PATH hint -------------------------------------------------------

BIN_PATH="$VENV/bin/claude-auto-continue"
SHELL_NAME=$(basename "${SHELL:-/bin/zsh}")

add_to_path() {
    local rc_file="$1"
    local alias_line="alias claude-auto-continue='$BIN_PATH'"
    if [[ -f "$rc_file" ]] && grep -qF "claude-auto-continue" "$rc_file" 2>/dev/null; then
        return 0
    fi
    printf '\n# claude-auto-continue\n%s\n' "$alias_line" >> "$rc_file"
    ok "Added alias to $rc_file"
    return 0
}

info "Setting up shell alias..."
case "$SHELL_NAME" in
    zsh)  add_to_path "$HOME/.zshrc" ;;
    bash) add_to_path "$HOME/.bashrc" ;;
    fish)
        mkdir -p "$HOME/.config/fish"
        FISH_CONF="$HOME/.config/fish/config.fish"
        if ! grep -qF "claude-auto-continue" "$FISH_CONF" 2>/dev/null; then
            printf '\nalias claude-auto-continue="%s"\n' "$BIN_PATH" >> "$FISH_CONF"
            ok "Added alias to $FISH_CONF"
        fi
        ;;
    *)    warn "Add this to your shell config: alias claude-auto-continue='$BIN_PATH'" ;;
esac

# ---- offer --setup ---------------------------------------------------------

echo ""
info "Installation complete!"
echo ""
echo "  Next steps:"
echo ""
echo "    1. Open a new terminal (or run: source ~/.${SHELL_NAME}rc)"
echo "    2. Run the setup wizard:"
echo ""
echo "       claude-auto-continue --setup"
echo ""
echo "    This grants Accessibility permission and optionally installs"
echo "    a background service that auto-starts on login."
echo ""
echo "  Or if you want to jump straight in:"
echo ""
echo "       claude-auto-continue"
echo ""

# ---- optional: run setup now -----------------------------------------------

if [[ -t 0 ]]; then
    printf '\033[1;34m==>\033[0m Run --setup now? [Y/n] '
    read -r answer
    case "${answer:-y}" in
        [Yy]|"")
            "$BIN_PATH" --setup
            ;;
        *)
            echo "Skipped. Run 'claude-auto-continue --setup' when ready."
            ;;
    esac
fi
