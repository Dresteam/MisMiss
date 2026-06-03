# MIST 直播平台机器人框架 —— 接口文档

## 1. 概述

本框架为直播平台机器人的事件驱动 API 定义了一套完整的抽象接口层。所有接口均使用 Python `ABC`（抽象基类）定义，位于 `src/interfaces/` 包下。

框架核心能力：

- **实体模型**：用户、直播间用户、创建者、礼物、粉丝勋章、提问
- **事件系统**：基于 `@event_handler` 装饰器的监听器模式，支持事件注册、注销与触发
- **直播间管理**：直播间属性的查询与操作（发送消息、赠送礼物等）
- **机器人 API**：机器人的消息发送、背包查询、礼物赠送等操作

---

## 2. 实体层级 (Entity Layer)

```
User (ABC)
├── LiveUser (ABC)
│   └── Creator (ABC)
├── Gift (ABC)
├── Medal (ABC)
└── Question (ABC)
```

### 2.1 User —— 基础用户

```python
from interfaces.entity import User
```

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 用户名。匿名用户返回 `""` 而非 `None` |
| `id` | `int` | 用户 ID |
| `introduction` | `Optional[str]` | 个人介绍。无时返回 `""` 而非 `None` |
| `icon_url` | `Optional[str]` | 头像 URL |

### 2.2 LiveUser —— 直播间用户

```python
from interfaces.entity import LiveUser
```

继承 `User`，额外属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `livestream` | `Livestream` | 用户所在的直播间 |
| `medal` | `Optional[Medal]` | 粉丝勋章 |
| `is_admin` | `bool` | 是否为直播间管理员 |

### 2.3 Creator —— 创建者（主播）

```python
from interfaces.entity import Creator
```

继承 `LiveUser`，额外属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `is_online` | `bool` | 是否在线（开播状态） |
| `room_medal` | `Optional[Medal]` | 直播间的粉丝勋章 |

### 2.4 Gift —— 礼物

```python
from interfaces.entity import Gift
```

| 属性 | 类型 | 说明 |
|------|------|------|
| `livestream` | `Optional[Livestream]` | 礼物所在的直播间 |
| `user` | `User` | 赠送礼物的用户 |
| `user_id` | `int` | 赠送者用户 ID（委托给 `user.id`） |
| `user_name` | `str` | 赠送者用户名（委托给 `user.name`） |
| `lucky_gift` | `Optional[Gift]` | 原始幸运礼物（若当前为幸运礼物结果） |
| `is_lucky_gift` | `bool` | 是否为幸运礼物 |
| `name` | `str` | 礼物名称 |
| `id` | `int` | 礼物 ID |
| `price` | `int` | 礼物价值（电池数或等价货币） |
| `num` | `int` | 礼物数量 |

### 2.5 Medal —— 粉丝勋章

```python
from interfaces.entity import Medal
```

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 粉丝勋章名称 |
| `level` | `int` | 粉丝勋章等级 |

### 2.6 Question —— 提问

```python
from interfaces.entity import Question
```

| 属性 | 类型 | 说明 |
|------|------|------|
| `livestream` | `Livestream` | 提问所属的直播间 |
| `user` | `User` | 提问的用户 |
| `user_id` | `int` | 提问者用户 ID（委托给 `user.id`） |
| `user_name` | `str` | 提问者用户名（委托给 `user.name`） |
| `question_id` | `str` | 问题 ID（十六进制字符串） |
| `text` | `str` | 问题文本内容 |
| `price` | `int` | 问题的出价/价格 |

---

## 3. 事件层级 (Event Layer)

```
Event (ABC, 标记接口)
└── LivestreamEvent (ABC)
    ├── LiveOpenEvent
    ├── LiveCloseEvent
    └── LivestreamUserEvent (ABC)
        ├── LiveJoinEvent
        ├── LiveFollowEvent
        ├── LiveMessageEvent  (+ message)
        └── LiveGiftEvent     (+ gift, gift_num)
```

### 3.1 Event —— 事件标记

所有事件的顶级标记接口，内部无方法定义。

```python
from interfaces import Event
```

### 3.2 LivestreamEvent —— 直播间事件基类

继承 `Event`，所有直播间事件的基类型。

| 属性 | 类型 | 说明 |
|------|------|------|
| `livestream` | `Livestream` | 事件涉及的直播间 |
| `bot` | `Optional[Bot]` | 事件相关的机器人（委托给 `livestream.bot`） |

### 3.3 LivestreamUserEvent —— 用户事件基类

