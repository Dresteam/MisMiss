# MisMiss 构建与部署指南

## 选型速查

| 场景 | 推荐方案 | 目标机器需要 |
|------|---------|:----------:|
| 本地开发 | 一、开发模式 | Python + Node.js |
| 个人服务器（单机） | 二、单端口生产模式 | Python |
| 分发给用户 | 三、源码归档分发包 | Python |
| **服务器生产环境（推荐）** | **四、Docker 部署包** | Docker |
| Linux 服务器（无 Docker） | 五、Linux 原生部署 | Python |
| Windows Server | 六、Windows 原生部署 | Python |
| 零依赖分发 | 七、PyInstaller exe | **无** |
| Python 开发者 | 八、pip wheel | Python |

---

## 前置要求

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.13+ | 后端运行时 |
| Node.js | 22+ | 前端构建（开发 / 构建时需要） |
| npm | 10+ | 前端包管理 |

---

## 一、开发模式（热更新）

前后端分离，修改代码自动刷新。

```bash
# 安装依赖（首次）
pip install -r requirements.txt
pip install -r web\backend\requirements.txt
cd web\frontend && npm install && cd ..\..

# 启动
start.bat
```

| 服务 | 地址 |
|------|------|
| 前端（Vite HMR） | `http://localhost:5173` |
| API（uvicorn --reload） | `http://localhost:8080/docs` |

前端 `/api/*` 请求由 Vite proxy 转发到后端。

---

## 二、单端口生产模式

前端编译为静态文件，后端同时提供 API 和前端 SPA。

```bash
# 一键构建 + 启动
start.bat build

# 或分步
cd web\frontend && npm run build && cd ..\..
start.bat prod
```

访问 `http://localhost:8080`（前端 + API 同端口）。

代码分割（vite.config.ts 已配置）：

| Chunk | 体积(gzip) | 加载场景 |
|-------|:-------:|------|
| `vendor-react` | 53 kB | 全部页面 |
| `vendor-charts` | 99 kB | 仪表盘 |
| `vendor-syntax` | 221 kB | 日志/配置页 |
| `vendor-markdown` | 131 kB | README 文档 |
| `vendor-ui` | 24 kB | 图标等通用组件 |

---

## 三、源码归档分发包（`.tar.gz` / `.zip`）

预编译前端的完整归档，部署方只需 Python。

### 3.1 构建

```bash
# Windows
powershell -File scripts\build.ps1 -Mode Archive

# Linux / macOS
bash scripts/build.sh archive
```

产物：`dist/mismiss-1.0.0.tar.gz` + `dist/mismiss-1.0.0.zip`

### 3.2 归档内容

```
mismiss-1.0.0/
├── config.yml / requirements.txt
├── start.sh / start.bat
├── src/                       # 源码
├── web/backend/               # FastAPI
├── web/frontend/dist/         # 前端（已编译，无需 Node.js）
├── data/ logs/ plugins/ permissions/   # 运行时目录
└── README.md
```

### 3.3 部署方使用

```bash
# 1. 解压
tar -xzf mismiss-1.0.0.tar.gz && cd mismiss-1.0.0

# 2. 安装依赖（只需 Python）
pip install -r requirements.txt
pip install fastapi "uvicorn[standard]" pydantic python-multipart

# 3. 启动
./start.sh --prod          # Linux
start.bat prod             # Windows
```

---

## 四、Docker 部署（部署包，推荐）

镜像**不推送到任何镜像仓库**，通过"部署包"分发：本地构建镜像并与部署栈一起打包成单个归档，上传服务器解压后一条命令完成部署 / 更新。

```
Browser (:18080)
  → Nginx (反向代理 + 静态缓存 + 限流)
    → Gunicorn (4× UvicornWorker)
      → FastAPI → React SPA
```

### 4.1 本地构建部署包

```bash
# Windows
powershell -File scripts\docker-release.ps1 -Version 1.2.0

# Linux / macOS
bash scripts/docker-release.sh 1.2.0
```

产物：`dist/mismiss-1.2.0-docker.zip`（Windows）或 `dist/mismiss-1.2.0-docker.tar.gz`（Linux / macOS）。

版本号未指定时自动解析（与 release.sh 一致）：`pyproject.toml` → git tag → 日期。例如当前项目会得到 `mismiss-1.0.0-beta.2-docker.zip`，与 `release/` 目录产物命名保持同一格式。

部署包内容：

