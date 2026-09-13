# MisMiss 待实现任务清单

> 基于 MIST 接口规范与当前实现对比，按重要/紧急程度分级。
> 最近校对：2026-09-13（对照 dev 分支，v1.2.0 之后）

---

## 🔴 P0 — 接口已定义，零实现

- [ ] **LivestreamManager 核心实现**
  - 接口：`src/interfaces/livestream/livestream_manager.py`
  - 需实现：`livestream_list` / `get_livestream` / `get_livestream_if_absent` / `register_new_livestream` / `unregister_livestream`
  - 现状：全仓搜索无任何具体子类。`MissevanServer` 内部用 `dict[int, Livestream]` 自行管理，未走该接口
  - 影响：接口文档已收录，README 架构图已展示，但实际不可用

- [x] **Question 实体 dataclass** ✅ 已完成
  - `src/core/models/question.py` 定义 `LiveQuestion(Question)`，
    实现 `livestream` / `user` / `question_id` / `text` / `price` /
    `status` / `created_time` / `updated_time` / `likes` / `liked` 全部属性
  - 事件侧 `LiveQuestionEvent` + WS `question:ask` 路由均已接通

- [ ] **私信功能 `send_private_message`**
  - 接口：`src/interfaces/bot/bot.py` → `send_private_message(user_id, message)`
  - 权限位：`BotPermission.SEND_PRIVATE_MESSAGE` 已定义
  - 现状：`src/core/bot/mis_bot.py:372` 定义，`:386` 直接 `raise NotImplementedError("私信功能尚未实现")`
  - 依赖：需先研究 Missevan 私信 API 端点

---

## 🟡 P1 — 已有骨架，逻辑不完整

- [x] **Plugin 插件系统** ✅ 已完成
  - 插件管理器：启动/停止/重载/安装/卸载/配置/权限/更新 完整生命周期
  - `Plugin` 基类：`initialize()` / `terminate()` / `on_enable()` 生命周期钩子，config 注入
  - `PluginMetadata`：完整元数据支持（`plugin_id`、`short_desc`、`repo`、`display_name`）
  - 配置管理：`_conf_schema.json` 自动识别 + 默认值生成 + 深度合并
  - 权限管理：自动分配默认权限 + 逐项修改 + contextvars 运行时拦截（Bot 权限为天花板）
  - 依赖管理：`requirements.txt` 自动安装
  - 失败插件追踪 + 重试机制
  - 数据目录：`data/accounts/{id}/plugins/{name}/` 专属存储 + 路径沙箱
  - 声明式 UI：`_ui_schema.json` + `PluginUI.tsx` 渲染
  - 详见 `src/core/plugin/` 目录与 `docs/plugin/PLUGIN_DEV_GUIDE.md`

- [ ] **插件热重载（开发模式）**
  - 使用 `watchfiles` 监听 `plugins/` 目录变化
  - 文件修改时自动 reload 对应插件
  - 通过环境变量 `MISMISS_DEV=1` 启用
  - 复杂度：中

- [x] **插件 KV 存储** ✅ 已完成
  - `PluginDataManager` 提供 `read_json/write_json/read_text/write_text/delete/exists` 方法
  - 注入为 `self.data` 属性，所有路径锁定于 `data/accounts/{id}/plugins/{name}/`
  - 详见 `src/core/plugin/data_manager.py`

- [ ] **插件市场集成**
  - 对接远端 registry 获取可用插件列表
  - 一键安装/更新
  - 复杂度：高

- [ ] **插件 i18n 国际化**
  - 支持插件提供多语言翻译文件（`i18n/zh-CN.json` 等）
  - 框架根据用户语言设置自动选择
  - 复杂度：中

- [ ] **插件间依赖声明**
  - `metadata.yaml` 中声明 `depends_on: [other_plugin_name]`
  - 加载时检查依赖是否满足，缺失则报错
  - 卸载时检查是否有其他插件依赖自己
  - 复杂度：中

