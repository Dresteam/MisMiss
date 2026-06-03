"""事件层接口。

提供事件系统的核心抽象，包括事件标记、监听器、事件管理器和装饰器。
"""

from .event import Event
from .listener import Listener
from .event_manager import EventManager
from .event_handler import event_handler, event_handler as EventHandler

__all__ = [
    "Event",
    "Listener",
    "EventManager",
    "event_handler",
    "EventHandler",
]
