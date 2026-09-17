"""用户关注直播间事件接口。"""

from abc import ABC

from ..cancellable import Cancellable
from .livestream_user_event import LivestreamUserEvent


class LiveFollowEvent(Cancellable, LivestreamUserEvent, ABC):
    """用户关注直播间事件。

    继承自 :class:`LivestreamUserEvent`，表示用户关注直播间事件。

    **可取消**：监听器调用 :meth:`~interfaces.event.Cancellable.cancel` 后，
    后续（更低优先级）的监听器收不到该事件。

    .. versionadded:: 1.0
    """
