"""默认 Cookie 获取 API。

向 Missevan 的用户信息接口发送请求，从响应头中提取 Cookie 字符串。
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

    async def api(self) -> str | None:
        """获取默认 Cookie。

        :return: Cookie 字符串，获取失败返回 ``None``
        """
        import httpx

        from ..throttle import gate

        # 这个端点绕开了 HTTPClient（要读响应头而不是 body），但**同样要过闸** ——
        # 每次 WebSocket 连接与重连都会调它一次，是重连风暴里实打实的一份流量。
        await gate.acquire()
        headers = self._build_headers()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(Urls.DEFAULT_COOKIE, headers=headers)
                if resp.status_code != 200:
                    gate.note_failure()
                    return None
                gate.note_success()
                return resp.headers.get("set-cookie")
        except Exception as e:
            gate.note_failure(e)
            return None

    @staticmethod
    def _build_headers() -> dict[str, str]:
        """构造与 bot HTTPClient 一致的请求头，避免 CDN 412/403。"""
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": "https://www.missevan.com",
            "Referer": "https://www.missevan.com",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
            ),
        }
