"""事件监听器标记接口。

定义了事件监听器的抽象。
"""

from abc import ABC


class Listener(ABC):
    """事件监听器标记接口。

    所有事件监听器必须实现此接口。
    监听方法必须是 ``public`` 方法，接受一个 :class:`Event` 参数，
    并用 :func:`event_handler` 装饰器标记。

    用法示例::

        class MyListener(Listener):
            @event_handler
            def on_live_open(self, event: LiveOpenEvent) -> None:
                ...

    .. seealso:: :func:`event_handler`
    .. versionadded:: 1.0
    """
