"""机器人状态 API。

获取机器人的背包状态、等级、所携带灯牌等信息。
"""

from __future__ import annotations

from typing import Any

from ..base import API
from ..urls import Urls


class BotStatusAPI(API):
    """获取机器人状态。

    返回数据包含 ``info.backpack``（背包礼物列表）、
    ``level``（等级）、``medal``（携带灯牌）等字段。

    用法::

        api = BotStatusAPI(cookie)
        status = await api.api()
    """

    async def api(self) -> dict[str, Any]:
        """获取机器人状态信息。

        :return: API 响应的 JSON 数据
        """
        return await self._http.get(Urls.BOT_STATUS)
