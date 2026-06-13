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

**MisMiss** 是 [MIST](https://github.com/MIST) 直播场控机器人标准在 **Missevan（猫耳FM）** 平台的参考实现。MIST 定义了一套完整的抽象接口规范——包括实体模型、事件系统、直播间管理和机器人操作——MisMiss 在此基础上提供了高性能的异步实现。

核心设计理念：**面向接口，事件驱动**。你只需实现一个监听器类，就能响应开播、下播、弹幕、礼物、关注等直播事件；同时通过统一 API 发送消息和赠送礼物。更换直播平台时，只需替换实现层，业务代码无需修改。

## ✨ 特性

- 📐 **MIST 标准兼容** — 严格遵循 MIST 接口规范，跨平台复用业务逻辑
- 🧩 **清晰的分层架构** — 接口层（`interfaces`）定义契约，核心层（`core`）负责实现
- ⚡ **事件驱动模型** — 基于 MRO 的事件分发，支持按事件类型继承树精确路由
- 🔒 **权限控制** — `BotPermission` Flag 位权限，敏感操作（如获取 Cookie）受 name-mangling 保护
- 💬 **优先级消息队列** — 消息按优先级排序发送，后台异步消费，自动限流
- 🔄 **WebSocket 长连接** — Brotli 解压、心跳维持、自动重连（指数退避）
- 💾 **状态持久化** — Server 启动自动恢复 Bot 和直播间，修改时自动保存
- 📝 **日志系统** — 基于 loguru，自动提取调用类名/方法名，支持多维度过滤
- 🧪 **完整类型标注** — mypy 严格模式，所有接口均有完善的 docstring

## 🏗️ 架构

```
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

  logging.py · exceptions.py
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
- **依赖**：httpx · websockets · brotli · loguru

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

    # 进入直播间 (开始接收事件)
    await live.join()

    # 发送消息
    await live.send_message("大家好！")

asyncio.run(main())
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

后台异步消费，每条间隔 100ms 防限流。Cookie 过期自动清空队列。

## 📂 项目结构

```
MissMiss/
├── requirements.txt              # 依赖清单
├── README.md                     # 本文件
│
├── src/
│   ├── interfaces/               # 📋 抽象接口层 (MIST 标准)
│   │   ├── entity/               #    实体接口 (User, Gift, Medal, …)
│   │   ├── event/                #    事件接口 (Event, Listener, EventManager)
│   │   │   └── livestream/       #    直播间事件 (6 种具体事件)
│   │   ├── livestream/           #    直播间接口
│   │   ├── bot/                  #    机器人接口 + 权限 Flag
│   │   ├── server.py             #    Server 接口
│   │   ├── exceptions.py         #    接口层异常
│   │   └── interface.md          #    MIST 接口规范文档
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
│       ├── server.py             #    Server 实现 (持久化)
│       ├── logging.py            #    日志系统 (loguru)
│       └── exceptions.py         #    核心层异常
│
└── test/                         # 🧪 演示 & 测试
    ├── bot_demo.py               #    Bot 连接演示
    ├── server_demo.py            #    Server 编排演示
    └── event_demo.py             #    事件总线演示
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
