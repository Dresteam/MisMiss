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
    CoreDisabledException,
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
        self._app = None  # FastAPI app 引用，由 lifespan 在 start() 前注入
        self._state_mtime: float = 0.0  # state 文件最后加载时间戳

    # ================================================================== #
    # 生命周期
    # ================================================================== #

    def set_app(self, app) -> None:
        """注入 FastAPI app 引用——必须在 :meth:`start` 前调用。"""
        self._app = app

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
        # 自动连接（使用 enable_livestream 确保完整流程）
        for lid in list(self._enabled_livestreams):
            if lid in self._livestreams:
                try:
                    await self.enable_livestream(lid)
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
        self._plugin_manager.set_server(self)
        await self._plugin_manager.load_all()
        # 恢复持久化的启用标记
        pm = self._plugin_manager
        for name in enabled_plugins:
            meta = pm.get_plugin(name)
            if meta:
                meta.enabled = True
        # 在 resume_all 之前注入 app 引用，确保 _ensure_plugin_loaded 注册路由时 _app 已可用
        if self._app is not None:
            self._plugin_manager.set_app(self._app)
        # Bot 可用且启用时，加载所有标记为启用的插件
        if self._bot_available and self._bot.enabled:
            pm.resume_all()
        else:
            _log.info("Bot 未启用，插件标记已恢复（待 Bot 启用后加载）")
        self._save_state()  # 立即持久化当前状态

        _log.info(
            "服务器启动完成 bot={} livestreams={} plugins={}",
            self._bot, len(self._livestreams),
            len(self._plugin_manager.list_plugins()),
        )

    async def shutdown(self) -> None:
        """关闭服务器——先持久化状态再停用所有组件。"""
        _log.info("服务器关闭中 ...")
        self._save_state()  # 先保存当前状态
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
        # start() 已通过 self._app 重新注入了 app 引用到新的 PluginManager

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
        was_enabled = self._bot.enabled
        bot = MissevanBot(
            cookie,
            permissions=permissions,
            timer_interval=self._config.get_float("bot.timer_interval", 60.0),
        )
        await bot.refresh()
        bot.enabled = was_enabled

        # 1. 先停用所有已启用插件（终止旧实例）
        pm = self._plugin_manager
        enabled_names = [p.name for p in pm.list_plugins() if p.enabled]
        for name in enabled_names:
            try:
                _log.info("Cookie 更新前停用插件: {}", name)
                pm.disable_plugin(name)
            except Exception as e:
                _log.warning("停用插件失败 [{}]: {}", name, e)

        # 2. 切换到新 Bot
        self._bot = bot
        self._bot_available = True
        self._bot_cookie = cookie
        self._bot_permissions = permissions
        self._constrain_plugin_permissions()

        # 3. 更新所有直播间的 bot 引用
        for live in self._livestreams.values():
            live._bot = bot

        # 4. 重新启用插件（使用新 bot 实例初始化）
        for name in enabled_names:
            try:
                _log.info("Cookie 更新后启用插件: {}", name)
                await pm.enable_plugin(name)
            except Exception as e:
                _log.warning("启用插件失败 [{}]: {}", name, e)

        self._save_state()
        _log.info("Bot 创建成功: {}", bot)
        return bot

    async def update_cookie(self, new_cookie: str) -> MissevanBot:
        old_perms = self._bot.permissions
        _log.info("更新 Bot Cookie ...")
        return await self.create_bot(new_cookie, permissions=old_perms)

    # ------------------------------------------------------------------ #
    # 跨 worker 状态同步（Docker 多 worker 兼容）
    # ------------------------------------------------------------------ #

    def _ensure_state_fresh(self) -> None:
        """通过检查 state 文件的修改时间判断是否需要重新加载。

        Docker 多 worker 模式（4× UvicornWorker）下，每个 worker 有独立内存。
        此方法在每次 API 请求时被 :func:`get_server` 依赖调用，
        通过对比 state 文件的 mtime 判断是否有其他 worker 修改了状态。

        仅当 mtime 变化时才重新加载，避免频繁磁盘 I/O。
        """
        try:
            current_mtime = os.path.getmtime(self._state_path)
        except OSError:
            return  # state 文件不存在（首次启动）
        if current_mtime <= self._state_mtime:
            return  # 未变化，无需刷新

        _log.debug("检测到 state 文件更新 (mtime: {} → {})，重新加载",
                   self._state_mtime, current_mtime)
        self._state_mtime = current_mtime

        state = self._load_state() or {}

        # Bot（异步恢复需配合 _ensure_bot_restored）

        # 直播间启用状态
        enabled_livestreams = set(state.get("enabled_livestreams", []))
        if enabled_livestreams != self._enabled_livestreams:
            self._enabled_livestreams = enabled_livestreams

        # 插件启用状态
        enabled_plugins: list[str] = state.get("enabled_plugins", [])
        pm = self._plugin_manager
        for meta in pm.list_plugins():
            should_enable = meta.name in enabled_plugins
            if meta.enabled != should_enable:
                meta.enabled = should_enable

    async def _ensure_bot_restored(self) -> None:
        """异步恢复 bot 和直播间（供端点调用）。

        _ensure_state_fresh 只负责同步状态；bot 的 refresh() 和 livestream 的
        _refresh() 是异步 API 调用，必须由端点 await 完成。
        """
        state = self._load_state() or {}

        # 1. Bot 恢复
        if self._bot.id == 0:
            bot_state = state.get("bot", {})
            if bot_state:
                _log.info("bot 状态从磁盘异步恢复（多 worker）")
                await self._restore_bot(bot_state)

        # 2. 直播间恢复——其他 worker 添加的直播间可能不在当前 _livestreams 中
        saved_ids = set(state.get("livestreams", []))
        missing_ids = saved_ids - set(self._livestreams.keys())
        for lid in missing_ids:
            _log.info("直播间 {} 从磁盘异步恢复（多 worker）", lid)
            await self._restore_livestream(lid)
        # 同步启用状态
        enabled = set(state.get("enabled_livestreams", []))
        if enabled != self._enabled_livestreams:
            self._enabled_livestreams = enabled

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
        livestream.enabled = False  # 新添加默认停用，等待用户显式启用（启用时自动连接）
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
        try:
            await livestream.quit()
        except CoreDisabledException:
            pass  # 已停用的直播间直接移除
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

        async def _safe_quit() -> None:
            try:
                await livestream.quit()
            except CoreDisabledException:
                pass  # 已停用/已断开，视为成功

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_safe_quit())
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
        if metadata.enabled and metadata.plugin_instance is not None:
            _log.info("插件已处于启用状态: {}", plugin_name)
            return

        pm._disabled_plugins.discard(plugin_name)

        if metadata.plugin_instance is None:
            # 尚未激活 → 完整加载（_activate_plugin 内部会处理初始化）
            try:
                await pm._activate_plugin(metadata)
            except Exception as e:
                raise CorePluginLoadException(plugin_name, str(e))
        elif not metadata.initialized:
            # 实例已存在（由 set_app 提前创建）但从未初始化
            try:
                await pm._finish_activation(metadata)
            except Exception as e:
                raise CorePluginLoadException(plugin_name, str(e))
        else:
            # 已初始化，仅重新注册到事件总线（从 suspend 恢复）
            pm._event_bus.register_new_event(metadata.plugin_instance)
            if pm._command_router is not None:
                pm._command_router.register_plugin(metadata.plugin_instance)
            metadata.enabled = True

        _log.info("插件已启用: {}", plugin_name)
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

    async def discard_failed_plugin(self, dir_name: str) -> None:
        """放弃加载失败的插件（从失败列表和插件列表中移除）。"""
        pm = self._require_plugin_manager()
        pm.discard_failed_plugin(dir_name)
        self._save_state()

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

    def list_timer_messages(self) -> dict:
        """列出全局与各直播间的定时消息（含执行位置指针）。"""
        return self._bot.list_timer_messages()

    def update_timer_message(self, message_id: str, message: str) -> bool:
        """编辑定时消息内容。"""
        return self._bot.update_timer_message(message_id, message)

    def move_timer_message(self, message_id: str, direction: int) -> bool:
        """上移/下移定时消息。"""
        return self._bot.move_timer_message(message_id, direction)

    def skip_timer_message_once(self, message_id: str) -> bool:
        """跳过某条定时消息的下一次播报。"""
        return self._bot.skip_timer_message_once(message_id)

    def set_timer_interval(self, interval: float) -> None:
        """设置定时消息发送间隔（秒），实时生效，不重置位置指针。"""
        self._bot.timer_interval = interval

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
        # 原子写入：先写临时文件再替换，防止写一半崩溃导致文件损坏
        tmp_path = self._state_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._state_path)

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
        livestream.enabled = False  # 默认禁用，由 enabled_livestreams 决定是否启用
        try:
            await livestream._refresh()  # type: ignore[attr-defined]
        except CoreApiException:
            _log.warning("Livestream 恢复时房间信息获取失败: live_id={}", live_id)
        self._livestreams[live_id] = livestream
        _log.info("Livestream 已恢复: live_id={}", live_id)
