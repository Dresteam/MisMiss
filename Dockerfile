# ============================================================
# MisMiss — 企业级多阶段 Docker 构建
# ============================================================
# 启用 BuildKit 以获得缓存加速:
#   set DOCKER_BUILDKIT=1                           (Windows)
#   export DOCKER_BUILDKIT=1                         (Linux)
#   docker compose up -d --build
#
# 仅源代码变化时跳过依赖重装（层缓存自动生效）。
# ============================================================

# syntax=docker/dockerfile:1

# ------------------------------------------------------------------ #
# Stage 1 — 前端构建
# ------------------------------------------------------------------ #
FROM node:22-alpine AS frontend-builder

WORKDIR /src/web/frontend

# npm 缓存挂载 —— 重复构建时跳过下载
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY web/frontend/ ./
RUN npm run build

# ------------------------------------------------------------------ #
# Stage 2 — 生产运行环境
# ------------------------------------------------------------------ #
FROM python:3.13-slim

LABEL org.opencontainers.image.title="MisMiss"
LABEL org.opencontainers.image.description="MIST 标准实现 · 猫耳FM 直播场控机器人框架"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# 非 root 用户
RUN groupadd -r mismiss && useradd -r -g mismiss -d /app mismiss

WORKDIR /app

# ------------------------------------------------------------------ #
# Python 依赖 —— pip 缓存挂载
# ------------------------------------------------------------------ #
COPY requirements.txt ./
COPY web/backend/requirements.txt web/backend/

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install -r web/backend/requirements.txt

# ------------------------------------------------------------------ #
# 源码 + 配置
# ------------------------------------------------------------------ #
COPY src/        ./src/
COPY web/backend/ ./web/backend/
COPY mismiss_cli.py pyproject.toml ./
COPY config.yml ./config.yml.dist

# 前端产物（Stage 1）
COPY --from=frontend-builder /src/web/frontend/dist/ ./web/frontend/dist/

# Entrypoint
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 运行时目录
RUN mkdir -p /app/data /app/logs /app/plugins /app/permissions /app/config \
    && chown -R mismiss:mismiss /app

USER mismiss

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

ENV PYTHONUNBUFFERED=1
ENV MISMISS_PROD=1
ENV API_PORT=8080
ENV WORKERS=4

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/docker-entrypoint.sh"]
