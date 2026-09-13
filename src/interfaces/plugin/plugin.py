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
    from interfaces.livestream.livestream import Livestream
    from core.plugin.data_manager import PluginDataManager
    from core.server import MissevanServer

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
    - :attr:`data` / :attr:`data_dir` — 数据目录与沙箱化读写器
    - :attr:`_server` — 所属 :class:`~core.server.MissevanServer`

    **生命周期钩子**（均可选覆写）：

    - :meth:`initialize` — 插件加载、注册到事件总线后调用
    - :meth:`terminate` — 插件卸载或禁用前调用，用于清理资源
    - :meth:`on_enable` — 已初始化过的实例被重新启用时调用

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

    _server: "MissevanServer | None" = None
    """所属服务器实例，由 PluginManager 注入。

    可用于查询 :attr:`livestreams` 等；:meth:`register_timer_message`
    也依赖它。未注入时为 ``None``。
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

    async def on_livestream_bound(self, livestream: "Livestream") -> None:
        """账户绑定直播间后调用——注册依赖直播间的资源的正确时机。

        触发时机有两种：

        - 账户**新绑定**直播间时
        - 插件被**启用 / 重新启用**时，若账户已绑定直播间，框架会补发一次

        因此插件不必再靠弹幕事件兜底重试：把 :meth:`register_timer_message`
        等依赖直播间的注册动作放在这里，就能保证「启用时有直播间」与
        「启用后才绑定直播间」两条路径都被覆盖到。

        :param livestream: 已绑定的直播间实例

        .. versionadded:: 1.3
        """

    # ------------------------------------------------------------------ #
    # 定时消息（插件注册的唯一入口）
    # ------------------------------------------------------------------ #

    def register_timer_message(
        self, message: str, *, only_when_live: bool = False
    ) -> str:
        """注册一条定时消息（**插件消息**）。

        这是插件注册定时消息的唯一入口。经此注册的消息会被标记为插件消息，
        与面板添加的普通消息区别对待：

        - **不写入**持久化文件——插件重启后自行重新注册，不会因异常终止
          而在队列里残留、进而在下次启动时重复注册
        - 面板**不可编辑 / 删除 / 上下移动**（但可「跳过」或「立即发送」）
        - 在轮转中**置顶**，与普通消息共用同一个执行指针

        框架会在插件被禁用/挂起/卸载/重载时自动清理其全部插件消息，
        因此插件**不需要**自己保存消息 ID 去反注册——注册动作放在
        :meth:`on_livestream_bound` 里即可，重复启用不会产生重复消息。

        账户尚未绑定直播间时返回空串。正常情况下用 :meth:`on_livestream_bound`
        作为注册时机就不会遇到；若在别处调用则需自行重试。

        :param message: 消息文本
        :param only_when_live: 为 ``True`` 时仅在直播间开播期间发送
        :return: 消息 ID；账户未绑定直播间或 server 未注入时为空串

        .. versionadded:: 1.3
        """
        server = self._server
        if server is None:
            return ""
        return server.register_plugin_timer_message(
            self.name, message, only_when_live=only_when_live
        )

    def unregister_timer_messages(self) -> None:
        """撤销本插件注册的全部定时消息。

        通常无需调用——框架会在插件停用时自动清理。仅当插件需要在运行期间
        主动放弃自己的定时消息时才使用（例如配置变更后准备重新注册）。

        .. versionadded:: 1.3
        """
        server = self._server
        if server is None:
            return
        server.unregister_plugin_timer_messages(self.name)
