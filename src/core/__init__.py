"""MIST 直播平台机器人框架 —— 核心实现层。

提供 Missevan（猫耳FM）平台的完整实现，包括：

- 网络层: HTTP 客户端、WebSocket 连接、API 端点
- 数据模型: 用户、礼物、勋章、事件类型
- 事件系统: 事件总线
- 机器人层: :class:`MissevanBot`
- 直播间层: :class:`MissevanLivestream`
- 服务器层: :class:`Server`

用法示例::

    from core import Server

    server = Server()
    await server.start()
"""

from .exceptions import (
    CoreApiException,
    CoreWebSocketException,
    CoreCookieException,
    CoreBrotliException,
    CoreDisabledException,
    CorePermissionException,
    CorePluginException,
    CorePluginNotFoundException,
    CorePluginLoadException,
    CorePluginMetadataException,
    CorePluginConfigException,
)
from .bot.mis_bot import MissevanBot
from .events.bus import EventBus
from .livestream.mis_livestream import MissevanLivestream
from .plugin.plugin_manager import PluginManager
from .plugin.config_manager import PluginConfigManager
from .server import MissevanServer, DATA_DIR

__all__ = [
    "CoreApiException",
    "CoreWebSocketException",
    "CoreCookieException",
    "CoreBrotliException",
    "CoreDisabledException",
    "CorePermissionException",
    "CorePluginException",
    "CorePluginNotFoundException",
    "CorePluginLoadException",
    "CorePluginMetadataException",
    "CorePluginConfigException",
    "MissevanBot",
    "EventBus",
    "MissevanLivestream",
    "MissevanServer",
    "DATA_DIR",
    "PluginManager",
    "PluginConfigManager",
]
