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
from .throttle import Lane, gate

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


def _platform_business_code(resp: httpx.Response) -> int | None:
    """响应体里能解析出平台业务码时返回它，否则 ``None``。

    猫耳的错误体形如 ``{"code":500030011,"info":"…"}``；而边缘节点 / 网关的
    拒绝（Cloudflare 页面、502 之类）是 HTML —— 两者必须区别对待：
    前者说明平台在正常工作，后者才是链路出了问题。
    """
    try:
        body = resp.json()
    except Exception:
        return None
    if isinstance(body, dict) and isinstance(body.get("code"), int):
        return body["code"]
    return None


class HTTPClient:
    """异步 HTTP 客户端。

    封装 ``httpx.AsyncClient``，自动附加 Missevan 所需的请求头。

    :param cookie: Cookie 字符串
    :param lane: 流量类别 —— 决定这次请求走哪条闸门车道（见
        :class:`core.network.throttle.Lane`）。后台轮询不该和发消息共用一条车道。
    """

    def __init__(self, cookie: str = "", lane: Lane = Lane.INTERACTIVE) -> None:
        self._cookie = cookie
        self._lane = lane

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
        # 进退避日志时用它标注「是哪个请求失败的」。
        # **去掉查询串**：有些端点把 token 拼在 query 里，原样打进日志
        # 等于把凭据留在磁盘上。
        where = f"{method} {url.split('?', 1)[0]}"

        # 过一次全进程闸门：出发间隔 + **在途并发上限** + 平台限流时的全局退避。
        #
        # ⚠️ 必须走 slot 而不是 acquire：acquire 只管「出发时刻」的间隔，不限制
        # 同时在途的请求数 —— 一批积压请求会被摊成每 0.1 秒出发一个、但**一起在途**，
        # 平台看到的就是几十条并发连接。这正是被封 IP 的形态。
        async with gate.slot(self._lane):
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
                    # ⚠️ **平台把「业务拒绝」也放在非 200 上返回**：给未开播的房间
                    # 发消息拿到的是 HTTP 400 + {"code":500030011,"info":"主播休息…"}。
                    # 那与「200 + 非零业务码」是同一件事 —— 平台规规矩矩回了业务码，
                    # 说明链路是通的，这不是负载信号，必须走同一套判定。
                    #
                    # 原来这里只看状态码就记失败，于是主播休息期间**每发一条消息攒一次
                    # 失败**，8 次就把整条交互车道熔断 —— 线上整夜退避、观众看得见的
                    # 欢迎语被压后几十秒到十几分钟，根因就在这一行。
                    #
                    # 只有「连规范应答都拿不到」才算失败：边缘节点 HTML 拒绝、5xx。
                    benign = (
                        400 <= resp.status_code < 500
                        and _platform_business_code(resp) is not None
                        and not gate.is_rate_limit_error(err)
                    )
                    if benign:
                        gate.note_success(self._lane)
                    else:
                        gate.note_failure(err, where, self._lane)
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
                    gate.note_success(self._lane)
                else:
                    gate.note_failure(err, where, self._lane)
                return result

            except httpx.TimeoutException:
                gate.note_failure(None, f"{where}（超时）", self._lane)
                raise CoreApiException("请求超时")
            except httpx.HTTPError as e:
                gate.note_failure(e, where, self._lane)
                raise CoreApiException(f"HTTP 请求失败: {e}")
            except json.JSONDecodeError:
                gate.note_failure(None, f"{where}（响应不是 JSON）", self._lane)
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
