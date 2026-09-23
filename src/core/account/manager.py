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
    CoreLicenseException,
)
from core.logging import get_logger, reset_account, set_account
from core.server import MissevanServer
from core.version import CURRENT_VERSION

_log = get_logger(__name__)

_PANEL_FILE = "panel.json"
_SCHEMA_VERSION = 1

# 广播类消息（更新提示、面板全局消息）的最长字符数 ——
# 直播弹幕有长度上限，超出会被平台拒绝，故统一在入库前裁剪
BROADCAST_MAX_LEN = 80

# 等待消息队列排空的秒数：调用方可能紧接着要重启进程，必须等真正发出去
BROADCAST_DRAIN_TIMEOUT = 15.0


def clip_broadcast(message: object) -> str:
    """裁剪广播消息：压掉多余空白并截断到 :data:`BROADCAST_MAX_LEN`。

    ``None`` / 非字符串一律按字符串处理；纯空白返回空串（调用方据此跳过发送）。
    """
    if message is None:
        return ""
    return " ".join(str(message).split())[:BROADCAST_MAX_LEN]


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
    # 最后一次确认已读更新日志的版本；"" = 尚未确认过（升级到本版本后会弹一次）
    seen_changelog_version: str = ""
    # 从插件库安装插件后是否自动启用（账户级偏好，默认关闭）
    auto_enable_on_install: bool = False

    @property
    def is_permanent(self) -> bool:
        """是否永久有效(``expires_at`` 为 ``None``)。

        注意与「已过期」的区别:``_parse_expires`` 对两者都返回 ``None``,
        因此判断时不能只依赖解析结果。
        """
        return self.expires_at is None

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
            "seen_changelog_version": self.seen_changelog_version,
            "auto_enable_on_install": self.auto_enable_on_install,
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
            seen_changelog_version=str(d.get("seen_changelog_version", "")),
            auto_enable_on_install=bool(d.get("auto_enable_on_install", False)),
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
        # 默认插件:新建账户时自动安装并启用(见 _install_default_plugins)
        self._default_plugins: list[str] = []
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
            "default_plugins": list(self._default_plugins),
        }

    def _save_panel(self) -> None:
        os.makedirs(self._root_data_dir, exist_ok=True)
        data = {
            "schema_version": _SCHEMA_VERSION,
            "next_account_id": self._next_account_id,
            "public_bot": self._public_bot,
            "accounts": {str(k): v.to_dict() for k, v in self._records.items()},
            "licenses": self._licenses,
            "default_plugins": list(self._default_plugins),
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
                self._default_plugins = [
                    str(n) for n in (data.get("default_plugins") or []) if n
                ]
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
        _log.debug("面板初始化完成(无账户)")

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
        # 标记账户上下文：启动过程中创建的后台任务（Bot 消费循环、直播间 WS、
        # 插件处理器）会按 contextvars 的复制语义继承它，日志自动带上账户名
        token = set_account(rec.name)
        try:
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
                        _log.debug("账户 {} 已使用公共 Cookie 创建 Bot", rec.name)
                    except CoreCookieException as e:
                        _log.warning("公共 Cookie 无效,账户 {} Bot 未创建: {}", rec.name, e)
            return server
        finally:
            reset_account(token)

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

    def change_account_password(
        self, account_id: int, current_password: str, new_password: str
    ) -> AccountRecord:
        """账户自助修改密码(需验证原密码)。

        :param current_password: 原密码,错误时抛 ValueError("原密码错误")
        :param new_password: 新密码(至少 4 位)
        :raises ValueError: 原密码错误 / 新密码不足 4 位
        """
        rec = self.get_record(account_id)
        if self._hash_password(current_password or "") != rec.password_hash:
            raise ValueError("原密码错误")
        pwd = (new_password or "").strip()
        if len(pwd) < 4:
            raise ValueError("新密码至少 4 位")
        rec.password_hash = self._hash_password(pwd)
        rec.updated_at = _now_iso()
        self._save_panel()
        _log.info("账户 {} 已自助修改登录密码", rec.id)
        return rec

    def ack_changelog(self, account_id: int, version: str) -> AccountRecord:
        """记录账户已读的更新日志版本(弹窗关闭时调用)。

        版本号由调用方取服务端当前版本传入,不信任客户端上报。

        :param version: 已确认的版本号
        """
        rec = self.get_record(account_id)
        if rec.seen_changelog_version == version:
            return rec
        rec.seen_changelog_version = version
        rec.updated_at = _now_iso()
        self._save_panel()
        _log.info("账户 {} 已确认更新日志 v{}", rec.id, version)
        return rec

    def set_auto_enable_on_install(self, account_id: int, enabled: bool) -> AccountRecord:
        """设置「从插件库安装插件后自动启用」偏好（账户自助，默认关闭）。

        :param enabled: 是否自动启用
        """
        rec = self.get_record(account_id)
        if rec.auto_enable_on_install == bool(enabled):
            return rec
        rec.auto_enable_on_install = bool(enabled)
        rec.updated_at = _now_iso()
        self._save_panel()
        _log.info("账户 {} 安装插件自动启用 = {}", rec.id, rec.auto_enable_on_install)
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
            "auto_enable_on_install": rec.auto_enable_on_install,
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
                "normal_timer_message_count": server.normal_timer_message_count,
                "plugin_timer_message_count": server.plugin_timer_message_count,
            })
        else:
            snap.update({
                "bot_enabled": False, "bot_available": False, "bot_name": "",
                "bot_public": rec.bot_mode == "public",
                "room_connected": False, "room_enabled": False, "room_name": "",
                "plugin_count": 0, "enabled_plugin_count": 0,
                "timer_message_count": 0,
                "normal_timer_message_count": 0,
                "plugin_timer_message_count": 0,
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
            # 全新账户不提示「更新」——它没有经历过本次更新
            seen_changelog_version=CURRENT_VERSION,
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
        # 默认插件：安装并启用（失败仅告警，不影响账户创建）
        default_applied = await self._install_default_plugins(aid)

        self._save_panel()
        _log.info(
            "账户已创建: id={} name={} mode={} 默认插件={}",
            aid, name, bot_mode, default_applied or "无",
        )
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
        """管理员续期 N 天(从 max(now, 当前到期时间) 起算)。

        永久账户叠加天数没有意义——「永久 + N 天」仍是永久,故原样返回。
        需把永久改成限期请用「设置剩余天数」(``_apply_renewal`` 传具体时间)。
        """
        if days <= 0:
            raise ValueError("续期天数必须大于 0")
        rec = self.get_record(account_id)
        if rec.is_permanent:
            return rec
        base = _parse_expires(rec.expires_at)
        if base is None or base < datetime.now(timezone.utc):
            # 已过期(或到期时间不可解析)时从当前时间起算
            base = datetime.now(timezone.utc)
        new_expires = (base + timedelta(days=days)).isoformat()
        return await self._apply_renewal(account_id, new_expires)

    async def redeem(self, account_id: int, code: str) -> AccountRecord:
        """兑换授权码:叠加天数并标记已使用。

        永久账户无需兑换,直接拒绝——**且在消耗授权码之前拒绝**,
        避免用户白白损失一个码。
        """
        rec = self.get_record(account_id)
        if rec.is_permanent:
            raise CoreLicenseException("该账户为永久有效,无需兑换授权码")
        days = self._license_store.redeem(code, account_id)
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
        return {"failed": failed}

    # ================================================================== #
    # 库级插件(共享 plugins/ 目录,各账户自行启用)
    # ================================================================== #

    async def refresh_library(self) -> None:
        """刷新插件库并同步各账户(仅扫描,不改变启用状态)。

        扫描会扇出到库与每个账户的 PluginManager，逐账户打日志会刷屏，
        故此处只在结束时汇总一条；单次扫描发现的新插件由
        :meth:`PluginManager.load_all` 各自汇总。
        """
        pm = self.get_library_pm()
        prev_count = len(pm.list_plugins())
        await pm.load_all()
        synced = 0
        for rec in self.list_records():
            server = self._servers.get(rec.id)
            if server is not None:
                await server.refresh_plugins()
                synced += 1
        new_count = len(pm.list_plugins())
        _log.info(
            "插件库已刷新: {} 个插件(新增 {}),已同步 {} 个账户",
            new_count, max(0, new_count - prev_count), synced,
        )

    # ================================================================== #
    # 批量补偿时长
    # ================================================================== #

    def select_compensation_targets(
        self,
        *,
        exclude_expired: bool = False,
        exclude_active: bool = False,
        exclude_over_days_left: int | None = None,
        exclude_ids: list[int] | None = None,
    ) -> list[AccountRecord]:
        """挑出可补偿的账户（不改变任何状态）。

        **默认全选，参数用于排除** —— 补偿通常面向全体，逐个勾选太费事，
        所以这里的每个参数都是「把谁剔出去」：

        - 永久账户始终排除（加天数对它们没有意义），无需参数
        - ``exclude_expired`` / ``exclude_active`` 剔掉对应到期状态的账户；
          两个都开就没有候选了，这是自然结果而非特例
        - ``exclude_over_days_left`` 剔掉剩余天数多于 N 的（即只留「快到期」的）；
          已过期账户的剩余天数 ≤ 0，天然落在保留范围内
        - ``exclude_ids`` 剔掉指定账户，供手动取消勾选

        :return: 命中的账户记录（按 id 升序）
        """
        excluded = set(exclude_ids or [])
        result: list[AccountRecord] = []
        for rec in self.list_records():
            if rec.is_permanent:
                continue  # 永久账户无需补偿
            if rec.id in excluded:
                continue
            if rec.expired:
                if exclude_expired:
                    continue
            elif exclude_active:
                continue
            if exclude_over_days_left is not None:
                left = rec.days_left
                if left is None or left > exclude_over_days_left:
                    continue
            result.append(rec)
        return result

    async def compensate_accounts(
        self,
        days: int,
        *,
        exclude_expired: bool = False,
        exclude_active: bool = False,
        exclude_over_days_left: int | None = None,
        exclude_ids: list[int] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """给筛选出的账户各补偿 ``days`` 天时长。

        叠加规则与单账户续期完全一致（:meth:`renew_days`）：从
        ``max(现在, 当前到期时间)`` 起算，所以已过期的账户补完即从今天续上；
        补完是否自动恢复运行也沿用账户自身的 ``auto_resume_on_renew`` 偏好 ——
        不引入第二套语义。

        目标账户**默认全选**，各 ``exclude_*`` 参数用于排除，语义见
        :meth:`select_compensation_targets`。

        :param dry_run: 只挑人不动手，供二次确认弹窗预览「将要补谁」
        :return: ``{"compensated": [...], "skipped": [...], "failed": [...],
            "groups": [...], "dry_run": bool, "days": int}``
        """
        if days <= 0:
            raise ValueError("补偿天数必须大于 0")

        expired_names: list[str] = []
        active_names: list[str] = []
        # 永久账户显式汇报成「跳过」：否则管理员会奇怪某个账户为什么没被补上
        skipped: list[str] = [
            f"{rec.name}（永久账户，无需补偿）"
            for rec in self.list_records() if rec.is_permanent
        ]
        failed: list[str] = []

        for rec in self.select_compensation_targets(
            exclude_expired=exclude_expired,
            exclude_active=exclude_active,
            exclude_over_days_left=exclude_over_days_left,
            exclude_ids=exclude_ids,
        ):
            # 归组要用**补偿前**的状态：renew_days 会就地改写 rec.expires_at，
            # 补完之后再看 rec.expired 永远是 False
            was_expired = rec.expired
            try:
                if not dry_run:
                    await self.renew_days(rec.id, days)
            except Exception as e:
                _log.warning("账户 {} 补偿时长失败: {}", rec.name, e)
                failed.append(f"{rec.name}（{e}）")
                continue
            (expired_names if was_expired else active_names).append(rec.name)

        groups: list[dict[str, Any]] = []
        if expired_names:
            groups.append({"label": "已过期（补后按偏好恢复运行）", "items": expired_names})
        if active_names:
            groups.append({"label": "未过期（在现有到期时间上顺延）", "items": active_names})

        total = len(expired_names) + len(active_names)
        if not dry_run:
            _log.info(
                "批量补偿时长: {} 个账户各 +{} 天（跳过 {} / 失败 {}）",
                total, days, len(skipped), len(failed),
            )

        return {
            "compensated": expired_names + active_names,
            "skipped": skipped,
            "failed": failed,
            "groups": groups,
            "days": days,
            "dry_run": dry_run,
        }

    # ================================================================== #
    # 全局消息
    # ================================================================== #

    async def broadcast_to_livestreams(self, message: str) -> dict[str, Any]:
        """用各账户的机器人，向**已启用且正在开播**的直播间各发一条消息。

        与「更新提示消息」共用同一条通道：只发给真正在播的房间，
        未绑定 / 未启用 / 未开播 / 已过期的账户逐个跳过。逐个账户独立兜底 ——
        任一账户的 Bot 不可用、房间没开播或发送异常，都只影响该账户。

        消息入队后即返回，故这里会等到消费循环真正发完再收尾；
        调用方若紧接着要重启进程（如程序更新），必须依赖这一等待。

        :param message: 消息文本，超长会被裁剪
        :return: ``{"sent": 成功数, "skipped": 跳过数, "failed": 失败数, "text": 实发文本}``
        """
        text = clip_broadcast(message)
        result: dict[str, Any] = {
            "sent": 0, "skipped": 0, "failed": 0, "text": text,
        }
        if not text:
            return result

        bots: list[Any] = []
        for rec in self.list_records():
            try:
                if rec.expired or not rec.room_id:
                    result["skipped"] += 1
                    continue
                server = self.get_server(rec.id)
                # 多 worker 下 Bot / 直播间可能还没在本 worker 恢复
                await server._ensure_bot_restored()
                if not server.bot_available:
                    _log.debug("账户 {} 的 Bot 不可用，跳过全局消息", rec.name)
                    result["skipped"] += 1
                    continue
                room = server.livestreams.get(int(rec.room_id))
                if room is None or not room.enabled:
                    _log.debug("账户 {} 的直播间未启用，跳过全局消息", rec.name)
                    result["skipped"] += 1
                    continue
                if not room.is_streaming:
                    _log.debug("账户 {} 的直播间未开播，跳过全局消息", rec.name)
                    result["skipped"] += 1
                    continue
                await room.send_message(text)
                bots.append(room.bot)
                result["sent"] += 1
            except Exception as e:
                _log.warning("账户 {} 发送全局消息失败: {}", rec.name, e)
                result["failed"] += 1

        for bot in bots:
            try:
                await bot.wait_message_queue_idle(BROADCAST_DRAIN_TIMEOUT)
            except Exception as e:
                _log.warning("等待全局消息发送完成时出错: {}", e)

        _log.info(
            "全局消息{}: {}（成功 {} / 跳过 {} / 失败 {}）",
            "已发送" if result["sent"] else "无需发送",
            text, result["sent"], result["skipped"], result["failed"],
        )
        return result

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
                "has_changelog": meta.changelog_path is not None,
                "is_default": meta.name in self._default_plugins,
                "used_by_accounts": sorted(used.get(meta.name, [])),
                "last_error": meta.last_error,
            }
            result.append(item)
        return result

    async def install_plugin_to_account(self, account_id: int, plugin_name: str) -> str:
        """账户从插件库安装插件:拷贝源码副本到账户目录并刷新实例。

        账户开启「安装插件自动启用」偏好时会随即启用；启用失败**不影响安装结果**
        （插件保留为已安装+停用，失败原因写入 last_error 并进日志），仅在返回值中说明。

        :return: 描述实际结果的消息（供界面直接展示）
        :raises CorePluginNotFoundException: 插件库中不存在
        :raises ValueError: 账户已安装该插件
        """
        from core.exceptions import CorePluginNotFoundException
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
        # 安装后立即注册 UI 路由:新插件处于禁用状态只有元数据,
        # 需补创建轻量实例以注册路由,否则插件主页 404(须等到启用或重启)
        pm = server._plugin_manager
        meta = pm.get_plugin(plugin_name)
        if meta is not None:
            pm._ensure_plugin_loaded(meta)
        _log.info("账户 {} 已安装插件 {}", account_id, plugin_name)

        if not self.get_record(account_id).auto_enable_on_install:
            return f"插件 '{plugin_name}' 已安装（默认停用）"

        try:
            await server.enable_plugin(plugin_name)
        except Exception as e:  # noqa: BLE001 — 启用失败不阻断安装
            # 安装已完成，不因启用失败而回滚——插件保留为已安装+停用，
            # 卡片上会显示「初始化失败」徽标，完整堆栈见插件日志
            _log.warning("账户 {} 安装后自动启用 {} 失败: {}", account_id, plugin_name, e)
            return f"插件 '{plugin_name}' 已安装，但自动启用失败：{e}"
        return f"插件 '{plugin_name}' 已安装并启用"

    async def update_plugin_in_account(self, account_id: int, plugin_name: str) -> None:
        """从插件库更新账户插件副本:覆盖源码并重载实例(保留启用状态)。

        新版本配置 schema 中的新字段由 load_config_with_defaults 自动补默认值,
        既有字段的用户配置值保留;插件数据目录不变。

        :raises CorePluginNotFoundException: 插件库或账户中不存在
        """
        from core.exceptions import CorePluginNotFoundException
        src = os.path.join("plugins", plugin_name)
        if not os.path.isdir(src):
            raise CorePluginNotFoundException(plugin_name)
        server = self.get_server(account_id)
        dest = os.path.join(self._server_dirs(account_id), "installed_plugins", plugin_name)
        if not os.path.isdir(dest):
            raise CorePluginNotFoundException(f"账户尚未安装插件 '{plugin_name}'")
        pm = server._plugin_manager
        meta = pm.get_plugin(plugin_name)
        was_enabled = bool(meta is not None and meta.enabled)

        # 1. 停用旧实例(终止钩子/取消注册/移除旧 UI 路由)
        if was_enabled:
            try:
                await pm.disable_plugin(plugin_name)
            except Exception as e:
                _log.warning("账户 {} 更新插件 {} 时停用旧实例失败: {}", account_id, plugin_name, e)
        # 2. 清除旧模块缓存并移除元数据条目(load_all 增量合并不会覆盖已存在条目)
        if meta is not None:
            pm._purge_modules(meta)
            pm._plugins.pop(plugin_name, None)
        # 3. 覆盖源码副本
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)
        # 4. 重新扫描元数据 → 轻量实例注册 UI 路由(禁用状态插件主页亦可用)
        await server.refresh_plugins()
        new_meta = pm.get_plugin(plugin_name)
        if new_meta is not None:
            pm._ensure_plugin_loaded(new_meta)
        # 5. 原启用状态则重新启用(完整激活,新字段自动补默认值)
        if was_enabled:
            await server.enable_plugin(plugin_name)
        server._save_state()
        _log.info("账户 {} 已更新插件 {} 到库版本", account_id, plugin_name)

    # ------------------------------------------------------------------ #
    # 插件：批量推送到账户
    # ------------------------------------------------------------------ #

    @staticmethod
    def _version_tuple(version: str) -> tuple[int, ...]:
        """把 ``"1.2.3"`` 转成可比较的元组；非法版本按 ``(0,)`` 处理。"""
        try:
            return tuple(int(x) for x in str(version).split("."))
        except (TypeError, ValueError):
            return (0,)

    def _library_targets(self, plugin_name: str | None) -> list[tuple[str, str]]:
        """取 ``[(插件名, 库版本), ...]``；指定单个插件时校验其存在于库中。"""
        from core.exceptions import CorePluginNotFoundException

        lib_pm = self.get_library_pm()
        if plugin_name is not None:
            lib_meta = lib_pm.get_plugin(plugin_name)
            if lib_meta is None:
                raise CorePluginNotFoundException(plugin_name)
            return [(plugin_name, lib_meta.version)]
        return [(m.name, m.version) for m in lib_pm.list_plugins()]

    async def _update_outdated_in_account(
        self, account_id: int, targets: list[tuple[str, str]], dry_run: bool = False
    ) -> dict[str, Any]:
        """对单个账户做版本守卫更新，返回**插件名**清单。

        只处理已安装的，并跳过「副本版本不低于库版本」的——更新会 stop/start
        插件实例（断掉插件消息与内部状态），无谓的重载应当避免。

        :param dry_run: 只计算不执行（供二次确认前预览明细），``updated`` 表示
                        「将会更新」而非「已更新」
        :return: ``{"updated", "skipped", "failed", "transitions"}``；
                 ``transitions`` 为 ``{插件名: 原版本}``，供展示版本跨度
        """
        out: dict[str, Any] = {
            "updated": [], "skipped": [], "failed": [], "transitions": {},
        }
        server = self._servers.get(account_id)
        if server is None:
            return out
        pm = server._plugin_manager
        for name, lib_version in targets:
            meta = pm.get_plugin(name)
            if meta is None:
                continue  # 该账户未安装此插件
            if self._version_tuple(meta.version) >= self._version_tuple(lib_version):
                out["skipped"].append(name)
                continue
            out["transitions"][name] = meta.version  # 更新会换掉 meta，先记下原版本
            if dry_run:
                out["updated"].append(name)
                continue
            try:
                await self.update_plugin_in_account(account_id, name)
                out["updated"].append(name)
            except Exception as e:
                _log.warning("账户 {} 更新插件 {} 失败: {}", account_id, name, e)
                out["failed"].append(name)
                out["transitions"].pop(name, None)
        return out

    async def update_plugins_in_account(
        self, account_id: int, dry_run: bool = False
    ) -> dict[str, Any]:
        """把账户中「副本版本低于库版本」的插件一键更新到库版本。

        与 :meth:`push_plugin_to_accounts` 同一套版本守卫，只是范围限定在单个账户——
        已是最新的、以及未安装的都不会被触碰。

        :param account_id: 账户 ID
        :param dry_run: 只计算不执行（供二次确认前预览明细）
        :return: ``{"updated", "skipped", "failed", "groups", "dry_run"}``；
                 ``groups`` 按插件给出**版本跨度**（如 ``v1.0.4 → v1.0.5``），
                 与面板推送的分组结构一致，前端可用同一套渲染
        :raises CoreAccountNotFoundException: 账户不存在
        """
        self.get_record(account_id)
        targets = self._library_targets(None)
        lib_versions = dict(targets)
        result = await self._update_outdated_in_account(
            account_id, targets, dry_run=dry_run
        )
        result["groups"] = [
            {
                "label": name,
                "items": [
                    f"v{result['transitions'].get(name, '?')}"
                    f" → v{lib_versions.get(name, '?')}"
                ],
            }
            for name in result["updated"]
        ]
        result["dry_run"] = dry_run
        return result

    async def push_plugin_to_accounts(
        self, plugin_name: str | None = None, dry_run: bool = False
    ) -> dict[str, Any]:
        """把插件库版本推送到各账户副本（面板级）。

        只处理**已安装该插件**的账户，并跳过「副本版本不低于库版本」的——
        因此手动改过副本的账户、以及已是最新的账户都不会被触碰。

        :param plugin_name: 插件名；``None`` 表示库中全部插件
        :param dry_run: 只计算不执行（供二次确认前预览明细）
        :return: ``{"updated": [...], "skipped": [...], "failed": [...]}``，
                 条目形如 ``插件名@账户名``
        :raises CorePluginNotFoundException: 指定的插件不在库中
        """
        targets = self._library_targets(plugin_name)

        updated: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []
        for rec in self.list_records():
            res = await self._update_outdated_in_account(rec.id, targets, dry_run=dry_run)
            updated += [f"{n}@{rec.name}" for n in res["updated"]]
            skipped += [f"{n}@{rec.name}" for n in res["skipped"]]
            failed += [f"{n}@{rec.name}" for n in res["failed"]]

        return {
            "updated": updated, "skipped": skipped, "failed": failed,
            "dry_run": dry_run,
        }

    # ------------------------------------------------------------------ #
    # 默认插件
    # ------------------------------------------------------------------ #

    def list_default_plugins(self) -> list[str]:
        """当前默认插件清单（新建账户会自动安装并启用）。"""
        return list(self._default_plugins)

    def set_plugin_default(self, plugin_name: str, is_default: bool) -> list[str]:
        """把插件加入 / 移出默认清单，返回更新后的清单。

        只影响**此后创建**的账户；存量账户需显式调用
        :meth:`apply_default_plugins` 补齐。

        :param plugin_name: 插件名
        :param is_default: ``True`` 加入，``False`` 移出
        :return: 更新后的默认插件清单
        """
        name = str(plugin_name)
        if is_default:
            if name not in self._default_plugins:
                self._default_plugins.append(name)
        elif name in self._default_plugins:
            self._default_plugins.remove(name)
        self._save_panel()
        _log.info("默认插件清单已更新: {}", self._default_plugins)
        return list(self._default_plugins)

    async def _install_default_plugins(
        self, account_id: int, dry_run: bool = False
    ) -> list[str]:
        """为账户安装并启用全部默认插件。

        已装且已启用的默认插件直接跳过（无需处理）。**失败只告警不抛出**——
        默认插件装不上（如库中已删除、依赖安装失败）不应让账户创建整体失败。
        返回实际生效（``dry_run`` 时为「将生效」）的插件名。
        """
        server = self._servers.get(account_id)
        if server is None or not self._default_plugins:
            return []
        pm = server._plugin_manager

        # 先算出待处理集：已装且已启用的无需动
        pending = [
            name for name in list(self._default_plugins)
            if not (lambda m: m is not None and m.enabled)(pm.get_plugin(name))
        ]
        if dry_run or not pending:
            return pending

        applied: list[str] = []
        for name in pending:
            try:
                if pm.get_plugin(name) is None:
                    await self.install_plugin_to_account(account_id, name)
                await server.enable_plugin(name)
                applied.append(name)
            except Exception as e:
                _log.warning("账户 {} 应用默认插件 {} 失败: {}", account_id, name, e)
        return applied

    async def apply_default_plugins(self, dry_run: bool = False) -> dict[str, Any]:
        """把默认插件补齐到全部现有账户（未安装的装上并启用、已装未启用的启用）。

        :param dry_run: 只计算不执行（供二次确认前预览明细），``applied`` 表示
                        「将会补齐」而非「已补齐」
        :return: ``{"applied": {账户名: [插件名]}, "failed": [...], "dry_run": bool}``
        """
        applied: dict[str, list[str]] = {}
        failed: list[str] = []
        for rec in self.list_records():
            if self._servers.get(rec.id) is None:
                continue
            names = await self._install_default_plugins(rec.id, dry_run=dry_run)
            if names:
                applied[rec.name] = names
        # 清单里存在但库中已删除的插件——补不上，明确报出来
        for name in self._default_plugins:
            if self.get_library_pm().get_plugin(name) is None:
                failed.append(name)
        _log.info(
            "默认插件{}: {} 个账户；清单中不存在于库的: {}",
            "预览" if dry_run else "已应用", len(applied), failed,
        )
        return {"applied": applied, "failed": failed, "dry_run": dry_run}

    async def uninstall_plugin_from_account(
        self, account_id: int, plugin_name: str,
        delete_config: bool = False, delete_data: bool = False,
        delete_persistent: bool = False,
    ) -> None:
        """账户卸载插件:停止实例、删除源码副本,可选清除配置/数据。

        数据按「谁创建的」分成两类，分别对应插件数据目录 ``plugins/{name}/`` 下的文件：

        - ``delete_data``：插件经 ``self.data`` 创建/读取的 **JSON** 数据
        - ``delete_persistent``：目录中的**其他**文件（插件自带或自行创建的非 JSON 文件）

        两者独立，都不选时数据目录原样保留（重新安装即可续用）。
        """
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
        # 配置与权限是**文件**（{name}_config.json / {name}_permissions.json），
        # 不是以插件名命名的目录——必须走各自管理器的删除方法，否则删不掉
        if delete_config:
            pm._config_mgr.delete_config_file(plugin_name)
            pm._permission_mgr.delete_permissions(plugin_name)
        if delete_data or delete_persistent:
            self._prune_plugin_data_dir(
                os.path.join(base, "plugins", plugin_name),
                delete_json=delete_data,
                delete_other=delete_persistent,
            )
        # load_all 只做增量合并,不会移除目录已消失的插件 → 显式清除条目
        pm._plugins.pop(plugin_name, None)
        await server.refresh_plugins()
        server._save_state()
        _log.info("账户 {} 已卸载插件 {}", account_id, plugin_name)

    @staticmethod
    def _prune_plugin_data_dir(
        data_dir: str, *, delete_json: bool, delete_other: bool
    ) -> None:
        """按类别清理插件数据目录里的文件，随后回收变空的目录。

        **按文件扩展名区分**：``*.json`` 视为插件经 ``self.data`` 创建的数据，
        其余文件视为插件自带或自行创建的持久化文件。两类可独立选择。

        :param data_dir: 插件数据目录（``data/accounts/{id}/plugins/{name}/``）
        :param delete_json: 删除 ``*.json``
        :param delete_other: 删除非 ``*.json`` 的文件
        """
        if not os.path.isdir(data_dir):
            return
        # topdown=False → 先处理子项，空目录才能自底向上回收
        for root, _dirs, files in os.walk(data_dir, topdown=False):
            for fname in files:
                is_json = fname.lower().endswith(".json")
                if (delete_json and is_json) or (delete_other and not is_json):
                    try:
                        os.remove(os.path.join(root, fname))
                    except OSError as e:
                        _log.warning("删除插件数据文件失败 {}: {}", fname, e)
            if root != data_dir and not os.listdir(root):
                shutil.rmtree(root, ignore_errors=True)
        if not os.listdir(data_dir):
            shutil.rmtree(data_dir, ignore_errors=True)

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
        self, plugin_name: str, delete_config: bool = False, delete_data: bool = False,
        disable_in_accounts: bool = False,
    ) -> None:
        """卸载库插件(彻底删除库源文件)。

        账户私有副本独立运行不受影响;``disable_in_accounts=True`` 时
        额外停用各账户中已启用的该插件实例(副本保留,可重新启用)。
        """
        if disable_in_accounts:
            for rec in self.list_records():
                server = self._servers.get(rec.id)
                if server is None:
                    continue
                pm = server._plugin_manager
                meta = pm.get_plugin(plugin_name)
                if meta is not None and meta.enabled:
                    try:
                        await pm.disable_plugin(plugin_name)
                        server._save_state()
                        _log.info("账户 {} 已停用插件 {}", rec.id, plugin_name)
                    except Exception as e:
                        _log.warning("账户 {} 停用插件 {} 失败: {}", rec.id, plugin_name, e)
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
