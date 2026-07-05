#!/usr/bin/env bash
# ============================================================
# MisMiss — 部署脚本 (Linux)
# ============================================================
# 用法:
#   bash scripts/deploy.sh              # 交互式
#   bash scripts/deploy.sh --docker     # Docker 部署
#   bash scripts/deploy.sh --native     # 原生部署（systemd + venv）
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

require_cmd() { command -v "$1" &>/dev/null || die "缺少命令: $1"; }

# ------------------------------------------------------------------ #
# Docker 部署
# ------------------------------------------------------------------ #
deploy_docker() {
    require_cmd docker
    step "Docker 部署"

    mkdir -p "$PROJECT_ROOT"/{data,logs,plugins,permissions}

    info "构建镜像..."
    docker build -t mismiss:latest "$PROJECT_ROOT"

    if docker compose version &>/dev/null 2>&1; then
        docker compose up -d
    elif command -v docker-compose &>/dev/null; then
        docker-compose up -d
    else
        docker rm -f mismiss 2>/dev/null || true
        docker run -d --name mismiss --restart unless-stopped \
            -p 8080:8080 \
            -v "$PROJECT_ROOT/data:/app/data" \
            -v "$PROJECT_ROOT/logs:/app/logs" \
            -v "$PROJECT_ROOT/plugins:/app/plugins" \
            -v "$PROJECT_ROOT/permissions:/app/permissions" \
            -v "$PROJECT_ROOT/config.yml:/app/config.yml:ro" \
            -e TZ=Asia/Shanghai \
            mismiss:latest
    fi

    info "部署完成 → http://localhost:8080"
    info "管理:  docker compose logs -f    |    docker compose down"
}

# ------------------------------------------------------------------ #
# 原生部署
# ------------------------------------------------------------------ #
deploy_native() {
    step "原生部署 (venv + systemd)"

    local PY; PY=$(command -v python3 || command -v python || die "缺少 Python 3.13+")

    # 虚拟环境
    if [ ! -d "$PROJECT_ROOT/.venv" ]; then
        info "创建虚拟环境..."
        "$PY" -m venv "$PROJECT_ROOT/.venv"
    fi
    source "$PROJECT_ROOT/.venv/bin/activate"

    info "安装依赖..."
    pip install -q --upgrade pip
    pip install -q -r "$PROJECT_ROOT/requirements.txt"
    pip install -q -r "$PROJECT_ROOT/web/backend/requirements.txt"

    # 前端构建
    if [ ! -d "$PROJECT_ROOT/web/frontend/dist" ]; then
        if command -v node &>/dev/null; then
            info "构建前端..."
            cd "$PROJECT_ROOT/web/frontend"
            [ -d node_modules ] || npm ci --silent 2>/dev/null || npm install --silent
            npm run build
            cd "$PROJECT_ROOT"
        else
            warn "Node.js 未安装，跳过前端构建（仅 API 可用）"
        fi
    fi

    mkdir -p "$PROJECT_ROOT"/{data,logs,plugins,permissions}
    deactivate

    # systemd 服务
    SERVICE_FILE="/etc/systemd/system/mismiss.service"
    if [ "$(id -u)" -eq 0 ]; then
        step "安装 systemd 服务..."
        local USER; USER=$(logname 2>/dev/null || echo "$SUDO_USER" || whoami)

        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=MisMiss — 猫耳FM 直播场控机器人
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_ROOT
Environment=PATH=$PROJECT_ROOT/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
Environment=TZ=Asia/Shanghai
Environment=MISMISS_PROD=1
ExecStart=$PROJECT_ROOT/.venv/bin/python -m uvicorn web.backend.main:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable mismiss
        systemctl start mismiss

        info "服务已安装并启动"
        echo ""
        echo "  管理命令:"
        echo "    systemctl status   mismiss    # 查看状态"
        echo "    systemctl restart  mismiss    # 重启"
        echo "    systemctl stop     mismiss    # 停止"
        echo "    journalctl -u mismiss -f     # 日志"
    else
        warn "非 root，跳过 systemd。手动启动:"
        echo ""
        echo "  cd $PROJECT_ROOT"
        echo "  source .venv/bin/activate"
        echo "  python -m uvicorn web.backend.main:app --host 0.0.0.0 --port 8080"
    fi

    info "部署完成 → http://localhost:8080"
}

# ------------------------------------------------------------------ #
# 入口
# ------------------------------------------------------------------ #
main() {
    echo ""
    echo "  === MisMiss 部署工具 ==="
    echo ""

    MODE="${1:-}"
    if [ -z "$MODE" ]; then
        echo "选择部署方式:"
        echo "  1) Docker  （推荐，隔离环境）"
        echo "  2) Native （systemd + venv）"
        read -rp "输入 [1-2] (默认=1): " choice
        case "${choice:-1}" in
            1) MODE="--docker" ;;
            2) MODE="--native" ;;
            *) die "无效选择" ;;
        esac
    fi

    case "$MODE" in
        --docker) deploy_docker ;;
        --native) deploy_native ;;
        *) echo "用法: bash scripts/deploy.sh [--docker|--native]"; exit 1 ;;
    esac
}

main "$@"