```
mismiss-1.2.0-docker/
├── mismiss-docker.tar.gz   # 应用镜像（docker save 导出）
├── docker-compose.yml      # 部署栈（应用 + Nginx）
├── nginx.conf              # Nginx 反向代理配置
├── config.yml.dist         # 配置模板（首次部署引导）
└── deploy.sh               # 服务器一键部署脚本
```

### 4.2 服务器部署

```bash
# 1. 上传部署包
scp dist/mismiss-1.2.0-docker.zip user@server:/opt/mismiss/

# 2. 解压 + 一键部署（导入镜像 → 引导配置 → 启动）
cd /opt/mismiss && unzip mismiss-1.2.0-docker.zip && cd mismiss-1.2.0-docker
bash deploy.sh
```

访问 `http://localhost:18080`（默认端口，避开 80 留给服务器统一反代）。

首次部署自动从 `config.yml.dist` 生成 `config.yml`（默认账号 `MisMiss` / `MisMiss`）——**编辑后执行 `./deploy.sh` 重启生效**。

> **排错**：若第一步导入镜像报 `unrecognized image format`，说明部署包由旧版打包脚本生成（嵌套 tar）或构建机启用了 Docker Desktop 的 containerd 镜像存储且未走 buildx。用最新 `docker-release` 脚本重新打包即可（自动优先 buildx 导出经典格式）。

> **在线更新**：首次部署后，日常更新可直接在 Web 控制台「更新 MisMiss」页一键完成（见 4.7 在线更新）。

### 4.3 更新

本地重新打包 → 上传解压覆盖部署目录 → 再次执行 `./deploy.sh`（幂等，自动重建容器）。

```bash
# 本地
powershell -File scripts\docker-release.ps1 -Version 1.3.0
scp dist/mismiss-1.3.0-docker.zip user@server:/opt/mismiss/

# 服务器
cd /opt/mismiss && unzip -o mismiss-1.3.0-docker.zip
cd mismiss-1.3.0-docker && bash deploy.sh
```

`config.yml`、`data/`、`plugins/` 等运行时文件不会被覆盖（部署包内不含）。

### 4.4 运维

```bash
docker compose logs -f            # 全部日志
docker compose logs -f mismiss    # 仅应用日志
docker compose ps                 # 状态
docker compose down               # 停止

# 调整 worker 数
MISMISS_WORKERS=8 docker compose up -d --force-recreate

# 自定义端口（默认 18080）
MISMISS_HTTP_PORT=9090 docker compose up -d --force-recreate
# 或写入 .env: echo "MISMISS_HTTP_PORT=9090" > .env

# 备份
tar -czf backup.tar.gz data/ plugins/ config.yml
```

### 4.5 服务器统一反向代理接入（Caddy 示例）

```
# Caddyfile
mismiss.example.com {
    reverse_proxy localhost:18080
}
```

### 4.6 本地快速测试

本地构建镜像后用同一份 compose 直接跑（无需打包）：

```bash
docker build -t mismiss:latest .
docker compose up -d
```

访问 `http://localhost:18080`。

### 4.7 在线更新（Web 控制台，推荐日常使用）

首次部署后，日常更新在 Web 控制台「更新 MisMiss」页手动点击完成，无需 SSH：

```
点击「更新到 vX」
  → 下载 mismiss-<版本>-docker.zip 部署包（复用镜像站/代理设置）
  → 校验格式（含内层镜像归档检查）
  → 备份当前部署包到 .mismiss-backup/
  → 解压到部署目录（config.yml 用户配置与 .env 不被覆盖）
  → docker load 导入新镜像
  → 派发一次性容器在宿主守护进程上执行 compose 重建
  → 页面短暂断开（约 10~30 秒），刷新后即新版本
```

更新页同时提供一键回滚（恢复备份的部署包并重建）。

原理：mismiss 容器挂载了宿主 `/var/run/docker.sock` 与部署目录（`/app/deploy`），镜像内置 docker CLI + compose 插件。重建由一次性容器执行——若在应用容器内直接跑 compose，重建会杀掉执行中的进程。

> **安全提示**：挂载 docker.sock 等同于授予容器宿主 Docker 完全控制权（等效 root，Portainer / Watchtower 同款模式）。如不需要在线更新，删除 `docker-compose.yml` 中 mismiss 服务的 docker.sock 与部署目录两处挂载即可（更新回落到部署包流程；更新页会自动提示未挂载）。在线更新要求容器内可写部署目录，root 部署时 `deploy.sh` 已自动 chown 到 uid 1000。

