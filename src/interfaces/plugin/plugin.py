"""插件接口。

定义了所有插件的抽象基类。
"""

from __future__ import annotations

import contextvars
from abc import ABC
from typing import TYPE_CHECKING

from interfaces.event.listener import Listener
from interfaces.plugin.miss_config import MissConfig

if TYPE_CHECKING:
    from interfaces.plugin.plugin import Plugin as _Plugin
    from core.plugin.data_manager import PluginDataManager

# ------------------------------------------------------------------ #
# 插件上下文 —— 用于在执行事件处理器时追踪当前插件，
# 以便 Bot 方法校验插件级权限
# ------------------------------------------------------------------ #

current_plugin: contextvars.ContextVar["_Plugin | None"] = contextvars.ContextVar(
    "current_plugin", default=None
)
"""当前正在执行事件处理器的插件实例。

由 :class:`~core.events.bus.EventBus` 在调用 handler 前设置、
调用后清除。Bot 方法通过此变量判断调用是否来自某个插件，
并据此校验插件级权限。

用法（内部）::

    plugin = current_plugin.get()
    if plugin is not None:
        # 来自插件调用，校验 plugin.permissions
        ...
"""


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
            async def initialize(self, config: MissConfig) -> None:
                print(f"插件 {self.name} 初始化完成")
                print(f"配置项: {config.get('key', 'default')}")
                # 若事件处理器中也需要配置，自行保存
                self._config = config

            @event_handler
            def on_message(self, event: LiveMessageEvent) -> None:
                print(f"收到消息: {event.message}")
                threshold = self._config.get("threshold", 100)

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

    data: "PluginDataManager | None" = None
    """插件数据文件管理器（:class:`~core.plugin.data_manager.PluginDataManager`）。

    由 PluginManager 在实例化后注入。插件应通过该实例进行所有数据文件
    的读写操作，而非直接使用 ``open()`` / ``json.load()`` 等底层 API。
    管理器确保所有文件操作限制在插件的 ``data_dir`` 目录内（路径沙箱）。

    用法::

        songs = self.data.read_json("playlist.json") or []
        self.data.write_json("playlist.json", songs)
    """

    # ------------------------------------------------------------------ #
    # 构造
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        permissions: dict | None = None,
    ) -> None:
        """初始化插件。

        :param permissions: 插件运行时权限（已合并 ``_permission.json`` 默认值）。
                            由 PluginManager 在加载时自动传入。
        """
        self.permissions: dict | None = permissions
        """插件运行时权限字典（key → bool）。若插件无 ``_permission.json`` 则为 ``None``。

        对标 :class:`~interfaces.bot.bot.BotPermission` Flag，
        每项权限可独立开关，最终生效权限还需取 Bot 实际权限的交集。
        """

    # ------------------------------------------------------------------ #
    # 生命周期钩子
    # ------------------------------------------------------------------ #

    async def initialize(self, config: MissConfig) -> None:
        """插件初始化钩子。

        在插件被 :class:`PluginManager` 加载并注册到事件总线后调用。
        可用于初始化数据库连接、加载资源等异步操作。

        :param config: 插件运行时配置（:class:`MissConfig` 实例），
                       由框架根据 ``_conf_schema.json`` 自动生成并注入。
                       若插件未定义 schema，传入空的 ``MissConfig({})``。

        插件若需在事件处理器中访问配置，应在该方法中将 ``config``
        保存为实例属性（如 ``self._config = config``）。
        """

    async def terminate(self) -> None:
        """插件终止钩子。

        在插件被卸载或禁用前调用，用于释放资源、关闭连接等清理操作。
        """

    async def on_enable(self) -> None:
        """插件重新启用钩子。

        当已初始化过的插件实例被禁用后再次启用时调用
        （首次启用走 :meth:`initialize`，不会调用本方法）。
        用于重新注册定时消息等需要在启用时恢复的资源。

        .. versionadded:: 1.2
        """
