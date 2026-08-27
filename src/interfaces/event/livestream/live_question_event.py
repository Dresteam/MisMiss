"""直播间提问事件接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .livestream_user_event import LivestreamUserEvent

if TYPE_CHECKING:
    from ...entity.question import Question


class LiveQuestionEvent(LivestreamUserEvent, ABC):
    """用户发起提问事件。

    继承自 :class:`LivestreamUserEvent`，对应 WebSocket 的
    ``question:ask`` 事件，表示用户在直播间中发起一条付费提问。

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
