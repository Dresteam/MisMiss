"""开播状态 / 主播在线状态 / WS 事件触发的刷新（无网络）。

两条规矩：

1. 「是否开播」与「主播在线」**不强制等价** —— 各取各的来源，谁也别顶替谁
   （主播可以在线而没开播）。
2. WS 收到开播/下播时**强制刷新一次**，由接口结果决定主播在线状态。

回归：`_refresh_soon()` 原先不带 force，会被 `_REFRESH_MIN_INTERVAL` 的 5 秒冷却
静默丢掉 —— 而开播/下播那一刻常与面板轮询、join 时的连调三次撞在一起，
表现就是「WS 明明收到了，状态却没跟着变」。

运行: .venv/Scripts/python.exe test/test_live_status.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.events.bus import EventBus  # noqa: E402
from core.livestream import mis_livestream as ML  # noqa: E402

ROOM = 869220320

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def _room_payload(*, open_: int, creator_online: bool | None, name: str) -> dict:
    """一份最小可用的房间信息响应。

    ``creator_online=None`` 表示接口**没给** online 字段。
    """
    creator: dict = {"user_id": 1, "username": "主播"}
    if creator_online is not None:
        creator["online"] = creator_online
    return {
        "code": 0,
        "info": {
            "room": {"name": name, "status": {"open": open_}},
            "creator": creator,
        },
    }


async def main() -> None:
    payloads: list[dict] = []

    class _StubRoomInfo:
        async def api(self, live_id: int) -> dict:  # noqa: ANN201
            return payloads.pop(0)

    class _StubMeta:
        async def api(self, live_id: int) -> dict:  # noqa: ANN201
            return {"code": 0, "info": {"members": {}}}

    ML.RoomInfoAPI = _StubRoomInfo  # type: ignore[assignment]
    ML.MetaAPI = _StubMeta  # type: ignore[assignment]

    live = ML.MissevanLivestream(ROOM, SimpleNamespace(), EventBus())

    # ---- 1. 正常：开播且在线 ----
    payloads.append(_room_payload(open_=1, creator_online=True, name="第一"))
    await live._refresh(force=True)
    check("开播：直播间状态为开播", live.is_streaming is True)
    check("开播：主播为在线", live.creator.is_online is True)

    # ---- 2. 开播但接口说主播不在线：如实照搬，不硬掰 ----
    payloads.append(_room_payload(open_=1, creator_online=False, name="第二"))
    await live._refresh(force=True)
    check("开播但接口说不在线 —— 照搬接口，不顶替成在线",
          live.is_streaming is True and live.creator.is_online is False,
          "两者不是一回事，谁也别顶替谁")

    # ---- 3. 未开播但接口说在线：同样照搬 ----
    payloads.append(_room_payload(open_=0, creator_online=True, name="第三"))
    await live._refresh(force=True)
    check("未开播但接口说在线 —— 同样照搬接口",
          live.is_streaming is False and live.creator.is_online is True)

    # ---- 4. 5 秒冷却：不 force 的刷新会被丢掉，force 才穿得过去 ----
    payloads.append(_room_payload(open_=0, creator_online=True, name="第四"))
    await live._refresh()  # 距上次刷新不足 _REFRESH_MIN_INTERVAL
    check("冷却期内不 force 的刷新被丢掉", live.room_name == "第三")
    check("那一次请求压根没发出去", len(payloads) == 1, f"还剩 {len(payloads)} 份桩数据")
    await live._refresh(force=True)
    check("force 能穿透冷却", live.room_name == "第四")

    # ---- 5. WS 开播：同步置开播 + 触发**强制**刷新，且不硬设在线 ----
    live.creator.set_online(False)  # 先摆成离线，看 WS 会不会硬掰
    calls: list[dict] = []
    live._refresh_soon = lambda **kw: calls.append(kw)  # type: ignore[method-assign]
    live._create_internal_listener().on_open(None)  # type: ignore[arg-type]

    check("WS 开播：立刻标记为开播", live.is_streaming is True)
    check("WS 开播：触发了刷新，且带 force",
          bool(calls) and calls[0].get("force") is True, f"拿到 {calls}")
    check("WS 开播：没有硬把主播设成在线", live.creator.is_online is False,
          "在线与否交给那次刷新按接口结果定")

    print(f"\n{_passed}/{_passed} 通过")


if __name__ == "__main__":
    asyncio.run(main())
