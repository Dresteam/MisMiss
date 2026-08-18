# MisMiss Web Console

现代化的 Web 控制台前端，完全替代 CLI，提供图形化的 MisMiss Bot 管理体验。

## 项目结构

```
web/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 应用入口（lifespan、CORS、认证中间件、路由注册、SPA fallback）
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
│   │       ├── timer.py        # 定时消息队列 API
│   │       ├── update.py       # 程序更新 API（GitHub Releases）
│   │       ├── auth.py         # 登录认证 API
│   │       ├── config.py       # 服务器配置 & 日志等级 API
│   │       ├── proxy.py        # 反向代理 API
│   │       └── ws.py           # WebSocket 实时日志
│   └── __init__.py
├── frontend/                   # React + TypeScript + Vite + Tailwind CSS
│   ├── package.json
│   ├── vite.config.ts          # 端口 15173，/api 代理到 18080
│   ├── tailwind.config.js      # zinc 中性灰 + primary 主题色
│   ├── index.html
│   └── src/
│       ├── main.tsx            # React 入口
│       ├── App.tsx             # 路由 & 全局状态（登录/主题）
│       ├── index.css           # Tailwind + 组件样式（卡片/按钮/徽章/Markdown）
│       ├── api/
│       │   ├── client.ts       # API 客户端（所有 REST 调用）
│       │   └── types.ts        # TypeScript 类型定义
│       ├── hooks/
│       │   ├── useAuth.ts      # 登录认证状态
│       │   ├── useLogStream.ts # WebSocket 日志流
│       │   └── useToast.ts     # Toast 通知系统
│       ├── components/
│       │   ├── Layout.tsx      # 全局布局（分组侧边栏 + 移动端抽屉 + Toast）
│       │   ├── Sidebar.tsx     # 左侧分组导航栏（含版本号）
│       │   ├── Button.tsx      # 按钮组件（含自定义悬浮提示）
│       │   ├── HoverTip.tsx    # 自定义悬浮提示（替代原生 title）
│       │   ├── Toast.tsx       # Toast 通知渲染
│       │   ├── StatusBadge.tsx # 状态指示点组件
│       │   ├── ConfirmDialog.tsx # 二次确认弹窗
│       │   ├── MarkdownRenderer.tsx # Markdown 渲染（GFM/数学/HTML）
│       │   ├── MarqueeText.tsx # 文字跑马灯
│       │   ├── RoomSelect.tsx  # 直播间选择器
│       │   ├── PluginDrawer.tsx # 插件详情抽屉
│       │   ├── PluginUI.tsx    # 插件声明式 UI 渲染器
│       │   ├── InstallModal.tsx # 插件安装弹窗（SSE 实时日志）
│       │   ├── ReadmeModal.tsx  # README/文档弹窗
│       │   ├── UninstallDialog.tsx # 卸载确认弹窗
│       │   ├── UpdateDialog.tsx # 插件更新弹窗
│       │   ├── AccountSetup.tsx # 账户设置（首次改密）
│       │   └── DynamicConfigForm.tsx # 动态配置表单生成器
│       └── pages/
│           ├── Dashboard.tsx   # 仪表盘（统计 + 饼图）
│           ├── BotPage.tsx     # Bot 管理（创建/信息/权限/Cookie）
│           ├── LivePage.tsx    # 直播间管理（列表/添加/弹幕）
│           ├── PluginPage.tsx  # 插件中心（列表/启停/配置/权限）
│           ├── PluginPageView.tsx # 插件自定义 UI 页面
│           ├── TimerPage.tsx   # 定时消息队列（合并轮转/倒计时）
│           ├── UpdatePage.tsx  # 程序更新（版本列表/镜像站/回滚）
│           ├── LogsPage.tsx    # 服务器日志（虚拟滚动）
│           ├── SettingsPage.tsx # 设置（账户/日志/端口/配置）
│           ├── ServerPage.tsx  # 服务器设置（状态/重载/关闭）
│           └── LoginPage.tsx   # 登录页
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

API 将在 http://localhost:18080 启动。
API 文档: http://localhost:18080/docs

### 4. 启动前端开发服务器

```bash
cd web/frontend/
npm run dev
```

前端将在 http://localhost:15173 启动，自动代理 `/api` 请求到后端（18080）。

也可以在项目根目录直接使用 `start.bat`（开发模式一键启动前后端）或 `start.bat prod`（生产单端口模式：:18080 同时提供前端与 API）。

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

### 日志
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs/history?since=&limit=` | 历史日志分页查询 |
| GET | `/api/logs/gap?from=&to=` | 断线补发 |
| GET | `/api/logs/stats` | 环形缓冲区统计 |

### 定时消息
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/timer/list` | 定时消息列表（合并轮转 + 倒计时） |
| PUT | `/api/timer/interval` | 修改发送间隔（实时生效并持久化） |
| POST | `/api/timer/add` | 添加消息（`live_id=0` 为全局） |
| PUT | `/api/timer/{id}` | 编辑消息内容 |
| DELETE | `/api/timer/{id}` | 删除消息 |
| POST | `/api/timer/{id}/move` | 上移/下移 |
| POST | `/api/timer/{id}/skip` | 跳过当前指针处消息（指针后移） |
| POST | `/api/timer/{id}/send` | 立即发送 |

### 程序更新
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/update/info` | 当前版本与更新配置 |
| GET | `/api/update/check` | 检测最新版本（语义版本比较） |
| GET | `/api/update/changelog/{version}` | 指定版本更新日志 |
| POST | `/api/update/settings` | 保存更新配置（仓库/镜像/代理） |
| POST | `/api/update/apply` | 执行更新（备份→下载→覆盖→重启） |
| POST | `/api/update/rollback` | 回滚到备份版本 |

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录（默认 MisMiss/MisMiss） |
| GET | `/api/auth/check` | 验证 token |
| POST | `/api/auth/skip-first-login` | 跳过首次登录引导 |

### 配置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 读取完整配置 |
| PUT | `/api/config` | 合并写入配置 |
| PUT | `/api/config/log-level` | 动态修改日志等级 |
| PUT | `/api/config/ports` | 修改 API 端口并重启 |
| GET | `/api/config/cookie` | 从持久化文件直读 Cookie |

## 技术栈

- **后端**: Python FastAPI + Pydantic v2 + uvicorn
- **前端**: React 18 + TypeScript + Vite + Tailwind CSS 3（zinc 中性灰主题）
- **图标**: Lucide React
- **图表**: Recharts
- **Markdown**: react-markdown + remark-gfm/math + rehype-katex/raw（GFM、数学公式、内联 HTML）
- **代码高亮**: react-syntax-highlighter
