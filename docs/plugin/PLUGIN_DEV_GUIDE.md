# MisMiss 插件开发指南

## 目录

1. [快速开始](#1-快速开始)
2. [插件目录结构](#2-插件目录结构)
3. [元数据](#3-元数据)
4. [配置系统](#4-配置系统)
5. [数据管理](#5-数据管理)
6. [事件处理](#6-事件处理)
7. [指令注解](#7-指令注解)
8. [Web UI](#8-web-ui)
9. [权限系统](#9-权限系统)
10. [生命周期](#10-生命周期)
11. [多账户运行模型（v1.1.0+）](#11-多账户运行模型v110)
12. [完整参考](#12-完整参考)

---

## 1. 快速开始

最小插件只需要两个文件：

```
plugins/my_plugin/
├── main.py              # 插件类（继承 Plugin）
└── metadata.yaml        # 插件元数据
```

**main.py**：

```python
from interfaces.plugin import Plugin
from interfaces.plugin.miss_config import MissConfig
from interfaces.event import event_handler
from interfaces.event.livestream import LiveMessageEvent

class MyPlugin(Plugin):
    async def initialize(self, config: MissConfig) -> None:
        self._config = config

    @event_handler
    async def on_message(self, event: LiveMessageEvent) -> None:
        await event.livestream.send_message(f"收到: {event.message}")
```

**metadata.yaml**：

```yaml
name: my_plugin
author: YourName
desc: 我的第一个插件
version: 1.0.0
```

---

## 2. 插件目录结构

完整的插件目录结构：

```
plugins/my_plugin/
├── main.py               # 插件主类（必须）
├── metadata.yaml          # 元数据（必须）
├── _conf_schema.json      # 配置项定义（可选）
├── _ui_schema.json        # Web UI 声明（可选）
├── requirements.txt       # Python 依赖（可选）
├── README.md              # 说明文档（可选）
└── CHANGELOG.md           # 更新日志（可选）
```

`PluginManager` 扫描 `plugins/` 目录，排除以 `_` 或 `.` 开头的子目录。每个子目录即为一个插件。

---

## 3. 元数据

`metadata.yaml` 定义插件的基本信息：

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 插件唯一标识，只能包含字母/数字/下划线 |
| `author` | ✅ | 插件作者 |
| `desc` | ✅ | 插件简介 |
| `version` | ✅ | 版本号（如 `1.0.0`） |
| `short_desc` | | 简短描述（列表页展示） |
| `display_name` | | 显示名称（Web UI 展示） |
| `repo` | | 仓库 URL |

`PluginManager` 自动注入以下属性到插件实例：

| 属性 | 说明 |
|------|------|
| `self.name` | 插件名称 |
| `self.author` | 插件作者 |
| `self.plugin_id` | 唯一标识 `{author}/{name}` |

---

## 4. 配置系统

### 4.1 定义配置项

`_conf_schema.json` 声明插件的配置项，框架自动生成默认值并注入到 `initialize()`：

```json
{
    "greeting_enabled": {
        "type": "boolean",
        "default": true,
        "description": "是否输出初始化问候"
    },
    "max_length": {
        "type": "int",
        "default": 500,
        "description": "最大长度"
    },
    "threshold": {
        "type": "float",
        "default": 100.0,
        "description": "阈值"
    },
    "allowed_rooms": {
        "type": "array",
        "default": [],
        "description": "启用的直播间 ID（空=全部）"
    },
    "template_text": {
        "type": "string",
        "default": "你好 {user}",
        "description": "模板文本"
    }
}
```

支持的类型：`string`, `int`, `integer`, `float`, `number`, `bool`, `boolean`, `array`, `list`, `template_list`, `object`。

### 4.2 读取配置

```python
from interfaces.plugin.miss_config import MissConfig

async def initialize(self, config: MissConfig) -> None:
    self._config = config

    # 类型安全读取
    name   = config.get_str("name", "default")
    count  = config.get_int("count", 0)
    ratio  = config.get_float("ratio", 0.0)
    flag   = config.get_bool("flag", False)
    items  = config.get_list("items", [])

    # 通用读取
    value  = config.get("key", "default")

    # Dict 兼容
    if "key" in config:
        ...
    for k in config:
        ...
    raw = config.raw       # 浅拷贝
    d   = config.to_dict()  # 导出为 dict
```

### 4.3 配置持久化

配置值由框架自动保存在 `data/config/{plugin_name}_config.json`。管理员可通过 Web 控制台修改，修改后立即生效（下一次 `initialize` 时传入新值）。插件若需立即响应配置变更，需自行实现重载逻辑。

---

## 5. 数据管理

### 5.1 PluginDataManager

框架通过 `self.data` 注入 `PluginDataManager` 实例。**所有文件读写必须通过该实例**，确保文件路径限于插件数据目录内（路径沙箱）。

| 方法 | 说明 |
|------|------|
| `self.data.read_json(filename)` | 读 JSON 文件，不存在返回 `None` |
| `self.data.write_json(filename, data)` | 写 JSON（自动创建父目录） |
| `self.data.read_text(filename)` | 读纯文本 |
| `self.data.write_text(filename, content)` | 写纯文本 |
| `self.data.delete(filename)` | 删除文件/目录 |
| `self.data.exists(filename)` | 检查是否存在 |
| `self.data.data_dir` | 数据目录绝对路径 |

### 5.2 示例

```python
async def initialize(self, config: MissConfig) -> None:
    # 读取
    data = self.data.read_json("playlist.json")
    if isinstance(data, dict):
        self._playlist = data.get("items", [])
    else:
        self._playlist = []

def _save(self) -> None:
    self.data.write_json("playlist.json", {"items": self._playlist})
```

### 5.3 路径沙箱

`PluginDataManager` 拒绝任何试图逃逸数据目录的路径：

```python
self.data.read_json("../etc/passwd")   # → ValueError: 路径逃逸
self.data.read_json("/etc/passwd")     # → ValueError: 路径逃逸
self.data.read_json("playlist.json")   # → OK: data/plugins/my_plugin/playlist.json
```

---

## 6. 事件处理

### 6.1 @event_handler 装饰器

用 `@event_handler` 标记方法，参数中声明事件类型，`EventBus` 自动按事件类型分发。

```python
from interfaces.event import event_handler
from interfaces.event.livestream import (
    LiveMessageEvent,   # 弹幕消息
    LiveGiftEvent,      # 礼物
    LiveOpenEvent,      # 开播
    LiveCloseEvent,     # 下播
    LiveJoinEvent,      # 用户进入
)

class MyPlugin(Plugin):
    @event_handler
    async def on_message(self, event: LiveMessageEvent) -> None:
        user = event.user           # 发送者
        msg  = event.message        # 消息内容
        live = event.livestream     # 直播间对象

        await live.send_message(f"收到: {msg}")

    @event_handler
    async def on_gift(self, event: LiveGiftEvent) -> None:
        gift = event.gift
        total = gift.price * gift.num

    @event_handler
    async def on_open(self, event: LiveOpenEvent) -> None:
        ...

    @event_handler
    async def on_close(self, event: LiveCloseEvent) -> None:
        ...

    @event_handler
    async def on_join(self, event: LiveJoinEvent) -> None:
        ...
```

### 6.2 同步/异步

handler 可以是同步或异步函数。异步 handler 的结果会被自动 `create_task` 调度。

### 6.3 插件上下文

`EventBus` 在调用 handler 前自动设置 `current_plugin` 上下文变量，Bot 方法通过该变量校验插件级权限。

---

## 7. 指令注解

`@command` 装饰器将直播间消息自动解析为结构化指令调用：

```python
from interfaces.command import command, Scope

class MyPlugin(Plugin):
    @command("echo", alias=["say"], scope=Scope.LIVEMESSAGE)
    def cmd_echo(self, text: str = ""):
        """复读指令: echo <内容>"""
        ...

    @command("add", scope=Scope.LIVEMESSAGE)
    def cmd_add(self, a: int, b: int):
        """加法指令: add <a> <b>"""
        result = a + b
        ...

    @command("stats", scope=Scope.LIVEMESSAGE)
    def cmd_stats(self):
        """无参数指令: stats"""
        ...
```

| 参数 | 说明 |
|------|------|
| 第一个参数 | 指令名 |
| `alias` | 别名列表 |
| `scope` | `Scope.LIVEMESSAGE`（仅直播间消息） |

参数自动按类型转换（`int`、`float`、`str`）。

---

## 8. Web UI

### 8.1 概述

插件通过 `_ui_schema.json` 声明式定义前端界面。**无需手写 HTML/CSS**——宿主应用（`PluginUI.tsx`）根据声明渲染 UI，自动继承主题。

### 8.2 register_routes()

定义 API 端点供前端调用：

```python
def register_routes(self, router: Any) -> None:
    from fastapi.responses import JSONResponse

    @router.get("/playlist")
    async def get_playlist():
        return JSONResponse([...])

    @router.post("/add")
    async def add_song(body: dict = Body(...)):
        ...
        return JSONResponse({"ok": True})
```

`PluginManager` 自动将路由注册到 FastAPI，多账户前缀为 `/api/accounts/{account_id}/plugin/{name}/ui`（见 [11.5 Web UI 路由前缀](#115-web-ui-路由前缀)；`_ui_schema.json` 中仍写 `/api/plugin/{name}/ui/...`，前端自动重写）。

### 8.3 _ui_schema.json 声明式 UI

支持的 `type` 值：

#### stats — 统计卡片

```json
{
    "type": "stats",
    "api": "/api/plugin/my_plugin/ui/stats",
    "fields": [
        { "key": "messages", "label": "弹幕数", "subtitle": "累计接收" },
        { "key": "gifts",    "label": "礼物数" }
    ]
}
```

API 返回格式：`{"messages": 77, "gifts": 0}`

#### table — 数据表格

```json
{
    "type": "table",
    "api": "/api/plugin/my_plugin/ui/list",
    "columns": [
        { "key": "name",   "label": "名称" },
        { "key": "status", "label": "状态", "type": "badge" },
        { "key": "url",    "label": "链接", "type": "link", "href_template": "https://github.com/{name}" },
        { "key": "active", "label": "激活", "type": "switch", "switch_url": "/api/plugin/my_plugin/ui/toggle" },
        { "key": "score",  "label": "得分", "type": "number", "decimals": 1 },
        { "key": "created","label": "创建", "type": "date", "date_format": "relative" },
        { "key": "avatar", "label": "头像", "type": "image", "image_width": 32 }
    ],
    "actions": [
        {
            "label": "添加",
            "method": "POST",
            "url": "/api/plugin/my_plugin/ui/add",
            "prompt_field": { "key": "name", "label": "名称", "placeholder": "输入名称..." }
        },
        {
            "label": "操作",
            "method": "POST",
            "url": "/api/plugin/my_plugin/ui/action",
            "body_template": { "action": "{{row.name}}", "row_id": "{{row.id}}" }
        }
    ]
}
```

API 返回格式：`[{"name":"Alice","status":"活跃","score":98.6,...}]` 或 `{"items":[...],"data":[...]}`

> **移动端自适应**：`table` 在移动端（<sm）自动切换为卡片列表——每行渲染为一张卡片，
> 「列标签: 值」纵向排列，操作按钮在卡片底部，无需横向滚动。

列类型（`columns[].type`）：

| `type` | 渲染 | 特殊字段 |
|--------|------|---------|
| `badge` | 圆角徽章 | `badge_colors`：手动颜色映射 |
| `link` | 可点击链接 | `href_template`：`{key}` 占位符 |
| `switch` | Toggle 开关 | `switch_url`：POST 端点 |
| `number` | 格式化数字 | `decimals`：小数位数 |
| `date` | 日期/相对时间 | `date_format`：`"relative"` / `"datetime"` |
| `image` | 图片缩略图 | `image_width`：像素宽度 |
| `text` | 可换行文本 | — |
| *(无)* | 纯文本 | — |

操作类型（`actions[]`）：

| 字段 | 说明 |
|------|------|
| `label` | 按钮文本 |
| `method` | HTTP 方法 |
| `url` | API 端点，`{id}` 占位符指向行 ID |
| `prompt_field` | 弹出输入对话框，收集 JSON body |
| `body_template` | 从行数据构建 JSON body：`{"key": "{{row.field}}"}` |
| `show_when` | 条件显示：行中该名字段（通常为布尔列）为真时才显示该按钮 |

#### list — 行列表

与 `table` 结构相同，以独立行渲染，内联显示列和操作按钮。

#### cards — 卡片网格

与 `table` 结构相同，以 1-2 列响应式卡片网格渲染。

#### playlist — 完整点播单

扩展 `table`，提供：房间选择器（多账户版本下账户仅一个直播间，选择器自动收敛为单选项）、统计栏、批量操作工具栏（批量状态切换 + 批量删除 + 清空点播单二次确认，工具栏固定底部不挤压列表）、行内状态图标、每个状态的状态切换按钮（变更同步通知直播间）。

```json
{
    "type": "playlist",
    "api": "/api/plugin/song_request/ui/playlist",
    "columns": [...],
    "add_action": {
        "label": "+ 添加点播",
        "method": "POST",
        "url": "/api/plugin/song_request/ui/add",
        "prompt_field": { "key": "song_name", "label": "歌名", "placeholder": "输入歌曲名称..." }
    },
    "status_actions": [
        { "label": "播放中", "status": "playing", "icon": "🎵" },
        { "label": "已完成", "status": "done",    "icon": "✅" }
    ]
}
```

需要 API 端点：
- `GET /rooms` → `[{room_id, room_name, count}]`
- `GET /playlist?room_id=X` → `[{index, song_name, user_name, status}]`
- `POST /add?room_id=X` 请求体 `{song_name}`
- `POST /status?room_id=X` 请求体 `{index, status}`
- `POST /delete?room_id=X` 请求体 `{index}`

> **移动端自适应**：移动端（<sm）点播单条目自动切换为卡片布局——
> 第一行「勾选 + 序号 + 歌名 + 状态徽章」，第二行「点播者 + 状态切换按钮」，
> 直播间选择器全宽显示，批量工具栏按钮带文字标签，操作按钮加大触控区域。

#### form — 表单

```json
{
    "type": "form",
    "submit": { "label": "提交", "method": "POST", "url": "/api/plugin/my_plugin/ui/submit" },
    "form_fields": [
        { "key": "title",    "label": "标题",    "type": "text",     "required": true, "placeholder": "输入标题..." },
        { "key": "category", "label": "分类",    "type": "select",   "options": [{"label":"技术","value":"tech"},{"label":"设计","value":"design"}] },
        { "key": "notes",    "label": "备注",    "type": "textarea", "rows": 3 },
        { "key": "count",    "label": "计数",    "type": "number",   "default": 0 },
        { "key": "deadline", "label": "截止日期","type": "date" },
        { "key": "notify",   "label": "启用通知","type": "switch",   "default": true }
    ]
}
```

#### composite — 复合页面

将多个类型的 section 组合到单个页面中：

```json
{
    "type": "composite",
    "sections": [
        {
            "title": "运行统计",
            "type": "stats",
            "api": "/api/plugin/my_plugin/ui/stats",
            "fields": [...]
        },
        {
            "title": "数据列表",
            "type": "table",
            "api": "/api/plugin/my_plugin/ui/list",
            "columns": [...],
            "actions": [...]
        },
        {
            "title": "快速操作",
            "type": "form",
            "submit": { ... },
            "form_fields": [...]
        }
    ]
}
```

---

## 9. 权限系统

### 9.1 插件权限

权限由 Server 自动分配默认值，管理员通过 Web 控制台逐项修改。

```python
# 初始化时接收权限
def __init__(self, permissions: dict | None = None):
    super().__init__(permissions=permissions)
    # self.permissions = {
    #     "SEND_LIVESTREAM_MESSAGE": True,
    #     "SEND_PRIVATE_MESSAGE": False,
    #     "SEND_BACKPACK_GIFT": False,
    #     "SEND_GIFT": False,
    #     "EXPOSE_COOKIE": False,
    # }
```

### 9.2 权限生效规则

1. 插件请求的权限 ⊆ Bot 实际持有的权限 → 允许
2. 管理员可随时通过 API 禁用/启用单个权限项
3. 最终生效权限 = 插件权限 ∩ Bot 权限

---

## 10. 生命周期

```
加载阶段                         启用阶段                         运行/禁用
────────                         ────────                         ────────
PluginManager                    PluginManager                    EventBus
     │                                │                               │
     ├─ load_plugin()                 ├─ _activate_plugin()           ├─ handler(event)
     │   ├─ 读取 metadata.yaml        │   ├─ 安装 requirements.txt    │   └─ set current_plugin
     │   ├─ 安装 requirements.txt     │   ├─ import 模块              │
     │   ├─ 解析 _conf_schema.json    │   ├─ 实例化插件              │
     │   ├─ 解析 _ui_schema.json      │   ├─ 注入属性                │
     │   └─ 存入 _plugins             │   ├─ register_routes()       │
     │                                │   ├─ initialize(config)      │
     └─ metadata (disabled)           │   ├─ EventBus 注册           │
                                      │   ├─ CommandRouter 注册      │
                                      │   └─ metadata.enabled=True   │
                                      │                               │
                                      └─ 运行中                       │
                                                                      │
                                  disable_plugin()                    │
                                      ├─ EventBus 取消注册            │
                                      ├─ CommandRouter 取消注册        │
                                      ├─ terminate()                  │
                                      └─ metadata.enabled=False       │
```

---

## 11. 多账户运行模型（v1.1.0+）

自 v1.1.0 起，MisMiss 采用多账户架构：**主面板管理多个账户（每个账户 = 1 个直播间 + 1 个 Bot）**。插件开发需理解以下运行规则。

### 11.1 安装 / 启用 / 禁用 / 卸载语义

| 操作 | 语义 |
|------|------|
| 面板「插件库」安装 | 仅把插件放入共享库（`plugins/`），**不运行** |
| 账户「安装」 | 把插件源码**拷贝一份**到 `data/accounts/{id}/installed_plugins/` 独立运行；各账户副本互不影响 |
| 启用 / 禁用 | 启动 / 停止该账户内的插件实例（`initialize()` / `terminate()`） |
| 卸载 | 停止实例并删除账户副本；可选择同时删除该账户的配置与持久化数据（不可撤销） |

插件版本对比：账户内已安装版本低于库中版本时，插件卡片显示「可更新」徽标。

### 11.2 直播间维度已移除

**插件不再需要（也不应该）按直播间区分任何逻辑**：

- 配置中的 `enabled_rooms` / `allowed_rooms` 等房间过滤字段已废弃（v1.1.0 起全部内置插件已移除）；
- 每个账户只绑定一个直播间，**事件总线按账户隔离** —— 插件收到的事件只会来自本账户的直播间，无需自行过滤；
- 数据存储按账户隔离：`self.data`（`PluginDataManager`）读写的是本账户的数据目录（`data/accounts/{id}/plugins/{name}/`），配置与权限同样按账户存放 —— **不要再用 `room_id` 等键做数据分区**；
- 弹幕指令按账户路由：不同账户启用同名插件时指令互不冲突。

### 11.3 定时消息

注册到**账户直播间队列**（账户仅一个直播间，统一由该队列轮转发送）：

```python
async def initialize(self, config: MissConfig) -> None:
    # 获取账户直播间 ID
    lives = self._server.livestreams
    room_id = next(iter(lives.keys()), 0)
    if room_id > 0:
        mid = self._server.register_timer_message(room_id, "欢迎来到直播间～")
```

不要使用 `live_id=0`（全局队列）：多账户版本下账户消息统一注册在房间队列，定时消息页与轮转发送都基于它。

### 11.4 Bot 权限天花板

账户 Bot 的权限是插件权限的**上限**：

- 使用**公共 Cookie** 的账户，Bot 权限被强制为「仅发送直播间消息」（`SEND_LIVESTREAM_MESSAGE`）—— 其插件无法使用发送私信 / 赠送礼物等权限；
- 使用**自定义 Cookie** 的账户可配置完整权限集；
- 插件权限仍通过 `_permission.json` 声明、账户内逐项配置，超出 Bot 权限的项自动不可用（详情抽屉会提示「Bot 未授予此权限」）。

### 11.5 Web UI 路由前缀

插件路由由框架自动注册，**多账户前缀**为：

```
/api/accounts/{account_id}/plugin/{name}/ui
```

`_ui_schema.json` 中仍按惯例写 `/api/plugin/{name}/ui/...` —— 前端引擎会自动重写为当前账户前缀，无需修改 schema。`register_routes()` 内不要硬编码绝对路径前缀（框架已按账户注入 router）。

### 11.6 重要约束

- **模块级全局变量跨账户共享**：同一进程内所有账户共用 Python 模块缓存（`sys.modules`）。插件状态必须放在实例属性上（或使用 `self.data`），**禁止**用模块级变量保存可写状态；
- 必须单 worker 部署（`MISMISS_WORKERS=1`），连接/定时器/插件实例均为单实例资源；
- 建议账户规模 ≤ 30~50（每账户 ≈ 1 个 WebSocket 连接 + 1 个定时循环 + N 个插件实例）。

---

## 12. 完整参考

### Plugin 基类属性

| 属性 | 类型 | 注入时机 | 说明 |
|------|------|---------|------|
| `self.name` | `str` | 实例化后 | 插件名称 |
| `self.author` | `str` | 实例化后 | 插件作者 |
| `self.plugin_id` | `str` | 实例化后 | `{author}/{name}` |
| `self.data_dir` | `str` | 实例化后 | 数据目录路径 |
| `self.data` | `PluginDataManager\|None` | 实例化后 | 数据文件管理器 |
| `self.permissions` | `dict\|None` | `__init__` | 运行时权限 |
| `self._server` | `MissevanServer` | 实例化后 | 服务器引用（直播间列表、定时消息等） |

### 服务引用（self._server）

框架将 `MissevanServer` 实例注入插件，可用于查询直播间列表、注册定时消息等：

```python
async def initialize(self, config: MissConfig) -> None:
    # 账户直播间（多账户版本下账户仅绑定一个直播间）
    lives = self._server.livestreams  # dict[int, MissevanLivestream]
    room_id = next(iter(lives.keys()), 0)

    # 定时消息：注册到账户直播间队列（统一轮转发送）
    if room_id > 0:
        mid = self._server.register_timer_message(room_id, "本直播间欢迎语")

        # 取消注册
        self._server.unregister_timer_message(mid)
```

**定时消息轮转**：账户队列每 `timer_interval` 秒发送一条（间隔在账户「定时消息」页实时修改，按账户持久化）。更多操作见 `MissevanServer` 的 `list_timer_messages()` / `update_timer_message()` / `move_timer_message()` / `skip_timer_message_once()` / `send_timer_message_now()`。详见 [11.3 定时消息](#113-定时消息)。

### Plugin 生命周期方法

| 方法 | 签名 | 说明 |
|------|------|------|
| `initialize` | `async (config: MissConfig) -> None` | 激活时调用，接收运行时配置 |
| `terminate` | `async () -> None` | 禁用/卸载前调用，清理资源 |
| `register_routes` | `(router: Any) -> None` | Web UI 路由注册 |

### MissConfig 方法

| 方法 | 返回 | 说明 |
|------|------|------|
| `config.get(key, default)` | `Any` | 通用读取 |
| `config.get_str(key, default)` | `str` | 字符串 |
| `config.get_int(key, default)` | `int` | 整数 |
| `config.get_float(key, default)` | `float` | 浮点数 |
| `config.get_bool(key, default)` | `bool` | 布尔（支持 `"true"/"1"/"yes"` 解析） |
| `config.get_list(key, default)` | `list` | 列表 |
| `config.raw` | `dict` | 原始字典浅拷贝 |
| `config.to_dict()` | `dict` | 导出为 dict |

### PluginDataManager 方法

| 方法 | 返回 | 说明 |
|------|------|------|
| `self.data.read_json(filename)` | `Any\|None` | 读 JSON |
| `self.data.write_json(filename, data)` | — | 写 JSON |
| `self.data.read_text(filename)` | `str\|None` | 读文本 |
| `self.data.write_text(filename, content)` | — | 写文本 |
| `self.data.delete(filename)` | — | 删除文件/目录 |
| `self.data.exists(filename)` | `bool` | 检查路径 |
| `self.data.data_dir` | `str` | 数据目录路径 |

### EventBus 事件类型

| 事件类 | 触发时机 | 关键属性 |
|--------|---------|---------|
| `LiveMessageEvent` | 收到弹幕 | `event.message`, `event.user`, `event.livestream` |
| `LiveGiftEvent` | 收到礼物 | `event.gift`(`.name`, `.price`, `.num`), `event.user` |
| `LiveOpenEvent` | 直播间开播 | `event.livestream` |
| `LiveCloseEvent` | 直播间下播 | `event.livestream` |
| `LiveJoinEvent` | 用户进入 | `event.user`, `event.livestream` |

### @command 装饰器

```python
@command(name, alias=[...], scope=Scope.LIVEMESSAGE)
```

参数自动类型转换支持：`str`, `int`, `float`, `bool`，以及带默认值的可选参数。
