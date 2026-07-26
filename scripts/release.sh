#!/usr/bin/env bash
# ============================================================
# MisMiss -- Release Build Script (Linux / macOS)
# ============================================================
# Builds all distribution formats for a GitHub release.
#
# Usage:
#   bash scripts/release.sh
#   bash scripts/release.sh -v 1.2.0
#   bash scripts/release.sh --skip-pyinstaller
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VERSION="${MISMISS_VERSION:-}"
SKIP_DOCKER=false
SKIP_PYINSTALLER=false

# ------------------------------------------------------------------ #
# Parse args
# ------------------------------------------------------------------ #
while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--version) VERSION="$2"; shift 2 ;;
        --skip-docker) SKIP_DOCKER=true; shift ;;
        --skip-pyinstaller) SKIP_PYINSTALLER=true; shift ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# Version from date if not set
if [ -z "$VERSION" ]; then
    VERSION="$(date +%Y.%-m.%-d)"
fi

ARCHIVE_NAME="mismiss-${VERSION}"
VERSION_CLEAN="${VERSION//[^0-9.]/}"
RELEASE_DIR="$PROJECT_ROOT/release"

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "         -> ${GREEN}$*${NC}"; }
die()  { echo -e "${RED}ERROR: $*${NC}"; exit 1; }
size() { du -sh "$1" 2>/dev/null | cut -f1; }

check_cmd() { command -v "$1" &>/dev/null || die "$1 is required"; }

# ------------------------------------------------------------------ #
# Prepare
# ------------------------------------------------------------------ #
step "Preparing release directory ..."
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"
rm -rf "$PROJECT_ROOT/build"

echo ""
echo "  =========================================="
echo "   MisMiss Release Builder v${VERSION}"
echo "  =========================================="
echo ""

# ------------------------------------------------------------------ #
# 1. Build frontend
# ------------------------------------------------------------------ #
step "[1/5] Building frontend ..."
check_cmd node; check_cmd npm

cd "$PROJECT_ROOT/web/frontend"
[ -d node_modules ] || npm ci --silent
npm run build
cd "$PROJECT_ROOT"
ok "dist ready"

# ------------------------------------------------------------------ #
# 2. Source archives
# ------------------------------------------------------------------ #
step "[2/5] Building source archives ..."

BUILD_DIR="$PROJECT_ROOT/build/$ARCHIVE_NAME"
mkdir -p "$BUILD_DIR"

