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

`test/` 下几乎都是**独立脚本**，逐条直接跑，输出 `PASS n: ...`：

```bash
.venv/Scripts/python.exe test/test_account_manager.py
```

两种写法都有，都能直接跑，别按其中一种去推断另一种坏了：多数带
`if __name__ == "__main__":` 守卫，另有 8 个（`test_compensate_accounts.py`、
`test_config_write_guard.py`、`test_default_password.py`、`test_live_binding.py`、
`test_live_unavailable.py`、`test_plugin_install_flow.py`、`test_server_broadcast.py`、
`test_update_notify.py`）**在顶层直接执行**，没有守卫。
新增测试请带守卫。

`pytest test/` 不可用：`pyproject.toml` 声明了 `asyncio_mode = "auto"`，但 dev 依赖里没有
`pytest-asyncio`，异步用例会报 "async def functions are not natively supported"。
`test_license_store.py` 是唯一 pytest 风格的纯同步用例。

**一律用 `.venv/Scripts/python.exe`**（Python 3.14）——本机 `python` 是 Windows Store
占位程序，无输出、退出码 49，会静默吞掉命令。Windows 控制台是 GBK，bash 里中文日志显示为
乱码属编码问题，看 `PASS`/`FAIL` 标记即可。

⚠️ GBK 控制台还会**让本来通过的测试看起来是失败的**：
`PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe test/xxx.py` 可以消除。
`test_changelog_popup.py` 就属于这种——不加这个变量会报
`UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f389'`，
加了就全绿。判断一个测试是不是真坏了，先加上这个变量再下结论。

#### 写新测试

照 `test/test_cookie_helper.py` 的头部抄，顺序**不能**换：

1. `os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(...)`——必须在 import 应用之前；
2. `sys.path.insert` 依次加 `../src`、`../web/backend`、`..`；
3. `import web.backend.main as backend`；
4. 打桩/取状态用 `from api.routes import xxx`（见「陷阱」里的双模块对象）；
5. 起应用前调自己的 `_assert_isolated()` 断言数据目录真的指向临时目录。

走 `/api/update/settings` 或 `/api/config/log-level` 的测试会改到**仓库根真实的
`config.yml`**（它进了 git），必须备份 + `atexit` 还原，照 `test/test_update_notify.py` 写。

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

## 文档地图

改代码前先看对应文档——这几份都比本文件详细，且是设计意图的权威来源：

| 文件 | 内容 |
|------|------|
| `docs/TASKS.md` | **待办清单（924 行）**，见下 |
| `docs/interfaces/interface.md` | MIST 抽象接口规范，`src/interfaces/` 的逐条说明 |
| `docs/plugin/PLUGIN_DEV_GUIDE.md` | 插件开发指南（生命周期、配置、权限、声明式 UI） |
| `docs/plugin/PLUGIN_PLAN.md` | 待开发插件的设计草案 |
| `docs/web/README.md` | 面板前后端，含 admin / account 双角色分流设计 |
| `docs/build/BUILDING.md` | 构建与部署选型 |
| `README.md` | 面向用户的总体说明，含事件继承树全图 |

### docs/TASKS.md 是权威待办

> 编号约定：`S*` 安全 · `C*` 正确性与数据一致性 · `P*` 性能 · `Q*` 代码质量。

- **编号稳定**，可且应当直接用于沟通与提交信息，如 `fix(security): S1 插件解压 Zip Slip`。
- `🔍已复核` = 审查时已逐行走通代码链路并确认；**无标记者来自静态分析，动手前需再确认一次现场**。
- 文件开头列了组合风险（如 S1+S2+S4 串成完整攻击链），并给出「建议的推进顺序」——
  挑活时先读那一节，别按编号顺序闷头做。
- 修完一项记得回该文件勾选 `- [x]` 并更新「完成度总览」。

## 架构

### 分层

```
src/interfaces/   MIST 抽象接口层（契约，不含任何实现）
src/core/         Missevan 平台适配实现
web/backend/      FastAPI 面板后端
web/frontend/     React + TS + Tailwind 面板前端
plugins/          官方插件库（独立 git 仓库，只作安装源，不直接运行）
missevanbot/      另一位作者的 Go 版猫耳机器人，带独立 .git，与本项目无代码往来
```

