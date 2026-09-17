"""事件监听器装饰器。

定义了标记事件处理方法所需的装饰器。
"""

from typing import Any, Callable, Optional


def event_handler(
    func: Optional[Callable[..., Any]] = None,
    *,
    priority: int = 0,
) -> Any:
    """标记一个方法为事件处理方法。

    事件监听器下监听事件的方法均需使用此装饰器标记。

    用法示例::

        class SimpleListener(Listener):
            @event_handler
            def on_message(self, event: LiveMessageEvent) -> None:
                print(f"收到消息: {event.message}")

            # 值越大越先收到事件；同优先级按注册顺序
            @event_handler(priority=100)
            def on_gift(self, event: LiveGiftEvent) -> None:
                ...

    :param func: 被装饰的方法（裸用 ``@event_handler`` 时由装饰器自动传入）
    :param priority: 分发优先级，**值越大越先执行**，默认 ``0``。
        同优先级按 ``(MRO 顺序, 注册顺序)`` 排列——即默认行为与未引入
        优先级之前完全一致
    :return: 原方法（附加 ``__event_handler__`` 与
        ``__event_handler_priority__`` 标记）
    :see: :class:`Listener`
    """

    def _wrap(target: Callable[..., Any]) -> Callable[..., Any]:
        # 用 setattr 而非属性赋值——Callable 类型上直接赋值会被 mypy 判为
        # attr-defined（函数对象挂自定义属性是运行时约定，类型系统无从得知）
        setattr(target, "__event_handler__", True)
        setattr(target, "__event_handler_priority__", int(priority))
        return target

    # 裸用法 @event_handler：func 即被装饰的方法
    # 带参用法 @event_handler(priority=N)：返回装饰器等待方法传入
    return _wrap(func) if func is not None else _wrap
