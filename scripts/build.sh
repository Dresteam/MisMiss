#!/usr/bin/env bash
# ============================================================
# MisMiss — 一键打包脚本 (Linux / macOS)
# ============================================================
# 用法:
#   bash scripts/build.sh              # 交互式选择
#   bash scripts/build.sh archive      # 构建 .tar.gz + .zip 分发包
#   bash scripts/build.sh wheel        # 构建 pip wheel
#   bash scripts/build.sh exe          # PyInstaller 独立可执行文件
#   bash scripts/build.sh all          # archive + wheel
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VERSION="${MISMISS_VERSION:-1.0.0}"
RELEASE_NAME="mismiss-${VERSION}"
BUILD_DIR="$PROJECT_ROOT/build/${RELEASE_NAME}"
DIST_DIR="$PROJECT_ROOT/dist"

# ------------------------------------------------------------------ #
# 颜色输出
# ------------------------------------------------------------------ #
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ------------------------------------------------------------------ #
# 辅助
# ------------------------------------------------------------------ #
require_cmd() { command -v "$1" &>/dev/null || die "缺少命令: $1，请先安装"; }
file_size()  { du -sh "$1" 2>/dev/null | cut -f1; }

# ------------------------------------------------------------------ #
# 清理
# ------------------------------------------------------------------ #
do_clean() {
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR" "$DIST_DIR"
}

# ------------------------------------------------------------------ #
# 1. 构建前端
# ------------------------------------------------------------------ #
build_frontend() {
    step "构建前端 (React + Vite) ..."
    cd "$PROJECT_ROOT/web/frontend"

    require_cmd node
    require_cmd npm

    if [ ! -d "node_modules" ]; then
        info "安装前端依赖..."
        npm ci --silent 2>/dev/null || npm install --silent
    fi

    npm run build
    cd "$PROJECT_ROOT"
    info "前端构建完成 → web/frontend/dist/"
}

