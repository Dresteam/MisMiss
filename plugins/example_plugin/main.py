"""示例插件。

监听直播间消息、礼物、开播、下播事件，演示插件基本用法。
"""

from __future__ import annotations

from core.logging import get_logger
from interfaces.plugin import Plugin
from interfaces.event import event_handler
from interfaces.event.livestream import (
    LiveMessageEvent,
    LiveGiftEvent,
    LiveOpenEvent,
    LiveCloseEvent,
    LiveJoinEvent,
)

_log = get_logger(__name__)

class ExamplePlugin(Plugin):
    """示例插件 —— 监听多种直播间事件。"""

    async def initialize(self) -> None:
        """插件初始化 —— 在加载后被 PluginManager 调用。"""
        _log.info("[ExamplePlugin] 示例插件初始化完成！")

    async def terminate(self) -> None:
        """插件终止 —— 在卸载/禁用前被调用。"""
        _log.info("[ExamplePlugin] 示例插件已终止。")

    @event_handler
    def on_open(self, event: LiveOpenEvent) -> None:
        """开播事件。"""
        _log.info(f"[ExamplePlugin] 🔴 直播间 {event.livestream.room_name} 开播了！")

    @event_handler
    def on_close(self, event: LiveCloseEvent) -> None:
        """下播事件。"""
        _log.info(f"[ExamplePlugin] ⚫ 直播间 {event.livestream.room_name} 下播了。")

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        """弹幕消息事件。"""
        _log.info(
            f"[ExamplePlugin] 💬 [{event.livestream.room_name}] "
            f"{event.user.name}: {event.message}"
        )

    @event_handler
    def on_gift(self, event: LiveGiftEvent) -> None:
        """礼物事件。"""
        gift = event.gift
        _log.info(
            f"[ExamplePlugin] 🎁 {event.user.name} 赠送了 "
            f"{gift.num} 个 {gift.name}（价值 {gift.price * gift.num} 电池）"
        )

    @event_handler
    def on_join(self, event: LiveJoinEvent) -> None:
        """用户进入事件。"""
        _log.info(f"[ExamplePlugin] 👋 {event.user.name} 进入了直播间")
