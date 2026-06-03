"""实体层接口。

提供直播平台核心实体的抽象接口。
"""

from .user import User
from .live_user import LiveUser
from .creator import Creator
from .gift import Gift
from .medal import Medal
from .question import Question

__all__ = [
    "User",
    "LiveUser",
    "Creator",
    "Gift",
    "Medal",
    "Question",
]
