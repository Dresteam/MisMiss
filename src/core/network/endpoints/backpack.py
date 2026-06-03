"""背包礼物赠送 API。

机器人向 Missevan 直播间赠送背包内礼物。
"""

from __future__ import annotations

from ..base import API
from ..urls import Urls


class BackpackSendAPI(API):
    """赠送背包内礼物。

    用法::

        api = BackpackSendAPI(cookie)
        result = await api.api(12345, gift_id=100, num=1)
    """

    async def api(self, live_id: int, gift_id: int, num: int = 1) -> dict:
        """赠送背包内礼物。

        :param live_id: 直播间 ID
        :param gift_id: 背包中礼物的 ID
        :param num: 礼物数量，默认 1
        :return: API 响应的 JSON 数据
        """
        data = {
            "room_id": live_id,
            "gift_id": gift_id,
            "gift_num": num,
        }
        return await self._http.post(Urls.BACKPACK_SEND, data)
