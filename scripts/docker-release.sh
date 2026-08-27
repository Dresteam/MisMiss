#!/usr/bin/env bash
# ============================================================
# MisMiss — Docker 镜像构建 & 部署包打包（不推镜像仓库）
# ============================================================
# 用法:
#   bash scripts/docker-release.sh            # 版本号自动解析（见下）
#   bash scripts/docker-release.sh 1.2.0      # 指定版本号（等价 -v 1.2.0）
#
# 版本号解析（与 release.sh 一致）: 参数 → pyproject.toml → git tag → 日期
#
# 产物: dist/mismiss-<版本>-docker.tar.gz（命名与 release/ 产物一致）
#   内含:
#     mismiss-docker.tar.gz   # 应用镜像（docker save 导出）
#     docker-compose.yml      # 部署栈（应用 + Nginx）
#     nginx.conf              # Nginx 反向代理配置
#     config.yml.dist         # 配置模板（服务器首次部署引导）
#     deploy.sh               # 服务器一键部署脚本
#   归档为扁平结构（无顶层目录），可直接解压到部署目录。
#
# 服务器使用方式:
#   tar -xzf mismiss-<版本>-docker.tar.gz -C /opt/mismiss
#   cd /opt/mismiss && bash deploy.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

VERSION="${1:-}"
case "$VERSION" in
    -v|--version) VERSION="${2:-}" ;;
    -*) echo "[ERROR] 未知参数: $VERSION（用法: bash scripts/docker-release.sh [版本号]）"; exit 1 ;;
esac

# ------------------------------------------------------------------ #
# 版本号解析（与 release.sh 一致）: 参数 → pyproject.toml → git tag → 日期
# ------------------------------------------------------------------ #
detect_version() {
    # 1. CLI 参数
    if [ -n "$VERSION" ]; then echo "$VERSION"; return; fi

    # 2. pyproject.toml
    if [ -f pyproject.toml ]; then
        local v
        v=$(grep '^version' pyproject.toml | head -1 | sed -E 's/version\s*=\s*"([^"]+)".*/\1/' | tr -d ' ')
        if [ -n "$v" ]; then echo "$v"; return; fi
    fi

    # 3. Git tag
    if command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null 2>&1; then
        local tag; tag=$(git describe --tags --abbrev=0 2>/dev/null || true)
        if [ -n "$tag" ]; then echo "${tag#v}"; return; fi
    fi

    # 4. 日期兜底
    date +%Y.%-m.%-d
}
VERSION=$(detect_version)
SEMVER="${VERSION#v}"
SEMVER="${SEMVER// /}"

PKG_NAME="mismiss-${SEMVER}-docker"
BUILD_DIR="$PROJECT_ROOT/build/docker/${PKG_NAME}"
DIST_DIR="$PROJECT_ROOT/dist"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

require_cmd() { command -v "$1" &>/dev/null || die "缺少命令: $1，请先安装"; }
file_size()  { du -sh "$1" 2>/dev/null | cut -f1; }

step "检查依赖 ..."
require_cmd docker
require_cmd gzip
require_cmd tar

# ------------------------------------------------------------------ #
# 1. 构建镜像 + 导出经典 docker 格式归档
# ------------------------------------------------------------------ #
step "构建镜像并导出归档 → mismiss:latest ..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

IMAGE_TAR_PATH="$BUILD_DIR/mismiss-docker.tar"

# 优先 buildx 导出：产出经典 docker 格式归档，
# 不受 Docker Desktop / containerd 镜像存储影响，任何版本服务器 docker load 均可导入
# --build-arg MISMISS_VERSION 注入版本号（更新页展示当前版本）
if docker buildx version &>/dev/null 2>&1 \
    && docker buildx build -t mismiss:latest --build-arg MISMISS_VERSION="$SEMVER" \
        --output type=docker,dest="$IMAGE_TAR_PATH" "$PROJECT_ROOT"; then
    info "已导出经典 docker 格式归档"
else
    warn "buildx 不可用，回退 docker build + docker save（若启用 containerd 镜像存储，老版本服务器 docker load 可能报 unrecognized image format）"
    docker build -t mismiss:latest --build-arg MISMISS_VERSION="$SEMVER" "$PROJECT_ROOT"
    docker save mismiss:latest -o "$IMAGE_TAR_PATH"
fi

# 本地也保留镜像，便于 docker compose 快速测试
docker load -qi "$IMAGE_TAR_PATH" 2>/dev/null || true

# gzip 直接压缩 docker 归档（gz 内部即 docker save 格式）
gzip -f "$IMAGE_TAR_PATH"

# ------------------------------------------------------------------ #
# 2. 收集部署文件
# ------------------------------------------------------------------ #
step "收集部署文件 → $BUILD_DIR/"

cp "$PROJECT_ROOT/docker-compose.yml"            "$BUILD_DIR/"
cp "$PROJECT_ROOT/nginx.conf"                    "$BUILD_DIR/"
cp "$PROJECT_ROOT/config.yml"                    "$BUILD_DIR/config.yml.dist"
cp "$PROJECT_ROOT/scripts/docker-server-deploy.sh" "$BUILD_DIR/deploy.sh"
chmod +x "$BUILD_DIR/deploy.sh"

warn "config.yml.dist 来自开发机配置，请检查不含敏感信息（默认账号 MisMiss / MisMiss，上线前务必修改）"

# ------------------------------------------------------------------ #
# 3. 打包部署包
# ------------------------------------------------------------------ #
step "打包部署包 → $DIST_DIR/${PKG_NAME}.tar.gz"
# 扁平打包（无顶层目录）：归档成员即部署文件本身，可直接解压到部署目录。
# 顶层目录会导致服务器在线更新校验按成员名精确匹配时找不到 mismiss-docker.tar.gz
( cd "$BUILD_DIR" && tar -czf "$DIST_DIR/${PKG_NAME}.tar.gz" * )

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║        DOCKER PACKAGE READY          ║"
echo "  ╠══════════════════════════════════════╣"
printf "  ║  %-34s  ║\n" "${PKG_NAME}.tar.gz  $(file_size "$DIST_DIR/${PKG_NAME}.tar.gz")"
echo "  ╚══════════════════════════════════════╝"
echo ""
info "服务器部署:"
echo ""
echo "  # 1. 上传部署包"
echo "  scp dist/${PKG_NAME}.tar.gz user@server:/opt/mismiss/"
echo ""
echo "  # 2. 服务器上解压 + 一键部署"
echo "  tar -xzf ${PKG_NAME}.tar.gz -C /opt/mismiss"
echo "  cd /opt/mismiss && bash deploy.sh"
echo ""
info "更新: 用新部署包覆盖部署目录，再次执行 bash deploy.sh"
