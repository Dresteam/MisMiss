# MisMiss 构建与部署指南

## 选型速查

| 场景 | 推荐方案 | 目标机器需要 |
|------|---------|:----------:|
| 本地开发 | 一、开发模式 | Python + Node.js |
| 个人服务器（单机） | 二、单端口生产模式 | Python |
| 分发给用户 | 三、源码归档分发包 | Python |
| 快速测试 | 四、Docker（简单） | Docker |
| **企业生产环境** | **五、Docker + Nginx** | Docker |
| Linux 服务器（无 Docker） | 七、Linux 原生部署 | Python |
| Windows Server | 八、Windows 原生部署 | Python |
| 零依赖分发 | 九、PyInstaller exe | **无** |
| Python 开发者 | 十、pip wheel | Python |

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

## 四、Docker 部署（开发 / 测试）

```bash
docker compose up -d --build

# 常用命令
docker compose logs -f      # 日志
docker compose down         # 停止
docker compose restart      # 重启
```

访问 `http://localhost:8080`。

---

## 五、企业级生产部署（Docker + Nginx，推荐）

```
Browser (:18080)
  → Nginx (反向代理 + 静态缓存 + 限流)
    → Gunicorn (4× UvicornWorker)
      → FastAPI → React SPA
```

### 5.1 关键文件

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 多阶段构建、tini init、非 root 用户、健康检查 |
| `nginx.conf` | 反向代理、gzip、安全头、限流 120r/m、WebSocket |
| `docker-compose.prod.yml` | App + Nginx 双服务、命名卷、资源限制 |

### 5.2 启动

生产 compose 只**拉取镜像**（由 CI/CD 发布），不在服务器上构建。

```bash
# 首次：放入配置文件
mkdir config && cp config.yml config/

# 启动（默认宿主机端口 18080，避开 80）
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

访问 `http://localhost:18080`。

**镜像尚未发布到 ghcr.io 时**，用本地构建 + 导出：

```bash
# 本地（开发机）
docker compose build                        # 用 docker-compose.yml 构建
docker save mismiss:latest | gzip > mismiss.tar.gz
scp mismiss.tar.gz user@server:/opt/mismiss/

# 服务器
docker load -i mismiss.tar.gz
docker tag mismiss:latest ghcr.io/dikxingmengya/mismiss:latest
docker compose -f docker-compose.prod.yml up -d
```

**自定义端口**：

```bash
# 方式一：环境变量
MISMISS_HTTP_PORT=9090 docker compose -f docker-compose.prod.yml up -d

# 方式二：.env 文件
echo "MISMISS_HTTP_PORT=9090" > .env
docker compose -f docker-compose.prod.yml up -d
```

**服务器统一反向代理接入**（Caddy 示例）：

```
# Caddyfile
mismiss.example.com {
    reverse_proxy localhost:18080
}
```

### 5.3 运维

```bash
docker compose -f docker-compose.prod.yml logs -f mismiss
docker compose -f docker-compose.prod.yml logs -f nginx

# 滚动更新
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# 调整 worker 数
MISMISS_WORKERS=8 docker compose -f docker-compose.prod.yml up -d

# 备份
tar -czf backup.tar.gz data/ plugins/ config/
```

### 5.4 资源限制（默认）

- App：128 MB ~ 512 MB
- Nginx：≤ 64 MB

---

## 六、CI/CD（GitHub Actions）

push 代码自动构建 Docker 镜像并推送到 `ghcr.io`。

### 触发规则

| 事件 | 镜像标签 |
|------|---------|
| push `dev` | `dev`、`sha-xxxxx` |
| push `main` | `latest`、`main` |
| tag `v1.0.0` | `1.0.0`、`1.0`、`latest` |

### 首发设置

GitHub → Settings → Actions → Workflow permissions → **Read and write packages**

### 服务器拉取

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## 七、Linux 原生部署（systemd + venv）

无 Docker 时的原生部署，注册 systemd 服务。

### 7.1 一键部署

```bash
# 上传到服务器后
bash scripts/deploy.sh --native
```

脚本自动：创建 venv → 安装依赖 → 构建前端 → 安装 systemd 服务 → 启动。

### 7.2 手动部署

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

### 7.3 管理

```bash
systemctl status mismiss
journalctl -u mismiss -f
```

---

## 八、Windows 原生部署（venv + NSSM 服务）

### 8.1 手动启动

```powershell
cd web\frontend && npm ci && npm run build && cd ..\..

python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -r web\backend\requirements.txt

set MISMISS_PROD=1
.venv\Scripts\python.exe -m web.backend.main --port 8080
```

### 8.2 注册为 Windows 服务

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

## 九、PyInstaller 独立可执行文件

目标机器**无需 Python / Node.js**，双击运行，数据存于 exe 同级目录。

### 9.1 构建

```bash
# Windows
powershell -File scripts\build.ps1 -Mode Exe

# Linux
bash scripts/build.sh exe
```

产物：`dist/mismiss.exe` 或 `dist/mismiss`

### 9.2 部署

将 exe 复制到目标目录，双击即可。首次启动自动创建：

```
MyBot/
├── mismiss.exe
├── config.yml            # 自动从模板复制
├── data/   logs/   plugins/   permissions/
```

### 9.3 注意事项

- 端口默认读取 `config.yml` 中的 `server.api_port`，`--port` 可覆盖
- 插件依赖安装需目标机器有 Python + pip
- 默认密码 `MisMiss` / `MisMiss`，请登录后修改

---

## 十、pip wheel

```bash
bash scripts/build.sh wheel
pip install dist/mismiss-1.0.0-py3-none-any.whl[web]
```

---

## 十一、脚本速查

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
bash scripts/deploy.sh --docker  # Docker 部署
bash scripts/deploy.sh --native  # Linux systemd 部署

powershell -File scripts\deploy.ps1 -Mode Docker
powershell -File scripts\deploy.ps1 -Mode Native
```

---

## 十二、目录结构

```
MisMiss/
├── config.yml                  # 服务器配置
├── pyproject.toml              # Python 包元数据
├── mismiss.spec                # PyInstaller 打包配置
│
├── Dockerfile                  # 多阶段 Docker 构建
├── docker-compose.yml          # Docker 简单部署
├── docker-compose.prod.yml     # Docker 生产部署（Nginx + App）
├── nginx.conf                  # Nginx 生产配置
│
├── .github/workflows/
│   └── docker-build.yml        # CI/CD 自动构建发布
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

## 十三、发布 Release（全量打包）

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
├── mismiss-1.0.0-beta.2-docker.tar          # Docker 镜像
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

CI/CD 已配置 tag 推送时自动构建 Docker 镜像（见第六章）。
