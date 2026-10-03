"""HTTP 客户端封装。

基于 ``httpx`` 提供统一的异步 HTTP 请求能力，
包括默认请求头构造和 Cookie 注入。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from ..exceptions import CoreApiException
from .throttle import gate

# ---------------------------------------------------------------------- #
# 共享连接池
# ---------------------------------------------------------------------- #
# 原先每个请求都 `async with httpx.AsyncClient(...)` 新建再关闭，等于每次都
# 重新做一遍 TCP + TLS 握手 —— 站点是 HTTPS，代价数百毫秒，而且对平台边缘
# 节点来说，同一 IP 反复建连本身就是「像机器人」的特征。
#
# 这里放一个全进程共享的 client。注意 httpx.AsyncClient 与事件循环绑定：
# 生产只有一个循环，但测试里每个用例可能各起一个，所以在「换过循环」时
# 丢弃旧的重新建，而不是硬把一个绑在别的循环上的 client 拿来用。
_shared_client: httpx.AsyncClient | None = None
_shared_client_loop: asyncio.AbstractEventLoop | None = None


def _get_shared_client() -> httpx.AsyncClient:
    """取当前事件循环上的共享 client（必要时新建）。"""
    global _shared_client, _shared_client_loop
    loop = asyncio.get_running_loop()
    if _shared_client is None or _shared_client.is_closed or _shared_client_loop is not loop:
        if _shared_client is not None and not _shared_client.is_closed:
            # 上一个循环留下的，关不掉也没关系（它所属的循环已经没了）
            _shared_client = None
        _shared_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        _shared_client_loop = loop
    return _shared_client


async def aclose_shared_client() -> None:
    """关闭共享 client（进程退出 / 测试收尾时调用）。"""
    global _shared_client, _shared_client_loop
    client, _shared_client, _shared_client_loop = _shared_client, None, None
    if client is not None and not client.is_closed:
        try:
            await client.aclose()
        except Exception:
            pass


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
        # 先过一次全进程闸门：限速 + 平台限流时的全局退避
        await gate.acquire()
        try:
            client = _get_shared_client()
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
                err = CoreApiException(
                    f"HTTP {resp.status_code}: {resp.text[:200]}",
                    status_code=resp.status_code,
                )
                gate.note_failure(err)
                raise err

            result: dict[str, Any] = resp.json()
            # 平台把错误写在 body 里（code != 0）而不是 HTTP 状态码，所以这里也要判。
            #
            # ⚠️ 但**不能**把非零业务码一律当成失败：那等于把「平台正常应答但业务
            # 拒绝」也算进限流计数。给未开播房间发消息返回的「主播休息」就是典型
            # —— 平台明明好好回复了我们。32 个账户发定时消息，8 次就攒满阈值，
            # 闸门于是反复进入全局退避，把欢迎消息这类实时消息一并压后几十秒。
            # （线上就这么发生过：加入事件实时到达，欢迎语却迟迟不发。）
            #
            # 只有**确实表明被限流**的才计入失败，其余按成功处理 —— 能拿到规范
            # 应答本身就说明链路是通的。
            err = CoreApiException(str(result.get("info", "")))
            if result.get("code") == 0 or not gate.is_rate_limit_error(err):
                gate.note_success()
            else:
                gate.note_failure(err)
            return result

        except httpx.TimeoutException:
            gate.note_failure()
            raise CoreApiException("请求超时")
        except httpx.HTTPError as e:
            gate.note_failure(e)
            raise CoreApiException(f"HTTP 请求失败: {e}")
        except json.JSONDecodeError:
            gate.note_failure()
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
