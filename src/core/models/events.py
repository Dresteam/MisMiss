"""直播间事件数据类型。

定义从 Missevan WebSocket 事件中解析出的具体事件数据类。
每个类实现对应的 :mod:`interfaces.event.livestream` 接口。

**属性可写性**：凡直接映射到某个 ``event_*`` 字段的属性都提供 setter，
监听器可据此改写事件参数（如 ``event.message = "改写后的内容"``），
改动对后续（更低优先级）的监听器可见。
派生属性（``bot`` / ``gift_num`` / ``question_id``）不提供 setter。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from interfaces.event.livestream.live_open_event import LiveOpenEvent
from interfaces.event.livestream.live_close_event import LiveCloseEvent
from interfaces.event.livestream.live_join_event import LiveJoinEvent
from interfaces.event.livestream.live_follow_event import LiveFollowEvent
from interfaces.event.livestream.live_message_event import LiveMessageEvent
from interfaces.event.livestream.live_gift_event import LiveGiftEvent
from interfaces.event.livestream.live_question_event import LiveQuestionEvent
from interfaces.event.livestream.live_statistics_event import LiveStatisticsEvent
from interfaces.event.livestream.live_cross_message_event import LiveCrossMessageEvent
from interfaces.event.livestream.live_cross_gift_event import LiveCrossGiftEvent

if TYPE_CHECKING:
    from interfaces.bot.bot import Bot
    from interfaces.entity.gift import Gift
    from interfaces.entity.live_user import LiveUser
    from interfaces.entity.question import Question
    from interfaces.livestream.livestream import Livestream


@dataclass
class OpenEvent(LiveOpenEvent):
    """直播间开播事件。"""

    event_livestream: Livestream

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot


@dataclass
class CloseEvent(LiveCloseEvent):
    """直播间下播事件。"""

    event_livestream: Livestream

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot


@dataclass
class MessageEvent(LiveMessageEvent):
    """用户发送消息事件。"""

    event_livestream: Livestream
    event_user: LiveUser
    event_message: str

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @user.setter
    def user(self, value: LiveUser) -> None:
        self.event_user = value

    @property
    def message(self) -> str:
        return self.event_message

    @message.setter
    def message(self, value: str) -> None:
        self.event_message = value


@dataclass
class JoinEvent(LiveJoinEvent):
    """用户加入直播间事件。"""

    event_livestream: Livestream
    event_user: LiveUser

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @user.setter
    def user(self, value: LiveUser) -> None:
        self.event_user = value


@dataclass
class FollowEvent(LiveFollowEvent):
    """用户关注直播间事件。"""

    event_livestream: Livestream
    event_user: LiveUser

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @user.setter
    def user(self, value: LiveUser) -> None:
        self.event_user = value


@dataclass
class GiftEvent(LiveGiftEvent):
    """用户赠送礼物事件。"""

    event_livestream: Livestream
    event_user: LiveUser
    event_gift: Gift

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @user.setter
    def user(self, value: LiveUser) -> None:
        self.event_user = value

    @property
    def gift(self) -> Gift:
        return self.event_gift

    @gift.setter
    def gift(self, value: Gift) -> None:
        self.event_gift = value

    @property
    def gift_num(self) -> int:
        return self.event_gift.num


@dataclass
class QuestionEvent(LiveQuestionEvent):
    """用户发起提问事件。"""

    event_livestream: Livestream
    event_user: LiveUser
    event_question: Question

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @user.setter
    def user(self, value: LiveUser) -> None:
        self.event_user = value

    @property
    def question(self) -> Question:
        return self.event_question

    @question.setter
    def question(self, value: Question) -> None:
        self.event_question = value

    @property
    def question_id(self) -> str:
        return self.event_question.question_id


@dataclass
class StatisticsEvent(LiveStatisticsEvent):
    """直播间实时统计事件。"""

    event_livestream: Livestream
    event_score: int
    event_online: int
    event_vip: int

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def score(self) -> int:
        return self.event_score

    @score.setter
    def score(self, value: int) -> None:
        self.event_score = value

    @property
    def online(self) -> int:
        return self.event_online

    @online.setter
    def online(self, value: int) -> None:
        self.event_online = value

    @property
    def vip(self) -> int:
        return self.event_vip

    @vip.setter
    def vip(self, value: int) -> None:
        self.event_vip = value


@dataclass
class CrossMessageEvent(LiveCrossMessageEvent):
    """跨房弹幕消息事件（连麦时对方直播间的弹幕）。"""

    event_livestream: Livestream
    event_user: LiveUser
    event_message: str
    event_origin_room_id: int = 0
    event_origin_creator_id: int = 0
    event_origin_creator_name: str = ""
    event_origin_creator_icon: str | None = None

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @user.setter
    def user(self, value: LiveUser) -> None:
        self.event_user = value

    @property
    def message(self) -> str:
        return self.event_message

    @message.setter
    def message(self, value: str) -> None:
        self.event_message = value

    @property
    def origin_room_id(self) -> int:
        return self.event_origin_room_id

    @origin_room_id.setter
    def origin_room_id(self, value: int) -> None:
        self.event_origin_room_id = value

    @property
    def origin_creator_id(self) -> int:
        return self.event_origin_creator_id

    @origin_creator_id.setter
    def origin_creator_id(self, value: int) -> None:
        self.event_origin_creator_id = value

    @property
    def origin_creator_name(self) -> str:
        return self.event_origin_creator_name

    @origin_creator_name.setter
    def origin_creator_name(self, value: str) -> None:
        self.event_origin_creator_name = value

    @property
    def origin_creator_icon(self) -> str | None:
        return self.event_origin_creator_icon

    @origin_creator_icon.setter
    def origin_creator_icon(self, value: str | None) -> None:
        self.event_origin_creator_icon = value


@dataclass
class CrossGiftEvent(LiveCrossGiftEvent):
    """跨房礼物事件（大厅中赠送给非主麦的礼物）。"""

    event_livestream: Livestream
    event_user: LiveUser
    event_gift: Gift
    event_target_room_id: int = 0
    event_target_creator_id: int = 0
    event_target_creator_name: str = ""
    event_target_creator_icon: str | None = None

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @livestream.setter
    def livestream(self, value: Livestream) -> None:
        self.event_livestream = value

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @user.setter
    def user(self, value: LiveUser) -> None:
        self.event_user = value

    @property
    def gift(self) -> Gift:
        return self.event_gift

    @gift.setter
    def gift(self, value: Gift) -> None:
        self.event_gift = value

    @property
    def gift_num(self) -> int:
        return self.event_gift.num

    @property
    def target_room_id(self) -> int:
        return self.event_target_room_id

    @target_room_id.setter
    def target_room_id(self, value: int) -> None:
        self.event_target_room_id = value

    @property
    def target_creator_id(self) -> int:
        return self.event_target_creator_id

    @target_creator_id.setter
    def target_creator_id(self, value: int) -> None:
        self.event_target_creator_id = value

    @property
    def target_creator_name(self) -> str:
        return self.event_target_creator_name

    @target_creator_name.setter
    def target_creator_name(self, value: str) -> None:
        self.event_target_creator_name = value

    @property
    def target_creator_icon(self) -> str | None:
        return self.event_target_creator_icon

    @target_creator_icon.setter
    def target_creator_icon(self, value: str | None) -> None:
        self.event_target_creator_icon = value
