"""用户关注直播间事件接口。"""

from abc import ABC

from .livestream_user_event import LivestreamUserEvent


class LiveFollowEvent(LivestreamUserEvent, ABC):
    """用户关注直播间事件。

    继承自 :class:`LivestreamUserEvent`，表示用户关注直播间事件。

    .. versionadded:: 1.0
    """
