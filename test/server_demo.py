"""MissevanServer 连接演示。

从 ``bot_demo_cookie.txt`` 读取 Cookie，连接机器人并输出信息。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import MissevanBot, MissevanServer
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
    server: MissevanServer = MissevanServer()
    await server.start()
    if not server.bot_available:
        bot: MissevanBot = await server.create_bot(
            _load_cookie(),
            permissions=BotPermission.SEND_LIVESTREAM_MESSAGE
        )
        print(bot.name)
        print(bot.introduction)


if __name__ == "__main__":
    asyncio.run(main())