`missevanbot/` 只是放在仓库里的参考实现（Go + Redis），Python 侧没有任何引用，
也不是 submodule。**不要**改它，也不要把它的文件混进提交。

### 磁盘布局

```
config.yml                     # 面板级配置（硬编码解析到仓库根）
data/panel.json                # 账户记录、公共 Cookie、授权码、默认插件
data/auth.json                 # 面板管理员凭据
data/tokens/                   # 登录令牌（一个 token 一个文件）
data/helper_tokens/            # 私有 Cookie 自助获取的一次性 token（json，带 state/expires）
data/_library_tmp/             # 插件库只读扫描用的临时 config/permissions/plugins 目录
data/update_state.json         # 在线更新运行时状态
data/accounts/{id}/
    server_state.json          # 运行时状态，键见下
    installed_plugins/{name}/  # 插件**源码副本**（从 plugins/ 拷来）
    config/{name}_config.json  # 插件配置
    permissions/{name}_permissions.json
    plugins/{name}/            # 插件数据（PluginDataManager 沙箱目录）
```

注意账户目录下 **`installed_plugins/` 是代码、`plugins/` 是数据**——名字反直觉。

`server_state.json` 的键（`src/core/server.py` 的 `_save_state`）：`enabled_plugins`、
`enabled_livestreams`、`livestreams`、`timer_interval`，以及条件写入的 `bot`
（`cookie` / `permissions` / `enabled`，另有 `saved_private_cookie`——从私有切到公共时
暂存的私人 Cookie，用于切回）和 `timer_messages`。`bot` 与 `timer_messages` 都只在
有值时才落盘。

### 插件：库 + 副本

「安装」= `copytree` 一份源码到账户目录，此后该账户独立运行。改插件库**不影响**已安装账户，
需在账户插件页点「更新」覆盖。

模块加载刻意**不**走 `import plugins.x.y`：`_import_plugin_module` 用
`mismiss_plugin_{sha1(abspath)[:12]}_{name}` 作模块名 + `spec_from_file_location`。
原因是账户的 `plugins/` 恰好是插件数据目录、且仓库 `plugins/` 是无 `__init__.py` 的 namespace 包，
按普通 import 会让多个账户共享同一份源码。

版本守卫：副本版本 `>=` 库版本即跳过，唯一实现收敛在 `_update_outdated_in_account`，
账户侧 `update_plugins_in_account` 与面板侧 `push_plugin_to_accounts` 共用。

「安装」与「启用」是两件事，由账户级开关 `AccountRecord.auto_enable_on_install`
（默认 `False`，落 `panel.json`，setter 是 `set_auto_enable_on_install`）决定装完是否顺手启用。

插件数据目录有一次**惰性迁移**：`get_plugin_data_dir` 每次被调用时，若新路径
`data/plugins/{name}/` 不存在而旧的 `data/{name}/` 在，就 `shutil.move` 过去
（`plugin_manager.py:1480`）。不是启动时一次性迁移——所以老部署第一次访问某插件
数据时才会搬，别在日志里看到「插件数据已迁移」以为启动流程重跑了。

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

⚠️ 「注册顺序」对**同一个 listener 内部**实为 **`dir(listener)` 顺序**，即方法名
**字母序**——不是源码里的书写顺序。想让同名 listener 的多个 handler 有确定先后，
显式写 priority，别靠排列方法定义的先后。

两个反直觉点：

- **异步 handler 无法 `cancel()`**——`async def` 的 handler 被 `create_task` 并发调度，
  派发循环早已跑完。需要「阻止传播」语义必须写成同步 handler。
- 跨房事件（`LiveCrossMessageEvent` / `LiveCrossGiftEvent`）与 `LiveMessageEvent` /
  `LiveGiftEvent` 是**兄弟而非父子**节点，监听本房弹幕的插件收不到对方直播间的事件。
  两者的「对方直播间」字段名方向相反：`origin_*`（弹幕来自）vs `target_*`（礼物送给）。
  要一次收下全部跨房事件就监听分组基类 `LiveCrossEvent`——它同样收不到本房事件。
  完整继承树见 `README.md` 的「事件继承树」。

### 定时消息

