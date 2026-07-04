"""MisMiss 命令行前端。

基于 ``Command`` 类的命令注册与路由系统，替代手工 ``if`` 检测
和 ``COMMAND_MAP`` 字典。

用法::

    cd MisMiss/
    python -m src.cli           # 推荐
    python src/cli.py           # 也可
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 确保项目根目录和 src/ 在路径中，并切换工作目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from core.logging import get_logger  # noqa: E402
from core import MissevanServer  # noqa: E402
from core.exceptions import (   # noqa: E402
    CoreCookieException, CorePermissionException, CoreDisabledException,
    CoreApiException, CorePluginNotFoundException,
    CorePluginPermissionException, CoreBotException,
)
from interfaces.bot import BotPermission  # noqa: E402
from interfaces.plugin.plugin_metadata import PluginMetadata  # noqa: E402

_log = get_logger(__name__)


# ================================================================== #
# Command 类
# ================================================================== #

Handler = Callable[..., Any]


@dataclass
class Command:
    """一条 CLI 命令。

    封装命令名、处理函数、帮助信息和参数约束。
    支持前缀匹配和自动参数解析。
    """

    prefix: str
    """命令前缀，如 ``"bot create"``。"""

    handler: Handler
    """处理函数。同步或异步均可，由调用方 ``await`` 判断。"""

    usage: str = ""
    """用法示例，如 ``"bot create <cookie> [perms...]"``。"""

    description: str = ""
    """功能简述。"""

    min_args: int = 0
    """最少必需参数数，不足时自动提示用法。"""

    # 自动生成的帮助标签
    group: str = field(default="", init=False)
    """命令分组标签，由前缀第一段自动生成（如 "bot" / "plugin"）。"""

    name: str = field(default="", init=False)
    """命令名，由前缀去首段自动生成。"""

    def __post_init__(self) -> None:
        parts = self.prefix.split()
        self.group = parts[0] if parts else ""
        self.name = " ".join(parts[1:]) if len(parts) > 1 else ""

    # ------------------------------------------------------------------ #
    # 匹配与解析
    # ------------------------------------------------------------------ #

    def matches(self, line: str) -> bool:
        """检查输入行是否匹配此命令。"""
        return line == self.prefix or line.startswith(self.prefix + " ")

    def parse_args(self, line: str) -> list[str]:
        """从输入行中提取参数列表。"""
        if line == self.prefix:
            return []
        return line[len(self.prefix) + 1:].split()

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #

    async def execute(self, args: list[str]) -> None:
        """执行命令（自动判断同步/异步）。"""
        result = self.handler(args)
        if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
            await result


# ================================================================== #
# CommandRegistry
# ================================================================== #


class CommandRegistry:
    """命令注册表。

    管理所有 ``Command`` 实例，提供注册、查找、帮助生成和路由执行。
    """

    def __init__(self) -> None:
        self._commands: list[Command] = []

    # ------------------------------------------------------------------ #
    # 注册
    # ------------------------------------------------------------------ #

    def register(self, cmd: Command) -> None:
        """注册一条命令。

        重名检测：同一 prefix 只能注册一次。
        """
        for existing in self._commands:
            if existing.prefix == cmd.prefix:
                raise ValueError(
                    f"命令 '{cmd.prefix}' 已注册"
                )
        self._commands.append(cmd)

    def register_many(self, *cmds: Command) -> None:
        """批量注册。"""
        for cmd in cmds:
            self.register(cmd)

    # ------------------------------------------------------------------ #
    # 查找
    # ------------------------------------------------------------------ #

    def find(self, line: str) -> Command | None:
        """按最长前缀匹配查找命令。

        例如 ``"plugin perm example SEND_GIFT true"`` 匹配
        ``Command("plugin perm")`` 而非 ``Command("plugin")``。
        """
        best: Command | None = None
        for cmd in self._commands:
            if cmd.matches(line):
                if best is None or len(cmd.prefix) > len(best.prefix):
                    best = cmd
        return best

    def match(self, line: str) -> tuple[Command, list[str]] | None:
        """查找命令并解析参数，一步完成。"""
        cmd = self.find(line)
        if cmd is None:
            return None
        return cmd, cmd.parse_args(line)

    # ------------------------------------------------------------------ #
    # 帮助
    # ------------------------------------------------------------------ #

    def help(self) -> str:
        """按分组生成帮助文本。"""
        groups: dict[str, list[Command]] = {}
        for cmd in self._commands:
            groups.setdefault(cmd.group, []).append(cmd)

        lines = ["+==================================================================+",
                 "|                    MisMiss CLI                                    |"]
        for group_name in ("bot", "live", "plugin", "server", "help"):
            if group_name not in groups:
                continue
            lines.append("+==================================================================+")
            title = {
                "bot": "Bot", "live": "Livestream",
                "plugin": "Plugin", "server": "Server",
                "help": "General",
            }.get(group_name, group_name.capitalize())
            lines.append(f"| {title:<64} |")
            for cmd in groups[group_name]:
                usage = cmd.usage or cmd.prefix
                desc = cmd.description
                line = f"|   {usage:<47} {desc:<16} |"
                lines.append(line[:68] + " |")
        lines.append("+==================================================================+")
        return "\n".join(lines)


# ================================================================== #
# 工具函数
# ================================================================== #


def _load_cookie() -> str:
    """从项目根目录的 test/cookie.txt 加载 Cookie。"""
    cookie_path = _PROJECT_ROOT / "test" / "cookie.txt"
    if not cookie_path.exists():
        return ""
    with open(cookie_path, "r", encoding="utf-8") as f:
        return "".join(line.strip() for line in f)


def _fmt_perms(perms: BotPermission) -> str:
    names = [p.name for p in BotPermission if perms & p]
    return ", ".join(names) if names else "(无)"


def _parse_permission_flag(value: str) -> BotPermission:
    flag = BotPermission(0)
    for name in value.strip().split():
        name = name.strip().upper()
        if not name:
            continue
        try:
            flag |= BotPermission[name]
        except KeyError:
            _log.info(f"  [警告] 忽略无效的权限名: {name}")
    return flag if flag.value else BotPermission.SEND_LIVESTREAM_MESSAGE


def _bool(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes", "on", "t", "y")


# ================================================================== #
# 全局状态
# ================================================================== #

server: MissevanServer
registry: CommandRegistry


# ================================================================== #
# 命令处理器（无参数校验的捷径函数）
# ================================================================== #

def _need_args(args: list[str], usage: str) -> bool:
    if not args:
        _log.info(f"用法: {usage}")
        return False
    return True


def _need_plugin(name: str) -> PluginMetadata | None:
    pm = server._plugin_manager  # noqa
    meta = pm.get_plugin(name)
    if meta is None:
        _log.info(f"[错误] 插件 '{name}' 不存在")
    return meta


def _parse_live_id(s: str) -> int | None:
    try:
        return int(s)
    except ValueError:
        _log.info(f"[错误] 无效的直播间 ID: {s}")
        return None


# ---------------------------------------------------------------- #
# Bot 处理器
# ---------------------------------------------------------------- #


async def _bot_create(args: list[str]) -> None:
    if not _need_args(args, "bot create <cookie> [perms...]"):
        return
    cookie = args[0]
    if cookie in ("-", "file", "cookie.txt"):
        cookie = _load_cookie()
        if not cookie:
            _log.info("[错误] cookie.txt 不存在或为空")
            return
    perms = (_parse_permission_flag(" ".join(args[1:]))
             if len(args) > 1 else BotPermission.SEND_LIVESTREAM_MESSAGE)

    _log.info(f"正在创建 Bot ...\n  Cookie 长度: {len(cookie)}\n  权限: {_fmt_perms(perms)}")
    try:
        bot = await server.create_bot(cookie, permissions=perms)
        _log.info(f"[成功] Bot 创建完成: {bot.name} (ID={bot.id})")
    except CoreCookieException as e:
        _log.info(f"[失败] Cookie 无效: {e}")


def _bot_info(_args: list[str]) -> None:
    bot = server.bot
    _log.info(f"  名称:       {bot.name}")
    _log.info(f"  ID:         {bot.id}")
    _log.info(f"  简介:       {bot.introduction}")
    _log.info(f"  头像URL:    {bot.icon_url}")
    _log.info(f"  启用:       {bot.enabled}")
    _log.info(f"  权限:       {_fmt_perms(bot.permissions)}")
    _log.info(f"  Bot 可用:   {server.bot_available}")


async def _bot_refresh(_args: list[str]) -> None:
    try:
        await server.bot.refresh()
        _log.info(f"[成功] 刷新完成: {server.bot.name}")
    except CoreCookieException:
        _log.info("[失败] Cookie 已过期，Bot 已自动停用")
    except CoreApiException as e:
        _log.info(f"[失败] API 错误: {e}")


def _bot_cookie(_args: list[str]) -> None:
    try:
        c = server.bot.get_cookie()
        _log.info(f"  Cookie: {c[:30]}...（截断）\n  全长: {len(c)} 字符")
    except CorePermissionException as e:
        _log.info(f"[权限不足] {e}\n  提示: 创建 Bot 时需授予 EXPOSE_COOKIE 权限")
    except CoreDisabledException as e:
        _log.info(f"[已停用] {e}")


async def _bot_verify(_args: list[str]) -> None:
    ok = await server.verify_bot()
    _log.info("[有效] Cookie 有效" if ok else "[无效] Cookie 已过期或网络错误")


def _bot_disable(_args: list[str]) -> None:
    server.bot.enabled = False
    _log.info("Bot 已停用")


async def _bot_enable(_args: list[str]) -> None:
    await server.enable_bot()
    _log.info("Bot 已启用")


# ---------------------------------------------------------------- #
# Livestream 处理器
# ---------------------------------------------------------------- #


async def _live_add(args: list[str]) -> None:
    if not _need_args(args, "live add <live_id>"):
        return
    lid = _parse_live_id(args[0])
    if lid is None:
        return
    try:
        live = await server.add_livestream(lid)
        _log.info("[成功] 直播间已添加:")
        _log.info(f"  ID={live.live_id}  名称={live.room_name}")
        _log.info(f"  简介={live.room_description}  热度={live.score}")
        _log.info(f"  主播={live.creator_name} (ID={live.creator_id})")
    except CoreBotException as e:
        _log.info(f"[失败] {e}")
    except CoreApiException as e:
        _log.info(f"[失败] API 错误: {e}")


def _live_list(_args: list[str]) -> None:
    lives = server.livestreams
    if not lives:
        _log.info("  (无直播间)")
        return
    for lid, live in lives.items():
        _log.info("  [{}] {}  conn={}  enabled={}",
                  lid, live.room_name,
                  "[+]" if live.is_connected else "[-]",
                  "[+]" if live.enabled else "[-]")


def _live_info(args: list[str]) -> None:
    if not _need_args(args, "live info <id>"):
        return
    lid = _parse_live_id(args[0])
    if lid is None or lid not in server.livestreams:
        if lid is not None:
            _log.info(f"[错误] 直播间 {lid} 不存在")
        return
    live = server.livestreams[lid]
    _log.info(f"  ID={live.live_id}  名称={live.room_name}")
    _log.info(f"  热度={live.score}  主播={live.creator_name}")
    _log.info(f"  已连接={live.is_connected}  已启用={live.enabled}")
    if live.medal:
        _log.info(f"  粉丝勋章={live.medal.name} (Lv.{live.medal.level})")


async def _live_enable(args: list[str]) -> None:
    if not _need_args(args, "live enable <id>"):
        return
    try:
        await server.enable_livestream(int(args[0]))
        _log.info(f"[成功] 直播间 {args[0]} 已启用")
    except (KeyError, ValueError):
        _log.info(f"[错误] 直播间 {args[0]} 不存在")


def _live_disable(args: list[str]) -> None:
    if not _need_args(args, "live disable <id>"):
        return
    try:
        server.disable_livestream(int(args[0]))
        _log.info(f"[成功] 直播间 {args[0]} 已停用")
    except (KeyError, ValueError):
        _log.info(f"[错误] 直播间 {args[0]} 不存在")


async def _live_join(args: list[str]) -> None:
    if not _need_args(args, "live join <id>"):
        return
    lid = _parse_live_id(args[0])
    if lid is None or lid not in server.livestreams:
        if lid is not None:
            _log.info(f"[错误] 直播间 {lid} 不存在，请先 live add")
        return
    try:
        await server.livestreams[lid].join()
        _log.info(f"[成功] 已进入直播间 {lid}: {server.livestreams[lid].room_name}")
    except CoreDisabledException as e:
        _log.info(f"[已停用] {e}")
    except CoreApiException as e:
        _log.info(f"[失败] {e}")


async def _live_quit(args: list[str]) -> None:
    if not _need_args(args, "live quit <id>"):
        return
    lid = _parse_live_id(args[0])
    if lid is None or lid not in server.livestreams:
        if lid is not None:
            _log.info(f"[错误] 直播间 {lid} 不存在")
        return
    try:
        await server.livestreams[lid].quit()
        _log.info(f"[成功] 已退出直播间 {lid}")
    except CoreDisabledException as e:
        _log.info(f"[已停用] {e}")


async def _live_remove(args: list[str]) -> None:
    if not _need_args(args, "live remove <id>"):
        return
    lid = _parse_live_id(args[0])
    if lid is None:
        return
    try:
        await server.remove_livestream(lid)
        _log.info(f"[成功] 直播间 {lid} 已移除")
    except KeyError:
        _log.info(f"[错误] 直播间 {lid} 不存在")


async def _live_msg(args: list[str]) -> None:
    priority = 0
    if args and args[0] == "-p":
        if len(args) < 4:
            _log.info("用法: live msg -p <priority> <id> <text>")
            return
        try:
            priority = int(args[1])
        except ValueError:
            _log.info(f"[错误] 无效的优先级: {args[1]}")
            return
        args = args[2:]
    if len(args) < 2:
        _log.info("用法: live msg [-p <priority>] <id> <text>")
        return
    lid = _parse_live_id(args[0])
    if lid is None or lid not in server.livestreams:
        if lid is not None:
            _log.info(f"[错误] 直播间 {lid} 不存在")
        return
    text = " ".join(args[1:])
    try:
        await server.livestreams[lid].send_message(text, priority=priority)
        _log.info(f"[已发送] → {lid}: {text}" + (f" (优先级={priority})" if priority else ""))
    except CoreDisabledException as e:
        _log.info(f"[已停用] {e}")
    except CorePermissionException as e:
        _log.info(f"[权限不足] {e}")
    except CoreApiException as e:
        _log.info(f"[失败] {e}")


# ---------------------------------------------------------------- #
# Plugin 处理器
# ---------------------------------------------------------------- #


def _plugin_list(_args: list[str]) -> None:
    plugins = server.plugins
    if not plugins:
        _log.info("  (无插件)")
        return
    for p in plugins:
        s = "[+] enabled" if p.enabled else "[-] disabled"
        _log.info(f"  [{p.name}] v{p.version}  {s}")
        _log.info(f"      plugin_id={p.plugin_id}  author={p.author}")
        if p.short_desc:
            _log.info(f"      desc={p.short_desc}")


def _plugin_info(args: list[str]) -> None:
    if not _need_args(args, "plugin info <name>"):
        return
    meta = _need_plugin(args[0])
    if meta is None:
        return
    _log.info(f"  名称={meta.name}  显示名={meta.display_name}")
    _log.info(f"  版本={meta.version}  作者={meta.author}")
    _log.info(f"  plugin_id={meta.plugin_id}  启用={meta.enabled}")
    _log.info(f"  描述={meta.desc}")
    if meta.permissions:
        enabled = [k for k, v in meta.permissions.items() if v]
        _log.info(f"  权限={enabled if enabled else '(仅默认)'}")


def _plugin_handlers(args: list[str]) -> None:
    if not _need_args(args, "plugin handlers <name>"):
        return
    try:
        handlers = server.list_plugin_handlers(args[0])
        if not handlers:
            _log.info("  (无事件处理器)")
            return
        _log.info(f"  {args[0]}: {len(handlers)} 个处理器")
        for method_name, event_type in handlers.items():
            _log.info(f"      {method_name} → {event_type.__name__}")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")


async def _plugin_enable(args: list[str]) -> None:
    if not _need_args(args, "plugin enable <name>"):
        return
    try:
        await server.enable_plugin(args[0])
        _log.info(f"[成功] 插件 '{args[0]}' 已启用")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")


def _plugin_disable(args: list[str]) -> None:
    if not _need_args(args, "plugin disable <name>"):
        return
    try:
        asyncio.get_running_loop().create_task(server.disable_plugin(args[0]))
        _log.info(f"[成功] 插件 '{args[0]}' 已禁用")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")


async def _plugin_reload(args: list[str]) -> None:
    if not _need_args(args, "plugin reload <name>"):
        return
    try:
        meta = await server.reload_plugin(args[0])
        _log.info(f"[成功] 插件已重载: {meta.name} v{meta.version}")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")


def _plugin_perms(args: list[str]) -> None:
    if not _need_args(args, "plugin perms <name>"):
        return
    name = args[0]
    if _need_plugin(name) is None:
        return
    try:
        info = server.get_plugin_permissions(name)
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")
        return
    _log.info(f"  {name} 权限:")
    for k, v in info["permissions"].items():
        _log.info(f"      {'[+]' if v else '[-]'} {k}")
    _log.info("  生效 Flag={}  生效={}",
              info["effective_flag"], info["effective_names"])
    if info["missing_in_bot"]:
        _log.info(f"  Bot 缺失: {info['missing_in_bot']} [WARN]")


def _plugin_perm(args: list[str]) -> None:
    if len(args) < 3:
        _log.info("用法: plugin perm <name> <key> <true/false>")
        return
    name, key, value_str = args[0], args[1].upper(), args[2]
    try:
        server.update_plugin_permission(name, key, _bool(value_str))
        _log.info(f"[成功] {name}.{key} = {_bool(value_str)}")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")
    except CorePluginPermissionException as e:
        _log.info(f"[错误] {e}")


def _plugin_readme(args: list[str]) -> None:
    if not _need_args(args, "plugin readme <name>"):
        return
    try:
        readme = server.get_plugin_readme(args[0])
        _log.info(readme if readme else "  (无 README)")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")


def _plugin_changelog(args: list[str]) -> None:
    if not _need_args(args, "plugin changelog <name>"):
        return
    try:
        cl = server.get_plugin_changelog(args[0])
        _log.info(cl if cl else "  (无 CHANGELOG)")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")


def _plugin_failed(_args: list[str]) -> None:
    failed = server.get_failed_plugins()
    if not failed:
        _log.info("  (无失败插件)")
        return
    for f in failed:
        _log.info(f"  [{f.get('dir_name')}] {f.get('error')}")


async def _plugin_refresh(_args: list[str]) -> None:
    """重新扫描插件目录，加载新插件。"""
    await server.refresh_plugins()
    _log.info("[成功] 插件目录已刷新，当前 {} 个插件", len(server.plugins))


async def _plugin_uninstall(args: list[str]) -> None:
    if not _need_args(args, "plugin uninstall <name>"):
        return
    try:
        await server.uninstall_plugin(args[0], delete_config=True, delete_data=False)
        _log.info(f"[成功] 插件 '{args[0]}' 已卸载")
    except CorePluginNotFoundException as e:
        _log.info(f"[错误] {e}")


# ---------------------------------------------------------------- #
# Server 处理器
# ---------------------------------------------------------------- #


def _server_status(_args: list[str]) -> None:
    bot = server.bot
    lives = server.livestreams
    plugins = server.plugins
    _log.info("+==========================================+")
    _log.info("|           MisMiss Server Status           |")
    _log.info(f"|  Bot:    {bot.name[:30]:<30} |")
    _log.info(f"|  ID:     {bot.id:<30} |")
    _log.info(f"|  Available: {str(server.bot_available):<26} |")
    _log.info(f"|  Perms:  {_fmt_perms(bot.permissions)[:28]:<28} |")
    _log.info(f"+  Lives:  {len(lives):<30} +")
    for lid, live in lives.items():
        _log.info(f"|    [{lid}] {live.room_name[:22]:<22} |")
    _log.info(f"+  Plugins:{len(plugins):<30} +")
    for p in plugins:
        _log.info(f"|    {'[+]' if p.enabled else '[-]'} {p.name:<26} |")
    _log.info("+==========================================+")


async def _server_shutdown(_args: list[str]) -> None:
    _log.info("正在关闭...")
    await server.shutdown()
    _log.info("服务器已关闭")


async def _server_reload(_args: list[str]) -> None:
    _log.info("正在重载...")
    await server.reload()
    _log.info("服务器已重载，{} 个插件", len(server.plugins))


# ================================================================== #
# 构建 Command 注册表
# ================================================================== #


def build_registry() -> CommandRegistry:
    """注册所有 CLI 命令。"""
    r = CommandRegistry()
    r.register_many(
        # ---- Bot ----
        Command("bot create",   _bot_create,   "bot create <cookie> [perms...]", "创建 Bot"),
        Command("bot info",     _bot_info,     "bot info",                       "Bot 信息"),
        Command("bot refresh",  _bot_refresh,  "bot refresh",                    "刷新/验证 Cookie"),
        Command("bot cookie",   _bot_cookie,   "bot cookie",                     "获取 Cookie"),
        Command("bot verify",   _bot_verify,   "bot verify",                     "验证 Cookie"),
        Command("bot disable",  _bot_disable,  "bot disable",                    "停用 Bot"),
        Command("bot enable",   _bot_enable,   "bot enable",                     "启用 Bot"),

        # ---- Livestream ----
        Command("live add",     _live_add,     "live add <id>",                  "添加直播间"),
        Command("live list",    _live_list,    "live list",                      "列出直播间"),
        Command("live info",    _live_info,    "live info <id>",                 "直播间详情"),
        Command("live enable",  _live_enable,  "live enable <id>",               "启用直播间"),
        Command("live disable", _live_disable, "live disable <id>",              "停用直播间"),
        
        
        Command("live remove",  _live_remove,  "live remove <id>",               "移除直播间"),
        Command("live msg",     _live_msg,     "live msg [-p <pri>] <id> <text>","发送弹幕"),

        # ---- Plugin ----
        Command("plugin list",      _plugin_list,      "plugin list",                    "列出插件"),
        Command("plugin info",      _plugin_info,      "plugin info <name>",             "插件详情"),
        Command("plugin handlers",  _plugin_handlers,  "plugin handlers <name>",         "事件处理器"),
        Command("plugin enable",    _plugin_enable,    "plugin enable <name>",           "启用插件"),
        Command("plugin disable",   _plugin_disable,   "plugin disable <name>",          "禁用插件"),
        Command("plugin reload",    _plugin_reload,    "plugin reload <name>",           "重载插件"),
        Command("plugin perms",     _plugin_perms,     "plugin perms <name>",            "查看权限"),
        Command("plugin perm",      _plugin_perm,      "plugin perm <name> <key> <T/F>", "修改权限"),
        Command("plugin readme",    _plugin_readme,    "plugin readme <name>",           "README"),
        Command("plugin changelog", _plugin_changelog, "plugin changelog <name>",        "CHANGELOG"),
        Command("plugin failed",    _plugin_failed,    "plugin failed",                  "失败插件"),
        Command("plugin refresh",   _plugin_refresh,   "plugin refresh",                 "扫描新插件"),
        Command("plugin uninstall", _plugin_uninstall, "plugin uninstall <name>",        "卸载插件"),

        # ---- Server ----
        Command("server status",   _server_status,   "server status",    "状态总览"),
        Command("server shutdown", _server_shutdown, "server shutdown",  "关闭服务器"),
        Command("server reload",   _server_reload,   "server reload",    "重载服务器"),

        # ---- General ----
        Command("help", lambda _: print(registry.help()), "help", "显示帮助"),
    )
    return r


# ================================================================== #
# Main
# ================================================================== #


async def main() -> None:
    global server, registry

    _log.info("+==================================================+")
    _log.info("|          MisMiss CLI                              |")
    _log.info("+==================================================+")
    registry = build_registry()

    server = MissevanServer()
    await server.start()

    cookie = _load_cookie()
    _log.info(f"Cookie: {'已有 (' + str(len(cookie)) + ' 字符)' if cookie else '未找到'}")
    _log.info(f"已加载插件: {len(server.plugins)} 个")
    for p in server.plugins:
        _log.info(f"  - {p.name} v{p.version} ({'enabled' if p.enabled else 'disabled'})")
    _log.info("\n输入 help 查看命令，exit 退出\n")

    loop = asyncio.get_running_loop()
    while True:
        try:
            line = (await loop.run_in_executor(None, input, "miss> ")).strip()
        except (EOFError, KeyboardInterrupt):
            _log.info("")
            break

        if not line:
            continue
        if line in ("exit", "quit", "q"):
            break

        matched = registry.match(line)
        if matched is None:
            _log.info(f"未知命令: {line}  (输入 help 查看可用命令)")
            continue

        cmd, args = matched
        try:
            await cmd.execute(args)
            await asyncio.sleep(0)  # 让出控制权给后台任务
        except Exception as e:
            _log.info(f"[异常] {type(e).__name__}: {e}")

    _log.info("正在关闭...")
    try:
        await server.shutdown()
    except Exception:
        pass
    _log.info("再见!")


if __name__ == "__main__":
    asyncio.run(main())
