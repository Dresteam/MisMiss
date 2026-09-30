"""出站节流 / 全局退避 / 失败重试抑制测试(无外部网络)。

覆盖针对「短时间向猫耳发太多请求被风控」的几处修复：

- 全进程闸门确实限速，且平台报限流时进入全局退避、成功后解除
- 预期内的业务错误（主播没开播）**不**触发额外的 Cookie 校验
- 同一账户的 Cookie 校验按最短间隔节流
- Bot 恢复失败后进入冷却，不再被面板轮询反复触发
- 直播间信息刷新合并（开机时连调三次只真发一次）
- 管理员列表按 TTL 复用
- 更新进度状态读-改-写不冲掉同一文件里的其它键

运行: .venv/Scripts/python.exe test/test_outbound_pacing.py
"""

import asyncio
import os
import sys
import tempfile
import time

# 必须在 import core.* 之前设好 —— 与其它测试一致，防止误读真实 data/
_TMP = tempfile.mkdtemp(prefix="mismiss-pacing-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP
# 关掉限速的等待，否则每个用例都要白等闸门放行（限速本身由用例 1 单独验证）
os.environ["MISMISS_RATE_LIMIT_MIN_INTERVAL"] = "0"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.exceptions import CoreApiException  # noqa: E402
from core.network.throttle import OutboundGate, gate  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


# ------------------------------------------------------------------ #
# 1. 闸门限速
# ------------------------------------------------------------------ #

async def test_gate_rate_limit() -> None:
    g = OutboundGate()
    g.configure(0.05)
    t0 = time.monotonic()
    for _ in range(10):
        await g.acquire()
    elapsed = time.monotonic() - t0
    # 第 1 个名额不等待，其后 9 个各等 0.05s → 约 0.45s
    check("闸门按最小间隔放行", 0.30 < elapsed < 0.90, f"实测 {elapsed:.2f}s")

    g.configure(0.0)
    t0 = time.monotonic()
    for _ in range(10):
        await g.acquire()
    check("间隔为 0 时不等待", time.monotonic() - t0 < 0.2)


# ------------------------------------------------------------------ #
# 2. 识别限流 + 全局退避
# ------------------------------------------------------------------ #

async def test_global_backoff() -> None:
    g = OutboundGate()
    g.configure(0.0)
    check("HTTP 429 判定为限流",
          g.is_rate_limit_error(CoreApiException("HTTP 429: too many requests", status_code=429)))
    check("正文里的限流字样也能识别",
          g.is_rate_limit_error(CoreApiException("操作频繁，请稍后再试")))
    check("普通错误不误判为限流",
          not g.is_rate_limit_error(CoreApiException("主播休息")))

    g.note_failure(CoreApiException("HTTP 429", status_code=429))
    first = g.backoff_remaining
    check("限流后进入全局退避", first > 0, f"剩余 {first:.0f}s")

    # 再次触发应升级（退避更长）
    g.note_failure(CoreApiException("HTTP 429", status_code=429))
    check("重复限流使退避升级", g.backoff_remaining > first)

    # 退避期间 acquire 必须真的等
    t0 = time.monotonic()
    wait_task = asyncio.ensure_future(g.acquire())
    await asyncio.sleep(0.05)
    check("退避期间请求被挡住", not wait_task.done())
    wait_task.cancel()
    try:
        await wait_task
    except asyncio.CancelledError:
        pass
    check("退避是被动等待而非立即放行", time.monotonic() - t0 >= 0.05)

    g.note_success()
    check("成功后解除退避", g.backoff_remaining == 0)


async def test_consecutive_failure_backoff() -> None:
    """识别不出限流码时的兜底：连续失败到阈值也退避。"""
    g = OutboundGate()
    g.configure(0.0)
    for _ in range(7):
        g.note_failure(CoreApiException("某种未知错误"))
    check("未达阈值时不退避", g.backoff_remaining == 0)
    g.note_failure(CoreApiException("某种未知错误"))
    check("连续失败达阈值后也退避", g.backoff_remaining > 0)


# ------------------------------------------------------------------ #
# 3. _safe_call：预期错误不触发 Cookie 校验 + 校验节流
# ------------------------------------------------------------------ #

async def test_safe_call_skips_benign_and_throttles() -> None:
    from core.bot.mis_bot import _MIN_COOKIE_CHECK_INTERVAL, MissevanBot

    bot = MissevanBot("")
    refreshes = {"n": 0}

    async def fake_refresh() -> None:
        refreshes["n"] += 1

    bot.refresh = fake_refresh  # type: ignore[method-assign]

    def boom(msg: str):
        async def factory():
            raise CoreApiException(msg)
        return factory

    # 未开播属于预期情况 —— 不该去校验 Cookie
    for _ in range(5):
        try:
            await bot._safe_call(boom("code=500030011 主播休息"))
        except CoreApiException:
            pass
    check("预期业务错误不触发 Cookie 校验", refreshes["n"] == 0, f"实际 {refreshes['n']} 次")

    # 真实失败：第一次校验，紧接着的失败被节流
    for _ in range(5):
        try:
            await bot._safe_call(boom("HTTP 500"))
        except CoreApiException:
            pass
    check("真实失败触发了一次 Cookie 校验", refreshes["n"] == 1, f"实际 {refreshes['n']} 次")

    # 过了节流窗口后应再次允许
    bot._last_cookie_check = time.monotonic() - _MIN_COOKIE_CHECK_INTERVAL - 1
    try:
        await bot._safe_call(boom("HTTP 500"))
    except CoreApiException:
        pass
    check("超过节流窗口后重新允许校验", refreshes["n"] == 2, f"实际 {refreshes['n']} 次")

    check("主播休息被统一定义为预期错误",
          bot._is_benign_error(CoreApiException("500030011"))
          and bot._is_benign_error(CoreApiException("主播休息"))
          and not bot._is_benign_error(CoreApiException("HTTP 500")))


# ------------------------------------------------------------------ #
# 4. Bot 恢复冷却
# ------------------------------------------------------------------ #

async def test_bot_restore_cooldown() -> None:
    from core.server import _BOT_RESTORE_COOLDOWN, MissevanServer

    server = MissevanServer.__new__(MissevanServer)  # 跳过 __init__ 的插件扫描
    server._bot_restore_failed_at = 0.0
    attempts = {"n": 0}

    async def fake_restore(_state: dict) -> None:
        attempts["n"] += 1

    class _FakeState(dict):
        pass

    server._restore_bot = fake_restore  # type: ignore[method-assign]
    server._bot = type("B", (), {"id": 0})()  # 恢复失败后 id 仍为 0
    server._load_state = lambda: {"bot": {"cookie": "x"}}  # type: ignore[method-assign]
    server._livestreams = {}
    server._enabled_livestreams = set()

    async def call() -> None:
        # 只跑「Bot 恢复」那一段的等价逻辑
        left = server._bot_restore_failed_at + _BOT_RESTORE_COOLDOWN - time.monotonic()
        if server._bot.id == 0 and left <= 0:
            await server._restore_bot({})

    await call()
    check("首次会尝试恢复", attempts["n"] == 1)

    server._note_bot_restore_failure("失败了")
    for _ in range(20):
        await call()
    check("冷却期内不再重试（模拟 20 次面板轮询）", attempts["n"] == 1, f"实际 {attempts['n']} 次")

    server._bot_restore_failed_at = time.monotonic() - _BOT_RESTORE_COOLDOWN - 1
    await call()
    check("冷却结束后恢复重试", attempts["n"] == 2)


# ------------------------------------------------------------------ #
# 5. 直播间刷新合并 + 管理员列表 TTL
# ------------------------------------------------------------------ #

async def test_refresh_cooldown_and_meta_ttl() -> None:
    from core.livestream import mis_livestream as ML

    calls = {"room": 0, "meta": 0}

    class FakeRoomAPI:
        async def api(self, _live_id: int) -> dict:
            calls["room"] += 1
            return {"code": 0, "info": {"room": {"statistics": {}}, "creator": {}}}

    class FakeMetaAPI:
        async def api(self, _live_id: int) -> dict:
            calls["meta"] += 1
            return {"code": 0, "info": {"members": {"admin": []}}}

    ML.RoomInfoAPI = FakeRoomAPI  # type: ignore[misc]
    ML.MetaAPI = FakeMetaAPI  # type: ignore[misc]

    from core.events.bus import EventBus

    room = ML.MissevanLivestream(123, None, EventBus())  # type: ignore[arg-type]

    await room._refresh()
    check("首次刷新真的请求了房间信息", calls["room"] == 1)
    check("首次刷新取一次管理员列表", calls["meta"] == 1)

    # 开机时 _restore_livestream / enable_livestream / join 连调三次
    await room._refresh()
    await room._refresh()
    check("冷却窗口内重复刷新被合并", calls["room"] == 1, f"实际 {calls['room']} 次")
    check("管理员列表也在冷却内被复用", calls["meta"] == 1, f"实际 {calls['meta']} 次")

    # 窗口过期后应重新请求房间信息，但管理员列表仍在 TTL 内
    room._last_refresh_at = time.monotonic() - ML._REFRESH_MIN_INTERVAL - 1
    await room._refresh()
    check("冷却过后重新请求房间信息", calls["room"] == 2, f"实际 {calls['room']} 次")
    check("管理员列表仍在 TTL 内复用", calls["meta"] == 1, f"实际 {calls['meta']} 次")

    # 强制刷新应无视两层缓存
    await room._refresh(force=True)
    check("force 无视冷却与 TTL", calls["room"] == 3 and calls["meta"] == 2,
          f"room={calls['room']} meta={calls['meta']}")


# ------------------------------------------------------------------ #
# 6. 更新进度状态：读-改-写不冲掉其它键
# ------------------------------------------------------------------ #

def test_update_state_merge() -> None:
    import pathlib

    from api.routes import update as U
    from api.routes.update import (
        _APPLY_DONE, _APPLY_INTERRUPTED, _APPLY_RUNNING, _read_apply_progress,
        _set_apply_progress, mark_interrupted_if_running,
    )

    U._UPDATE_STATE_FILE = pathlib.Path(_TMP) / "update_state.json"

    U._patch_update_state(backup_dir="/tmp/bak", backup_version="1.3.0")
    U._mark_notify_pending("1.5.0", "好了")
    _set_apply_progress("apply", _APPLY_RUNNING, "load", "导入中", "1.5.0")

    state = U._load_update_state()
    check("写进度不冲掉备份信息", state.get("backup_dir") == "/tmp/bak")
    check("写进度不冲掉待发提示", "notify_pending" in state)
    check("进度带可读步骤文案", _read_apply_progress()["step_label"] == U._STEP_LABELS["load"])

    mark_interrupted_if_running()
    check("残留 running 被判为中断", _read_apply_progress()["state"] == _APPLY_INTERRUPTED)

    _set_apply_progress("apply", _APPLY_DONE, "done", "好了", "1.5.0")
    mark_interrupted_if_running()
    check("已是终态则不被改写", _read_apply_progress()["state"] == _APPLY_DONE)

    check("原子写不残留 .tmp",
          not (pathlib.Path(_TMP) / "update_state.tmp").exists())


# ------------------------------------------------------------------ #

async def main() -> None:
    await test_gate_rate_limit()
    await test_global_backoff()
    await test_consecutive_failure_backoff()
    await test_safe_call_skips_benign_and_throttles()
    await test_bot_restore_cooldown()
    await test_refresh_cooldown_and_meta_ttl()
    test_update_state_merge()
    print(f"\n{_passed}/{_passed} 通过")


if __name__ == "__main__":
    gate.reset()
    asyncio.run(main())
