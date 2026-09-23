"""批量补偿时长测试（无网络）。

覆盖：
- 筛选取并集：已过期 / 未过期 / 剩余天数 ≤ N / 手动勾选
- 永久账户始终排除，且显式计入「跳过」（管理员能看出为什么没补它）
- dry_run 只预览不改库，且给出与实补一致的分组明细
- 实补按 renew_days 语义叠加：已过期从「现在」起算，未过期在原到期时间上顺延
- 补完是否自动恢复运行，跟随账户自身的 auto_resume_on_renew 偏好
- 参数校验：天数 ≤ 0 / 非整数 → 400，且不误改任何账户

运行： .venv/Scripts/python.exe test/test_compensate_accounts.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

_DATA = tempfile.mkdtemp(prefix="mismiss-compensate-")
os.environ["MISMISS_DATA_DIR"] = _DATA

from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402
from api.deps import get_account_manager  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


def _iso(delta_days: float) -> str:
    """相对现在的到期时间（带时区，days_left 要拿它和 aware utcnow 相减）。"""
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


with TestClient(app) as c:
    tok = c.post(
        "/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"},
    ).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    mgr = get_account_manager()

    def mk(name: str, *, expires: str | None, auto_resume: bool = True) -> int:
        r = c.post("/api/panel/accounts", headers=H, json={
            "name": name, "bot_mode": "private", "cookie": "",
            "username": f"u{name}", "password": "pw123456", "duration_days": 30,
        })
        aid = r.json()["id"]
        rec = mgr.get_record(aid)
        rec.expires_at = expires
        rec.auto_resume_on_renew = auto_resume
        mgr._save_panel()
        return aid

    # 过期 2 个 / 未过期 3 个（其中 1 个 3 天后到期）/ 永久 1 个
    far = mk("远未到期", expires=_iso(60))
    near = mk("三天后到期", expires=_iso(3))
    mid = mk("半月后到期", expires=_iso(15))
    exp1 = mk("已过期甲", expires=_iso(-5))
    exp2 = mk("已过期乙", expires=_iso(-1))
    perm = mk("永久账户", expires=None)

    def post(**body):
        payload = {"days": 3, "include_expired": True, "include_active": True}
        payload.update(body)
        return c.post("/api/panel/accounts/compensate", headers=H, json=payload)

    def left(aid: int) -> int | None:
        return mgr.get_record(aid).days_left

    def names(r) -> set[str]:
        return set(r.json()["compensated"])

    # ---- 1. 参数校验 ----
    check("天数 0 -> 400", post(days=0).status_code == 400,
          str(post(days=0).status_code))
    check("天数为负 -> 400", post(days=-3).status_code == 400)
    check("天数非整数 -> 400", post(days="abc").status_code == 400)
    check("max_days_left 非整数 -> 400", post(max_days_left="x").status_code == 400)
    check("account_ids 含非整数 -> 400", post(account_ids=["a"]).status_code == 400)
    check("未认证 -> 401", c.post(
        "/api/panel/accounts/compensate", json={"days": 3}).status_code == 401)

    # ---- 2. dry_run 只预览、不改库 ----
    before = {aid: left(aid) for aid in (far, near, mid, exp1, exp2, perm)}
    r = post(dry_run=True)
    check("dry_run 返回 200", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
    check("dry_run 预览到 5 个目标（永久排除）", len(r.json()["compensated"]) == 5,
          str(r.json()["compensated"]))
    check("dry_run 不动库", {aid: left(aid) for aid in before} == before,
          f"{before} -> " + str({aid: left(aid) for aid in before}))
    check("dry_run 标记为真", r.json()["dry_run"] is True)
    check("永久账户计入跳过且说明原因",
          any("永久账户" in s for s in r.json()["skipped"]),
          str(r.json()["skipped"]))
    groups = {g["label"]: g["items"] for g in r.json()["groups"]}
    check("预览按过期/未过期分组",
          len(groups) == 2 and len(sum(groups.values(), [])) == 5,
          str({k: len(v) for k, v in groups.items()}))

    # ---- 3. 筛选取并集 ----
    check("只勾已过期 -> 只有 2 个过期账户",
          names(post(dry_run=True, include_active=False)) == {"已过期甲", "已过期乙"},
          str(names(post(dry_run=True, include_active=False))))
    check("只勾未过期 -> 3 个未过期账户",
          names(post(dry_run=True, include_expired=False)) == {"远未到期", "三天后到期", "半月后到期"},
          str(names(post(dry_run=True, include_expired=False))))
    check("两个都不勾 -> 无候选",
          names(post(dry_run=True, include_expired=False, include_active=False)) == set(),
          str(names(post(dry_run=True, include_expired=False, include_active=False))))
    check("剩余 ≤ 5 天 -> 三天后到期 + 两个已过期",
          names(post(dry_run=True, max_days_left=5)) == {"三天后到期", "已过期甲", "已过期乙"},
          str(names(post(dry_run=True, max_days_left=5))))
    check("手动勾选只补指定账户",
          names(post(dry_run=True, account_ids=[far, exp1])) == {"远未到期", "已过期甲"},
          str(names(post(dry_run=True, account_ids=[far, exp1]))))
    check("手动勾选与筛选取交集（勾了不满足条件的则不补）",
          names(post(dry_run=True, include_active=False, account_ids=[far])) == set(),
          str(names(post(dry_run=True, include_active=False, account_ids=[far]))))

    # ---- 4. 实补：叠加语义 ----
    r = post(days=10)
    check("实补返回 200", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
    check("实补 5 个账户", len(r.json()["compensated"]) == 5, str(r.json()["compensated"]))
    check("未过期在原到期时间上顺延（60 -> 70）",
          68 <= (left(far) or 0) <= 70, str(left(far)))
    check("未过期在原到期时间上顺延（3 -> 13）",
          12 <= (left(near) or 0) <= 13, str(left(near)))
    check("已过期从「现在」起算（不是 -5+10=5）",
          9 <= (left(exp1) or 0) <= 10, str(left(exp1)))
    check("永久账户未被改动", mgr.get_record(perm).is_permanent)
    check("结果里说明天数与数量",
          "+10" in r.json()["message"] and "5" in r.json()["message"],
          r.json()["message"])

    # ---- 5. 恢复行为跟随账户自身偏好 ----
    # 光把 expires_at 改成过去只是「记录上过期」，运行态不会自己变 —— 得手动
    # 摆成「已到期并被强制停用」的样子，否则断言的是一个从未发生过的前提
    def mark_expired_stopped(aid: int) -> None:
        rec = mgr.get_record(aid)
        rec.expires_at = _iso(-2)
        rec.paused_reason = "expiry"
        mgr.get_server(aid).bot.enabled = False
        mgr._save_panel()

    # 记录 resume_after_renew 是否被调用（真实实现要联网，测试里只关心「有没有尝试」）
    calls: list[int] = []
    real_resume = mgr.resume_after_renew

    async def spy_resume(account_id: int):
        calls.append(account_id)
        return await real_resume(account_id)

    mgr.resume_after_renew = spy_resume  # type: ignore[method-assign]

    quiet = mk("静默恢复", expires=None, auto_resume=False)
    mark_expired_stopped(quiet)
    check("前置：静默账户已停用且标记为到期",
          mgr.get_server(quiet).bot.enabled is False
          and mgr.get_record(quiet).paused_reason == "expiry",
          f"{mgr.get_server(quiet).bot.enabled} / {mgr.get_record(quiet).paused_reason}")
    calls.clear()
    post(days=5, include_active=False, account_ids=[quiet])
    check("偏好关闭时只加时长、不尝试恢复", calls == [], str(calls))
    check("偏好关闭时并非自动启用 Bot",
          mgr.get_server(quiet).bot.enabled is False,
          str(mgr.get_server(quiet).bot.enabled))
    check("偏好关闭时仍清掉了到期标记",
          mgr.get_record(quiet).paused_reason is None,
          str(mgr.get_record(quiet).paused_reason))
    check("仍然补上了时长", (left(quiet) or 0) >= 4, str(left(quiet)))

    loud = mk("自动恢复", expires=None, auto_resume=True)
    mark_expired_stopped(loud)
    calls.clear()
    r = post(days=5, include_active=False, account_ids=[loud])
    check("偏好开启时补偿成功", r.status_code == 200, f"{r.status_code} {r.text[:80]}")
    check("偏好开启时会尝试恢复运行", calls == [loud], str(calls))
    check("补上时长", (left(loud) or 0) >= 4, str(left(loud)))

    mgr.resume_after_renew = real_resume  # type: ignore[method-assign]

# ---------------------------------------------------------------- #

passed = sum(1 for _, ok, _ in res if ok)
for i, (name, ok, detail) in enumerate(res, 1):
    print(f"{'PASS' if ok else 'FAIL'} {i}: {name}" + (f"  [{detail}]" if not ok else ""))
print(f"\n{passed}/{len(res)} 通过")
sys.exit(0 if passed == len(res) else 1)
