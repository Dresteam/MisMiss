# MisMiss 构建与部署指南

## 前置要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Python | 3.13+ | 后端 |
| Node.js | 20+ | 前端（含 npm） |

---

## 一、开发模式（热更新）

前后端分离，代码修改自动刷新。

```bash
# 安装依赖（首次）
pip install -r requirements.txt
pip install -r web\backend\requirements.txt
cd web\frontend && npm install && cd ..\..

# 启动
start.bat
```

访问：前端 `http://localhost:15173`，API `http://localhost:18080/docs`

---

## 二、单端口生产模式（npm run build）

后端同时提供前端 SPA，单端口部署。

```bash
# 构建前端
cd web\frontend
npm install
npm run build
cd ..\..

# 启动（仅后端）
start.bat prod
```

访问 `http://localhost:18080`（前端 + API 同端口）。

---

## 三、Docker 部署

### 3.1 配置镜像加速（中国大陆必做）

Docker Desktop → ⚙ → Docker Engine，添加：

```json
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com"
  ]
}
```

Apply & Restart。

### 3.2 构建并启动

```bash
docker compose up -d --build
```

### 3.3 常用命令

```bash
docker compose logs -f     # 查看日志
docker compose down        # 停止
docker compose up -d       # 重新启动（不重新构建）
```

访问 `http://localhost:18080`。

---

## 四、PyInstaller 独立 exe（无需 Python / Node.js）

目标机器无需安装任何运行时，双击 exe 即可运行。

### 4.1 构建

```bash
# 先构建前端（必须）
cd web\frontend
npm install
npm run build
cd ..\..

# 构建 exe
.\scripts\build.ps1 -Mode Exe
```

产物：`dist\mismiss.exe`。

### 4.2 部署到目标机器

将以下内容复制到目标机器同一目录：

```
mismiss.exe          # 主程序
config.yml           # 配置文件（自动复制）
data\                # 空目录（运行时自动创建）
logs\                # 空目录
plugins\             # 空目录
permissions\         # 空目录
```

双击 `mismiss.exe` 或命令行：

```cmd
mismiss.exe
mismiss.exe --port 9000
```

访问 `http://localhost:18080`。

### 4.3 PyInstaller 常见问题

| 问题 | 解决 |
|------|------|
| `pip._vendor.distlib` 缺失 | 检查 mismiss.spec 中 `pip._vendor` 在列表中 |
| 插件依赖安装失败 | 确保 exe 所在目录有 `plugins\` 文件夹 |
| 首次启动 config 未复制 | 删除 `config.yml` 后重启，exe 会自动生成默认配置 |

---

## 五、纯 pip 安装（开发者）

```bash
pip install mismiss-1.0.0-py3-none-any.whl[web]
mismiss
```

---

## 六、构建脚本速查

```bash
.\scripts\build.ps1              # 交互式选择
.\scripts\build.ps1 -Mode Archive # zip + tar.gz
.\scripts\build.ps1 -Mode Exe     # PyInstaller exe
.\scripts\build.ps1 -Mode Wheel   # pip wheel
.\scripts\build.ps1 -Mode Clean   # 清理 build/ dist/

start.bat                         # 开发模式
start.bat prod                    # 生产模式
start.bat build                   # 构建前端后启动
```

---

## 七、目录结构

```
MisMiss/
├── config.yml            # 服务器配置
├── start.bat             # 一键启动
├── mismiss.spec          # PyInstaller 打包配置
├── Dockerfile            # Docker 构建
├── docker-compose.yml    # Docker 一键部署
├── BUILDING.md           # 本文档
├── src/                  # Python 源码
├── web/
│   ├── backend/          # FastAPI 后端
│   └── frontend/         # React 前端
├── plugins/              # 插件目录
├── data/                 # 运行时数据
├── logs/                 # 日志
├── scripts/              # 构建脚本
│   ├── build.ps1
│   ├── pyinstaller_entry.py
│   └── start.bat
└── dist/                 # 构建产物
    └── mismiss.exe
```
