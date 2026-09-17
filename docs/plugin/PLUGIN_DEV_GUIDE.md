# MisMiss 插件开发指南

## 目录

1. [快速开始](#1-快速开始)
2. [插件目录结构](#2-插件目录结构)
3. [元数据](#3-元数据)
4. [配置系统](#4-配置系统)
5. [数据管理](#5-数据管理)
6. [事件处理](#6-事件处理) — 含[优先级 / 取消传播 / 修改参数](#64-优先级取消传播与修改参数v130)
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
        "description": "是否输出初始化问候",
        "group": "常用"
    },
    "max_length": {
        "type": "int",
        "default": 500,
        "description": "最大长度",
        "group": "常用"
    },
    "threshold": {
        "type": "float",
        "default": 100.0,
        "description": "阈值",
        "group": "高级"
    },
    "template_text": {
        "type": "string",
        "default": "你好 {user}",
        "description": "模板文本",
        "group": "文案"
    }
}
```

支持的类型：`string`, `int`, `integer`, `float`, `number`, `bool`, `boolean`, `array`, `list`, `template_list`, `object`。

#### 配置分组（可选）

给字段加 `group` 即按组展示配置页，便于用户找到常用项：

| 分组 | 放什么 |
|------|--------|
| `常用` | 功能开关、指令名——用户最常改的项。**默认展开** |
| `文案` | 消息与提示模板——想改话术时来这里 |
| `高级` | 装饰线、边框、emoji、格式模板、接口地址等细节 |

规则：

- **一个都不写 = 不分组**，配置页维持平铺（老插件无需任何改动）
- 只要有一个字段写了 `group`，整个配置页就按组渲染；组的顺序 = 字段在 schema 中出现的顺序
- 未写 `group` 的字段归入「其他」，排在最后且**默认展开**（避免把没标注的项藏起来）
- 除「常用」与「其他」外，各组**默认折叠**，标题右侧显示项数
- `group` 只是展示元数据：不会进入配置值，`generate_default_config` 与既有配置读写均不受影响

分组名可自定义（不限上述三个），但建议沿用这套词汇以保持一致。

> 配置项多的插件（如 `gift_thanks` 43 项、`number_bomb` 37 项、`song_request` 32 项）强烈建议分组；
> 只有几项的插件分组反而啰嗦，可不写。

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

**这条差异对「取消传播」至关重要**，见 6.4：异步 handler 是并发启动的，
不能在执行期间阻断其他 handler。

### 6.3 插件上下文

`EventBus` 在调用 handler 前自动设置 `current_plugin` 上下文变量，Bot 方法通过该变量校验插件级权限。

### 6.4 优先级、取消传播与修改参数（v1.3.0+）

对齐 Minecraft Java 插件的事件监听模型，`@event_handler` 支持三项能力。

#### 优先级

`@event_handler(priority=N)` —— **值越大越先收到事件**，默认 `0`。

```python
class MyPlugin(Plugin):
    @event_handler(priority=1000)   # 最先执行
    def rewrite(self, event: LivestreamUserEvent) -> None:
        ...

    @event_handler                  # 默认 0
    async def on_message(self, event: LiveMessageEvent) -> None:
        ...
```

分发顺序 = **优先级降序**；优先级相同时按 `(MRO 顺序, 注册顺序)` 排列——
因此不写 `priority` 时，行为与引入该特性之前**完全一致**（子类 handler 先于
基类 handler，同层按插件注册顺序）。优先级可以跨 MRO 层级覆盖：
监听基类但优先级更高的 handler，会先于监听子类的低优先级 handler 执行。

#### 取消传播

**用户内容类事件**可取消（弹幕 / 礼物 / 进入 / 关注 / 提问 / 跨房弹幕 / 跨房礼物），
开播 / 下播 / 统计不可取消——它们是已发生的事实。取消后事件总线**不再把它传给
后续（更低优先级）的 handler**：

```python
@event_handler(priority=100)
def on_message(self, event: LiveMessageEvent) -> None:
    if event.message == "[屏蔽词]":
        event.cancel()      # 后续 handler 收不到这条弹幕
```

> ⚠️ **取消只对同步 handler 有效。**
> 异步 handler 由事件总线 `create_task` 并发调度，其执行时全部 handler
> 早已派发完毕，此时再调用 `cancel()` 无法阻断传播。
> 需要取消语义的 handler 必须写成**同步函数**；若还需异步工作（如发送消息），
> 在同步 handler 内用 `asyncio.get_running_loop().create_task(...)` 发起：
>
> ```python
> @event_handler(priority=100)
> def on_message(self, event: LiveMessageEvent) -> None:
>     if event.message == "[屏蔽词]":
>         event.cancel()
>         asyncio.get_running_loop().create_task(self._notify(event.livestream))
> ```

事件是否可取消由接口层决定：可取消的事件都实现了
`interfaces.event.Cancellable`，可用 `isinstance(event, Cancellable)` 判断。

#### 修改参数

凡是直接映射到事件字段的属性都可**直接赋值**，改动对后续（更低优先级）
的 handler 可见。派生属性（`bot` / `gift_num` / `question_id`）只读。

```python
@event_handler(priority=500)
def sanitize(self, event: LiveMessageEvent) -> None:
    event.message = event.message.replace("广告", "***")   # 后续 handler 看到改写后的内容
```

#### 改写用户显示名

`event.user.display_name` 可覆盖 `event.user.name` 的返回值。由于事件里的
用户对象**每次事件都新建**，该覆盖是**单事件作用域**的，不会泄漏到别的事件
或其他直播间：

```python
@event_handler(priority=1000)
def apply_nickname(self, event: LivestreamUserEvent) -> None:
    nick = self._nicks.get(event.user.id)
    if nick:
        event.user.display_name = nick      # 后续所有插件看到的 event.user.name 都是昵称
```

`plugins/nickname` 是这套能力的完整示范（专属昵称插件）。

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

插件注册定时消息有**唯一入口** —— 基类的 `self.register_timer_message()`，
注册时机则是 `on_livestream_bound` 钩子：

```python
async def on_livestream_bound(self, livestream) -> None:
    # 账户已绑定直播间——注册依赖直播间的资源
    text = self._config.get_str("my_timer_message", "欢迎来到直播间～")
    if text:
        self.register_timer_message(text)
```

**为什么用 `on_livestream_bound` 而不是 `initialize`**：账户可能尚未绑定直播间。
该钩子在两种时机触发，两条路径都能覆盖：

- 账户**新绑定**直播间时
- 插件被**启用 / 重新启用**时，若账户已绑定直播间，框架会**补发**一次

因此**不需要**再靠弹幕事件兜底重试注册。若仍在 `initialize` 里注册，就必须自行处理
「返回空串 → 以后重试」的分支。

经此注册的消息是**插件消息**，与面板添加的普通消息区别对待：

| 维度 | 普通消息 | 插件消息 |
|------|---------|---------|
| 注册途径 | 面板「定时消息」页 | `self.register_timer_message()` |
| 持久化 | 写入账户 state 文件 | **不写入** |
| 编辑 / 删除 / 排序 | 允许 | **禁止** |
| 立即发送 / 跳过 | 允许 | **允许**（只推进指针，不改消息） |
| 轮转位置 | 队列中段 | **置顶**（在全局消息与房间消息之前） |
| 执行指针 | 与插件消息共用同一个 | 同左 |
| 生命周期 | 由面板管理 | 插件停用 / 挂起 / 卸载 / 重载时**由框架自动清理** |

**插件不需要自己保存 `message_id`**。框架在插件停用时回收其全部插件消息，激活前还会先清一遍——
因此即使上一次是异常终止（`terminate` 没跑到），重新启用也不会累积出重复消息。
只有在运行期想主动放弃自己的定时消息时才调用 `self.unregister_timer_messages()`（撤销本插件全部）。

**仅开播时发送**：把 `only_when_live` 置为 `True`，该消息在直播间未开播期间会被自动跳过
（跳过时指针照常推进，不影响其他消息的轮转）：

```python
async def on_livestream_bound(self, livestream) -> None:
    self.register_timer_message("本场直播的欢迎语", only_when_live=True)
```

**账户未绑定直播间时** `register_timer_message()` 返回空串（不抛异常）。
用 `on_livestream_bound` 作为注册时机就不会遇到这种情况；若确实在别处调用，
需自行判断返回值并稍后重试。

**不要**改用 `self._server.register_timer_message(live_id, msg)`：那是普通消息通道，
经它注册的消息会落盘、面板可编辑删除，失去插件消息的全部保护。

> 发送间隔 `timer_interval` 是账户级的，插件消息与普通消息共用。

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

- **状态优先放实例属性**：每个账户的插件模块是**独立加载**的（按副本绝对路径加载，模块名含路径指纹），
  模块级变量不再跨账户共享。但仍建议把可写状态放在实例属性或 `self.data` 上——
  同一账户内重载插件会重新执行模块代码，模块级状态同样会丢；
- **副本即运行代码**：账户从插件库「安装」后，实际运行的是 `data/accounts/{id}/installed_plugins/<name>/`
  下的**副本**。改库不会影响已安装账户，需在账户插件页点「更新」才会覆盖副本；
- **不要在配置里声明 `enabled` 之类的自控开关**：插件的启用/停用由服务器侧统一管理
  （账户插件页的启用/停用按钮，会真实地注册/注销事件监听）。再在 `_conf_schema.json`
  里放一个 `enabled` 只会制造两个互相矛盾的开关——用户把它设为 `false` 后，
  插件在服务器看来仍是「已启用、已注册事件」，排查时极易误判。
  同理，不要在 `initialize` 里用配置值决定「要不要注册事件处理器」；
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
| `self._server` | `MissevanServer\|None` | 实例化后 | 服务器引用（查询直播间列表等） |

### 服务引用（self._server）

框架将 `MissevanServer` 实例注入插件，可用于查询直播间列表等：

```python
async def initialize(self, config: MissConfig) -> None:
    # 账户直播间（多账户版本下账户仅绑定一个直播间）
    lives = self._server.livestreams  # dict[int, MissevanLivestream]
    room_id = next(iter(lives.keys()), 0)
```

定时消息请**不要**走 `self._server.register_timer_message()` —— 那是普通消息通道。
插件注册定时消息一律用基类的 `self.register_timer_message()`，理由与完整对照表见
[11.3 定时消息](#113-定时消息)。

**定时消息轮转**：每个账户的合并轮转为「插件消息 → 全局消息 → 房间独立消息」，
每 `timer_interval` 秒发送一条（间隔在账户「定时消息」页实时修改，按账户持久化）。
面板侧可用的队列操作见 `MissevanServer` 的 `list_timer_messages()` / `update_timer_message()` /
`move_timer_message()` / `skip_timer_message_once()` / `send_timer_message_now()`。

### Plugin 生命周期方法

| 方法 | 签名 | 说明 |
|------|------|------|
| `initialize` | `async (config: MissConfig) -> None` | 激活时调用，接收运行时配置 |
| `terminate` | `async () -> None` | 禁用/卸载前调用，清理资源 |
| `on_enable` | `async () -> None` | 已初始化过的实例被重新启用时调用 |
| `on_livestream_bound` | `async (livestream) -> None` | 账户绑定直播间时调用；激活时若已绑定则补发一次 |
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

「可取消」列表示该事件是否实现了
[`Cancellable`](../interfaces/interface.md)——只有可取消事件才能用
`event.cancel()` 阻断传播（见 6.4）。

| 事件类 | 触发时机 | 可取消 | 关键属性 |
|--------|---------|:------:|---------|
| `LiveMessageEvent` | 收到**本房**弹幕 | ✅ | `event.message`, `event.user`, `event.livestream` |
| `LiveGiftEvent` | 收到**本房**礼物 | ✅ | `event.gift`(`.name`, `.price`, `.num`), `event.user` |
| `LiveOpenEvent` | 直播间开播 | ❌ | `event.livestream` |
| `LiveCloseEvent` | 直播间下播 | ❌ | `event.livestream` |
| `LiveJoinEvent` | 用户进入 | ✅ | `event.user`, `event.livestream` |
| `LiveFollowEvent` | 用户关注直播间 | ✅ | `event.user`, `event.livestream` |
| `LiveStatisticsEvent` | 直播间实时统计 | ❌ | `event.score`, `event.online`, `event.vip` |
| `LiveQuestionEvent` | 用户付费提问 | ✅ | `event.question`, `event.user` |
| `LiveCrossMessageEvent` | **连麦**时对方直播间的弹幕 | `event.message`, `event.user`, `event.origin_room_id`, `event.origin_creator_name` |
| `LiveCrossGiftEvent` | **大厅**中赠送给非主麦的礼物 | `event.gift`, `event.user`, `event.target_creator_name`（受赠主播）, `event.target_creator_id` |
| `LiveCrossEvent` | 上面两个的**基类**：注册一个 handler 收下全部跨房事件 | 无额外字段，按具体类型分支取 `origin_*` / `target_*` |

**跨房事件是独立事件，不会漏进本房事件。** 连麦时对方直播间的弹幕走
`LiveCrossMessageEvent`，大厅里送给别的麦的礼物走 `LiveCrossGiftEvent`——
二者与 `LiveMessageEvent` / `LiveGiftEvent` 是**兄弟节点**（都继承
`LivestreamUserEvent`）。因此：

- 监听 `LiveMessageEvent` 的插件**收不到**跨房弹幕（指令类插件不会被对方直播间
  的弹幕误触发）
- 想做「连麦互动」就要显式监听跨房事件
- 监听父类 `LivestreamUserEvent` 会同时收到本房与跨房两类

两个跨房事件都带「对方直播间」四件套（`*_room_id` / `*_creator_id` /
`*_creator_name` / `*_creator_icon`），但**前缀按方向区分**：

| 事件 | 前缀 | 对方是 | 例 |
|------|------|--------|-----|
| `LiveCrossMessageEvent` | `origin_` | 弹幕**来自**那里（来源） | `event.origin_creator_name` = 发弹幕者所在房的主播 |
| `LiveCrossGiftEvent` | `target_` | 礼物**送给**那里（去向） | `event.target_creator_name` = **被赠礼物**的主播 |

平台未携带时按未知处理（id 为 `0`、昵称为空串、头像为 `None`），可用真值判断对方是否可知。

**想一次收下全部跨房事件**（如连麦互动插件），监听分组基类 `LiveCrossEvent` 即可 ——
它同样**收不到**本房弹幕与礼物。由于字段名按方向区分，在 handler 内按具体类型分支：

```python
from interfaces.event.livestream import LiveCrossEvent, LiveCrossGiftEvent

@event_handler
def on_cross(self, event: LiveCrossEvent) -> None:
    if isinstance(event, LiveCrossGiftEvent):
        print(f"{event.user.name} 送给 {event.target_creator_name} 一个 {event.gift.name}")
    else:
        print(f"[跨房] {event.user.name}: {event.message}")
```

### @command 装饰器

```python
@command(name, alias=[...], scope=Scope.LIVEMESSAGE)
```

参数自动类型转换支持：`str`, `int`, `float`, `bool`，以及带默认值的可选参数。
