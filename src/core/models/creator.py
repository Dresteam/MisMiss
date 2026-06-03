"""直播间创建者（主播）实现。

提供 ``Creator`` 接口的具体实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from interfaces.entity.creator import Creator

if TYPE_CHECKING:
    from interfaces.entity.medal import Medal
    from interfaces.livestream.livestream import Livestream


@dataclass
class LiveCreator(Creator):
    """直播间创建者。

    实现 :class:`Creator` 接口，包含创建者的基本信息和在线状态。
    """

    creator_livestream: Livestream
    creator_id: int
    creator_name: str
    creator_room_medal: Medal | None = None
    creator_intro: str | None = None
    creator_is_online: bool = False

    # ---- User ----

    @property
    def name(self) -> str:
        return self.creator_name

    @property
    def id(self) -> int:
        return self.creator_id

    @property
    def introduction(self) -> Optional[str]:
        return self.creator_intro or ""

    @property
    def icon_url(self) -> Optional[str]:
        return None  # Missevan 未提供创建者头像 URL

    # ---- LiveUser ----

    @property
    def livestream(self) -> Livestream:
        return self.creator_livestream

    @property
    def medal(self) -> Optional[Medal]:
        return self.creator_livestream.medal

    @property
    def is_admin(self) -> bool:
        return True  # 创建者必然是管理员

    # ---- Creator ----

    @property
    def is_online(self) -> bool:
        return self.creator_is_online

    @property
    def room_medal(self) -> Optional[Medal]:
        return self.creator_room_medal

    def set_online(self, online: bool) -> None:
        """更新在线状态。

        :param online: 是否在线
        """
        self.creator_is_online = online
