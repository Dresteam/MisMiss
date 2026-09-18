"""跨房事件(连麦 / 大厅)分发测试(无网络)。

核心断言是「分离」:跨房包必须只触达跨房事件,不得漏进本房的
LiveMessageEvent / LiveGiftEvent——否则监听本房弹幕的指令类插件会被
对方直播间的弹幕触发,礼物插件会把别人的礼物算进本房。

运行: .venv/Scripts/python.exe test/test_cross_events.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.events.bus import EventBus  # noqa: E402
from core.livestream.handler import Live  # noqa: E402
from interfaces.event import event_handler  # noqa: E402
from interfaces.event.listener import Listener  # noqa: E402
from interfaces.event.livestream import (  # noqa: E402
    LiveMessageEvent,
    LiveGiftEvent,
    LiveCrossEvent,
    LiveCrossMessageEvent,
    LiveCrossGiftEvent,
    LivestreamUserEvent,
)

# 用户提供的真实 gift:cross_send 样本
CROSS_GIFT_PACKET = {
    "type": "gift", "event": "cross_send", "room_id": 869222866,
    "user": {
        "user_id": 38214227, "username": "_莓柿",
        "iconurl": "https://static.maoercdn.com/avatars/202609/14/c7fd.png",
        "titles": [{"type": "level", "level": 8}],
    },
    "room": {
        "room_id": 869224364, "creator_id": 38189528, "creator_username": "s_晴天",
        "creator_iconurl": "https://static.maoercdn.com/avatars/202609/15/837e.png",
    },
    "time": 1789535675323,
    "gift": {
        "gift_id": 10244, "name": "喵卡龙",
        "icon_url": "https://static.maoercdn.com/live/gifts/icons/10244.png",
        "price": 1, "num": 1,
    },
    "combo": {"id": "6aaa25bb9046a8d5a89f5ed6", "num": 1, "remain_time": 5000},
    "traces": '{"gift_trace_id":"d764602c-077a-4e60-95a8-1b92c88291f1"}',
}

# 用户提供的真实跨房**幸运**礼物样本 —— 携带 lucky 字段。
# 上面那份样本没有 lucky，只是因为那份礼物（喵卡龙）本就不是幸运礼物，
# 并非跨房包结构上不含该字段——曾据此把 gift_lucky 写死为 None，属误判。
CROSS_GIFT_LUCKY_PACKET = {
    "type": "gift", "event": "cross_send", "room_id": 869222866,
    "user": {
        "user_id": 24797403, "username": "TexasTheDrest",
        "iconurl": "https://static.maoercdn.com/avatars/202601/03/8b68.png",
        "titles": [{"type": "level", "level": 36}],
    },
    "room": {
        "room_id": 869224371, "creator_id": 38189986, "creator_username": "S_比达",
        "creator_iconurl": "https://static.maoercdn.com/avatars/202609/14/877e.png",
    },
    "time": 1789709377173,
    "gift": {
        "gift_id": 92342, "name": "汉堡包",
        "icon_url": "https://static.maoercdn.com/live/gifts/icons/10128.png",
        "price": 1, "num": 1,
    },
    "lucky": {
        "gift_id": 80165, "name": "秋韵宝藏",
        "icon_url": "https://static.maoercdn.com/live/gifts/icons/80165.png",
        "price": 10, "num": 1,
    },
    "traces": '{"gift_trace_id":"f75680e9-94da-4b67-8a3f-615bd09e4d06"}',
}

# message:cross_new 暂无真实样本，按其与 cross_send 同构（携带 room）构造
CROSS_MSG_PACKET = {
    "type": "message", "event": "cross_new", "room_id": 869222866,
    "user": {"user_id": 38214227, "username": "_莓柿", "iconurl": None, "titles": []},
    "room": {
        "room_id": 869224364, "creator_id": 38189528,
        "creator_username": "s_晴天", "creator_iconurl": "https://x/y.png",
    },
    "message": "对面直播间的弹幕",
}

PLAIN_MSG_PACKET = {
    "type": "message", "event": "new", "room_id": 869222866,
    "user": {"user_id": 7, "username": "本房观众", "iconurl": None, "titles": []},
    "message": "本房弹幕",
}

PLAIN_GIFT_PACKET = {
    "type": "gift", "event": "send", "room_id": 869222866,
    "user": {"user_id": 8, "username": "本房观众", "iconurl": None, "titles": []},
    "gift": {"gift_id": 1, "name": "本房礼物", "price": 10, "num": 2},
}


class Recorder(Listener):
    """同时监听本房、跨房与父类事件，用于验证分发边界。"""

    def __init__(self) -> None:
        self.msg: list = []
        self.gift: list = []
        self.cross_msg: list = []
        self.cross_gift: list = []
        self.user_events: list = []

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        self.msg.append(event)

    @event_handler
    def on_gift(self, event: LiveGiftEvent) -> None:
        self.gift.append(event)

    @event_handler
    def on_cross_message(self, event: LiveCrossMessageEvent) -> None:
        self.cross_msg.append(event)

    @event_handler
    def on_cross_gift(self, event: LiveCrossGiftEvent) -> None:
        self.cross_gift.append(event)

    @event_handler
    def on_any_user_event(self, event: LivestreamUserEvent) -> None:
        self.user_events.append(event)


class CrossGroupProbe(Listener):
    """只监听跨房分组基类：应收下全部跨房事件，且收不到任何本房事件。"""

    def __init__(self) -> None:
        self.events: list = []

    @event_handler
    def on_cross(self, event: LiveCrossEvent) -> None:
        self.events.append(event)


def _make_live(bus: EventBus) -> Live:
    fake = SimpleNamespace(
        live_id=869222866,
        creator_id=999,          # 与包内 user_id 不同 → 不会被判成主播
        get_admin_list=lambda: [],
        event_bus=bus,
    )
    return Live(fake)


async def main() -> None:
    res: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        res.append((name, cond, detail))

    bus = EventBus()
    rec = Recorder()
    cross_probe = CrossGroupProbe()
    bus.register_new_event(rec)
    bus.register_new_event(cross_probe)
    live = _make_live(bus)

    # ---- 1. 跨房弹幕 → 只进跨房事件 ----
    await live.on_message(dict(CROSS_MSG_PACKET))
    check("cross_new 触达 LiveCrossMessageEvent", len(rec.cross_msg) == 1, f"{len(rec.cross_msg)}")
    check("cross_new 不泄漏进 LiveMessageEvent", len(rec.msg) == 0, f"{len(rec.msg)}")

    # ---- 2. 跨房礼物 → 只进跨房事件 ----
    await live.on_message(dict(CROSS_GIFT_PACKET))
    check("cross_send 触达 LiveCrossGiftEvent", len(rec.cross_gift) == 1, f"{len(rec.cross_gift)}")
    check("cross_send 不泄漏进 LiveGiftEvent", len(rec.gift) == 0, f"{len(rec.gift)}")

    # ---- 3. 本房事件不受影响（回归） ----
    await live.on_message(dict(PLAIN_MSG_PACKET))
    await live.on_message(dict(PLAIN_GIFT_PACKET))
    check("本房 message:new 仍进 LiveMessageEvent", len(rec.msg) == 1, f"{len(rec.msg)}")
    check("本房 gift:send 仍进 LiveGiftEvent", len(rec.gift) == 1, f"{len(rec.gift)}")
    check("本房事件不进跨房事件", len(rec.cross_msg) == 1 and len(rec.cross_gift) == 1,
          f"{len(rec.cross_msg)}/{len(rec.cross_gift)}")

    # ---- 4. 对方直播间字段解析 ----
    # 弹幕用 origin_*（对方是来源），礼物用 target_*（对方是去向）
    cg = rec.cross_gift[0]
    check("跨房礼物:受赠直播间 ID", cg.target_room_id == 869224364, f"{cg.target_room_id}")
    check("跨房礼物:受赠主播 ID", cg.target_creator_id == 38189528, f"{cg.target_creator_id}")
    check("跨房礼物:受赠主播昵称", cg.target_creator_name == "s_晴天", f"{cg.target_creator_name!r}")
    check("跨房礼物:受赠主播头像", (cg.target_creator_icon or "").startswith("https://"),
          f"{cg.target_creator_icon!r}")
    check("跨房礼物:礼物与送礼人",
          cg.gift.name == "喵卡龙" and cg.gift.num == 1 and cg.user.name == "_莓柿",
          f"{cg.gift.name}/{cg.user.name}")
    check("跨房礼物:gift_num 便捷属性", cg.gift_num == 1, f"{cg.gift_num}")
    check("跨房礼物:不再有 origin_* 字段（方向语义不混用）",
          not hasattr(cg, "origin_creator_name") and not hasattr(cg, "origin_room_id"))

    # ---- 4b. 跨房幸运礼物：必须解析 lucky ----
    # 曾长期把 gift_lucky 写死为 None（注释误以为跨房包不携带 lucky），
    # 导致跨房幸运礼物对幸运值榜单零贡献。此用例锁定正确行为。
    await live.on_message(dict(CROSS_GIFT_LUCKY_PACKET))
    cgl = rec.cross_gift[-1]
    check("跨房幸运礼物:is_lucky_gift 为真", cgl.gift.is_lucky_gift is True,
          f"{cgl.gift.is_lucky_gift}")
    check("跨房幸运礼物:lucky_gift 已解析",
          cgl.gift.lucky_gift is not None and cgl.gift.lucky_gift.name == "秋韵宝藏",
          f"{getattr(cgl.gift.lucky_gift, 'name', None)!r}")
    check("跨房幸运礼物:幸运原价 = lucky.price × num",
          cgl.gift.lucky_gift is not None
          and cgl.gift.lucky_gift.price * cgl.gift.lucky_gift.num == 10,
          f"{getattr(cgl.gift.lucky_gift, 'price', 0)}")
    check("跨房幸运礼物:标注不受影响", cgl.target_creator_name == "S_比达",
          f"{cgl.target_creator_name!r}")

    cm = rec.cross_msg[0]
    check("跨房弹幕:内容与来源",
          cm.message == "对面直播间的弹幕" and cm.origin_room_id == 869224364
          and cm.origin_creator_name == "s_晴天",
          f"{cm.message!r}/{cm.origin_room_id}")
    check("跨房弹幕:保留 origin_* 字段（对方是来源）",
          hasattr(cm, "origin_creator_name") and not hasattr(cm, "target_creator_name"))

    # ---- 5. 监听父类的插件两者都能收到 ----
    check("监听 LivestreamUserEvent 可收到全部 5 类用户事件",
          len(rec.user_events) == 5, f"{len(rec.user_events)}")

    # ---- 6. 包内缺 room 字段时按未知处理，不抛异常 ----
    bare = {k: v for k, v in CROSS_MSG_PACKET.items() if k != "room"}
    await live.on_message(bare)
    check("缺 room 字段不抛异常且按未知处理",
          len(rec.cross_msg) == 2 and rec.cross_msg[1].origin_room_id == 0
          and rec.cross_msg[1].origin_creator_name == "",
          f"{len(rec.cross_msg)}/{rec.cross_msg[-1].origin_room_id}")

    # ---- 7. 跨房分组基类：一个 handler 收全部跨房事件，且不漏本房 ----
    # 到此处共发出 4 个跨房包（2 弹幕 + 2 礼物）与 2 个本房包（弹幕 + 礼物）
    check("监听 LiveCrossEvent 收下全部跨房事件(2 弹幕 + 2 礼物)",
          len(cross_probe.events) == 4, f"{len(cross_probe.events)}")
    check("监听 LiveCrossEvent 收不到本房事件",
          all(isinstance(e, LiveCrossEvent) for e in cross_probe.events),
          f"{[type(e).__name__ for e in cross_probe.events]}")

    # ---- 8. 事件类型确非父子关系（分离的根据） ----
    check("LiveCrossMessageEvent 不是 LiveMessageEvent 的子类",
          not issubclass(LiveCrossMessageEvent, LiveMessageEvent))
    check("LiveCrossGiftEvent 不是 LiveGiftEvent 的子类",
          not issubclass(LiveCrossGiftEvent, LiveGiftEvent))
    check("两者都继承自 LiveCrossEvent",
          issubclass(LiveCrossMessageEvent, LiveCrossEvent)
          and issubclass(LiveCrossGiftEvent, LiveCrossEvent))
    check("LiveCrossEvent 继承自 LivestreamUserEvent",
          issubclass(LiveCrossEvent, LivestreamUserEvent))

    for name, ok, detail in res:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   [{detail}]"))
    print("---")
    print("全部通过" if all(r[1] for r in res) else "存在失败项")


if __name__ == "__main__":
    asyncio.run(main())
