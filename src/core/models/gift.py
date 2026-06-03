"""礼物数据类型。

提供 ``Gift`` 接口的具体数据类实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from interfaces.entity.gift import Gift

if TYPE_CHECKING:
    from interfaces.entity.user import User
    from interfaces.livestream.livestream import Livestream


@dataclass
class BotGift(Gift):
    """背包中的礼物（机器人视角）。

    用于表示机器人背包内的礼物条目。
    """

    gift_bot: User
    gift_id: int
    gift_name: str
    gift_price: int
    gift_num: int

    @property
    def livestream(self) -> Optional[Livestream]:
        return None

    @property
    def user(self) -> User:
        return self.gift_bot

    @property
    def user_id(self) -> int:
        return self.gift_bot.id

    @property
    def user_name(self) -> str:
        return self.gift_bot.name

    @property
    def lucky_gift(self) -> Optional[Gift]:
        return None

    @property
    def is_lucky_gift(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return self.gift_name

    @property
    def id(self) -> int:
        return self.gift_id

    @property
    def price(self) -> int:
        return self.gift_price

    @property
    def num(self) -> int:
        return self.gift_num


@dataclass
class LiveGift(Gift):
    """直播间中送出的礼物。

    用于表示从 WebSocket 事件中收到的礼物数据，
    可包含关联的幸运礼物。
    """

    gift_livestream: Livestream
    gift_user: User
    gift_id: int
    gift_name: str
    gift_price: int
    gift_num: int
    gift_lucky: Gift | None = None

    @property
    def livestream(self) -> Optional[Livestream]:
        return self.gift_livestream

    @property
    def user(self) -> User:
        return self.gift_user

    @property
    def user_id(self) -> int:
        return self.gift_user.id

    @property
    def user_name(self) -> str:
        return self.gift_user.name

    @property
    def lucky_gift(self) -> Optional[Gift]:
        return self.gift_lucky

    @property
    def is_lucky_gift(self) -> bool:
        return self.gift_lucky is not None

    @property
    def name(self) -> str:
        return self.gift_name

    @property
    def id(self) -> int:
        return self.gift_id

    @property
    def price(self) -> int:
        return self.gift_price

    @property
    def num(self) -> int:
        return self.gift_num
