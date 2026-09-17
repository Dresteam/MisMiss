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

    # 本类不是 @dataclass，故其注解不会被实现类的 @dataclass 收集为字段
    # （@dataclass 只收集被装饰类自身的注解与 dataclass 基类的字段）。
    # 这个类属性仅作默认值，setter 会在实例上写入同名属性做覆盖。
    _display_name: str | None = None

    @property
    def display_name(self) -> str | None:
        """专属显示名覆盖。

        ``None`` 表示未覆盖，:attr:`User.name` 返回原始用户名。
        监听器可在事件处理中设置它来临时改写该用户的显示名——
        由于事件里的用户对象**每次事件都新建**，覆盖只在当前事件内生效。

        .. versionadded:: 1.3.0
        """
        return self._display_name

    @display_name.setter
    def display_name(self, value: str | None) -> None:
        self._display_name = value

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