「插件消息 → 全局消息 → 房间消息」合并轮转，每 `timer_interval` 秒发一条。
插件消息**不落盘**（插件重启后自行重注册）、面板不可改删、轮转置顶，与普通消息
**共用同一个位置指针**——增删插件消息时 `_shift_positions` 同步挪指针，
保证指针始终指向同一条消息。`only_when_live=True` 的未开播时跳过且指针照常推进。

### 状态持久化与跨 worker

`server_state.json` 最后写入者获胜，**没有锁**。每次写前调 `_ensure_state_fresh()`
按 mtime 判断是否重读，避免陈旧 worker 复活已删除的对象；FastAPI 的账户级依赖
（`api/deps.py` 的 `require_account` / `require_active_account`）每个请求都会调用它。

**默认单 worker**：直播间连接、Bot 定时器、插件实例都是单实例资源，
多 worker 会导致连接重复与事件分裂。多 worker 同步代码保留但仅作兜底。

worker 数有三处来源，名字**每一层都不一样**，搜 `MISMISS_WORKERS` 或 `WORKERS` 都只命中一部分：

- 本地开发：`web/backend/main.py` 的 `main()` 里 `uvicorn.run(..., reload=True)`，
  **不传** `workers`（uvicorn 默认 1），无环境变量可调；
- Docker 宿主侧：`docker-compose.yml:64` 的 `WORKERS=${MISMISS_WORKERS:-1}`——
  **宿主编排层的变量名是 `MISMISS_WORKERS`**；
- 容器内：compose 把它改名成 `WORKERS` 注入，`scripts/docker-entrypoint.sh` 用它跑
  gunicorn `--workers`；`Dockerfile:123` 另有 `ENV WORKERS=1` 兜底。

⚠️ 端口同理分两层，别混淆：宿主 **`MISMISS_HTTP_PORT`**（默认 18080，nginx 对外）
→ 容器内 gunicorn **8080**（`API_PORT`）。本地开发不走 Docker，直接就是 18080。

### 认证

Token 是**磁盘文件**（`data/tokens/{64位hex}`），不是内存字典——多 worker 下才能共享。
载荷 `{username, expires, role, account_id, must_change_password}`，TTL 30 天。
文件名即 token，因此校验强制 64 位 hex（WS 握手把 token 放在 query 参数里）。

角色：`admin` 全部可访问；`account` 只能访问 `/api/accounts/{自己的 id}/...`，
中间件按字符串解析路径判断（`web/backend/main.py`）。

默认账户密码 `user123`（`core/account/manager.py` 的 `DEFAULT_ACCOUNT_PASSWORD`），
前端 `AccountDialogs.tsx` 里有同一份明文兜底——**改一处必须改另一处**。
仍在使用默认密码的账户登录后强制先改密。

#### 私有 Cookie 自助获取

账户自助换 Cookie 的专用通道：

- `/api/accounts/{id}/helper/token` 签发一次性 token（落 `data/helper_tokens/`），
  `/helper/status` 轮询状态；
- `/api/helper/cookie` 是匿名回传端点——书签脚本跑在猫耳页面上，带不了面板令牌，
  只能靠 URL 里那个一次性 token 授权；
- token 单次有效、会过期、跨账户不可用；非法 token 一律返回**同一个 400**，
  不区分「不存在 / 过期 / 已用过」，避免成为探测接口；
- 回传体走 `_read_body_capped` 限长，写 Cookie 前过 `_lock_for(account_id)` 的账户级锁；
- 领取动作靠 `O_CREAT|O_EXCL` 建标记文件实现「一次性」（`_claim_helper_token`），
  token TTL 300 秒；失败次数上限是**全局**而非按 IP 的（防的是遍历而非单点爆破）。

⚠️ **兑换成功会把账户切成私有模式**（`bot_mode="private"`），不是只换 Cookie。
走的是 `switch_bot_mode(..., "private", ...)`——一步完成「换 Cookie + 改模式 + 落盘」，
少了切模式那步，从公共模式兑换出来的私人 Cookie 权限对不上。改这块别只改 Cookie 写入。

#### 匿名放行面（`main.py` 的中间件）

改这块前先看清楚一共有几类，它是认证的唯一软肋：

- `PUBLIC_PATHS`（**精确路径**）：`/api/auth/login`、`/api/auth/check`、
  `/api/auth/skip-first-login`、`/api/health`、`/api/helper/cookie`。
  注释写明刻意用精确路径而非前缀——前缀匹配是对未归一化路径做裸 `startswith`，口子太宽。
