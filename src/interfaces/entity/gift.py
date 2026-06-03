"""礼物接口。

定义了直播平台礼物的抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User
    from ..livestream.livestream import Livestream


class Gift(ABC):
    """礼物接口。

    表示直播平台中的一个礼物，包含赠送者、礼物属性等信息。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def livestream(self) -> Optional[Livestream]:
        """获取礼物所在的直播间。

        :return: 直播间实例，若未关联则返回 ``None``
        """
        ...

    @property
    @abstractmethod
    def user(self) -> User:
        """获取赠送礼物的用户。

        :return: 赠送者用户
        """
        ...

    @property
    def user_id(self) -> int:
        """获取赠送者用户 ID。

        等价于 ``self.user.id``。

        :return: 赠送者用户 ID
        """
        return self.user.id

    @property
    def user_name(self) -> str:
        """获取赠送者用户名。

        等价于 ``self.user.name``。

        :return: 赠送者用户名
        """
        return self.user.name

    @property
    @abstractmethod
    def lucky_gift(self) -> Optional[Gift]:
        """获取幸运礼物。

        如果当前礼物是某幸运礼物的中奖结果，此属性返回原始幸运礼物。

        :return: 原始幸运礼物，若非幸运礼物结果则返回 ``None``
        """
        ...

    @property
    @abstractmethod
    def is_lucky_gift(self) -> bool:
        """检查是否为幸运礼物。

        :return: 若为幸运礼物返回 ``True``，否则返回 ``False``
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """获取礼物名称。

        :return: 礼物名称
        """
        ...

    @property
    @abstractmethod
    def id(self) -> int:
        """获取礼物 ID。

        :return: 礼物 ID
        """
        ...

    @property
    @abstractmethod
    def price(self) -> int:
        """获取礼物价值（通常为电池数或等价货币）。

        :return: 礼物价值
        """
        ...

    @property
    @abstractmethod
    def num(self) -> int:
        """获取礼物数量。

        :return: 礼物数量
        """
        ...
