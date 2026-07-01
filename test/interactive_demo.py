"""MisMiss 交互式功能演示。

启动后进入 REPL 交互模式，支持所有核心 API 的操作演示：
- Bot 管理（创建/信息/刷新/Cookie/验证）
- 直播间管理（添加/列表/启停/发消息/加入退出）
- 插件管理（列表/详情/启停/重载/权限读写/文档）
- Server 状态总览

用法::

    python test/interactive_demo.py

Cookie 从 ``test/cookie.txt`` 自动读取（单行纯文本）。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core import MissevanServer
from core.exceptions import (
    CoreCookieException,
    CorePermissionException,
    CoreDisabledException,
    CoreApiException,
    CorePluginNotFoundException,
    CorePluginPermissionException,
    CoreBotException,
)
from interfaces.bot import BotPermission
from interfaces.plugin.plugin_metadata import PluginMetadata

# ================================================================== #
# 工具
# ================================================================== #


def _load_cookie() -> str:
    """从 test/cookie.txt 读取 Cookie（单行纯文本）。"""
    cookie_path = str(Path(__file__).resolve().parent / "cookie.txt")
    if not os.path.exists(cookie_path):
        return ""
    with open(cookie_path, "r", encoding="utf-8") as f:
        return "".join(line.strip() for line in f)


def _fmt_perms(perms: BotPermission) -> str:
    """格式化权限 Flag 为可读字符串。"""
    names = [p.name for p in BotPermission if perms & p]
    return ", ".join(names) if names else "(无)"


def _parse_permission_flag(value: str) -> BotPermission:
    """将用户输入的权限名列表解析为 Flag。"""
    flag = BotPermission(0)
    for name in value.strip().split():
        name = name.strip().upper()
        if not name:
            continue
        try:
            flag |= BotPermission[name]
        except KeyError:
            print(f"  [警告] 忽略无效的权限名: {name}")
    return flag if flag.value else BotPermission.SEND_LIVESTREAM_MESSAGE


def _bool(s: str) -> bool:
    """将 'true'/'1'/'yes'/'on' 转为 True，其余 False。"""
    return s.strip().lower() in ("true", "1", "yes", "on", "t", "y")


# ================================================================== #
# 全局状态
# ================================================================== #

server: MissevanServer
"""全局 Server 实例。"""


# ================================================================== #
# 命令处理
# ================================================================== #


def cmd_help(_args: list[str] | None = None) -> None:
    """打印帮助信息。"""
    print(
        """