- `PUBLIC_PREFIXES`：`/api/auth/`、`/api/proxy/`。图片代理靠「域名白名单 + 内网拦截」
  收紧目标，而非鉴权（`<img>` 带不了 header）。
- 插件 UI：路径同时含 `/plugin/` 与 `/ui/` 就放行（详见「陷阱」）。
- 非 `/api/` 路径（静态文件）直接跳过。

`/api/helper/cookie` 是其中**唯一会写状态**的一个，其余都是只读或鉴权本身。
`account` 令牌除自己的账户路径外，只额外放行 `/api/health`、`/api/auth/`、`/api/proxy/`。

⚠️ 归属校验是 `if parts[3].isdigit()`——**非数字段直接落空不拦**
（`main.py` 里 `int(parts[3]) != int(info["account_id"])` 那段）。加账户级路由时
若路径第 4 段不是纯数字 id，别假定中间件替你挡了。

### 账户编号

`AccountRecord.id` 取自 `_next_account_id`（持久化在 `panel.json`，载入时会被
`max(现有 id) + 1` 抬高，因此**只增不减**）。它同时是账户数据目录名
（`data/accounts/{id}/`）与插件 UI 路由前缀的一部分。

⚠️ **占号必须排在全部校验之后**（`create_account`）。历史上它写在最前面，
于是用户名重复 / 密码太短 / Cookie 无效 / 启动失败都会白白吃掉一个号且
永远补不回来——表现就是列表里 #25 的下一个直接成了 #27。
任何在占号之后新增的失败路径，都必须调 `_release_account_id(aid)` 还回去
（它只在「仍是最后分配的那个」时回退，避免覆盖并发创建用掉的号）；
已经建好运行时再失败（如 Cookie 无效）要调 `_discard_failed_account(aid)`
整个撤掉，否则会留下「面板报失败、账户却存在」的幽灵记录。

`renumber_accounts()` 用于清掉历史遗留的空号，压紧为 1..N：

- 两阶段改目录名 —— `25→5` 会撞上仍然存在的 `5`，必须先全部挪到临时名再落位
- 必须先 `unmount_ui_routes()` 再 `shutdown()`：插件 UI 路由前缀里嵌着账户 id，
  而 `PluginManager.shutdown_all()` **只调 `terminate`、不摘路由**，指望不上
- 重启走 `start_all()`，顺带享受启动错峰
- 令牌里的 `account_id` 由 web 层负责改写（`auth.remap_token_account_ids`、
  `cookie_login.remap_helper_token_account_ids`）——不改的话账户角色用户
  要么被中间件拒掉，要么落到别人的账户上

### 到期停用

`AccountRecord.expired` 是裸 UTC 比较；`ExpiryScheduler` 每 60s 巡检，
到期走 `stop_for_expiry`：停 Bot、断开全部直播间、`suspend_all()` 插件
（注销 handler 但**保留 `enabled` 标记**，不是 disable），写 `paused_reason="expiry"`。
续期经 `resume_after_renew` 自动恢复。永久账户兑换授权码会被拒绝且不消耗该码。

### 出站节流（`core/network/throttle.py`）

面向猫耳平台的自我保护闸门，**所有**发往平台的请求都要过一次 `gate.acquire()`：
全进程共享一个最小请求间隔（`ratelimit.min_interval`，默认 0.1s ≈ 10 req/s），
平台报限流时进入**全局退避**（连续失败达阈值也触发），成功后解除。

- 出口在 `HTTPClient._request` 与 `DefaultCookieAPI.api` 两处 ——
  后者绕开了 HTTPClient（要读响应头而非 body），但**同样要过闸**，
  因为每次 WS 连接与重连都会调它。
- 存在意义是兜底：分散的单点修复（启动错峰、失败豁免、重连抖动）都可能被
  将来新增的代码绕过，只有这里是绕不过去的。
- 识别限流靠错误码/文案特征，默认表不含猫耳私有码；可用
  `MISMISS_RATE_LIMIT_MARKERS` 环境变量追加，不必改代码。
- 测试里请求被打了桩却仍要白等限速，会平白拖慢套件 ——
  测试开头设 `MISMISS_RATE_LIMIT_MIN_INTERVAL=0` 关掉等待
  （限速本身由 `test/test_outbound_pacing.py` 单独验证）。

