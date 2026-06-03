"""直播间事件基接口。

定义了所有直播间事件的公共抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from ..event import Event

if TYPE_CHECKING:
    from ...livestream.livestream import Livestream
    from ...bot.bot import Bot


class LivestreamEvent(Event, ABC):
    """直播间事件基接口。

    继承自 :class:`Event`，表示所有与直播间相关的事件的基类型。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def livestream(self) -> Livestream:
        """获取事件涉及的直播间。

        :return: 直播间实例
        """
        ...

    @property
    def bot(self) -> Optional[Bot]:
        """获取事件相关的机器人。

        等价于 ``self.livestream.bot``。

        :return: 机器人实例，若无则返回 ``None``
        """
        return self.livestream.bot
