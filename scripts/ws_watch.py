"""直播间 WebSocket 检测工具。

连接指定直播间的弹幕 WebSocket，实时打印收到的消息：
- 自动维持心跳（每 30 秒发送 ❤️，防止连接被服务端断开）
- 每 10 秒输出一次连接健康状态（心跳检测）
- 断线自动重连（指数退避，最多 5 次）
- 重连成功后自动重新加入房间

用法::

    python scripts/ws_watch.py 12345     # 检测直播间 12345
    python scripts/ws_watch.py           # 交互式输入直播间 ID

Cookie 通过 :class:`DefaultCookieAPI` 自动获取（无需登录）。

.. note:: 需在项目根目录运行，脚本会自动将 ``src/`` 加入导入路径。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

# Windows 控制台统一使用 UTF-8，避免中文乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# 将项目 src 加入导入路径（支持从任意目录运行）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.network.websocket import LiveWebSocket  # noqa: E402


def _ts() -> str:
    """当前时间戳，用于控制台输出前缀。"""
    return time.strftime("%H:%M:%S")


class RoomWatcher(LiveWebSocket):
    """观看指定直播间 WebSocket 消息（复用项目的心跳/重连/Brotli 解析）。"""

    async def on_open(self) -> None:
        """连接成功后加入房间。

        首次连接与每次重连成功后都会被调用（基类保证）。
        """
        data = {
            "action": "join",
            "room_id": self._live_id,
            "type": "room",
            "uuid": str(uuid.uuid4()),
        }
        if self._ws:
            await self._ws.send(json.dumps(data))
        print(f"[{_ts()}] ✅ 已加入直播间 {self._live_id}（WS 连接建立）")

    async def on_message(self, data: dict) -> None:
        """打印解析后的原始消息。"""
        msg_type = data.get("type", "")
        event = data.get("event", "")
        print(f"[{_ts()}] 📩 {msg_type}:{event} {json.dumps(data, ensure_ascii=False)}")


async def health_watch(watcher: RoomWatcher, stop: asyncio.Event) -> None:
    """连接健康监测：每 10 秒报告一次心跳/连接状态。"""
    while not stop.is_set():
        await asyncio.sleep(10)
        if watcher._ws is not None:
            print(f"[{_ts()}] 💓 连接正常（心跳自动维持，每 30 秒发送 ❤️）")
        else:
            print(f"[{_ts()}] ⚠️ 连接中断，正在自动重连（指数退避，最多 5 次）")


async def main() -> None:
    parser = argparse.ArgumentParser(description="直播间 WebSocket 检测工具")
    parser.add_argument("live_id", nargs="?", type=int, default=0,
                        help="直播间 ID（缺省时交互式询问）")
    args = parser.parse_args()

    live_id = args.live_id
    if live_id <= 0:
        print("请设置要监听的直播间：")
    while live_id <= 0:
        try:
            raw = input("直播间 ID（回车确认）: ").strip()
        except EOFError:
            print("\n未输入直播间 ID，退出")
            return
        if not raw:
            print("未输入直播间 ID，退出")
            return
        try:
            live_id = int(raw)
        except ValueError:
            print("无效的直播间 ID，请重新输入")
            continue
        if live_id <= 0:
            print("直播间 ID 必须为正整数")

    watcher = RoomWatcher(live_id)
    stop = asyncio.Event()
    health_task = asyncio.create_task(health_watch(watcher, stop))

    print(f"[{_ts()}] 🚀 开始检测直播间 {live_id}，Ctrl+C 退出")
    try:
        await watcher.connect()
        # 消息循环由基类在后台运行，主协程保持存活即可
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[{_ts()}] ❌ 连接失败: {e}")
    finally:
        stop.set()
        health_task.cancel()
        await watcher.close()
        print(f"[{_ts()}] 👋 已退出")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
