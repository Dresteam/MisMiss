# ============================================================
# MisMiss — 企业级多阶段 Docker 构建
# ============================================================
# 镜像不推送到仓库，通过部署包分发:
#   本地打包:  bash scripts/docker-release.sh
#   本地测试:  docker build -t mismiss:latest . && docker compose up -d
#
# 启用 BuildKit 以获得缓存加速:
#   set DOCKER_BUILDKIT=1                           (Windows)
#   export DOCKER_BUILDKIT=1                         (Linux)
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

# 版本号注入镜像（更新页展示当前版本），打包脚本通过 --build-arg 传入
ARG MISMISS_VERSION=1.0.0

# Docker CLI / compose 插件版本（在线更新能力，可用 --build-arg 覆盖）
ARG DOCKER_CLI_VERSION=27.5.1
ARG COMPOSE_VERSION=v2.32.4

LABEL org.opencontainers.image.title="MisMiss"
LABEL org.opencontainers.image.description="MIST 标准实现 · 猫耳FM 直播场控机器人框架"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

# 不用 cache 挂载：共享 apt 缓存在慢网/中断场景易损坏
# （曾出现 "cannot stat pathname /tmp/apt-dpkg-install-*.deb"）；
# 该层内容稳定，镜像层缓存已足够
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini curl gosu \
    && rm -rf /var/lib/apt/lists/*

# 非 root 用户 —— 固定 uid=1000，与部署目录绑定挂载的宿主文件属主兼容
# （Linux 服务器首个普通用户 uid 即 1000；root 部署时 deploy.sh 会 chown 到 1000）
RUN groupadd -r mismiss && useradd -r -u 1000 -g mismiss -d /app mismiss

# ------------------------------------------------------------------ #
# Docker CLI + compose 插件（在线更新：通过 /var/run/docker.sock 操作宿主 Docker）
# ------------------------------------------------------------------ #
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
        amd64) DOCKER_ARCH=x86_64 ;; \
        arm64) DOCKER_ARCH=aarch64 ;; \
        *) echo "unsupported arch"; exit 1 ;; \
    esac; \
    curl -fSL --retry 3 "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_CLI_VERSION}.tgz" \
        | tar xz -C /usr/local/bin --strip-components=1; \
    mkdir -p /usr/local/lib/docker/cli-plugins; \
    curl -fSL --retry 3 "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${DOCKER_ARCH}" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose; \
    test -s /usr/local/lib/docker/cli-plugins/docker-compose; \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

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

# Entrypoint（仅启动 Gunicorn；目录/配置由 compose 挂载与部署脚本负责）
# —— 强制 LF，防止 Windows 检出 CRLF 导致 bash\r 错误
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# 运行时目录
RUN mkdir -p /app/data /app/logs /app/plugins /app/permissions /app/config \
    && chown -R mismiss:mismiss /app

# 注意：不设置 USER —— entrypoint 以 root 启动，将 mismiss 加入 docker.sock
# 属组后通过 gosu 降权运行应用（未挂载 socket 时直接降权，行为不变）。
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

ENV PYTHONUNBUFFERED=1
ENV MISMISS_PROD=1
ENV API_PORT=8080
ENV WORKERS=1
ENV MISMISS_VERSION=${MISMISS_VERSION}

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/docker-entrypoint.sh"]
