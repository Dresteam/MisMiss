"""服务器接口。

定义了主程序的抽象，管理 Bot、Livestream、Plugin 的生命周期。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interfaces.bot.bot import Bot, BotPermission
    from interfaces.event.event_manager import EventManager
    from interfaces.livestream.livestream import Livestream


class Server(ABC):
    """服务器标准接口。

    管理 Bot、Livestream、Plugin 的中央调度器。
    实现类负责持久化、生命周期和实例管理。

    .. versionadded:: 1.0
    """

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def start(self) -> None:
        """启动服务器——从磁盘加载持久化数据。"""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭服务器——停用所有组件。"""
        ...

    # ------------------------------------------------------------------ #
    # Bot
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def create_bot(
        self,
        cookie: str,
        *,
        permissions: "BotPermission | None" = None,
    ) -> "Bot":
        """创建机器人。

        :param cookie: Cookie 字符串
        :param permissions: 权限集合（创建后不可修改）
        :return: 新创建的 Bot 实例
        """
        ...

    @abstractmethod
    async def update_cookie(self, new_cookie: str) -> "Bot":
        """更换 Bot Cookie——停用旧 Bot 并用新 Cookie 重建。

        :param new_cookie: 新的 Cookie 字符串
        :return: 新创建的 Bot 实例
        """
        ...

    @property
    @abstractmethod
    def bot(self) -> "Bot | None":
        """获取当前 Bot（可能为 None）。"""
        ...

    @property
    @abstractmethod
    def bot_available(self) -> bool:
        """Bot 是否已初始化并可正常使用。

        返回 ``True`` 表示 Bot 已创建且已通过刷新验证。
        """
        ...

    # ------------------------------------------------------------------ #
    # Livestream
    # ------------------------------------------------------------------ #

    @abstractmethod
    def add_livestream(self, live_id: int) -> "Livestream":
        """添加直播间。

        :param live_id: 直播间 ID
        :return: 直播间实例
        """
        ...

    @abstractmethod
    def enable_livestream(self, live_id: int) -> None:
        """启用直播间（不销毁实例）。"""
        ...

    @abstractmethod
    def disable_livestream(self, live_id: int) -> None:
        """停用直播间（不销毁实例）。"""
        ...

    @property
    @abstractmethod
    def livestreams(self) -> "dict[int, Livestream]":
        """获取所有直播间。"""
        ...

    @property
    @abstractmethod
    def event_bus(self) -> "EventManager":
        """获取全局事件总线。"""
        ...

    # ------------------------------------------------------------------ #
    # Plugin
    # ------------------------------------------------------------------ #

    @abstractmethod
    def install_plugin(self, plugin: object) -> None:
        """安装插件（后续扩展）。"""
        ...

    @property
    @abstractmethod
    def plugins(self) -> "list[object]":
        """获取已安装插件列表。"""
        ...
