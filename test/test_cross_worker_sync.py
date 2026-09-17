"""跨 worker 状态同步模拟测试(无网络,临时目录)。

模拟 Docker 4-worker 场景下两个 Server 实例共享同一 state 文件,
验证: 删除直播间同步、过期保存不复活、Bot 启用/删除同步、停用断连同步。
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.server import MissevanServer  # noqa: E402
from core.exceptions import CoreDisabledException  # noqa: E402
from interfaces.bot import BotPermission  # noqa: E402


class FakeLive:
    def __init__(self, live_id, enabled=False, connected=False):
        self.live_id = live_id
        self.room_name = f"room{live_id}"
        self.enabled = enabled
        self.is_connected = connected
        self.quit_calls = 0

    async def quit(self):
        if not self.enabled:
            raise CoreDisabledException("已停用")
        await self.disconnect()

    async def disconnect(self):
        if self.is_connected:
            self.quit_calls += 1
        self.is_connected = False


async def main():
    tmp = tempfile.mkdtemp(prefix="mismiss-sync-test-")
    state_path = os.path.join(tmp, "server_state.json")
    s1 = MissevanServer()
    s2 = MissevanServer()
    s1._data_dir = tmp
    s2._data_dir = tmp

    # ---- 初始: 两个 worker 都有直播间 123(启用+连接) ----
    live1_a = FakeLive(123, enabled=True, connected=True)
    live1_b = FakeLive(123, enabled=True, connected=True)
    s1._livestreams[123] = live1_a
    s2._livestreams[123] = live1_b
    s1._enabled_livestreams = {123}
    s2._enabled_livestreams = {123}
    s1._save_state()

    # ---- 1. worker A 删除 123 → worker B 刷新后应消失 ----
    await s1.remove_livestream(123)
    assert 123 not in s1._livestreams
    s2._ensure_state_fresh()
    await asyncio.sleep(0.05)  # 等待后台 quit 任务
    assert 123 not in s2._livestreams, "FAIL: 已删除直播间仍残留在另一 worker 内存"
    assert live1_b.quit_calls == 1, "FAIL: 清理时未退出残留连接"
    print("PASS 1: 删除直播间跨 worker 同步(含断连)")

    # ---- 2. worker B 过期保存不应复活 123 ----
    s2._save_state()
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    assert 123 not in state["livestreams"], "FAIL: 过期内存保存复活了已删除直播间"
    print("PASS 2: 过期内存保存不复活已删除直播间")

    # ---- 3. 保存前强制同步: B 内存残留 999 时保存应自动清理 ----
    s2._livestreams[999] = FakeLive(999)
    s2._state_mtime = 0  # 模拟 B 错过上一次写入
    s2._save_state()
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    assert 999 not in state["livestreams"], "FAIL: 保存前未同步, 残留直播间写入文件"
    assert 999 not in s2._livestreams
    print("PASS 3: 保存前自动同步清理过期内存")

    # ---- 4. Bot 启用同步 ----
    s1._bot = SimpleNamespace(id=1, enabled=True, timer_interval=60.0)
    s1._bot_available = True
    s1._bot_cookie = "cookie-x"
    s1._bot_permissions = BotPermission.SEND_LIVESTREAM_MESSAGE
    s1._save_state()
    s2._bot = SimpleNamespace(id=1, enabled=False, timer_interval=60.0)
    s2._ensure_state_fresh()
    assert s2._bot.enabled is True, "FAIL: Bot 启用状态未跨 worker 同步"
    print("PASS 4: Bot 启用状态跨 worker 同步")

    # ---- 5. Bot 删除同步 ----
    s1._bot = SimpleNamespace(id=0, enabled=False, timer_interval=60.0)
    s1._bot_available = False
    s1._bot_cookie = ""
    s1._save_state()
    s2._ensure_state_fresh()
    assert s2._bot.id == 0 and s2._bot_available is False, "FAIL: Bot 删除未跨 worker 同步"
    print("PASS 5: Bot 删除跨 worker 同步")

    # ---- 6. 停用直播间同步(实例标记 + 断连) ----
    live2_a = FakeLive(456, enabled=True, connected=True)
    live2_b = FakeLive(456, enabled=True, connected=True)
    s1._livestreams[456] = live2_a
    s2._livestreams[456] = live2_b
    s1._enabled_livestreams.add(456)
    s2._enabled_livestreams.add(456)
    s1._save_state()
    s2._ensure_state_fresh()  # 对齐 baseline
    s1.disable_livestream(456)
    await asyncio.sleep(0.05)
    s2._ensure_state_fresh()
    await asyncio.sleep(0.05)
    assert s2._livestreams[456].enabled is False, "FAIL: 停用状态未同步到实例标记"
    assert live2_b.quit_calls == 1 and live2_b.is_connected is False, \
        "FAIL: 停用同步后未断开本 worker 连接"
    assert live2_a.quit_calls == 1 and live2_a.is_connected is False, \
        "FAIL: 本 worker 停用流程未实际断开连接"
    print("PASS 6: 停用直播间跨 worker 同步(标记+断连)")

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
