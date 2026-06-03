"""用户接口。

定义了直播平台用户的基本抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class User(ABC):
    """用户接口。

    表示直播平台中的一个用户。匿名用户的用户名字段应为 ``""`` 而非 ``None``。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """获取用户名。

        匿名用户用户名应为 ``""`` 而非 ``None``。

        :return: 用户名
        """
        ...

    @property
    @abstractmethod
    def id(self) -> int:
        """获取用户 ID。

        :return: 用户 ID
        """
        ...

    @property
    @abstractmethod
    def introduction(self) -> Optional[str]:
        """获取用户个人介绍。

        若无个人介绍则返回 ``""`` 而非 ``None``。

        :return: 用户个人介绍
        """
        ...

    @property
    @abstractmethod
    def icon_url(self) -> Optional[str]:
        """获取用户头像链接。

        :return: 用户头像链接
        """
        ...
