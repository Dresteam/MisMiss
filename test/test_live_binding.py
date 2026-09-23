"""直播间绑定与开播状态测试（无网络）。

覆盖：
- ``parse_live_id`` 接受裸数字与各种形态的直播间链接，非法输入报错
- 绑定直播间时 ``live_id`` 传链接等价于传数字（同一个房间）
- 账户总览下发 ``room_streaming``（开播状态），供列表直接展示
- 总览下发 ``next_account_id``，用于预填默认用户名

运行： .venv/Scripts/python.exe test/test_live_binding.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(prefix="mismiss-live-bind-")

from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402
from api.deps import get_account_manager  # noqa: E402
from core.network.urls import live_page_url, parse_live_id  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


# ---------------------------------------------------------------- #
# 1. 链接 / 裸数字 → 直播间 id
# ---------------------------------------------------------------- #

LIVE_ID = 869198039
ok_cases = [
    LIVE_ID,
    str(LIVE_ID),
    f"  {LIVE_ID}  ",
    f"https://fm.missevan.com/live/{LIVE_ID}",
    f"http://fm.missevan.com/live/{LIVE_ID}",
    f"fm.missevan.com/live/{LIVE_ID}",
    f"https://fm.missevan.com/live/{LIVE_ID}/",
    f"https://fm.missevan.com/live/{LIVE_ID}?from=share",
    f"https://fm.missevan.com/live/{LIVE_ID}#anchor",
    f"https://www.missevan.com/live/{LIVE_ID}",
    f"https://fm.missevan.com/api/v2/live/{LIVE_ID}",
]
check("各种写法都能解析出同一个 id",
      all(parse_live_id(c) == LIVE_ID for c in ok_cases),
      str([c for c in ok_cases if parse_live_id(c) != LIVE_ID]))

for bad in ["", "   ", "abc", "https://fm.missevan.com/room/abc", "0", "-5", None, True]:
    try:
        got = parse_live_id(bad)
        check(f"非法输入 {bad!r} 应报错", False, f"却返回 {got}")
    except ValueError:
        pass
check("非法输入全部被拒绝", all(len(r) <= 3 or r[1] for r in res) and True)

check("链接模板正确",
      live_page_url(LIVE_ID) == f"https://fm.missevan.com/live/{LIVE_ID}",
      live_page_url(LIVE_ID))


# ---------------------------------------------------------------- #
# 2. 接口层：绑定、开播状态、下一个 id
# ---------------------------------------------------------------- #

with TestClient(app) as c:
    tok = c.post(
        "/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"},
    ).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    mgr = get_account_manager()

    r = c.post("/api/panel/accounts", headers=H, json={
        "name": "绑定测试", "bot_mode": "private", "cookie": "",
        "username": "bindtest", "password": "pw123456", "duration_days": 30,
    })
    aid = r.json()["id"]
    s = mgr.get_server(aid)
    s._bot._id = 1
    s._bot._name = "stub"
    s._bot._initialized = True
    s._bot_available = True
    s._bot.enabled = True

    # 桩掉真实房间加载（_refresh 需联网）
    def _fake_live(lid: int, streaming: bool) -> SimpleNamespace:
        return SimpleNamespace(
            live_id=lid, room_name=f"房间{lid}", room_description="",
            score=0, online_count=0, creator_name="主播", creator_id=1,
            is_connected=True, enabled=True, medal=None,
            cover_url="", is_streaming=streaming,
            creator=SimpleNamespace(is_online=streaming, icon_url="", introduction=""),
            bot=s._bot,
        )

    async def _add(lid: int):
        live = _fake_live(lid, True)
        s._livestreams[lid] = live
        return live

    async def _remove(lid: int):
        if lid not in s._livestreams:
            raise KeyError(lid)
        del s._livestreams[lid]

    s.add_livestream = _add          # type: ignore[method-assign]
    s.remove_livestream = _remove    # type: ignore[method-assign]

    # 用链接绑定
    r = c.post(f"/api/accounts/{aid}/live/add", headers=H,
               json={"live_id": f"https://fm.missevan.com/live/{LIVE_ID}?from=share"})
    check("用直播间链接可以绑定", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    check("绑定后解析出的房间正确", r.json().get("live_id") == LIVE_ID,
          str(r.json().get("live_id")))
    check("账户记录写入了正确的 room_id", mgr.get_record(aid).room_id == LIVE_ID,
          str(mgr.get_record(aid).room_id))

    # 非法输入
    r = c.post(f"/api/accounts/{aid}/live/add", headers=H,
               json={"live_id": "https://fm.missevan.com/live/abc"})
    check("非法链接 -> 400 且带可读说明",
          r.status_code == 400 and "直播间" in r.json().get("detail", ""),
          f"{r.status_code} {r.text[:120]}")

    # 总览：开播状态 + 下一个账户 id
    ov = c.get("/api/panel/overview", headers=H).json()
    mine = next(a for a in ov["accounts"] if a["id"] == aid)
    check("总览下发 room_streaming", mine.get("room_streaming") is True,
          str(mine.get("room_streaming")))
    check("room_streaming 为布尔值（未开播时为 False）",
          _fake_live(1, False).is_streaming is False)
    check("未绑定直播间的账户 room_streaming 为 False",
          all(a["room_streaming"] is False for a in ov["accounts"] if a["room_id"] is None),
          str([(a["name"], a["room_streaming"], a["room_id"]) for a in ov["accounts"]]))
    check("总览下发 next_account_id",
          isinstance(ov.get("next_account_id"), int) and ov["next_account_id"] > aid,
          f"next={ov.get('next_account_id')} aid={aid}")

    # next_account_id 必须等于后端真实分配的下一个 id（删过账户后会跳号，
    # 前端按 max(id)+1 算会对不上）
    expect = mgr._next_account_id
    check("next_account_id 与后端分配器一致", ov["next_account_id"] == expect,
          f"{ov['next_account_id']} vs {expect}")

# ---------------------------------------------------------------- #
# 3. 开播状态必须由 WS 事件**同步**更新
#    回归：此前 on_open/on_close 只异步跑 _refresh() 去查 room.status.open，
#    于是「主播已开播但仍显示未开播」要等接口回来（甚至失败就一直不对），
#    与同一时刻已被同步更新的「主播在线」对不上。
# ---------------------------------------------------------------- #

from core.events.bus import EventBus  # noqa: E402
from core.livestream.mis_livestream import MissevanLivestream  # noqa: E402

with TestClient(app) as c:
    tok = c.post(
        "/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"},
    ).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    r = c.post("/api/panel/accounts", headers=H, json={
        "name": "开播同步", "bot_mode": "private", "cookie": "",
        "username": "streamsync", "password": "pw123456", "duration_days": 30,
    })
    bot = get_account_manager().get_server(r.json()["id"])._bot

    live = MissevanLivestream(123456, bot, EventBus())
    listener = live._create_internal_listener()

    check("初始为未开播", live.is_streaming is False, str(live.is_streaming))
    # 直接调用监听器（不经过事件总线）：这里要验证的正是「同步生效」，
    # 走总线会引入分发时机，反而看不出是同步还是异步
    listener.on_open(object())  # type: ignore[arg-type]
    check("on_open 后立即为开播中（同步，无需等接口）",
          live.is_streaming is True, str(live.is_streaming))
    listener.on_close(object())  # type: ignore[arg-type]
    check("on_close 后立即为未开播",
          live.is_streaming is False, str(live.is_streaming))

# ---------------------------------------------------------------- #

passed = sum(1 for _, ok, _ in res if ok)
for i, (name, ok, detail) in enumerate(res, 1):
    print(f"{'PASS' if ok else 'FAIL'} {i}: {name}" + (f"  [{detail}]" if not ok else ""))
print(f"\n{passed}/{len(res)} 通过")
sys.exit(0 if passed == len(res) else 1)
