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
    子类需要实现 :meth:`on_message` 方法来处理解析后的 JSON 数据。

    :param live_id: 直播间 ID
    """

    HEARTBEAT = "❤️"
    _MAX_RETRIES = 5

    def __init__(self, live_id: int) -> None:
        self._live_id = live_id
        self._ws: ClientConnection | None = None
        self._retry_count = 0
        self._heartbeat_task: asyncio.Task[Any] | None = None

    # ------------------------------------------------------------------ #
    # 公共接口
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """建立 WebSocket 连接并开始接收消息。

        内部自动获取默认 Cookie 构造请求头。

        :raises CoreWebSocketException: 连接失败或达到最大重试次数时
        """
        cookie = await DefaultCookieAPI().api()
        headers = self._build_headers(cookie)

        try:
            self._ws = await websockets.connect(
                f"{Urls.LIVE_WEBSOCKET}{self._live_id}",
                additional_headers=headers,
            )
        except (WebSocketException, OSError) as e:
            raise CoreWebSocketException(f"WebSocket 连接失败: {e}")

        # 启动心跳
        self._start_heartbeat()

        # 进入消息循环
        try:
            await self._message_loop()
        except ConnectionClosed:
            await self._handle_disconnect()

    async def close(self) -> None:
        """正常关闭 WebSocket 连接。"""
        await self._stop_heartbeat()
        if self._ws is not None:
            try:
                await self._ws.close()
            except WebSocketException:
                pass
            self._ws = None

    # ------------------------------------------------------------------ #
    # 子类需实现
    # ------------------------------------------------------------------ #

    async def on_message(self, data: dict[str, Any]) -> None:
        """处理解析后的 JSON 消息。

        子类必须实现此方法。

        :param data: 解析后的 JSON 数据
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # 内部：消息循环
    # ------------------------------------------------------------------ #

    async def _message_loop(self) -> None:
        """消息接收循环。"""
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
    # 内部：重连
    # ------------------------------------------------------------------ #

    async def _handle_disconnect(self) -> None:
        """处理异常断开，尝试自动重连。"""
        await self._stop_heartbeat()
        self._retry_count += 1

        if self._retry_count > self._MAX_RETRIES:
            raise CoreWebSocketException("重连失败，已达到最大重试次数")

        delay = 2.0 * self._retry_count
        await asyncio.sleep(delay)

        try:
            await self.connect()
        except CoreWebSocketException:
            await self._handle_disconnect()

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
