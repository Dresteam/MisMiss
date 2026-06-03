"""机器人信息 API。

获取机器人的用户信息（用户 ID、昵称、简介、灯牌等）。
"""

from __future__ import annotations

from typing import Any

from ..base import API
from ..urls import Urls


class BotInfoAPI(API):
    """获取机器人账号信息。

    用法::

        api = BotInfoAPI(cookie)
        bot_data = await api.api()
    """

    async def api(self) -> dict[str, Any]:
        """获取机器人信息。

        :return: API 响应的 JSON 数据
        """
        return await self._http.get(Urls.BOT_INFO)
