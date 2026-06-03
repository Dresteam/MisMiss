"""直播间事件数据类型。

定义从 Missevan WebSocket 事件中解析出的具体事件数据类。
每个类实现对应的 :mod:`interfaces.event.livestream` 接口。
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

if TYPE_CHECKING:
    from interfaces.bot.bot import Bot
    from interfaces.entity.gift import Gift
    from interfaces.entity.live_user import LiveUser
    from interfaces.livestream.livestream import Livestream


@dataclass
class OpenEvent(LiveOpenEvent):
    """直播间开播事件。"""

    event_livestream: Livestream

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

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

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @property
    def message(self) -> str:
        return self.event_message


@dataclass
class JoinEvent(LiveJoinEvent):
    """用户加入直播间事件。"""

    event_livestream: Livestream
    event_user: LiveUser

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user


@dataclass
class FollowEvent(LiveFollowEvent):
    """用户关注直播间事件。"""

    event_livestream: Livestream
    event_user: LiveUser

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user


@dataclass
class GiftEvent(LiveGiftEvent):
    """用户赠送礼物事件。"""

    event_livestream: Livestream
    event_user: LiveUser
    event_gift: Gift

    @property
    def livestream(self) -> Livestream:
        return self.event_livestream

    @property
    def bot(self) -> Bot:
        return self.event_livestream.bot

    @property
    def user(self) -> LiveUser:
        return self.event_user

    @property
    def gift(self) -> Gift:
        return self.event_gift

    @property
    def gift_num(self) -> int:
        return self.event_gift.num
