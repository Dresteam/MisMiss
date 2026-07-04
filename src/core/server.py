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
from core.command.router import CommandRouter
from core.plugin.plugin_manager import PluginManager
from core.plugin.permission_manager import PluginPermissionManager
from core.exceptions import (
    CoreApiException,
    CoreCookieException,
    CorePluginLoadException,
    CorePluginNotFoundException,
    CorePluginPermissionException,
)
from core.config import ServerConfig
from core.logging import get_logger

_log = get_logger(__name__)


class MissevanServer(ServerInterface):
    """Missevan 服务器——管理 Bot、Livestream、Plugin 的中央调度器。

    启动时从 ``config.yml`` 加载服务器配置，
    从 ``{data_dir}/{state_file}`` 加载持久化数据。
    Bot、插件、直播间默认均为**禁用**状态，需显式启用。
    """

    def __init__(self, config: ServerConfig | None = None) -> None:
        self._config = config or ServerConfig.load()
        self._data_dir: str = self._config.get_str("server.data_dir", "data")
        self._state_file: str = self._config.get_str("server.state_file", "server_state.json")

        self._bot: MissevanBot = MissevanBot(
            "",
            timer_interval=self._config.get_float("bot.timer_interval", 60.0),
        )
        self._bot_available: bool = False
        self._bot_cookie: str = ""
        self._bot_permissions: BotPermission = BotPermission.SEND_LIVESTREAM_MESSAGE
        self._livestreams: dict[int, MissevanLivestream] = {}
        self._enabled_livestreams: set[int] = set()
        self._event_bus: EventBus = EventBus()
        self._plugin_manager: PluginManager = PluginManager("", EventBus(), "")

    # ================================================================== #
    # 生命周期
    # ================================================================== #

    async def start(self) -> None:
        """启动服务器——从磁盘加载持久化数据。"""
        _log.info("服务器启动中 ...")
        self._ensure_data_dir()

        state = self._load_state() or {}

        # 恢复 Bot（创建但不启用）
        bot_state = state.get("bot", {})
        if bot_state:
            await self._restore_bot(bot_state)

        # 恢复 Livestream
        for live_id in state.get("livestreams", []):
            await self._restore_livestream(live_id)

        # 已启用直播间自动 join
        self._enabled_livestreams = set(state.get("enabled_livestreams", []))
        # 兼容旧状态：enabled=True 但尚未记录的直播间自动纳入
        for lid, live in self._livestreams.items():
            if live.enabled and lid not in self._enabled_livestreams:
                _log.info("自动纳入已启用直播间: live_id={}", lid)
                self._enabled_livestreams.add(lid)
        # 自动连接
        for lid in list(self._enabled_livestreams):
            if lid in self._livestreams:
                try:
                    await self._livestreams[lid].join()
                    _log.info("已自动连接直播间: live_id={}", lid)
                except Exception as e:
                    _log.warning("自动连接直播间失败 live_id={}: {}", lid, e)

        # 加载插件（首次加载的插件默认禁用）
        enabled_plugins: list[str] = state.get("enabled_plugins", [])
        command_router = CommandRouter(self._event_bus)
        self._plugin_manager = PluginManager(
            plugin_dir="plugins",
            event_bus=self._event_bus,
            config_dir=os.path.join(self._data_dir, "config"),
            permission_dir=os.path.join(self._data_dir, "permissions"),
            plugin_data_dir=os.path.join(self._data_dir, "plugins"),
            disabled_plugins=[],  # 初始全部禁用，由 enabled_plugins 决定
            command_router=command_router,
            pip_mirror=self._config.get_str("plugin.pip_mirror"),
        )
        await self._plugin_manager.load_all()
        # 仅启用 state 中记录的已启用插件
        for name in enabled_plugins:
            try:
                await self._plugin_manager.enable_plugin(name)
            except Exception:
                _log.warning("恢复插件启用状态失败: {}", name)

        _log.info(
            "服务器启动完成 bot={} livestreams={} plugins={}",
            self._bot, len(self._livestreams),
            len(self._plugin_manager.list_plugins()),
        )

    async def shutdown(self) -> None:
        """关闭服务器——停用所有组件。"""
        _log.info("服务器关闭中 ...")
        await self._plugin_manager.shutdown_all()
        for livestream in self._livestreams.values():
            try:
                await livestream.quit()
            except Exception:
                pass
            livestream.enabled = False
        self._bot.enabled = False
        _log.info("服务器已关闭")

    async def reload(self) -> None:
        """重载服务器（shutdown + start）。"""
        await self.shutdown()
        await self.start()

    async def refresh_plugins(self) -> None:
        """重新扫描插件目录，加载新插件（已加载的不重载）。"""
        pm = self._require_plugin_manager()
        prev_count = len(pm.list_plugins())
        await pm.load_all()
        new_count = len(pm.list_plugins())
        _log.info("插件刷新完成: {} → {} 个", prev_count, new_count)

    # ================================================================== #
    # Bot
    # ================================================================== #

    async def create_bot(
        self, cookie: str, *,
        permissions: BotPermission = BotPermission.SEND_LIVESTREAM_MESSAGE,
    ) -> MissevanBot:
        _log.info("创建 Bot ...")
        self._bot.enabled = False
        bot = MissevanBot(
            cookie,
            permissions=permissions,
            timer_interval=self._config.get_float("bot.timer_interval", 60.0),
        )
        await bot.refresh()
        self._bot = bot
        self._bot_available = True
        self._bot_cookie = cookie
        self._bot_permissions = permissions
        self._constrain_plugin_permissions()
        self._save_state()
        _log.info("Bot 创建成功: {}", bot)
        return bot

    async def update_cookie(self, new_cookie: str) -> MissevanBot:
        old_perms = self._bot.permissions
        _log.info("更新 Bot Cookie ...")
        return await self.create_bot(new_cookie, permissions=old_perms)

    @property
    def bot(self) -> MissevanBot:
        return self._bot

    @property
    def bot_available(self) -> bool:
        return self._bot_available and self._bot.enabled

    async def verify_bot(self) -> bool:
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

    async def enable_bot(self) -> None:
        """启用 Bot —— 验证 Cookie 后置为启用。"""
        if self._bot.id == 0:
            await self._bot.refresh()
        self._bot_available = True
        self._bot.enabled = True
        self._save_state()
        _log.info("Bot 已启用: {}", self._bot)

    # ================================================================== #
    # Livestream
    # ================================================================== #

    async def add_livestream(self, live_id: int) -> MissevanLivestream:
        """添加直播间——获取房间信息并注册（不连接 WebSocket）。

        添加时通过 API 获取房间元信息（名称、简介、主播等），
        但不建立 WebSocket 连接。调用 :meth:`enable_livestream` 来连接。

        :param live_id: 直播间 ID
        :return: 已填充元信息的直播间实例
        :raises CoreApiException: 房间信息获取失败
        """
        if live_id in self._livestreams:
            return self._livestreams[live_id]
        livestream = MissevanLivestream(live_id, self._bot, self._event_bus)
        await livestream._refresh()  # type: ignore[attr-defined]
        self._livestreams[live_id] = livestream
        self._save_state()
        _log.info(
            "直播间已添加: live_id={} name={}", live_id, livestream.room_name
        )
        return livestream

    async def remove_livestream(self, live_id: int) -> None:
        if live_id not in self._livestreams:
            raise KeyError(f"直播间 {live_id} 不存在")
        livestream = self._livestreams[live_id]
        await livestream.quit()
        del self._livestreams[live_id]
        self._enabled_livestreams.discard(live_id)
        self._save_state()
        _log.info("直播间已移除: live_id={}", live_id)

    async def enable_livestream(self, live_id: int) -> None:
        """启用直播间并自动连接 WebSocket。"""
        livestream = self._livestreams[live_id]
        livestream.enabled = True
        await livestream._refresh()  # type: ignore[attr-defined]
        await livestream.join()
        self._enabled_livestreams.add(live_id)
        self._save_state()
        _log.info("直播间已启用并连接: live_id={} name={}", live_id, livestream.room_name)

    def disable_livestream(self, live_id: int) -> None:
        """停用直播间并断开连接。"""
        import asyncio
        livestream = self._livestreams[live_id]
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(livestream.quit())
        except RuntimeError:
            pass
        livestream.enabled = False
        self._enabled_livestreams.discard(live_id)
        self._save_state()
        _log.info("直播间已停用: live_id={}", live_id)

    @property
    def livestreams(self) -> dict[int, MissevanLivestream]:
        return dict(self._livestreams)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    # ================================================================== #
    # Plugin
    # ================================================================== #

    def _require_plugin_manager(self) -> PluginManager:
        return self._plugin_manager

    def _constrain_plugin_permissions(self) -> None:
        """将所有已加载插件的权限强制缩小至 Bot 当前权限范围。

        Bot 权限为插件权限的天花板：若插件拥有某权限但 Bot 没有，
        则强制禁用该插件的对应权限并持久化。
        """
        pm = self._require_plugin_manager()
        if not self._bot_available:
            return
        bot_perm_dict = PluginPermissionManager.to_dict(self._bot.permissions)
        for meta in pm.list_plugins():
            if meta.permissions is None:
                continue
            changed = False
            for key in list(meta.permissions.keys()):
                if meta.permissions[key] and not bot_perm_dict.get(key, False):
                    meta.permissions[key] = False
                    changed = True
                    _log.info(
                        "插件 [%s] 权限 %s 超出 Bot 范围，已强制禁用",
                        meta.name, key,
                    )
            if changed:
                pm.permission_manager.save_permissions(meta.name, meta.permissions)

    async def install_plugin(self, plugin_name: str) -> PluginMetadata:
        pm = self._require_plugin_manager()
        metadata = await pm.load_plugin(plugin_name)
        if metadata is None:
            raise CorePluginLoadException(plugin_name, "插件加载失败")
        self._save_state()
        return metadata

    async def install_plugin_from_url(self, url: str) -> PluginMetadata:
        pm = self._require_plugin_manager()
        metadata = await pm.install_plugin(url=url)
        self._save_state()
        return metadata

    async def install_plugin_from_local(self, path: str) -> PluginMetadata:
        pm = self._require_plugin_manager()
        metadata = await pm.install_plugin(local_path=path)
        self._save_state()
        return metadata

    async def uninstall_plugin(
        self, plugin_name: str,
        delete_config: bool = False, delete_data: bool = False,
    ) -> None:
        pm = self._require_plugin_manager()
        pm.uninstall_plugin(plugin_name, delete_config, delete_data)
        self._save_state()

    async def reload_plugin(self, plugin_name: str) -> PluginMetadata:
        pm = self._require_plugin_manager()
        metadata = await pm.reload_plugin(plugin_name)
        self._save_state()
        return metadata

    async def enable_plugin(self, plugin_name: str) -> None:
        pm = self._require_plugin_manager()
        metadata = pm.get_plugin(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)
        if metadata.enabled:
            return  # 已启用，无需操作

        if metadata.plugin_instance is None:
            # 尚未激活 → 同步等待激活完成
            try:
                await pm._activate_plugin(metadata)
            except Exception as e:
                raise CorePluginLoadException(plugin_name, str(e))
        else:
            pm._event_bus.register_new_event(metadata.plugin_instance)

        metadata.enabled = True
        pm._disabled_plugins.discard(plugin_name)
        self._save_state()

    async def disable_plugin(self, plugin_name: str) -> None:
        pm = self._require_plugin_manager()
        pm.disable_plugin(plugin_name)
        self._save_state()

    @property
    def plugins(self) -> list[PluginMetadata]:
        return self._plugin_manager.list_plugins()

    def list_plugin_handlers(self, plugin_name: str) -> dict[str, type]:
        return self._require_plugin_manager().get_plugin_handlers(plugin_name)

    def get_plugin_readme(self, plugin_name: str) -> str | None:
        return self._require_plugin_manager().get_plugin_readme(plugin_name)

    def get_plugin_changelog(self, plugin_name: str) -> str | None:
        return self._require_plugin_manager().get_plugin_changelog(plugin_name)

    # ================================================================== #
    # Plugin 权限
    # ================================================================== #

    def get_plugin_permissions(self, plugin_name: str) -> dict[str, Any]:
        pm = self._require_plugin_manager()
        metadata = pm.get_plugin(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)
        perms_dict = metadata.permissions or {}
        effective_flag = PluginPermissionManager.to_bot_permission(perms_dict)
        bot = self._bot if self._bot_available else None
        if bot is not None:
            effective_flag = BotPermission(effective_flag.value & bot.permissions.value)
        bot_names = PluginPermissionManager.to_dict(bot.permissions) if bot else {}
        missing = (
            PluginPermissionManager.check_bot_permissions(bot, effective_flag, plugin_name)
            if bot else []
        )
        return {
            "permissions": perms_dict,
            "effective_flag": effective_flag.value,
            "effective_names": [k for k, v in perms_dict.items() if v],
            "bot_permissions": [k for k, v in bot_names.items() if v],
            "missing_in_bot": missing,
        }

    def update_plugin_permission(
        self, plugin_name: str, key: str, value: bool
    ) -> None:
        pm = self._require_plugin_manager()
        metadata = pm.get_plugin(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)
        try:
            BotPermission[key]
        except KeyError:
            raise CorePluginPermissionException(
                plugin_name=plugin_name,
                reason=f"无效的权限名 '{key}'，有效值: {[p.name for p in BotPermission]}",
            )
        pm.permission_manager.update_permission(plugin_name, key, value)
        if metadata.permissions is not None:
            metadata.permissions[key] = value
        _log.info("插件 [{}] 权限已更新: {} = {}", plugin_name, key, value)

    def get_plugin_config_schema(self, plugin_name: str) -> dict[str, Any] | None:
        pm = self._require_plugin_manager()
        metadata = pm.get_plugin(plugin_name)
        if metadata is None:
            raise CorePluginNotFoundException(plugin_name)
        if metadata.config_schema_path:
            return pm.config_manager.load_schema(metadata.config_schema_path)
        return None

    def get_failed_plugins(self) -> list[dict[str, Any]]:
        return self._plugin_manager.get_failed_plugins()

    async def retry_failed_plugin(self, dir_name: str) -> PluginMetadata:
        pm = self._require_plugin_manager()
        metadata = await pm.retry_failed_plugin(dir_name)
        self._save_state()
        return metadata

    # ================================================================== #
    # 定时消息
    # ================================================================== #

    def register_timer_message(self, live_id: int, message: str) -> str:
        return self._bot.register_timer_message(live_id, message)

    def unregister_timer_message(self, message_id: str) -> None:
        self._bot.unregister_timer_message(message_id)

    def register_timer_messages(
        self, entries: list[tuple[int, str]]
    ) -> list[str]:
        return self._bot.register_timer_messages(entries)

    def unregister_timer_messages(self, message_ids: list[str]) -> None:
        self._bot.unregister_timer_messages(message_ids)

    @property
    def timer_message_count(self) -> int:
        return self._bot.timer_message_count

    def get_plugin_data_dir(self, plugin_name: str) -> str:
        pm = self._require_plugin_manager()
        if pm.get_plugin(plugin_name) is None:
            raise CorePluginNotFoundException(plugin_name)
        return pm.get_plugin_data_dir(plugin_name)

    # ================================================================== #
    # 持久化
    # ================================================================== #

    def _ensure_data_dir(self) -> None:
        Path(self._data_dir).mkdir(parents=True, exist_ok=True)

    @property
    def _state_path(self) -> str:
        return os.path.join(self._data_dir, self._state_file)

    def _save_state(self) -> None:
        self._ensure_data_dir()
        state: dict[str, Any] = {
            "enabled_plugins": [
                p.name for p in self._plugin_manager.list_plugins() if p.enabled
            ],
            "enabled_livestreams": list(self._enabled_livestreams),
        }
        if self._bot_available or self._bot_cookie:
            state["bot"] = {
                "cookie": self._bot_cookie,
                "permissions": self._bot_permissions.value,
                "enabled": self._bot.enabled,
            }
        state["livestreams"] = list(self._livestreams.keys())
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _load_state(self) -> dict[str, Any] | None:
        if not os.path.exists(self._state_path):
            return None
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            _log.warning("持久化数据损坏，忽略")
            return None

    async def _restore_bot(self, bot_state: dict[str, Any]) -> None:
        """从持久化数据恢复 Bot——创建但不启用。"""
        cookie = bot_state.get("cookie", "")
        perms_val = bot_state.get("permissions", 1)
        try:
            permissions = BotPermission(perms_val)
        except ValueError:
            permissions = BotPermission.SEND_LIVESTREAM_MESSAGE
        try:
            self._bot = MissevanBot(
                cookie,
                permissions=permissions,
                timer_interval=self._config.get_float("bot.timer_interval", 60.0),
            )
            await self._bot.refresh()
            self._bot_available = True
            self._bot_cookie = cookie
            self._bot_permissions = permissions
            # 恢复启用状态
            if bot_state.get("enabled", False):
                self._bot.enabled = True
                _log.info("Bot 已恢复（启用）: {}", self._bot)
            else:
                self._bot.enabled = False
                _log.info("Bot 已恢复（禁用）: {}", self._bot)
        except CoreApiException as e:
            self._bot_available = False
            _log.error("Bot 恢复时发生错误：{}", str(e))
        except CoreCookieException:
            _log.warning("Cookie 已过期")

    async def _restore_livestream(self, live_id: int) -> None:
        """从持久化数据恢复 Livestream（不自动 join）。"""
        livestream = MissevanLivestream(live_id, self._bot, self._event_bus)
        try:
            await livestream._refresh()  # type: ignore[attr-defined]
        except CoreApiException:
            _log.warning("Livestream 恢复时房间信息获取失败: live_id={}", live_id)
        self._livestreams[live_id] = livestream
        _log.info("Livestream 已恢复: live_id={}", live_id)
