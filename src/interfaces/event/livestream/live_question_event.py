"""直播间提问事件接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..cancellable import Cancellable
from .livestream_user_event import LivestreamUserEvent

if TYPE_CHECKING:
    from ...entity.question import Question


class LiveQuestionEvent(Cancellable, LivestreamUserEvent, ABC):
    """用户发起提问事件。

    继承自 :class:`LivestreamUserEvent`，对应 WebSocket 的
    ``question:ask`` 事件，表示用户在直播间中发起一条付费提问。

    **可取消**：监听器调用 :meth:`~interfaces.event.Cancellable.cancel` 后，
    后续（更低优先级）的监听器收不到该事件。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def question(self) -> Question:
        """获取提问。

        :return: 事件提问
        """
        ...

    @property
    def question_id(self) -> str:
        """获取问题 ID。

        等价于 ``self.question.question_id``。

        :return: 问题 ID
        """
        return self.question.question_id