# Source code
cp -r "$PROJECT_ROOT/src"                "$BUILD_DIR/"
mkdir -p "$BUILD_DIR/web/backend"
cp -r "$PROJECT_ROOT/web/backend"/*.py   "$BUILD_DIR/web/backend/" 2>/dev/null || true
cp -r "$PROJECT_ROOT/web/backend/api"    "$BUILD_DIR/web/backend/"
mkdir -p "$BUILD_DIR/web/frontend/dist"
cp -r "$PROJECT_ROOT/web/frontend/dist"/* "$BUILD_DIR/web/frontend/dist/"

# Config & metadata
cp "$PROJECT_ROOT/config.yml"            "$BUILD_DIR/"
cp "$PROJECT_ROOT/requirements.txt"      "$BUILD_DIR/"
cp "$PROJECT_ROOT/pyproject.toml"        "$BUILD_DIR/"
cp "$PROJECT_ROOT/mismiss_cli.py"        "$BUILD_DIR/"
cp "$PROJECT_ROOT/README.md"             "$BUILD_DIR/"

# Scripts
mkdir -p "$BUILD_DIR/scripts"
cp "$PROJECT_ROOT/scripts/"*             "$BUILD_DIR/scripts/" 2>/dev/null || true

# Runtime dirs
mkdir -p "$BUILD_DIR"/{data,logs,plugins,permissions}

# Clean
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

# Create archives
cd "$PROJECT_ROOT/build"
tar -czf "$RELEASE_DIR/${ARCHIVE_NAME}.tar.gz" "$ARCHIVE_NAME"
zip -qr "$RELEASE_DIR/${ARCHIVE_NAME}.zip" "$ARCHIVE_NAME"
cd "$PROJECT_ROOT"

ok "source .tar.gz  ($(size "$RELEASE_DIR/${ARCHIVE_NAME}.tar.gz"))"
ok "source .zip     ($(size "$RELEASE_DIR/${ARCHIVE_NAME}.zip"))"

rm -rf "$BUILD_DIR"

# ------------------------------------------------------------------ #
# 3. pip wheel
# ------------------------------------------------------------------ #
step "[3/5] Building pip wheel ..."
check_cmd python3 || check_cmd python
PY=$(command -v python3 || command -v python)

"$PY" -m pip install -q --upgrade pip build 2>/dev/null
"$PY" -m build --wheel --outdir "$RELEASE_DIR" "$PROJECT_ROOT"

WHL=$(ls -1 "$RELEASE_DIR"/mismiss-*.whl 2>/dev/null | head -1)
ok "wheel  ($(size "$WHL"))"

# ------------------------------------------------------------------ #
# 4. PyInstaller
# ------------------------------------------------------------------ #
if $SKIP_PYINSTALLER; then
    step "[4/5] PyInstaller -- SKIPPED"
else
    step "[4/5] Building PyInstaller standalone binary ..."
    check_cmd python3 || check_cmd python

    "$PY" -m pip install -q pyinstaller 2>/dev/null

    "$PY" -m PyInstaller \
        --distpath "$RELEASE_DIR" \
        --workpath "$PROJECT_ROOT/build/pyinstaller" \
        --specpath "$PROJECT_ROOT/build" \
        --name "mismiss" \
        --onefile \
        --console \
        --clean \
        --add-data "$PROJECT_ROOT/web/frontend/dist:web/frontend/dist" \
        --add-data "$PROJECT_ROOT/config.yml:." \
        --add-data "$PROJECT_ROOT/src:src" \
        --add-data "$PROJECT_ROOT/web/backend:web/backend" \
        --hidden-import "core" \
        --hidden-import "core.server" \
        --hidden-import "core.bot.mis_bot" \
        --hidden-import "core.events.bus" \
        --hidden-import "core.livestream.mis_livestream" \
        --hidden-import "core.plugin.plugin_manager" \
        --hidden-import "core.network.client" \
        --hidden-import "core.logging" \
        --hidden-import "core.config" \
        --hidden-import "interfaces" \
        --hidden-import "interfaces.server" \
        --hidden-import "interfaces.bot.bot" \
        --hidden-import "interfaces.event.event" \
        --hidden-import "interfaces.plugin.plugin" \
        --hidden-import "uvicorn" \
        --hidden-import "uvicorn.loops.auto" \
        --hidden-import "uvicorn.protocols.http.auto" \
        --hidden-import "fastapi" \
        --hidden-import "websockets" \
        --hidden-import "httpx" \
        --hidden-import "brotli" \
        --hidden-import "loguru" \
        --hidden-import "yaml" \
        --exclude-module "pip" \
        --exclude-module "pip._vendor" \
        --exclude-module "pip._internal" \
        --collect-all "fastapi" \
        --collect-all "uvicorn" \
        "$PROJECT_ROOT/scripts/pyinstaller_entry.py"

    if [ -f "$RELEASE_DIR/mismiss.exe" ]; then
        ok "exe  ($(size "$RELEASE_DIR/mismiss.exe"))"
    else
        ok "binary  ($(size "$RELEASE_DIR/mismiss"))"
    fi
fi

# ------------------------------------------------------------------ #
# 5. Checksums
# ------------------------------------------------------------------ #
step "[5/5] Generating checksums ..."

CHECKSUM_FILE="$RELEASE_DIR/checksums_${VERSION_CLEAN}.txt"
cd "$RELEASE_DIR"
for f in *; do
    if [ "$f" != "$(basename "$CHECKSUM_FILE")" ] && [ -f "$f" ]; then
        sha256sum "$f" >> "$CHECKSUM_FILE"
    fi
done
cd "$PROJECT_ROOT"

ok "SHA256 checksums"

# ------------------------------------------------------------------ #
# Done
# ------------------------------------------------------------------ #
RELEASE_SIZE=$(du -sh "$RELEASE_DIR" 2>/dev/null | cut -f1)

echo ""
echo "  =========================================="
echo -e "  ${GREEN} RELEASE v${VERSION} BUILD COMPLETE${NC}"
echo "  =========================================="
echo ""
echo "  Output: $RELEASE_DIR"
echo "  Size:   $RELEASE_SIZE"
echo ""

ls -lh "$RELEASE_DIR" | tail -n +2 | while read -r line; do
    echo "    $line"
done

echo ""
echo "  Draft release notes:"
echo ""
echo "  ## v${VERSION}"
echo "  | Asset | Size |"
echo "  |-------|------|"

ls -lh "$RELEASE_DIR" | tail -n +2 | while read -r _ _ size _ _ name; do
    if echo "$name" | grep -qE '\.(zip|gz|whl|exe)$|^mismiss$'; then
        echo "  | $name | $size |"
    fi
done
