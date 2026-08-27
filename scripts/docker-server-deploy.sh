#!/usr/bin/env bash
# ============================================================
# MisMiss — 服务器端一键部署脚本（随部署包分发，打包时重命名为 deploy.sh）
# ============================================================
# 用法（在部署包解压目录内执行）:
#   bash deploy.sh         # 首次部署 / 更新，幂等可重复执行
#   （chmod +x deploy.sh 后也可直接 ./deploy.sh）
#
# 流程:
#   1. 导入镜像            docker load
#   2. 首次部署引导配置    从 config.yml.dist 生成 config.yml（已存在则不动）
#   3. 运行时目录 + 属主 + .env 注入（MISMISS_HOME 宿主绝对路径，在线更新用）
#   4. 启动 / 更新         docker compose up -d --force-recreate
#
# 首次部署后，日常更新可走 Web 控制台「更新 MisMiss」页（在线更新）。
# ============================================================

set -euo pipefail

cd "$(dirname "$0")"

IMAGE_TAR="mismiss-docker.tar.gz"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

command -v docker &>/dev/null || die "未找到 docker，请先安装 Docker Engine 与 Compose 插件"

# ------------------------------------------------------------------ #
# 1. 导入镜像
# ------------------------------------------------------------------ #
[ -f "$IMAGE_TAR" ] || die "未找到镜像文件 $IMAGE_TAR，部署包不完整？"

# 预检归档格式：docker load 要求 gz 内直接是 docker save 归档（根含 manifest.json）。
# 嵌套 tar / OCI layout 归档会导致 "unrecognized image format"。
if ! tar -tzf "$IMAGE_TAR" manifest.json >/dev/null 2>&1; then
    die "镜像归档格式异常（缺少 manifest.json），服务器 docker load 将报 'unrecognized image format'。请用最新版 docker-release 脚本重新打包（自动优先 buildx 导出经典格式），再重新上传部署。"
fi

echo "[1/4] 导入镜像 ..."
docker load -i "$IMAGE_TAR"

# ------------------------------------------------------------------ #
# 2. 首次部署引导配置
# ------------------------------------------------------------------ #
echo "[2/4] 引导配置 ..."
if [ ! -f config.yml ]; then
    cp config.yml.dist config.yml
    warn "已生成 config.yml（默认配置），请编辑后执行 ./deploy.sh 重启生效"
fi

# ------------------------------------------------------------------ #
# 3. 运行时目录 + 属主 + .env 注入
# ------------------------------------------------------------------ #
echo "[3/4] 准备运行时目录 ..."
mkdir -p data logs plugins permissions

# 写入 .env：MISMISS_HOME 为部署目录绝对路径（容器内在线更新重建容器时，
# compose 需按宿主路径解析挂载；手动部署时默认为当前目录不受影响）
touch .env
if grep -q '^MISMISS_HOME=' .env; then
    sed -i "s|^MISMISS_HOME=.*|MISMISS_HOME=$(pwd)|" .env
else
    echo "MISMISS_HOME=$(pwd)" >> .env
fi

# 容器内以 uid=1000 运行；root 部署时把部署目录交给该 uid
# （在线更新需要容器内进程可写部署目录：下载/解压部署包）
if [ "$(id -u)" -eq 0 ]; then
    chown -R 1000:1000 .
fi

# ------------------------------------------------------------------ #
# 4. 启动 / 更新
# ------------------------------------------------------------------ #
echo "[4/4] 启动服务 ..."
# 兼容旧部署：早期 compose 无 name 字段，项目名来自目录名（保留/去除点号两种归一化）
OLD1=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_.-]/-/g')
OLD2=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')
for p in "$OLD1" "$OLD2"; do
    [ "$p" = "mismiss" ] && continue
    docker compose -p "$p" down 2>/dev/null || true
done

# --force-recreate：镜像 tag 不变时也确保重建
docker compose up -d --force-recreate

echo ""
info "部署完成 → http://localhost:${MISMISS_HTTP_PORT:-18080}"
echo ""
echo "  查看日志:  docker compose logs -f"
echo "  查看状态:  docker compose ps"
echo "  停止:      docker compose down"
echo "  在线更新:  Web 控制台「更新 MisMiss」页（手动点击，自动重建容器）"
