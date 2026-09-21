"""程序更新提示消息测试（无网络）。

覆盖：
- 只发给「直播间已启用且正在开播」的账户，其余（未绑定 / 未启用 / 未开播 / 已过期）跳过
- 「更新前」提示等消息队列真正排空后才返回（否则重启会把它掐掉）
- 重启后的「更新完成」提示靠 update_state.json 的待发标记驱动，且只发一次
- 标记可撤销、普通重启不会误发、空文案不误发
- 单账户发送失败不阻断其余账户
- 消息长度裁剪

运行： .venv/Scripts/python.exe test/test_update_notify.py

注意：所有 await 都必须在同一个事件循环里 —— asyncio 的 Lock/Event 一旦
在某个循环里用过就绑定到它，跨循环使用会直接 RuntimeError。
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

_DATA = tempfile.mkdtemp(prefix="mismiss-update-notify-")
os.environ["MISMISS_DATA_DIR"] = _DATA

# update 配置写在项目根 config.yml（不能用 MISMISS_DATA_DIR 隔离），
# 测完必须原样还回去 —— 否则会污染开发机上的真实配置。
# 用 atexit 而非 try/finally：断言中途抛异常时同样能还原。
import atexit  # noqa: E402

_CONFIG = Path(_ROOT) / "config.yml"
_CONFIG_BACKUP = _CONFIG.read_bytes() if _CONFIG.exists() else None


def _restore_config() -> None:
    if _CONFIG_BACKUP is not None:
        _CONFIG.write_bytes(_CONFIG_BACKUP)
    else:
        _CONFIG.unlink(missing_ok=True)


atexit.register(_restore_config)

from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402
from api.deps import get_account_manager  # noqa: E402
from api.routes import update as upd  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


# ---------------------------------------------------------------- #
# 打桩：拦下真实发消息请求，只记录「发到哪个房间、内容是什么」
# ---------------------------------------------------------------- #

SENT: list[tuple[int, str]] = []


class _FakeSendAPI:
    """替身只做到「调用成功」：_check_success 认的是顶层 code == 0。"""

    def __init__(self, cookie: str) -> None:
        self._cookie = cookie

    async def api(self, live_id: int, message: str) -> dict:
        SENT.append((live_id, message))
        return {"code": 0}


import core.bot.mis_bot as _mis_bot  # noqa: E402

_mis_bot.MessageSendAPI = _FakeSendAPI  # type: ignore[assignment]


def _fake_room(lid: int, *, enabled: bool, streaming: bool) -> SimpleNamespace:
    """最小直播间替身：_notify_livestreams 只用 enabled / is_streaming / bot / send_message。"""
    room = SimpleNamespace(live_id=lid, enabled=enabled, is_streaming=streaming, bot=None)

    async def send_message(message: str, priority: int = 0) -> None:
        await room.bot.send_livestream_message(lid, message, priority)

    room.send_message = send_message
    return room


def _set_notify(enabled: bool, before: str, after: str) -> None:
    """绕过 HTTP 直接改配置（HTTP 那条路径单独用接口验证）。"""
    cfg = upd._update_config()
    upd._save_update_config(
        cfg["repo"], cfg["mirror"], cfg["proxy"], enabled, before, after,
    )


async def _async_checks(mgr) -> None:
    """全部异步断言 —— 必须共用一个事件循环。"""
    # ---- 关闭时：一条都不发 ----
    _set_notify(False, "即将更新", "已更新完成")
    SENT.clear()
    await upd.notify_before_update(mgr)
    check("未开启时发送 0 条", len(SENT) == 0, f"sent={len(SENT)}")

    # ---- 更新前提示：只有 A 收到 ----
    _set_notify(True, "即将更新", "已更新完成")
    SENT.clear()
    await upd.notify_before_update(mgr)
    check("更新前提示只发给开播且已启用的直播间",
          SENT == [(710001, "即将更新")], f"sent={SENT}")

    # ---- 队列排空语义：入队即返回，等待要真的等到发完 ----
    bot = _mis_bot.MissevanBot("cookie", timer_interval=120.0)
    bot._id, bot._name, bot._initialized = 1, "stub", True
    SENT.clear()
    await bot.send_livestream_message(720001, "第一条")
    await bot.send_livestream_message(720001, "第二条")
    ok = await bot.wait_message_queue_idle(timeout=10.0)
    check("等待队列排空返回 True", ok is True, f"ok={ok}")
    check("排空后队列为空", len(bot._message_queue) == 0,
          f"left={len(bot._message_queue)}")
    check("排空的等待覆盖了队列里的每一条",
          [m for _, m in SENT] == ["第一条", "第二条"], f"sent={SENT}")

    # ---- 重启后的补发 ----
    check("初始无待发标记", upd._load_update_state().get("notify_pending") is None,
          str(upd._load_update_state()))

    upd._mark_notify_pending("1.3.1", "已更新完成")
    check("标记已写入",
          upd._load_update_state().get("notify_pending")
          == {"version": "1.3.1", "message": "已更新完成"},
          str(upd._load_update_state()))

    SENT.clear()
    await upd.notify_after_update(mgr)
    check("重启后补发只发给开播且已启用的直播间",
          SENT == [(710001, "已更新完成")], f"sent={SENT}")
    check("补发后标记被清除", upd._load_update_state().get("notify_pending") is None,
          str(upd._load_update_state()))

    # ---- 只生效一次 / 无标记不发 / 空文案不发 ----
    SENT.clear()
    await upd.notify_after_update(mgr)
    check("普通重启（无标记）不发送", len(SENT) == 0, f"sent={len(SENT)}")

    upd._mark_notify_pending("1.3.2", "   ")
    SENT.clear()
    await upd.notify_after_update(mgr)
    check("空文案不发且标记仍被清除",
          len(SENT) == 0 and upd._load_update_state().get("notify_pending") is None,
          f"sent={len(SENT)} state={upd._load_update_state()}")

    # ---- 单账户发送失败不阻断整体 ----
    a_room = mgr.get_server(1).livestreams[710001]

    async def _boom(message: str, priority: int = 0) -> None:
        raise RuntimeError("发送炸了")

    good_send = a_room.send_message
    a_room.send_message = _boom
    upd._mark_notify_pending("1.3.3", "容错测试")
    await upd.notify_after_update(mgr)
    check("单账户发送失败不阻断整体流程（标记仍被清除）",
          upd._load_update_state().get("notify_pending") is None,
          str(upd._load_update_state()))
    a_room.send_message = good_send


with TestClient(app) as c:
    token = c.post(
        "/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"},
    ).json()["token"]
    H = {"Authorization": f"Bearer {token}"}
    mgr = get_account_manager()

    def mk_account(name: str, uname: str, live_id: int, *, enabled: bool,
                   streaming: bool, days: int = 30, with_room: bool = True):
        r = c.post("/api/panel/accounts", headers=H, json={
            "name": name, "bot_mode": "private", "cookie": "",
            "username": uname, "password": "pw123456", "duration_days": days,
        })
        s = mgr.get_server(r.json()["id"])
        # 桩掉 Bot（避免联网校验 Cookie），并让其可用
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

    # A：已启用 + 开播中 → 应收到；B：未开播 → 跳过
    # C：未启用（即使人在播）→ 跳过；D：未绑定 → 跳过；E：已过期 → 跳过
    mk_account("A-开播", "notifyA", 710001, enabled=True, streaming=True)
    mk_account("B-未开播", "notifyB", 710002, enabled=True, streaming=False)
    mk_account("C-未启用", "notifyC", 710003, enabled=False, streaming=True)
    mk_account("D-未绑定", "notifyD", 0, enabled=False, streaming=False,
               with_room=False)
    e_srv = mk_account("E-已过期", "notifyE", 710005,
                       enabled=True, streaming=True, days=1)
    e_srv.account_record.expires_at = "2000-01-01T00:00:00"

    # 打桩掉异步 Bot 恢复（真实实现要联网）
    async def _noop_restore() -> None:
        return None

    for aid in (1, 5):
        mgr.get_server(aid)._ensure_bot_restored = _noop_restore  # type: ignore[method-assign]

    # ---- 消息裁剪 ----
    raw = "  a   b\n" + "x" * 200
    check("消息裁剪：压掉多余空白并截断到上限",
          upd._clip(raw) == ("a b " + "x" * 200)[:upd._NOTIFY_MAX_LEN]
          and len(upd._clip(raw)) == upd._NOTIFY_MAX_LEN,
          repr(upd._clip(raw)))
    check("空白消息裁剪后为空", upd._clip("  \n\t ") == "", repr(upd._clip("  \n\t ")))

    # ---- 接口契约：默认值 + 保存往返 ----
    info = c.get("/api/update/info", headers=H).json()
    check("默认关闭更新提示", info["notify_enabled"] is False,
          str(info["notify_enabled"]))
    check("默认文案非空", bool(info["notify_before"]) and bool(info["notify_after"]),
          f"{info['notify_before']!r} / {info['notify_after']!r}")
    check("接口返回字符上限", isinstance(info.get("notify_max_len"), int)
          and info["notify_max_len"] > 0, str(info.get("notify_max_len")))

    r = c.post("/api/update/settings", headers=H, json={
        "repo": info["repo"], "mirror": "", "proxy": "",
        "notify_enabled": True,
        "notify_before": "  即将更新  ",
        "notify_after": "已更新完成",
    })
    check("保存更新提示设置", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
    cfg = upd._update_config()
    check("设置已持久化且入库前被裁剪",
          cfg["notify_enabled"] and cfg["notify_before"] == "即将更新"
          and cfg["notify_after"] == "已更新完成", str(cfg))

    # ---- 待发标记与备份信息互不覆盖 ----
    upd._save_update_state({"backup_dir": "/tmp/bak", "backup_version": "1.3.0"})
    upd._mark_notify_pending("1.3.4", "再来一条")
    st = upd._load_update_state()
    check("待发标记与备份信息互不覆盖",
          st.get("backup_dir") == "/tmp/bak"
          and st.get("backup_version") == "1.3.0"
          and st.get("notify_pending", {}).get("version") == "1.3.4",
          json.dumps(st, ensure_ascii=False))

    upd._mark_notify_pending("1.3.5", "待撤销")
    upd._clear_notify_pending()
    check("_clear_notify_pending 可撤销标记",
          upd._load_update_state().get("notify_pending") is None,
          str(upd._load_update_state()))

    # ---- 全部异步断言（同一事件循环） ----
    asyncio.run(_async_checks(mgr))

# ---------------------------------------------------------------- #

_restore_config()
check("项目根 config.yml 已还原",
      _CONFIG.read_bytes() == _CONFIG_BACKUP if _CONFIG_BACKUP else not _CONFIG.exists(),
      "测试污染了真实配置文件")

passed = sum(1 for _, ok, _ in res if ok)
for i, (name, ok, detail) in enumerate(res, 1):
    print(f"{'PASS' if ok else 'FAIL'} {i}: {name}" + (f"  [{detail}]" if not ok else ""))
print(f"\n{passed}/{len(res)} 通过")
sys.exit(0 if passed == len(res) else 1)
