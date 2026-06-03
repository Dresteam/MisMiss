"""机器人子包。

提供机器人及其相关异常的定义。
"""

from .bot import Bot, BotPermission
from .cookie_exception import CookieException

__all__ = [
    "Bot",
    "BotPermission",
    "CookieException",
]
