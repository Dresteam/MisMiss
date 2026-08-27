"""直播间接口。

定义了直播间的完整抽象，包括属性查询和操作。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from ..event.event_manager import EventManager

if TYPE_CHECKING:
    from ..bot.bot import Bot
    from ..entity.creator import Creator
    from ..entity.medal import Medal
    from ..entity.user import User


class Livestream(EventManager, ABC):
    """直播间接口。

    继承自 :class:`EventManager`，表示单个直播间。

    调用 :meth:`call_event` 时，仅可触发在该 :class:`Livestream`
    下注册的事件监听器。在 :class:`Livestream` 下注册的事件监听器，
    仅可监听该直播间的事件。

    .. versionadded:: 1.0
    """

    # ------------------------------------------------------------------ #
    # 启停控制
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """获取启用状态。

        :return: ``True`` 表示已启用，``False`` 表示已停用
        """
        ...

    @enabled.setter
    @abstractmethod
    def enabled(self, value: bool) -> None:
        """设置启用状态。

        停用时所有操作将抛出 :class:`CoreDisabledException`。

        :param value: ``True`` 启用，``False`` 停用
        """
        ...

    # ------------------------------------------------------------------ #
    # 属性
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """检查直播间是否已连接。

        :return: 如果直播间已连接则返回 ``True``，否则返回 ``False``
        """
        ...

    @property
    @abstractmethod
    def live_id(self) -> int:
        """获取直播间 ID。

        :return: 直播间 ID
        """
        ...

    @property
    @abstractmethod
    def room_name(self) -> str:
        """获取直播间名称。

        :return: 直播间名称
        """
        ...

    @property
    @abstractmethod
    def room_description(self) -> str:
        """获取直播间简介。

        :return: 直播间简介内容
        """
        ...

    @property
    @abstractmethod
    def score(self) -> int:
        """获取直播间热度值。

        当未开播时返回 ``-1``。

        :return: 直播间热度值
        """
        ...

    @property
    @abstractmethod
    def online_count(self) -> int:
        """获取直播间当前在线人数。

        通过 WebSocket ``room:statistics`` 事件实时更新；
        未收到统计事件时返回 ``0``。

        :return: 当前在线人数
        """
        ...

    @property
    @abstractmethod
    def creator(self) -> Creator:
        """获取直播间创建者。

        :return: 直播间创建者信息
        """
        ...

    @property
    def creator_id(self) -> int:
        """获取直播间创建者 ID。

        等价于 ``self.creator.id``。

        :return: 直播间创建者 ID
        """
        return self.creator.id

    @property
    def creator_name(self) -> str:
        """获取直播间创建者名称。

        等价于 ``self.creator.name``。

        :return: 直播间创建者昵称
        """
        return self.creator.name

    @property
    def medal(self) -> Optional[Medal]:
        """获取直播间粉丝勋章。

        等价于 ``self.creator.room_medal``。

        :return: 直播间粉丝勋章
        """
        return self.creator.room_medal

    @property
    @abstractmethod
    def bot(self) -> Bot:
        """获取监听此直播间的机器人。

        :return: 监听机器人
        """
        ...

    @abstractmethod
    async def send_message(self, message: str, priority: int = 0) -> None:
        """向直播间发送信息。

        等价于 ``self.bot.send_livestream_message(self.live_id, message, priority)``。

        :param message: 信息文本
        :param priority: 消息优先级（值越大越优先），默认为 0
        :raises RequestFailedException: 当请求失败时
        """
        ...

    @abstractmethod
    async def send_gift(self, gift_id: int, num: int) -> None:
        """向直播间赠送礼物。

        等价于 ``self.bot.send_livestream_gift(self.live_id, gift_id, num)``。

        :param gift_id: 礼物 ID
        :param num: 礼物数量
        :raises RequestFailedException: 当请求失败时
        """
        ...

    @abstractmethod
    async def send_backpack(self, gift_id: int, num: int) -> None:
        """向直播间赠送背包内礼物。

        等价于 ``self.bot.send_livestream_backpack(self.live_id, gift_id, num)``。

        :param gift_id: 礼物 ID
        :param num: 礼物数量
        :raises RequestFailedException: 当请求失败时
        """
        ...

    # ------------------------------------------------------------------ #
    # 管理
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_admin_list(self) -> list[User]:
        """获取直播间管理员列表。

        在创建直播间实例时通过 Meta API 获取并缓存，
        后续调用直接返回 ``User`` 对象列表。

        :return: 管理员 User 列表
        """
        ...