+==================================================================+
|                    MisMiss Interactive Demo                       |
+==================================================================+
| Bot                                                               |
|   bot create [cookie]           创建 Bot（省略 cookie 则从文件读） |
|   bot create [cookie] [perms]   创建 Bot 并指定权限（空格分隔）    |
|   bot info                      查看 Bot 信息                     |
|   bot refresh                   刷新 Bot 信息 / 验证 Cookie        |
|   bot cookie                    获取 Cookie（需 EXPOSE_COOKIE）    |
|   bot verify                    主动验证 Cookie 有效性             |
|   bot disable / bot enable      停用 / 启用 Bot                    |
+==================================================================+
| Livestream                                                        |
|   live add <id>                 添加直播间                        |
|   live list                     列出所有直播间                    |
|   live info <id>                查看直播间详情                    |
|   live enable <id>              启用直播间                        |
|   live disable <id>             停用直播间                        |
|   live join <id>                进入直播间（连 WebSocket）         |
|   live quit <id>                退出直播间                        |
|   live msg <id> <text>          发送弹幕                          |
|   live msg -p <n> <id> <text>   发送弹幕（指定优先级）             |
+==================================================================+
| Plugin                                                            |
|   plugin list                   列出所有插件                      |
|   plugin info <name>            插件详情                          |
|   plugin handlers <name>        查看事件处理器                    |
|   plugin enable <name>          启用插件                          |
|   plugin disable <name>         禁用插件                          |
|   plugin reload <name>          重载插件                          |
|   plugin perms <name>           查看插件权限                      |
|   plugin perm <name> <key> <on/off>  修改单个权限                 |
|   plugin readme <name>          查看 README                       |
|   plugin changelog <name>       查看 CHANGELOG                    |
|   plugin failed                 查看加载失败的插件                |
|   plugin uninstall <name>       卸载插件                          |
+==================================================================+
| Server                                                            |
|   server status                 服务器状态总览                    |
|   server shutdown               关闭服务器                        |
+==================================================================+
|   help                          显示此帮助                        |
|   exit / quit                   退出                              |
+==================================================================+
"""
    )


# ---------------------------------------------------------------- #
# Bot 命令
# ---------------------------------------------------------------- #


async def cmd_bot_create(args: list[str]) -> None:
    """创建 Bot。"""
    if not args:
        print("用法: bot create [cookie] [permission1 permission2 ...]")
        return

    cookie = args[0]
    if cookie in ("-", "file", "cookie.txt"):
        cookie = _load_cookie()
        if not cookie:
            print("[错误] cookie.txt 不存在或为空")
            return

    perms = BotPermission.SEND_LIVESTREAM_MESSAGE
    if len(args) > 1:
        perms = _parse_permission_flag(" ".join(args[1:]))

    print("正在创建 Bot ...")
    print(f"  Cookie 长度: {len(cookie)}")
    print(f"  权限: {_fmt_perms(perms)}")

    try:
        bot = await server.create_bot(cookie, permissions=perms)
        print(f"[成功] Bot 创建完成: {bot.name} (ID={bot.id})")
    except CoreCookieException as e:
        print(f"[失败] Cookie 无效: {e}")


def cmd_bot_info(_args: list[str] | None = None) -> None:
    """查看 Bot 信息。"""
    bot = server.bot
    print(f"  名称:       {bot.name}")
    print(f"  ID:         {bot.id}")
    print(f"  简介:       {bot.introduction}")
    print(f"  头像URL:    {bot.icon_url}")
    print(f"  启用:       {bot.enabled}")
    print(f"  权限:       {_fmt_perms(bot.permissions)}")
    print(f"  Bot 可用:   {server.bot_available}")


async def cmd_bot_refresh(_args: list[str] | None = None) -> None:
    """刷新 Bot 信息。"""
    try:
        await server.bot.refresh()
        print(f"[成功] 刷新完成: {server.bot.name}")
    except CoreCookieException:
        print("[失败] Cookie 已过期，Bot 已自动停用")
    except CoreApiException as e:
        print(f"[失败] API 错误: {e}")


def cmd_bot_cookie(_args: list[str] | None = None) -> None:
    """获取 Cookie。"""
    try:
        c = server.bot.get_cookie()
        print(f"  Cookie: {c[:30]}...（截断）")
        print(f"  全长: {len(c)} 字符")
    except CorePermissionException as e:
        print(f"[权限不足] {e}")
        print("  提示: 创建 Bot 时需授予 EXPOSE_COOKIE 权限")
    except CoreDisabledException as e:
        print(f"[已停用] {e}")


async def cmd_bot_verify(_args: list[str] | None = None) -> None:
    """主动验证 Cookie。"""
    ok = await server.verify_bot()
    if ok:
        print("[有效] Cookie 有效")
    else:
        print("[无效] Cookie 已过期或网络错误")


def cmd_bot_disable(_args: list[str] | None = None) -> None:
    server.bot.enabled = False
    print("Bot 已停用")


def cmd_bot_enable(_args: list[str] | None = None) -> None:
    server.bot.enabled = True
    print("Bot 已启用")


# ---------------------------------------------------------------- #
# Livestream 命令
# ---------------------------------------------------------------- #


async def cmd_live_add(args: list[str]) -> None:
    """添加直播间。"""
    if not args:
        print("用法: live add <live_id>")
        return
    try:
        live_id = int(args[0])
    except ValueError:
        print(f"[错误] 无效的直播间 ID: {args[0]}")
        return

    try:
        live = await server.add_livestream(live_id)
        print("[成功] 直播间已添加:")
        print(f"  ID:     {live.live_id}")
        print(f"  名称:   {live.room_name}")
        print(f"  简介:   {live.room_description}")
        print(f"  热度:   {live.score}")
        print(f"  主播:   {live.creator_name} (ID={live.creator_id})")
    except CoreBotException as e:
        print(f"[失败] {e}")
    except CoreApiException as e:
        print(f"[失败] API 错误: {e}")


def cmd_live_list(_args: list[str] | None = None) -> None:
    """列出所有直播间。"""
    lives = server.livestreams
    if not lives:
        print("  (无直播间)")
        return
    for lid, live in lives.items():
        conn = "[+]" if live.is_connected else "[-]"
        enabled = "[+]" if live.enabled else "[-]"
        print(
            f"  [{lid}] {live.room_name}  "
            f"已连接={conn}  已启用={enabled}"
        )


def cmd_live_info(args: list[str]) -> None:
    """查看直播间详情。"""
    if not args:
        print("用法: live info <id>")
        return
    try:
        live_id = int(args[0])
    except ValueError:
        print(f"[错误] 无效的直播间 ID: {args[0]}")
        return

    lives = server.livestreams
    if live_id not in lives:
        print(f"[错误] 直播间 {live_id} 不存在")
        return
    live = lives[live_id]
    print(f"  ID:         {live.live_id}")
    print(f"  名称:       {live.room_name}")
    print(f"  简介:       {live.room_description}")
    print(f"  热度:       {live.score}")
    print(f"  主播:       {live.creator_name} (ID={live.creator_id})")
    print(f"  已连接:     {live.is_connected}")
    print(f"  已启用:     {live.enabled}")
    if live.medal:
        print(f"  粉丝勋章:   {live.medal.name} (Lv.{live.medal.level})")


def cmd_live_enable(args: list[str]) -> None:
    """启用直播间。"""
    if not args:
        print("用法: live enable <id>")
        return
    try:
        server.enable_livestream(int(args[0]))
        print(f"[成功] 直播间 {args[0]} 已启用")
    except KeyError:
        print(f"[错误] 直播间 {args[0]} 不存在")


def cmd_live_disable(args: list[str]) -> None:
    """停用直播间。"""
    if not args:
        print("用法: live disable <id>")
        return
    try:
        server.disable_livestream(int(args[0]))
        print(f"[成功] 直播间 {args[0]} 已停用")
    except KeyError:
        print(f"[错误] 直播间 {args[0]} 不存在")


async def cmd_live_join(args: list[str]) -> None:
    """进入直播间。"""
    if not args:
        print("用法: live join <id>")
        return
    try:
        live_id = int(args[0])
    except ValueError:
        print(f"[错误] 无效的直播间 ID: {args[0]}")
        return

    lives = server.livestreams
    if live_id not in lives:
        print(f"[错误] 直播间 {live_id} 不存在，请先 live add")
        return

    try:
        await lives[live_id].join()
        print(f"[成功] 已进入直播间 {live_id}")
        print(f"  名称: {lives[live_id].room_name}")
    except CoreDisabledException as e:
        print(f"[已停用] {e}")
    except CoreApiException as e:
        print(f"[失败] {e}")


async def cmd_live_quit(args: list[str]) -> None:
    """退出直播间。"""
    if not args:
        print("用法: live quit <id>")
        return
    try:
        live_id = int(args[0])
    except ValueError:
        print(f"[错误] 无效的直播间 ID: {args[0]}")
        return

    lives = server.livestreams
    if live_id not in lives:
        print(f"[错误] 直播间 {live_id} 不存在")
        return

    try:
        await lives[live_id].quit()
        print(f"[成功] 已退出直播间 {live_id}")
    except CoreDisabledException as e:
        print(f"[已停用] {e}")


async def cmd_live_msg(args: list[str]) -> None:
    """发送弹幕。"""
    priority = 0
    if args and args[0] == "-p":
        if len(args) < 4:
            print("用法: live msg -p <priority> <id> <text>")
            return
        try:
            priority = int(args[1])
        except ValueError:
            print(f"[错误] 无效的优先级: {args[1]}")
            return
        args = args[2:]

    if len(args) < 2:
        print("用法: live msg [-p <priority>] <id> <text>")
        return
    try:
        live_id = int(args[0])
    except ValueError:
        print(f"[错误] 无效的直播间 ID: {args[0]}")
        return
    text = " ".join(args[1:])

    lives = server.livestreams
    if live_id not in lives:
        print(f"[错误] 直播间 {live_id} 不存在")
        return

    try:
        await lives[live_id].send_message(text, priority=priority)
        print(f"[已发送] → {live_id}: {text}")
        if priority != 0:
            print(f"  优先级: {priority}")
    except CoreDisabledException as e:
        print(f"[已停用] {e}")
    except CorePermissionException as e:
        print(f"[权限不足] {e}")
    except CoreApiException as e:
        print(f"[失败] {e}")


# ---------------------------------------------------------------- #
# Plugin 命令
# ---------------------------------------------------------------- #


def cmd_plugin_list(_args: list[str] | None = None) -> None:
    """列出所有插件。"""
    plugins = server.plugins
    if not plugins:
        print("  (无插件)")
        return
    for p in plugins:
        status = "[+] enabled" if p.enabled else "[-] disabled"
        print(f"  [{p.name}] v{p.version}  {status}")
        print(f"      plugin_id: {p.plugin_id}")
        print(f"      author:    {p.author}")
        if p.short_desc:
            print(f"      desc:      {p.short_desc}")


def _require_plugin(name: str) -> PluginMetadata | None:
    """查找插件，找不到时打印错误。"""
    pm = server._plugin_manager  # noqa
    meta = pm.get_plugin(name)
    if meta is None:
        print(f"[错误] 插件 '{name}' 不存在")
        return None
    return meta


def cmd_plugin_info(args: list[str]) -> None:
    """查看插件详情。"""
    if not args:
        print("用法: plugin info <name>")
        return
    meta = _require_plugin(args[0])
    if meta is None:
        return
    print(f"  名称:         {meta.name}")
    print(f"  显示名:       {meta.display_name}")
    print(f"  版本:         {meta.version}")
    print(f"  作者:         {meta.author}")
    print(f"  plugin_id:    {meta.plugin_id}")
    print(f"  描述:         {meta.desc}")
    print(f"  仓库:         {meta.repo}")
    print(f"  目录名:       {meta.root_dir_name}")
    print(f"  启用:         {meta.enabled}")
    print(f"  模块路径:     {meta.module_path}")
    print(f"  配置 schema:  {'有' if meta.config_schema_path else '无'}")
    print(f"  数据目录:     {meta.data_dir}")
    if meta.permissions:
        perms = meta.permissions
        enabled = [k for k, v in perms.items() if v]
        print(f"  插件权限:     {enabled if enabled else '(仅默认)'}")


def cmd_plugin_handlers(args: list[str]) -> None:
    """查看事件处理器。"""
    if not args:
        print("用法: plugin handlers <name>")
        return
    try:
        handlers = server.list_plugin_handlers(args[0])
        if not handlers:
            print(f"  {args[0]}: (无事件处理器)")
            return
        print(f"  {args[0]}: {len(handlers)} 个处理器")
        for method_name, event_type in handlers.items():
            print(f"      {method_name} → {event_type.__name__}")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")


def cmd_plugin_enable(args: list[str]) -> None:
    """启用插件。"""
    if not args:
        print("用法: plugin enable <name>")
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(server.enable_plugin(args[0]))
        print(f"[成功] 插件 '{args[0]}' 已启用")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")


def cmd_plugin_disable(args: list[str]) -> None:
    """禁用插件。"""
    if not args:
        print("用法: plugin disable <name>")
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(server.disable_plugin(args[0]))
        print(f"[成功] 插件 '{args[0]}' 已禁用")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")


async def cmd_plugin_reload(args: list[str]) -> None:
    """重载插件。"""
    if not args:
        print("用法: plugin reload <name>")
        return
    try:
        meta = await server.reload_plugin(args[0])
        print(f"[成功] 插件已重载: {meta.name} v{meta.version}")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")


def cmd_plugin_perms(args: list[str]) -> None:
    """查看插件权限。"""
    if not args:
        print("用法: plugin perms <name>")
        return
    name = args[0]
    meta = _require_plugin(name)
    if meta is None:
        return

    try:
        info = server.get_plugin_permissions(name)
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")
        return

    print(f"  {name} 权限信息:")
    print("  ┌- 当前配置:")
    for k, v in info["permissions"].items():
        mark = "[+]" if v else "[-]"
        print(f"  |   {mark} {k}: {v}")
    print(f"  +- 生效 Flag 值: {info['effective_flag']}")
    print(f"  +- 生效权限: {info['effective_names']}")
    if info["bot_permissions"]:
        print(f"  +- Bot 权限: {info['bot_permissions']}")
    if info["missing_in_bot"]:
        print(f"  +- Bot 缺失: {info['missing_in_bot']}  [WARN]️")
    else:
        print("  +- Bot 缺失: (无)")


def cmd_plugin_perm(args: list[str]) -> None:
    """修改单个插件权限。"""
    if len(args) < 3:
        print("用法: plugin perm <name> <key> <true/false>")
        print("  例: plugin perm example_plugin SEND_GIFT true")
        return

    name, key, value_str = args[0], args[1].upper(), args[2]
    value = _bool(value_str)

    try:
        server.update_plugin_permission(name, key, value)
        print(f"[成功] {name}.{key} = {value}")
        # 重新加载显示
        info = server.get_plugin_permissions(name)
        enabled = [k for k, v in info["permissions"].items() if v]
        print(f"  当前启用的权限: {enabled}")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")
    except CorePluginPermissionException as e:
        print(f"[错误] {e}")


def cmd_plugin_readme(args: list[str]) -> None:
    """查看插件 README。"""
    if not args:
        print("用法: plugin readme <name>")
        return
    try:
        readme = server.get_plugin_readme(args[0])
        if readme:
            print(readme)
        else:
            print("  (无 README)")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")


def cmd_plugin_changelog(args: list[str]) -> None:
    """查看插件 CHANGELOG。"""
    if not args:
        print("用法: plugin changelog <name>")
        return
    try:
        cl = server.get_plugin_changelog(args[0])
        if cl:
            print(cl)
        else:
            print("  (无 CHANGELOG)")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")


def cmd_plugin_failed(_args: list[str] | None = None) -> None:
    """查看加载失败的插件。"""
    failed = server.get_failed_plugins()
    if not failed:
        print("  (无失败插件)")
        return
    for f in failed:
        print(f"  [{f.get('dir_name')}] {f.get('error')}")


async def cmd_plugin_uninstall(args: list[str]) -> None:
    """卸载插件。"""
    if not args:
        print("用法: plugin uninstall <name>")
        return
    try:
        await server.uninstall_plugin(args[0], delete_config=True, delete_data=False)
        print(f"[成功] 插件 '{args[0]}' 已卸载（配置已清理）")
    except CorePluginNotFoundException as e:
        print(f"[错误] {e}")


# ---------------------------------------------------------------- #
# Server 命令
# ---------------------------------------------------------------- #


def cmd_server_status(_args: list[str] | None = None) -> None:
    """服务器状态总览。"""
    bot = server.bot
    lives = server.livestreams
    plugins = server.plugins

    print("+==========================================+")
    print("|           MisMiss Server Status           |")
    print("+==========================================+")
    print("|  Bot                                     |")
    print(f"|    名称:  {bot.name:<30} |")
    print(f"|    ID:    {bot.id:<30} |")
    print(f"|    可用:  {str(server.bot_available):<30} |")
    print(f"|    权限:  {_fmt_perms(bot.permissions)[:30]:<30} |")
    print("+==========================================+")
    print(f"|  Livestreams: {len(lives):<27} |")
    for lid, live in lives.items():
        conn = "[+]" if live.is_connected else "[-]"
        print(
            f"|    [{lid}] {live.room_name[:20]:<20} "
            f"conn={conn} |"
        )
    print("+==========================================+")
    print(f"|  Plugins: {len(plugins):<30} |")
    for p in plugins:
        status = "[+]" if p.enabled else "[-]"
        print(f"|    {status} {p.name:<28} |")
    failed = server.get_failed_plugins()
    if failed:
        print(f"|  Failed: {len(failed):<31} |")
    print("+==========================================+")


async def cmd_server_shutdown(_args: list[str] | None = None) -> None:
    """关闭服务器。"""
    print("正在关闭...")
    await server.shutdown()
    print("服务器已关闭")


# ================================================================== #
# 命令路由
# ================================================================== #

COMMAND_MAP: dict[str, callable] = {  # type: ignore[type-arg]
    # help
    "help": cmd_help,
    # bot
    "bot create": cmd_bot_create,
    "bot info": cmd_bot_info,
    "bot refresh": cmd_bot_refresh,
    "bot cookie": cmd_bot_cookie,
    "bot verify": cmd_bot_verify,
    "bot disable": cmd_bot_disable,
    "bot enable": cmd_bot_enable,
    # livestream
    "live add": cmd_live_add,
    "live list": cmd_live_list,
    "live info": cmd_live_info,
    "live enable": cmd_live_enable,
    "live disable": cmd_live_disable,
    "live join": cmd_live_join,
    "live quit": cmd_live_quit,
    "live msg": cmd_live_msg,
    # plugin
    "plugin list": cmd_plugin_list,
    "plugin info": cmd_plugin_info,
    "plugin handlers": cmd_plugin_handlers,
    "plugin enable": cmd_plugin_enable,
    "plugin disable": cmd_plugin_disable,
    "plugin reload": cmd_plugin_reload,
    "plugin perms": cmd_plugin_perms,
    "plugin perm": cmd_plugin_perm,
    "plugin readme": cmd_plugin_readme,
    "plugin changelog": cmd_plugin_changelog,
    "plugin failed": cmd_plugin_failed,
    "plugin uninstall": cmd_plugin_uninstall,
    # server
    "server status": cmd_server_status,
    "server shutdown": cmd_server_shutdown,
}


def match_command(line: str) -> tuple[callable, list[str]] | None:  # type: ignore[type-arg]
    """按前缀匹配命令。"""
    line = line.strip()
    if not line:
        return None

    # 精确匹配前缀最长的命令
    best_match: tuple[int, callable, str] | None = None  # type: ignore[type-arg]
    for prefix, handler in COMMAND_MAP.items():
        if line == prefix or line.startswith(prefix + " "):
            if best_match is None or len(prefix) > best_match[0]:
                best_match = (len(prefix), handler, prefix)

    if best_match is None:
        return None

    _, handler, prefix = best_match
    # 提取参数
    if line == prefix:
        args: list[str] = []
    else:
        args = line[len(prefix) + 1 :].split()
    return handler, args


# ================================================================== #
# Main
# ================================================================== #


async def main() -> None:
    global server

    print("+==================================================+")
    print("|          MisMiss Interactive Demo                 |")
    print("+==================================================+")
    print()
    print("启动 Server ...")

    # 初始化
    server = MissevanServer()
    await server.start()

    # 显示初始状态
    cookie = _load_cookie()
    print(f"Cookie 文件: {'已找到 (' + str(len(cookie)) + ' 字符)' if cookie else '未找到'}")
    print(f"已加载插件: {len(server.plugins)} 个")
    for p in server.plugins:
        print(f"  - {p.name} v{p.version} ({'enabled' if p.enabled else 'disabled'})")
    print()
    print("输入 help 查看命令列表，exit 退出")
    print()

    # REPL — input() 在 executor 中运行，避免阻塞事件循环
    # （否则 create_task 调度的后台任务永远不会被执行）
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = (await loop.run_in_executor(None, input, "miss> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line in ("exit", "quit", "q"):
            break

        matched = match_command(line)
        if matched is None:
            print(f"未知命令: {line}")
            print("输入 help 查看可用命令")
            continue

        handler, args = matched
        try:
            result = handler(args)
            # 如果是协程则 await
            if asyncio.iscoroutine(result):
                await result
                # 给后台任务（消息消费队列等）执行机会
                await asyncio.sleep(0)
        except Exception as e:
            print(f"[异常] {type(e).__name__}: {e}")

    # 退出
    print("正在关闭...")
    try:
        await server.shutdown()
    except Exception:
        pass
    print("再见!")


if __name__ == "__main__":
    asyncio.run(main())
