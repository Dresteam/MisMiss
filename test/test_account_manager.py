"""AccountManager 测试(无网络):CRUD、panel.json 原子写、到期停用/续期、总览。

运行: docker run --rm -v <repo>:/src -w /src mismiss:latest python /src/test/test_account_manager.py
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.account import AccountManager, ExpiryScheduler  # noqa: E402
from core.config import ServerConfig  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def main():
    tmp = tempfile.mkdtemp(prefix="mismiss-account-test-")
    cfg = ServerConfig({"server": {"data_dir": tmp}})
    manager = AccountManager(cfg)
    manager.load()

    # ---- 1. 创建账户(无 cookie/房间,不触网) ----
    rec1 = await manager.create_account("账户A", bot_mode="public", username="acctA")
    assert rec1.id == 1 and rec1.bot_mode == "public"
    rec2 = await manager.create_account(
        "账户B", bot_mode="private", duration_days=30, username="acctB",
    )
    assert rec2.id == 2
    with open(os.path.join(tmp, "panel.json"), encoding="utf-8") as f:
        panel = json.load(f)
    assert len(panel["accounts"]) == 2 and panel["next_account_id"] == 3
    print("PASS 1: 账户创建 + panel.json 持久化")

    # ---- 2. 查询与快照 ----
    snap = manager.overview()
    assert snap["total"] == 2 and snap["expired_count"] == 0
    assert snap["accounts"][0]["name"] == "账户A"
    assert manager.require_active(1).account_id == 1
    print("PASS 2: overview 聚合与运行时访问")

    # ---- 3. 到期停用(幂等) ----
    await manager.stop_for_expiry(2)
    assert manager.get_record(2).paused_reason == "expiry"
    await manager.stop_for_expiry(2)  # 幂等,不抛
    print("PASS 3: stop_for_expiry 幂等")

    # ---- 4. 到期守卫 ----
    expired = await manager.create_account(
        "账户C", bot_mode="private", duration_days=30, username="acctC",
    )
    expired.expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    manager._save_panel()
    try:
        manager.require_active(expired.id)
        raise AssertionError("FAIL: 过期账户未拒绝")
    except Exception as e:
        assert "过期" in str(e), f"FAIL: {e}"
    print("PASS 4: require_active 过期拒绝")

    # ---- 5. 续期解除过期 ----
    rec = await manager.renew_days(2, 30)
    assert rec.paused_reason is None
    assert not rec.expired
    assert rec.days_left >= 29
    assert manager.require_active(2).account_id == 2
    print("PASS 5: 续期解除过期并恢复访问")

    # ---- 6. 删除账户 ----
    await manager.delete_account(1)
    assert len(manager.list_records()) == 2
    try:
        manager.get_record(1)
        raise AssertionError("FAIL: 已删除账户仍存在")
    except Exception:
        pass
    await manager.delete_account(expired.id, purge_data=True)
    assert not os.path.exists(os.path.join(tmp, "accounts", str(expired.id)))
    print("PASS 6: 删除(含 purge)")

    # ---- 7. 调度器 tick ----
    rec3 = await manager.create_account("账户D", bot_mode="private", duration_days=30, username="acctD")
    rec3.expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    manager._save_panel()
    scheduler = ExpiryScheduler(manager, interval=5.0)
    await scheduler.tick()
    assert manager.get_record(rec3.id).paused_reason == "expiry"
    print("PASS 7: 调度器 tick 自动停用到期账户")

    # ---- 8. 关闭 ----
    await manager.shutdown_all()
    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
