"""HTTP 客户端封装。

基于 ``httpx`` 提供统一的异步 HTTP 请求能力，
包括默认请求头构造和 Cookie 注入。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..exceptions import CoreApiException


class HTTPClient:
    """异步 HTTP 客户端。

    封装 ``httpx.AsyncClient``，自动附加 Missevan 所需的请求头。

    :param cookie: Cookie 字符串
    """

    def __init__(self, cookie: str = "") -> None:
        self._cookie = cookie

    # ------------------------------------------------------------------ #
    # 公共方法
    # ------------------------------------------------------------------ #

    async def get(self, url: str) -> dict[str, Any]:
        """发送 GET 请求并返回解析后的 JSON。

        :param url: 请求地址
        :return: 响应 JSON
        :raises CoreApiException: 请求失败时
        """
        return await self._request("GET", url)

    async def post(self, url: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 POST 请求并返回解析后的 JSON。

        :param url: 请求地址
        :param data: 请求体（JSON 序列化）
        :return: 响应 JSON
        :raises CoreApiException: 请求失败时
        """
        return await self._request("POST", url, data)

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    async def _request(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行 HTTP 请求并处理异常。

        :param method: 请求方法（GET / POST）
        :param url: 请求地址
        :param data: 请求体
        :return: 响应 JSON
        :raises CoreApiException: 统一异常
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self._build_headers()
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                else:
                    resp = await client.post(
                        url,
                        headers=headers,
                        content=json.dumps(data) if data else "",
                    )

                if resp.status_code != 200:
                    raise CoreApiException(
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                return resp.json()  # type: ignore[no-any-return]

        except httpx.TimeoutException:
            raise CoreApiException("请求超时")
        except httpx.HTTPError as e:
            raise CoreApiException(f"HTTP 请求失败: {e}")
        except json.JSONDecodeError:
            raise CoreApiException("JSON 解析失败")

    def _build_headers(self) -> dict[str, str]:
        """构造 Missevan API 所需的默认请求头。

        :return: 请求头字典
        """
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://www.missevan.com",
            "Referer": "https://www.missevan.com",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Sec-Ch-Ua": (
                '"Chromium";v="128", "Not;A=Brand";v="24", '
                '"Microsoft Edge";v="128"'
            ),
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Cache-Control": "no-cache",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0"
            ),
            "Cookie": self._cookie,
        }
