#!/usr/bin/env bash
# ============================================================
# Docker 容器入口脚本
# ============================================================
# 职责：
#   1. 首次运行：复制默认 config.yml → 持久卷
#   2. 确保运行时目录存在
#   3. 启动 Gunicorn + Uvicorn workers
# ============================================================

set -euo pipefail

APP_DIR="${APP_DIR:-/app}"
CONFIG_SRC="$APP_DIR/config.yml.dist"
CONFIG_DST="$APP_DIR/config/config.yml"
PORT="${API_PORT:-8080}"
WORKERS="${WORKERS:-4}"

# ------------------------------------------------------------------ #
# 首次引导：将 config.yml 复制到持久化目录
# ------------------------------------------------------------------ #
if [ ! -f "$CONFIG_DST" ] && [ -f "$CONFIG_SRC" ]; then
    echo "[entrypoint] Bootstrapping config.yml -> $CONFIG_DST"
    mkdir -p "$(dirname "$CONFIG_DST")"
    cp "$CONFIG_SRC" "$CONFIG_DST"
fi

# 运行时目录
mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$APP_DIR/plugins" "$APP_DIR/permissions"

# 切换到工作目录
cd "$APP_DIR"

# ------------------------------------------------------------------ #
# 启动 Gunicorn
# ------------------------------------------------------------------ #
# --worker-class uvicorn_worker.UvicornWorker  = ASGI worker
# --preload                                   = 启动时加载 app（共享资源）
# --graceful-timeout                          = 优雅关闭等待时间
# --keep-alive                                = HTTP keep-alive

exec gunicorn web.backend.main:app \
    --bind "0.0.0.0:${PORT}" \
    --workers "$WORKERS" \
    --worker-class uvicorn.workers.UvicornWorker \
    --preload \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
