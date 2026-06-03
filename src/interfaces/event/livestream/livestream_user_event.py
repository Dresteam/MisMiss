"""直播间用户事件基接口。

定义了所有涉及用户交互的直播间事件的公共抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .livestream_event import LivestreamEvent

if TYPE_CHECKING:
    from ...entity.live_user import LiveUser


class LivestreamUserEvent(LivestreamEvent, ABC):
    """直播间用户事件基接口。

    继承自 :class:`LivestreamEvent`，表示涉及用户交互的直播间事件。
    注意：通过此事件获取的用户实例上，
    :meth:`LiveUser.introduction` 可能返回 ``None``。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def user(self) -> LiveUser:
        """获取事件涉及的用户。

        :return: 直播间用户实例
        """
        ...