### 4.8 关键文件与资源限制

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 多阶段构建、docker CLI + compose 插件、tini init、非 root 用户（uid=1000）、健康检查 |
| `docker-compose.yml` | 应用 + Nginx 双服务、绑定挂载、docker.sock 挂载、资源限制（本地 / 服务器通用） |
| `nginx.conf` | 反向代理、gzip、安全头、限流 120r/m、WebSocket |
| `scripts/docker-release.sh` / `.ps1` | 本地构建镜像 + 打包部署包 |
| `scripts/docker-server-deploy.sh` | 服务器一键部署（打包时重命名为 `deploy.sh`，含 .env 注入与在线更新支持） |
| `scripts/docker-entrypoint.sh` | 容器入口：匹配 docker.sock 属组后降权启动 |

资源限制（默认）：App 128 MB ~ 512 MB，Nginx ≤ 64 MB。

---

## 五、Linux 原生部署（systemd + venv）

无 Docker 时的原生部署，注册 systemd 服务。

### 5.1 一键部署

```bash
# 上传到服务器后
bash scripts/deploy.sh --native
```

脚本自动：创建 venv → 安装依赖 → 构建前端 → 安装 systemd 服务 → 启动。

### 5.2 手动部署

```bash
# 1. 虚拟环境
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r web/backend/requirements.txt

# 2. 前端构建
cd web/frontend && npm ci && npm run build && cd ../..
mkdir -p data logs plugins permissions

# 3. 安装服务
sudo tee /etc/systemd/system/mismiss.service << 'EOF'
[Unit]
Description=MisMiss
After=network.target

[Service]
Type=simple
User=mismiss
WorkingDirectory=/opt/mismiss
Environment=PATH=/opt/mismiss/.venv/bin:/usr/bin:/bin
Environment=MISMISS_PROD=1
ExecStart=/opt/mismiss/.venv/bin/gunicorn web.backend.main:app \
    --bind 0.0.0.0:8080 --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now mismiss
```

### 5.3 管理

```bash
systemctl status mismiss
journalctl -u mismiss -f
```

---

## 六、Windows 原生部署（venv + NSSM 服务）

### 6.1 手动启动

```powershell
cd web\frontend && npm ci && npm run build && cd ..\..

python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -r web\backend\requirements.txt

set MISMISS_PROD=1
.venv\Scripts\python.exe -m web.backend.main --port 8080
```

### 6.2 注册为 Windows 服务

