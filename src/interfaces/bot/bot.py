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
    内置 **权限控制** 和 **启停控制**：
    每个敏感操作执行前会检查权限和启用状态。

    - 权限不足时抛出 :class:`CorePermissionException`
    - 停用时抛出 :class:`CoreDisabledException`
    - 默认权限：仅 :attr:`~BotPermission.SEND_LIVESTREAM_MESSAGE`
    - 默认状态：已启用

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

        :param value: ``True`` 启用，``False`` 停用
        """
        ...

    # ------------------------------------------------------------------ #
    # 权限控制
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def permissions(self) -> BotPermission:
        """获取当前已授予的权限集合（只读）。

        权限仅在构造时通过 ``permissions`` 参数设置，
        创建后不可修改，以保护 Cookie 等敏感操作。

        :return: 权限标志组合
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
    # 刷新
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def refresh(self) -> None:
        """刷新机器人信息并验证 Cookie 状态。

        从 API 重新获取用户资料（名称、简介、头像等），
        同时检查 Cookie 是否仍然有效。
        Cookie 过期时自动将机器人设为停用状态。

        :raises CoreCookieException: Cookie 已过期
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
