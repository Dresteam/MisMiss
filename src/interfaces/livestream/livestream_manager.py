"""直播间管理器接口。

定义了管理多个直播间的抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .livestream import Livestream


class LivestreamManager(ABC):
    """直播间管理器接口。

    管理多个 :class:`Livestream` 实例的注册中心。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def livestream_list(self) -> list[Livestream]:
        """获取所有直播间列表。

        :return: 直播间列表
        """
        ...

    @abstractmethod
    def get_livestream(self, live_id: int) -> Livestream:
        """获取某个直播间，如果不存在则自动注册。

        :param live_id: 直播间 ID
        :return: 直播间实例
        """
        ...

    @abstractmethod
    def get_livestream_if_absent(self, live_id: int) -> Optional[Livestream]:
        """获取某个直播间，如果不存在则返回 ``None``。

        :param live_id: 直播间 ID
        :return: 直播间实例或 ``None``
        """
        ...

    @abstractmethod
    def register_new_livestream(self, live_id: int) -> Livestream:
        """注册一个新直播间，并返回该直播间实例。

        :param live_id: 直播间 ID
        :return: 新注册的直播间实例
        """
        ...

    @abstractmethod
    def unregister_livestream(self, livestream: Livestream) -> None:
        """删除一个已经注册的直播间。

        :param livestream: 要删除的直播间
        """
        ...
