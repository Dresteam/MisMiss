"""提问数据类型。

提供 ``Question`` 接口的具体数据类实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from interfaces.entity.question import Question

if TYPE_CHECKING:
    from interfaces.entity.user import User
    from interfaces.livestream.livestream import Livestream


@dataclass
class LiveQuestion(Question):
    """直播间中的付费提问。

    用于表示从 WebSocket ``question:ask`` 事件中收到的提问数据。
    字段名带 ``question_`` 前缀以避免与基类抽象 property 同名
    （dataclass 会以 ``getattr`` 探测默认值，同名会引发字段顺序错误）。
    """

    question_livestream: Livestream
    question_user: User
    question_qid: str
    question_text: str
    question_price: int
    question_status: int
    question_created_time: int
    question_updated_time: int
    question_likes: int
    question_liked: bool

    @property
    def livestream(self) -> Livestream:
        return self.question_livestream

    @property
    def user(self) -> User:
        return self.question_user

    @property
    def user_id(self) -> int:
        return self.question_user.id

    @property
    def user_name(self) -> str:
        return self.question_user.name

    @property
    def question_id(self) -> str:
        return self.question_qid

    @property
    def text(self) -> str:
        return self.question_text

    @property
    def price(self) -> int:
        return self.question_price

    @property
    def status(self) -> int:
        return self.question_status

    @property
    def created_time(self) -> int:
        return self.question_created_time

    @property
    def updated_time(self) -> int:
        return self.question_updated_time

    @property
    def likes(self) -> int:
        return self.question_likes

    @property
    def liked(self) -> bool:
        return self.question_liked
