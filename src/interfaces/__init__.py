"""MIST 直播平台机器人框架 —— 接口层。

本包定义了框架的全部抽象接口，包括：

- 实体层: :class:`User`, :class:`LiveUser`, :class:`Creator`, :class:`Gift`, :class:`Medal`, :class:`Question`
- 事件层: :class:`Event`, :class:`Listener`, :class:`EventManager`, :func:`event_handler`
- 直播间层: :class:`Livestream`, :class:`LivestreamManager`
- 机器人层: :class:`Bot`
- 异常: :class:`RequestFailedException`, :class:`CookieException`

用法示例::

    from interfaces import Event, Listener, event_handler
    from interfaces.entity import User, LiveUser
    from interfaces.livestream import Livestream

.. versionadded:: 1.0
"""

from .event.event import Event
from .event.listener import Listener
from .event.event_manager import EventManager
from .event.event_handler import event_handler, event_handler as EventHandler
from .exceptions import RequestFailedException

__all__ = [
    "Event",
    "Listener",
    "EventManager",
    "event_handler",
    "EventHandler",
    "RequestFailedException",
]
