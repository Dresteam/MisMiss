"""专属昵称插件测试(无网络)。

覆盖:设置/查看/重置指令、回执文案渲染、昵称改写作用于全部用户事件、
指令消息的取消传播(可配置)、匿名用户豁免、超长拒绝、持久化与重载。

运行: .venv/Scripts/python.exe test/test_nickname_plugin.py
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.events.bus import EventBus  # noqa: E402
from core.models.events import GiftEvent, JoinEvent, MessageEvent  # noqa: E402
from core.models.user import MissevanLiveUser, MissevanUser  # noqa: E402
from core.plugin.data_manager import PluginDataManager  # noqa: E402
from interfaces.event import Listener, event_handler  # noqa: E402
from interfaces.event.livestream import LiveMessageEvent  # noqa: E402
from interfaces.plugin.miss_config import MissConfig  # noqa: E402

_PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "..", "plugins", "nickname")
sys.path.insert(0, _PLUGIN_DIR)

import main as nickname_main  # noqa: E402


def _defaults() -> dict:
    """从随插件分发的 _conf_schema.json 读取默认配置。"""
    with open(os.path.join(_PLUGIN_DIR, "_conf_schema.json"), encoding="utf-8") as f:
        schema = json.load(f)
    return {key: spec.get("default") for key, spec in schema.items()}


def _expect(key: str, **values) -> str:
    """按 schema 默认文案渲染期望回执。

    不硬编码文案——改 _conf_schema.json 的默认文案不应导致测试失败。
    """
    text = str(_defaults()[key])
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


class FakeLive:
    """记录已发送消息的假直播间。"""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_message(self, message: str, priority: int = 0) -> None:
        self.sent.append(message)


class Probe(Listener):
    """优先级 0 的旁观者——用于验证指令消息是否被取消。"""

    def __init__(self) -> None:
        self.seen: list[str] = []

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        self.seen.append(event.message)


def _user(uid: int = 42, name: str = "真名") -> MissevanLiveUser:
    return MissevanLiveUser(
        base_user=MissevanUser(user_id=uid, username=name), user_livestream=None
    )


def _msg(live: FakeLive, text: str, uid: int = 42) -> MessageEvent:
    return MessageEvent(event_livestream=live, event_user=_user(uid), event_message=text)


def _build(data_dir: str, **overrides) -> tuple:
    """构造插件实例 + 独立总线。"""
    cfg = _defaults()
    cfg.update(overrides)
    plugin = nickname_main.NicknamePlugin()
    plugin.name = "nickname"
    plugin.data = PluginDataManager(data_dir)
    plugin._config = MissConfig(cfg)
    plugin._load_nicks()
    bus = EventBus()
    bus.register_new_event(plugin)
    return plugin, bus


async def main() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-nickname-")

    # ---- 1. 设置昵称：回执 + 落盘 ----
    live = FakeLive()
    plugin, bus = _build(tmp)
    bus.call_event(_msg(live, "昵称 小明"))
    await asyncio.sleep(0)  # 回执走 create_task
    assert live.sent == [_expect("msg_set", user="真名", nick="小明")], \
        f"FAIL: 回执错误 {live.sent}"
    assert plugin._nicks.get(42) == "小明", "FAIL: 昵称未写入内存"
    with open(os.path.join(tmp, "nicknames.json"), encoding="utf-8") as f:
        assert json.load(f) == {"42": "小明"}, "FAIL: 昵称未落盘"
    print("PASS 1: 「昵称 小明」设置成功、回执正确、已落盘")

    # ---- 2. 改写作用于所有用户事件 ----
    m = _msg(live, "随便说说")
    bus.call_event(m)
    assert m.user.name == "小明", f"FAIL: 弹幕用户名未改写 {m.user.name!r}"
    g = GiftEvent(event_livestream=live, event_user=_user(), event_gift=SimpleNamespace(num=1))
    bus.call_event(g)
    assert g.user.name == "小明", "FAIL: 礼物事件用户名未改写"
    j = JoinEvent(event_livestream=live, event_user=_user())
    bus.call_event(j)
    assert j.user.name == "小明", "FAIL: 进入事件用户名未改写"
    print("PASS 2: 弹幕/礼物/进入事件的用户名都被替换")

    # ---- 3. 查看昵称 ----
    live.sent.clear()
    bus.call_event(_msg(live, "昵称"))
    await asyncio.sleep(0)
    assert live.sent == [_expect("msg_show", user="小明", nick="小明")], f"FAIL: {live.sent}"
    print("PASS 3: 「昵称」回显(回执中已用昵称指代)")

    # ---- 4. 未设置时的提示 ----
    live2 = FakeLive()
    _, bus_other = _build(tempfile.mkdtemp(prefix="mismiss-nick-"))
    bus_other.call_event(_msg(live2, "昵称"))
    await asyncio.sleep(0)
    assert live2.sent == [_expect("msg_not_set", user="真名")], f"FAIL: {live2.sent}"
    print("PASS 4: 未设置时提示正确")

    # ---- 5. 重置昵称 ----
    live.sent.clear()
    bus.call_event(_msg(live, "重置昵称"))
    await asyncio.sleep(0)
    assert live.sent == [_expect("msg_reset", user="小明")], f"FAIL: {live.sent}"
    after = _msg(live, "再来一条")
    bus.call_event(after)
    assert after.user.name == "真名", f"FAIL: 重置后仍被改写 {after.user.name!r}"
    print("PASS 5: 「重置昵称」清除后恢复真实用户名")

    # ---- 6. 指令消息默认被取消，低优先级监听器收不到 ----
    probe = Probe()
    bus.register_new_event(probe)
    bus.call_event(_msg(live, "昵称 小红"))
    await asyncio.sleep(0)
    assert probe.seen == [], f"FAIL: 指令消息未被取消 {probe.seen}"
    print("PASS 6: 默认取消 —— 低优先级监听器收不到指令消息")

    # ---- 7. 关闭开关后不取消 ----
    plugin2, bus2 = _build(tempfile.mkdtemp(prefix="mismiss-nick-"), block_command_message=False)
    probe2 = Probe()
    bus2.register_new_event(probe2)
    bus2.call_event(_msg(FakeLive(), "昵称 小刚"))
    await asyncio.sleep(0)
    assert probe2.seen == ["昵称 小刚"], f"FAIL: 关闭开关后仍被取消 {probe2.seen}"
    print("PASS 7: block_command_message=false 时指令继续传播")

    # ---- 8. 匿名用户(id=0)不参与昵称 ----
    anon = MissevanLiveUser(
        base_user=MissevanUser(user_id=0, username="匿名用户"), user_livestream=None
    )
    plugin2._nicks[0] = "不该出现"
    ev = MessageEvent(event_livestream=FakeLive(), event_user=anon, event_message="x")
    bus2.call_event(ev)
    assert ev.user.name == "匿名用户", f"FAIL: 匿名用户被改写 {ev.user.name!r}"
    print("PASS 8: 匿名用户豁免")

    # ---- 9. 超长昵称被拒绝且不写入 ----
    live3 = FakeLive()
    p3, bus3 = _build(tempfile.mkdtemp(prefix="mismiss-nick-"))
    bus3.call_event(_msg(live3, "昵称 这是一个非常非常长的昵称超出了限制"))
    await asyncio.sleep(0)
    assert 42 not in p3._nicks, "FAIL: 超长昵称被写入"
    assert live3.sent == [_expect("msg_too_long", user="真名", max=12)], f"FAIL: {live3.sent}"
    print("PASS 9: 超长昵称被拒绝")

    # ---- 10. 非指令消息一律不响应、不取消 ----
    live4 = FakeLive()
    _, bus4 = _build(tempfile.mkdtemp(prefix="mismiss-nick-"))
    probe4 = Probe()
    bus4.register_new_event(probe4)
    non_commands = [
        "[普通弹幕]",           # 普通方括号聊天
        "[昵称 小明]",          # 旧的方括号指令形式——已废弃,不应再被识别
        "[昵称]",
        "[重置昵称]",
        "昵称abc",              # 指令名后未跟空格,不构成设置
        "我的昵称是小明",        # 普通聊天包含「昵称」但不以之开头
        "重置昵称了",            # 不以精确匹配结尾
    ]
    for text in non_commands:
        probe4.seen.clear()
        live4.sent.clear()
        bus4.call_event(_msg(live4, text))
        await asyncio.sleep(0)
        assert live4.sent == [], f"FAIL: {text!r} 不应有回执 {live4.sent}"
        assert probe4.seen == [text], f"FAIL: {text!r} 不应被取消 {probe4.seen}"
    assert 42 not in bus4._listeners[0]._nicks, "FAIL: 非指令消息不应改动昵称"
    print(f"PASS 10: {len(non_commands)} 种非指令消息均不响应、不取消")

    # ---- 11. 持久化：新实例重载 ----
    plugin5, bus5 = _build(tmp)  # 复用步骤 1/5/6 的同一数据目录
    assert plugin5._nicks.get(42) == "小红", f"FAIL: 重载后昵称丢失 {plugin5._nicks}"
    ev5 = _msg(FakeLive(), "重载后的弹幕")
    bus5.call_event(ev5)
    assert ev5.user.name == "小红", "FAIL: 重载后改写失效"
    print("PASS 11: 昵称持久化并在新实例中生效")

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
