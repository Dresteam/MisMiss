"""永久账户续期/兑换语义测试(TestClient,隔离数据目录,无网络)。

覆盖:永久账户叠加续期保持永久并返回提示、永久账户兑换被拒绝且**不消耗**
授权码、永久账户可被显式设为限期(设置剩余天数)、限期与已过期账户的叠加
续期语义不变、新增的「设为永久」入口。

运行: .venv/Scripts/python.exe test/test_permanent_account.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))

_TMP_DATA = tempfile.mkdtemp(prefix="mismiss-permanent-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP_DATA

from fastapi.testclient import TestClient  # noqa: E402

import web.backend.main as main_mod  # noqa: E402
from api.deps import get_account_manager  # noqa: E402


def _now(days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _mk(client, h, name: str, username: str, days: int) -> int:
    """创建账户,days=-1 表示永久。"""
    r = client.post("/api/panel/accounts", headers=h,
                    json={"name": name, "bot_mode": "public",
                          "username": username, "password": "test1234",
                          "duration_days": days})
    assert r.status_code == 200, f"FAIL: 创建账户失败 {r.text}"
    return r.json()["id"]


def main():
    with TestClient(main_mod.app) as client:
        manager = get_account_manager()
        r = client.post("/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"})
        assert r.status_code == 200, f"FAIL: 管理员登录失败 {r.text}"
        h = {"Authorization": f"Bearer {r.json()['token']}"}

        # ---- 1. 永久账户叠加续期:保持永久 + 提示 ----
        perm = _mk(client, h, "永久账户", "perma", -1)
        rec = manager.get_record(perm)
        assert rec.is_permanent and rec.expires_at is None, "FAIL: 新建的永久账户状态不对"

        r = client.post(f"/api/panel/accounts/{perm}/renew", headers=h, json={"days": 30})
        assert r.status_code == 200, f"FAIL: {r.text}"
        body = r.json()
        assert body["expires_at"] is None, f"FAIL: 永久账户被续成限期 {body['expires_at']}"
        assert body["days_left"] is None, "FAIL: 永久账户 days_left 应为 None"
        assert body["notice"] == "该账户为永久有效，无需续期", f"FAIL: 缺少提示 {body.get('notice')}"
        print("PASS 1: 永久账户「续期 30 天」仍为永久,并返回提示")

        # ---- 2. 永久账户兑换授权码:拒绝且不消耗 ----
        r = client.post("/api/panel/licenses/generate", headers=h, json={"count": 1, "days": 30})
        code = r.json()[0]["code"]
        r = client.post(f"/api/panel/accounts/{perm}/redeem", headers=h, json={"code": code})
        assert r.status_code == 400, f"FAIL: 永久账户兑换应被拒绝,实际 {r.status_code}"
        assert "永久" in r.json()["detail"], f"FAIL: 提示不含原因 {r.json()['detail']}"
        assert manager._licenses[code]["used_at"] is None, "FAIL: 授权码被白白消耗"
        assert manager.get_record(perm).expires_at is None, "FAIL: 永久账户状态被改动"
        print("PASS 2: 永久账户兑换被拒绝,授权码未被消耗")

        # ---- 3. 该授权码仍可被限期账户正常使用(证明未被消耗) ----
        temp = _mk(client, h, "限期账户", "tempa", 10)
        r = client.post(f"/api/panel/accounts/{temp}/redeem", headers=h, json={"code": code})
        assert r.status_code == 200, f"FAIL: 授权码不可用 {r.text}"
        assert r.json()["days_left"] == 40, f"FAIL: 兑换后应 40 天,实际 {r.json()['days_left']}"
        assert manager._licenses[code]["used_at"] is not None, "FAIL: 兑换后未标记已使用"
        print("PASS 3: 同一个码随后被限期账户成功兑换(证明未被消耗)")

        # ---- 4. 限期账户叠加续期:语义不变(回归) ----
        r = client.post(f"/api/panel/accounts/{temp}/renew", headers=h, json={"days": 5})
        assert r.status_code == 200 and r.json()["days_left"] == 45, \
            f"FAIL: 限期账户叠加异常 {r.json()}"
        assert r.json()["notice"] is None, "FAIL: 限期账户不应有提示"
        print("PASS 4: 限期账户「续期 5 天」正常叠加至 45 天")

        # ---- 5. 已过期账户叠加续期:从当前时间起算(回归) ----
        r = client.post(f"/api/panel/accounts/{temp}/renew", headers=h,
                        json={"expires_at": _now(-2)})
        assert r.json()["expired"] is True, "FAIL: 未成功制造成过期"
        r = client.post(f"/api/panel/accounts/{temp}/renew", headers=h, json={"days": 7})
        assert r.json()["days_left"] == 7, \
            f"FAIL: 过期账户应从 now 起算 7 天,实际 {r.json()['days_left']}"
        print("PASS 5: 已过期账户「续期 7 天」从当前时间起算")

        # ---- 6. 永久账户可被显式设为限期(设置剩余天数,有意行为) ----
        r = client.post(f"/api/panel/accounts/{perm}/renew", headers=h,
                        json={"expires_at": _now(15)})
        assert r.status_code == 200 and r.json()["days_left"] == 15, f"FAIL: {r.json()}"
        assert manager.get_record(perm).is_permanent is False, "FAIL: 未转为限期"
        print("PASS 6: 永久账户可通过「设置剩余天数」显式转为限期")

        # ---- 7. 新增「设为永久」入口 ----
        r = client.post(f"/api/panel/accounts/{temp}/renew", headers=h, json={"permanent": True})
        assert r.status_code == 200, f"FAIL: {r.text}"
        assert r.json()["expires_at"] is None and r.json()["days_left"] is None, \
            f"FAIL: 未被设为永久 {r.json()}"
        assert manager.get_record(temp).is_permanent is True
        print("PASS 7: 限期账户可被「设为永久」")

        # ---- 8. 过期账户设为永久后自动恢复运行 ----
        exp = _mk(client, h, "过期账户", "expa", -1)
        client.post(f"/api/panel/accounts/{exp}/renew", headers=h, json={"expires_at": _now(-1)})
        assert manager.get_record(exp).expired is True, "FAIL: 未成功制造成过期"
        r = client.post(f"/api/panel/accounts/{exp}/renew", headers=h, json={"permanent": True})
        assert r.status_code == 200 and r.json()["expired"] is False, f"FAIL: {r.json()}"
        assert manager.get_record(exp).paused_reason is None, "FAIL: 暂停标记未清除"
        print("PASS 8: 过期账户「设为永久」后解除过期与暂停")

        # ---- 9. 三选一校验 ----
        r = client.post(f"/api/panel/accounts/{perm}/renew", headers=h, json={})
        assert r.status_code == 400, f"FAIL: 空请求应 400,实际 {r.status_code}"
        print("PASS 9: 未提供任何续期参数时返回 400")

        print("\n全部通过")


if __name__ == "__main__":
    main()
