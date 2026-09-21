"""面板「全局消息」接口测试（无网络）。

覆盖：
- POST /api/server/broadcast 只发给「已启用且正在开播」的直播间
- 未绑定 / 未启用 / 未开播 / 已过期的账户被跳过，且不计入失败
- 空消息 / 纯空白 → 400，不会误发
- 超长消息被裁剪到上限（与更新提示共用同一上限）
- 单账户发送失败不影响其余账户，结果里记为失败
- /api/server/status 下发字符上限，供前端限制输入框

运行： .venv/Scripts/python.exe test/test_server_broadcast.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(prefix="mismiss-broadcast-")

from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402
from api.deps import get_account_manager  # noqa: E402
from core.account import BROADCAST_MAX_LEN, clip_broadcast  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


SENT: list[tuple[int, str]] = []


class _FakeSendAPI:
    """替身只需让 _check_success 通过：顶层 code == 0。"""

    def __init__(self, cookie: str) -> None:
        self._cookie = cookie

    async def api(self, live_id: int, message: str) -> dict:
        SENT.append((live_id, message))
        return {"code": 0}


import core.bot.mis_bot as _mis_bot  # noqa: E402

_mis_bot.MessageSendAPI = _FakeSendAPI  # type: ignore[assignment]


def _fake_room(lid: int, *, enabled: bool, streaming: bool) -> SimpleNamespace:
    # 字段需覆盖两处消费方：广播只读 enabled / is_streaming / bot，
    # 而 manager.overview() 的快照还读 is_connected / room_name
    room = SimpleNamespace(
        live_id=lid, room_name=f"房间{lid}", enabled=enabled,
        is_streaming=streaming, is_connected=enabled, bot=None,
    )

    async def send_message(message: str, priority: int = 0) -> None:
        await room.bot.send_livestream_message(lid, message, priority)

    room.send_message = send_message
    return room


with TestClient(app) as c:
    tok = c.post(
        "/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"},
    ).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    mgr = get_account_manager()

    def mk_account(name: str, uname: str, live_id: int, *, enabled: bool,
                   streaming: bool, days: int = 30, with_room: bool = True):
        r = c.post("/api/panel/accounts", headers=H, json={
            "name": name, "bot_mode": "private", "cookie": "",
            "username": uname, "password": "pw123456", "duration_days": days,
        })
        s = mgr.get_server(r.json()["id"])
        s._bot._id = 1
        s._bot._name = "stub"
        s._bot._initialized = True
        s._bot_available = True
        s._bot.enabled = True
        if with_room:
            s.account_record.room_id = live_id
            room = _fake_room(live_id, enabled=enabled, streaming=streaming)
            room.bot = s._bot
            s._livestreams[live_id] = room
        return s

    async def _noop_restore() -> None:
        return None

    # A：已启用 + 开播中 → 应收到
    a_srv = mk_account("A-开播", "bcA", 810001, enabled=True, streaming=True)
    # B：未开播 → 跳过
    mk_account("B-未开播", "bcB", 810002, enabled=True, streaming=False)
    # C：未启用 → 跳过
    mk_account("C-未启用", "bcC", 810003, enabled=False, streaming=True)
    # D：未绑定 → 跳过
    mk_account("D-未绑定", "bcD", 0, enabled=False, streaming=False, with_room=False)
    # E：已过期 → 跳过
    e_srv = mk_account("E-已过期", "bcE", 810005, enabled=True, streaming=True, days=1)
    # 带时区 —— days_left 拿它和 aware 的 utcnow 相减
    e_srv.account_record.expires_at = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()

    for aid in (1, 5):
        mgr.get_server(aid)._ensure_bot_restored = _noop_restore  # type: ignore[method-assign]

    def post(msg: str):
        return c.post("/api/server/broadcast", headers=H, json={"message": msg})

    # ---- 1. 参数校验 ----
    check("空消息 -> 400", post("").status_code == 400, str(post("").status_code))
    check("纯空白 -> 400", post("   \n\t ").status_code == 400,
          str(post("   ").status_code))
    check("缺 message 字段 -> 400", c.post(
        "/api/server/broadcast", headers=H, json={}).status_code == 400)
    check("未认证 -> 401", c.post(
        "/api/server/broadcast", json={"message": "x"}).status_code == 401)

    # ---- 2. 状态接口下发字符上限 ----
    st = c.get("/api/server/status", headers=H).json()
    check("status 下发 broadcast_max_len",
          st.get("broadcast_max_len") == BROADCAST_MAX_LEN,
          str(st.get("broadcast_max_len")))

    # ---- 3. 只发给开播且已启用的直播间 ----
    SENT.clear()
    r = post("全局公告")
    check("发送成功", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
    check("只有开播且已启用的直播间收到",
          SENT == [(810001, "全局公告")], f"sent={SENT}")
    body = r.json()
    check("结果里说明发送数", "1" in body["message"], body["message"])
    check("结果里说明跳过数（4 个账户被跳过）", "4" in body["message"], body["message"])

    # ---- 4. 消息裁剪 ----
    check("裁剪：压空白并截断",
          clip_broadcast("  a   b\n" + "x" * 200)
          == ("a b " + "x" * 200)[:BROADCAST_MAX_LEN],
          repr(clip_broadcast("  a   b\n" + "x" * 200)))
    SENT.clear()
    post("y" * 200)
    check("超长消息按上限截断后发出",
          SENT and len(SENT[0][1]) == BROADCAST_MAX_LEN, f"len={len(SENT[0][1]) if SENT else 0}")
    SENT.clear()
    post("  首尾有空白  ")
    check("首尾空白被去掉", SENT == [(810001, "首尾有空白")], f"sent={SENT}")

    # ---- 5. 单账户失败不影响其余账户 ----
    b_room = mgr.get_server(1).livestreams[810001]

    async def _boom(message: str, priority: int = 0) -> None:
        raise RuntimeError("发送炸了")

    good = b_room.send_message
    b_room.send_message = _boom
    SENT.clear()
    r = post("容错测试")
    check("发送失败仍返回 200 且不抛出", r.status_code == 200,
          f"{r.status_code} {r.text[:80]}")
    check("失败计入结果", "失败" in r.json()["message"], r.json()["message"])
    b_room.send_message = good

    # ---- 6. 没有可发送的直播间时给出明确提示 ----
    a_room = mgr.get_server(1).livestreams[810001]
    a_room.enabled = False
    try:
        r = post("无人接收")
        msg = r.json()["message"]
        check("无接收方时提示原因",
              r.status_code == 200 and "没有可发送" in msg, msg)
    finally:
        a_room.enabled = True

# ---------------------------------------------------------------- #

passed = sum(1 for _, ok, _ in res if ok)
for i, (name, ok, detail) in enumerate(res, 1):
    print(f"{'PASS' if ok else 'FAIL'} {i}: {name}" + (f"  [{detail}]" if not ok else ""))
print(f"\n{passed}/{len(res)} 通过")
sys.exit(0 if passed == len(res) else 1)
