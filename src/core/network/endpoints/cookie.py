"""默认 Cookie 获取 API。

向 Missevan 的用户信息接口发送空请求，
从响应头中提取 Cookie 字符串。
"""

from __future__ import annotations

from ..base import API
from ..urls import Urls


class DefaultCookieAPI(API):
    """获取默认 Cookie。

    用法::

        api = DefaultCookieAPI()
        cookie = await api.api()
    """

    async def api(self) -> str:
        """获取默认 Cookie。

        :return: Cookie 字符串
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(Urls.DEFAULT_COOKIE)
                if resp.status_code != 200:
                    return ""
                return resp.headers.get("set-cookie")
        except Exception:
            return ""
