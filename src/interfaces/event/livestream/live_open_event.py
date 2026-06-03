"""直播间开启事件接口。"""

from abc import ABC

from .livestream_event import LivestreamEvent


class LiveOpenEvent(LivestreamEvent, ABC):
    """直播间开启事件。

    继承自 :class:`LivestreamEvent`，表示直播间开播事件。

    .. versionadded:: 1.0
    """