**同一条链上的另外几道闸**（都在 `test_outbound_pacing.py` 里有断言）：

| 位置 | 行为 |
|------|------|
| `MissevanBot._safe_call` | 预期业务错误（`500030011`/主播休息）**不**触发 Cookie 校验；其余失败按 `_MIN_COOKIE_CHECK_INTERVAL` 节流 |
| `MissevanServer._ensure_bot_restored` | 恢复失败后进入 `_BOT_RESTORE_COOLDOWN`，不再被 8 秒轮询反复触发 |
| `MissevanLivestream._refresh` | `_REFRESH_MIN_INTERVAL` 内合并重复刷新（开机时会被连调三次）；管理员列表另有 `_ADMIN_LIST_TTL` 缓存，`force=True` 可穿透 |
| `AccountManager.start_all` | 账户之间 `ratelimit.startup_stagger` 随机错峰 |
| `MissevanBot._run_timer` / `_reconnect` | 定时消息与 WS 重连都加抖动；重连「成功即清零」已改为**稳定连上 `_STABLE_CONNECTION_SECONDS` 才清零**，否则秒断秒连的退避会永远停在 2 秒下限 |

⚠️ 改这些默认值前先读 `docs/TASKS.md` 里对应的行——它们的取值都是为了压住
「平台限流 → 请求更多 → 限流更紧」的正反馈，调小会让风控复发。

### 更新流程

`update:` 段落在**仓库根 `config.yml`**，运行时状态在 `data/update_state.json`。

**更新是后台执行的**：`/api/update/apply` 与 `/rollback` 取到 `_update_task` 后
立刻返回 202，前端轮询 `GET /api/update/status`。别改回同步——原先整个流程
（下载 200MB+ → 校验 → 解压 → `docker load`）都挂在一个 HTTP 请求里，
超过 nginx `proxy_read_timeout` 就被 504 掐断，而后端还在正常干活，
表现为「文件下载了但更新没生效」。所有阻塞调用一律 `asyncio.to_thread`。

进度写在 `update_state.json` 的 `apply` 键，**必须用 `_patch_update_state` 读-改-写**：
`_save_update_state` 是整表覆盖，直接调会冲掉同一文件里的 `backup_dir` / `notify_pending`。
启动时 `mark_interrupted_if_running()` 把残留的 `running` 判为中断
（Docker 重建与 uvicorn reload 都会换进程，所以运行的进程没了就是中断）。

重建的一次性容器输出写到 `<部署目录>/logs/update-recreate.log`。派发前会探测
`mismiss-online-update` 是否仍在运行，**在跑就不杀**——杀掉会把栈留在半重建状态。
Docker 路径：校验部署包（须含 `docker-compose.yml` + 真实 `docker save` 归档）→
备份到 `.mismiss-backup` → 解压（跳过 `config.yml` / `.env`）→ `docker load` →
派发**一次性容器**在宿主执行 compose 重建。重建必须由独立容器执行——在应用容器内
直接跑 compose 会杀掉执行中的进程。`notify_before` 在下载后、写盘前发送；
`notify_after` 由**下一个进程**在 `lifespan` 里补发。

`notify_after` 走 `broadcast_to_livestreams`，而**每次重启都会触发一轮**——
这正是历史上把平台请求打爆的路径之一，改更新流程时留意别把它变成无节制的扇出。

### 环境变量

全部散落在各处读取，没有集中定义，改名前先全局搜一遍：

| 变量 | 默认 | 作用 |
|------|------|------|
| `MISMISS_DATA_DIR` | `data` | 数据目录。`web/backend/main.py:75`、`api/routes/auth.py`、`api/routes/config.py` 各自解析 |
| `MISMISS_HOME` | `sys.executable` 所在目录 / `os.getcwd()` | 部署根目录。`deploy.sh` 写进部署目录 `.env`，在线更新靠它定位宿主路径 |
| `MISMISS_BUNDLE` | `sys._MEIPASS` | PyInstaller 打包态的资源根，前端产物从它下面找 |
| `MISMISS_VERSION` | 读 `pyproject.toml` | Docker 构建时 `--build-arg` 注入镜像，更新页展示 |
| `MISMISS_PROD` | 无 | `scripts/deploy.sh` 写进 systemd unit，标记生产模式 |
| `MISMISS_WORKERS` | `1` | Docker **宿主侧**：compose 读取后改名 `WORKERS` 注入容器 |
| `WORKERS` | `1` | Docker **容器内**：gunicorn worker 数（`Dockerfile:123` 兜底） |
| `MISMISS_HTTP_PORT` | `18080` | Docker 宿主侧：nginx 对外端口（容器内是 8080） |
| `API_PORT` | `8080` | Docker 容器内：gunicorn 监听端口 |

