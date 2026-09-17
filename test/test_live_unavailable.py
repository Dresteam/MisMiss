"""已绑定直播间加载失败(不存在/封禁/注销)场景测试(无网络)。

背景:``GET /live/`` 对「从未绑定」与「绑了但加载不出来」都返回 ``null``,
前端若只看它就会把后者当成未绑定、给出绑定输入框,用户看不出绑定还在。
区分依据是账户记录里的 ``room_id``——本测试锁住这一点,以及随之而来的
「同 ID 重试加载」入口。

运行: .venv/Scripts/python.exe test/test_live_unavailable.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(prefix="mismiss-live-na-")

from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402
from api.deps import get_account_manager  # noqa: E402

ROOM = 555001
res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


def _fake_live(lid: int) -> SimpleNamespace:
    """足够 _live_to_info 取用的最小直播间替身。"""
    return SimpleNamespace(
        live_id=lid, room_name="测试直播间", room_description="",
        score=0, online_count=0, creator_name="主播", creator_id=1,
        is_connected=False, enabled=False, medal=None,
        cover_url="", is_streaming=False,
    )


with TestClient(app) as c:
    token = c.post(
        "/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"},
    ).json()["token"]
    H = {"Authorization": f"Bearer {token}"}

    aid = c.post("/api/panel/accounts", headers=H, json={
        "name": "live-na", "bot_mode": "private", "cookie": "",
        "username": "livena", "password": "pw12", "duration_days": 30,
    }).json()["id"]

    s = get_account_manager().get_server(aid)
    s._bot._id = 1
    s._bot._name = "stub"
    s._bot._initialized = True
    s._bot_available = True
    s._bot.enabled = True

    # 桩掉真实房间加载（_refresh 需联网）
    async def _add(lid: int):
        live = _fake_live(lid)
        s._livestreams[lid] = live
        return live

    async def _remove(lid: int):
        if lid not in s._livestreams:
            raise KeyError(lid)
        del s._livestreams[lid]

    s.add_livestream = _add          # type: ignore[method-assign]
    s.remove_livestream = _remove    # type: ignore[method-assign]

    def summary():
        ov = c.get("/api/panel/overview", headers=H).json()
        return next(a for a in ov["accounts"] if a["id"] == aid)

    def live_get():
        return c.get(f"/api/accounts/{aid}/live/", headers=H)

    # ---- 1. 未绑定时：room_id 为空、live 返回 null ----
    check("未绑定：live 返回 null", live_get().status_code == 200 and live_get().json() is None,
          f"{live_get().status_code} {live_get().text[:80]}")
    check("未绑定：账户记录 room_id 为空", summary()["room_id"] is None,
          f"{summary()['room_id']}")

    # 先正常绑定一次
    r = c.post(f"/api/accounts/{aid}/live/add", headers=H, json={"live_id": ROOM})
    check("绑定直播间成功", r.status_code == 200, f"{r.status_code} {r.text[:100]}")

    # ---- 2. 模拟房间加载失败：记录里 room_id 还在，但 livestream 实例没了 ----
    del s._livestreams[ROOM]
    check("加载失败：live 返回 null（接口契约不变）", live_get().json() is None,
          f"{live_get().text[:80]}")
    check("加载失败：账户记录仍保留 room_id（前端据此区分）",
          summary()["room_id"] == ROOM, f"{summary()['room_id']}")

    # ---- 3. 同 ID 重试加载应放行，且不能把刚加回来的房间又删掉 ----
    r = c.post(f"/api/accounts/{aid}/live/add", headers=H, json={"live_id": ROOM})
    check("同 ID 重试加载放行", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    check("重试后直播间已回到内存（未被自删）",
          ROOM in s._livestreams, f"{list(s._livestreams.keys())}")
    check("重试后 live 接口恢复返回房间信息",
          (live_get().json() or {}).get("live_id") == ROOM, f"{live_get().text[:80]}")

    # ---- 4. 房间健康时，重复绑定同 ID 仍应被拒绝 ----
    r = c.post(f"/api/accounts/{aid}/live/add", headers=H, json={"live_id": ROOM})
    check("房间正常时重复绑定同 ID → 400", r.status_code == 400, f"{r.status_code} {r.text[:100]}")

    # ---- 5. 更换到别的房间仍能正常替换旧房间 ----
    OTHER = 555002
    r = c.post(f"/api/accounts/{aid}/live/add", headers=H, json={"live_id": OTHER})
    check("更换到新直播间成功", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
    check("旧直播间已移除", ROOM not in s._livestreams, f"{list(s._livestreams.keys())}")
    check("账户记录已指向新直播间", summary()["room_id"] == OTHER, f"{summary()['room_id']}")

for name, ok, detail in res:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   [{detail}]"))
print("---")
print("全部通过" if all(r[1] for r in res) else "存在失败项")
