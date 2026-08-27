#!/usr/bin/env bash
# ============================================================
# Docker 容器入口
# ============================================================
# 1. 挂载了宿主 Docker socket 时，把 mismiss 加入 socket 属组
#    （在线更新需要容器内 docker CLI 访问宿主守护进程）
# 2. 降权到 mismiss（uid=1000）启动 Gunicorn + Uvicorn workers
# ============================================================

set -euo pipefail

# ------------------------------------------------------------------ #
# Docker socket 属组（宿主 gid 不定，动态匹配）
# ------------------------------------------------------------------ #
if [ -S /var/run/docker.sock ]; then
    SOCK_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || true)
    if [ -n "$SOCK_GID" ] && [ "$SOCK_GID" != "0" ]; then
        if ! getent group "$SOCK_GID" >/dev/null 2>&1; then
            groupadd -g "$SOCK_GID" dockerhost 2>/dev/null || true
        fi
        usermod -aG "$SOCK_GID" mismiss 2>/dev/null || true
    fi
fi

PORT="${API_PORT:-8080}"
WORKERS="${WORKERS:-1}"

# ------------------------------------------------------------------ #
# 降权启动 Gunicorn
# ------------------------------------------------------------------ #
# --worker-class uvicorn_worker.UvicornWorker  = ASGI worker
# --preload                                   = 启动时加载 app（共享资源）
# --graceful-timeout                          = 优雅关闭等待时间
# --keep-alive                                = HTTP keep-alive

exec gosu mismiss gunicorn web.backend.main:app \
    --bind "0.0.0.0:${PORT}" \
    --workers "$WORKERS" \
    --worker-class uvicorn.workers.UvicornWorker \
    --preload \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
