#!/usr/bin/env bash
# ============================================================
# MisMiss -- Release Build Script (Linux / macOS)
# ============================================================
# Builds all distribution formats for a GitHub release.
#
# Naming: mismiss-<version>[-<platform>].<ext>
#
# Usage:
#   bash scripts/release.sh
#   bash scripts/release.sh -v 1.1.0
#   bash scripts/release.sh --skip-pyinstaller
#   bash scripts/release.sh --skip-docker
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VERSION=""
SKIP_DOCKER=false
SKIP_PYINSTALLER=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--version) VERSION="$2"; shift 2 ;;
        --skip-docker) SKIP_DOCKER=true; shift ;;
        --skip-pyinstaller) SKIP_PYINSTALLER=true; shift ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# ------------------------------------------------------------------ #
# Version detection
# ------------------------------------------------------------------ #
detect_version() {
    # 1. CLI parameter
    if [ -n "$VERSION" ]; then echo "$VERSION"; return; fi

    # 2. pyproject.toml
    if [ -f pyproject.toml ]; then
        local v; v=$(grep -oP 'version\s*=\s*"\K[^"]+' pyproject.toml | head -1)
        if [ -n "$v" ]; then echo "$v"; return; fi
    fi

    # 3. Git tag
    if command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null 2>&1; then
        local tag; tag=$(git describe --tags --abbrev=0 2>/dev/null || true)
        if [ -n "$tag" ]; then echo "${tag#v}"; return; fi
    fi

    # 4. Date fallback
    date +%Y.%-m.%-d
}

VERSION=$(detect_version)
# SemVer clean: strip leading 'v', preserve pre-release (-beta.2) and build (+hash)
SEMVER="${VERSION#v}"
SEMVER="${SEMVER// /}"

# Short hash for dev builds
SHORT_HASH=""
if command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null 2>&1; then
    SHORT_HASH=$(git rev-parse --short=7 HEAD 2>/dev/null || true)
fi

# ------------------------------------------------------------------ #
# Platform
# ------------------------------------------------------------------ #
case "$(uname -s)" in
    Linux*)  PLATFORM="linux" ;;
    Darwin*) PLATFORM="macos" ;;
    *)       PLATFORM="linux" ;;
esac

# ------------------------------------------------------------------ #
# Archive names
# ------------------------------------------------------------------ #
SRC_NAME="mismiss-${SEMVER}"
if [ -n "$SHORT_HASH" ]; then
    EXE_NAME="mismiss-${SEMVER}-${PLATFORM}-${SHORT_HASH}"
else
    EXE_NAME="mismiss-${SEMVER}-${PLATFORM}"
fi

RELEASE_DIR="$PROJECT_ROOT/release"

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "         -> ${GREEN}$*${NC}"; }
die()  { echo -e "${RED}ERROR: $*${NC}"; exit 1; }
_size() { du -sh "$1" 2>/dev/null | cut -f1; }

check_cmd() { command -v "$1" &>/dev/null || die "$1 is required"; }

# ------------------------------------------------------------------ #
# Prepare
# ------------------------------------------------------------------ #
echo ""
echo "  =========================================="
echo "   MisMiss Release Builder"
echo "   Version: $VERSION"
[ -n "$SHORT_HASH" ] && echo "   Commit:  $SHORT_HASH"
echo "  =========================================="
echo ""

step "Preparing release directory ..."
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"
rm -rf "$PROJECT_ROOT/build"

# ------------------------------------------------------------------ #
# 1. Build frontend
# ------------------------------------------------------------------ #
step "[1/6] Building frontend ..."
check_cmd node; check_cmd npm

cd "$PROJECT_ROOT/web/frontend"
[ -d node_modules ] || npm ci --silent
npm run build
cd "$PROJECT_ROOT"
ok "dist ready"

# ------------------------------------------------------------------ #
# 2. Source archives
# ------------------------------------------------------------------ #
step "[2/6] Building source archives ..."

BUILD_DIR="$PROJECT_ROOT/build/$SRC_NAME"
mkdir -p "$BUILD_DIR"

