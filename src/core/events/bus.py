"""事件总线。

实现 ``EventManager`` 接口，基于 ``@event_handler`` 装饰器
将事件分发到注册的监听器方法。
"""

from __future__ import annotations

import asyncio
import typing
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from interfaces.event.event_manager import EventManager
from interfaces.plugin.plugin import Plugin, current_plugin

if TYPE_CHECKING:
    from interfaces.event.event import Event
    from interfaces.event.listener import Listener


class EventBus(EventManager):
    """轻量事件总线。

    注册时扫描 ``Listener`` 的 ``@event_handler`` 方法，
    按其第一个参数类型建立事件 → 处理器的映射。
    触发事件时按类型匹配分发。

    用法::

        bus = EventBus()
        bus.register_new_event(my_listener)
        bus.call_event(open_event)
    """

    def __init__(self) -> None:
        # event_type -> list[(listener, method)]
        self._handlers: dict[type, list[tuple[Listener, Callable[..., object]]]] = (
            defaultdict(list)
        )
        self._listeners: list[Listener] = []

    # ------------------------------------------------------------------ #
    # EventManager 接口实现
    # ------------------------------------------------------------------ #

    def register_new_event(self, listener: Listener) -> None:
        """注册一个事件监听器。

        扫描 ``listener`` 上所有带 ``__event_handler__`` 标记的方法，
        按方法的第一个参数（事件类型）建立映射。

        :param listener: 事件监听器实例
        """
        if listener in self._listeners:
            return
        self._listeners.append(listener)

        for attr_name in dir(listener):
            method = getattr(listener, attr_name, None)
            if not callable(method) or not getattr(
                method, "__event_handler__", False
            ):
                continue

            # 使用 get_type_hints 正确解析类型（包括字符串前向引用）
            # noinspection PyBroadException
            try:
                hints = typing.get_type_hints(method)
            except Exception:
                continue

            # 跳过 self，取第一个非 self 且非 return 的参数类型
            event_type = None
            for name, hint in hints.items():
                if name in ("return",):
                    continue
                event_type = self._extract_type(hint)
                break

            if event_type is not None:
                self._handlers[event_type].append((listener, method))

    def unregister_event(self, listener: Listener) -> None:
        """删除一个已注册的监听器。

        :param listener: 事件监听器实例
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

        for handlers in self._handlers.values():
            handlers[:] = [
                (l, m) for l, m in handlers if l is not listener  # noqa: E741
            ]

    def call_event(self, event: Event, clazz: type | None = None) -> None:
        """触发事件。

        按事件实例的类型以及其所有父类型匹配处理函数并依次调用。
        若 handler 属于某个 ``Plugin``，自动设置 :data:`current_plugin`
        上下文变量，以便 Bot 方法校验插件级权限。

        **同步与异步**：handler 可以是同步或异步函数。
        若为异步（``async def``），自动通过 ``create_task`` 调度到事件循环，
        ``current_plugin`` 上下文会随 Task 传播。

        :param event: 事件实例
        :param clazz: 指定分发的事件类型；若为 ``None`` 则按 ``type(event)`` 分发
        """
        target_type = clazz if clazz is not None else type(event)

        # 遍历 MRO（包含所有父类型），匹配注册的处理函数
        for base_type in target_type.__mro__:
            if base_type in self._handlers:
                for _listener, handler in self._handlers[base_type]:
                    # 若监听器是 Plugin 实例，设置插件上下文
                    token = None
                    if isinstance(_listener, Plugin):
                        token = current_plugin.set(_listener)
                    try:
                        result = handler(event)
                        # 若 handler 是异步函数，调度到事件循环
                        if asyncio.iscoroutine(result):
                            asyncio.get_running_loop().create_task(result)
                    finally:
                        if token is not None:
                            current_plugin.reset(token)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    @property
    def handler_count(self) -> int:
        """已注册的事件处理器总数。"""
        return sum(len(h) for h in self._handlers.values())

    @property
    def event_type_count(self) -> int:
        """已注册的事件类型数量。"""
        return len(self._handlers)

    def get_listener_handlers(self, listener: Listener) -> dict[str, type]:
        """查询指定监听器注册的所有事件处理器。

        :param listener: 监听器实例
        :return: 方法名 → 事件类型的映射
        """
        result: dict[str, type] = {}
        for event_type, handlers in self._handlers.items():
            for _listener, method in handlers:
                if _listener is listener:
                    result[method.__name__] = event_type
        return result

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_type(hint: type) -> type:
        """从 get_type_hints 解析出的类型中提取具体类型。

        处理 ``Optional[X]``（即 ``Union[X, None]``）的情况，
        取第一个非 ``None`` 的类型。

        :param hint: 类型提示
        :return: 提取出的具体类型
        """
        origin = getattr(hint, "__origin__", None)
        if origin is not None:
            # Union[X, None] → X
            args = getattr(hint, "__args__", ())
            for arg in args:
                if arg is not type(None):
                    return arg
        return hint
