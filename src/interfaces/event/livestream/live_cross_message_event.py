"""跨房弹幕消息事件接口。

连麦场景下，对方直播间的弹幕会经由 ``message:cross_new`` 送达本直播间。

本事件与 :class:`LiveMessageEvent` **刻意不构成继承关系**：事件总线按 MRO
遍历分发，若它继承自 ``LiveMessageEvent``，所有监听本房弹幕的插件都会连带
收到跨房弹幕，「本房 / 跨房」就分不开了。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .live_cross_event import LiveCrossEvent


class LiveCrossMessageEvent(LiveCrossEvent, ABC):
    """跨房弹幕消息事件（连麦时对方直播间的弹幕）。

    与 :class:`LiveMessageEvent` 是**兄弟节点**而非父子关系，因此：

    - 监听 ``LiveMessageEvent`` 的插件**不会**收到本事件
    - 监听父类 :class:`LivestreamUserEvent` 的插件两者都会收到

    用法::

        from interfaces.event.livestream import LiveCrossMessageEvent

        class MyPlugin(Plugin):
            @event_handler
            def on_cross_message(self, event: LiveCrossMessageEvent) -> None:
                print(f"[跨房 {event.origin_room_id}] {event.user.name}: {event.message}")

    .. versionadded:: 1.3
    """

    @property
    @abstractmethod
    def message(self) -> str:
        """获取弹幕内容。

        :return: 消息文本
        """
        ...

    @property
    @abstractmethod
    def origin_room_id(self) -> int:
        """获取弹幕来源直播间 ID（对方直播间）。

        :return: 来源直播间 ID；包内未携带时为 ``0``
        """
        ...

    @property
    @abstractmethod
    def origin_creator_id(self) -> int:
        """获取来源直播间主播的用户 ID。

        :return: 主播用户 ID；未知时为 ``0``
        """
        ...

    @property
    @abstractmethod
    def origin_creator_name(self) -> str:
        """获取来源直播间主播昵称。

        :return: 主播昵称；未知时为空串
        """
        ...

    @property
    @abstractmethod
    def origin_creator_icon(self) -> str | None:
        """获取来源直播间主播头像 URL。

        :return: 头像 URL；未知时为 ``None``
        """
        ...
