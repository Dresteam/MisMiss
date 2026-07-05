#!/usr/bin/env bash
# ============================================================
# MisMiss — 启动脚本 (Linux / macOS)
# ============================================================
# 用法:
#   bash scripts/start.sh              # 开发模式（前后端分离，热重载）
#   bash scripts/start.sh --prod       # 生产模式（构建前端 → 单端口）
#   bash scripts/start.sh --backend    # 仅启动后端
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MODE="${1:-dev}"
API_PORT="${MISMISS_API_PORT:-8080}"
WEB_PORT="${MISMISS_WEB_PORT:-5173}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

find_python() {
    if command -v python3 &>/dev/null; then echo "python3"
    elif command -v python &>/dev/null; then echo "python"
    else die "Python 未安装"; fi
}

# ------------------------------------------------------------------ #
# 安装依赖
# ------------------------------------------------------------------ #
setup_backend() {
    local PY; PY=$(find_python)
    if [ ! -d "$PROJECT_ROOT/.venv" ]; then
        info "创建虚拟环境..."
        "$PY" -m venv "$PROJECT_ROOT/.venv"
    fi
    source "$PROJECT_ROOT/.venv/bin/activate"
    info "安装后端依赖..."
    pip install -q -r "$PROJECT_ROOT/requirements.txt"
    pip install -q -r "$PROJECT_ROOT/web/backend/requirements.txt"
}

setup_frontend() {
    if ! command -v node &>/dev/null; then die "Node.js 未安装"; fi
    if [ ! -d "$PROJECT_ROOT/web/frontend/node_modules" ]; then
        info "安装前端依赖..."
        cd "$PROJECT_ROOT/web/frontend"
        npm install --silent
        cd "$PROJECT_ROOT"
    fi
}

ensure_dirs() {
    mkdir -p "$PROJECT_ROOT"/{data,logs,plugins,permissions}
}

# ------------------------------------------------------------------ #
# 启动模式
# ------------------------------------------------------------------ #
start_dev() {
    info "开发模式"
    setup_backend
    setup_frontend
    ensure_dirs
    source "$PROJECT_ROOT/.venv/bin/activate"

    info "后端 (port $API_PORT, --reload)"
    python -m uvicorn web.backend.main:app \
        --host 0.0.0.0 --port "$API_PORT" --reload \
        --reload-dir "$PROJECT_ROOT/src" \
        --reload-dir "$PROJECT_ROOT/web/backend" &
    BACKEND_PID=$!

    info "前端 (port $WEB_PORT)"
    cd "$PROJECT_ROOT/web/frontend"
    npx vite --host 0.0.0.0 --port "$WEB_PORT" &
    FRONTEND_PID=$!
    cd "$PROJECT_ROOT"

    echo ""
    echo "  API  : http://localhost:$API_PORT/docs"
    echo "  Web  : http://localhost:$WEB_PORT"
    echo ""
    echo "  Ctrl+C 停止"

    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
    wait
}

start_prod() {
    info "生产模式"
    setup_backend

    # 构建前端（如未构建）
    if [ ! -d "$PROJECT_ROOT/web/frontend/dist" ]; then
        if command -v node &>/dev/null; then
            info "构建前端..."
            cd "$PROJECT_ROOT/web/frontend"
            [ -d node_modules ] || npm install --silent
            npm run build
            cd "$PROJECT_ROOT"
        else
            warn "Node.js 未安装，跳过前端构建"
        fi
    fi

    ensure_dirs
    source "$PROJECT_ROOT/.venv/bin/activate"

    echo ""
    echo "  Web  : http://localhost:$API_PORT"
    echo "  API  : http://localhost:$API_PORT/docs"
    echo ""

    MISMISS_PROD=1 python -m uvicorn web.backend.main:app --host 0.0.0.0 --port "$API_PORT"
}

start_backend() {
    info "仅后端模式"
    setup_backend
    ensure_dirs
    source "$PROJECT_ROOT/.venv/bin/activate"

    python -m uvicorn web.backend.main:app \
        --host 0.0.0.0 --port "$API_PORT" --reload
}

# ------------------------------------------------------------------ #
# 入口
# ------------------------------------------------------------------ #
case "$MODE" in
    dev|--dev)         start_dev ;;
    prod|--prod)       start_prod ;;
    backend|--backend|--api) start_backend ;;
    *) echo "用法: bash scripts/start.sh [dev|prod|backend]"; exit 1 ;;
esac
