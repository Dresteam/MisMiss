"""事件监听器装饰器。

定义了标记事件处理方法所需的装饰器。
"""

from typing import Callable, Any


def event_handler(func: Callable[..., Any]) -> Callable[..., Any]:
    """标记一个方法为事件处理方法。

    事件监听器下监听事件的方法均需使用此装饰器标记。

    用法示例::

        class SimpleListener(Listener):
            @event_handler
            def on_message(self, event: LiveMessageEvent) -> None:
                print(f"收到消息: {event.message}")

    :param func: 被装饰的方法
    :return: 原方法（附加了 ``__event_handler__`` 标记）
    :see: :class:`Listener`
    """
    func.__event_handler__ = True
    return func
