"""直播间用户接口。

定义了直播间中用户的抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from .user import User

if TYPE_CHECKING:
    from ..livestream.livestream import Livestream
    from .medal import Medal


class LiveUser(User, ABC):
    """直播间用户接口。

    继承自 :class:`User`，表示直播间内的一个用户。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def livestream(self) -> Livestream:
        """获取用户所在的直播间。

        :return: 直播间实例
        """
        ...

    @property
    @abstractmethod
    def medal(self) -> Optional[Medal]:
        """获取用户的粉丝勋章。

        :return: 粉丝勋章，若无则返回 ``None``
        """
        ...

    @property
    @abstractmethod
    def is_admin(self) -> bool:
        """检查用户是否为直播间管理员。

        :return: 若为管理员返回 ``True``，否则返回 ``False``
        """
        ...
