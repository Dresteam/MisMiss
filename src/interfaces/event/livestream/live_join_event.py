"""用户加入直播间事件接口。"""

from abc import ABC

from .livestream_user_event import LivestreamUserEvent


class LiveJoinEvent(LivestreamUserEvent, ABC):
    """用户加入直播间事件。

    继承自 :class:`LivestreamUserEvent`，表示用户进入直播间事件。

    .. versionadded:: 1.0
    """
