"""直播间关闭事件接口。"""

from abc import ABC

from .livestream_event import LivestreamEvent


class LiveCloseEvent(LivestreamEvent, ABC):
    """直播间关闭事件。

    继承自 :class:`LivestreamEvent`，表示直播间下播事件。

    .. versionadded:: 1.0
    """