⚠️ `MISMISS_DATA_DIR` / `MISMISS_HOME` 是在 **import 期**就被解析成模块级常量的
（`auth.py:_DATA_ROOT`、`cookie_login.py:_HELPER_TOKEN_DIR`），测试里必须在
`import web.backend.main` **之前**设好，晚设就隔离不掉了。

### 命令系统

与事件系统**并列**的第二条分发路径，专收文本指令。插件在方法上标
`@command("歌单", alias=[...], scope=Scope.LIVEMESSAGE)`，`CommandRouter` 扫描实例后
注册一个共享的 `_CommandDispatchListener`。

- 报文格式 `<指令名> [arg1] [arg2] ...`，`shlex.split` 切分；参数按**位置**对形参，
  按注解转换（支持 `str` / `int` / `float` / `bool`，其余保持字符串），`*args` 吃剩余全部，
  缺参但有默认值则取默认值，否则 `TypeError`。
- 指令名冲突在注册时直接抛 `ValueError`（不覆盖），别名一起占用命名空间。
- 匹配失败静默忽略，且**不 `cancel()` 事件**——同一条弹幕仍会流到其他
  `LiveMessageEvent` handler。
- `Scope.PRIVATEMESSAGE` 已定义未实装，只有 `LIVEMESSAGE` 真正生效。
- 路由实例由 `AccountManager` 建好交给 `PluginManager`，随插件 load / unload / reload
  自动注册与注销；`data/_library_tmp/` 那套库级 PM 不带 router（库只读元数据、不跑插件）。

⚠️ **`@command` 方法必须是同步的**。派发处是同步 handler，直接 `entry.method(*args)`，
没有任何 coroutine 处理——写成 `async def` 只会返回一个没人 await 的协程，
表现为「指令毫无反应且不报错」。需要发消息就在方法里
`asyncio.get_running_loop().create_task(...)`（照 `plugins/song_list/main.py`）。

### 日志

loguru：`logs/bot_{date}.log`（10MB 轮转 / 保留 7 天）+ `error_{date}.log` + stderr，
`core.logging` 在 import 时自动初始化。

⚠️ `error_{date}.log` 的 retention 传的是 **`retention * 2`**（`core/logging.py:289`），
默认下就是字符串 `"7 days7 days"`——loguru 按两个匹配解析，实际约 **14 天**。
这是有意留的（错误日志留久点），但改 `retention` 格式时要知道它会被重复拼接。WS 日志流的环形缓冲（10000 条）与 200ms 批量推送
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

- ⚠️ **聚合路径必须保证「单个账户异常不扩散」**（`manager._account_snapshot`
  是唯一的公共出口，账户列表 / 总览 / 服务状态全走它）。

  `MissevanLivestream.creator` 在直播间**未 join** 时**直接抛**
  `CoreApiException`，而 `creator_name` / `creator_id` / `medal` 都是它的
  转发属性——裸读一个就能让整页 500。线上踩过：平台风控（HTTP 418）导致
  账户集体起不来、直播间一直没 join，面板三个接口一起挂，整页打不开。

  这类字段一律走 `_safe_room_attr(room, name, default)`；`_safe_creator_intro`
  早就是这个写法，但当初只覆盖了它自己那一个字段。**新增字段时照抄这个模式**。

  同一条链上还有个更隐蔽的教训：`PluginLibraryPage` 用
  `Promise.all([fetchLibraryPlugins(), fetchAccounts()])` 把两个**互不依赖**的
  请求绑死，再配 `catch { /* ignore */ }`。账户接口 500 → 插件列表也变成空 →
  错误被吞 → 界面显示「插件库为空」。**真实情况是「另一个接口挂了」，界面却
  说「你没装插件」**，排查时被这个假象带偏过一轮。→ 用 `allSettled` 各自结算，
  并且**不要吞掉错误**。

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
