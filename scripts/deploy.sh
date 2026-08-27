#!/usr/bin/env bash
# ============================================================
# MisMiss — 部署脚本 (Linux，原生 systemd + venv)
# ============================================================
# Docker 部署请走部署包流程（镜像不推仓库）:
#   本地:   bash scripts/docker-release.sh   → dist/mismiss-<版本>-docker.tar.gz
#   服务器: 解压部署包 → ./deploy.sh
# ============================================================
# 用法:
#   bash scripts/deploy.sh              # 原生部署（systemd + venv）
#   bash scripts/deploy.sh --native     # 同上
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
    echo "  === MisMiss 部署工具（原生 systemd + venv）==="
    echo ""
    echo "  Docker 部署请使用部署包（镜像不推仓库）:"
    echo "    本地:   bash scripts/docker-release.sh"
    echo "    服务器: 解压部署包后执行 ./deploy.sh"
    echo ""

    MODE="${1:---native}"
    case "$MODE" in
        --native) deploy_native ;;
        --docker) die "Docker 部署已改为部署包流程，见 scripts/docker-release.sh" ;;
        *) echo "用法: bash scripts/deploy.sh [--native]"; exit 1 ;;
    esac
}

main "$@"
