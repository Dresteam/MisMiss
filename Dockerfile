# ============================================================
# MisMiss — 多阶段 Docker 构建
# ============================================================
# 构建:  docker build -t mismiss .
# 运行:  docker run -d -p 8080:8080 --name mismiss mismiss
# ============================================================

# ------------------------------------------------------------------ #
# Stage 1 — 前端构建
# ------------------------------------------------------------------ #
FROM node:22-alpine AS frontend-builder

WORKDIR /app/web/frontend

COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm install --legacy-peer-deps

COPY web/frontend/ ./
RUN npm run build

# ------------------------------------------------------------------ #
# Stage 2 — 后端运行环境
# ------------------------------------------------------------------ #
FROM python:3.13-slim

LABEL org.opencontainers.image.title="MisMiss"
LABEL org.opencontainers.image.description="MIST 标准实现 - 猫耳FM 直播场控机器人框架"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY web/backend/requirements.txt web/backend/
RUN pip install --no-cache-dir -r web/backend/requirements.txt

# 源码
COPY src/ ./src/
COPY web/backend/ ./web/backend/
COPY config.yml ./

# 前端构建产物
COPY --from=frontend-builder /app/web/frontend/dist/ ./web/frontend/dist/

# 运行时目录
RUN mkdir -p /app/data /app/logs /app/plugins /app/permissions

EXPOSE 18080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:18080/api/health')" || exit 1

ENV PYTHONUNBUFFERED=1
ENV MISMISS_PROD=1

CMD ["python", "-m", "web.backend.main", "--port", "18080"]
