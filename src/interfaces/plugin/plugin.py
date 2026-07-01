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

    **注入属性**（由 PluginManager 在实例化后设置）：

    - :attr:`name` — 插件名称
    - :attr:`author` — 插件作者
    - :attr:`plugin_id` — 插件唯一标识（``{author}/{name}``）

    **生命周期钩子**（均可选覆写）：

    - :meth:`initialize` — 插件加载、注册到事件总线后调用
    - :meth:`terminate` — 插件卸载或禁用前调用，用于清理资源

    用法示例::

        from interfaces.plugin import Plugin
        from interfaces.event import event_handler
        from interfaces.event.livestream import LiveMessageEvent

        class MyPlugin(Plugin):
            async def initialize(self) -> None:
                print(f"插件 {self.name} 初始化完成")
                # 可通过 self.config 访问配置

            @event_handler
            def on_message(self, event: LiveMessageEvent) -> None:
                print(f"收到消息: {event.message}")

    .. versionadded:: 1.1
    """

    # ------------------------------------------------------------------ #
    # 注入属性（由 PluginManager 设置）
    # ------------------------------------------------------------------ #

    name: str = ""
    """插件名称，由 PluginManager 从 metadata.yaml 注入。"""

    author: str = ""
    """插件作者，由 PluginManager 从 metadata.yaml 注入。"""

    plugin_id: str = ""
    """插件唯一标识（``{author}/{name}``），由 PluginManager 注入。"""

    data_dir: str = ""
    """插件专属数据目录（``data/{plugin_name}/``），由 PluginManager 注入。

    插件可将自定义数据文件（数据库、缓存等）存储在此目录下。
    目录在插件加载时自动创建，卸载时可通过 ``delete_data=True`` 清理。
    """

    # ------------------------------------------------------------------ #
    # 构造
    # ------------------------------------------------------------------ #

    def __init__(self, config: dict | None = None) -> None:
        """初始化插件。

        :param config: 插件运行时配置（已合并 ``_conf_schema.json`` 默认值）。
                       由 PluginManager 在加载时自动传入。
        """
        self.config: dict | None = config
        """插件运行时配置字典。若插件无 ``_conf_schema.json`` 则为 ``None``。"""

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
