"""提问接口。

定义了直播间提问的抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User
    from ..livestream.livestream import Livestream


class Question(ABC):
    """提问接口。

    表示直播间中的一条付费提问。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def livestream(self) -> Livestream:
        """获取提问所属的直播间。

        :return: 直播间实例
        """
        ...

    @property
    @abstractmethod
    def user(self) -> User:
        """获取提问的用户。

        :return: 提问者用户
        """
        ...

    @property
    def user_id(self) -> int:
        """获取提问者用户 ID。

        等价于 ``self.user.id``。

        :return: 提问者用户 ID
        """
        return self.user.id

    @property
    def user_name(self) -> str:
        """获取提问者用户名。

        等价于 ``self.user.name``。

        :return: 提问者用户名
        """
        return self.user.name

    @property
    @abstractmethod
    def question_id(self) -> str:
        """获取问题 ID。

        问题 ID 为一个十六进制字符串。

        :return: 问题 ID（十六进制字符串）
        """
        ...

    @property
    @abstractmethod
    def text(self) -> str:
        """获取问题文本内容。

        :return: 问题文本
        """
        ...

    @property
    @abstractmethod
    def price(self) -> int:
        """获取问题的出价/价格。

        :return: 问题价格
        """
        ...

    @property
    @abstractmethod
    def status(self) -> int:
        """获取问题状态。

        已知取值：``0`` 表示待回答（pending）。

        :return: 问题状态码
        """
        ...

    @property
    @abstractmethod
    def created_time(self) -> int:
        """获取问题创建时间。

        :return: Unix 毫秒时间戳
        """
        ...

    @property
    @abstractmethod
    def updated_time(self) -> int:
        """获取问题最近更新时间。

        :return: Unix 毫秒时间戳
        """
        ...

    @property
    @abstractmethod
    def likes(self) -> int:
        """获取问题点赞数。

        :return: 点赞数量
        """
        ...

    @property
    @abstractmethod
    def liked(self) -> bool:
        """检查机器人当前用户是否已点赞。

        :return: 已点赞返回 ``True``
        """
        ...
