"""直播 WebSocket 事件路由。

连接 Missevan WebSocket，将原始 JSON 事件转换为类型化事件数据类
并通过事件总线分发。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from ..models.events import (
    OpenEvent,
    CloseEvent,
    MessageEvent,
    JoinEvent,
    FollowEvent,
    GiftEvent,
)
from ..models.gift import LiveGift
from ..models.user import MissevanUser, MissevanLiveUser
from ..network.websocket import LiveWebSocket

if TYPE_CHECKING:
    from interfaces.entity.medal import Medal
    from .room import MissevanLivestream


class Live(LiveWebSocket):
    """Missevan 直播事件路由器。

    继承 :class:`LiveWebSocket`，解析 WebSocket 消息中的
    ``type`` 和 ``event`` 字段，创建对应的事件数据类并
    通过直播间的事件总线分发。

    :param livestream: 所属的直播间实例
    """

    def __init__(self, livestream: MissevanLivestream) -> None:
        super().__init__(livestream.live_id)
        self._livestream = livestream

    # ------------------------------------------------------------------ #
    # WebSocket 生命周期
    # ------------------------------------------------------------------ #

    async def on_open(self) -> None:
        """WebSocket 连接成功后发送加入房间消息。"""
        data = {
            "action": "join",
            "room_id": self._live_id,
            "type": "room",
            "uuid": str(uuid.uuid4()),
        }
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def on_message(self, data: dict[str, Any]) -> None:
        """处理 Missevan WebSocket 消息。

        根据 ``type`` 和 ``event`` 字段路由到不同类型的事件。

        :param data: 解析后的 JSON 数据
        """
        msg_type = data.get("type", "")
        msg_event = data.get("event", "")
        key = f"{msg_type}:{msg_event}"

        handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            "room:open": self._handle_room_open,
            "room:close": self._handle_room_close,
            "message:new": self._handle_message,
            "message:cross_new": self._handle_message,
            "member:join_queue": self._handle_join_queue,
            "member:followed": self._handle_follow,
            "gift:send": self._handle_gift,
            # 以下事件暂不需要处理
            # "room:join": ...   # 返回自己的个人信息
            # "member:join": ...  # 主播进入房间（触发逻辑未知）
        }

        handler = handlers.get(key)
        if handler:
            handler(data)

    # ------------------------------------------------------------------ #
    # 事件处理
    # ------------------------------------------------------------------ #

    def _handle_room_open(self, data: dict[str, Any]) -> None:
        self._post_event(OpenEvent(event_livestream=self._livestream))

    def _handle_room_close(self, data: dict[str, Any]) -> None:
        self._post_event(CloseEvent(event_livestream=self._livestream))

    def _handle_message(self, data: dict[str, Any]) -> None:
        user = data.get("user", {})
        live_user = self._build_live_user(user)
        msg = data.get("message", "")
        self._post_event(MessageEvent(
            event_livestream=self._livestream,
            event_user=live_user,
            event_message=msg,
        ))

    def _handle_join_queue(self, data: dict[str, Any]) -> None:
        queue: list[dict[str, Any]] = data.get("queue", [])
        for item in queue:
            user_id = item.get("user_id", 0)
            if user_id == 0:
                # 匿名用户
                base_user = MissevanUser(
                    user_id=0, username="匿名用户", user_intro=None, user_icon=None
                )
                live_user = MissevanLiveUser(
                    base_user=base_user,
                    user_livestream=self._livestream,
                    user_medal=None,
                    user_is_admin=False,
                )
            else:
                live_user = self._build_live_user(item)

            self._post_event(JoinEvent(
                event_livestream=self._livestream,
                event_user=live_user,
            ))

    def _handle_follow(self, data: dict[str, Any]) -> None:
        user = data.get("user", {})
        live_user = self._build_live_user(user)
        self._post_event(FollowEvent(
            event_livestream=self._livestream,
            event_user=live_user,
        ))

    def _handle_gift(self, data: dict[str, Any]) -> None:
        user = data.get("user", {})
        live_user = self._build_live_user(user)

        # 幸运礼物
        lucky_data = data.get("lucky")
        lucky: LiveGift | None = None
        if lucky_data:
            lucky = LiveGift(
                gift_livestream=self._livestream,
                gift_user=live_user,
                gift_id=lucky_data.get("gift_id", 0),
                gift_name=lucky_data.get("name", ""),
                gift_price=lucky_data.get("price", 0),
                gift_num=lucky_data.get("num", 0),
                gift_lucky=None,
            )

        gift_data = data.get("gift", {})
        gift = LiveGift(
            gift_livestream=self._livestream,
            gift_user=live_user,
            gift_id=gift_data.get("gift_id", 0),
            gift_name=gift_data.get("name", ""),
            gift_price=gift_data.get("price", 0),
            gift_num=gift_data.get("num", 0),
            gift_lucky=lucky,
        )

        self._post_event(GiftEvent(
            event_livestream=self._livestream,
            event_user=live_user,
            event_gift=gift,
        ))

    # ------------------------------------------------------------------ #
    # 辅助方法
    # ------------------------------------------------------------------ #

    def _post_event(self, event: Any) -> None:
        """通过事件总线分发事件。

        :param event: 事件实例
        """
        self._livestream.event_bus.call_event(event)

    def _build_live_user(self, data: dict[str, Any]) -> MissevanLiveUser:
        """从 JSON 数据构建直播间用户实例。

        :param data: 用户 JSON 数据（含 user_id, username, iconurl, titles）
        :return: 直播间用户
        """
        user_id = data.get("user_id", 0)
        username = data.get("username", "")
        icon_url = data.get("iconurl")

        base_user = MissevanUser(
            user_id=user_id,
            username=username,
            user_intro=None,
            user_icon=icon_url,
        )

        titles = data.get("titles", [])
        medal = self._extract_medal(titles)
        is_admin = self._check_admin(titles)

        return MissevanLiveUser(
            base_user=base_user,
            user_livestream=self._livestream,
            user_medal=medal,
            user_is_admin=is_admin,
        )

    @staticmethod
    def _extract_medal(titles: list[dict[str, Any]]) -> Medal | None:
        """从 titles 数组中提取粉丝勋章。

        :param titles: titles JSON 数组
        :return: 勋章实例或 None
        """
        from ..models.medal import RoomMedal

        if not isinstance(titles, list):
            return None
        for item in titles:
            if isinstance(item, dict) and item.get("type") == "medal":
                return RoomMedal(
                    medal_name=item.get("name", ""),
                    medal_level=item.get("level", 0),
                )
        return None

    @staticmethod
    def _check_admin(titles: list[dict[str, Any]]) -> bool:
        """从 titles 数组中判断是否为管理员。

        管理员的 username 类型 title 颜色为 #FF8686。

        :param titles: titles JSON 数组
        :return: 是否为管理员
        """
        if not isinstance(titles, list):
            return False
        for item in titles:
            if (
                isinstance(item, dict)
                and item.get("type") == "username"
                and item.get("color") == "#FF8686"
            ):
                return True
        return False