cp -r "$PROJECT_ROOT/src"                "$BUILD_DIR/"
mkdir -p "$BUILD_DIR/web/backend"
cp -r "$PROJECT_ROOT/web/backend"/*.py   "$BUILD_DIR/web/backend/" 2>/dev/null || true
cp -r "$PROJECT_ROOT/web/backend/api"    "$BUILD_DIR/web/backend/"
mkdir -p "$BUILD_DIR/web/frontend/dist"
cp -r "$PROJECT_ROOT/web/frontend/dist"/* "$BUILD_DIR/web/frontend/dist/"
cp "$PROJECT_ROOT/config.yml"            "$BUILD_DIR/"
cp "$PROJECT_ROOT/requirements.txt"      "$BUILD_DIR/"
cp "$PROJECT_ROOT/pyproject.toml"        "$BUILD_DIR/"
cp "$PROJECT_ROOT/mismiss_cli.py"        "$BUILD_DIR/"
cp "$PROJECT_ROOT/README.md"             "$BUILD_DIR/"

mkdir -p "$BUILD_DIR/scripts"
cp "$PROJECT_ROOT/scripts/"*             "$BUILD_DIR/scripts/" 2>/dev/null || true
mkdir -p "$BUILD_DIR"/{data,logs,plugins,permissions}

find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

cd "$PROJECT_ROOT/build"
tar -czf "$RELEASE_DIR/${SRC_NAME}.tar.gz" "$SRC_NAME"
zip -qr "$RELEASE_DIR/${SRC_NAME}.zip" "$SRC_NAME"
cd "$PROJECT_ROOT"

ok "source zip      ${SRC_NAME}.zip  ($(_size "$RELEASE_DIR/${SRC_NAME}.zip"))"
ok "source tar.gz   ${SRC_NAME}.tar.gz  ($(_size "$RELEASE_DIR/${SRC_NAME}.tar.gz"))"

rm -rf "$BUILD_DIR"

# ------------------------------------------------------------------ #
# 3. pip wheel
# ------------------------------------------------------------------ #
step "[3/6] Building pip wheel ..."
check_cmd python3 || check_cmd python
PY=$(command -v python3 || command -v python)

"$PY" -m pip install -q --upgrade pip build 2>/dev/null
"$PY" -m build --wheel --outdir "$RELEASE_DIR" "$PROJECT_ROOT"

WHL=$(ls -1 "$RELEASE_DIR"/mismiss-*-py3-none-any.whl 2>/dev/null | head -1)

# PEP 427 normalizes 1.0.0-beta.2 → 1.0.0b2, rename to SemVer
WHL_SEMVER="$RELEASE_DIR/mismiss-${SEMVER}-py3-none-any.whl"
if [ "$WHL" != "$WHL_SEMVER" ] && [ -f "$WHL" ]; then
    mv "$WHL" "$WHL_SEMVER"
    WHL="$WHL_SEMVER"
fi

ok "wheel           $(basename "$WHL")  ($(_size "$WHL"))"

# ------------------------------------------------------------------ #
# 4. PyInstaller
# ------------------------------------------------------------------ #
if $SKIP_PYINSTALLER; then
    step "[4/5] PyInstaller -- SKIPPED"
else
    step "[4/6] Building PyInstaller standalone binary ..."
    check_cmd python3 || check_cmd python

    "$PY" -m pip install -q pyinstaller 2>/dev/null

    "$PY" -m PyInstaller \
        --distpath "$RELEASE_DIR" \
        --workpath "$PROJECT_ROOT/build/pyinstaller" \
        --specpath "$PROJECT_ROOT/build" \
        --name "$EXE_NAME" \
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

    BINARY=""
    if [ -f "$RELEASE_DIR/${EXE_NAME}.exe" ]; then
        BINARY="${EXE_NAME}.exe"
    elif [ -f "$RELEASE_DIR/$EXE_NAME" ]; then
        BINARY="$EXE_NAME"
    fi
    ok "binary          $BINARY  ($(_size "$RELEASE_DIR/$BINARY"))"
fi

# ------------------------------------------------------------------ #
# 5. Docker deploy package (via docker-release.sh)
# ------------------------------------------------------------------ #
if $SKIP_DOCKER; then
    step "[5/6] Docker package -- SKIPPED"
elif command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    step "[5/6] Building Docker deploy package ..."

    bash "$PROJECT_ROOT/scripts/docker-release.sh" "$SEMVER"

    DOCKER_FILE="mismiss-${SEMVER}-docker.tar.gz"
    cp "$PROJECT_ROOT/dist/$DOCKER_FILE" "$RELEASE_DIR/"

    ok "docker package $DOCKER_FILE  ($(_size "$RELEASE_DIR/$DOCKER_FILE"))"
else
    step "[5/6] Docker package -- Docker not available, skipped"
fi

# ------------------------------------------------------------------ #
# 6. Checksums
# ------------------------------------------------------------------ #
step "[6/6] Generating checksums ..."

CHECKSUM_NAME="checksums-${SEMVER}.txt"
cd "$RELEASE_DIR"
for f in *; do
    if [ "$f" != "$CHECKSUM_NAME" ] && [ -f "$f" ]; then
        sha256sum "$f" >> "$CHECKSUM_NAME"
    fi
done
cd "$PROJECT_ROOT"

ok "checksums      $CHECKSUM_NAME"

# ------------------------------------------------------------------ #
# Done
# ------------------------------------------------------------------ #
RELEASE_SIZE=$(du -sh "$RELEASE_DIR" 2>/dev/null | cut -f1)

echo ""
echo "  =========================================="
echo -e "  ${GREEN} RELEASE BUILD COMPLETE${NC}"
echo "  =========================================="
echo ""
echo "  Output: $RELEASE_DIR"
echo "  Size:   $RELEASE_SIZE"
echo ""

ls -lh "$RELEASE_DIR" | tail -n +2 | while read -r line; do
    echo "    $line"
done

echo ""
echo "  --- Release notes table ---"
ls -lh "$RELEASE_DIR" | tail -n +2 | while read -r _ _ size _ _ name; do
    if echo "$name" | grep -qvE '^checksums'; then
        echo "  | $name | $size |"
    fi
done
