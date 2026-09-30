# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

MisMiss 是 [MIST](https://github.com/dikxingmengya/MIST) 直播场控机器人标准在**猫耳FM**平台的参考实现。
一个面板（`AccountManager`）托管 N 个账户，每个账户 = 1 个 Bot + 1 个直播间 +
独立的事件总线 / 插件副本 / 配置 / 权限。Web 控制台是唯一入口，`src/cli.py` 是遗留 CLI。

代码、注释、文档、提交信息**一律用中文**。

## 常用命令

### 运行

```bash
start.bat              # 开发：Vite :15173 + API :18080（Vite 把 /api 代理到后端）
start.bat prod         # 单端口：:18080 同时提供前端与 API（需先 npm run build）
start.bat build        # 构建前端后以 prod 模式启动
```

面板默认账号 **MisMiss / MisMiss**（`data/auth.json`），首次登录强制改密。
start.bat 内部调 `python`，在本机解析到 Windows Store 占位程序会静默失败——
必要时用 `.venv/Scripts/python.exe -m web.backend.main --port 18080`。

### 测试

`test/` 下除 `test_license_store.py` 外**都是 `if __name__ == "__main__"` 驱动的独立脚本**，
逐条直接跑，输出 `PASS n: ...`：

```bash
.venv/Scripts/python.exe test/test_account_manager.py
```

`pytest test/` 不可用：`pyproject.toml` 声明了 `asyncio_mode = "auto"`，但 dev 依赖里没有
`pytest-asyncio`，异步用例会报 "async def functions are not natively supported"。
`test_license_store.py` 是唯一 pytest 风格的纯同步用例。

**一律用 `.venv/Scripts/python.exe`**（Python 3.14）——本机 `python` 是 Windows Store
占位程序，无输出、退出码 49，会静默吞掉命令。Windows 控制台是 GBK，bash 里中文日志显示为
乱码属编码问题，看 `PASS`/`FAIL` 标记即可。

### 检查

```bash
.venv/Scripts/python.exe -m ruff check src/ web/backend/     # line-length 100, py313
.venv/Scripts/python.exe -m mypy src/
cd web/frontend && npm run build                             # tsc -b && vite build
```

前端发布构建因类型错误而失败——提交前跑一次 `npm run build`，别只看 `vite dev`。

### 发版

```bash
powershell -File scripts/release.ps1 -Version 1.5.0    # 全格式
bash scripts/docker-release.sh 1.5.0                   # 只出 Docker 部署包
```

版本号解析顺序：CLI 参数 → `pyproject.toml` 的 `version` → git tag → 日期。发版前**必须**：

1. 改 `pyproject.toml` 的 `version`（Docker 构建经 `MISMISS_VERSION` 注入镜像）；
2. 新建 `docs/changelog/v<版本>.md`——账户登录后的更新日志弹窗读的就是它，缺失则弹窗为空。

在线更新只认 GitHub Releases 上**更高**的版本号，复用同版本号资产不会被检测为可更新。
Docker 部署包必须是**扁平结构**（顶层无目录，成员直接是 `deploy.sh` / `docker-compose.yml` /
`mismiss-docker.tar.gz`），旧版服务器的校验按精确成员名匹配，嵌套目录会让在线更新失败。
Windows 打包用系统 `bsdtar`——Git 自带的 tar 不支持盘符路径。

## 架构

### 分层

```
src/interfaces/   MIST 抽象接口层（契约，不含任何实现）
src/core/         Missevan 平台适配实现
web/backend/      FastAPI 面板后端
web/frontend/     React + TS + Tailwind 面板前端
plugins/          官方插件库（独立 git 仓库，只作安装源，不直接运行）
```

### 磁盘布局

```
config.yml                     # 面板级配置（硬编码解析到仓库根）
data/panel.json                # 账户记录、公共 Cookie、授权码、默认插件
data/auth.json                 # 面板管理员凭据
data/tokens/                   # 登录令牌（一个 token 一个文件）
data/accounts/{id}/
    server_state.json          # 运行时状态：bot / timer_messages / livestreams / enabled_plugins
    installed_plugins/{name}/  # 插件**源码副本**（从 plugins/ 拷来）
    config/{name}_config.json  # 插件配置
    permissions/{name}_permissions.json
    plugins/{name}/            # 插件数据（PluginDataManager 沙箱目录）
```

注意账户目录下 **`installed_plugins/` 是代码、`plugins/` 是数据**——名字反直觉。

### 插件：库 + 副本

「安装」= `copytree` 一份源码到账户目录，此后该账户独立运行。改插件库**不影响**已安装账户，
需在账户插件页点「更新」覆盖。

模块加载刻意**不**走 `import plugins.x.y`：`_import_plugin_module` 用
`mismiss_plugin_{sha1(abspath)[:12]}_{name}` 作模块名 + `spec_from_file_location`。
原因是账户的 `plugins/` 恰好是插件数据目录、且仓库 `plugins/` 是无 `__init__.py` 的 namespace 包，
按普通 import 会让多个账户共享同一份源码。

版本守卫：副本版本 `>=` 库版本即跳过，唯一实现收敛在 `_update_outdated_in_account`，
账户侧 `update_plugins_in_account` 与面板侧 `push_plugin_to_accounts` 共用。

三个附属管理器：

- `PluginConfigManager` —— 按 `_conf_schema.json` 生成默认值与已存配置深合并，**仅当 schema 出现新字段时**才回写，用户值不会被覆盖
- `PluginPermissionManager` —— 首次加载分配默认权限（仅 `SEND_LIVESTREAM_MESSAGE`），新增的 `BotPermission` 成员自动补 `False`
- `PluginDataManager` —— 路径沙箱，`..` 与绝对路径抛 `ValueError`

### 权限三层

`BotPermission` Flag 是天花板，∩ 插件权限；执行时经 `contextvars` 的 `current_plugin`
在 Bot 的敏感方法内实时校验。公共 Cookie 账户的 Bot 被强制降为「仅发送直播间消息」，
其插件也随之只能发消息。

### 事件系统

`EventBus.call_event` 按 `type(event).__mro__` 收集 handler，再按
`@event_handler(priority=N)` **降序**稳定排序（值大者先执行）；同优先级保持
(MRO 顺序, 注册顺序)，因此不写 priority 时行为与传统顺序完全一致。

两个反直觉点：

- **异步 handler 无法 `cancel()`**——`async def` 的 handler 被 `create_task` 并发调度，
  派发循环早已跑完。需要「阻止传播」语义必须写成同步 handler。
- 跨房事件（`LiveCrossMessageEvent` / `LiveCrossGiftEvent`）与 `LiveMessageEvent` /
  `LiveGiftEvent` 是**兄弟而非父子**节点，监听本房弹幕的插件收不到对方直播间的事件。
  两者的「对方直播间」字段名方向相反：`origin_*`（弹幕来自）vs `target_*`（礼物送给）。

### 定时消息

「插件消息 → 全局消息 → 房间消息」合并轮转，每 `timer_interval` 秒发一条。
插件消息**不落盘**（插件重启后自行重注册）、面板不可改删、轮转置顶，与普通消息
**共用同一个位置指针**——增删插件消息时 `_shift_positions` 同步挪指针，
保证指针始终指向同一条消息。`only_when_live=True` 的未开播时跳过且指针照常推进。

### 状态持久化与跨 worker

`server_state.json` 最后写入者获胜，**没有锁**。每次写前调 `_ensure_state_fresh()`
按 mtime 判断是否重读，避免陈旧 worker 复活已删除的对象；FastAPI 的账户级依赖
（`api/deps.py` 的 `require_account` / `require_active_account`）每个请求都会调用它。

**默认单 worker**（`MISMISS_WORKERS=1`）：直播间连接、Bot 定时器、插件实例都是单实例资源，
多 worker 会导致连接重复与事件分裂。多 worker 同步代码保留但仅作兜底。

### 认证

Token 是**磁盘文件**（`data/tokens/{64位hex}`），不是内存字典——多 worker 下才能共享。
载荷 `{username, expires, role, account_id, must_change_password}`，TTL 30 天。
文件名即 token，因此校验强制 64 位 hex（WS 握手把 token 放在 query 参数里）。

角色：`admin` 全部可访问；`account` 只能访问 `/api/accounts/{自己的 id}/...`，
中间件按字符串解析路径判断（`web/backend/main.py`）。

默认账户密码 `user123`（`core/account/manager.py` 的 `DEFAULT_ACCOUNT_PASSWORD`），
前端 `AccountDialogs.tsx` 里有同一份明文兜底——**改一处必须改另一处**。
仍在使用默认密码的账户登录后强制先改密。

### 到期停用

`AccountRecord.expired` 是裸 UTC 比较；`ExpiryScheduler` 每 60s 巡检，
到期走 `stop_for_expiry`：停 Bot、断开全部直播间、`suspend_all()` 插件
（注销 handler 但**保留 `enabled` 标记**，不是 disable），写 `paused_reason="expiry"`。
续期经 `resume_after_renew` 自动恢复。永久账户兑换授权码会被拒绝且不消耗该码。

### 更新流程

`update:` 段落在**仓库根 `config.yml`**，运行时状态在 `data/update_state.json`。
Docker 路径：校验部署包（须含 `docker-compose.yml` + 真实 `docker save` 归档）→
备份到 `.mismiss-backup` → 解压（跳过 `config.yml` / `.env`）→ `docker load` →
派发**一次性容器**在宿主执行 compose 重建。重建必须由独立容器执行——在应用容器内
直接跑 compose 会杀掉执行中的进程。`notify_before` 在下载后、写盘前发送；
`notify_after` 由**下一个进程**在 `lifespan` 里补发。

### 日志

loguru：`logs/bot_{date}.log`（10MB 轮转 / 保留 7 天）+ `error_{date}.log` + stderr，
`core.logging` 在 import 时自动初始化。WS 日志流的环形缓冲（10000 条）与 200ms 批量推送
在 `web/backend/api/routes/ws.py`，**不在** `core/logging.py`。
WS 握手只允许 admin，鉴权在 `ws.py` 内单独完成——WebSocket 不经过认证中间件。

**日志等级约定**：默认 INFO，由 `config.yml` 的 `logging.level` 驱动。无价值 / 高频重复
的日志一律 `debug`——判据是「这条日志能否回答一次线上排查」。批量扇出操作（如刷新插件库
会打到每个账户）只在循环外打**一条汇总**，不要逐账户打。

## 约定

- 提交信息用中文 conventional 前缀（`feat:` / `fix:` / `release:` / `docs:` / `refactor:`），
  作者 `Drest <dikxingmeng@163.com>`，提交人 `Claude <noreply@anthropic.com>`。
- 新增面板文案直接写进组件：`web/frontend/src/i18n/zh-CN.ts` 虽然存在，但全部代码里只有
  十几次 `t()` 调用，实际上未接线，不必为它新增词条。

## 陷阱

- **`config.yml` 是硬编码路径**（`src/core/config.py` 从 `__file__` 上溯三级到仓库根）。
  `MISMISS_DATA_DIR` 只隔离 `data/`，隔离不了它——测试若走 `/api/update/settings` 或
  `/api/config/log-level` 会改到开发机真实配置，必须备份 + `atexit` 还原
  （照 `test/test_update_notify.py` 的写法）。该文件**在 git 里**，改坏了会进提交。
- `config.yml` 在 Docker 里是**单文件 bind mount**，无法原子替换；`write_text_resilient`
  在 `EBUSY` 时会退回直接覆写。不要「顺手」改回 `os.replace` 原子写。
- `web/backend` 的导入写作 `from api.xxx import ...`，靠 `main.py` 把 `web/backend/`
  插进 `sys.path` 才成立；路由里的 `api.deps` 用函数内导入规避循环依赖。
- ⚠️ **同一个路由文件会有两个模块对象**：`api.routes.x` 与 `web.backend.api.routes.x`
  是同名文件被各执行一次的两个模块。测试里打桩**必须**用 `from api.routes import x`
  （app 走的就是这条路径），用 `web.backend.api.routes` 打桩会静默无效——改了类属性，
  但 app 用的是另一份，表现为「桩明明打上了，行为还是真的」。
- ⚠️ **`MISMISS_DATA_DIR` 拼错会静默读到真实 `data/`**（名字是 MISMISS，不是 MISSISS）。
  `os.environ.get` 拿不到就回落到 `"data"`，进程照常启动并把线上账户的 Bot 一并拉起。
  测试里在起应用前显式断言数据目录（见 `test/test_cookie_helper.py` 的 `_assert_isolated()`）。
- 后端遍布模块级单例（`api/deps.py` 的 `_manager`、`ws.py` 的环形缓冲与客户端表、
  `update.py` 的 docker 探测缓存、`plugin.py` 的 `_install_lock`），测试要自行重置。
- `PluginManager.load_all` 是**增量**的：目录删掉后条目仍在，调用方需显式
  `pm._plugins.pop(...)`。
- `register_routes` 是鸭子类型（不在 `Plugin` ABC 上），靠 `hasattr` 判断。
- 插件 `initialize` 抛异常时实例**不会**被丢弃——路由照常可用，`last_error` 记原因，
  `enabled=False`。不要据此以为插件已卸载。
- 插件 UI 路由按账户挂载为 `/api/accounts/{id}/plugin/{name}/ui`，且在认证中间件里被
  **匿名放行**（`<img>` 等无法携带 Authorization 头）。挂载时需先摘掉 SPA 兜底路由、
  插完再挂回，否则 Starlette 的顺序匹配会把 UI 请求吞进 SPA。
- `AccountRecord.expired` 是裸 UTC 比较，且 `_parse_expires` 对「永久」和「格式损坏」
  都返回 `None`——判断前先看 `is_permanent`。
- `AccountRecord` 刻意**不持有 Cookie**：私有 Cookie 落在该账户自己的 `server_state.json`，
  公共 Cookie 存在 `panel.json` 并在保存时强制降权为仅发消息。
