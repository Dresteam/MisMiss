# 🎙️ MisMiss

<div align="center">

**MIST 标准实现 · 猫耳FM 直播场控机器人框架**

[![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-AGPL--3.0-orange?logo=gnu)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Code Style](https://img.shields.io/badge/Code%20Style-ruff-purple?logo=ruff)](https://docs.astral.sh/ruff)
[![Type Check](https://img.shields.io/badge/Type%20Check-mypy-informational?logo=python)](https://mypy-lang.org)

</div>

---

## 📖 简介

**MisMiss** 是 [MIST](https://github.com/dikxingmengya/MIST) 直播场控机器人标准在 **Missevan（猫耳FM）** 平台的参考实现。MIST 定义了一套完整的抽象接口规范——包括实体模型、事件系统、直播间管理、机器人操作和插件框架——MisMiss 在此基础上提供了高性能的异步实现。

核心设计理念：**面向接口，事件驱动**。你只需实现一个监听器类，就能响应开播、下播、弹幕、礼物、关注等直播事件；同时通过统一 API 发送消息和赠送礼物。更换直播平台时，只需替换实现层，业务代码无需修改。

## ✨ 特性

- 📐 **MIST 标准兼容** — 严格遵循 MIST 接口规范，跨平台复用业务逻辑
- 🧩 **清晰的分层架构** — 接口层（`interfaces`）定义契约，核心层（`core`）负责实现
- 🔌 **插件系统** — 启动/停止/重载/安装/卸载 全生命周期；`_conf_schema.json` 配置自动注入默认值；Server 自动分配权限（对标 `BotPermission`）；`requirements.txt` 自动安装；插件专属 `data/{name}/` 数据目录
- ⚡ **事件驱动模型** — 基于 MRO 的事件分发，支持按事件类型继承树精确路由
- 🔒 **双层权限控制** — `BotPermission` Flag 位权限，敏感操作（如获取 Cookie）受 name-mangling 保护；插件级权限自动分配、可逐项修改，执行时实时拦截校验
- 💬 **优先级消息队列** — 消息按优先级排序发送，后台异步消费，自动限流
- 🔄 **WebSocket 长连接** — Brotli 解压、心跳维持、自动重连（指数退避）
- 💾 **状态持久化** — Server 启动自动恢复 Bot、直播间和插件状态，修改时自动保存
- 📝 **日志系统** — 基于 loguru，自动提取调用类名/方法名，支持多维度过滤
- 🧪 **完整类型标注** — mypy 严格模式，所有接口均有完善的 docstring

## 🏗️ 架构

```
plugins/  ──  插件目录
═══════════════════════════════════════════════════════
  example_plugin/
  ├── main.py             # 插件类（继承 Plugin）
  ├── metadata.yaml       # 元数据（必须）
  ├── _conf_schema.json   # 配置 schema（可选）
  ├── requirements.txt    # 依赖（可选）
  ├── README.md           # 文档（可选）
  └── CHANGELOG.md        # 更新日志（可选）

test/  ──  演示程序
═══════════════════════════════════════════════════════

interfaces/  ──  抽象接口层 (MIST 标准)
───────────────────────────────────────────────────────

  Entity (实体)        Event (事件)         Service (服务)
  ─────────────        ────────────         ───────────────
  User                 Event                Livestream
  ├─ LiveUser          ├─ Listener          LivestreamManager
  │  └─ Creator        ├─ EventManager      Bot
  Gift                 │  └─ EventBus       Server
  Medal                └─ @event_handler    BotPermission
  Question
                       Plugin
                       ├─ Plugin (ABC)
                       └─ PluginMetadata

core/  ──  核心实现层 (Missevan 适配)
───────────────────────────────────────────────────────

  bot/                 livestream/           network/
  ────────             ──────────────        ────────────
  MissevanBot          MissevanLivestream    HTTPClient
  (优先级队列)          Live (WS 事件路由)    LiveWebSocket
                                             7 个 API 端点

  models/              events/               server.py
  ────────             ──────────────        ──────────
  用户·礼物·勋章       EventBus              持久化调度器
  6 种事件数据类       (MRO 分发)

  plugin/
  ─────────────
  PluginManager            # 全生命周期管理
  PluginConfigManager      # 配置读写 + schema 默认值
  PluginPermissionManager  # 权限自动分配 + 持久化
```

### 事件继承树

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

事件分发按 **MRO** 遍历：监听 `LivestreamEvent` 可以收到所有直播间子事件；监听 `LiveMessageEvent` 则仅收到弹幕。

## 📦 安装

### 环境要求

- **Python** ≥ 3.13
- **依赖**：httpx · websockets · brotli · loguru · pyyaml

```bash
git clone https://github.com/MIST/MissMiss.git
cd MissMiss

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

## 🚀 快速开始

### 1. 启动机器人

```python
import asyncio
from core import MissevanBot
from interfaces.bot import BotPermission

async def main():
    bot = MissevanBot(cookie="你的Cookie")
    await bot.refresh()

    print(f"🤖 机器人上线: {bot.name} (ID: {bot.id})")

    # 发送消息到直播间
    await bot.send_livestream_message(live_id=12345, message="大家好~")

    # 赠送背包礼物
    await bot.send_livestream_backpack(live_id=12345, gift_id=100, num=3)

asyncio.run(main())
```

### 2. 监听直播间事件

```python
from interfaces import Listener, event_handler
from interfaces.event.livestream import (
    LiveMessageEvent, LiveGiftEvent, LiveOpenEvent,
)

class MyListener(Listener):
    """自定义事件监听器"""

    @event_handler
    def on_open(self, event: LiveOpenEvent) -> None:
        print(f"🔴 {event.livestream.room_name} 开播了！")

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        print(f"💬 [{event.livestream.room_name}] {event.user.name}: {event.message}")

    @event_handler
    def on_gift(self, event: LiveGiftEvent) -> None:
        gift = event.gift
        print(f"🎁 {event.user.name} 赠送了 {gift.num} 个 {gift.name}")
        print(f"   价值: {gift.price * gift.num} 电池")
```

### 3. 使用 Server 完整编排

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

    # 注册监听器
    live.register_new_event(MyListener())

    # 进入直播间（开始接收事件）
    await live.join()

    # 发送消息
    await live.send_message("大家好！")

asyncio.run(main())
```

### 4. 编写插件

插件继承 `Plugin`（本质是 `Listener`），使用 `@event_handler` 声明事件处理方法，放在 `plugins/` 目录下即可被 Server 自动加载。插件框架会自动注入配置、权限和数据目录。

**目录结构：**

```
plugins/
└── my_plugin/
    ├── metadata.yaml         # 插件元数据（必须）
    ├── main.py               # 插件入口（必须）
    ├── _conf_schema.json     # 配置 schema + 默认值（可选）
    └── requirements.txt      # 依赖（可选）
```

**metadata.yaml：**

```yaml
name: my_plugin
desc: 我的第一个插件
author: YourName
version: 1.0.0

# 可选字段
short_desc: 监听弹幕和礼物的示例插件
repo: https://github.com/YourName/my-plugin
display_name: 我的插件
```

**_conf_schema.json（可选）：**

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

**main.py：**

```python
import json
import os
from interfaces.plugin import Plugin
from interfaces.event import event_handler
from interfaces.event.livestream import LiveMessageEvent, LiveGiftEvent, LiveJoinEvent

class MyPlugin(Plugin):
    """我的第一个插件 —— 演示 config / permissions / data_dir 用法"""

    async def initialize(self) -> None:
        # self.config 已由框架自动注入（包含 schema 默认值）
        cfg = self.config or {}
        if cfg.get("welcome_enabled"):
            print(f"[{self.name}] 插件就绪 (plugin_id={self.plugin_id})")
        print(f"[{self.name}] 配置: {json.dumps(cfg, ensure_ascii=False)}")

        # self.permissions 由 Server 自动分配（对标 BotPermission）
        print(f"[{self.name}] 权限: {self.permissions}")

        # self.data_dir 是插件专属数据目录（自动创建）
        print(f"[{self.name}] 数据目录: {self.data_dir}")
        self._load_stats()

    async def terminate(self) -> None:
        # 保存数据到 data_dir
        self._save_stats()

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        cfg = self.config or {}
        max_len = cfg.get("max_message_length", 500)
        msg = event.message[:max_len]
        print(f"[MSG] {event.user.name}: {msg}")
        self._stats["messages"] += 1

    @event_handler
    def on_gift(self, event: LiveGiftEvent) -> None:
        total = event.gift.price * event.gift.num
        threshold = (self.config or {}).get("gift_threshold", 100.0)
        if total >= threshold:
            print(f"[GIFT] {event.user.name} 赠送 {event.gift.name} x{event.gift.num}")
        self._stats["gifts"] += 1

    @event_handler
    def on_join(self, event: LiveJoinEvent) -> None:
        self._stats["joins"] += 1

    def _load_stats(self):
        path = os.path.join(self.data_dir, "stats.json")
        try:
            with open(path) as f:
                self._stats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._stats = {"messages": 0, "gifts": 0, "joins": 0}

    def _save_stats(self):
        path = os.path.join(self.data_dir, "stats.json")
        with open(path, "w") as f:
            json.dump(self._stats, f)
```

Server 启动时会自动扫描 `plugins/` 并加载所有插件。你也可以通过 API 手动管理：

```python
# 查看所有插件
for p in server.plugins:
    print(f"{p.name} v{p.version} by {p.author}")
    print(f"  plugin_id: {p.plugin_id}")
    print(f"  display_name: {p.display_name}")

# 查看插件的事件处理器
handlers = server.list_plugin_handlers("my_plugin")
# {"on_message": LiveMessageEvent, "on_gift": LiveGiftEvent, "on_join": LiveJoinEvent}

# 禁用插件（取消事件注册，保留实例和文件）
await server.disable_plugin("my_plugin")

# 重新启用
await server.enable_plugin("my_plugin")

# 重载插件（代码更新后热加载）
await server.reload_plugin("my_plugin")

# 安装插件（从 URL 或本地路径）
await server.install_plugin_from_url("https://example.com/plugin.zip")
await server.install_plugin_from_local("./my_local_plugin/")

# 卸载插件（可选删除配置和数据目录）
await server.uninstall_plugin("my_plugin", delete_config=True, delete_data=True)

# 查看插件文档
readme = server.get_plugin_readme("my_plugin")
changelog = server.get_plugin_changelog("my_plugin")
```

## 📚 核心概念

### 🧩 实体模型

| 实体 | 关键属性 |
|------|---------|
| `User` | `name`, `id`, `introduction`, `icon_url` |
| `LiveUser` | 继承 User + `livestream`, `medal`, `is_admin` |
| `Creator` | 继承 LiveUser + `is_online`, `room_medal` |
| `Gift` | `name`, `id`, `price`, `num`, `lucky_gift`, `is_lucky_gift` |
| `Medal` | `name`, `level` |
| `Question` | `user`, `text`, `price`, `question_id` |

### 🎯 事件类型

| 事件类 | 触发时机 | 特有属性 |
|--------|---------|---------|
| `LiveOpenEvent` | 直播间开播 | — |
| `LiveCloseEvent` | 直播间下播 | — |
| `LiveJoinEvent` | 用户进入直播间 | — |
| `LiveFollowEvent` | 用户关注直播间 | — |
| `LiveMessageEvent` | 收到弹幕消息 | `message: str` |
| `LiveGiftEvent` | 收到礼物 | `gift: Gift` |

### 🔐 权限控制

```python
from interfaces.bot import BotPermission

# 组合权限——创建后不可修改
permissions = (
    BotPermission.SEND_LIVESTREAM_MESSAGE   # 发送弹幕
    | BotPermission.SEND_GIFT               # 赠送直售礼物
    | BotPermission.SEND_BACKPACK_GIFT      # 赠送背包礼物
    | BotPermission.EXPOSE_COOKIE           # 获取 Cookie（敏感）
)

bot = MissevanBot(cookie="...", permissions=permissions)
bot.get_cookie()  # ✅ 有 EXPOSE_COOKIE 权限
```

权限不足时抛出 `CorePermissionException`，Bot 停用后所有操作抛出 `CoreDisabledException`。

### 🔄 消息队列

```python
# 优先级消息——priority 越大越优先发送
await bot.send_livestream_message(12345, "VIP 消息", priority=100)
await bot.send_livestream_message(12345, "普通消息", priority=0)
```

后台异步消费，每条消息发送间隔 100ms 防止被平台限流。Cookie 过期时自动清空队列。

### 🔌 插件系统

插件系统提供完整的生命周期管理和配置能力：

#### 生命周期

| 功能 | 方法 | 说明 |
|------|------|------|
| 加载 | `PluginManager.load_all()` | Server 启动时自动扫描 `plugins/`，注入 config 和 data_dir |
| 启动 | `start_plugin(name)` / `enable_plugin(name)` | 注册到事件总线，移除禁用标记 |
| 停止 | `stop_plugin(name)` / `disable_plugin(name)` | 取消事件注册，调用 `terminate()`，保留实例和文件 |
| 重载 | `reload_plugin(name)` | 终止 → 清除模块缓存 → 重新检测依赖 → 重新加载 |
| 安装 | `install_plugin(url=...)` / `install_plugin(local_path=...)` | 从 URL 或本地路径安装，自动解压、安装依赖、加载 |
| 卸载 | `uninstall_plugin(name, delete_config, delete_data)` | 终止插件，可选删除配置文件、数据目录和插件目录 |

#### 配置管理

插件在目录下放置 `_conf_schema.json` 定义配置项，框架自动：

1. **解析 schema** → 提取每个字段的 `type` 和 `default`
2. **生成默认值** → `string→""`, `int→0`, `float→0.0`, `bool→false`, `array→[]`
3. **合并已保存的值** → 深度合并，已保存的值覆盖默认值
4. **注入插件实例** → 通过 `Plugin.__init__(config=...)` 传入，`self.config` 即可访问
5. **自动补充新字段** → schema 新增字段时自动写回配置文件，用户修改的值永不丢失

```python
class MyPlugin(Plugin):
    async def initialize(self) -> None:
        # self.config 即合并后的完整配置（含默认值）
        greeting = (self.config or {}).get("greeting_enabled", True)
```

运行时配置文件存储在 `data/config/{plugin_name}_config.json`。

#### 权限管理

插件**无需声明权限文件**。Server 自动为每个插件分配默认权限（与 Bot 默认一致，仅 `SEND_LIVESTREAM_MESSAGE`），管理员可通过 Server API 逐项授予或收回：

```python
# 查看插件权限信息
info = server.get_plugin_permissions("my_plugin")
# {
#     "permissions": {"SEND_LIVESTREAM_MESSAGE": True, "SEND_GIFT": False, ...},
#     "effective_flag": 1,
#     "effective_names": ["SEND_LIVESTREAM_MESSAGE"],
#     "bot_permissions": [...],
#     "missing_in_bot": [],
# }

# 逐项修改权限（立即持久化到 data/permissions/{name}_permissions.json）
server.update_plugin_permission("my_plugin", "SEND_GIFT", True)
```

#### 权限拦截

框架通过 `contextvars` 追踪当前执行的插件，在 Bot 的敏感方法（`send_livestream_message`、`send_livestream_gift`、`send_livestream_backpack`、`get_cookie`）中**实时校验**插件是否拥有对应权限：

```python
# 插件 handler 中调用 bot 方法
@event_handler
def on_gift(self, event: LiveGiftEvent) -> None:
    # 若插件未授予 SEND_LIVESTREAM_MESSAGE，这里会抛出 CorePermissionException
    event.livestream.send_message("谢谢礼物！")
```

权限不足时抛出 `CorePermissionException("插件 'xxx' 缺少 SEND_GIFT 权限")`。非插件调用（Server 直接调用）不受影响，向后兼容。插件可通过 `self.permissions` 字典主动查询自身权限。

#### 数据目录

每个插件有专属数据目录 `data/{plugin_name}/`，在加载时自动创建。插件可通过 `self.data_dir` 直接使用，存储数据库、缓存等自定义文件。卸载时可通过 `delete_data=True` 清理。

```python
class MyPlugin(Plugin):
    async def initialize(self) -> None:
        # self.data_dir → "data/my_plugin/"
        db_path = os.path.join(self.data_dir, "cache.db")
```

#### 依赖管理

插件目录下放置 `requirements.txt` 声明 Python 依赖，框架在加载前自动安装缺失的包（使用 `pip install`）。

#### 失败插件追踪

加载失败的插件会被记录（含错误信息和部分元数据），可通过 `server.get_failed_plugins()` 查看和 `server.retry_failed_plugin(dir_name)` 重试。

## 📂 项目结构

```
MissMiss/
├── requirements.txt              # 依赖清单
├── README.md                     # 本文件
│
├── plugins/                      # 🔌 插件目录
│   └── example_plugin/           # 示例插件
│       ├── main.py               #   插件入口（演示 config / permissions / data_dir）
│       ├── metadata.yaml         #   元数据（含可选字段）
│       ├── _conf_schema.json     #   配置 schema
│       ├── README.md             #   说明文档
│       └── CHANGELOG.md          #   更新日志
│
├── src/
│   ├── cli.py                    # 🖥️ 命令行前端 (Command 类路由)
│   ├── interfaces/               # 📋 抽象接口层 (MIST 标准)
│   │   ├── entity/               #    实体接口 (User, Gift, Medal, …)
│   │   ├── event/                #    事件接口 (Event, Listener, EventManager)
│   │   │   └── livestream/       #    直播间事件 (6 种具体事件)
│   │   ├── livestream/           #    直播间接口
│   │   ├── bot/                  #    机器人接口 + 权限 Flag
│   │   ├── plugin/               #    插件接口 (Plugin, PluginMetadata)
│   │   ├── server.py             #    Server 接口
│   │   └── exceptions.py         #    接口层异常
│   │
│   └── core/                     # ⚙️ 核心实现层 (Missevan 适配)
│       ├── bot/mis_bot.py        #    机器人实现 (优先级队列)
│       ├── livestream/           #    直播间实现 + WebSocket 事件路由
│       ├── events/bus.py         #    事件总线 (MRO 分发)
│       ├── models/               #    数据类 (User, Gift, Medal, Events)
│       ├── network/              #    HTTP 客户端 + 7 个 API 端点
│       │   ├── client.py         #    httpx 封装
│       │   ├── websocket.py      #    WebSocket 客户端 (Brotli + 心跳)
│       │   ├── endpoints/        #    各 API 实现
│       │   └── urls.py           #    端点常量
│       ├── plugin/               #    插件系统实现
│       │   ├── plugin_manager.py #    PluginManager (全生命周期)
│       │   ├── config_manager.py #    PluginConfigManager (schema 默认值)
│       │   └── permission_manager.py # PluginPermissionManager (权限分配 + 拦截)
│       ├── server.py             #    Server 实现 (持久化)
│       ├── logging.py            #    日志系统 (loguru)
│       └── exceptions.py         #    核心层异常
│
└── test/                         # 🧪 演示 & 测试
    ├── interactive_demo.py       #    交互式 REPL 演示 (28+ 命令)
    ├── bot_demo.py               #    Bot 连接演示
    ├── server_demo.py            #    Server 编排演示
    ├── event_demo.py             #    事件总线演示
    └── plugin_demo.py            #    插件系统演示 (13 项功能测试)
```

## 🛠️ 开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 代码检查
ruff check src/

# 类型检查
mypy src/

# 运行测试
pytest test/ -v
```

## 📄 开源协议

本项目基于 [GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html) 开源。

> MisMiss 是 [MIST](https://github.com/dikxingmengya/MIST) 直播场控标准的一部分。
> MIST 定义了跨平台的直播机器人接口规范，MisMiss 作为 Missevan 平台的适配实现，
> 遵循相同的接口契约。欢迎贡献其他平台的实现。

---

<div align="center">

**MisMiss** — MIST 标准 · 猫耳FM 实现 · 让直播机器人开发变得优雅 🎧

</div>
