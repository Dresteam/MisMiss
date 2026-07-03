"""聊天室 Meta API。

获取 Missevan 聊天室的元数据（管理员列表等）。
"""

from __future__ import annotations

from typing import Any

from ..base import API
from ..urls import Urls


class MetaAPI(API):
    """获取聊天室元数据。

    用法::

        api = MetaAPI()
        data = await api.api(12345)
        admins = data.get("info", {}).get("members", {}).get("admin", [])
    """

    async def api(self, room_id: int) -> dict[str, Any]:
        """获取指定聊天室的元数据。

        :param room_id: 直播间（聊天室）ID
        :return: API 响应的 JSON 数据
        :raises CoreApiException: 请求失败时
        """
        return await self._http.get(f"{Urls.CHATROOM_META}{room_id}")
