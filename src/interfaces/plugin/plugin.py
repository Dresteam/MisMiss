"""插件接口。

定义了所有插件的抽象基类。
"""

from __future__ import annotations

from abc import ABC

from interfaces.event.listener import Listener


class Plugin(Listener, ABC):
    """插件基类。

    所有插件必须继承此类。
    由于继承自 :class:`~interfaces.event.listener.Listener`，
    插件可直接使用 :func:`~interfaces.event.event_handler.event_handler`
    装饰器标记事件处理方法，由 :class:`~core.events.bus.EventBus` 自动扫描注册。

    **生命周期钩子**（均可选覆写）：

    - :meth:`initialize` — 插件加载、注册到事件总线后调用
    - :meth:`terminate` — 插件卸载或禁用前调用，用于清理资源

    用法示例::

        from interfaces.plugin import Plugin
        from interfaces.event import event_handler
        from interfaces.event.livestream import LiveMessageEvent

        class MyPlugin(Plugin):
            async def initialize(self) -> None:
                print("插件初始化完成")

            @event_handler
            def on_message(self, event: LiveMessageEvent) -> None:
                print(f"收到消息: {event.message}")

    .. versionadded:: 1.1
    """

    # ------------------------------------------------------------------ #
    # 生命周期钩子
    # ------------------------------------------------------------------ #

    async def initialize(self) -> None:
        """插件初始化钩子。

        在插件被 :class:`PluginManager` 加载并注册到事件总线后调用。
        可用于初始化数据库连接、加载资源等异步操作。
        """

    async def terminate(self) -> None:
        """插件终止钩子。

        在插件被卸载或禁用前调用，用于释放资源、关闭连接等清理操作。
        """
