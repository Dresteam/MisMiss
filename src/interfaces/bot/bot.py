"""机器人接口。

定义了直播机器人的抽象及权限控制机制。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import TYPE_CHECKING

from ..entity.user import User

if TYPE_CHECKING:
    from ..entity.gift import Gift


class BotPermission(Flag):
    """机器人操作权限标志。

    各方法执行前需检查对应权限是否已授予。
    默认只授予 :attr:`SEND_LIVESTREAM_MESSAGE`。
    """

    SEND_LIVESTREAM_MESSAGE = auto()  # 发送直播间消息
    SEND_PRIVATE_MESSAGE = auto()     # 发送私信（后续扩展）
    SEND_BACKPACK_GIFT = auto()       # 赠送背包礼物
    SEND_GIFT = auto()                # 赠送直售礼物
    EXPOSE_COOKIE = auto()            # 暴露 / 获取 Cookie


class Bot(User, ABC):
    """机器人接口。

    继承自 :class:`User`，表示一个直播平台机器人。
    内置 **权限控制机制**：每个敏感操作执行前会检查对应权限，
    权限不足时抛出 :class:`CorePermissionException`。

    默认权限：仅 :attr:`~BotPermission.SEND_LIVESTREAM_MESSAGE`。

    .. versionadded:: 1.0
    """

    # ------------------------------------------------------------------ #
    # 权限控制
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def permissions(self) -> BotPermission:
        """获取当前已授予的权限集合。

        :return: 权限标志组合
        """
        ...

    @permissions.setter
    @abstractmethod
    def permissions(self, value: BotPermission) -> None:
        """设置权限集合。

        :param value: 权限标志组合
        """
        ...

    # ------------------------------------------------------------------ #
    # 消息
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def send_livestream_message(
        self, live_id: int, message: str, priority: int = 0
    ) -> None:
        """向指定直播间发送消息。

        需要权限 :attr:`~BotPermission.SEND_LIVESTREAM_MESSAGE`。

        :param live_id: 直播间 ID
        :param message: 信息文本
        :param priority: 优先级（值越大越优先），默认为 0
        :raises RequestFailedException: 当请求失败时
        :raises PermissionError: 权限不足
        """
        ...

    @abstractmethod
    async def send_private_message(
        self, user_id: int, message: str
    ) -> None:
        """向指定用户发送私信（后续扩展）。

        需要权限 :attr:`~BotPermission.SEND_PRIVATE_MESSAGE`。

        :param user_id: 目标用户 ID
        :param message: 信息文本
        :raises PermissionError: 权限不足
        """
        ...

    # ------------------------------------------------------------------ #
    # 礼物
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def get_backpack_gifts(self, live_id: int) -> list[Gift]:
        """获取机器人背包礼物列表。

        通过直播间 ID 刷新背包状态后返回背包内礼物。

        :param live_id: 直播间 ID，用于刷新背包状态
        :return: 背包礼物列表
        :raises RequestFailedException: 当请求失败时
        """
        ...

    @abstractmethod
    async def send_livestream_gift(
        self, live_id: int, gift_id: int, num: int
    ) -> None:
        """向指定直播间赠送礼物（通过礼物 ID）。

        需要权限 :attr:`~BotPermission.SEND_GIFT`。

        :param live_id: 直播间 ID
        :param gift_id: 礼物 ID
        :param num: 礼物数量
        :raises RequestFailedException: 当请求失败时
        :raises PermissionError: 权限不足
        """
        ...

    @abstractmethod
    async def send_livestream_backpack(
        self, live_id: int, gift_id: int, num: int
    ) -> None:
        """向指定直播间赠送背包内礼物。

        需要权限 :attr:`~BotPermission.SEND_BACKPACK_GIFT`。

        :param live_id: 直播间 ID
        :param gift_id: 礼物 ID
        :param num: 礼物数量
        :raises RequestFailedException: 当请求失败时
        :raises PermissionError: 权限不足
        """
        ...

    # ------------------------------------------------------------------ #
    # Cookie
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_cookie(self) -> str:
        """获取机器人的 Cookie 字符串。

        需要权限 :attr:`~BotPermission.EXPOSE_COOKIE`。
        这是唯一暴露 Cookie 的入口，用于需要原始 Cookie 的场景。

        :return: Cookie 字符串
        :raises PermissionError: 权限不足
        """
        ...
