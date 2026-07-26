# MisMiss 构建与部署指南

## 前置要求

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.13+ | 后端运行时 |
| Node.js | 22+ | 前端构建（仅开发/构建时需要） |
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

前端 `/api/*` 请求由 Vite proxy 转发到后端 `:8080`。

---

## 二、单端口生产模式

前端构建为静态文件，后端同时提供 API 和前端 SPA，单端口部署。

```bash
# 构建前端 + 启动（一条命令）
start.bat build

# 或者分步
cd web\frontend && npm run build && cd ..\..
start.bat prod
```

访问 `http://localhost:8080` — 前端 + API 同端口。

`vite.config.ts` 中已配置代码分割，大依赖按需加载：

| Chunk | 内容 | 加载场景 |
|-------|------|---------|
| `vendor-react` | React + Router | 全部页面 |
| `vendor-charts` | recharts | 仪表盘 |
| `vendor-syntax` | react-syntax-highlighter | 日志/配置页 |
| `vendor-markdown` | KaTeX + remark | README 文档 |
| `vendor-ui` | lucide-react 图标等 | 多页面 |

---

## 三、Docker 部署（开发/测试）

### 快速启动

```bash
docker compose up -d --build
```

### 常用命令

```bash
docker compose logs -f    # 日志
docker compose down       # 停止
docker compose up -d      # 重新启动（不重建）
docker compose restart    # 重启
```

访问 `http://localhost:8080`。

---

## 四、企业级生产部署（推荐）

架构：**Nginx → Gunicorn + Uvicorn workers → FastAPI**

```
Browser (:80)
  → Nginx (反向代理 + 静态缓存 + 限流)
    → Gunicorn (4 worker × UvicornWorker)
      → FastAPI → React SPA
```

### 4.1 配置文件

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 多阶段构建、非 root 用户、tini init、健康检查 |
| `nginx.conf` | 反向代理、gzip、安全头、API 限流（120r/m）、WebSocket |
| `docker-compose.prod.yml` | App + Nginx 双服务、命名卷持久化、资源限制 |

### 4.2 启动

```bash
# 首次：创建 config 目录并放入配置文件
mkdir config
cp config.yml config/

# 启动
docker compose -f docker-compose.prod.yml up -d --build
```

访问 `http://localhost`（80 端口，无需输入端口号）。

### 4.3 运维

```bash
# 滚动更新
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# 查看日志
docker compose -f docker-compose.prod.yml logs -f mismiss
docker compose -f docker-compose.prod.yml logs -f nginx

# 缩放 worker（默认 4）
MISMISS_WORKERS=8 docker compose -f docker-compose.prod.yml up -d

# 备份数据
tar -czf backup.tar.gz data/ plugins/ config/
```

### 4.4 资源限制

`docker-compose.prod.yml` 已配置：
- App: 128MB ~ 512MB 内存
- Nginx: 最大 64MB 内存

根据服务器规格调整 `deploy.resources.limits`。

---

## 五、CI/CD（GitHub Actions）

推送代码自动构建并发布 Docker 镜像到 `ghcr.io`。

### 触发规则

| 事件 | 镜像标签 |
|------|---------|
| push `dev` | `dev`、`sha-xxxxx` |
| push `main` | `latest`、`main`、`sha-xxxxx` |
| tag `v1.0.0` | `1.0.0`、`1.0`、`latest` |
| 手动触发 | 自定义 |

### 首发设置

1. GitHub → Settings → Actions → General → Workflow permissions → **Read and write packages**
2. 推送代码即可触发首次构建

### 服务器拉取

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## 六、PyInstaller 独立可执行文件

目标机器**无需 Python/Node.js**，双击运行。exe 数据自动存储在 exe 同级目录。

### 6.1 构建

```bash
# Windows
powershell -File scripts\build.ps1 -Mode Exe

# Linux / macOS
bash scripts/build.sh exe
```

产物：`dist/mismiss.exe` (Windows) 或 `dist/mismiss` (Linux)。

### 6.2 部署

将 `mismiss.exe` 复制到目标目录，双击运行。首次启动自动创建：

```
MyBot/
├── mismiss.exe
├── config.yml          # 自动从内置模板复制
├── data/               # 运行时状态
│   ├── server_state.json
│   ├── config/         # 插件配置
│   ├── permissions/    # 插件权限
│   └── plugins/        # 插件数据
├── logs/               # 日志
├── plugins/            # 插件源码
└── permissions/        # 权限文件
```

### 6.3 使用

```cmd
mismiss.exe                  # 默认 :8080
mismiss.exe --port 9000      # 自定义端口
```

### 6.4 注意事项

- **exe 必须和 `data/` `logs/` 等目录在同一目录下**（自动处理）
- 插件依赖安装需要目标机器有 Python + pip（exe 内不捆绑 pip）
- 默认密码 `MisMiss` / `MisMiss`，登录后立即修改

---

## 七、pip wheel（Python 开发者）

```bash
# 构建
bash scripts/build.sh wheel

# 安装
pip install dist/mismiss-1.0.0-py3-none-any.whl[web]
```

---

## 八、脚本速查

### 构建脚本（`scripts/`）

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

### 启动脚本（`scripts/`）

```bash
bash scripts/start.sh            # 开发模式
bash scripts/start.sh --prod    # 生产模式（单端口 :8080）
bash scripts/start.sh --backend # 仅 API

# Windows
scripts\start.bat                # 开发模式
scripts\start.bat prod          # 生产模式
scripts\start.bat backend       # 仅 API
```

### 部署脚本（`scripts/`）

```bash
bash scripts/deploy.sh --docker  # Docker 部署
bash scripts/deploy.sh --native  # 原生部署（Linux systemd + venv）

# Windows
powershell -File scripts\deploy.ps1 -Mode Docker
powershell -File scripts\deploy.ps1 -Mode Native
```

---

## 九、目录结构

```
MisMiss/
├── config.yml                 # 服务器配置
├── pyproject.toml             # Python 包元数据
├── mismiss.spec               # PyInstaller 打包配置
│
├── Dockerfile                 # 企业级多阶段构建
├── docker-compose.yml         # Docker 开发/测试
├── docker-compose.prod.yml    # Docker 生产（Nginx + App）
├── nginx.conf                 # Nginx 生产配置
│
├── .github/workflows/
│   └── docker-build.yml       # CI/CD 自动构建 & 推送
│
├── src/                       # Python 核心框架
│   ├── interfaces/            # MIST 抽象接口
│   └── core/                  # Missevan 实现
│
├── web/
│   ├── backend/               # FastAPI Web 控制台
│   │   ├── main.py            # 入口
│   │   └── api/routes/        # API 路由
│   └── frontend/              # React + Vite + Tailwind
│
├── scripts/                   # 构建 & 部署 & 启动脚本
│   ├── build.sh / build.ps1   # 打包（archive / wheel / exe）
│   ├── deploy.sh / deploy.ps1 # 部署（docker / native）
│   ├── start.sh / start.bat   # 启动（dev / prod / backend）
│   ├── pyinstaller_entry.py   # PyInstaller 入口
│   └── docker-entrypoint.sh   # Docker 容器入口
│
├── start.bat                  # 快捷启动（委托 → scripts/start.bat）
├── mismiss_cli.py             # pip install 入口
│
├── plugins/                   # 插件目录
├── data/                      # 运行时数据
├── logs/                      # 日志
├── permissions/               # 权限配置
│
├── build/                     # 构建临时目录（.gitignore）
└── dist/                      # 构建产物（.gitignore）
```