# ------------------------------------------------------------------ #
# 2. 收集分发文件
# ------------------------------------------------------------------ #
collect_files() {
    step "收集分发文件 → $BUILD_DIR/"

    # — Python 源码 —
    cp -r "$PROJECT_ROOT/src"                "$BUILD_DIR/"

    # — Web 后端 —
    mkdir -p "$BUILD_DIR/web/backend"
    cp -r "$PROJECT_ROOT/web/backend"/*.py   "$BUILD_DIR/web/backend/" 2>/dev/null || true
    cp -r "$PROJECT_ROOT/web/backend/api"    "$BUILD_DIR/web/backend/"

    # — 前端（已构建） —
    mkdir -p "$BUILD_DIR/web/frontend/dist"
    cp -r "$PROJECT_ROOT/web/frontend/dist"/* "$BUILD_DIR/web/frontend/dist/"

    # — 运行时文件 —
    cp "$PROJECT_ROOT/config.yml"            "$BUILD_DIR/"
    cp "$PROJECT_ROOT/requirements.txt"      "$BUILD_DIR/"
    cp "$PROJECT_ROOT/pyproject.toml"        "$BUILD_DIR/"
    cp "$PROJECT_ROOT/mismiss_cli.py"        "$BUILD_DIR/"

    # — 脚本 —
    cp "$PROJECT_ROOT/scripts/start.sh"      "$BUILD_DIR/"
    cp "$PROJECT_ROOT/scripts/start.bat"     "$BUILD_DIR/"
    cp "$PROJECT_ROOT/scripts/deploy.sh"     "$BUILD_DIR/"
    cp "$PROJECT_ROOT/scripts/deploy.ps1"    "$BUILD_DIR/"

    # — 文档 —
    cp "$PROJECT_ROOT/README.md"             "$BUILD_DIR/"

    # — 运行时空目录 —
    mkdir -p "$BUILD_DIR/"{data,logs,plugins,permissions}

    # — 清理缓存 —
    find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$BUILD_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

    chmod +x "$BUILD_DIR/start.sh"  2>/dev/null || true
    chmod +x "$BUILD_DIR/deploy.sh" 2>/dev/null || true

    info "文件收集完成 ($(file_size "$BUILD_DIR"))"
}

# ------------------------------------------------------------------ #
# 3. 创建归档
# ------------------------------------------------------------------ #
create_archives() {
    step "压缩归档 → $DIST_DIR/"

    cd "$PROJECT_ROOT/build"

    info "创建 ${RELEASE_NAME}.tar.gz ..."
    tar -czf "$DIST_DIR/${RELEASE_NAME}.tar.gz" "$RELEASE_NAME"

    info "创建 ${RELEASE_NAME}.zip ..."
    zip -qr "$DIST_DIR/${RELEASE_NAME}.zip" "$RELEASE_NAME"

    cd "$PROJECT_ROOT"

    echo ""
    echo "  ╔══════════════════════════════════╗"
    echo "  ║        BUILD SUCCESS             ║"
    echo "  ╠══════════════════════════════════╣"
    printf "  ║  %-30s  ║\n" "${RELEASE_NAME}.tar.gz  $(file_size "$DIST_DIR/${RELEASE_NAME}.tar.gz")"
    printf "  ║  %-30s  ║\n" "${RELEASE_NAME}.zip      $(file_size "$DIST_DIR/${RELEASE_NAME}.zip")"
    echo "  ╚══════════════════════════════════╝"
    echo ""
    info "部署方使用方式:"
    echo ""
    echo "  # 1. 解压"
    echo "  unzip ${RELEASE_NAME}.zip && cd ${RELEASE_NAME}"
    echo ""
    echo "  # 2. 安装依赖（只需 Python 3.13+，不需要 Node.js）"
    echo "  pip install -r requirements.txt"
    echo "  pip install fastapi \"uvicorn[standard]\" pydantic python-multipart"
    echo ""
    echo "  # 3. 启动"
    echo "  ./start.sh --prod        # 单端口 8080"
    echo ""
    echo "  # 4. 访问"
    echo "  http://localhost:8080"
}

# ------------------------------------------------------------------ #
# 4. pip wheel
# ------------------------------------------------------------------ #
build_wheel() {
    step "构建 pip wheel ..."
    require_cmd python3 || require_cmd python

    local PY; PY=$(command -v python3 || command -v python)

    "$PY" -m pip install -q --upgrade pip build 2>/dev/null
    "$PY" -m build --wheel --outdir "$DIST_DIR" "$PROJECT_ROOT"

    local WHL; WHL=$(ls -1 "$DIST_DIR"/mismiss-*.whl 2>/dev/null | head -1)
    echo ""
    info "Wheel: $WHL  ($(file_size "$WHL"))"
    echo ""
    info "部署方安装:"
    echo "  pip install ${RELEASE_NAME}-py3-none-any.whl[web]"
    echo "  mismiss-web    # 启动"
}

# ------------------------------------------------------------------ #
# 5. PyInstaller 独立可执行文件
# ------------------------------------------------------------------ #
build_pyinstaller() {
    step "PyInstaller 独立可执行文件 ..."
    require_cmd python3 || require_cmd python
    local PY; PY=$(command -v python3 || command -v python)

    # 确保前端已构建
    if [ ! -d "$PROJECT_ROOT/web/frontend/dist" ]; then
        build_frontend
    fi

    "$PY" -m pip install -q pyinstaller 2>/dev/null

    "$PY" -m PyInstaller \
        --distpath "$DIST_DIR" \
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
        --collect-all "fastapi" \
        --collect-all "uvicorn" \
        "$PROJECT_ROOT/scripts/pyinstaller_entry.py"

    local EXE
    if [ -f "$DIST_DIR/mismiss.exe" ]; then
        EXE="$DIST_DIR/mismiss.exe"
    else
        EXE="$DIST_DIR/mismiss"
    fi

    echo ""
    echo "  ╔══════════════════════════════════╗"
    echo "  ║     PYINSTALLER BUILD DONE       ║"
    echo "  ╠══════════════════════════════════╣"
    printf "  ║  %-30s  ║\n" "$(basename "$EXE")  $(file_size "$EXE")"
    echo "  ╚══════════════════════════════════╝"
    echo ""
    info "目标机器无需 Python/Node.js，直接运行:"
    echo "  ${EXE}"
    echo "  ${EXE} --port 9000"
}

# ------------------------------------------------------------------ #
# 入口
# ------------------------------------------------------------------ #
print_banner() {
    echo ""
    echo "  ╔══════════════════════════════════╗"
    echo "  ║     MisMiss 打包构建工具         ║"
    printf "  ║     v%-27s ║\n" "$VERSION"
    echo "  ╚══════════════════════════════════╝"
    echo ""
}

main() {
    print_banner

    MODE="${1:-}"

    # 交互式选择
    if [ -z "$MODE" ]; then
        echo "请选择打包方式:"
        echo "  1) archive  — 源码分发包 (.tar.gz + .zip)"
        echo "  2) wheel    — pip wheel (.whl)"
        echo "  3) exe      — PyInstaller 独立可执行文件"
        echo "  4) all      — archive + wheel"
        read -rp "输入数字 [1-4] (默认=1): " choice
        case "${choice:-1}" in
            1) MODE="archive" ;;
            2) MODE="wheel" ;;
            3) MODE="exe" ;;
            4) MODE="all" ;;
            *) die "无效选择" ;;
        esac
    fi

    case "$MODE" in
        archive|--archive)
            do_clean
            build_frontend
            collect_files
            create_archives
            ;;
        wheel|--wheel)
            build_wheel
            ;;
        exe|--exe|pyinstaller|--pyinstaller)
            build_pyinstaller
            ;;
        all|--all)
            do_clean
            build_frontend
            collect_files
            create_archives
            build_wheel
            echo ""
            warn "提示: PyInstaller 构建请单独运行: bash scripts/build.sh exe"
            ;;
        clean|--clean)
            step "清理构建产物..."
            rm -rf "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
            info "已清理 build/ 和 dist/"
            ;;
        *)
            echo "用法: bash scripts/build.sh [archive|wheel|exe|all|clean]"
            echo ""
            echo "  archive  — .tar.gz + .zip 分发包（默认，推荐）"
            echo "  wheel    — pip wheel"
            echo "  exe      — PyInstaller 独立可执行文件（零依赖）"
            echo "  all      — archive + wheel"
            echo "  clean    — 清理构建产物"
            exit 1
            ;;
    esac
}

main "$@"
