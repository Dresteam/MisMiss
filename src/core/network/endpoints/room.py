"""房间信息 API。

获取 Missevan 直播间的元数据（房间名、简介、创建者、热度等）。
"""

from __future__ import annotations

from typing import Any

from ..base import API
from ..urls import Urls


class RoomInfoAPI(API):
    """获取直播间信息。

    用法::

        api = RoomInfoAPI(cookie)
        room_data = await api.api(12345)
    """

    async def api(self, live_id: int) -> dict[str, Any]:
        """获取指定直播间的元数据。

        :param live_id: 直播间 ID
        :return: API 响应的 JSON 数据
        :raises CoreApiException: 请求失败时
        """
        return await self._http.get(f"{Urls.ROOM_INFO}{live_id}")
