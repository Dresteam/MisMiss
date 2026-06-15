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
from core.exceptions import (
    CoreApiException,
    CoreCookieException,
    CoreBotException,
    CorePluginException,
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
        self._bot: MissevanBot | None = None
        self._bot_available: bool = False
        self._bot_cookie: str = ""
        self._bot_permissions: BotPermission = BotPermission.SEND_LIVESTREAM_MESSAGE
        self._livestreams: dict[int, MissevanLivestream] = {}
        self._event_bus: EventBus = EventBus()
        self._plugin_manager: PluginManager | None = None

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
        bot_state = state.get("bot")
        if bot_state:
            await self._restore_bot(bot_state)

        # 恢复 Livestream
        for live_id in state.get("livestreams", []):
            if self._bot is not None:
                self._restore_livestream(live_id)

        # 加载插件
        disabled_plugins: list[str] = state.get("disabled_plugins", [])
        self._plugin_manager = PluginManager(
            plugin_dir="plugins",
            event_bus=self._event_bus,
            config_dir=os.path.join(DATA_DIR, "config"),
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
        if self._plugin_manager is not None:
            await self._plugin_manager.shutdown_all()
        for livestream in self._livestreams.values():
            livestream.enabled = False
        if self._bot is not None:
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
        if self._bot is not None:
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
        old_perms = (
            self._bot.permissions if self._bot
            else BotPermission.SEND_LIVESTREAM_MESSAGE
        )
        _log.info("更新 Bot Cookie ...")
        return await self.create_bot(new_cookie, permissions=old_perms)

    @property
    def bot(self) -> MissevanBot | None:
        """获取当前 Bot（可能为 None）。"""
        return self._bot

    @property
    def bot_available(self) -> bool:
        """Bot 是否已初始化并可正常使用。

        返回 ``True`` 表示 Bot 已创建、已通过刷新验证且处于启用状态。
        """
        try:
            self._bot.refresh()
        except CoreCookieException:
            return False
        return self._bot_available and self._bot is not None and self._bot.enabled

    # ------------------------------------------------------------------ #
    # Livestream
    # ------------------------------------------------------------------ #

    def add_livestream(self, live_id: int) -> MissevanLivestream:
        """添加直播间。

        :param live_id: 直播间 ID
        :return: 直播间实例
        :raises RuntimeError: Bot 尚未创建
        """
        if not self.bot_available:
            raise CoreBotException("Bot 不存在或 Cookie 过期")

        if live_id in self._livestreams:
            return self._livestreams[live_id]

        livestream = MissevanLivestream(live_id, self._bot, self._event_bus)
        self._livestreams[live_id] = livestream
        self._save_state()
        _log.info("直播间添加成功: live_id={}", live_id)
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
        """获取插件管理器，未初始化时抛出异常。

        :return: PluginManager 实例
        :raises RuntimeError: 服务器尚未启动
        """
        if self._plugin_manager is None:
            raise RuntimeError("服务器尚未启动，请先调用 start()")
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
        if self._plugin_manager is None:
            return []
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
            "disabled_plugins": (
                list(self._plugin_manager.disabled_plugin_names)
                if self._plugin_manager else []
            ),
        }

        if self._bot is not None:
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

    def _restore_livestream(self, live_id: int) -> None:
        """从持久化数据恢复 Livestream。"""
        if self._bot is None:
            return
        livestream = MissevanLivestream(live_id, self._bot, self._event_bus)
        self._livestreams[live_id] = livestream
        _log.info("Livestream 已恢复: live_id={}", live_id)
