"""MissevanBot 连接演示。

从 ``bot_demo_cookie.txt`` 读取 Cookie，连接机器人并输出信息。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import MissevanBot
from core.exceptions import CoreCookieException, CorePermissionException
from interfaces.bot import BotPermission


def _load_cookie() -> str:
    """从文件中加载 Cookie。"""
    cookie_path = os.path.join(os.path.dirname(__file__), "bot_demo_cookie.txt")
    if not os.path.exists(cookie_path):
        print(f"Cookie 文件不存在: {cookie_path}")
        print("请创建 bot_demo_cookie.txt 并写入 Cookie 字符串")
        return ""
    with open(cookie_path, "r", encoding="utf-8") as f:
        return "".join(line.strip() for line in f)


async def main():
    print("=" * 50)
    print("MissevanBot 连接演示")
    print("=" * 50)

    cookie = _load_cookie()
    if not cookie:
        return

    print(f"Cookie 长度: {len(cookie)} 字符\n")

    # 创建机器人
    print("[1] 创建 MissevanBot ...")
    bot = MissevanBot(cookie)

    # 刷新信息
    print("[2] 刷新机器人信息 ...")
    try:
        await bot.refresh()
    except CoreCookieException as e:
        print(f"  Cookie 无效或已过期: {e}")
        print(f"  机器人已自动停用: enabled={bot.enabled}")
        return

    # 输出信息
    print()
    print("--- 机器人信息 ---")
    print(f"  ID:       {bot.id}")
    print(f"  名称:     {bot.name}")
    print(f"  简介:     {bot.introduction}")
    print(f"  头像URL:  {bot.icon_url}")
    print(f"  启用状态: {bot.enabled}")
    print(f"  权限:     {bot.permissions}")
    print()

    # 测试 Cookie 权限
    print("[3] 测试 get_cookie（默认无权限）...")
    try:
        bot.get_cookie()
    except CorePermissionException as e:
        print(f"  权限不足（预期）: {e}")

    # 权限仅在构造时设置，创建后不可修改
    print()
    print("[4] 创建带 EXPOSE_COOKIE 权限的机器人...")
    bot2 = MissevanBot(
        cookie,
        permissions=BotPermission.SEND_LIVESTREAM_MESSAGE | BotPermission.EXPOSE_COOKIE,
    )
    await bot2.refresh()
    c = bot2.get_cookie()
    print(f"  Cookie: {c[:20]}...")

    # 验证权限不可修改
    print()
    print("[5] 验证 permissions 为只读...")
    try:
        bot2.permissions = BotPermission.SEND_LIVESTREAM_MESSAGE  # type: ignore
        print("  WARN: 权限被修改了（不应该发生）")
    except AttributeError:
        print("  权限不可修改（AttributeError——符合预期）")

    print()
    print("=" * 50)
    print("演示完成")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
