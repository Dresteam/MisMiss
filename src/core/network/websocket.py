"""直播 WebSocket 客户端。

封装 ``websockets`` 库，实现 Missevan 直播弹幕协议的连接、
Brotli 解压缩、心跳维持和自动重连。
连接时自动通过 :class:`DefaultCookieAPI` 获取 Cookie，无需外部传入。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import brotli
import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed, WebSocketException

from .endpoints.cookie import DefaultCookieAPI
from .urls import Urls
from ..exceptions import CoreWebSocketException


class LiveWebSocket:
    """Missevan 直播弹幕 WebSocket 客户端。

    连接时自动获取默认 Cookie，无需外部传入。

    :meth:`connect` 建立连接后立即返回，消息循环在后台异步运行。
    断连时自动重连（指数退避），重连成功后会重新调用 :meth:`on_open`。
    子类需要实现 :meth:`on_message` 来处理解析后的 JSON 数据。

    :param live_id: 直播间 ID
    """

    HEARTBEAT = "❤️"
    _MAX_RETRIES = 5

    def __init__(self, live_id: int) -> None:
        self._live_id = live_id
        self._ws: ClientConnection | None = None
        self._retry_count = 0
        self._heartbeat_task: asyncio.Task[Any] | None = None
        self._loop_task: asyncio.Task[Any] | None = None
        self._closing: bool = False

    # ------------------------------------------------------------------ #
    # 公共接口
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """建立 WebSocket 连接并启动后台消息循环，立即返回。

        内部自动获取默认 Cookie 构造请求头。
        消息循环作为后台任务运行，断连时自动重连。

        :raises CoreWebSocketException: 首次连接失败
        """
        self._closing = False
        self._retry_count = 0

        await self._do_connect()
        self._start_heartbeat()

        # 子类钩子 —— 连接成功后发送加入房间等初始化消息
        await self.on_open()

        # 消息循环作为后台任务运行，不阻塞调用方
        self._loop_task = asyncio.create_task(self._run_message_loop())

    async def close(self) -> None:
        """正常关闭 WebSocket 连接。

        取消心跳和消息循环后台任务，关闭底层连接。
        """
        self._closing = True
        await self._stop_heartbeat()

        # 取消消息循环任务
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        # 关闭底层连接
        if self._ws is not None:
            try:
                await self._ws.close()
            except WebSocketException:
                pass
            self._ws = None

    # ------------------------------------------------------------------ #
    # 子类钩子
    # ------------------------------------------------------------------ #

    async def on_open(self) -> None:
        """WebSocket 连接成功后的钩子（首次连接和每次重连成功后均会调用）。

        子类可覆写此方法发送初始化消息（如加入房间）。
        """

    async def on_message(self, data: dict[str, Any]) -> None:
        """处理解析后的 JSON 消息。

        子类必须实现此方法。

        :param data: 解析后的 JSON 数据
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # 内部：连接建立
    # ------------------------------------------------------------------ #

    async def _do_connect(self) -> None:
        """实际建立 WebSocket 连接（获取 Cookie + 握手）。"""
        cookie = await self._get_cookie()
        headers = self._build_headers(cookie)

    async def _get_cookie(self) -> str:
        """获取用于 WebSocket 连接的 Cookie。

        优先使用 livestream 关联的 bot cookie（已配置）。
        若不可用则回退到 DefaultCookieAPI。
        """
        # 通过 _livestream 或 _stream 查找关联的 livestream
        for attr in ('_livestream', '_stream'):
            stream = getattr(self, attr, None)
            if stream is not None:
                bot = getattr(stream, '_bot', None)
                if bot is not None:
                    try:
                        c = bot.get_cookie()
                        if c and len(c) > 10:
                            return c
                    except Exception:
                        pass
        return await DefaultCookieAPI().api() or ""

        try:
            self._ws = await websockets.connect(
                f"{Urls.LIVE_WEBSOCKET}{self._live_id}",
                additional_headers=headers,
            )
        except (WebSocketException, OSError) as e:
            raise CoreWebSocketException(f"WebSocket 连接失败: {e}")

    # ------------------------------------------------------------------ #
    # 内部：消息循环（后台任务）
    # ------------------------------------------------------------------ #

    async def _run_message_loop(self) -> None:
        """后台消息循环 —— 自动处理断连与重连。

        作为 ``asyncio.Task`` 运行，不阻塞调用方。
        通过 ``self._closing`` 标志控制退出。
        """
        while not self._closing:
            try:
                await self._message_loop()
            except ConnectionClosed:
                if self._closing:
                    return
                # 断连 → 尝试自动重连
                try:
                    await self._reconnect()
                except CoreWebSocketException:
                    return  # 超过最大重试次数，退出
            except (WebSocketException, asyncio.CancelledError):
                if self._closing:
                    return

    async def _message_loop(self) -> None:
        """单次消息接收循环。"""
        if self._ws is None:
            return

        async for raw in self._ws:
            if isinstance(raw, str):
                if raw != self.HEARTBEAT:
                    data = json.loads(raw)
                    await self.on_message(data)
            elif isinstance(raw, bytes):
                data = self._parse_brotli(raw)
                if data:
                    await self.on_message(data)

    # ------------------------------------------------------------------ #
    # 内部：重连
    # ------------------------------------------------------------------ #

    async def _reconnect(self) -> None:
        """断连后自动重连（指数退避，循环重试，无递归）。"""
        await self._stop_heartbeat()

        while self._retry_count <= self._MAX_RETRIES:
            if self._closing:
                return

            self._retry_count += 1
            delay = 2.0 * self._retry_count
            await asyncio.sleep(delay)

            try:
                await self._do_connect()
                # 重连成功 — 重置计数，恢复心跳，通知子类
                self._retry_count = 0
                self._start_heartbeat()
                await self.on_open()
                return
            except CoreWebSocketException:
                continue  # 重试

        raise CoreWebSocketException("重连失败，已达到最大重试次数")

    # ------------------------------------------------------------------ #
    # 内部：心跳
    # ------------------------------------------------------------------ #

    def _start_heartbeat(self) -> None:
        """启动心跳定时器（每 30 秒发送 ❤️）。"""
        if self._heartbeat_task is not None:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        """停止心跳定时器。"""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """心跳循环。"""
        while True:
            try:
                await asyncio.sleep(30)
                if self._ws is not None:
                    await self._ws.send(self.HEARTBEAT)
            except (asyncio.CancelledError, WebSocketException):
                break

    # ------------------------------------------------------------------ #
    # 内部：Brotli
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_brotli(data: bytes) -> dict[str, Any] | None:
        """解压 Brotli 编码的二进制数据。

        Missevan WebSocket 的二进制消息格式：
        - 第 1 字节：标志位（0x01 = Brotli）
        - 第 2-4 字节：未知
        - 剩余字节：Brotli 压缩的 JSON

        :param data: 原始二进制数据
        :return: 解析后的 JSON 字典，失败返回 ``None``
        """
        if len(data) < 4 or data[0] != 0x01:
            return None

        try:
            payload = data[4:]
            decompressed = brotli.decompress(payload)

            text = decompressed.decode("utf-8")
            if text.startswith("["):
                text = text[1:-1]

            return json.loads(text)  # type: ignore[no-any-return]
        except (brotli.error, json.JSONDecodeError, UnicodeDecodeError):
            return None

    # ------------------------------------------------------------------ #
    # 内部：请求头
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_headers(cookie: str) -> dict[str, str]:
        """构造 WebSocket 连接请求头。

        :param cookie: Cookie 字符串
        :return: 请求头字典
        """
        return {
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Origin": "https://fm.missevan.com",
            "Pragma": "no-cache",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
            ),
            "Cookie": cookie,
        }
