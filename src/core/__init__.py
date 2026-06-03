"""MIST 直播平台机器人框架 —— 核心实现层。

提供 Missevan（猫耳FM）平台的完整实现，包括：

- 网络层: HTTP 客户端、WebSocket 连接、API 端点
- 数据模型: 用户、礼物、勋章、事件类型
- 事件系统: 事件总线
- 机器人层: :class:`MissevanBot`
- 直播间层: :class:`MissevanLivestream`

用法示例::

    from core import MissevanBot, EventBus, MissevanLivestream

    bot = MissevanBot(cookie="...")
    await bot.initialize()

    bus = EventBus()
    livestream = MissevanLivestream(live_id=12345, bot=bot, event_bus=bus)
    await livestream.join()
"""

from .exceptions import (
    CoreApiException,
    CoreWebSocketException,
    CoreCookieException,
    CoreBrotliException,
    CorePermissionException,
)
from .bot.bot import MissevanBot
from .events.bus import EventBus
from .livestream.room import MissevanLivestream

__all__ = [
    "CoreApiException",
    "CoreWebSocketException",
    "CoreCookieException",
    "CoreBrotliException",
    "CorePermissionException",
    "MissevanBot",
    "EventBus",
    "MissevanLivestream",
]
