"""账户 API 集成测试(TestClient,隔离数据目录)。

运行: docker run --rm -v <repo>:/src -w /src mismiss:latest python /src/test/test_account_api.py
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))

# 必须在导入 main 之前设置隔离数据目录
_TMP_DATA = tempfile.mkdtemp(prefix="mismiss-api-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP_DATA

from fastapi.testclient import TestClient  # noqa: E402

import web.backend.main as main_mod  # noqa: E402


def _now(days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def main():
    with TestClient(main_mod.app) as client:
        # ---- 登录 ----
        r = client.post("/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"})
        assert r.status_code == 200, f"FAIL: 登录失败 {r.text}"
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        # ---- 未认证 401 ----
        assert client.get("/api/panel/overview").status_code == 401
        print("PASS 1: 认证守卫")

        # ---- 创建账户(public,无网络) ----
        r = client.post("/api/panel/accounts", headers=h,
                        json={"name": "API账户", "bot_mode": "public", "username": "apia"})
        assert r.status_code == 200, f"FAIL: {r.text}"
        aid = r.json()["id"]
        print("PASS 2: 创建账户")

        # ---- 总览 ----
        r = client.get("/api/panel/overview", headers=h)
        assert r.status_code == 200 and r.json()["total"] >= 1
        print("PASS 3: 总览")

        # ---- public 账户 cookie 403 ----
        r = client.get(f"/api/accounts/{aid}/bot/cookie", headers=h)
        assert r.status_code == 403, f"FAIL: {r.status_code} {r.text}"
        print("PASS 4: public 账户 Cookie 不可见")

        # ---- 未绑定房间 / 定时消息需要 Bot ----
        r = client.post(f"/api/accounts/{aid}/timer/add", headers=h, json={"message": "hi"})
        assert r.status_code == 400, f"FAIL: {r.status_code}"
        print("PASS 5: 无 Bot 时定时消息拒绝")

        # ---- 过期账户写操作 403 ----
        r = client.post("/api/panel/accounts", headers=h,
                        json={"name": "过期账户", "bot_mode": "public", "duration_days": 30, "username": "expireda"})
        # 续期接口直接改到过去,制造过期
        r = client.post(f"/api/panel/accounts/{r.json()['id']}/renew", headers=h,
                        json={"expires_at": _now(-1)})
        assert r.status_code == 200
        expired_id = r.json()["id"]
        r = client.post(f"/api/accounts/{expired_id}/bot/enable", headers=h)
        assert r.status_code == 403, f"FAIL: {r.status_code} {r.text}"
        assert "过期" in r.json()["detail"]
        print("PASS 6: 过期账户写操作 403")

        # ---- 授权码生成 + 兑换 ----
        r = client.post("/api/panel/licenses/generate", headers=h,
                        json={"count": 2, "days": 30})
        assert r.status_code == 200 and len(r.json()) == 2
        code = r.json()[0]["code"]
        r = client.post(f"/api/panel/accounts/{expired_id}/redeem", headers=h,
                        json={"code": code})
        assert r.status_code == 200, f"FAIL: {r.text}"
        assert r.json()["days_left"] == 30 and not r.json()["expired"]
        print("PASS 7: 授权码兑换解除过期")

        # ---- 续期 ----
        # aid 创建时未给 duration_days,即永久账户——叠加续期应保持永久并给出提示
        r = client.post(f"/api/panel/accounts/{aid}/renew", headers=h, json={"days": 7})
        assert r.status_code == 200, f"FAIL: {r.text}"
        assert r.json()["expires_at"] is None and r.json()["days_left"] is None, \
            f"FAIL: 永久账户被续成限期 {r.json()['expires_at']}"
        assert r.json()["notice"], "FAIL: 永久账户续期应返回提示"
        # 设为永久对已永久账户幂等
        r = client.post(f"/api/panel/accounts/{aid}/renew", headers=h, json={"permanent": True})
        assert r.status_code == 200 and r.json()["expires_at"] is None
        print("PASS 8: 手动续期(永久账户保持永久并提示)")

        # ---- 删除 ----
        r = client.delete(f"/api/panel/accounts/{aid}", headers=h)
        assert r.status_code == 200
        r = client.get("/api/panel/accounts", headers=h)
        assert all(a["id"] != aid for a in r.json())
        print("PASS 9: 删除账户")

        print("\n全部通过")


if __name__ == "__main__":
    main()
