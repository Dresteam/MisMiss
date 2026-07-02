"""命令装饰器与作用域定义。

提供 ``@command`` 装饰器将插件方法声明为指令处理器，
框架自动监听消息事件，匹配指令名并解析参数调用对应方法。

用法::

    from interfaces.command import command, Scope

    class MyPlugin(Plugin):
        @command("greet", alias=["hello", "hi"], scope=Scope.LIVEMESSAGE)
        def on_greet(self, target: str, count: int = 1):
            '''当用户发送 "greet world 3" 时被调用'''
            ...
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any


class Scope(enum.Flag):
    """指令作用域——控制在哪些消息来源上匹配指令。

    可组合使用：``Scope.LIVEMESSAGE | Scope.PRIVATEMESSAGE``
    """

    LIVEMESSAGE = enum.auto()
    """直播间弹幕消息。"""

    PRIVATEMESSAGE = enum.auto()
    """私信消息（未实装）。"""

    ALL = LIVEMESSAGE | PRIVATEMESSAGE
    """所有消息渠道。"""


# ------------------------------------------------------------------ #
# 元数据存储键
# ------------------------------------------------------------------ #

_COMMAND_META_KEY = "__command_meta__"
"""存储在方法上的命令元数据属性名。"""


# ------------------------------------------------------------------ #
# 装饰器
# ------------------------------------------------------------------ #


def command(
    name: str,
    *,
    alias: list[str] | None = None,
    scope: Scope = Scope.LIVEMESSAGE,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """将方法声明为指令处理器。

    框架在加载插件时扫描 ``@command`` 方法，自动注册消息监听器。
    当用户发送的消息以 ``name`` 或 ``alias`` 开头时，
    框架解析剩余部分为参数，按位置传入方法。

    参数类型转换基于方法的类型注解：
    - ``str`` → 直接传入
    - ``int`` → ``int(value)``
    - ``float`` → ``float(value)``
    - ``bool`` → ``value.lower() in ("true","1","yes","on")``
    - 无注解 → ``str``

    :param name: 指令名（如 ``"greet"``），用户需发送 ``greet ...`` 触发
    :param alias: 别名列表（如 ``["hello", "hi"]``），同样触发此方法
    :param scope: 作用域，默认为直播间消息
    :return: 装饰后的方法（附加 ``__command_meta__`` 属性）

    用法::

        @command("ban", alias=["kick"], scope=Scope.LIVEMESSAGE)
        def on_ban(self, user_name: str, reason: str = ""):
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__command_meta__ = {  # type: ignore[attr-defined]
            "name": name.strip().lower(),
            "alias": [a.strip().lower() for a in (alias or [])],
            "scope": scope,
        }
        return func

    return decorator
