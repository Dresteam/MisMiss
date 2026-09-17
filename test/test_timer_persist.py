"""定时消息持久化测试(无网络)。

运行: docker run --rm -v <repo>:/src -w /src mismiss:latest python /src/test/test_timer_persist.py
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.server import MissevanServer  # noqa: E402
from core.bot.mis_bot import MissevanBot  # noqa: E402


async def main():
    tmp = tempfile.mkdtemp(prefix="mismiss-timer-test-")
    state_path = os.path.join(tmp, "server_state.json")
    s = MissevanServer()
    s._data_dir = tmp
    s._bot_cookie = "cookie-x"  # 使 _save_state 写出 bot 与 timer_messages
    s._bot_available = True
    s._bot.enabled = True

    g1 = s.register_timer_message(0, "全局1")
    g2 = s.register_timer_message(0, "全局2")
    r1 = s.register_timer_message(12345, "房间消息1")

    # 指针操作与排序(注意顺序: skip 在 move 之前, 否则指针处消息不同)
    assert s.skip_timer_message_once(g1, 12345), "全局消息应位于指针处"
    assert s.move_timer_message(g2, -1), "g2 应可上移"
    assert s.update_timer_message(r1, "房间消息1改")

    # ---- 1. 持久化内容 ----
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    assert "timer_messages" in state, "FAIL: state 文件缺少 timer_messages"
    tm = state["timer_messages"]
    assert [m["message_id"] for m in tm["global"]] == [g2, g1], "FAIL: 全局顺序未持久化"
    assert tm["rooms"][0]["live_id"] == 12345
    assert tm["rooms"][0]["position"] == 1, "FAIL: 轮转指针未持久化"
    assert tm["rooms"][0]["messages"][0]["message"] == "房间消息1改", "FAIL: 消息内容未持久化"
    print("PASS 1: 定时消息随 state 持久化(顺序/指针/内容)")

    # ---- 2. 恢复 roundtrip ----
    bot2 = MissevanBot("", timer_interval=60.0)
    bot2.restore_timer_state(tm)
    assert bot2.export_timer_state() == tm, "FAIL: 恢复 roundtrip 不一致"
    assert bot2.timer_message_count == 3, "FAIL: 恢复数量错误"
    print("PASS 2: 恢复 roundtrip 一致(3 条, 停用态不启动计时循环)")

    # ---- 3. Cookie 更新迁移(create_bot 内部逻辑) ----
    old_bot = MissevanBot("old", timer_interval=60.0)
    old_bot.restore_timer_state(tm)
    new_bot = MissevanBot("new", timer_interval=60.0)
    new_bot.restore_timer_state(old_bot.export_timer_state())
    assert new_bot.export_timer_state() == tm, "FAIL: Cookie 更新后定时消息丢失"
    print("PASS 3: Cookie 更新迁移保留定时消息")

    # ---- 4. 删除消息后持久化同步 ----
    s.unregister_timer_message(g2)
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    saved_ids = [m["message_id"] for m in state["timer_messages"]["global"]]
    assert saved_ids == [g1], f"FAIL: 删除未持久化 {saved_ids}"
    print("PASS 4: 删除定时消息后持久化同步")

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