继承 `LivestreamEvent`，涉及用户交互的直播间事件。

| 属性 | 类型 | 说明 |
|------|------|------|
| `user` | `LiveUser` | 事件涉及的用户（此实例上 `introduction` 可能返回 `None`） |

### 3.4 具体事件类型

| 类 | 父类 | 说明 | 额外属性 |
|----|------|------|----------|
| `LiveOpenEvent` | `LivestreamEvent` | 直播间开播 | 无 |
| `LiveCloseEvent` | `LivestreamEvent` | 直播间下播 | 无 |
| `LiveJoinEvent` | `LivestreamUserEvent` | 用户加入直播间 | 无 |
| `LiveFollowEvent` | `LivestreamUserEvent` | 用户关注直播间 | 无 |
| `LiveMessageEvent` | `LivestreamUserEvent` | 用户发送消息 | `message: str` |
| `LiveGiftEvent` | `LivestreamUserEvent` | 用户赠送礼物 | `gift: Gift`, `gift_num: int`（委托） |

---

## 4. 事件系统 (Event System)

### 4.1 EventManager —— 事件管理器

```python
from interfaces import EventManager
```

| 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `register_new_event` | `listener: Listener` | `None` | 注册一个新的事件监听器 |
| `unregister_event` | `listener: Listener` | `None` | 删除一个已注册的监听器 |
| `call_event` | `event: Event`, `clazz: type \| None = None` | `None` | 触发事件。`clazz=None` 时直接触发；指定 `clazz` 时用于向上递归 |

### 4.2 Listener —— 监听器标记

```python
from interfaces import Listener
```

标记接口。所有事件监听器必须实现此接口。监听方法用 `@event_handler` 装饰。

### 4.3 `@event_handler` —— 事件处理装饰器

```python
from interfaces import event_handler
# 别名
from interfaces import EventHandler
```

标记监听器类中的方法为事件处理方法。

**用法示例：**

```python
from interfaces import Listener, event_handler
from interfaces.event.livestream import LiveMessageEvent, LiveGiftEvent

class MyListener(Listener):

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        print(f"[{event.livestream.room_name}] {event.user.name}: {event.message}")

    @event_handler
    def on_gift(self, event: LiveGiftEvent) -> None:
        print(f"[{event.livestream.room_name}] {event.user.name} 赠送了 "
              f"{event.gift_num} 个 {event.gift.name}")
```

被装饰的方法会被添加 `__event_handler__ = True` 属性，供事件调度器在运行时识别。

---

## 5. 直播间 (Livestream)

### 5.1 Livestream —— 直播间接口

```python
from interfaces.livestream import Livestream
```

继承 `EventManager`。调用 `call_event` 时仅能触发该直播间下注册的监听器；在该直播间下注册的监听器仅监听该直播间的事件。

**属性：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `is_connected` | `bool` | 直播间是否已连接 |
| `live_id` | `int` | 直播间 ID |
| `room_name` | `str` | 直播间名称 |
| `room_description` | `str` | 直播间简介 |
| `score` | `int` | 直播间热度（未开播时返回 `-1`） |
| `creator` | `Creator` | 直播间创建者 |
| `creator_id` | `int` | 创建者 ID（委托给 `creator.id`） |
| `creator_name` | `str` | 创建者昵称（委托给 `creator.name`） |
| `medal` | `Optional[Medal]` | 粉丝勋章（委托给 `creator.room_medal`） |
| `bot` | `Bot` | 监听此直播间的机器人 |

**方法：**

| 方法 | 参数 | 说明 |
|------|------|------|
| `send_message` | `message: str` | 发送消息（委托给 `bot.send_livestream_message`） |
| `send_gift` | `gift_id: int, num: int` | 赠送礼物（委托给 `bot.send_livestream_gift`） |
| `send_backpack` | `gift_id: int, num: int` | 赠送背包礼物（委托给 `bot.send_livestream_backpack`） |

### 5.2 LivestreamManager —— 直播间管理器

```python
from interfaces.livestream import LivestreamManager
```

| 属性/方法 | 参数 | 返回 | 说明 |
|-----------|------|------|------|
| `livestream_list` | — | `list[Livestream]` | 获取所有直播间列表 |
| `get_livestream` | `live_id: int` | `Livestream` | 获取直播间，不存在则自动注册 |
| `get_livestream_if_absent` | `live_id: int` | `Optional[Livestream]` | 获取直播间，不存在则返回 `None` |
| `register_new_livestream` | `live_id: int` | `Livestream` | 注册新直播间 |
| `unregister_livestream` | `livestream: Livestream` | `None` | 删除已注册的直播间 |

