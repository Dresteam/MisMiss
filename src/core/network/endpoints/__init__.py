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
# 注:猫耳登录相关的端点类曾在这里（passport.py）。已删除 —— 登录接口要求
# X-M-DeviceSign（浏览器指纹签名）、签名会话 Cookie 与表单型 Content-Type,
# 后端无法伪造。参见 web/backend/api/routes/cookie_login.py 的模块说明。
