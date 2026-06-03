"""事件标记接口。

定义了所有事件的顶级标记类型。
"""

from abc import ABC


class Event(ABC):
    """事件标记接口。

    所有事件的顶级接口，用于统一的事件类型标识。

    .. versionadded:: 1.0
    """
