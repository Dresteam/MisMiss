"""用户发送消息事件接口。"""

from abc import ABC, abstractmethod

from ..cancellable import Cancellable
from .livestream_user_event import LivestreamUserEvent


class LiveMessageEvent(Cancellable, LivestreamUserEvent, ABC):
    """用户发送消息事件。

    继承自 :class:`LivestreamUserEvent`，表示用户在直播间中发送消息的事件。

    **可取消**：监听器调用 :meth:`~interfaces.event.Cancellable.cancel` 后，
    后续（更低优先级）的监听器收不到该事件。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def message(self) -> str:
        """获取消息文本内容。

        :return: 消息文本
        """
        ...
