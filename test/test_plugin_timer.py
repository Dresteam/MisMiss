"""插件定时消息测试(无网络)。

覆盖:插件消息不落盘、置顶且与普通消息共用指针、不可改删移动、
按插件清理互不影响、增删时指针补偿、基类专用接口。

运行: .venv/Scripts/python.exe test/test_plugin_timer.py
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.server import MissevanServer  # noqa: E402
from core.bot.mis_bot import MissevanBot  # noqa: E402
from interfaces.plugin import Plugin  # noqa: E402

ROOM = 12345


async def main():
    tmp = tempfile.mkdtemp(prefix="mismiss-plugin-timer-")
    state_path = os.path.join(tmp, "server_state.json")
    s = MissevanServer()
    s._data_dir = tmp
    s._bot_cookie = "cookie-x"  # 使 _save_state 写出 bot 与 timer_messages
    s._bot_available = True
    s._bot.enabled = True
    # 无网络环境下用 account_record 提供账户房间（_account_room_id 的主路径）
    s.account_record = SimpleNamespace(room_id=ROOM)

    # 面板通道注册的普通消息
    n1 = s.register_timer_message(ROOM, "普通1")
    n2 = s.register_timer_message(ROOM, "普通2")
    # 插件消息（经 Server 门面，即框架给插件的专用接口）
    p1 = s.register_plugin_timer_message("timer_messages", "插件1")
    p2 = s.register_plugin_timer_message("timer_messages", "插件2")
    q1 = s.register_plugin_timer_message("song_request", "点播提示")
    assert p1 and p2 and q1, "FAIL: 插件消息注册失败"

    def room_messages():
        data = s.list_timer_messages()
        return next(r for r in data["rooms"] if r["live_id"] == ROOM)["messages"]

    # ---- 1. 插件消息不写入持久化文件 ----
    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)
    saved_ids = [m["message_id"] for m in state["timer_messages"]["rooms"][0]["messages"]]
    assert saved_ids == [n1, n2], f"FAIL: 落盘内容异常 {saved_ids}"
    print("PASS 1: 插件消息不写入持久化文件(仅普通消息落盘)")

    # ---- 2. export_timer_state 同样不含插件消息 ----
    exported = s._bot.export_timer_state()
    exp_ids = [m["message_id"] for r in exported["rooms"] for m in r["messages"]]
    assert exp_ids == [n1, n2], f"FAIL: 导出内容含插件消息 {exp_ids}"
    print("PASS 2: export_timer_state 不含插件消息")

    # ---- 3. 列表按合并轮转返回：插件消息置顶 + source 标记 ----
    msgs = room_messages()
    order = [m["message_id"] for m in msgs]
    assert order == [p1, p2, q1, n1, n2], f"FAIL: 轮转顺序 {order}"
    by_id = {m["message_id"]: m for m in msgs}
    assert by_id[p1]["source"] == "plugin", "FAIL: 插件消息未标记 source"
    assert by_id[p1]["plugin_name"] == "timer_messages", "FAIL: 未带插件名"
    assert by_id[n1]["source"] == "normal" and by_id[n1]["plugin_name"] is None
    listed = s.list_timer_messages()
    assert len(listed["plugin"]) == 3, "FAIL: 顶层 plugin 列表不完整"
    print("PASS 3: 插件消息置顶、source/plugin_name 标记正确")

    # ---- 4. 不可编辑 / 删除 / 移动 ----
    assert not s.update_timer_message(p1, "被改了"), "FAIL: 插件消息被编辑"
    assert not s.move_timer_message(p1, 1), "FAIL: 插件消息被移动"
    s.unregister_timer_message(p1)  # 应被静默拒绝
    assert s.is_plugin_timer_message(p1), "FAIL: 插件消息被删除"
    assert [m["message_id"] for m in room_messages()] == [p1, p2, q1, n1, n2]
    print("PASS 4: 插件消息不可编辑/删除/移动")

    # ---- 5. 普通消息仍可编辑/删除/移动（未误伤） ----
    assert s.update_timer_message(n1, "普通1改"), "FAIL: 普通消息编辑被误伤"
    assert s.move_timer_message(n2, -1), "FAIL: 普通消息移动被误伤"
    assert [m["message_id"] for m in room_messages()] == [p1, p2, q1, n2, n1]
    print("PASS 5: 普通消息的编辑/移动不受影响")

    # ---- 6. 按插件清理，只影响该插件 ----
    removed = s.unregister_plugin_timer_messages("timer_messages")
    assert removed == 2, f"FAIL: 清理条数 {removed}"
    ids = [m["message_id"] for m in room_messages()]
    assert ids == [q1, n2, n1], f"FAIL: 清理后 {ids}"
    assert not s.is_plugin_timer_message(p1)
    assert s.is_plugin_timer_message(q1), "FAIL: 误删了其他插件的消息"
    print("PASS 6: 按插件清理互不影响")

    # ---- 7. 共用指针：插件消息参与轮转且排在普通消息之前 ----
    bot = s._bot
    assert bot._combined_cycle(ROOM) == [q1, n2, n1], "FAIL: 合并轮转组成错误"
    bot._room_positions[ROOM] = 0
    assert bot._combined_cycle(ROOM)[0] == q1, "FAIL: 指针首位不是插件消息"
    print("PASS 7: 插件消息与普通消息共用同一轮转指针")

    # ---- 8. 增删插件消息时指针补偿（仍指向原来那条） ----
    b2 = MissevanBot("", timer_interval=60.0)
    a = b2.register_timer_message(ROOM, "A")
    b = b2.register_timer_message(ROOM, "B")
    b2._room_positions[ROOM] = 1  # 指向 B
    assert b2._combined_cycle(ROOM)[1] == b

    pid = b2.register_plugin_timer_message("plug", ROOM, "P")
    assert b2._combined_cycle(ROOM) == [pid, a, b], "FAIL: 插件消息未置顶"
    assert b2._room_positions[ROOM] == 2, f"FAIL: 插入后指针未补偿 {b2._room_positions[ROOM]}"
    assert b2._combined_cycle(ROOM)[b2._room_positions[ROOM]] == b, "FAIL: 插入后指针指向变了"

    b2.unregister_plugin_timer_messages("plug")
    assert b2._combined_cycle(ROOM) == [a, b]
    assert b2._room_positions[ROOM] == 1, f"FAIL: 删除后指针未补偿 {b2._room_positions[ROOM]}"
    assert b2._combined_cycle(ROOM)[b2._room_positions[ROOM]] == b, "FAIL: 删除后指针指向变了"
    print("PASS 8: 插件消息增删时指针保持指向同一条消息")

    # ---- 9. 插件基类专用接口 ----
    class _Demo(Plugin):
        pass

    pl = _Demo()
    pl.name = "timer_messages"
    pl._server = s
    mid = pl.register_timer_message("经基类注册")
    assert mid and s.is_plugin_timer_message(mid), "FAIL: 基类接口未走插件消息通道"
    assert s.list_timer_messages()["plugin"][-1]["plugin_name"] == "timer_messages"
    pl.unregister_timer_messages()
    assert not s.is_plugin_timer_message(mid), "FAIL: 基类撤销未生效"
    # server 未注入时安全返回空串，不抛异常
    pl2 = _Demo()
    pl2.name = "x"
    assert pl2.register_timer_message("hi") == ""
    pl2.unregister_timer_messages()
    print("PASS 9: 基类 register/unregister_timer_messages 行为正确")

    # ---- 10. 账户未绑定直播间时返回空串（插件据此重试） ----
    s2 = MissevanServer()
    s2._data_dir = tempfile.mkdtemp(prefix="mismiss-plugin-timer-noroom-")
    s2.account_record = SimpleNamespace(room_id=None)
    assert s2.register_plugin_timer_message("p", "消息") == "", "FAIL: 无房间时应返回空串"
    print("PASS 10: 账户未绑定直播间时注册返回空串")

    # ---- 11. 插件异常终止后重新启用不产生重复消息 ----
    # 该插件的 terminate 故意抛异常（模拟崩溃未清理），只有框架的强制清理能兜住。
    tmp2 = tempfile.mkdtemp(prefix="mismiss-plugin-timer-pm-")
    lib = os.path.join(tmp2, "plugins")  # 模块以 plugins.<name> 导入，故须置于 plugins/ 下
    pdir = os.path.join(lib, "crash_timer")
    os.makedirs(pdir)
    with open(os.path.join(pdir, "metadata.yaml"), "w", encoding="utf-8") as f:
        f.write("name: crash_timer\ndesc: 异常终止插件\nauthor: test\nversion: 1.0.0\n")
    # 该插件只在 on_livestream_bound 里注册（新推荐的写法），
    # 且 terminate 故意抛异常（模拟崩溃未清理）——只有框架的强制清理能兜住。
    with open(os.path.join(pdir, "main.py"), "w", encoding="utf-8") as f:
        f.write(
            "from interfaces.plugin import Plugin\n\n\n"
            "class CrashTimer(Plugin):\n"
            "    async def on_livestream_bound(self, livestream):\n"
            "        self.register_timer_message('崩溃插件消息')\n\n"
            "    async def terminate(self):\n"
            "        raise RuntimeError('模拟异常终止，未清理定时消息')\n"
        )

    srv = MissevanServer(data_dir=os.path.join(tmp2, "acc"), plugin_library_dir=lib)
    srv.account_record = SimpleNamespace(room_id=ROOM)
    await srv.start()
    # 账户已绑定直播间：新的插件只需实现 on_livestream_bound 即可注册
    srv._livestreams[ROOM] = SimpleNamespace(
        live_id=ROOM, room_name="测试直播间", enabled=True, is_streaming=True,
    )

    await srv.enable_plugin("crash_timer")
    assert srv._bot.plugin_timer_message_count == 1, "FAIL: 启用时未通过绑定钩子注册"
    assert srv._bot.normal_timer_message_count == 0, "FAIL: 普通消息计数被污染"
    await srv.disable_plugin("crash_timer")
    assert srv._bot.plugin_timer_message_count == 0, "FAIL: 禁用后插件消息未被强制清理"
    await srv.enable_plugin("crash_timer")
    assert srv._bot.plugin_timer_message_count == 1, "FAIL: 重新启用后重复注册"
    await srv.disable_plugin("crash_timer")
    await srv.enable_plugin("crash_timer")
    assert srv._bot.plugin_timer_message_count == 1, "FAIL: 多轮启停后重复注册"
    await srv.uninstall_plugin("crash_timer", delete_config=True, delete_data=True)
    assert srv._bot.plugin_timer_message_count == 0, "FAIL: 卸载后插件消息未清理"
    await srv.shutdown()
    print("PASS 11: 插件异常终止后重新启用不产生重复消息（经绑定钩子注册）")

    # ---- 12. 仅开播时发送 ----
    b3 = MissevanBot("", timer_interval=60.0)
    live_state = {"live": False}
    b3.set_live_checker(lambda lid: live_state["live"])
    sent: list[str] = []

    async def _fake_send(entry):
        sent.append(entry.message)
        return True

    b3._send_message_entry = _fake_send  # type: ignore[method-assign]
    b3.register_timer_message(ROOM, "普通消息")
    b3.register_plugin_timer_message("plug", ROOM, "仅开播消息", only_when_live=True)

    b3._room_positions[ROOM] = 0
    await b3._send_next_combined(ROOM)  # 插件消息：未开播 → 跳过
    await b3._send_next_combined(ROOM)  # 普通消息：照常发送
    assert sent == ["普通消息"], f"FAIL: 未开播时不应发送插件消息 {sent}"

    live_state["live"] = True
    b3._room_positions[ROOM] = 0
    await b3._send_next_combined(ROOM)  # 插件消息：已开播 → 发送
    assert sent[-1] == "仅开播消息", f"FAIL: 开播后应发送插件消息 {sent}"

    # 未注入检查器时一律视为开播（不误吞消息）
    b3.set_live_checker(None)
    assert b3._is_live(ROOM) is True, "FAIL: 无检查器时应视为开播"
    print("PASS 12: 仅开播时发送条件生效")

    # ---- 13. 计数区分普通 / 插件 ----
    b4 = MissevanBot("", timer_interval=60.0)
    b4.register_timer_message(ROOM, "N1")
    b4.register_timer_message(ROOM, "N2")
    b4.register_plugin_timer_message("plug", ROOM, "P1")
    b4.register_plugin_timer_message("plug", ROOM, "P2")
    b4.register_plugin_timer_message("plug", ROOM, "P3")
    assert b4.normal_timer_message_count == 2, "FAIL: 普通消息计数错误"
    assert b4.plugin_timer_message_count == 3, "FAIL: 插件消息计数错误"
    assert b4.timer_message_count == 5, "FAIL: 总数计数错误"
    print("PASS 13: 普通 / 插件消息计数分别正确")

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
