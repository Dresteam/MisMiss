"""可取消事件标记接口。

实现本接口的事件可被监听器取消——取消后事件总线**不再把它传给后续
（更低优先级）的监听器**，即阻止传播。

可取消性由接口层声明（见 ``interfaces/event/livestream/`` 下的各事件类），
只有「用户内容」类事件可取消；开播 / 下播 / 统计属于已发生的事实，不可取消。

用法示例::

    from interfaces.event import event_handler
    from interfaces.event.livestream import LiveMessageEvent

    @event_handler(priority=100)
    def on_message(self, event: LiveMessageEvent) -> None:
        if event.message == "[屏蔽]":
            event.cancel()   # 后续监听器收不到这条弹幕

.. warning::
   取消只对**同步** handler 有效。异步 handler 由事件总线通过
   ``create_task`` 并发调度，其执行时全部 handler 早已派发完毕，
   此时调用 :meth:`cancel` 无法阻断传播。需要取消语义的 handler
   必须写成同步函数（可在其中用 ``asyncio.get_running_loop().create_task(...)``
   发起异步工作）。
"""

from abc import ABC


class Cancellable(ABC):
    """可取消事件标记接口。

    .. versionadded:: 1.3.0
    """

    # 刻意不加类型注解：注解会让 @dataclass 子类把它收成数据字段，
    # 从而影响 __init__ / __eq__ / __repr__。此处的类属性仅作默认值，
    # cancel() 会在实例上写入同名属性做覆盖。
    _cancelled = False

    @property
    def cancelled(self) -> bool:
        """事件是否已被取消。

        :return: 已取消返回 ``True``，否则 ``False``
        """
        return self._cancelled

    def cancel(self) -> None:
        """取消事件，阻止其继续向更低优先级的监听器传播。"""
        self._cancelled = True

    def uncancel(self) -> None:
        """撤销取消，恢复事件的正常传播。"""
        self._cancelled = False
