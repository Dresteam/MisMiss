"""事件管理器接口。

定义了事件注册、注销与触发的抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .event import Event
    from .listener import Listener


class EventManager(ABC):
    """事件管理器接口。

    提供事件的注册、注销和调用功能。

    .. versionadded:: 1.0
    """

    @abstractmethod
    def register_new_event(self, listener: Listener) -> None:
        """注册一个新的事件监听器。

        :param listener: 事件监听器
        """
        ...

    @abstractmethod
    def unregister_event(self, listener: Listener) -> None:
        """删除一个已经注册的监听器。

        :param listener: 事件监听器
        """
        ...

    @abstractmethod
    def call_event(self, event: Event, clazz: type | None = None) -> None:
        """触发事件。

        当 ``clazz`` 为 ``None`` 时，直接触发该事件；
        当指定 ``clazz`` 时，用于事件触发的向上递归，将 ``event``
        作为源事件以 ``clazz`` 类型触发。

        :param event: 事件实例
        :param clazz: 当前触发的事件类型，用于向上递归；若为 ``None`` 则直接触发
        """
        ...