[NSSM](https://nssm.cc/) 可将任何程序注册为 Windows 服务：

```powershell
nssm install MisMiss
# 弹出窗口填写：
#   Application:  C:\opt\mismiss\.venv\Scripts\python.exe
#   Arguments:    -m web.backend.main --port 8080
#   Startup dir:  C:\opt\mismiss
#   Environment:  MISMISS_PROD=1

nssm start MisMiss         # 启动
nssm status MisMiss        # 状态
```

---

## 七、PyInstaller 独立可执行文件

目标机器**无需 Python / Node.js**，双击运行，数据存于 exe 同级目录。

### 7.1 构建

```bash
# Windows
powershell -File scripts\build.ps1 -Mode Exe

# Linux
bash scripts/build.sh exe
```

产物：`dist/mismiss.exe` 或 `dist/mismiss`

### 7.2 部署

将 exe 复制到目标目录，双击即可。首次启动自动创建：

```
MyBot/
├── mismiss.exe
├── config.yml            # 自动从模板复制
├── data/   logs/   plugins/   permissions/
```

### 7.3 注意事项

- 端口默认读取 `config.yml` 中的 `server.api_port`，`--port` 可覆盖
- 插件依赖安装需目标机器有 Python + pip
- 默认密码 `MisMiss` / `MisMiss`，请登录后修改

---

## 八、pip wheel

```bash
bash scripts/build.sh wheel
pip install dist/mismiss-1.0.0-py3-none-any.whl[web]
```

---

## 九、脚本速查

### 构建

```bash
# Windows
powershell -File scripts\build.ps1               # 交互式
powershell -File scripts\build.ps1 -Mode Archive  # zip + tar.gz
powershell -File scripts\build.ps1 -Mode Exe      # PyInstaller
powershell -File scripts\build.ps1 -Mode Wheel    # pip wheel
powershell -File scripts\build.ps1 -Mode Clean    # 清理

# Linux / macOS
bash scripts/build.sh archive   # zip + tar.gz
bash scripts/build.sh exe       # PyInstaller
bash scripts/build.sh wheel     # pip wheel
bash scripts/build.sh all       # archive + wheel
bash scripts/build.sh clean     # 清理
```

### 启动

```bash
bash scripts/start.sh            # 开发模式
bash scripts/start.sh --prod    # 生产模式
bash scripts/start.sh --backend # 仅 API

scripts\start.bat                # 开发模式
scripts\start.bat prod          # 生产模式
scripts\start.bat backend       # 仅 API
```

### 部署

```bash
# Docker 部署包（镜像不推仓库，推荐，见第四章）
bash scripts/docker-release.sh 1.2.0             # 构建镜像 + 打包 → dist/
powershell -File scripts\docker-release.ps1 -Version 1.2.0

# 服务器端（在部署包解压目录内）
bash deploy.sh                                   # 导入镜像 + 启动 / 更新

# 原生部署
bash scripts/deploy.sh --native                  # Linux systemd 部署
powershell -File scripts\deploy.ps1 -Mode Native
```

---

## 十、目录结构

```
MisMiss/
├── config.yml                  # 服务器配置
├── pyproject.toml              # Python 包元数据
├── mismiss.spec                # PyInstaller 打包配置
│
├── Dockerfile                  # 多阶段 Docker 构建
├── docker-compose.yml          # Docker 部署栈（应用 + Nginx，本地 / 服务器通用）
├── nginx.conf                  # Nginx 生产配置
│
├── src/                        # Python 核心框架
│   ├── interfaces/             # MIST 抽象接口
│   └── core/                   # Missevan 实现
│
├── web/
│   ├── backend/                # FastAPI Web 控制台
│   └── frontend/               # React + Vite + Tailwind
│
├── scripts/                    # 构建 / 部署 / 启动脚本
│   ├── build.sh / build.ps1
│   ├── docker-release.sh / .ps1       # Docker 镜像构建 + 部署包打包
│   ├── docker-server-deploy.sh        # 服务器一键部署（随部署包分发）
│   ├── deploy.sh / deploy.ps1
│   ├── start.sh / start.bat
│   ├── pyinstaller_entry.py
│   └── docker-entrypoint.sh
│
├── start.bat                   # 快捷入口 → scripts/start.bat
├── mismiss_cli.py              # pip install 入口
│
├── plugins/   data/   logs/   permissions/   # 运行时
├── build/     dist/     release/              # 构建产物（gitignore）
└── docs/build/BUILDING.md                     # 本文档
```

---

## 十一、发布 Release（全量打包）

一条命令构建所有分发格式，用于发布 GitHub Release。

### 命名规范

遵循 **SemVer 2.0**（语义化版本），格式：

```
mismiss-<semver>[-<platform>][-<hash>].<ext>
```

| 占位符 | 规则 | 示例 |
|--------|------|------|
| `semver` | `MAJOR.MINOR.PATCH[-prerelease][+build]` | `1.0.0-beta.2` |
| `platform` | 仅 PyInstaller：`win` / `linux` / `macos` | `win` |
| `hash` | git short hash，仅非 tag 开发版 | `abc1234` |
| `ext` | `.zip` `.tar.gz` `.whl` `.exe` | |

版本号来源优先级：`-v` 参数 → `pyproject.toml` → git tag → 日期（`2026.7.26`）

```bash
# Windows
powershell -File scripts/release.ps1 -Version 1.0.0-beta.2

# Linux / macOS
bash scripts/release.sh -v 1.0.0-rc.1
```

### 产物示例

```
release/
├── mismiss-1.0.0-beta.2.tar.gz              # 源码归档
├── mismiss-1.0.0-beta.2.zip                 # 源码归档
├── mismiss-1.0.0-beta.2-py3-none-any.whl    # pip wheel
├── mismiss-1.0.0-beta.2-win.exe             # PyInstaller Windows
├── mismiss-1.0.0-beta.2-linux               # PyInstaller Linux
├── mismiss-1.0.0-beta.2-docker.tar.gz       # Docker 部署包（镜像 + 部署栈，Windows 打包为 .zip）
└── checksums-1.0.0-beta.2.txt               # SHA256 校验
```

### 参数

```bash
# 指定版本号
bash scripts/release.sh -v 1.2.0

# 跳过 PyInstaller（更快，适合 Linux 发版）
bash scripts/release.sh --skip-pyinstaller
```

### GitHub Release 发布流程

1. 运行 `bash scripts/release.sh -v 1.0.0`
2. GitHub → Releases → Draft a new release
3. Tag: `v1.0.0`，标题: `v1.0.0`
4. 将 `release/` 下所有文件拖入附件
5. 粘贴脚本输出的 Markdown 表格到 Release 说明
6. Publish release

Docker 部署包已随 Release 产出，服务器解压后执行 `bash deploy.sh` 即可部署（见第四章）。
