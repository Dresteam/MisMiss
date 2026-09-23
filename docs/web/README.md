# MisMiss Web Console

现代化的 Web 控制台，完全替代 CLI，提供图形化的 MisMiss 管理体验。

v1.1.0 起从「单服务器仪表盘」重构为**多账户面板**：同一份前端构建产物服务两种角色，
**同一个域名、同一个登录页**，登录后按角色分流：

- **管理面板**（`role = admin`）——面板管理员维护账户、插件库、授权码与系统设置
- **账户界面**（`role = account`）——直播主只能看到并操作自己的
  Bot / 直播间 / 定时消息 / 插件，没有任何面板功能

身份完全由登录凭据决定（token 中携带 `role` 与 `account_id`），前端路由按 `role` 守卫。

账户登录后若服务器已更新到新版本，会**自动弹出该版本的更新日志**（每个账户每个版本只弹一次，
关闭时回写 `panel.json` 的 `seen_changelog_version`）。日志取自 `docs/changelog/v{版本}.md`，
该目录随部署包分发。

## 项目结构

```
web/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 应用入口（lifespan、CORS、认证中间件、路由注册、SPA fallback）
│   ├── requirements.txt        # Python 依赖
│   ├── api/
│   │   ├── deps.py             # AccountManager 依赖注入 + 账户守卫
│   │   ├── schemas.py          # Pydantic 请求/响应模型
│   │   └── routes/
│   │       ├── panel.py        # 面板：账户 CRUD / 授权码 / 公共 Bot（管理员）
│   │       ├── account.py      # 账户自身信息、自助兑换、自助改密
│   │       ├── account_plugins.py # 账户级插件（安装副本/启停/配置/权限/更新）
│   │       ├── bot.py          # 账户级 Bot 管理 API
│   │       ├── live.py         # 账户级直播间管理 API
│   │       ├── timer.py        # 账户级定时消息队列 API
│   │       ├── plugin.py       # 插件库管理 API（面板级，安装/卸载/刷新）
│   │       ├── server.py       # 服务器控制 API
│   │       ├── update.py       # 程序更新 API（GitHub Releases）
│   │       ├── auth.py         # 登录认证 API（admin + account 双角色）
│   │       ├── config.py       # 服务器配置 & 日志等级 API
│   │       ├── proxy.py        # 图片代理 API（域名白名单 + 内网拦截）
│   │       └── ws.py           # WebSocket 实时日志 + 日志查询
│   └── __init__.py
├── frontend/                   # React + TypeScript + Vite + Tailwind CSS
│   ├── package.json
│   ├── vite.config.ts          # 端口 15173，/api 代理到 18080
│   ├── tailwind.config.js      # zinc 中性灰 + primary 主题色
│   ├── index.html
│   └── src/
│       ├── main.tsx            # React 入口
│       ├── App.tsx             # 路由 & 全局状态（登录/主题/控制台 vs 门户分支）
│       ├── index.css           # Tailwind + 组件样式（卡片/按钮/徽章/Markdown）
│       ├── api/
│       │   ├── client.ts       # API 客户端（所有 REST 调用）
│       │   └── types.ts        # TypeScript 类型定义
│       ├── hooks/
│       │   ├── useAuth.ts      # 登录认证状态（token / role / accountId）
│       │   ├── useLogStream.ts # WebSocket 日志流（虚拟滚动 + 级别过滤）
│       │   └── useToast.ts     # Toast 通知系统
│       ├── i18n/               # 文案表（zh-CN）
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
│       │   ├── ExpiryBadge.tsx # 授权到期徽标（剩余天数/已过期/永久）
│       │   ├── PluginDrawer.tsx # 插件详情抽屉（信息/监听器/权限/配置/文档）
│       │   ├── PluginUI.tsx    # 插件声明式 UI 渲染器（_ui_schema.json）
│       │   ├── UninstallDialog.tsx # 卸载确认弹窗（可选删除配置/数据）
│       │   ├── UpdateDialog.tsx # 插件更新弹窗
│       │   ├── AccountDialogs.tsx # 创建账户 / 续期 / 重置凭据弹窗
│       │   ├── AccountSetup.tsx # 管理员账户设置（首次改密）
│       │   ├── ChangelogDialog.tsx # 更新日志弹窗（更新页 + 登录后自动弹出）
│       │   └── DynamicConfigForm.tsx # 动态配置表单生成器（_conf_schema.json）
│       └── pages/
│           ├── AccountsPage.tsx    # 账户总览（面板首页，卡片 + 10s 刷新）
│           ├── AccountDetailPage.tsx # 账户详情（概览/直播间/Bot/定时/插件/插件库 标签页）
│           ├── AccountPortalPages.tsx # 账户界面各页面（复用详情页标签组件）
│           ├── PluginLibraryPage.tsx # 插件库（面板级，安装/卸载/失败插件）
│           ├── PluginPageView.tsx  # 插件自定义 UI 页面
│           ├── UpdatePage.tsx  # 程序更新（版本列表/镜像站/回滚）
│           ├── LogsPage.tsx    # 服务器日志（虚拟滚动）
│           ├── SettingsPage.tsx # 设置（账户安全/公共 Bot/授权码/日志/端口/配置）
│           ├── ServerPage.tsx  # 服务器设置（状态/重载/关闭）
│           └── LoginPage.tsx   # 登录页（管理端与账户端共用，按 role 分流）
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

## 认证与授权

中间件（`main.py`）统一保护 `/api/*`，按 token 中的 `role` 分权：

| 角色 | 来源 | 可访问范围 |
|------|------|-----------|
| `admin` | `data/auth.json`（默认 `MisMiss` / `MisMiss`，首次登录强制改密） | 全部接口 |
| `account` | 账户记录中的用户名/密码 | 仅 `/api/accounts/{自己的 id}/...`，以及 `/api/health`、`/api/auth/`、`/api/proxy/` |

匿名可访问的入口只有：

- `/api/auth/*`（登录与令牌校验本身）
- `/api/proxy/image`（`<img>` 无法携带 Authorization header，改由域名白名单 + 内网地址拦截限制目标）
- `/api/accounts/{id}/plugin/{name}/ui/*`（插件自带 UI 的静态资源路径，运行时由 `PluginManager` 注册）
- `/api/health`

token 为 64 位十六进制字符串，按文件存放在 `data/tokens/`（多 worker 共享），有效期 30 天。

## API 端点总览

### 面板管理（admin）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/panel/overview` | 账户总览聚合（含公共 Bot 配置状态） |
| GET | `/api/panel/status` | 服务器聚合状态 |
| GET | `/api/panel/accounts` | 账户列表 |
| POST | `/api/panel/accounts` | 创建账户 |
| GET | `/api/panel/accounts/{id}` | 账户详情 |
| PATCH | `/api/panel/accounts/{id}` | 修改账户（名称/直播间/Bot 模式/Cookie） |
| POST | `/api/panel/accounts/{id}/credentials` | 重置账户登录凭据 |
| DELETE | `/api/panel/accounts/{id}?purge_data=` | 删除账户（可选清除数据目录） |
| POST | `/api/panel/accounts/{id}/renew` | 续期（叠加天数 / 直接设置到期时间） |
| POST | `/api/panel/accounts/compensate` | 批量补偿时长（按条件筛选账户） |
| POST | `/api/panel/accounts/{id}/redeem` | 用授权码为账户充值 |
| GET | `/api/panel/licenses` | 授权码列表 |
| POST | `/api/panel/licenses/generate` | 批量生成授权码 |
| DELETE | `/api/panel/licenses/{code}` | 撤销未使用的授权码 |

**批量补偿时长**：`POST /api/panel/accounts/compensate`，请求体
`{days, include_expired, include_active, max_days_left?, account_ids?, dry_run?}`。

- 筛选条件之间取**并集**（勾了「已过期」和「未过期」就是两者合集）；两个都不勾
  则没有候选，避免手滑把全部账户补一遍。`max_days_left` 再收窄为「剩余 ≤ N 天」，
  `account_ids` 再收窄为「在这批 id 里」（手动勾选）
- **永久账户始终排除**，并显式计入 `skipped`（管理员能看出为什么没补它）
- 叠加规则与单账户续期完全一致：从 `max(现在, 原到期时间)` 起算，
  所以已过期的账户补完即从今天续上；补完是否自动恢复运行沿用账户自身的
  `auto_resume_on_renew` 偏好，不引入第二套语义
- 面板走「预览（`dry_run=true`）→ 二次确认列出将要补谁 → 执行」两段式，
  返回体带 `groups`（按 已过期 / 未过期 分组）与 `message` 供弹窗直接展示
- `days` 非正整数、`max_days_left` 非整数、`account_ids` 含非整数均返回 400
| GET | `/api/panel/public-bot` | 公共 Bot 信息（不含 Cookie） |
| GET | `/api/panel/public-bot/cookie` | 公共 Bot 的明文 Cookie |
| PUT | `/api/panel/public-bot` | 保存公共 Cookie（仅保存，不下发） |
| POST | `/api/panel/public-bot/apply` | 下发公共 Cookie 到全部公共账户 |
| POST | `/api/panel/public-bot/refresh` | 刷新公共 Bot 信息 |
| POST | `/api/panel/public-bot/verify` | 验证公共 Cookie |
| DELETE | `/api/panel/public-bot` | 清除公共 Cookie |

### 账户（admin 与账户本人）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/accounts/{id}/info` | 账户信息与运行时状态 |
| POST | `/api/accounts/{id}/redeem` | 自助兑换授权码（过期账户亦可，兑换后自动恢复） |
| POST | `/api/accounts/{id}/change-password` | 自助改密（需原密码，成功后撤销该账户全部会话） |

### Bot（账户级）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/accounts/{id}/bot/create` | 创建/更新 Bot（公共 Cookie 模式禁用） |
| POST | `/api/accounts/{id}/bot/mode` | 切换公共/私有 Cookie 模式 |
| GET | `/api/accounts/{id}/bot/info` | Bot 信息 |
| POST | `/api/accounts/{id}/bot/refresh` | 刷新信息 |
| GET | `/api/accounts/{id}/bot/cookie` | 查看 Cookie（需 `EXPOSE_COOKIE`，公共模式禁用） |
| POST | `/api/accounts/{id}/bot/verify` | 验证 Cookie |
| POST | `/api/accounts/{id}/bot/enable` | 启用 Bot |
| POST | `/api/accounts/{id}/bot/disable` | 停用 Bot |
| DELETE | `/api/accounts/{id}/bot/` | 删除 Bot（公共模式仅停用） |

### 直播间（账户级，每账户一个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/accounts/{id}/live/` | 直播间信息 |
| POST | `/api/accounts/{id}/live/add` | 绑定/更换直播间 |
| DELETE | `/api/accounts/{id}/live/` | 解除绑定 |
| POST | `/api/accounts/{id}/live/refresh` | 刷新房间信息 |
| POST | `/api/accounts/{id}/live/enable` | 启用（自动进入直播间） |
| POST | `/api/accounts/{id}/live/disable` | 停用（断开连接） |
| POST | `/api/accounts/{id}/live/join` | 进入直播间 |
| POST | `/api/accounts/{id}/live/quit` | 退出直播间 |
| POST | `/api/accounts/{id}/live/message` | 发送弹幕 |

### 定时消息（账户级）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/accounts/{id}/timer/list` | 定时消息列表（合并轮转 + 倒计时） |
| PUT | `/api/accounts/{id}/timer/interval` | 修改发送间隔（实时生效并持久化） |
| POST | `/api/accounts/{id}/timer/add` | 添加消息 |
| PUT | `/api/accounts/{id}/timer/{message_id}` | 编辑消息内容 |
| DELETE | `/api/accounts/{id}/timer/{message_id}` | 删除消息 |
| POST | `/api/accounts/{id}/timer/{message_id}/move` | 上移/下移 |
| POST | `/api/accounts/{id}/timer/{message_id}/skip` | 跳过指针处消息 |
| POST | `/api/accounts/{id}/timer/{message_id}/send` | 立即发送 |

### 账户插件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/accounts/{id}/plugins/library` | 插件库列表（标注是否已安装） |
| POST | `/api/accounts/{id}/plugins/install` | 从插件库安装副本（默认禁用） |
| POST | `/api/accounts/{id}/plugins/update-all` | **一键更新**：把本账户中副本版本低于库版本的插件全部更新（保留启用状态与配置） |
| POST | `/api/accounts/{id}/plugins/{name}/update` | 从插件库覆盖更新副本（保留启用状态与配置） |
| GET | `/api/accounts/{id}/plugins/` | 已安装插件列表 |
| GET | `/api/accounts/{id}/plugins/{name}` | 插件详情（含配置 schema 与 UI schema） |
| DELETE | `/api/accounts/{id}/plugins/{name}?delete_config=&delete_data=&delete_persistent=` | 卸载（三个数据选项互相独立，默认全 false） |
| POST | `/api/accounts/{id}/plugins/{name}/enable` | 启用 |
| POST | `/api/accounts/{id}/plugins/{name}/disable` | 禁用 |
| POST | `/api/accounts/{id}/plugins/{name}/reload` | 重载 |
| GET/PUT | `/api/accounts/{id}/plugins/{name}/permissions` | 权限查询 / 逐项更新 |
| GET/PUT | `/api/accounts/{id}/plugins/{name}/config` | 配置查询 / 更新（运行时热重载） |
| GET | `/api/accounts/{id}/plugins/{name}/readme` | README |
| GET | `/api/accounts/{id}/plugins/{name}/changelog` | CHANGELOG |
| GET | `/api/accounts/{id}/plugin/{name}/ui/*` | 插件自带 UI 的数据端点（由插件 `register_routes` 注册） |

### 插件库（面板级，admin）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plugin/list` | 插件库列表（含被哪些账户使用） |
| POST | `/api/plugin/install` | 上传 zip 安装到库（版本冲突返回 409 与新版本号） |
| POST | `/api/plugin/install/update` | 确认覆盖更新库中插件并重载各账户已启用实例 |
| POST | `/api/plugin/install/stream` | SSE 流式安装（实时进度日志） |
| DELETE | `/api/plugin/{name}?delete_config=&delete_data=&disable_in_accounts=` | 从库中卸载 |
| GET | `/api/plugin/{name}/readme` | README |
| GET | `/api/plugin/{name}/changelog` | CHANGELOG |
| POST | `/api/plugin/refresh` | 重新扫描插件库 |
| POST | `/api/plugin/{name}/push` | 把该插件的库版本推送到各账户副本 |
| POST | `/api/plugin/push-all` | 把库中全部插件推送到各账户副本 |
| POST | `/api/plugin/{name}/default` | 设为 / 取消默认插件（body: `{"default": true}`） |
| POST | `/api/plugin/apply-defaults` | 把默认插件补齐到全部现有账户 |

**批量推送的版本守卫**：只处理**已安装该插件**的账户，并跳过「副本版本不低于库版本」的。
更新会 stop/start 插件实例（断掉插件消息与内部状态），无谓的重载应当避免——因此手动改过
副本的账户、以及已是最新的账户都不会被触碰。返回 `{updated, skipped, failed, message}`。

**账户卸载的三个数据选项**（互相独立，**默认全部不勾选**，且每次打开弹窗都会重置）：

| 参数 | 删除什么 |
|------|---------|
| `delete_config` | 配置与权限文件（`config/{name}_config.json`、`permissions/{name}_permissions.json`） |
| `delete_data` | 插件经 `self.data` 创建的 **JSON** 数据（`{name}/` 下的 `*.json`） |
| `delete_persistent` | 数据目录中的**其他**文件——插件自带或自行创建的非 `.json` 文件（缓存/数据库/日志等） |

后两者按**文件扩展名**区分，都不选时数据目录原样保留，重新安装即可续用；删空的子目录会被回收。

**默认插件**：清单存于 `data/panel.json` 的 `default_plugins`，只对**此后创建**的账户生效
（`create_account` 会在账户起来后自动安装并启用，失败仅告警不阻断创建）；
存量账户需显式调用 `apply-defaults` 补齐。插件库列表的每项带 `is_default` 标记。

### 服务器

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/server/status` | 服务器状态（含 `broadcast_max_len` 全局消息上限） |
| POST | `/api/server/reload` | 重载全部账户运行时 |
| POST | `/api/server/shutdown` | 关闭全部账户运行时 |
| POST | `/api/server/broadcast` | 用各账户的机器人发送一条全局消息 |

**全局消息**：`POST /api/server/broadcast`，请求体 `{"message": "..."}`。
与程序更新的提示消息走**同一条通道**（`AccountManager.broadcast_to_livestreams`）：

- 只发给**已启用且正在开播**的直播间；未绑定 / 未启用 / 未开播 / 已过期的账户跳过
- 单个账户发送失败只影响它自己，结果里计入「失败」，不影响其余账户
- 消息会压掉多余空白并截断到 `broadcast_max_len`（默认 80，弹幕有长度上限）
- 消息为空或纯空白返回 400；面板「服务器设置」页有对应输入框与二次确认

### WebSocket

浏览器 WebSocket API 无法设置 `Authorization` header，因此 token 通过查询参数传递；
日志属于面板功能，仅 `admin` 可连。鉴权失败时服务端以关闭码 **4401** 断开，
前端据此停止重连并提示。

| 路径 | 说明 |
|------|------|
| `/api/ws?token=&last_seq=&levels=` | 实时日志推送（批量帧） + 重连补发 |

### 日志

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/logs/history?since=&limit=&levels=&scope=&account=` | 历史日志分页查询（`scope=plugin` 仅返回插件相关日志） |
| GET | `/api/logs/gap?from_seq=&to_seq=` | 断线补发（数据被淘汰时返回 `status: expired`） |
| GET | `/api/logs/stats` | 环形缓冲区统计（容量 10000 条） |

**日志的账户筛选**：`account` 参数**可重复传递以多选**（`?account=甲&account=乙`），
WebSocket 实时推送用同一套参数；其中**空串表示只看面板级日志**，不传该参数则不过滤。
面板日志页的筛选器是多选浮层，勾选即生效。

### 程序更新

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/update/info` | 当前版本与更新配置 |
| GET | `/api/update/check` | 检测最新版本（语义版本比较） |
| GET | `/api/update/changelog/{version}` | 指定版本更新日志 |
| POST | `/api/update/settings` | 保存更新配置（仓库/镜像/代理/更新提示消息） |
| POST | `/api/update/apply` | 执行更新（Docker 走镜像重建，原生走覆盖解压） |
| POST | `/api/update/rollback` | 回滚到备份版本 |

**更新提示消息**：`update.notify_enabled` 打开后，程序更新时会用各账户的机器人
在其**已启用且正在开播**的直播间各发一条自定义消息（未绑定 / 未启用 / 未开播 /
已过期的账户自动跳过，单账户失败不影响其余账户）：

- `update.notify_before`（默认「机器人即将更新，稍后自动恢复」）——在更新包下载完成、
  覆盖程序文件**之前**发送；发送后等消息队列真正排空，否则解压触发的进程重启会把
  未发出的消息一并掐掉（原生部署的 uvicorn `reload=True` 会在覆盖 `src/` 后自动重启）。
- `update.notify_after`（默认「机器人已更新完成，已恢复正常」）——更新时把待发标记写入
  `data/update_state.json`，由新版本启动完成后的 lifespan 补发，只发一次；解压失败会
  撤销标记，普通重启不会误发。

单条消息上限 80 字符，超出截断；留空则跳过对应阶段。

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录（先试面板管理员，再试账户凭据） |
| POST | `/api/auth/change-password` | 修改面板管理员账号/密码（清除全部 token） |
| GET | `/api/auth/check` | 验证 token（返回 role / account_id） |
| POST | `/api/auth/skip-first-login` | 跳过首次登录引导 |

### 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 读取完整配置 |
| PUT | `/api/config` | 合并写入配置 |
| PUT | `/api/config/log-level` | 动态修改日志等级 |
| PUT | `/api/config/ports` | 修改 API 端口并重启 |
| POST | `/api/config/pip-install` | 安装 pip 包（admin） |
| GET | `/api/proxy/image?url=` | 图片代理（域名白名单 + 内网拦截） |

**日志等级**：由 `config.yml` 的 `logging.level` 决定，默认 **INFO**。
`core.logging.init()`、面板实时日志流（WS sink）与「设置」页的调试开关都读写这同一项——
面板切换 DEBUG 会就地改各 handler 的等级并持久化，无需重启。
排查插件加载、`state` 文件同步等流程时需要先切到 DEBUG，这些细节日志按 DEBUG 输出。

## 技术栈

- **后端**: Python FastAPI + Pydantic v2 + uvicorn（Docker 下为 gunicorn + UvicornWorker，默认单 worker）
- **前端**: React 18 + TypeScript + Vite + Tailwind CSS 3（zinc 中性灰主题）
- **图标**: Lucide React
- **图表**: Recharts
- **虚拟滚动**: react-virtuoso（日志万条不卡顿）
- **Markdown**: react-markdown + remark-gfm/math + rehype-katex/raw（GFM、数学公式、内联 HTML）
- **代码高亮**: react-syntax-highlighter
