"""Missevan 直播间实现。

提供 ``Livestream`` 接口的完整实现，管理直播间的连接、数据刷新、
WebSocket 事件监听和消息/礼物操作。
"""

from __future__ import annotations

from typing import Optional

from interfaces.bot.bot import Bot
from interfaces.entity.creator import Creator
from interfaces.entity.user import User
from interfaces.entity.medal import Medal
from interfaces.event import event_handler, Listener
from interfaces.event.event import Event
from interfaces.event.livestream import LiveOpenEvent, LiveCloseEvent
from interfaces.livestream.livestream import Livestream

from ..network.endpoints.meta import MetaAPI
from ..network.endpoints.room import RoomInfoAPI
from ..events.bus import EventBus
from ..models.creator import LiveCreator
from ..models.medal import RoomMedal
from ..models.user import MissevanUser
from .handler import Live
from ..exceptions import CoreApiException, CoreDisabledException


class MissevanLivestream(Livestream):
    """Missevan 直播间。

    实现 :class:`Livestream` 接口，封装单个直播间的完整生命周期。

    调用 :meth:`join` 进入直播间（刷新数据 + 连接 WebSocket），
    调用 :meth:`quit` 退出直播间（关闭 WebSocket）。

    :param live_id: 直播间 ID
    :param bot: 监听此直播间的机器人
    :param event_bus: 事件总线实例
    """

    def __init__(self, live_id: int, bot: Bot, event_bus: EventBus) -> None:
        self._live_id: int = live_id
        self._bot: Bot = bot
        self._event_bus: EventBus = event_bus

        # 直播间状态
        self._is_connected: bool = False
        self._room_name: str = ""
        self._room_description: str = ""
        self._score: int = -1
        self._creator: Creator | None = None

        # WebSocket
        self._websocket: Live | None = None
        # 启用状态
        self._enabled: bool = True
        # 管理员列表缓存（在 _refresh() 中通过 Meta API 获取）
        self._admin_list: list[User] = []

        # 注册内部监听器 — 监听开播/下播事件以更新状态
        self._event_bus.register_new_event(self._create_internal_listener())

    # ------------------------------------------------------------------ #
    # 启停控制
    # ------------------------------------------------------------------ #

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def _check_enabled(self) -> None:
        """检查是否已启用，停用时抛出异常。

        :raises CoreDisabledException: 直播间已停用
        """
        if not self._enabled:
            raise CoreDisabledException("直播间已停用")

    # ------------------------------------------------------------------ #
    # 属性
    # ------------------------------------------------------------------ #

    @property
    def event_bus(self) -> EventBus:
        """获取此直播间的事件总线。"""
        return self._event_bus

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def live_id(self) -> int:
        return self._live_id

    @property
    def room_name(self) -> str:
        return self._room_name

    @property
    def room_description(self) -> str:
        return self._room_description

    @property
    def score(self) -> int:
        return self._score

    @property
    def creator(self) -> Creator:
        if self._creator is None:
            raise CoreApiException("直播间尚未初始化，请先调用 join()")
        return self._creator

    @property
    def creator_id(self) -> int:
        return self.creator.id

    @property
    def creator_name(self) -> str:
        return self.creator.name

    @property
    def medal(self) -> Optional[Medal]:
        return self.creator.room_medal

    @property
    def bot(self) -> Bot:
        return self._bot

    # ------------------------------------------------------------------ #
    # EventManager 实现
    # ------------------------------------------------------------------ #

    def register_new_event(self, listener: Listener) -> None:
        self._event_bus.register_new_event(listener)

    def unregister_event(self, listener: Listener) -> None:
        self._event_bus.unregister_event(listener)

    def call_event(self, event: Event, clazz: type | None = None) -> None:
        self._event_bus.call_event(event, clazz)

    # ------------------------------------------------------------------ #
    # 直播间操作
    # ------------------------------------------------------------------ #

    async def send_message(self, message: str, priority: int = 0) -> None:
        """向直播间发送消息。

        :param message: 消息文本
        :param priority: 消息优先级（值越大越优先），默认为 0
        :raises CoreDisabledException: 直播间已停用
        """
        self._check_enabled()
        await self._bot.send_livestream_message(
            self._live_id, message, priority
        )

    async def send_gift(self, gift_id: int, num: int) -> None:
        """向直播间赠送礼物。

        :param gift_id: 礼物 ID
        :param num: 礼物数量
        :raises CoreDisabledException: 直播间已停用
        """
        self._check_enabled()
        await self._bot.send_livestream_gift(self._live_id, gift_id, num)

    async def send_backpack(self, gift_id: int, num: int) -> None:
        """向直播间赠送背包内礼物。

        :param gift_id: 礼物 ID
        :param num: 礼物数量
        :raises CoreDisabledException: 直播间已停用
        """
        self._check_enabled()
        await self._bot.send_livestream_backpack(self._live_id, gift_id, num)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def join(self) -> None:
        """进入直播间。

        刷新房间数据并建立 WebSocket 连接。

        :raises CoreDisabledException: 直播间已停用
        """
        self._check_enabled()
        await self._refresh()

        if self._websocket is None:
            self._websocket = self._create_websocket()

        if not self._is_connected:
            await self._websocket.connect()
            self._is_connected = True

    async def quit(self) -> None:
        """退出直播间。

        关闭 WebSocket 连接。

        :raises CoreDisabledException: 直播间已停用
        """
        self._check_enabled()
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
        self._is_connected = False

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    async def _refresh(self) -> None:
        """刷新直播间元数据。"""
        response = await RoomInfoAPI().api(self._live_id)

        if response.get("code") != 0:
            raise CoreApiException(
                response.get("info", "房间信息获取失败")
            )

        info = response.get("info", {})
        room = info.get("room", {})
        creator_data = info.get("creator", {})

        # 房间基本信息
        self._room_name = room.get("name", "")
        self._room_description = room.get("announcement", "")

        # 粉丝勋章
        medal_data = room.get("medal")
        medal: RoomMedal | None = None
        if medal_data and medal_data.get("name"):
            medal = RoomMedal(
                medal_name=medal_data["name"],
                medal_level=0,
            )

        # 创建者
        self._creator = LiveCreator(
            creator_livestream=self,
            creator_id=creator_data.get("user_id", 0),
            creator_name=creator_data.get("username", ""),
            creator_room_medal=medal,
            creator_intro=creator_data.get("introduction", ""),
            creator_is_online=creator_data.get("online", False),
        )

        # 热度
        statistics = room.get("statistics", {})
        self._score = statistics.get("score", -1)

        # 管理员列表（Meta API，仅调用一次）
        try:
            meta = await MetaAPI().api(self._live_id)
            if meta.get("code") == 0:
                members = meta.get("info", {}).get("members", {})
                raw = members.get("admin", [])
                self._admin_list = [
                    MissevanUser(
                        user_id=a.get("user_id", 0),
                        username=a.get("username", ""),
                        user_intro="",
                        user_icon=a.get("iconurl", ""),
                    )
                    for a in raw
                    if isinstance(a, dict)
                ]
        except Exception:
            self._admin_list = []

    def get_admin_list(self) -> list[User]:
        """获取直播间管理员列表。

        在 :meth:`_refresh` 中通过 Meta API 获取并缓存，
        返回 ``User`` 对象列表。

        :return: 管理员 User 列表
        """
        return list(self._admin_list)

    def _create_websocket(self) -> Live:
        """创建 WebSocket 实例。

        :return: Live 实例
        """
        from .handler import Live
        return Live(self)

    def _create_internal_listener(self) -> Listener:
        """创建内部事件监听器。

        监听开播/下播事件以自动更新创建者在线状态。

        :return: 监听器实例
        """
        livestream_ref = self

        class _InternalListener(Listener):
            @event_handler
            def on_open(self, event: LiveOpenEvent) -> None:
                if livestream_ref._creator and hasattr(livestream_ref._creator, "set_online"):
                    livestream_ref._creator.set_online(True)
                # 开播时刷新数据
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(livestream_ref._refresh())
                except RuntimeError:
                    pass

            @event_handler
            def on_close(self, event: LiveCloseEvent) -> None:
                if livestream_ref._creator and hasattr(livestream_ref._creator, "set_online"):
                    livestream_ref._creator.set_online(False)
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(livestream_ref._refresh())
                except RuntimeError:
                    pass

        return _InternalListener()