---

## 6. 机器人 (Bot)

### 6.1 Bot —— 机器人接口

```python
from interfaces.bot import Bot
```

继承 `User`。出于账号安全考虑，不暴露 Cookie。

| 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `send_livestream_message` | `live_id: int`, `message: str` | `None` | 向直播间发送消息 |
| `get_backpack_gifts` | `live_id: int` | `list[Gift]` | 获取机器人背包礼物列表 |
| `send_livestream_gift` | `live_id: int`, `gift_id: int`, `num: int` | `None` | 通过礼物 ID 向直播间赠送礼物 |
| `send_livestream_backpack` | `live_id: int`, `gift_id: int`, `num: int` | `None` | 向直播间赠送背包内礼物 |

---

## 7. 异常参考

### RequestFailedException

```python
from interfaces import RequestFailedException
```

当向服务器发送请求失败时抛出。覆盖所有与直播平台 API 交互的方法网络错误场景。

```python
raise RequestFailedException("发送消息失败: 网络超时")
```

### CookieException

```python
from interfaces.bot import CookieException
```

当机器人 Cookie 无效、过期或无法通过验证时抛出。

```python
raise CookieException("Cookie 已过期，请重新登录")
```

---

## 8. 空值约定

| 类型标注 | 语义 |
|---------|------|
| `str` | 保证非空；匿名用户返回 `""` |
| `Optional[str]` | 可为 `None`；部分场景下返回 `""` |
| `list[T]` | 保证非空列表（可能为空列表 `[]`） |
| `Optional[T]` | 可为 `None` |
| `int` / `bool` | 原始类型，不可为 `None` |

---

## 9. 实现指南

### 9.1 实现实体接口

实现实体接口（如 `User`、`Gift`）时，只需实现所有标注 `@abstractmethod` 的属性。带有具体实现的委托属性（如 `Gift.user_id`、`Livestream.creator_name`）无需覆写，但可根据需要重写。

```python
class MyUser(User):
    def __init__(self, name: str, uid: int):
        self._name = name
        self._id = uid

    @property
    def name(self) -> str:
        return self._name

    @property
    def id(self) -> int:
        return self._id

    @property
    def introduction(self) -> Optional[str]:
        return ""

    @property
    def icon_url(self) -> Optional[str]:
        return None
```

### 9.2 实现事件监听器

```python
class MyListener(Listener):

    @event_handler
    def on_live_open(self, event: LiveOpenEvent) -> None:
        """直播间开播时调用"""
        ...

    @event_handler
    def on_live_message(self, event: LiveMessageEvent) -> None:
        """收到消息时调用"""
        ...
```

### 9.3 导入方式

**推荐**：从具体子包导入（明确依赖关系）：
```python
from interfaces.entity import User, Gift
from interfaces.event.livestream import LiveMessageEvent, LiveGiftEvent
from interfaces.livestream import Livestream
from interfaces.bot import Bot
```

**便捷**：从顶层包导入常用类型：
```python
from interfaces import Event, Listener, event_handler, RequestFailedException
```

### 9.4 抽象方法清单

实现各接口时必须覆写的所有 `@abstractmethod` 属性/方法：

| 接口 | 必须实现的抽象成员 |
|------|-------------------|
| `User` | `name`, `id`, `introduction`, `icon_url` |
| `LiveUser` | 上述 4 项 + `livestream`, `medal`, `is_admin` |
| `Creator` | 上述 7 项 + `is_online`, `room_medal` |
| `Gift` | `livestream`, `user`, `lucky_gift`, `is_lucky_gift`, `name`, `id`, `price`, `num` |
| `Medal` | `name`, `level` |
| `Question` | `livestream`, `user`, `question_id`, `text`, `price` |
| `Livestream` | `is_connected`, `live_id`, `room_name`, `room_description`, `score`, `creator`, `bot`, `send_message`, `send_gift`, `send_backpack` + EventManager 的 3 个方法 |
| `LivestreamManager` | `livestream_list`, `get_livestream`, `get_livestream_if_absent`, `register_new_livestream`, `unregister_livestream` |
| `Bot` | User 的 4 项 + `send_livestream_message`, `get_backpack_gifts`, `send_livestream_gift`, `send_livestream_backpack` |
| `LivestreamEvent` | `livestream` |
| `LivestreamUserEvent` | 上述 1 项 + `user` |
| `LiveMessageEvent` | 上述 2 项 + `message` |
| `LiveGiftEvent` | 上述 2 项 + `gift` |
