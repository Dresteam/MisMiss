# MisMiss Web Console

现代化的 Web 控制台前端，完全替代 CLI，提供图形化的 MisMiss Bot 管理体验。

## 项目结构

```
web/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 应用入口（lifespan、CORS、路由注册）
│   ├── requirements.txt        # Python 依赖
│   ├── api/
│   │   ├── deps.py             # Server 单例依赖注入
│   │   ├── schemas.py          # Pydantic 请求/响应模型
│   │   └── routes/
│   │       ├── bot.py          # Bot 管理 API
│   │       ├── live.py         # 直播间管理 API
│   │       ├── plugin.py       # 插件生命周期/权限/配置 API
│   │       ├── server.py       # 服务器控制 API
│   │       ├── dashboard.py    # 仪表盘聚合 API
│   │       └── ws.py           # WebSocket 实时日志
│   └── __init__.py
├── frontend/                   # React + TypeScript + Vite + Tailwind CSS
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx            # React 入口
│       ├── App.tsx             # 路由 & 全局状态
│       ├── index.css           # Tailwind + 组件样式
│       ├── api/
│       │   ├── client.ts       # API 客户端（所有 REST 调用）
│       │   └── types.ts        # TypeScript 类型定义
│       ├── hooks/
│       │   ├── useToast.ts     # Toast 通知系统
│       │   └── useWebSocket.ts # WebSocket 日志连接
│       ├── components/
│       │   ├── Layout.tsx      # 全局布局（侧边栏 + 内容 + Toast + 日志）
│       │   ├── Sidebar.tsx     # 左侧导航栏
│       │   ├── Toast.tsx       # Toast 通知渲染
│       │   ├── StatusBadge.tsx # 状态指示点组件
│       │   ├── ConfirmDialog.tsx # 二次确认弹窗
│       │   ├── LogViewer.tsx   # 底部日志抽屉
│       │   ├── PluginDrawer.tsx # 插件详情抽屉
│       │   └── DynamicConfigForm.tsx # 动态配置表单生成器
│       └── pages/
│           ├── Dashboard.tsx   # 仪表盘（统计 + 饼图）
│           ├── BotPage.tsx     # Bot 管理（创建/信息/权限/Cookie）
│           ├── LivePage.tsx    # 直播间管理（列表/添加/弹幕）
│           ├── PluginPage.tsx  # 插件中心（列表/启停/配置/权限）
│           └── ServerPage.tsx  # 服务器设置（状态/重载/关闭）
└── README.md
```

## 快速启动

### 1. 安装后端依赖

```bash
cd MisMiss/
pip install -r requirements.txt          # 项目原有依赖
pip install -r web/backend/requirements.txt  # Web API 依赖
```

### 2. 安装前端依赖

```bash
cd web/frontend/
npm install
```

### 3. 启动后端 API

```bash
# 在项目根目录 MisMiss/ 下运行
python -m web.backend.main
```

API 将在 http://localhost:8000 启动。
API 文档: http://localhost:8000/docs

### 4. 启动前端开发服务器

```bash
cd web/frontend/
npm run dev
```

前端将在 http://localhost:5173 启动，自动代理 API 请求到后端。

### 5. 生产构建

```bash
cd web/frontend/
npm run build
```

构建产物在 `web/frontend/dist/`，后端会自动将其作为静态文件提供服务。

## API 端点总览

### 仪表盘
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard` | 聚合统计数据 |

### Bot 管理
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bot/create` | 创建/更新 Bot |
| GET | `/api/bot/info` | Bot 信息 |
| POST | `/api/bot/refresh` | 刷新信息 |
| GET | `/api/bot/cookie` | 查看 Cookie（需权限） |
| POST | `/api/bot/verify` | 验证 Cookie |
| POST | `/api/bot/enable` | 启用 Bot |
| POST | `/api/bot/disable` | 停用 Bot |

### 直播间管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/live/list` | 直播间列表 |
| POST | `/api/live/add` | 添加直播间 |
| GET | `/api/live/{id}` | 直播间详情 |
| POST | `/api/live/{id}/enable` | 启用 |
| POST | `/api/live/{id}/disable` | 停用 |
| POST | `/api/live/{id}/join` | 进入 |
| POST | `/api/live/{id}/quit` | 退出 |
| DELETE | `/api/live/{id}` | 移除 |
| POST | `/api/live/message` | 发送弹幕 |

### 插件中心
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plugin/list` | 插件列表 |
| GET | `/api/plugin/{name}` | 插件详情 |
| GET | `/api/plugin/{name}/handlers` | 事件处理器 |
| POST | `/api/plugin/{name}/enable` | 启用 |
| POST | `/api/plugin/{name}/disable` | 禁用 |
| POST | `/api/plugin/{name}/reload` | 重载 |
| DELETE | `/api/plugin/{name}` | 卸载 |
| GET | `/api/plugin/{name}/permissions` | 权限列表 |
| PUT | `/api/plugin/{name}/permissions` | 更新权限 |
| GET | `/api/plugin/{name}/config` | 配置 Schema + 值 |
| PUT | `/api/plugin/{name}/config` | 更新配置 |
| GET | `/api/plugin/{name}/readme` | README |
| GET | `/api/plugin/{name}/changelog` | CHANGELOG |
| GET | `/api/plugin/failed/list` | 失败插件 |
| POST | `/api/plugin/failed/{name}/retry` | 重试加载 |
| POST | `/api/plugin/refresh` | 扫描新插件 |

### 服务器
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/server/status` | 服务器状态 |
| POST | `/api/server/reload` | 重载服务器 |
| POST | `/api/server/shutdown` | 关闭服务器 |

### WebSocket
| 路径 | 说明 |
|------|------|
| `/api/ws` | 实时日志推送 |

## 技术栈

- **后端**: Python FastAPI + Pydantic v2 + uvicorn
- **前端**: React 18 + TypeScript + Vite + Tailwind CSS 3
- **图标**: Lucide React
- **图表**: Recharts
- **Markdown**: react-markdown
