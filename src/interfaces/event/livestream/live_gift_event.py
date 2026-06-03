"""用户赠送礼物事件接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .livestream_user_event import LivestreamUserEvent

if TYPE_CHECKING:
    from ...entity.gift import Gift


class LiveGiftEvent(LivestreamUserEvent, ABC):
    """用户赠送礼物事件。

    继承自 :class:`LivestreamUserEvent`，表示用户在直播间中赠送礼物的事件。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def gift(self) -> Gift:
        """获取礼物。

        :return: 事件礼物
        """
        ...

    @property
    def gift_num(self) -> int:
        """获取礼物数量。

        等价于 ``self.gift.num``。

        :return: 礼物数量
        """
        return self.gift.num
