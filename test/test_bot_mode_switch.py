"""Bot 模式切换：切到公共 Cookie 时自有 Cookie 不得丢失（无外部网络）。

覆盖：
- private → public：自有 Cookie 被留存，且落进 server_state.json
- public  → private：必须显式提供 Cookie；切回后留存清空
- public  → private 不给 Cookie：拒绝
- 走 update_account（管理端的另一条切模式入口）同样会留存，没有绕过路径
- 切到公共后权限被强制降级

运行: .venv/Scripts/python.exe test/test_bot_mode_switch.py
"""

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import MissevanServer  # noqa: E402
from core.account import AccountManager  # noqa: E402
from core.config import ServerConfig  # noqa: E402
from interfaces.bot import BotPermission  # noqa: E402


# ------------------------------------------------------------------ #
# 打桩:替换 update_cookie,避免真的去打 fm.missevan.com
# 行为对齐真实实现的关键部分(写入 _bot_cookie / 覆盖权限 / 落盘 state)
# ------------------------------------------------------------------ #

async def _fake_update_cookie(self, new_cookie, permissions=None):
    self._bot_cookie = new_cookie
    if permissions is not None:
        self._bot_permissions = permissions
    self._save_state()
    return self.bot


async def _fake_refresh_public_bot(self):
    return {}


MissevanServer.update_cookie = _fake_update_cookie
AccountManager.refresh_public_bot = _fake_refresh_public_bot


def _state_of(data_dir: str, account_id: int) -> dict:
    path = os.path.join(data_dir, "accounts", str(account_id), "server_state.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def main():
    tmp = tempfile.mkdtemp(prefix="mismiss-mode-test-")
    cfg = ServerConfig({"server": {"data_dir": tmp}})
    manager = AccountManager(cfg)
    manager.load()

    # 面板公共 Cookie —— 切公共模式的前置条件
    await manager.set_public_bot("PANEL=1")

    rec = await manager.create_account("模式账户", bot_mode="private", username="mode_a")
    acc = rec.id
    server = manager.get_server(acc)

    # ---- 1. 起始：私有 Cookie 在用，没有留存 ----
    await manager.switch_bot_mode(acc, "private", "MINE=1")
    assert server.bot_cookie == "MINE=1", server.bot_cookie
    assert server.saved_private_cookie == ""
    print("PASS 1: 私有模式起始状态正确")

    # ---- 2. 切公共：自有 Cookie 被留存，不是被丢掉 ----
    await manager.switch_bot_mode(acc, "public")
    assert manager.get_record(acc).bot_mode == "public"
    assert server.bot_cookie == "PANEL=1", server.bot_cookie
    assert server.saved_private_cookie == "MINE=1", server.saved_private_cookie
    print("PASS 2: 切公共后自有 Cookie 已留存")

    # ---- 3. 留存写进了 server_state.json（重启/多 worker 也拿得回来） ----
    on_disk = _state_of(tmp, acc)["bot"]
    assert on_disk.get("saved_private_cookie") == "MINE=1", on_disk
    assert on_disk["cookie"] == "PANEL=1", on_disk
    print("PASS 3: 留存已落盘")

    # ---- 4. 切公共时权限被强制降级 ----
    assert server.bot.permissions == BotPermission.SEND_LIVESTREAM_MESSAGE, server.bot.permissions
    print("PASS 4: 公共模式权限强制降级")

    # ---- 5. 不给 Cookie 切不回私有 ----
    try:
        await manager.switch_bot_mode(acc, "private", "")
        raise AssertionError("留空应当被拒绝")
    except ValueError:
        pass
    assert manager.get_record(acc).bot_mode == "public", "失败的切换不应改变模式"
    print("PASS 5: 切回私有必须显式提供 Cookie")

    # ---- 6. 给 Cookie 切回私有，留存随之清空 ----
    await manager.switch_bot_mode(acc, "private", "MINE=1")
    assert manager.get_record(acc).bot_mode == "private"
    assert server.bot_cookie == "MINE=1"
    assert server.saved_private_cookie == "", "切回私有后留存应清空"
    assert "saved_private_cookie" not in _state_of(tmp, acc)["bot"]
    print("PASS 6: 切回私有后留存清空")

    # ---- 7. 管理端那条入口（update_account）同样留存，没有绕过路径 ----
    await manager.update_account(acc, bot_mode="public")
    assert manager.get_record(acc).bot_mode == "public"
    assert server.bot_cookie == "PANEL=1", server.bot_cookie
    assert server.saved_private_cookie == "MINE=1", (
        "update_account 也必须留存自有 Cookie，否则绕过了 switch_bot_mode 的保护"
    )
    # 且权限同样被降级（此前这条路径没有强制降级）
    assert server.bot.permissions == BotPermission.SEND_LIVESTREAM_MESSAGE, server.bot.permissions
    print("PASS 7: update_account 路径同样留存并降级")

    await manager.shutdown_all()
    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
