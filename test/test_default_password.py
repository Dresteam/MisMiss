"""默认密码强制改密测试（无网络）。

场景：新建账户的登录密码预填 `user123`，人人都知道，等于没设防。这类账户登录后
应被要求立刻改密，且**不能靠刷新页面绕过**。

覆盖：
- 用默认密码登录 → 标记 must_change_password
- 换成自己的密码后登录 → 不再标记
- 标记写进 token，因此 /auth/check（刷新页面走的接口）同样回报
- 改密成功后该账户的 token 全部作废 → 必须用新密码重新登录
- 管理员不受影响（它有自己那套首次登录引导）

运行： .venv/Scripts/python.exe test/test_default_password.py
"""
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

os.environ["MISMISS_DATA_DIR"] = tempfile.mkdtemp(prefix="mismiss-defaultpwd-")

from fastapi.testclient import TestClient  # noqa: E402
from web.backend.main import app  # noqa: E402
from core.account import DEFAULT_ACCOUNT_PASSWORD  # noqa: E402

res: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    res.append((name, cond, detail))


def login(c, username: str, password: str) -> dict:
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {r.status_code} {r.text[:120]}"
    return r.json()


def check_auth(c, token: str) -> dict:
    r = c.get("/api/auth/check", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text[:120]
    return r.json()


with TestClient(app) as c:
    admin_token = login(c, "MisMiss", "MisMiss")["token"]
    AH = {"Authorization": f"Bearer {admin_token}"}

    # 账户 A：沿用默认密码；账户 B：建好后就改成别的密码
    r = c.post("/api/panel/accounts", headers=AH, json={
        "name": "默认密码账户", "bot_mode": "private", "cookie": "",
        "username": "defpwd", "password": DEFAULT_ACCOUNT_PASSWORD,
        "duration_days": 30,
    })
    aid = r.json()["id"]

    r = c.post("/api/panel/accounts", headers=AH, json={
        "name": "自设密码账户", "bot_mode": "private", "cookie": "",
        "username": "ownpwd", "password": "my-own-pw",
        "duration_days": 30,
    })

    # ---- 1. 登录标记 ----
    d = login(c, "defpwd", DEFAULT_ACCOUNT_PASSWORD)
    check("默认密码登录被标记须改密", d.get("must_change_password") is True,
          str(d.get("must_change_password")))
    check("仍返回 account 角色与账户 id",
          d.get("role") == "account" and d.get("account_id") == aid,
          f"{d.get('role')} / {d.get('account_id')}")

    d2 = login(c, "ownpwd", "my-own-pw")
    check("自设密码的账户不被标记", d2.get("must_change_password") is False,
          str(d2.get("must_change_password")))

    # 管理员有自己那套首次登录引导，不该被这个标记影响
    d3 = login(c, "MisMiss", "MisMiss")
    check("管理员不受影响", d3.get("must_change_password") is False,
          str(d3.get("must_change_password")))

    # ---- 2. 刷新页面绕不过去（标记存在 token 里）----
    tok = d["token"]
    info = check_auth(c, tok)
    check("/auth/check 回报须改密（刷新绕不过）",
          info.get("must_change_password") is True,
          str(info.get("must_change_password")))

    own_tok = d2["token"]
    check("自设密码账户的 check 不回报",
          check_auth(c, own_tok).get("must_change_password") is False)

    # 管理员 token 的 check 也不该报
    check("管理员 check 不回报",
          check_auth(c, admin_token).get("must_change_password") is False)

    # ---- 3. 改密后标记消失、旧 token 失效 ----
    r = c.post(f"/api/accounts/{aid}/change-password", headers={"Authorization": f"Bearer {tok}"},
               json={"current_password": DEFAULT_ACCOUNT_PASSWORD,
                     "new_password": "brand-new-pw", "confirm_password": "brand-new-pw"})
    check("用默认密码改密成功", r.status_code == 200, f"{r.status_code} {r.text[:120]}")

    check("改密后旧 token 失效（须重新登录）",
          check_auth(c, tok).get("valid") is False, str(check_auth(c, tok)))

    d4 = login(c, "defpwd", "brand-new-pw")
    check("用新密码登录后不再被标记", d4.get("must_change_password") is False,
          str(d4.get("must_change_password")))
    check("新 token 的 check 也不再回报",
          check_auth(c, d4["token"]).get("must_change_password") is False)

    # ---- 4. 改回默认密码会重新被标记（判据是「密码是不是默认值」）----
    r = c.post(f"/api/accounts/{aid}/change-password",
               headers={"Authorization": f"Bearer {d4['token']}"},
               json={"current_password": "brand-new-pw",
                     "new_password": DEFAULT_ACCOUNT_PASSWORD,
                     "confirm_password": DEFAULT_ACCOUNT_PASSWORD})
    check("改回默认密码", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    d5 = login(c, "defpwd", DEFAULT_ACCOUNT_PASSWORD)
    check("改回默认密码后重新被标记", d5.get("must_change_password") is True,
          str(d5.get("must_change_password")))

# ---------------------------------------------------------------- #

passed = sum(1 for _, ok, _ in res if ok)
for i, (name, ok, detail) in enumerate(res, 1):
    print(f"{'PASS' if ok else 'FAIL'} {i}: {name}" + (f"  [{detail}]" if not ok else ""))
print(f"\n{passed}/{len(res)} 通过")
sys.exit(0 if passed == len(res) else 1)
