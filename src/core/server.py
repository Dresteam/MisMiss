"""服务器——主程序入口。

管理 Bot、Livestream、Plugin 的生命周期与持久化存储。
启动时从磁盘加载实例，修改时自动保存。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from interfaces.server import Server as ServerInterface
from interfaces.bot import BotPermission
from interfaces.plugin.plugin_metadata import PluginMetadata
from core.bot.mis_bot import MissevanBot
from core.events.bus import EventBus
from core.livestream.mis_livestream import MissevanLivestream
from core.plugin.plugin_manager import PluginManager
from core.plugin.permission_manager import PluginPermissionManager
from core.exceptions import (
    CoreApiException,
    CoreCookieException,
    CoreBotException,
    CorePluginLoadException,
    CorePluginNotFoundException,
    CorePluginPermissionException,
)
from core.logging import get_logger

_log = get_logger(__name__)

# ================================================================ #
# 持久化路径（可修改常量，便于后续优化）
# ================================================================ #

DATA_DIR: str = "data"
"""数据存储目录。"""

_STATE_FILE: str = "server_state.json"
"""主状态文件名。"""


# ================================================================ #
# MissevanServer
# ================================================================ #

class MissevanServer(ServerInterface):
    """Missevan 服务器——管理 Bot、Livestream、Plugin 的中央调度器。

    实现 :class:`~interfaces.server.Server` 标准接口。
    启动时从 ``{DATA_DIR}/server_state.json`` 加载持久化数据，
    每次创建或修改 Bot / Livestream / Plugin 时自动保存。

    用法::

        server = MissevanServer()
        await server.start()
    """

    def __init__(self) -> None:
        self._bot: MissevanBot = MissevanBot("")
        self._bot_available: bool = False
        self._bot_cookie: str = ""
        self._bot_permissions: BotPermission = BotPermission.SEND_LIVESTREAM_MESSAGE
        self._livestreams: dict[int, MissevanLivestream] = {}
        self._event_bus: EventBus = EventBus()
        self._plugin_manager: PluginManager = PluginManager("", EventBus(), "")

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """启动服务器——从磁盘加载持久化数据。"""
        _log.info("服务器启动中 ...")
        self._ensure_data_dir()

        state = self._load_state()
        if not state:
            _log.info("未找到持久化数据，使用空状态启动")
            state = {}

        # 恢复 Bot
        bot_state = state.get("bot", {})
        if bot_state:
            await self._restore_bot(bot_state)

        # 恢复 Livestream
        for live_id in state.get("livestreams", []):
            await self._restore_livestream(live_id)

        # 加载插件
        disabled_plugins: list[str] = state.get("disabled_plugins", [])
        self._plugin_manager = PluginManager(
            plugin_dir="plugins",
            event_bus=self._event_bus,
            config_dir=os.path.join(DATA_DIR, "config"),
            permission_dir=os.path.join(DATA_DIR, "permissions"),
            plugin_data_dir=DATA_DIR,
            disabled_plugins=disabled_plugins,
        )
        await self._plugin_manager.load_all()

        _log.info(
            "服务器启动完成 bot={} livestreams={} plugins={}",
            self._bot,
            len(self._livestreams),
            len(self._plugin_manager.list_plugins()),
        )

    async def shutdown(self) -> None:
        """关闭服务器——停用所有插件、Livestream 和 Bot。"""
        _log.info("服务器关闭中 ...")
        await self._plugin_manager.shutdown_all()
        for livestream in self._livestreams.values():
            livestream.enabled = False
        self._bot.enabled = False
        _log.info("服务器已关闭")

    # ------------------------------------------------------------------ #
    # Bot
    # ------------------------------------------------------------------ #

    async def create_bot(
        self,
        cookie: str,
        *,
        permissions: BotPermission = BotPermission.SEND_LIVESTREAM_MESSAGE,
    ) -> MissevanBot:
        """创建机器人。

        若已存在 Bot，则先停用旧 Bot 再创建新的。

        :param cookie: Cookie 字符串
        :param permissions: 权限集合（创建后不可修改）
        :return: 新创建的 Bot 实例
        :raises CoreCookieException: Cookie 无效
        """
        _log.info("创建 Bot ...")

        # 停用旧 Bot
        self._bot.enabled = False
        _log.info("已停用旧 Bot: {}", self._bot)

        bot = MissevanBot(cookie, permissions=permissions)
        await bot.refresh()

        self._bot = bot
        self._bot_available = True
        self._bot_cookie = cookie
        self._bot_permissions = permissions
        self._save_state()
        _log.info("Bot 创建成功: {}", bot)
        return bot

    async def update_cookie(self, new_cookie: str) -> MissevanBot:
        """更新 Bot Cookie——停用旧 Bot 并用新 Cookie 重建。

        重建时保留旧 Bot 的权限配置。

        :param new_cookie: 新的 Cookie 字符串
        :return: 新创建的 Bot 实例
        :raises CoreCookieException: 新 Cookie 无效
        """
        old_perms = self._bot.permissions

        _log.info("更新 Bot Cookie ...")
        return await self.create_bot(new_cookie, permissions=old_perms)

    @property
    def bot(self) -> MissevanBot:
        """获取当前 Bot。"""
        return self._bot

    @property
    def bot_available(self) -> bool:
        """Bot 是否已初始化并可正常使用。

        返回 ``True`` 表示 Bot 已创建、已通过刷新验证且处于启用状态。

        .. note::
           此属性仅读取缓存状态，不发起网络请求。
           如需主动验证 Cookie 是否过期，请调用 :meth:`verify_bot`。
        """
        return self._bot_available and self._bot.enabled

    async def verify_bot(self) -> bool:
        """主动验证 Bot Cookie 是否有效（发起网络请求）。

        :return: Cookie 有效返回 ``True``，过期返回 ``False``
        """
        try:
            await self._bot.refresh()
            self._bot_available = True
            return True
        except CoreCookieException:
            self._bot_available = False
            _log.warning("Cookie 已过期")
            return False
        except CoreApiException as e:
            _log.error("验证 Bot 时发生 API 错误: {}", e)
            return False

    # ------------------------------------------------------------------ #
    # Livestream
    # ------------------------------------------------------------------ #

    async def add_livestream(self, live_id: int) -> MissevanLivestream:
        """添加直播间。

        添加前会主动验证 Bot Cookie 是否有效，
        创建后立即获取房间信息（名称、主播、热度等），无需先调用 :meth:`join`。

        若直播间已存在且尚未初始化，会补刷新房间数据。

        :param live_id: 直播间 ID
        :return: 直播间实例
        :raises CoreBotException: Bot Cookie 已过期
        :raises CoreApiException: 房间信息获取失败
        """
        if not await self.verify_bot():
            raise CoreBotException("Bot Cookie 已过期，无法添加直播间")

        if live_id in self._livestreams:
            existing = self._livestreams[live_id]
            # 如果已存在但从未初始化（例如从持久化恢复），补充刷新
            if existing._creator is None:  # type: ignore[attr-defined]
                await existing._refresh()  # type: ignore[attr-defined]
            return existing

        livestream = MissevanLivestream(live_id, self._bot, self._event_bus)
        await livestream._refresh()  # type: ignore[attr-defined]
        self._livestreams[live_id] = livestream
        self._save_state()
        _log.info(
            "直播间添加成功: live_id={} name={}",
            live_id,
            livestream.room_name,
        )
        return livestream

    def enable_livestream(self, live_id: int) -> None:
        """启用直播间（不销毁实例）。

        :param live_id: 直播间 ID
        :raises KeyError: 直播间不存在
        """
        livestream = self._livestreams[live_id]
        livestream.enabled = True
        _log.info("直播间已启用: live_id={}", live_id)

    def disable_livestream(self, live_id: int) -> None:
        """停用直播间（不销毁实例）。

        :param live_id: 直播间 ID
        :raises KeyError: 直播间不存在
        """
        livestream = self._livestreams[live_id]
        livestream.enabled = False
        _log.info("直播间已停用: live_id={}", live_id)

    @property
    def livestreams(self) -> dict[int, MissevanLivestream]:
        """获取所有直播间（只读视图）。"""
        return dict(self._livestreams)

    @property
    def event_bus(self) -> EventBus:
        """获取全局事件总线。"""
        return self._event_bus

    # ------------------------------------------------------------------ #
    # Plugin
    # ------------------------------------------------------------------ #

    def _require_plugin_manager(self) -> PluginManager:
        """获取插件管理器。

        :return: PluginManager 实例
        """
        return self._plugin_manager

    async def install_plugin(self, plugin_name: str) -> PluginMetadata:
        """安装并加载插件。

        扫描 ``plugins/`` 目录，加载指定插件。

        :param plugin_name: 插件目录名或 metadata.yaml 中声明的 name
        :return: 插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        :raises CorePluginLoadException: 插件加载失败
        """
        pm = self._require_plugin_manager()
        metadata = await pm.load_plugin(plugin_name)
        if metadata is None:
            raise CorePluginLoadException(plugin_name, "插件加载失败")
        self._save_state()
        return metadata

    async def install_plugin_from_url(self, url: str) -> PluginMetadata:
        """从远程 URL 下载并安装插件。

        :param url: 插件 zip 包的远程 URL
        :return: 插件元数据
        :raises CorePluginInstallException: 安装失败
        """
        pm = self._require_plugin_manager()
        metadata = await pm.install_plugin(url=url)
        self._save_state()
        return metadata

    async def install_plugin_from_local(self, path: str) -> PluginMetadata:
        """从本地路径安装插件。

        :param path: 本地 zip 文件或目录路径
        :return: 插件元数据
        :raises CorePluginInstallException: 安装失败
        """
        pm = self._require_plugin_manager()
        metadata = await pm.install_plugin(local_path=path)
        self._save_state()
        return metadata

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
        pm = self._require_plugin_manager()
        pm.uninstall_plugin(plugin_name, delete_config, delete_data)
        self._save_state()

    async def reload_plugin(self, plugin_name: str) -> PluginMetadata:
        """重载插件。

        :param plugin_name: 插件名称
        :return: 新的插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        metadata = await pm.reload_plugin(plugin_name)
        self._save_state()
        return metadata

    async def enable_plugin(self, plugin_name: str) -> None:
        """启用一个已加载但被禁用的插件。

        :param plugin_name: 插件名称
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        pm.enable_plugin(plugin_name)
        self._save_state()

    async def disable_plugin(self, plugin_name: str) -> None:
        """禁用一个已启用的插件。

        :param plugin_name: 插件名称
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        pm.disable_plugin(plugin_name)
        self._save_state()

    @property
    def plugins(self) -> list[PluginMetadata]:
        """获取所有已加载插件的元数据列表。"""
        return self._plugin_manager.list_plugins()

    def list_plugin_handlers(self, plugin_name: str) -> dict[str, type]:
        """查看指定插件注册的所有事件处理器。

        :param plugin_name: 插件名称
        :return: 方法名到事件类型的映射
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        return pm.get_plugin_handlers(plugin_name)

    def get_plugin_readme(self, plugin_name: str) -> str | None:
        """获取插件的 README.md 内容。

        :param plugin_name: 插件名称
        :return: README 文本内容，若不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        return pm.get_plugin_readme(plugin_name)

    def get_plugin_changelog(self, plugin_name: str) -> str | None:
        """获取插件的 CHANGELOG.md 内容。

        :param plugin_name: 插件名称
        :return: CHANGELOG 文本内容，若不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        return pm.get_plugin_changelog(plugin_name)

    # ------------------------------------------------------------------ #
    # Plugin 权限（Server 自动分配默认值，管理员可修改）
    # ------------------------------------------------------------------ #

    def get_plugin_permissions(self, plugin_name: str) -> dict[str, Any]:
        """获取插件的权限信息。

        :param plugin_name: 插件名称
        :return: 权限信息字典：
                 - ``permissions`` — 合并后的权限字典（key → bool）
                 - ``effective_flag`` — 生效的 ``BotPermission`` Flag 值
                 - ``effective_names`` — 生效的权限名列表
                 - ``bot_permissions`` — Bot 当前拥有的权限名列表
                 - ``missing_in_bot`` — 插件启用但 Bot 缺失的权限名
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        metadata = pm.get_plugin(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)

        # 加载合并后的权限
        perms_dict = metadata.permissions or {}
        effective_flag = PluginPermissionManager.to_bot_permission(perms_dict)

        # 以 Bot 实际权限为天花板
        bot = self._bot if self._bot_available else None
        if bot is not None:
            effective_flag = BotPermission(
                effective_flag.value & bot.permissions.value
            )

        bot_names = (
            PluginPermissionManager.to_dict(bot.permissions)
            if bot
            else {}
        )
        missing = PluginPermissionManager.check_bot_permissions(
            bot, effective_flag, plugin_name
        ) if bot else []

        return {
            "permissions": perms_dict,
            "effective_flag": effective_flag.value,
            "effective_names": [
                k for k, v in perms_dict.items() if v
            ],
            "bot_permissions": [
                k for k, v in bot_names.items() if v
            ],
            "missing_in_bot": missing,
        }

    def update_plugin_permission(
        self, plugin_name: str, key: str, value: bool
    ) -> None:
        """更新插件的单个权限项，立即持久化（对标 ``update_config_value``）。

        :param plugin_name: 插件名称
        :param key: 权限键名（如 ``"SEND_GIFT"``，必须为 ``BotPermission`` 成员名）
        :param value: 新值（``True`` 启用，``False`` 禁用）
        :raises CorePluginNotFoundException: 插件不存在
        :raises CorePluginPermissionException: 无效的权限名
        """
        pm = self._require_plugin_manager()
        metadata = pm.get_plugin(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)

        # 校验 key 是否为有效的 BotPermission 成员名
        try:
            BotPermission[key]
        except KeyError:
            raise CorePluginPermissionException(
                plugin_name=plugin_name,
                reason=(
                    f"无效的权限名 '{key}'，"
                    f"有效值: {[p.name for p in BotPermission]}"
                ),
            )

        pm.permission_manager.update_permission(plugin_name, key, value)
        # 同步更新内存中的元数据
        if metadata.permissions is not None:
            metadata.permissions[key] = value
        _log.info(
            "插件 [{}] 权限已更新: {} = {}", plugin_name, key, value
        )

    def get_plugin_config_schema(self, plugin_name: str) -> dict[str, Any] | None:
        """获取插件的配置 schema。

        :param plugin_name: 插件名称
        :return: 配置 schema 字典，不存在则返回 ``None``
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        metadata = pm.get_plugin(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)
        if metadata.config_schema_path:
            return pm.config_manager.load_schema(metadata.config_schema_path)
        return None

    def get_failed_plugins(self) -> list[dict[str, Any]]:
        """获取加载失败的插件信息列表。

        :return: 失败插件信息列表
        """
        return self._plugin_manager.get_failed_plugins()

    async def retry_failed_plugin(self, dir_name: str) -> PluginMetadata:
        """重试加载之前失败的插件。

        :param dir_name: 插件目录名
        :return: 插件元数据
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        metadata = await pm.retry_failed_plugin(dir_name)
        self._save_state()
        return metadata

    def get_plugin_data_dir(self, plugin_name: str) -> str:
        """获取插件的专属数据目录。

        :param plugin_name: 插件名称
        :return: 数据目录绝对路径
        :raises CorePluginNotFoundException: 插件不存在
        """
        pm = self._require_plugin_manager()
        if pm.get_plugin(plugin_name) is None:
            raise CorePluginNotFoundException(plugin_name)
        return pm.get_plugin_data_dir(plugin_name)

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ensure_data_dir() -> None:
        """确保数据目录存在。"""
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

    @property
    def _state_path(self) -> str:
        return os.path.join(DATA_DIR, _STATE_FILE)

    def _save_state(self) -> None:
        """保存当前状态到磁盘。"""
        self._ensure_data_dir()

        state: dict[str, Any] = {
            "disabled_plugins": list(self._plugin_manager.disabled_plugin_names),
        }

        if self._bot_available:
            state["bot"] = {
                "cookie": self._bot_cookie,
                "permissions": self._bot_permissions.value,
            }

        state["livestreams"] = list(self._livestreams.keys())

        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _load_state(self) -> dict[str, Any] | None:
        """从磁盘加载状态。"""
        if not os.path.exists(self._state_path):
            return None
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            _log.warning("持久化数据损坏，忽略")
            return None

    async def _restore_bot(self, bot_state: dict[str, Any]) -> None:
        """从持久化数据恢复 Bot。"""
        cookie = bot_state.get("cookie", "")
        perms_val = bot_state.get("permissions", 1)
        try:
            permissions = BotPermission(perms_val)
        except ValueError:
            permissions = BotPermission.SEND_LIVESTREAM_MESSAGE

        try:
            self._bot = MissevanBot(cookie, permissions=permissions)
            await self._bot.refresh()
            self._bot_available = True
            self._bot_cookie = cookie
            self._bot_permissions = permissions
            _log.info("Bot 已恢复: {}", self._bot)
        except CoreApiException as e:
            self._bot_available = False
            _log.error("Bot 恢复时发生错误：{}", str(e))
        except CoreCookieException:
            _log.warning("Cookie 已过期")
            # TODO 处理 Cookie 过期

    async def _restore_livestream(self, live_id: int) -> None:
        """从持久化数据恢复 Livestream，补刷新房间数据。"""
        livestream = MissevanLivestream(live_id, self._bot, self._event_bus)
        try:
            await livestream._refresh()  # type: ignore[attr-defined]
        except CoreApiException:
            _log.warning("Livestream 恢复时房间信息获取失败: live_id={}", live_id)
        self._livestreams[live_id] = livestream
        _log.info("Livestream 已恢复: live_id={}", live_id)
