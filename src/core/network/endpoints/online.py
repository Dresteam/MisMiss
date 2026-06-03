"""登录房间 API。

向 Missevan 发送上线请求，用于刷新背包中的礼物状态。
"""

from __future__ import annotations

from typing import Any

from ..base import API
from ..urls import Urls
from ...exceptions import CoreApiException


class OnlineAPI(API):
    """登录直播间（刷新背包）。

    先获取房间信息以确定开播状态，再发送上线请求。

    用法::

        api = OnlineAPI(cookie)
        result = await api.api(12345)
    """

    async def api(self, live_id: int) -> dict[str, Any]:
        """登录直播间。

        先调用 :class:`RoomInfoAPI` 获取房间开播状态，
        再发送上线请求以刷新背包中礼物。

        :param live_id: 直播间 ID
        :return: API 响应的 JSON 数据
        :raises CoreApiException: 无法获取房间状态或请求失败时
        """
        from .room import RoomInfoAPI

        # 获取房间信息以判断开播状态
        room_info = await RoomInfoAPI(self._cookie).api(live_id)

        info = room_info.get("info", {})
        creator = info.get("creator", {})
        online = creator.get("online")

        if online is None:
            raise CoreApiException("无法获取房间状态")

        data = {
            "room_id": live_id,
            "counter": 1 if online else 0,
        }
        return await self._http.post(Urls.ONLINE_API, data)
