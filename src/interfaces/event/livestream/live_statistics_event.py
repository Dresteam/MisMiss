"""直播间实时统计事件接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .livestream_event import LivestreamEvent


class LiveStatisticsEvent(LivestreamEvent, ABC):
    """直播间实时统计事件。

    继承自 :class:`LivestreamEvent`，对应 WebSocket 的
    ``room:statistics`` 事件，携带热度、在线人数与 VIP 人数。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def score(self) -> int:
        """获取直播间热度值。

        :return: 热度值
        """
        ...

    @property
    @abstractmethod
    def online(self) -> int:
        """获取直播间当前在线人数。

        :return: 在线人数
        """
        ...

    @property
    @abstractmethod
    def vip(self) -> int:
        """获取直播间当前 VIP 人数。

        :return: VIP 人数
        """
        ...
