"""API 端点层。

封装 Missevan 平台各业务 API 的请求逻辑。
"""

from .backpack import BackpackSendAPI
from .bot_info import BotInfoAPI
from .bot_status import BotStatusAPI
from .cookie import DefaultCookieAPI
from .meta import MetaAPI
from .gift import GiftSendAPI
from .message import MessageSendAPI
from .online import OnlineAPI
from .room import RoomInfoAPI

__all__ = [
    "BackpackSendAPI",
    "BotInfoAPI",
    "BotStatusAPI",
    "MetaAPI",
    "DefaultCookieAPI",
    "GiftSendAPI",
    "MessageSendAPI",
    "OnlineAPI",
    "RoomInfoAPI",
]
