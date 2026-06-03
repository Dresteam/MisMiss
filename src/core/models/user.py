"""用户数据类型。

提供 ``User``、``LiveUser`` 接口的具体数据类实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from interfaces.entity.user import User
from interfaces.entity.live_user import LiveUser

if TYPE_CHECKING:
    from interfaces.livestream.livestream import Livestream
    from interfaces.entity.medal import Medal


@dataclass
class MissevanUser(User):
    """Missevan 用户数据。

    实现 :class:`User` 接口的具体数据类。
    """

    user_id: int
    username: str
    user_intro: str | None = None
    user_icon: str | None = None

    @property
    def name(self) -> str:
        """用户名。"""
        return self.username

    @property
    def id(self) -> int:
        """用户 ID。"""
        return self.user_id

    @property
    def introduction(self) -> Optional[str]:
        """个人介绍。无时返回 ``""``。"""
        return self.user_intro or ""

    @property
    def icon_url(self) -> Optional[str]:
        """头像 URL。"""
        return self.user_icon


@dataclass
class MissevanLiveUser(LiveUser):
    """Missevan 直播间用户数据。

    实现 :class:`LiveUser` 接口的具体数据类。
    """

    base_user: User
    user_livestream: Livestream
    user_medal: Medal | None = None
    user_is_admin: bool = False

    @property
    def name(self) -> str:
        return self.base_user.name

    @property
    def id(self) -> int:
        return self.base_user.id

    @property
    def introduction(self) -> Optional[str]:
        return self.base_user.introduction

    @property
    def icon_url(self) -> Optional[str]:
        """头像 URL。"""
        return self.base_user.icon_url

    @property
    def livestream(self) -> Livestream:
        return self.user_livestream

    @property
    def medal(self) -> Optional[Medal]:
        return self.user_medal

    @property
    def is_admin(self) -> bool:
        return self.user_is_admin
