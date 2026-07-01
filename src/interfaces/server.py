"""服务器接口。

定义了主程序的抽象，管理 Bot、Livestream、Plugin 的生命周期。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from interfaces.bot.bot import Bot, BotPermission
    from interfaces.event.event_manager import EventManager
    from interfaces.livestream.livestream import Livestream
    from interfaces.plugin.plugin_metadata import PluginMetadata


class Server(ABC):
    """服务器标准接口。

    管理 Bot、Livestream、Plugin 的中央调度器。
    实现类负责持久化、生命周期和实例管理。

    .. versionadded:: 1.0
    """

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def start(self) -> None:
        """启动服务器——从磁盘加载持久化数据。"""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭服务器——停用所有组件。"""
        ...

    # ------------------------------------------------------------------ #
    # Bot
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def create_bot(
        self,
        cookie: str,
        *,
        permissions: "BotPermission | None" = None,
    ) -> "Bot":
        """创建机器人。

        :param cookie: Cookie 字符串
        :param permissions: 权限集合（创建后不可修改）
        :return: 新创建的 Bot 实例
        """
        ...

    @abstractmethod
    async def update_cookie(self, new_cookie: str) -> "Bot":
        """更换 Bot Cookie——停用旧 Bot 并用新 Cookie 重建。

        :param new_cookie: 新的 Cookie 字符串
        :return: 新创建的 Bot 实例
        """
        ...

    @property
    @abstractmethod
    def bot(self) -> "Bot | None":
        """获取当前 Bot（可能为 None）。"""
        ...

    @property
    @abstractmethod
    def bot_available(self) -> bool:
        """Bot 是否已初始化并可正常使用。

        返回 ``True`` 表示 Bot 已创建且已通过刷新验证。
        """
        ...

    @abstractmethod
    async def verify_bot(self) -> bool:
        """主动验证 Bot Cookie 是否有效（发起网络请求）。

        与 :meth:`bot_available` 不同，此方法会发起实际的 API 请求
        来验证当前 Cookie 是否仍然有效。

        :return: Cookie 有效返回 ``True``，过期或网络错误返回 ``False``
        """
        ...

    # ------------------------------------------------------------------ #
    # Livestream
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def add_livestream(self, live_id: int) -> "Livestream":
        """添加直播间。

        添加前会主动验证 Bot Cookie 是否有效。

        :param live_id: 直播间 ID
        :return: 直播间实例
        """
        ...

    @abstractmethod
    def enable_livestream(self, live_id: int) -> None:
        """启用直播间（不销毁实例）。"""
        ...

    @abstractmethod
    def disable_livestream(self, live_id: int) -> None:
        """停用直播间（不销毁实例）。"""
        ...

    @property
    @abstractmethod
    def livestreams(self) -> "dict[int, Livestream]":
        """获取所有直播间。"""
        ...

    @property
    @abstractmethod
    def event_bus(self) -> "EventManager":
        """获取全局事件总线。"""
        ...

    # ------------------------------------------------------------------ #
    # Plugin
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def install_plugin(self, plugin_name: str) -> "PluginMetadata":
        """安装并加载插件。

        扫描 ``plugins/`` 目录，加载指定插件模块，注册事件处理器。

        :param plugin_name: 插件目录名或 metadata.yaml 中声明的 name
        :return: 插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        :raises CorePluginLoadException: 插件加载失败
        """
        ...

    @abstractmethod
    async def install_plugin_from_url(self, url: str) -> "PluginMetadata":
        """从远程 URL 下载并安装插件。

        :param url: 插件 zip 包的远程 URL
        :return: 插件元数据
        :raises CorePluginInstallException: 安装失败
        """
        ...

    @abstractmethod
    async def install_plugin_from_local(self, path: str) -> "PluginMetadata":
        """从本地路径安装插件。

        :param path: 本地 zip 文件或目录路径
        :return: 插件元数据
        :raises CorePluginInstallException: 安装失败
        """
        ...

    @abstractmethod
    async def uninstall_plugin(
        self,
        plugin_name: str,
        delete_config: bool = False,
        delete_data: bool = False,
    ) -> None:
        """卸载插件，可选删除配置和插件目录。

        :param plugin_name: 插件名称
        :param delete_config: 是否删除配置文件
        :param delete_data: 是否删除插件目录
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @abstractmethod
    async def reload_plugin(self, plugin_name: str) -> "PluginMetadata":
        """重载插件。

        :param plugin_name: 插件名称
        :return: 新的插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @abstractmethod
    async def enable_plugin(self, plugin_name: str) -> None:
        """启用一个已加载但被禁用的插件。

        将插件重新注册到事件总线并更新持久化状态。

        :param plugin_name: 插件名称
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @abstractmethod
    async def disable_plugin(self, plugin_name: str) -> None:
        """禁用一个已启用的插件。

        插件实例保留在内存中，仅取消事件注册并更新持久化状态。

        :param plugin_name: 插件名称
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @property
    @abstractmethod
    def plugins(self) -> "list[PluginMetadata]":
        """获取所有已加载插件的元数据列表。

        :return: 插件元数据列表（包括已启用和已禁用的插件）
        """
        ...

    @abstractmethod
    def list_plugin_handlers(self, plugin_name: str) -> "dict[str, type]":
        """查看指定插件注册的所有事件处理器。

        :param plugin_name: 插件名称
        :return: 方法名到事件类型的映射，如 ``{"on_message": LiveMessageEvent}``
        :raises CorePluginNotFoundException: 插件不存在或未启用
        """
        ...

    @abstractmethod
    def get_plugin_readme(self, plugin_name: str) -> "str | None":
        """获取插件的 README.md 内容。

        :param plugin_name: 插件名称
        :return: README 文本内容，若不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @abstractmethod
    def get_plugin_changelog(self, plugin_name: str) -> "str | None":
        """获取插件的 CHANGELOG.md 内容。

        :param plugin_name: 插件名称
        :return: CHANGELOG 文本内容，若不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    # ------------------------------------------------------------------ #
    # Plugin 权限与配置（新增）
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_plugin_permissions(self, plugin_name: str) -> "dict[str, Any]":
        """获取插件的权限信息。

        返回字典包含：
        - ``permissions`` — 合并后的权限字典（key → bool）
        - ``effective_flag`` — 生效的 ``BotPermission`` Flag 值
        - ``effective_names`` — 生效的权限名列表
        - ``bot_permissions`` — Bot 当前拥有的权限名列表
        - ``missing_in_bot`` — 插件启用但 Bot 缺失的权限名

        :param plugin_name: 插件名称
        :return: 权限信息字典
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @abstractmethod
    def update_plugin_permission(
        self, plugin_name: str, key: str, value: bool
    ) -> None:
        """更新插件的单个权限项，立即持久化。

        对标 :meth:`PluginConfigManager.update_config_value` 模式。

        :param plugin_name: 插件名称
        :param key: 权限键名（如 ``"SEND_GIFT"``，必须为 ``BotPermission`` 成员名）
        :param value: 新值（``True`` 启用，``False`` 禁用）
        :raises CorePluginNotFoundException: 插件不存在
        :raises CorePluginPermissionException: 无效的权限名
        """
        ...

    @abstractmethod
    def get_plugin_config_schema(self, plugin_name: str) -> "dict[str, Any] | None":
        """获取插件的配置 schema。

        :param plugin_name: 插件名称
        :return: 配置 schema 字典，不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @abstractmethod
    def get_failed_plugins(self) -> "list[dict[str, Any]]":
        """获取加载失败的插件信息列表。

        :return: 失败插件信息列表
        """
        ...

    @abstractmethod
    async def retry_failed_plugin(self, dir_name: str) -> "PluginMetadata":
        """重试加载之前失败的插件。

        :param dir_name: 插件目录名
        :return: 插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...

    @abstractmethod
    def get_plugin_data_dir(self, plugin_name: str) -> str:
        """获取插件的专属数据目录。

        目录自动创建，插件可将自定义数据文件存储在此。

        :param plugin_name: 插件名称
        :return: 数据目录绝对路径
        :raises CorePluginNotFoundException: 插件不存在
        """
        ...
