"""消息发送 API。

机器人向 Missevan 直播间发送聊天消息。
"""

from __future__ import annotations

import uuid

from ..base import API
from ..urls import Urls


class MessageSendAPI(API):
    """发送直播间消息。

    用法::

        api = MessageSendAPI(cookie)
        result = await api.api(12345, "Hello!")
    """

    async def api(self, live_id: int, message: str) -> dict:
        """发送消息。

        :param live_id: 直播间 ID
        :param message: 消息文本
        :return: API 响应的 JSON 数据
        """
        data = {
            "room_id": live_id,
            "message": message,
            "uuid": str(uuid.uuid4()),
        }
        return await self._http.post(Urls.MESSAGE_SEND, data)
