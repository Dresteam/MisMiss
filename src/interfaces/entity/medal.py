"""粉丝勋章接口。

定义了直播平台粉丝勋章的抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Medal(ABC):
    """粉丝勋章接口。

    表示直播间中的粉丝勋章，与用户的粉丝等级挂钩。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """获取粉丝勋章名称。

        :return: 粉丝勋章名称
        """
        ...

    @property
    @abstractmethod
    def level(self) -> int:
        """获取粉丝勋章等级。

        :return: 粉丝勋章等级
        """
        ...