- [x] **插件沙箱隔离** 🟡 路径沙箱已完成，venv 沙箱待定
  - ✅ 路径沙箱：`PluginDataManager._resolve()` 拒绝 `../` 逃逸和绝对路径
  - ⬜ venv 沙箱：每个插件独立 venv（复杂度：高，优先级低）

- [ ] **插件更新检测（远端）** 🟡 本地比对已完成
  - ✅ v1.1.0 起：面板对比「账户已安装副本版本 vs 插件库版本」，
    显示「可更新」徽标，并支持一键从库覆盖更新（保留启用状态与既有配置）
  - ⬜ 待办：对接远端 registry/marketplace 自动检测库本身是否落后
  - 复杂度：中

- [ ] ~~**Cookie 过期恢复策略**~~ — 已被 v1.1.0 的授权到期体系取代
  - 现在：`ExpiryScheduler` 60s 兜底 + 端点守卫，到期硬停用 Bot/直播间/插件；
    续期后自动恢复，失败原因记录在 `resume_error` 并展示在面板

- [ ] **开播/下播异步刷新失败处理**
  - `src/core/livestream/mis_livestream.py` — 内部监听器中 `create_task(_refresh())`
    失败时仅捕获 `RuntimeError` 后静默
  - 风险：无事件循环时异常被吞，creator 在线状态可能不更新
  - 建议：至少加 `log.warning`，或改为同步调用（如果 API 是轻量的）

---

## 🟢 P2 — 工程化完善

- [x] **测试体系搭建** ✅ 已完成
  - `test/test_account_manager.py` — 账户 CRUD / 持久化 / 到期停用 / 调度器
  - `test/test_account_api.py` — FastAPI TestClient 端到端（登录守卫 / 过期 403 / 授权码兑换）
  - `test/test_license_store.py` — 授权码生成与兑换规则 / 回滚；唯一可直接被 pytest 收集的文件
  - `test/test_cross_worker_sync.py` — 多 worker 状态同步（mtime 协调）
  - `test/test_timer_persist.py` — 定时消息持久化与 Cookie 轮换后存活
  - 注：除 `test_license_store.py` 外均为 `__main__` 驱动的独立脚本，需手动执行

- [x] **清理死代码** ✅ 已完成
  - 已删除：`core/bot/mis_bot.py` 的空 `if TYPE_CHECKING: pass` 块、
    重复定义的 `plugin_changelog` 路由、3 个无引用的前端组件
    （`InstallModal` / `RoomSelect` / `ReadmeModal`）、
    无引用的 `InlineLoader` 与 `DashboardResponse` / `ErrorResponse` / `WSLogMessage` schema

- [ ] **类型标注收窄**
  - 6 处 `# type: ignore` 集中在 JSON 反序列化（`json.load` / `resp.json` 返回 `Any`）
  - 可考虑用 `TypedDict` 或显式 `cast()` 替代 ignore
  - 另：`mypy src/` 尚有 4 处既有告警（`event_handler.py:25`、`plugin_manager.py:568/684/1518`）

- [ ] **README 示例代码对齐**
  - README 的 Python API 示例仍按单服务器模型书写，需改为 `AccountManager` 用法

---

## 🔵 已知遗留（v1.1.0 重构后）

- [ ] **插件自带 UI 路由为匿名可访问**
  - `/api/accounts/{id}/plugin/{name}/ui/*` 由 `PluginManager` 运行时注册，
    中间件对其放行（`main.py` 中按 `/plugin/` + `/ui/` 特征匹配）
  - 影响：未登录者可读取账户级插件 UI 数据（如点播单）
  - 收紧需要配套改动 `PluginUI.tsx` 的请求方式，属独立设计问题

- [ ] **图片代理白名单只能改配置文件**
  - `proxy.allowed_hosts` 已支持 `config.yml` 覆盖，但设置页尚未提供编辑入口

- [ ] **多 worker 部署**
  - 当前硬约束单 worker（`MISMISS_WORKERS=1`）——直播间连接、Bot 定时器、
    插件实例均为单实例资源；`_ensure_state_fresh()` 的同步机制仅作兜底

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
