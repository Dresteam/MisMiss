# ============================================================
# MisMiss — 企业级多阶段 Docker 构建
# ============================================================
# Stage 1: 前端构建 (Node)
# Stage 2: 生产镜像 (Python + Gunicorn + 前端产物)
# ============================================================

# ------------------------------------------------------------------ #
# Stage 1 — 前端构建
# ------------------------------------------------------------------ #
FROM node:22-alpine AS frontend-builder

WORKDIR /src/web/frontend

COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY web/frontend/ ./
RUN npm run build

# ------------------------------------------------------------------ #
# Stage 2 — 生产运行环境
# ------------------------------------------------------------------ #
FROM python:3.13-slim

LABEL org.opencontainers.image.title="MisMiss"
LABEL org.opencontainers.image.description="MIST 标准实现 · 猫耳FM 直播场控机器人框架"
LABEL org.opencontainers.image.licenses="AGPL-3.0"
LABEL org.opencontainers.image.source="https://github.com/dikxingmengya/MisMiss"

# 系统依赖 + 安全补丁
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

# — 非 root 用户 —
RUN groupadd -r mismiss && useradd -r -g mismiss -d /app mismiss

WORKDIR /app

# ------------------------------------------------------------------ #
# Python 依赖（利用 Docker 层缓存）
# ------------------------------------------------------------------ #
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY web/backend/requirements.txt web/backend/
RUN pip install --no-cache-dir -r web/backend/requirements.txt

# ------------------------------------------------------------------ #
# 源码 + 配置
# ------------------------------------------------------------------ #
COPY src/        ./src/
COPY web/backend/ ./web/backend/
COPY mismiss_cli.py pyproject.toml ./

# config.yml 作为模板，运行时由 entrypoint 复制到持久卷
COPY config.yml ./config.yml.dist

# ------------------------------------------------------------------ #
# 前端产物（Stage 1）
# ------------------------------------------------------------------ #
COPY --from=frontend-builder /src/web/frontend/dist/ ./web/frontend/dist/

# ------------------------------------------------------------------ #
# Entrypoint
# ------------------------------------------------------------------ #
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 运行时目录（可被 volume 覆盖）
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

# tini 作为 init 进程，正确处理信号和僵尸进程
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/docker-entrypoint.sh"]
