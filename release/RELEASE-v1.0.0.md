# 🎉 MisMiss v1.0.0 — MIST 参考实现正式发布

<div align="center">

**MIST 标准实现 · 猫耳FM 直播场控机器人框架**

[![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-AGPL--3.0-orange?logo=gnu)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Code Style](https://img.shields.io/badge/Code%20Style-ruff-purple?logo=ruff)](https://docs.astral.sh/ruff)
[![Type Check](https://img.shields.io/badge/Type%20Check-mypy-informational?logo=python)](https://mypy-lang.org)

</div>

---

## 📖 关于本版本

**MisMiss** 是 [MIST](https://github.com/dikxingmengya/MIST) 直播场控机器人标准在 **Missevan（猫耳FM）** 平台的参考实现。MIST 定义了一套完整的抽象接口规范——涵盖实体模型、事件系统、直播间管理、机器人操作与插件框架——MisMiss 在此基础上提供了高性能的异步实现。

核心设计理念：**面向接口，事件驱动**。你只需实现一个监听器类即可响应开播、下播、弹幕、礼物、关注等直播事件；同时通过统一 API 发送消息和赠送礼物。更换直播平台时，仅需替换实现层，业务代码无需修改。

v1.0.0 是 MisMiss 的首个正式版本，提供了从接口定义、核心实现、插件系统到 Web 控制台的完整闭环，是对 MIST 规范的一次完整落地。

---

## ✨ 核心特性

- 🖥️ **Web 控制台** — React + TypeScript + Tailwind CSS 现代化管理面板，完全替代 CLI
- 📐 **MIST 标准兼容** — 严格遵循 MIST 接口规范，跨平台复用业务逻辑
- 🧩 **清晰的分层架构** — 接口层（`interfaces`）定义契约，核心层（`core`）负责实现
- 🔌 **插件系统** — 全生命周期管理：加载/启动/停止/重载/安装/卸载；`_conf_schema.json` 配置自动注入默认值；Server 自动分配权限；`requirements.txt` 自动安装依赖；插件专属 `data/{name}/` 数据目录
- ⚡ **事件驱动模型** — 基于 MRO 的事件分发，支持按事件类型继承树精确路由
- 🔒 **双层权限控制** — `BotPermission` Flag 位权限（5 个维度），插件级权限自动分配、逐项可调、执行时实时拦截校验
- 💬 **优先级消息队列** — 消息按优先级排序发送，后台异步消费，100ms 自动限流
- 🔄 **WebSocket 长连接** — Brotli 解压、30s 心跳维持、指数退避自动重连（最多 5 次）
- 💾 **状态持久化** — Server 启动自动恢复 Bot、直播间和插件状态，修改时即时保存
- 🔐 **登录认证** — SHA-256 哈希存储，首次登录强制修改默认密码
- 📝 **日志系统** — 基于 loguru，实时 WebSocket 推送至 Web 控制台，虚拟滚动万条无卡顿
- 🧪 **完整类型标注** — mypy 严格模式，所有公开接口均有完善 docstring

---

## 🏗️ 架构概览

MisMiss 严格遵循 MIST 接口规范，采用 **接口层（Interface）→ 核心层（Core）** 的双层架构，辅以独立的插件目录：

```
plugins/  ──  插件目录
═══════════════════════════════════════════════════════
  example_plugin/
  ├── main.py             # 插件入口（继承 Plugin）
  ├── metadata.yaml       # 元数据（必须）
  ├── _conf_schema.json   # 配置 schema + 默认值（可选）
  ├── requirements.txt    # 依赖声明（可选）
  ├── README.md           # 说明文档（可选）
  └── CHANGELOG.md        # 更新日志（可选）

interfaces/  ──  抽象接口层（MIST 标准）
───────────────────────────────────────────────────────

  Entity（实体）       Event（事件）          Service（服务）
  ───────────────      ──────────────         ──────────────────
  User                 Event                  Livestream
  ├─ LiveUser          ├─ Listener            LivestreamManager
  │  └─ Creator        ├─ EventManager        Bot
  Gift                 │  └─ EventBus         Server
  Medal                └─ @event_handler      BotPermission
  Question
                       Plugin
                       ├─ Plugin (ABC)
                       └─ PluginMetadata

core/  ──  核心实现层（Missevan 适配）
───────────────────────────────────────────────────────

  bot/                 livestream/           network/
  ────────             ──────────────        ────────────
  MissevanBot          MissevanLivestream    HTTPClient
  （优先级队列）        （WS 事件路由）        LiveWebSocket
                                             7 个 API 端点

  models/              events/               server.py
  ────────             ──────────────        ──────────
  用户·礼物·勋章       EventBus              持久化调度器
  6 种事件数据类       （MRO 分发）

  plugin/
  ─────────────
  PluginManager            # 全生命周期管理
  PluginConfigManager      # 配置读写 + schema 默认值
  PluginPermissionManager  # 权限自动分配 + 持久化
```

### 事件继承树

事件分发按 **MRO**（方法解析顺序）遍历：监听 `LivestreamEvent` 可收到所有直播间子事件；监听 `LiveMessageEvent` 则仅收到弹幕。

```
Event (ABC, 标记)
 └── LivestreamEvent (ABC)      ← 直播间事件基类
      ├── LiveOpenEvent          ← 开播
      ├── LiveCloseEvent         ← 下播
      └── LivestreamUserEvent    ← 用户事件基类
           ├── LiveJoinEvent     ← 用户进入
           ├── LiveFollowEvent   ← 关注直播间
           ├── LiveMessageEvent  ← 弹幕消息  (+ message)
           └── LiveGiftEvent     ← 赠送礼物  (+ gift)
```

---

## 🔌 插件系统详解

插件系统是 v1.0.0 的核心交付物之一，提供从加载到卸载的完整生命周期管理。

### 生命周期

| 阶段 | 方法 | 说明 |
|------|------|------|
| 加载 | `PluginManager.load_all()` | Server 启动时自动扫描 `plugins/`，注入 config 和 data_dir |
| 启动 | `start_plugin(name)` | 注册到事件总线，移除禁用标记 |
| 停止 | `stop_plugin(name)` | 取消事件注册，调用 `terminate()`，保留实例和文件 |
| 重载 | `reload_plugin(name)` | 终止 → 清除模块缓存 → 重新检测依赖 → 重新加载（热更新） |
| 安装 | `install_plugin(url=…)` | 从 URL 或本地路径安装，自动解压、安装依赖、加载 |
| 卸载 | `uninstall_plugin(name, …)` | 终止插件，可选删除配置、数据目录及插件目录 |

### 配置管理

插件在目录下放置 `_conf_schema.json` 定义配置项，框架自动完成：

1. **解析 schema** → 提取每个字段的 `type` 与 `default`
2. **生成默认值** → `string→""`、`int→0`、`float→0.0`、`bool→false`、`array→[]`
3. **深度合并** → 已持久化的值覆盖默认值
4. **注入插件** → 通过 `initialize(config)` 参数传入 `MissConfig` 实例

```json
{
    "welcome_enabled": {
        "type": "boolean",
        "default": true,
        "description": "是否在新用户进入时发送欢迎消息"
    },
    "max_message_length": {
        "type": "int",
        "default": 500,
        "description": "弹幕最大显示长度"
    },
    "gift_threshold": {
        "type": "float",
        "default": 100.0,
        "description": "礼物价值过滤阈值"
    }
}
```

### 权限管理

插件**无需声明权限文件**——Server 自动分配默认权限（仅 `SEND_LIVESTREAM_MESSAGE`），管理员可通过 API 逐项授予或收回。框架通过 `contextvars` 追踪当前执行插件，在 Bot 的 4 个敏感方法中**实时校验**，权限不足时抛出 `CorePermissionException("插件 'xxx' 缺少 SEND_GIFT 权限")`。插件权限自动收敛至 Bot 能力上限，杜绝越权。

```python
from interfaces.bot import BotPermission

# 五维位标志权限模型
permissions = (
    BotPermission.SEND_LIVESTREAM_MESSAGE   # 发送弹幕
    | BotPermission.SEND_GIFT               # 赠送直售礼物
    | BotPermission.SEND_BACKPACK_GIFT      # 赠送背包礼物
    | BotPermission.SEND_PRIVATE_MESSAGE    # 发送私信
    | BotPermission.EXPOSE_COOKIE           # 获取 Cookie（敏感）
)
```

### 其他能力

- **独立数据目录** — `data/{plugin_name}/` 自动创建，`self.data_dir` 直接使用，卸载时可选择清理
- **依赖自动安装** — 检测 `requirements.txt`，自动 `pip install` 缺失包，支持配置 PyPI 镜像源
- **失败插件追踪** — 加载失败的插件记录错误信息与元数据，可通过 `get_failed_plugins()` 查看、`retry_failed_plugin()` 重试

---

## ⚡ 事件驱动模型

### 事件类型一览

| 事件类 | 触发时机 | 特有属性 |
|--------|---------|---------|
| `LiveOpenEvent` | 直播间开播 | — |
| `LiveCloseEvent` | 直播间下播 | — |
| `LiveJoinEvent` | 用户进入直播间 | — |
| `LiveFollowEvent` | 用户关注直播间 | — |
| `LiveMessageEvent` | 收到公屏弹幕 | `message: str` |
| `LiveGiftEvent` | 收到礼物 | `gift: Gift` |

### 实体模型

| 实体 | 关键属性 |
|------|---------|
| `User` | `name`, `id`, `introduction`, `icon_url` |
| `LiveUser` | 继承 User + `livestream`, `medal`, `is_admin` |
| `Creator` | 继承 LiveUser + `is_online`, `room_medal` |
| `Gift` | `name`, `id`, `price`, `num`, `lucky_gift`, `is_lucky_gift` |
| `Medal` | `name`, `level` |
| `Question` | `user`, `text`, `price`, `question_id` |

### 优先级消息队列

```python
# priority 越大越优先发送
await bot.send_livestream_message(12345, "VIP 消息", priority=100)
await bot.send_livestream_message(12345, "普通消息", priority=0)
```

后台异步消费者逐条发送，间隔 100ms 防平台限流；Cookie 过期时自动清空队列。

---

## 🌐 Web 控制台

基于 **React 18 + TypeScript + Tailwind CSS + Vite** 构建，FastAPI 驱动后端，单端口或前后端分离两种部署模式：

- **仪表盘** — 服务状态、Bot 在线数、直播间状态一目了然
- **Bot 管理** — 多账号、Cookie 认证、状态切换
- **直播间管理** — 房间信息、WebSocket 连接监控
- **插件管理** — 可视化安装/卸载/启用/禁用、动态配置表单、权限勾选、README 预览
- **实时日志** — WebSocket 日志流推送，等级过滤、关键词搜索，虚拟滚动万条不卡
- **服务端设置** — 运行时配置调整，即时生效

---

## 📦 预置插件

v1.0.0 随发布附带 5 个可直接使用的参考插件：

| 插件 | 版本 | 功能 |
|------|------|------|
| `welcome` | v1.1.0 | 新用户进入自动欢迎（拼音昵称、首次到访识别、房间过滤） |
| `gift_thanks` | v1.0.1 | 礼物自动答谢（猫粮特殊处理、礼物价值展示） |
| `follow_thanks` | v1.0.0 | 关注自动答谢（拼音昵称、首次关注识别、冷却机制） |
| `song_request` | v1.0.0 | 点歌系统（队列管理、主持人完成/删除操作） |
| `example_plugin` | v1.1.3 | 完整功能演示（配置、权限、数据目录、@command 指令） |

---

## 🚀 快速开始

### Server 完整编排（Python API）

```python
import asyncio
from core import MissevanServer
from interfaces.bot import BotPermission

async def main():
    server = MissevanServer()
    await server.start()

    # 创建机器人
    bot = await server.create_bot(
        cookie="你的Cookie",
        permissions=BotPermission.SEND_LIVESTREAM_MESSAGE
                   | BotPermission.SEND_GIFT
                   | BotPermission.SEND_BACKPACK_GIFT,
    )

    # 添加直播间
    live = server.add_livestream(live_id=12345)

    # 注册监听器并进入直播间
    live.register_new_event(MyListener())
    await live.join()
    await live.send_message("大家好！")

asyncio.run(main())
```

### 启动 Web 控制台

```bash
git clone https://github.com/MisMissDev/MisMiss.git
cd MisMiss
pip install -r requirements.txt
python -m web.backend.main

# 或一键启动
# Windows: start.bat
# Linux/macOS: bash start.sh
```

Web 控制台默认监听 `http://localhost:18080`，默认用户名密码均为 **MisMiss**。

---

## 🐳 部署方式

| 方式 | 适用场景 |
|------|---------|
| 源码运行 | 开发调试，Python 3.13+ / Node.js 20+ |
| Docker | 生产部署，多阶段构建，镜像体积优化 |
| Docker Compose | 一键编排，数据卷持久化，开箱即用 |
| PyInstaller EXE | Windows 独立可执行文件，无需 Python 环境 |
| pip Wheel | 标准 Python 包分发 |

---

## 📋 技术栈

| 层级 | 技术选型 |
|------|---------|
| 后端语言 | Python 3.13+ |
| 后端框架 | FastAPI + httpx + websockets |
| 前端框架 | React 18 + TypeScript + Tailwind CSS + Vite |
| 实时通信 | WebSocket（Brotli 压缩） |
| 构建分发 | PyInstaller / Docker / pip Wheel |
| 代码质量 | ruff（lint）+ mypy（strict type check）+ pytest |
| 许可证 | AGPL-3.0 |

---

## 🔮 未来规划

- **P0 — 高优先级**：`LivestreamManager` 多直播间并发管理、`Question` 问答类事件支持、`send_private_message` 私信能力补全
- **P1 — 中优先级**：自动化测试套件、插件市场（中心化索引与一键安装）、Web 控制台国际化（英文支持）
- **P2 — 低优先级**：更多平台适配（基于 MIST 接口扩展）、Prometheus 性能监控、移动端体验增强

---

## 📄 许可证

MisMiss 采用 **GNU Affero General Public License v3.0（AGPL-3.0）** 许可证：

- ✅ 自由使用、修改和分发
- ✅ 可用于商业目的
- ⚠️ 通过网络提供服务（含修改版）须公开源代码

> MisMiss 是 [MIST](https://github.com/dikxingmengya/MIST) 直播场控标准的一部分。MIST 定义了跨平台的直播机器人接口规范，MisMiss 作为 Missevan 平台的适配实现，遵循相同的接口契约。欢迎贡献其他平台的实现。

---

## 🙏 致谢

感谢所有为本项目做出贡献的开发者以及 MIST 标准的早期采用者。v1.0.0 是一个起点——我们期待社区的力量让 MisMiss 和 MIST 生态走得更远。

---

<div align="center">

**MisMiss** — MIST 标准 · 猫耳FM 实现 · 让直播机器人开发变得优雅 🎧

</div>
