"""用户发送消息事件接口。"""

from abc import ABC, abstractmethod

from .livestream_user_event import LivestreamUserEvent


class LiveMessageEvent(LivestreamUserEvent, ABC):
    """用户发送消息事件。

    继承自 :class:`LivestreamUserEvent`，表示用户在直播间中发送消息的事件。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def message(self) -> str:
        """获取消息文本内容。

        :return: 消息文本
        """
        ...
