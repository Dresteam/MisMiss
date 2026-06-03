"""礼物赠送 API。

机器人向 Missevan 直播间赠送直售礼物。
"""

from __future__ import annotations

from ..base import API
from ..urls import Urls


class GiftSendAPI(API):
    """赠送直售礼物。

    用法::

        api = GiftSendAPI(cookie)
        result = await api.api(12345, gift_id=100, num=3)
    """

    async def api(self, live_id: int, gift_id: int, num: int = 1) -> dict:
        """赠送直售礼物。

        :param live_id: 直播间 ID
        :param gift_id: 礼物 ID
        :param num: 礼物数量，默认 1
        :return: API 响应的 JSON 数据
        """
        data = {
            "room_id": live_id,
            "gift_id": gift_id,
            "gift_num": num,
            "combo": 0,
        }
        return await self._http.post(Urls.GIFT_SEND, data)
