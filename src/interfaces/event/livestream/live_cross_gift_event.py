"""跨房礼物事件接口。

大厅类型直播间赠送礼物时可选择赠送对象；若对象**不是主麦**，平台会产生
``gift:cross_send`` 包，其中 ``room`` 字段标明该礼物归属的对方直播间。

本事件与 :class:`LiveGiftEvent` **刻意不构成继承关系**：事件总线按 MRO 遍历
分发，若它继承自 ``LiveGiftEvent``，礼物感谢、幸运值榜单等监听本房礼物的
插件会连带把别的直播间的礼物算进本房。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .live_cross_event import LiveCrossEvent

if TYPE_CHECKING:
    from ...entity.gift import Gift


class LiveCrossGiftEvent(LiveCrossEvent, ABC):
    """跨房礼物事件（大厅中赠送给非主麦的礼物）。

    与 :class:`LiveGiftEvent` 是**兄弟节点**而非父子关系，因此：

    - 监听 ``LiveGiftEvent`` 的插件**不会**收到本事件
    - 监听父类 :class:`LivestreamUserEvent` 的插件两者都会收到

    用法::

        from interfaces.event.livestream import LiveCrossGiftEvent

        class MyPlugin(Plugin):
            @event_handler
            def on_cross_gift(self, event: LiveCrossGiftEvent) -> None:
                print(f"{event.user.name} 向 {event.target_creator_name} "
                      f"赠送了 {event.gift.name}")

    .. versionadded:: 1.3
    """

    @property
    @abstractmethod
    def gift(self) -> Gift:
        """获取礼物。

        :return: 事件礼物
        """
        ...

    @property
    def gift_num(self) -> int:
        """获取礼物数量。

        等价于 ``self.gift.num``。

        :return: 礼物数量
        """
        return self.gift.num

    @property
    @abstractmethod
    def target_room_id(self) -> int:
        """获取礼物**送达**的直播间 ID（对方直播间）。

        与 :class:`LiveCrossMessageEvent` 的 ``origin_room_id`` 相对：那边是弹幕
        **来自**的直播间，这边是礼物**送给**的直播间。跨房礼物就是「本房观众把
        礼物送给了同台其他麦的主播」，故用 ``target`` 而非 ``origin``。

        :return: 目标直播间 ID；包内未携带时为 ``0``
        """
        ...

    @property
    @abstractmethod
    def target_creator_id(self) -> int:
        """获取**被赠送礼物**的主播用户 ID。

        :return: 主播用户 ID；未知时为 ``0``
        """
        ...

    @property
    @abstractmethod
    def target_creator_name(self) -> str:
        """获取**被赠送礼物**的主播昵称。

        :return: 主播昵称；未知时为空串
        """
        ...

    @property
    @abstractmethod
    def target_creator_icon(self) -> str | None:
        """获取**被赠送礼物**的主播头像 URL。

        :return: 头像 URL；未知时为 ``None``
        """
        ...
