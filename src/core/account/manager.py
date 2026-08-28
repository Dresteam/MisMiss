"""账户管理器 —— 面板级账户 CRUD 与 per-account 运行时生命周期。

架构:
    AccountManager(面板级)
      ├── panel.json          账户记录 / 公共 Bot / 授权码
      ├── data/accounts/{id}/  每个账户的 MissevanServer 运行时
      │     ├── server_state.json
      │     ├── config/       插件配置(按账户隔离)
      │     ├── permissions/  插件权限(按账户隔离)
      │     └── plugins/      插件数据(按账户隔离)
      └── 库级 PluginManager   插件库安装/卸载/刷新(共享 plugins/ 目录)

每个账户 = 1 个直播间 + 1 个 Bot(私有 cookie 或面板公共 cookie)。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from core.account.license import LicenseStore
from core.config import ServerConfig
from core.exceptions import (
    CoreAccountExpiredException,
    CoreAccountNotFoundException,
    CoreApiException,
    CoreCookieException,
)
from core.logging import get_logger
from core.server import MissevanServer

_log = get_logger(__name__)

_PANEL_FILE = "panel.json"
_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_expires(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass
class AccountRecord:
    """账户面板记录(存储于 panel.json)。

    Bot cookie 不在此处 —— private 模式存于账户 state 文件,public 模式使用面板公共 cookie。
    账户登录凭据(username/password_hash)由面板管理,支持随时重置。
    """

    id: int
    name: str
    room_id: int | None
    bot_mode: str  # "private" | "public"
    expires_at: str | None  # UTC ISO 字符串,null = 永不过期
    created_at: str
    updated_at: str
    paused_reason: str | None = None  # null | "expiry"
    auto_resume_on_renew: bool = True
    resume_error: str | None = None
    username: str = ""
    password_hash: str = ""

    @property
    def expired(self) -> bool:
        dt = _parse_expires(self.expires_at)
        return dt is not None and datetime.now(timezone.utc) >= dt

    @property
    def days_left(self) -> int | None:
        """剩余天数(向上取整);None = 永不过期;≤0 表示已过期。"""
        dt = _parse_expires(self.expires_at)
        if dt is None:
            return None
        remain = dt - datetime.now(timezone.utc)
        return (remain.days + (1 if remain.seconds > 0 else 0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "room_id": self.room_id,
            "bot_mode": self.bot_mode,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "paused_reason": self.paused_reason,
            "auto_resume_on_renew": self.auto_resume_on_renew,
            "resume_error": self.resume_error,
            "username": self.username,
            "password_hash": self.password_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AccountRecord":
        return cls(
            id=int(d["id"]),
            name=str(d.get("name", "")),
            room_id=d.get("room_id"),
            bot_mode=str(d.get("bot_mode", "private")),
            expires_at=d.get("expires_at"),
            created_at=str(d.get("created_at", _now_iso())),
            updated_at=str(d.get("updated_at", _now_iso())),
            paused_reason=d.get("paused_reason"),
            auto_resume_on_renew=bool(d.get("auto_resume_on_renew", True)),
            resume_error=d.get("resume_error"),
            username=str(d.get("username", "")),
            password_hash=str(d.get("password_hash", "")),
        )


class AccountManager:
    """面板级账户管理器。"""

    def __init__(
        self,
        config: ServerConfig | None = None,
        data_dir: str | None = None,
    ) -> None:
        self._config = config or ServerConfig.load()
        # data_dir 可用环境变量/参数覆盖(如 MISMISS_DATA_DIR),便于测试与数据卷分离
        self._root_data_dir: str = data_dir or self._config.get_str("server.data_dir", "data")
        self._panel_path: str = os.path.join(self._root_data_dir, _PANEL_FILE)
        self._accounts_dir: str = os.path.join(self._root_data_dir, "accounts")

        self._records: dict[int, AccountRecord] = {}
        self._servers: dict[int, MissevanServer] = {}
        self._next_account_id: int = 1
        self._public_bot: dict[str, Any] = {"cookie": "", "permissions": 1, "updated_at": 0}
        self._licenses: dict[str, dict] = {}
        self._license_store = LicenseStore(self._licenses)
        self._app = None
        self._library_pm = None  # 库级 PluginManager(仅 install/uninstall/refresh)

    # ================================================================== #
    # 持久化
    # ================================================================== #

    def _default_panel(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "next_account_id": self._next_account_id,
            "public_bot": dict(self._public_bot),
            "accounts": {},
            "licenses": self._licenses,
        }

    def _save_panel(self) -> None:
        os.makedirs(self._root_data_dir, exist_ok=True)
        data = {
            "schema_version": _SCHEMA_VERSION,
            "next_account_id": self._next_account_id,
            "public_bot": self._public_bot,
            "accounts": {str(k): v.to_dict() for k, v in self._records.items()},
            "licenses": self._licenses,
        }
        tmp_path = self._panel_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._panel_path)

    def load(self) -> None:
        """从 panel.json 加载面板状态(不存在则初始化为空)。"""
        if os.path.exists(self._panel_path):
            try:
                with open(self._panel_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                _log.warning("panel.json 损坏,重建为空面板")
                data = None
            if isinstance(data, dict):
                self._next_account_id = int(data.get("next_account_id", 1))
                self._public_bot = data.get("public_bot") or self._public_bot
                self._licenses = data.get("licenses") or {}
                self._license_store = LicenseStore(self._licenses)
                self._records = {
                    int(k): AccountRecord.from_dict(v)
                    for k, v in (data.get("accounts") or {}).items()
                }
                # 旧数据补录登录凭据(用户名 account{id} + 随机密码,由面板重置)
                _need_save = False
                for rec in self._records.values():
                    if not rec.username:
                        rec.username = f"account{rec.id}"
                        _need_save = True
                    if not rec.password_hash:
                        import secrets
                        rec.password_hash = self._hash_password(secrets.token_hex(8))
                        _need_save = True
                if _need_save:
                    self._save_panel()
                    _log.info("已为旧账户补录登录凭据(可在面板重置)")
                self._next_account_id = max(
                    self._next_account_id,
                    max(self._records.keys(), default=0) + 1,
                )
                _log.info(
                    "面板已加载: {} 个账户, 公共Bot {}",
                    len(self._records),
                    "已配置" if self._public_bot.get("cookie") else "未配置",
                )
                return
        os.makedirs(self._accounts_dir, exist_ok=True)
        self._save_panel()
        _log.info("面板初始化完成(无账户)")

    # ================================================================== #
    # app 注入与库级插件
    # ================================================================== #

    def set_app(self, app) -> None:
        self._app = app

    def set_library_pm(self, pm) -> None:
        self._library_pm = pm

    def get_library_pm(self):
        if self._library_pm is None:
            from core.command.router import CommandRouter
            from core.events.bus import EventBus
            from core.plugin.plugin_manager import PluginManager
            self._library_pm = PluginManager(
                plugin_dir="plugins",
                event_bus=EventBus(),
                config_dir=os.path.join(self._root_data_dir, "_library_tmp", "config"),
                permission_dir=os.path.join(self._root_data_dir, "_library_tmp", "permissions"),
                plugin_data_dir=os.path.join(self._root_data_dir, "_library_tmp", "plugins"),
                disabled_plugins=[],  # 库级不启用任何插件
                pip_mirror=self._config.get_str("plugin.pip_mirror"),
            )
            if self._app is not None:
                self._library_pm.set_app(self._app)
        return self._library_pm

    # ================================================================== #
    # 账户运行时
    # ================================================================== #

    def _server_dirs(self, account_id: int) -> str:
        return os.path.join(self._accounts_dir, str(account_id))

    def _new_server(self, account_id: int) -> MissevanServer:
        """构造账户专属 MissevanServer 实例。

        插件库目录为账户私有副本目录(``data/accounts/{id}/installed_plugins``):
        账户从库「安装」插件即把源码拷贝一份到该目录独立运行,
        各账户之间的插件源码、配置与数据互不干扰。
        """
        data_dir = self._server_dirs(account_id)

        # 插件 UI 路由按账户隔离
        def _prefix(name: str) -> str:
            return f"/api/accounts/{account_id}/plugin/{name}/ui"

        server = MissevanServer(
            self._config,
            data_dir=data_dir,
            state_file="server_state.json",
            plugin_library_dir=os.path.join(data_dir, "installed_plugins"),
            timer_interval_persist="state",
            plugin_ui_prefix=_prefix,
        )
        server.account_id = account_id
        if self._app is not None:
            server.set_app(self._app)
        return server

    async def _start_account(self, rec: AccountRecord) -> MissevanServer:
        """启动账户运行时;public 模式无 Bot 时自动用公共 cookie 创建。"""
        server = self._new_server(rec.id)
        server.account_record = rec
        self._servers[rec.id] = server
        await server.start(auto_resume=not rec.expired)
        # public 模式:注入公共 cookie(未配置公共 cookie 时跳过)
        # 公共 Cookie 的 Bot 权限强制为「仅发送直播间消息」
        if rec.bot_mode == "public" and server.bot.id == 0:
            cookie = self._public_bot.get("cookie", "")
            if cookie:
                from interfaces.bot import BotPermission
                try:
                    await server.create_bot(
                        cookie, permissions=BotPermission.SEND_LIVESTREAM_MESSAGE
                    )
                    _log.info("账户 {} 已使用公共 Cookie 创建 Bot", rec.name)
                except CoreCookieException as e:
                    _log.warning("公共 Cookie 无效,账户 {} Bot 未创建: {}", rec.name, e)
        return server

    async def start_all(self) -> None:
        """启动全部账户运行时(lifespan 调用)。"""
        # 先扫描共享插件库(账户安装列表依赖它)
        try:
            await self.get_library_pm().load_all()
        except Exception as e:
            _log.warning("插件库扫描失败: {}", e)
        for rec in sorted(self._records.values(), key=lambda r: r.id):
            try:
                await self._start_account(rec)
            except Exception as e:
                _log.error("账户 {} 启动失败: {}", rec.id, e)

    async def shutdown_all(self) -> None:
        for aid, server in list(self._servers.items()):
            try:
                await server.shutdown()
            except Exception as e:
                _log.warning("账户 {} 关闭异常: {}", aid, e)
        self._servers.clear()

    async def reload_all(self) -> None:
        """重载全部账户(shutdown_all + start_all)。"""
        await self.shutdown_all()
        await self.start_all()

    # ================================================================== #
    # 查询
    # ================================================================== #

    def reset_credentials(
        self, account_id: int, username: str = "", password: str = ""
    ) -> AccountRecord:
        """重置账户登录凭据(面板操作)。

        :param username: 新用户名(留空保持不变)
        :param password: 新密码(必填,至少 4 位)
        """
        import secrets
        rec = self.get_record(account_id)
        if password:
            if len(password) < 4:
                raise ValueError("密码至少 4 位")
            rec.password_hash = self._hash_password(password)
        elif not rec.password_hash:
            rec.password_hash = self._hash_password(secrets.token_hex(8))
        if username:
            uname = username.strip()
            if any(r.username == uname and r.id != rec.id for r in self._records.values()):
                raise ValueError(f"用户名 '{uname}' 已被其他账户使用")
            rec.username = uname
        rec.updated_at = _now_iso()
        self._save_panel()
        _log.info("账户 {} 登录凭据已重置 (username={})", rec.id, rec.username)
        return rec

    def get_record(self, account_id: int) -> AccountRecord:
        rec = self._records.get(int(account_id))
        if rec is None:
            raise CoreAccountNotFoundException(int(account_id))
        return rec

    def list_records(self) -> list[AccountRecord]:
        return sorted(self._records.values(), key=lambda r: r.id)

    def get_server(self, account_id: int) -> MissevanServer:
        rec = self.get_record(account_id)
        server = self._servers.get(rec.id)
        if server is None:
            raise CoreAccountNotFoundException(rec.id)
        server.account_record = rec
        return server

    def require_active(self, account_id: int) -> MissevanServer:
        """获取账户运行时并执行过期守卫(供写操作依赖调用)。"""
        rec = self.get_record(account_id)
        if rec.expired:
            raise CoreAccountExpiredException(rec.id)
        server = self.get_server(rec.id)
        server._ensure_state_fresh()
        server.account_record = rec
        return server

    def is_expired(self, account_id: int) -> bool:
        return self.get_record(account_id).expired

    def _account_snapshot(self, rec: AccountRecord) -> dict[str, Any]:
        """账户运行时快照(供 overview / 列表)。"""
        server = self._servers.get(rec.id)
        snap: dict[str, Any] = {
            "id": rec.id,
            "name": rec.name,
            "username": rec.username,
            "room_id": rec.room_id,
            "bot_mode": rec.bot_mode,
            "expires_at": rec.expires_at,
            "expired": rec.expired,
            "days_left": rec.days_left,
            "paused_reason": rec.paused_reason,
            "resume_error": rec.resume_error,
        }
        if server is not None:
            bot = server.bot
            lives = server.livestreams
            room = lives.get(rec.room_id) if rec.room_id else None
            snap.update({
                "bot_enabled": bool(bot.enabled),
                "bot_available": bool(server.bot_available),
                "bot_name": bot.name or "",
                "bot_public": rec.bot_mode == "public",
                "room_connected": bool(room and room.is_connected),
                "room_enabled": bool(room and room.enabled),
                "room_name": (room.room_name or "") if room else "",
                "plugin_count": len(server._plugin_manager.list_plugins()),
                "enabled_plugin_count": sum(
                    1 for p in server._plugin_manager.list_plugins() if p.enabled
                ),
                "timer_message_count": server.timer_message_count,
            })
        else:
            snap.update({
                "bot_enabled": False, "bot_available": False, "bot_name": "",
                "bot_public": rec.bot_mode == "public",
                "room_connected": False, "room_enabled": False, "room_name": "",
                "plugin_count": 0, "enabled_plugin_count": 0,
                "timer_message_count": 0,
            })
        return snap

    def overview(self) -> dict[str, Any]:
        """面板总览聚合。"""
        accounts = [self._account_snapshot(r) for r in self.list_records()]
        return {
            "accounts": accounts,
            "total": len(accounts),
            "expired_count": sum(1 for a in accounts if a["expired"]),
            "running_count": sum(1 for a in accounts if not a["expired"] and a["bot_enabled"]),
            "public_bot_configured": bool(self._public_bot.get("cookie")),
            "library_plugin_count": len(self.list_library_plugins()),
            "license_unused": sum(
                1 for info in self._licenses.values() if not info.get("used_at")
            ),
        }

    # ================================================================== #
    # 账户 CRUD
    # ================================================================== #

    @staticmethod
    def _hash_password(password: str) -> str:
        import hashlib
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def authenticate_account(self, username: str, password: str) -> AccountRecord | None:
        """账户登录验证(用户名 + 密码)。"""
        pwd_hash = self._hash_password(password or "")
        for rec in self._records.values():
            if rec.username == username and rec.password_hash == pwd_hash:
                return rec
        return None

    async def create_account(
        self,
        name: str,
        *,
        room_id: int | None = None,
        bot_mode: str = "private",
        cookie: str = "",
        permissions: Any = None,
        duration_days: int = -1,
        username: str = "",
        password: str = "",
    ) -> AccountRecord:
        """创建账户并启动其运行时。

        - ``duration_days``: 有效时长(天),-1 为永久
        - private 模式提供 cookie 时立即验证并创建 Bot(无效则拒绝创建)
        - public 模式使用面板公共 cookie(若有);无公共 cookie 时 Bot 留空待配置
        - username 留空自动生成 ``account{id}``;password 为空自动生成随机密码
        """
        import secrets
        name = (name or "").strip()
        if not name:
            raise ValueError("账户名称不能为空")
        if bot_mode not in ("private", "public"):
            raise ValueError("bot_mode 必须为 private 或 public")

        aid = self._next_account_id
        self._next_account_id += 1

        # 有效时长: -1 → 永久;N → now + N 天
        if duration_days < 0:
            expires_at: str | None = None
        else:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()

        # 登录凭据(用户名必填且全局唯一,用于账户分辨)
        uname = (username or "").strip()
        if not uname:
            raise ValueError("登录用户名必填")
        if any(r.username == uname for r in self._records.values()):
            raise ValueError(f"用户名 '{uname}' 已被其他账户使用")
        pwd = (password or "").strip() or secrets.token_hex(8)
        if len(pwd) < 4:
            raise ValueError("密码至少 4 位")

        rec = AccountRecord(
            id=aid,
            name=name,
            room_id=room_id,
            bot_mode=bot_mode,
            expires_at=expires_at,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            username=uname,
            password_hash=self._hash_password(pwd),
        )
        os.makedirs(self._server_dirs(aid), exist_ok=True)
        self._records[aid] = rec
        try:
            server = await self._start_account(rec)
        except Exception:
            self._records.pop(aid, None)
            self._servers.pop(aid, None)
            raise

        # 房间绑定
        if room_id:
            try:
                await server.add_livestream(int(room_id))
                _log.info("账户 {} 已绑定直播间 {}", name, room_id)
            except Exception as e:
                _log.warning("账户 {} 直播间绑定失败: {}", name, e)

        # private 模式:验证 cookie 并创建 Bot
        if bot_mode == "private" and cookie.strip():
            from interfaces.bot import BotPermission
            perms = permissions if permissions is not None else BotPermission.SEND_LIVESTREAM_MESSAGE
            try:
                await server.create_bot(cookie.strip(), permissions=perms)
            except CoreCookieException as e:
                _log.error("账户 {} Bot 创建失败: {}", name, e)
                raise ValueError(f"Cookie 无效: {e}")
        self._save_panel()
        _log.info("账户已创建: id={} name={} mode={}", aid, name, bot_mode)
        return rec

    async def delete_account(self, account_id: int, purge_data: bool = False) -> None:
        """删除账户:停止运行时、移除记录;purge_data 时删除数据目录。"""
        rec = self.get_record(account_id)
        server = self._servers.pop(rec.id, None)
        if server is not None:
            try:
                await server.shutdown()
            except Exception as e:
                _log.warning("账户 {} 关闭异常: {}", rec.id, e)
        self._records.pop(rec.id, None)
        if purge_data:
            shutil.rmtree(self._server_dirs(rec.id), ignore_errors=True)
        self._save_panel()
        _log.info("账户已删除: id={} name={}{}", rec.id, rec.name,
                  "(已清除数据)" if purge_data else "(数据目录保留)")

    async def switch_bot_mode(
        self, account_id: int, mode: str, cookie: str = "", permissions: Any = None
    ) -> AccountRecord:
        """切换账户 Bot 模式(账户持有者与面板均可调用)。

        - ``public``:改用面板公共 Cookie(未配置则拒绝),权限强制降级为仅发送直播间消息
        - ``private``:改用账户自定义 Cookie(必填,同模式下即更新 Cookie),
          可传入完整权限集(自定义 Cookie 才允许更完整权限设置)
        """
        rec = self.get_record(account_id)
        server = self.get_server(account_id)
        if mode not in ("public", "private"):
            raise ValueError("mode 必须为 public 或 private")

        if mode == "public":
            pub_cookie = self._public_bot.get("cookie", "")
            if not pub_cookie:
                raise ValueError("面板公共 Cookie 未配置,无法切换为公共模式")
            # 公共 Cookie 权限强制降级为仅发送直播间消息
            from interfaces.bot import BotPermission
            await server.update_cookie(
                pub_cookie, permissions=BotPermission.SEND_LIVESTREAM_MESSAGE
            )
            rec.bot_mode = "public"
        else:
            cookie = (cookie or "").strip()
            if not cookie:
                raise ValueError("自定义 Cookie 不能为空")
            await server.update_cookie(cookie, permissions=permissions)
            rec.bot_mode = "private"

        rec.updated_at = _now_iso()
        self._save_panel()
        _log.info("账户 {} Bot 模式已切换为 {}", rec.id, mode)
        return rec

    async def update_account(self, account_id: int, **fields: Any) -> AccountRecord:
        """更新账户字段(name / room_id / bot_mode / expires_at 等)。

        bot_mode 切换:
        - private → public:用面板公共 cookie 重建 Bot
        - public → private:必须同时提供 cookie
        """
        rec = self.get_record(account_id)
        server = self.get_server(account_id)

        if "name" in fields and fields["name"]:
            rec.name = str(fields["name"]).strip()

        # 房间切换
        new_room = fields.get("room_id", rec.room_id)
        if new_room != rec.room_id:
            if rec.room_id:
                try:
                    await server.remove_livestream(int(rec.room_id))
                except KeyError:
                    pass
            if new_room:
                await server.add_livestream(int(new_room))
            rec.room_id = int(new_room) if new_room else None

        # Bot 模式切换
        new_mode = fields.get("bot_mode", rec.bot_mode)
        if new_mode not in ("private", "public"):
            raise ValueError("bot_mode 必须为 private 或 public")
        if new_mode != rec.bot_mode:
            if new_mode == "public":
                cookie = self._public_bot.get("cookie", "")
                if not cookie:
                    raise ValueError("面板公共 Cookie 未配置,无法切换为公共模式")
                await server.update_cookie(cookie)
            else:
                cookie = str(fields.get("cookie", "")).strip()
                if not cookie:
                    raise ValueError("切换为私有模式必须提供 Cookie")
                await server.update_cookie(cookie)
            rec.bot_mode = new_mode

        if "expires_at" in fields:
            rec.expires_at = fields["expires_at"]

        rec.updated_at = _now_iso()
        self._save_panel()
        return rec

    # ================================================================== #
    # 到期与续期
    # ================================================================== #

    async def stop_for_expiry(self, account_id: int) -> None:
        """到期强制停用(幂等):停 Bot → 断房间 → 暂停插件(保留启用标记)。"""
        rec = self.get_record(account_id)
        if rec.paused_reason == "expiry":
            return
        server = self._servers.get(rec.id)
        if server is not None:
            server.bot.enabled = False
            for lid in list(server.livestreams.keys()):
                try:
                    server.disable_livestream(lid)
                except Exception as e:
                    _log.warning("账户 {} 断开直播间 {} 失败: {}", rec.id, lid, e)
            try:
                server._plugin_manager.suspend_all()
            except Exception as e:
                _log.warning("账户 {} 暂停插件失败: {}", rec.id, e)
            server._save_state()
        rec.paused_reason = "expiry"
        rec.updated_at = _now_iso()
        self._save_panel()
        _log.info("账户 {} 已到期,已强制停用", rec.name)

    async def resume_after_renew(self, account_id: int) -> dict[str, Any]:
        """续期后自动恢复:启用 Bot → 连接房间 → 恢复插件。

        :return: {"resumed": bool, "errors": [str, ...]}
        """
        rec = self.get_record(account_id)
        server = self.get_server(account_id)
        errors: list[str] = []

        try:
            await server.enable_bot()
        except Exception as e:
            errors.append(f"Bot 启用失败: {e}")
        if rec.room_id:
            lives = server.livestreams
            if rec.room_id not in lives:
                try:
                    await server.add_livestream(int(rec.room_id))
                except Exception as e:
                    errors.append(f"直播间恢复失败: {e}")
            else:
                try:
                    await server.enable_livestream(int(rec.room_id))
                except Exception as e:
                    errors.append(f"直播间连接失败: {e}")
        try:
            server._plugin_manager.resume_all()
        except Exception as e:
            errors.append(f"插件恢复失败: {e}")

        rec.resume_error = "; ".join(errors) if errors else None
        rec.updated_at = _now_iso()
        self._save_panel()
        if errors:
            _log.warning("账户 {} 恢复完成但有错误: {}", rec.name, rec.resume_error)
        else:
            _log.info("账户 {} 已恢复运行", rec.name)
        return {"resumed": not errors, "errors": errors}

    async def _apply_renewal(self, account_id: int, new_expires: str | None) -> AccountRecord:
        """设置新的到期时间;若此前因到期暂停且新时间未过期,自动恢复。"""
        rec = self.get_record(account_id)
        was_expiry = rec.paused_reason == "expiry"
        rec.expires_at = new_expires
        rec.updated_at = _now_iso()
        if was_expiry and not rec.expired:
            rec.paused_reason = None
            if rec.auto_resume_on_renew:
                await self.resume_after_renew(account_id)
        self._save_panel()
        return rec

    async def renew_days(self, account_id: int, days: int) -> AccountRecord:
        """管理员续期 N 天(从 max(now, 当前到期时间) 起算)。"""
        if days <= 0:
            raise ValueError("续期天数必须大于 0")
        base = _parse_expires(self.get_record(account_id).expires_at)
        if base is None or base < datetime.now(timezone.utc):
            base = datetime.now(timezone.utc)
        new_expires = (base + timedelta(days=days)).isoformat()
        return await self._apply_renewal(account_id, new_expires)

    async def redeem(self, account_id: int, code: str) -> AccountRecord:
        """兑换授权码:叠加天数并标记已使用。"""
        days = self._license_store.redeem(code, account_id)
        rec = self.get_record(account_id)
        base = _parse_expires(rec.expires_at)
        if base is None or base < datetime.now(timezone.utc):
            base = datetime.now(timezone.utc)
        new_expires = (base + timedelta(days=days)).isoformat()
        result = await self._apply_renewal(account_id, new_expires)
        self._save_panel()  # _apply_renewal 已保存;此处确保兑换标记落盘(双保险)
        return result

    # ================================================================== #
    # 公共 Bot
    # ================================================================== #

    def get_public_bot(self) -> dict[str, Any]:
        return dict(self._public_bot)

    async def set_public_bot(self, cookie: str, permissions: Any = None) -> None:
        """保存面板公共 Cookie(仅保存,不立即下发;同时刷新并缓存 Bot 资料)。

        公共 Cookie 的 Bot 权限**强制**为「仅发送直播间消息」,
        忽略传入的 permissions(规则:只有自定义 Cookie 才允许更完整权限)。
        """
        import time
        from interfaces.bot import BotPermission
        self._public_bot["cookie"] = cookie.strip()
        self._public_bot["permissions"] = int(BotPermission.SEND_LIVESTREAM_MESSAGE.value)
        # epoch 秒(与 PublicBotResponse.updated_at 的 float 语义一致)
        self._public_bot["updated_at"] = time.time()
        self._save_panel()
        _log.info("公共 Cookie 已保存(未下发,权限固定为发送直播间消息)")
        # 尝试刷新 Bot 资料,失败仅记录(卡片显示"不可用")
        try:
            await self.refresh_public_bot()
        except Exception as e:
            _log.warning("公共 Cookie 资料刷新失败: {}", e)

    async def refresh_public_bot(self) -> dict[str, Any]:
        """用公共 Cookie 创建临时 Bot 刷新资料,并缓存到面板状态。

        :raises CoreCookieException: Cookie 无效
        :raises CoreApiException: API 请求失败
        :return: 缓存的 Bot 资料字典
        """
        cookie = self._public_bot.get("cookie", "")
        if not cookie:
            raise ValueError("公共 Cookie 未配置")
        from core.bot.mis_bot import MissevanBot
        from interfaces.bot import BotPermission
        try:
            perms = BotPermission(int(self._public_bot.get("permissions", 1)))
        except ValueError:
            perms = BotPermission.SEND_LIVESTREAM_MESSAGE
        bot = MissevanBot(cookie, permissions=perms)
        try:
            await bot.refresh()
        except (CoreCookieException, CoreApiException):
            self._public_bot["bot_available"] = False
            self._save_panel()
            raise
        self._public_bot.update({
            "bot_name": bot.name or "",
            "bot_id": int(bot.id or 0),
            "introduction": bot.introduction or "",
            "icon_url": bot.icon_url or "",
            "bot_available": True,
        })
        self._save_panel()
        _log.info("公共 Cookie Bot 资料已刷新: {}", bot)
        return self.get_public_bot()

    async def verify_public_bot(self) -> dict[str, Any]:
        """验证公共 Cookie 有效性。

        :return: {"valid": bool, "name": str, "message": str}
        """
        try:
            await self.refresh_public_bot()
            return {"valid": True, "name": self._public_bot.get("bot_name", ""), "message": "Cookie 有效"}
        except CoreCookieException:
            return {"valid": False, "name": "", "message": "Cookie 已过期或无效"}
        except CoreApiException as e:
            return {"valid": False, "name": "", "message": f"API 错误: {e}"}
        except ValueError as e:
            return {"valid": False, "name": "", "message": str(e)}

    def clear_public_bot(self) -> None:
        """删除公共 Cookie(已运行的公共账户实例保持运行,重启后失效)。"""
        self._public_bot = {"cookie": "", "permissions": 1, "updated_at": 0}
        self._save_panel()
        _log.info("公共 Cookie 已删除")

    async def apply_public_cookie(self) -> dict[str, Any]:
        """将公共 Cookie 下发到所有 public 模式账户。"""
        cookie = self._public_bot.get("cookie", "")
        if not cookie:
            raise ValueError("公共 Cookie 未配置")
        failed: list[dict[str, Any]] = []
        for rec in self.list_records():
            if rec.bot_mode != "public":
                continue
            server = self._servers.get(rec.id)
            if server is None:
                failed.append({"account_id": rec.id, "error": "运行时未启动"})
                continue
            try:
                from interfaces.bot import BotPermission
                try:
                    perms = BotPermission(int(self._public_bot.get("permissions", 1)))
                except ValueError:
                    perms = BotPermission.SEND_LIVESTREAM_MESSAGE
                if server.bot.id == 0:
                    await server.create_bot(cookie, permissions=perms)
                else:
                    await server.update_cookie(cookie)
            except Exception as e:
                failed.append({"account_id": rec.id, "error": str(e)})
        if failed:
            _log.warning("公共 Cookie 下发部分失败: {}", failed)
        else:
            _log.info("公共 Cookie 已下发到全部 public 账户")
        return {"failed": failed}

    # ================================================================== #
    # 库级插件(共享 plugins/ 目录,各账户自行启用)
    # ================================================================== #

    async def refresh_library(self) -> None:
        """刷新插件库并同步各账户(仅扫描,不改变启用状态)。"""
        pm = self.get_library_pm()
        await pm.load_all()
        for rec in self.list_records():
            server = self._servers.get(rec.id)
            if server is not None:
                await server.refresh_plugins()
        _log.info("插件库已刷新: {} 个插件", len(pm.list_plugins()))

    def list_library_plugins(self) -> list[dict[str, Any]]:
        """库级插件列表(含被哪些账户启用)。"""
        pm = self.get_library_pm()
        used: dict[str, list[int]] = {}
        for rec in self.list_records():
            server = self._servers.get(rec.id)
            if server is None:
                continue
            for meta in server._plugin_manager.list_plugins():
                if meta.enabled:
                    used.setdefault(meta.name, []).append(rec.id)
        result = []
        for meta in pm.list_plugins():
            item = {
                "name": meta.name,
                "plugin_id": meta.plugin_id,
                "author": meta.author,
                "version": meta.version,
                "display_name": meta.display_name,
                "short_desc": meta.short_desc,
                "desc": meta.desc,
                "has_config": meta.config_schema_path is not None,
                "has_readme": meta.readme_path is not None,
                "has_ui": meta.ui_schema_path is not None,
                "has_changelog": bool(meta.module_path),
                "used_by_accounts": sorted(used.get(meta.name, [])),
            }
            result.append(item)
        return result

    async def install_plugin_to_account(self, account_id: int, plugin_name: str) -> None:
        """账户从插件库安装插件:拷贝源码副本到账户目录并刷新实例。

        :raises CorePluginNotFoundException: 插件库中不存在
        :raises ValueError: 账户已安装该插件
        """
        from core.exceptions import CorePluginNotFoundException
        lib_pm = self.get_library_pm()
        src = os.path.join("plugins", plugin_name)
        if not os.path.isdir(src):
            raise CorePluginNotFoundException(plugin_name)
        server = self.get_server(account_id)
        dest_dir = os.path.join(self._server_dirs(account_id), "installed_plugins")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, plugin_name)
        if os.path.exists(dest):
            raise ValueError(f"插件 '{plugin_name}' 已安装到该账户")
        shutil.copytree(src, dest)
        await server.refresh_plugins()
        _log.info("账户 {} 已安装插件 {}", account_id, plugin_name)

    async def uninstall_plugin_from_account(
        self, account_id: int, plugin_name: str,
        delete_config: bool = False, delete_data: bool = False,
    ) -> None:
        """账户卸载插件:停止实例、删除源码副本,可选清除配置/数据。"""
        server = self.get_server(account_id)
        pm = server._plugin_manager
        meta = pm.get_plugin(plugin_name)
        if meta is not None and meta.enabled:
            try:
                await pm.disable_plugin(plugin_name)
            except Exception as e:
                _log.warning("账户 {} 停用插件 {} 失败: {}", account_id, plugin_name, e)
        base = self._server_dirs(account_id)
        shutil.rmtree(os.path.join(base, "installed_plugins", plugin_name), ignore_errors=True)
        if delete_config:
            shutil.rmtree(os.path.join(base, "config", plugin_name), ignore_errors=True)
            shutil.rmtree(os.path.join(base, "permissions", plugin_name), ignore_errors=True)
        if delete_data:
            shutil.rmtree(os.path.join(base, "plugins", plugin_name), ignore_errors=True)
        # load_all 只做增量合并,不会移除目录已消失的插件 → 显式清除条目
        pm._plugins.pop(plugin_name, None)
        pm._failed_plugins.pop(plugin_name, None)
        await server.refresh_plugins()
        server._save_state()
        _log.info("账户 {} 已卸载插件 {}", account_id, plugin_name)

    def list_available_plugins(self, account_id: int) -> list[dict[str, Any]]:
        """账户可安装的库插件列表(含是否已安装)。"""
        server = self._servers.get(account_id)
        installed = {
            m.name for m in server._plugin_manager.list_plugins()
        } if server else set()
        result = []
        for item in self.list_library_plugins():
            result.append({**item, "installed": item["name"] in installed})
        return result

    async def reload_plugin_in_accounts(self, plugin_name: str) -> None:
        """插件库更新后,重载各账户中已启用该插件的实例。"""
        for rec in self.list_records():
            server = self._servers.get(rec.id)
            if server is None:
                continue
            pm = server._plugin_manager
            meta = pm.get_plugin(plugin_name)
            if meta is None or not meta.enabled:
                continue
            try:
                was_enabled = meta.enabled
                pm.suspend_plugin(plugin_name)
                new_meta = await pm.reload_plugin(plugin_name)
                new_meta.enabled = was_enabled
                if was_enabled and server.bot_available:
                    pm.resume_plugin(plugin_name)
                _log.info("账户 {} 插件 {} 已重载为新版本", rec.id, plugin_name)
            except Exception as e:
                _log.warning("账户 {} 插件 {} 更新后重载失败: {}", rec.id, plugin_name, e)

    async def uninstall_plugin(
        self, plugin_name: str, delete_config: bool = False, delete_data: bool = False
    ) -> None:
        """卸载库插件(仅从共享库删除;各账户的私有副本独立运行不受影响)。"""
        pm = self.get_library_pm()
        pm.uninstall_plugin(plugin_name, delete_config=delete_config, delete_data=delete_data)
        await self.refresh_library()

    # ================================================================== #
    # 授权码(委托 LicenseStore)
    # ================================================================== #

    def generate_licenses(self, count: int, days: int, note: str = "") -> list[str]:
        codes = self._license_store.generate(count, days, note)
        self._save_panel()
        return codes

    def list_licenses(self) -> list[dict[str, Any]]:
        return self._license_store.list()

    def revoke_license(self, code: str) -> None:
        self._license_store.revoke(code)
        self._save_panel()
