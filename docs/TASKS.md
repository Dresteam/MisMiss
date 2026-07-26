# MisMiss 待实现任务清单

> 基于 MIST 接口规范与当前实现对比，按重要/紧急程度分级。

---

## 🔴 P0 — 接口已定义，零实现

- [ ] **LivestreamManager 核心实现**
  - 接口：`interfaces/livestream/livestream_manager.py`
  - 需实现：`livestream_list` / `get_livestream` / `get_livestream_if_absent` / `register_new_livestream` / `unregister_livestream`
  - 参考：`MissevanServer` 内部已有 `dict[int, Livestream]` 管理逻辑，可提取为独立 Manager
  - 影响：接口文档已收录，README 架构图已展示，但实际不可用

- [ ] **Question 实体 dataclass**
  - 接口：`interfaces/entity/question.py`
  - 属性：`livestream` / `user` / `question_id` / `text` / `price`
  - 影响：6 个实体中唯一缺失的，纯数据类，实现成本极低

- [ ] **私信功能 `send_private_message`**
  - 接口：`interfaces/bot/bot.py` → `send_private_message(user_id, message)`
  - 权限位：`BotPermission.SEND_PRIVATE_MESSAGE` 已定义
  - 现状：`core/bot/mis_bot.py:284` 直接 `raise NotImplementedError`
  - 依赖：需先研究 Missevan 私信 API 端点

---

## 🟡 P1 — 已有骨架，逻辑不完整

- [x] **Plugin 插件系统** ✅ 已完成
  - 插件管理器：启动/停止/重载/安装/卸载/配置/权限 七大功能
  - `Plugin` 基类：`initialize()` / `terminate()` 生命周期钩子，config 注入
  - `PluginMetadata`：完整元数据支持（`plugin_id`、`short_desc`、`repo`、`display_name`）
  - 配置管理：`_conf_schema.json` 自动识别 + 默认值生成 + 深度合并
  - 权限管理：`_permission.json` 权限 schema + 运行时配置
  - 依赖管理：`requirements.txt` 自动安装
  - 失败插件追踪 + 重试机制
  - 插件数据目录：`data/{plugin_name}/` 专属存储空间
  - 详见 `src/core/plugin/` 目录

- [ ] **插件热重载（开发模式）**
  - 使用 `watchfiles` 监听 `plugins/` 目录变化
  - 文件修改时自动 reload 对应插件
  - 通过环境变量 `MISMISS_DEV=1` 启用
  - 复杂度：中

- [x] **插件 KV 存储** ✅ 已完成
  - `PluginDataManager` 提供 `read_json/write_json/read_text/write_text/delete/exists` 方法
  - 注入为 `self.data` 属性，所有路径锁定于 `data/{plugin_name}/`
  - 详见 `src/core/plugin/data_manager.py`

- [ ] **插件市场集成**
  - 对接远端 registry 获取可用插件列表
  - 版本比对、一键安装/更新
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

- [ ] **插件更新检测**
  - 对比本地版本与远端 registry/marketplace 版本
  - 在 `list_plugins()` 中标记可更新状态
  - 复杂度：中

- [ ] **Cookie 过期恢复策略**
  - `core/server.py:304` — `_restore_bot()` 遇到过期 Cookie 仅 `log.warning`
  - 需实现：通知机制、状态清理、或延迟重试
  - 当前行为：静默失败，Bot 恢复后 `bot_available` 为 `False`，无用户感知

- [ ] **开播/下播异步刷新失败处理**
  - `core/livestream/mis_livestream.py:285-296` — 内部监听器中 `create_task(_refresh())` 失败时 `except RuntimeError: pass`
  - 风险：无事件循环时静默吞掉异常，creator 在线状态可能不更新
  - 建议：至少加 `log.warning` 或改为同步调用（如果 API 是轻量的）

---

## 🟢 P2 — 工程化完善

- [ ] **测试体系搭建**
  - 现状：`test/bot_demo.py` / `server_demo.py` / `event_demo.py` 仅为手动演示脚本
  - `requirements.txt` 已声明 `pytest` / `pytest-cov`，但无任何测试文件
  - 建议优先覆盖：
    - `EventBus` 注册/注销/分发（纯逻辑，不依赖网络）
    - 实体 dataclass 属性正确性
    - `BotPermission` Flag 位运算
    - `HTTPClient._check_success()` 响应校验

- [ ] **清理死代码**
  - `core/bot/mis_bot.py:30-31` — 空的 `if TYPE_CHECKING: pass` 块

- [ ] **类型标注收窄**
  - 6 处 `# type: ignore` 集中在 JSON 反序列化（`json.load` / `resp.json` 返回 `Any`）
  - 可考虑用 `TypedDict` 或显式 `cast()` 替代 ignore

- [ ] **README 示例代码对齐**
  - README 快速开始部分未演示 `LivestreamManager` 用法
  - `MissevanServer` 实际是 `add_livestream()` 而非 `get_livestream()` 模式
  - 待 Manager 实现后统一更新

---

## 📊 完成度总览

| 模块 | 接口定义 | 核心实现 | 测试 | 完成度 |
|------|:------:|:------:|:----:|:-----:|
| User / LiveUser / Creator | ✅ | ✅ | ❌ | 70% |
| Gift / Medal | ✅ | ✅ | ❌ | 70% |
| Question | ✅ | ❌ | ❌ | 30% |
| Event 系统 (6 种事件) | ✅ | ✅ | ❌ | 70% |
| EventManager / EventBus | ✅ | ✅ | ❌ | 70% |
| Livestream | ✅ | ✅ | ❌ | 70% |
| LivestreamManager | ✅ | ❌ | ❌ | 30% |
| Bot (消息/礼物/背包) | ✅ | ✅ | ❌ | 70% |
| Bot (私信) | ✅ | ❌ | ❌ | 30% |
| Server | ✅ | ✅ | ❌ | 75% |
| Plugin 系统 | ✅ | ✅ | ❌ | 85% |
| 日志系统 | — | ✅ | ❌ | 80% |
| WebSocket / HTTP | — | ✅ | ❌ | 80% |
