# 🎙️ MisMiss

<div align="center">

**MIST 标准实现 · 猫耳FM 直播场控机器人框架**

[![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-AGPL--3.0-orange?logo=gnu)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Code Style](https://img.shields.io/badge/Code%20Style-ruff-purple?logo=ruff)](https://docs.astral.sh/ruff)
[![Type Check](https://img.shields.io/badge/Type%20Check-mypy-informational?logo=python&logoColor=white)](https://mypy-lang.org)

</div>

---

## 📖 简介

**MisMiss** 是 [MIST](https://github.com/dikxingmengya/MIST) 直播场控机器人标准在 **Missevan（猫耳FM）** 平台的参考实现。MIST 定义了一套完整的抽象接口规范——包括实体模型、事件系统、直播间管理、机器人操作和插件框架——MisMiss 在此基础上提供了高性能的异步实现。

核心设计理念：**面向接口，事件驱动**。你只需实现一个监听器类，就能响应开播、下播、弹幕、礼物、关注等直播事件；同时通过统一 API 发送消息和赠送礼物。更换直播平台时，只需替换实现层，业务代码无需修改。

v1.1.0 起，MisMiss 从「单服务器仪表盘」升级为**多账户面板**：一个面板可托管多个直播账户，每个账户拥有完全隔离的 Bot、直播间、插件副本与配置。管理端与账户端共用同一个域名与登录页，登录后按角色进入各自界面。

## ✨ 特性

- 🖥️ **Web 控制台** — React + TypeScript + Tailwind CSS 现代化面板，完全替代 CLI
- 👥 **多账户体系** — 一个面板托管 N 个账户，实例/配置/权限/数据完全隔离；每个账户 = 1 个 Bot + 1 个直播间
- 🚪 **账户独立门户** — 与面板同域名、同登录页，直播主用自己的凭据登录即进入账户界面，自助改密、自助兑换授权码（过期账户兑换后自动恢复），无任何面板功能
- 📣 **更新日志弹窗** — 服务器更新后账户再次登录自动弹出该版本更新日志，每个账户每个版本只弹一次；日志随部署包分发，无需联网
- 🤖 **Bot 双模式** — 私有 Cookie（账户独立配置）或公共 Cookie（面板统一下发，多账户并发共享，权限强制降为仅发送消息，账户内不可查看）
- 💳 **授权与到期** — 账户到期时间、`MM-XXXX-XXXX-XXXX` 授权码批量生成与兑换、到期硬停用（Bot/直播间/插件）与续期自动恢复
- 🔌 **插件生态** — 官方插件库 + 账户副本隔离：从库「安装」即拷贝一份源码到账户目录独立运行，各账户互不干扰；支持启用/禁用/重载/配置/权限/一键更新
- 📐 **MIST 标准兼容** — 严格遵循 MIST 接口规范，跨平台复用业务逻辑
- 🧩 **清晰的分层架构** — 接口层（`interfaces`）定义契约，核心层（`core`）负责实现
- 🎨 **插件自带 UI** — 插件放置 `_ui_schema.json` 即可获得声明式 Web 页面（表格/列表/卡片/统计/播放列表/表单/组合布局），无需写前端代码
- ⚡ **事件驱动模型** — 基于 MRO 的事件分发，支持按事件类型继承树精确路由；每账户独立事件总线与命令路由
- 🔒 **三层权限控制** — `BotPermission` Flag 位权限（Bot 为天花板）→ 插件权限字典 → 执行时经 `contextvars` 实时拦截；敏感操作（如获取 Cookie）受 name-mangling 保护
- 💬 **优先级消息队列** — 消息按优先级排序发送，后台异步消费，自动限流
- ⏰ **定时消息** — 插件消息 / 普通消息分类管理：插件消息不落盘、面板不可改删、轮转置顶，与普通消息共用执行指针；插件可声明「仅开播时发送」，面板可按来源筛选；每账户独立间隔，支持跳过/立即发送，改 Cookie 后普通队列不丢
- 🔄 **WebSocket 长连接** — Brotli 解压、心跳维持、指数退避自动重连
- 💾 **状态持久化** — 启动自动恢复 Bot、直播间和插件状态，修改时原子写入
- 📝 **日志系统** — 基于 loguru，实时 WebSocket 批量推送（万条虚拟滚动不卡顿），环形缓冲 + 断线补发
- 🚀 **一键部署与在线更新** — Docker 部署包（镜像 + compose + `deploy.sh`）；面板内点击即可下载新版部署包、校验、备份、导入镜像并重建容器，支持一键回滚

## 🏗️ 架构

```
AccountManager  ──  面板级编排（data/panel.json）
═══════════════════════════════════════════════════════
  ├── MissevanServer #1   ──  账户 1 运行时（data/accounts/1/）
  │     ├── MissevanBot          私有/公共 Cookie
  │     ├── MissevanLivestream   1 个直播间 + WS 事件路由
  │     ├── PluginManager        账户插件副本 + 配置 + 权限
  │     └── EventBus             账户独立事件总线
  ├── MissevanServer #2   ──  账户 2 运行时（data/accounts/2/）
  └── ...
        ▲
        │  共享插件库（仅作安装源，不直接运行）
        └── plugins/   +   ExpiryScheduler（60s 到期巡检）
```

**每个账户的隔离边界**（`data/accounts/{id}/`）：

| 内容 | 路径 |
|------|------|
| 运行时状态 | `server_state.json` |
| 插件源码副本 | `installed_plugins/{name}/` |
| 插件配置 | `config/{name}_config.json` |
| 插件权限 | `permissions/{name}_permissions.json` |
| 插件数据 | `plugins/{name}/` |

### 分层

```
plugins/  ──  官方插件库（独立 git 仓库）
═══════════════════════════════════════════════════════
  checkin/  gift_thanks/  number_bomb/  qiuqian/  song_request/
  timer_messages/  welcome/  zodiac/  keyword_reply/  song_list/  ...

interfaces/  ──  抽象接口层 (MIST 标准)
───────────────────────────────────────────────────────

  Entity (实体)        Event (事件)         Service (服务)
  ─────────────        ────────────         ───────────────
  User                 Event                Livestream
  ├─ LiveUser          ├─ Listener          Bot
  │  └─ Creator        ├─ EventManager      Server
  Gift                 │  └─ EventBus       BotPermission
  Medal                └─ @event_handler
  Question
                       Plugin               Command
                       ├─ Plugin (ABC)      ├─ @command
                       └─ PluginMetadata    └─ Scope

core/  ──  核心实现层 (Missevan 适配)
───────────────────────────────────────────────────────

  account/             bot/                  livestream/
  ──────────           ────────              ──────────────
  AccountManager       MissevanBot           MissevanLivestream
  LicenseStore         (优先级队列)          Live (WS 事件路由)
  ExpiryScheduler      (权限拦截)
  migrate_legacy_data

  network/             events/               models/
  ──────────           ──────────────        ────────
  HTTPClient           EventBus              用户·礼物·勋章·提问
  LiveWebSocket        (MRO 分发)            11 种事件数据类
  9 个 API 端点

  plugin/                               server.py
  ─────────────                         ──────────
  PluginManager            # 全生命周期管理    MissevanServer
  PluginConfigManager      # 配置 + schema 默认值  (单账户编排)
  PluginPermissionManager  # 权限分配 + 拦截       config.py / logging.py
  PluginDataManager        # 沙箱化数据读写
```

### 事件继承树

```
Event (ABC, 标记)
 └── LivestreamEvent (ABC)      ← 直播间事件基类
      ├── LiveOpenEvent          ← 开播
      ├── LiveCloseEvent         ← 下播
      ├── LiveStatisticsEvent    ← 直播间实时统计（热度/在线/VIP）
      └── LivestreamUserEvent    ← 用户事件基类
           ├── LiveJoinEvent     ← 用户进入
           ├── LiveFollowEvent   ← 关注直播间
           ├── LiveMessageEvent  ← 弹幕消息  (+ message)
           ├── LiveGiftEvent     ← 赠送礼物  (+ gift)
           ├── LiveQuestionEvent ← 提问      (+ question)
           └── LiveCrossEvent    ← 跨房事件基类（连麦 / 大厅，分发分组标记）
                ├── LiveCrossMessageEvent ← 跨房弹幕（对方直播间, + origin_*）
                └── LiveCrossGiftEvent    ← 跨房礼物（送给非主麦, + target_*）
```

事件分发按 **MRO** 遍历：监听 `LivestreamEvent` 可以收到所有直播间子事件；监听 `LiveMessageEvent` 则仅收到弹幕。

跨房事件（连麦 / 大厅）刻意与 `LiveMessageEvent` / `LiveGiftEvent` 构成**兄弟节点而非父子**，
因此监听本房弹幕或礼物的插件不会收到对方直播间的事件；想处理跨房事件需显式监听这两个新事件。

两个事件都带「对方直播间」信息，但**方向相反、故字段名不同**：

- `LiveCrossMessageEvent.origin_*` —— 弹幕**来自**的直播间（对方是来源）
- `LiveCrossGiftEvent.target_*` —— 礼物**送给**的直播间（对方是去向，如 `target_creator_name` 即受赠主播）

要「一个 handler 收下全部跨房事件」（如连麦互动插件），监听分组基类
`LiveCrossEvent` 即可 —— 它同样收不到本房事件；字段名按方向区分，在 handler 内按具体类型分支。

## 📦 安装

- **Python** ≥ 3.13 · **Node.js** ≥ 20（Web 控制台需要）
- 依赖：httpx · websockets · brotli · loguru · pyyaml · fastapi · uvicorn · react

```bash
git clone https://github.com/Dresteam/MisMiss.git
cd MisMiss

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r web/backend/requirements.txt
cd web/frontend && npm install && cd ../..
```

## 🚀 快速开始

### 方式一：Docker 部署包（推荐用于服务器）

```bash
# 本地构建部署包（版本号取自 pyproject.toml，可显式指定）
powershell -File scripts\docker-release.ps1              # Windows
bash scripts/docker-release.sh                           # Linux / macOS

# 上传到服务器后一条命令完成导入镜像 + 引导配置 + 启动
scp dist/mismiss-<版本>-docker.zip user@server:/opt/mismiss/
cd /opt/mismiss && unzip -o mismiss-<版本>-docker.zip && bash deploy.sh
```

首次部署会生成 `config.yml` 与 `data/` 等目录，默认通过 Nginx 暴露在 **18080** 端口。
后续更新可在面板「更新 MisMiss」页在线完成（下载 → 校验 → 备份 → 导入镜像 → 重建容器），
也可覆盖部署目录后重新执行 `bash deploy.sh`。

详细流程与安全说明见 [docs/build/BUILDING.md](docs/build/BUILDING.md)。

### 方式二：本地开发

```bash
start.bat          # 开发模式：前端 :15173 + API :18080
start.bat prod     # 单端口：:18080 同时提供前端和 API
```

打开浏览器访问 `http://localhost:15173`（开发）或 `http://localhost:18080`（生产）。

- **管理面板**：用默认账号（用户名密码均为 **MisMiss**）登录，首次登录强制改密，登录后进面板
- **账户界面**：同一个登录页，用面板中创建的账户凭据登录，登录后自动进入账户界面

### 方式三：Python API

面板是主要使用方式，但在自定义场景下也可以直接使用核心层：

```python
import asyncio
from core.account import AccountManager

async def main():
    manager = AccountManager(data_dir="data")
    manager.load()
    await manager.start_all()

    # 创建账户（内部会拉起独立的 MissevanServer）
    record = await manager.create_account(
        "我的直播间",
        room_id=12345,          # 绑定直播间，自动添加并进入
        bot_mode="private",     # 或 "public"（用面板公共 Cookie）
        cookie="你的Cookie",
        username="streamer",    # 账户门户登录凭据，全局唯一
        password="secret",
        duration_days=30,       # -1 表示永久
    )

    # 拿到该账户的 Server，做进一步操作
    server = manager.get_server(record.id)
    live = next(iter(server.livestreams.values()), None)
    await live.send_message("大家好~")

    await manager.shutdown_all()

asyncio.run(main())
```

单账户场景可以绕过 `AccountManager`，直接使用 `MissevanServer`：

```python
from core import MissevanServer

server = MissevanServer(data_dir="data/accounts/manual")
await server.start()
bot = await server.create_bot(cookie="你的Cookie")
live = await server.add_livestream(12345)   # 只拉取房间信息，不连接
await server.enable_livestream(12345)       # 启用并进入直播间
await live.send_message("大家好！", priority=0)
```

### 监听事件

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

## 🔌 插件系统

### 运行模型：库 + 副本

```
plugins/{name}/                      ← 插件库（安装源，不直接运行）
        │
        │  账户「安装」= 拷贝一份源码
        ▼
data/accounts/{id}/installed_plugins/{name}/   ← 账户副本（独立运行）
```

- 面板「插件库」页负责**安装/卸载/刷新库**（上传 zip、从库中删除）
- 账户「插件」页负责**管理自己的副本**（从库安装、启用/禁用、配置、权限、更新）
- 副本会随库的更新而落后，卡片上会显示「可更新」徽标，一键即可从库覆盖更新
  （保留启用状态与既有配置，新版本 schema 新增的字段自动补默认值）

账户侧的插件页带一个**一键更新**按钮：把它自己那些「副本版本低于库版本」的插件一次更新到库版本
（按钮上显示可更新数量，全部最新时置灰）。与面板推送共用同一套版本守卫。

库更新后要把改动带到各账户，面板提供两个批量入口：

- **推送到账户** — 按插件（卡片上的图标）或一次性推送全部插件。只处理**已安装**该插件的账户，
  并**跳过副本版本不低于库版本**的：更新会 stop/start 插件实例（断掉插件消息与内部状态），
  无谓的重载应当避免，所以手动改过副本的账户与已最新的账户都不会被触碰
- **默认插件** — 在插件卡片上点亮星标即设为默认。**新建账户**会自动安装并启用默认插件
  （失败仅告警，不阻断账户创建）；存量账户通过「应用默认插件」按钮显式补齐

### 目录结构

```
plugins/
└── my_plugin/
    ├── metadata.yaml         # 插件元数据（必须）
    ├── main.py               # 插件入口（必须）
    ├── _conf_schema.json     # 配置 schema + 默认值（可选）
    ├── _ui_schema.json       # 声明式 Web UI（可选）
    ├── requirements.txt      # 依赖（可选）
    ├── README.md             # 文档（可选）
    └── CHANGELOG.md          # 更新日志（可选）
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

支持的类型：`string` / `int`(`integer`) / `float`(`number`) / `bool`(`boolean`) /
`array`(`list` / `template_list`) / `object`。

**main.py：**

```python
from interfaces.plugin import Plugin, MissConfig
from interfaces.event import event_handler
from interfaces.event.livestream import LiveMessageEvent, LiveGiftEvent, LiveJoinEvent


class MyPlugin(Plugin):
    """我的第一个插件 —— 演示 config / permissions / data_dir 用法"""

    async def initialize(self, config: MissConfig) -> None:
        # config 通过参数传入 —— 框架自动注入（含 schema 默认值）
        # 事件处理器中若要使用配置，需自行保存为实例属性
        self._config = config
        print(f"[{self.name}] 插件就绪 (plugin_id={self.plugin_id})")
        print(f"[{self.name}] 权限: {self.permissions}")
        print(f"[{self.name}] 数据目录: {self.data_dir}")

        # self.data 是路径沙箱化的读写器（拒绝 ../ 逃逸），所有文件 I/O 都应走它
        self._stats = self.data.read_json("stats.json") or {
            "messages": 0, "gifts": 0, "joins": 0,
        }

    async def terminate(self) -> None:
        self.data.write_json("stats.json", self._stats)

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        max_len = self._config.get_int("max_message_length", 500)
        print(f"[MSG] {event.user.name}: {event.message[:max_len]}")
        self._stats["messages"] += 1

    @event_handler
    def on_gift(self, event: LiveGiftEvent) -> None:
        total = event.gift.price * event.gift.num
        if total >= self._config.get_float("gift_threshold", 100.0):
            print(f"[GIFT] {event.user.name} 赠送 {event.gift.name} x{event.gift.num}")
        self._stats["gifts"] += 1

    @event_handler
    def on_join(self, event: LiveJoinEvent) -> None:
        self._stats["joins"] += 1
```

### 生命周期

| 钩子 | 时机 |
|------|------|
| `async initialize(config: MissConfig)` | 插件启用时，事件注册之前 |
| `async terminate()` | 插件禁用/重载/卸载之前，用于落盘与释放资源 |
| `async on_enable()` | 已初始化过的实例被**重新启用**时（首次启用走 `initialize`） |
| `register_routes(router)` | 注册插件自带 UI 的数据端点（同步方法） |

### 注入的属性

| 属性 | 说明 |
|------|------|
| `self.name` / `self.author` | 来自 `metadata.yaml` |
| `self.plugin_id` | `{author}/{name}`（小写） |
| `self.data_dir` | 账户私有数据目录绝对路径 |
| `self.data` | `PluginDataManager`——`read_json` / `write_json` / `read_text` / `write_text` / `delete` / `exists`，路径锁定在该目录内 |
| `self.permissions` | `dict[str, bool]`，由框架分配，可逐项修改 |
| `self._server` | 所属 `MissevanServer`，可查询 `livestreams` 等 |

### 配置读取

`MissConfig` 只读，提供 `get` / `get_str` / `get_int` / `get_float` / `get_bool` /
`get_list` / `get_int_list`，以及 `raw` / `to_dict()` 取原始字典。

框架会按 `_conf_schema.json` 生成默认值，与已保存的配置深度合并（用户值优先），
仅在 schema 新增字段时回写文件——因此已保存的值不会被覆盖。

### 权限

插件**无需声明权限文件**。框架为每个插件自动分配默认权限，管理员可在插件的
「权限管理」中逐项开关。有效权限 = 插件权限 ∩ Bot 权限（Bot 是天花板）：

- 公共 Cookie 账户的 Bot 被强制为「仅发送直播间消息」，因此其插件也只能发消息
- 自定义 Cookie 账户的 Bot 可勾选完整权限，插件随之放开

执行时通过 `contextvars` 追踪当前插件，在 Bot 的敏感方法中实时校验：

```python
@event_handler
def on_gift(self, event: LiveGiftEvent) -> None:
    # 若插件未授予 SEND_LIVESTREAM_MESSAGE，这里会抛出 CorePermissionException
    event.livestream.send_message("谢谢礼物！")
```

### 声明式 Web UI（可选）

放置 `_ui_schema.json` 即可让插件获得自己的页面，无需编写前端代码：

```json
{
  "type": "table",
  "api": "/api/plugin/my_plugin/ui/list",
  "columns": [
    { "key": "keyword", "label": "关键词" },
    {
      "key": "match_label", "label": "匹配方式", "type": "badge",
      "badge_colors": {
        "包含": "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        "正则表达式": "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400"
      }
    },
    { "key": "enabled", "label": "启用", "type": "switch",
      "switch_url": "/api/plugin/my_plugin/ui/toggle" }
  ],
  "actions": [
    {
      "label": "+ 添加规则", "method": "POST",
      "url": "/api/plugin/my_plugin/ui/add", "toolbar_only": true,
      "prompt_fields": [
        { "key": "keyword", "label": "关键词" },
        { "key": "match_type", "label": "匹配方式", "input_type": "select",
          "options": [
            { "label": "包含", "value": "contains" },
            { "label": "正则表达式", "value": "regex" }
          ] },
        { "key": "reply", "label": "回复内容", "input_type": "textarea" }
      ]
    },
    {
      "label": "删除", "method": "POST",
      "url": "/api/plugin/my_plugin/ui/delete", "row_only": true,
      "body_template": { "id": "{{row.id}}" }
    }
  ]
}
```

支持 `table` / `list` / `cards` / `stats` / `playlist` / `form` / `composite` 七种布局，
单元格类型含 `text` / `number` / `date` / `badge` / `link` / `image` / `switch`，
操作支持 `prompt_field` / `prompt_fields` / `body_template` / `show_when`。

插件用 `register_routes(router)` 提供这些端点即可。多账户模式下实际挂载前缀为
`/api/accounts/{id}/plugin/{name}/ui`，schema 里写 `/api/plugin/{name}/ui/...`
即可，前端会自动重写前缀。

### 编写约束

- **状态放实例属性**——每个账户的插件模块独立加载（按副本路径加载，模块名唯一），
  模块级变量不再跨账户共享；但同一账户内重载会重新执行模块代码，
  所以可写状态仍应放在实例属性或 `self.data` 里
- **副本即运行代码**——账户运行的是自己 `installed_plugins/` 下的副本，
  改插件库不影响已安装账户，需在账户插件页点「更新」才会覆盖
- **不要按 `room_id` 分区数据**——多账户模型下一个账户只有一个直播间，
  事件与数据已天然按账户隔离

完整规范见 [docs/plugin/PLUGIN_DEV_GUIDE.md](docs/plugin/PLUGIN_DEV_GUIDE.md)。

## 📚 核心概念

### 🧩 实体模型

| 实体 | 关键属性 |
|------|---------|
| `User` | `name`, `id`, `introduction`, `icon_url` |
| `LiveUser` | 继承 User + `livestream`, `medal`, `is_admin` |
| `Creator` | 继承 LiveUser + `is_online`, `room_medal` |
| `Gift` | `name`, `id`, `price`, `num`, `lucky_gift`, `is_lucky_gift` |
| `Medal` | `name`, `level` |
| `Question` | `user`, `text`, `price`, `question_id`, `status`, `likes`, `liked` |

### 🎯 事件类型

| 事件类 | 触发时机 | 特有属性 |
|--------|---------|---------|
| `LiveOpenEvent` | 直播间开播 | — |
| `LiveCloseEvent` | 直播间下播 | — |
| `LiveStatisticsEvent` | 直播间实时统计 | `score`, `online`, `vip` |
| `LiveJoinEvent` | 用户进入直播间 | — |
| `LiveFollowEvent` | 用户关注直播间 | — |
| `LiveMessageEvent` | 收到弹幕消息 | `message: str` |
| `LiveGiftEvent` | 收到礼物 | `gift: Gift` |
| `LiveQuestionEvent` | 收到提问 | `question: Question` |
| `LiveCrossMessageEvent` | 连麦时收到**对方直播间**的弹幕 | `message: str`, `origin_room_id`, `origin_creator_name` … |
| `LiveCrossGiftEvent` | 大厅中赠送给**非主麦**的礼物 | `gift: Gift`, `target_room_id`, `target_creator_name`（受赠主播）… |

### 🔐 权限控制

```python
from interfaces.bot import BotPermission

permissions = (
    BotPermission.SEND_LIVESTREAM_MESSAGE   # 发送弹幕      (1)
    | BotPermission.SEND_PRIVATE_MESSAGE    # 发送私信      (2)  预留，尚未实现
    | BotPermission.SEND_BACKPACK_GIFT      # 赠送背包礼物  (4)
    | BotPermission.SEND_GIFT               # 赠送直售礼物  (8)
    | BotPermission.EXPOSE_COOKIE           # 获取 Cookie   (16) 敏感
)

bot = MissevanBot(cookie="...", permissions=permissions)
bot.get_cookie()  # ✅ 有 EXPOSE_COOKIE 权限
```

权限在构造后不可修改。权限不足时抛出 `CorePermissionException`，
Bot 停用后所有操作抛出 `CoreDisabledException`。

### 🔄 消息队列

```python
# 优先级消息——priority 越大越优先发送
await bot.send_livestream_message(12345, "VIP 消息", priority=100)
await bot.send_livestream_message(12345, "普通消息", priority=0)
```

后台异步消费，每条消息发送间隔 100ms 防止被平台限流。Cookie 过期时自动清空队列。

### ⏰ 定时消息

每个账户的合并轮转为「**插件消息 → 全局消息 → 房间消息**」，
每 `timer_interval` 秒发送**一条**，确保不会同时刷屏。

面板添加的是**普通消息**，插件通过 `self.register_timer_message()` 注册的是**插件消息**：

| 维度 | 普通消息 | 插件消息 |
|------|---------|---------|
| 持久化 | 写入账户 state 文件 | **不写入**（插件重启后自行重新注册） |
| 编辑 / 删除 / 排序 | 面板可操作 | **不可**，只能「立即发送」或「跳过」 |
| 轮转位置 | 队列中段 | **置顶** |
| 开播条件 | 无 | 可声明 `only_when_live=True`，未开播时跳过该条 |
| 生命周期 | 由面板管理 | 插件停用/挂起/卸载/重载时由框架自动清理 |

插件消息不落盘，因此插件即使异常终止（`terminate` 没跑到），重新启用也不会累积出重复消息。

```python
# 普通消息通道（面板/Server API）
server.register_timer_message(live_id, "每条消息都会轮到的~")
server.set_timer_interval(60)          # 每账户独立持久化，不重置位置指针

# 队列操作
server.list_timer_messages()                                   # 带位置指针，每条带 source 标记
server.move_timer_message(message_id, -1)                      # 上移（1 为下移）
server.skip_timer_message_once(message_id, live_id)            # 跳过指针处消息
await server.send_timer_message_now(message_id, live_id)       # 立即发送
```

```python
# 插件通道：注册的是插件消息（详见 docs/plugin/PLUGIN_DEV_GUIDE.md）
class MyPlugin(Plugin):
    async def on_livestream_bound(self, livestream) -> None:
        # 账户绑定时（或插件启用时账户已绑定）回调，无需靠事件兜底重试
        self.register_timer_message("欢迎来到直播间～")
        # 仅开播期间发送：未开播则跳过该条，指针照常推进
        self.register_timer_message("本场专属语", only_when_live=True)
```

普通定时队列在更换 Cookie 时会随 Bot 迁移，不会丢失。

### 💳 授权与到期

- 账户有 `expires_at`（或永久），面板可按「续期 N 天」（叠加）或「设置剩余 N 天」（覆盖）调整
- 到期后 `ExpiryScheduler`（60s 巡检）+ 端点守卫硬停用：停 Bot、断开房间、暂停插件（保留启用标记）
- 账户可自助用授权码兑换，兑换天数从 `max(now, 到期时间)` 起算，过期账户兑换后自动恢复运行
- 授权码格式 `MM-XXXX-XXXX-XXXX`，字母表刻意排除易混淆的 `0 O 1 I L`

## 📂 项目结构

```
MissMiss/
├── requirements.txt              # 依赖清单
├── README.md                     # 本文件
├── start.bat / start.sh          # 一键启动脚本
├── mismiss.spec                  # PyInstaller 打包配置
├── Dockerfile / docker-compose.yml / nginx.conf   # Docker 部署栈
│
├── web/                          # 🖥️ Web 控制台
│   ├── backend/                  # FastAPI 后端
│   │   ├── main.py               #   入口 + 认证中间件 + SPA fallback
│   │   └── api/
│   │       ├── deps.py           #   AccountManager 依赖注入 + 账户守卫
│   │       ├── schemas.py        #   Pydantic 请求/响应模型
│   │       └── routes/           #   Panel / Account / AccountPlugins / Bot / Live /
│   │                             #   Timer / Plugin / Server / Auth / Config /
│   │                             #   Proxy / Update / Ws
│   └── frontend/                 # React + TypeScript + Tailwind CSS
│       └── src/
│           ├── pages/            #   账户总览 / 账户详情 / 账户门户 / 插件库 /
│           │                     #   日志 / 设置 / 服务器 / 更新 / 登录
│           ├── components/       #   布局 / 侧边栏 / 插件抽屉 / 插件UI渲染器 /
│           │                     #   动态配置表单 / 各类弹窗
│           ├── hooks/            #   useAuth / useLogStream / useToast
│           └── i18n/             #   文案表
│
├── plugins/                      # 🔌 官方插件库（独立 git 仓库）
│   ├── checkin/  gift_thanks/  follow_thanks/  welcome/  zodiac/
│   ├── number_bomb/  song_request/  song_list/  keyword_reply/
│   ├── qiuqian/  question_thanks/  timer_messages/  ...
│
├── src/
│   ├── cli.py                    # 🖥️ 命令行前端
│   ├── interfaces/               # 📋 抽象接口层 (MIST 标准)
│   │   ├── entity/               #    实体接口 (User, Gift, Medal, Question, …)
│   │   ├── event/                #    事件接口 (Event, Listener, EventManager)
│   │   │   └── livestream/       #    9 种直播间事件
│   │   ├── livestream/           #    直播间接口
│   │   ├── bot/                  #    机器人接口 + 权限 Flag
│   │   ├── plugin/               #    插件接口 (Plugin, PluginMetadata, MissConfig)
│   │   ├── command/              #    命令接口 (@command, Scope)
│   │   ├── server.py             #    Server 接口
│   │   └── exceptions.py         #    接口层异常
│   │
│   └── core/                     # ⚙️ 核心实现层 (Missevan 适配)
│       ├── account/              #    多账户体系
│       │   ├── manager.py        #      AccountManager (账户编排 + 隔离)
│       │   ├── license.py        #      授权码生成/兑换/撤销
│       │   ├── expiry.py         #      到期巡检调度器
│       │   └── migration.py      #      单服务器 → 多账户数据迁移
│       ├── bot/mis_bot.py        #    机器人实现 (优先级队列 + 权限拦截)
│       ├── livestream/           #    直播间实现 + WebSocket 事件路由
│       ├── events/bus.py         #    事件总线 (MRO 分发)
│       ├── models/               #    数据类 (用户/礼物/勋章/提问/事件)
│       ├── network/              #    HTTP 客户端 + 9 个 API 端点
│       │   ├── client.py         #      httpx 封装
│       │   ├── websocket.py      #      WebSocket 客户端 (Brotli + 心跳 + 退避)
│       │   ├── endpoints/        #      各 API 实现
│       │   └── urls.py           #      端点常量
│       ├── plugin/               #    插件系统实现
│       │   ├── plugin_manager.py     # PluginManager (全生命周期)
│       │   ├── config_manager.py     # PluginConfigManager (schema 默认值)
│       │   ├── permission_manager.py # PluginPermissionManager (权限分配)
│       │   └── data_manager.py       # PluginDataManager (路径沙箱)
│       ├── command/router.py     #    命令路由器
│       ├── server.py             #    MissevanServer (单账户编排 + 持久化)
│       ├── config.py             #    配置加载 (config.yml)
│       ├── logging.py            #    日志系统 (loguru)
│       └── exceptions.py         #    核心层异常
│
├── docs/                         # 📚 文档
│   ├── build/BUILDING.md         #    构建与部署指南
│   ├── plugin/PLUGIN_DEV_GUIDE.md #   插件开发指南
│   ├── interfaces/interface.md   #    MIST 接口文档
│   ├── web/README.md             #    Web 控制台说明 + API 端点总览
│   ├── changelog/                #    各版本变更记录
│   └── TASKS.md                  #    待实现任务清单
│
├── test/                         # 🧪 测试
│   ├── test_account_manager.py   #    账户管理
│   ├── test_account_api.py       #    API 端到端
│   ├── test_license_store.py     #    授权码
│   ├── test_cross_worker_sync.py #    多 worker 状态同步
│   ├── test_timer_persist.py     #    定时消息持久化
│   ├── test_plugin_timer.py      #    插件定时消息（不落盘/只读/指针共用）
│   └── test_plugin_copy_isolation.py # 插件副本隔离（加载账户副本而非插件库）
│
└── scripts/                      # 🛠️ 构建 / 部署 / 发布脚本
    ├── build.ps1 / build.sh
    ├── release.ps1 / release.sh
    ├── docker-release.ps1 / docker-release.sh
    ├── docker-server-deploy.sh
    └── docker-entrypoint.sh
```

## 🛠️ 开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 代码检查
ruff check src/ web/backend/

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

**MisMiss** — MIST 标准 · 猫耳FM 实现 · 一个面板，一群账户，各自精彩 🎧

</div>
