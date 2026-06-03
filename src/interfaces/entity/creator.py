"""创建者接口。

定义了直播间创建者（主播）的抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from .live_user import LiveUser

if TYPE_CHECKING:
    from .medal import Medal


class Creator(LiveUser, ABC):
    """创建者接口。

    继承自 :class:`LiveUser`，表示直播间的创建者/主播。

    .. versionadded:: 1.0
    """

    @property
    @abstractmethod
    def is_online(self) -> bool:
        """检查创建者是否在线（即开播状态）。

        :return: 若在线返回 ``True``，否则返回 ``False``
        """
        ...

    @property
    @abstractmethod
    def room_medal(self) -> Optional[Medal]:
        """获取该直播间的粉丝勋章。

        :return: 直播间粉丝勋章，若无则返回 ``None``
        """
        ...
