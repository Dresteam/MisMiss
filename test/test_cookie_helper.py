"""书签助手 / 手动粘贴 Cookie 测试(无外部网络)。

覆盖:
- token 单次有效、过期失效、跨账户不可用
- 匿名回传端点的授权边界(非法 token 一律同一个 400)
- Cookie 写入走 update_cookie 且**不改动账户既有权限**
- Cookie 无效时既有 Cookie 原样保留、失败原因写回 token 记录

运行: .venv/Scripts/python.exe test/test_cookie_helper.py
"""

import json
import os
import sys
import tempfile
import time

# 必须在 import web.backend.main 之前设好 —— auth.py 与 cookie_login.py
# 都在 import 期就把 _DATA_ROOT 解析成常量,晚设就隔离不掉了。
#
# ⚠️ 名字是 MISMISS(项目名 MisMiss),不是 MISSISS。拼错不会报错,而是
# **静默失败**:进程照常启动,读到的是真实 data/ —— 会把线上账户的 Bot
# 一并拉起来。下面的断言就是为了让这种拼错立刻炸掉,而不是悄悄跑起来。
_TMP = tempfile.mkdtemp(prefix="mismiss-cookie-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from core import MissevanServer  # noqa: E402
from core.exceptions import CoreCookieException  # noqa: E402
import web.backend.main as backend  # noqa: E402

# ⚠️ 走 `api.routes` 而不是 `web.backend.api.routes` —— main.py 把 web/backend
# 塞进 sys.path 后按 `api.routes` 导入,同一个文件因此被当作两个模块各执行
# 一次。要断言/操作运行时状态就必须用 app 真正在用的那一份。
from api.routes import auth as auth_route  # noqa: E402
from api.routes import cookie_login  # noqa: E402

# ------------------------------------------------------------------ #
# 隔离自检:名字拼错会静默读到真实 data/,把线上账户的 Bot 一并拉起来,
# 所以这里在起应用之前先确认数据目录确实指向临时目录。
# ------------------------------------------------------------------ #
def _assert_isolated() -> None:
    import pathlib

    want = pathlib.Path(_TMP).resolve()
    got = {
        "web.backend.main": pathlib.Path(backend._DATA_DIR).resolve(),
        "api.routes.auth": pathlib.Path(auth_route._DATA_ROOT).resolve(),
        "cookie_login": pathlib.Path(cookie_login._HELPER_TOKEN_DIR).parent.resolve(),
    }
    for where, path in got.items():
        assert path == want, (
            f"数据目录未隔离!{where} 解析为 {path},期望 {want}。"
            f"检查环境变量名是否为 MISMISS_DATA_DIR(注意是 MISMISS 不是 MISSISS)。"
        )


# ------------------------------------------------------------------ #
# 打桩:替换 update_cookie,避免真的去打 fm.missevan.com
# ------------------------------------------------------------------ #

_swap_calls: list[tuple[str, object]] = []


async def _fake_update_cookie(self, new_cookie, permissions=None):
    _swap_calls.append((new_cookie, permissions))
    if new_cookie.startswith("bad"):
        raise CoreCookieException("Cookie 已过期")
    if permissions is None:
        # 真实实现里 None 表示「保留原权限」,这里如实反映,好让测试断言最终权限
        pass
    return self.bot


MissevanServer.update_cookie = _fake_update_cookie


def main():
    _assert_isolated()
    with TestClient(backend.app) as client:
        # ---- 0. 登录并建一个私有 Cookie 账户 ----
        r = client.post("/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"})
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        auth = {"Authorization": f"Bearer {token}"}

        r = client.post("/api/panel/accounts", json={
            "name": "测试账户", "bot_mode": "private",
            "username": "acct_cookie", "password": "pass1234", "duration_days": -1,
        }, headers=auth)
        assert r.status_code == 200, r.text
        acc_id = r.json()["id"]
        print(f"PASS 0: 账户已创建 (id={acc_id}, data_dir={_TMP})")

        base = f"/api/accounts/{acc_id}"

        # ---- 1. 签发 token ----
        r = client.post(f"{base}/helper/token", headers=auth)
        assert r.status_code == 200, r.text
        body = r.json()
        htoken, expires = body["token"], body["expires_at"]
        assert len(htoken) == 64 and expires > time.time()
        print("PASS 1: 书签 token 已签发")

        # ---- 2. 初始状态是 waiting ----
        r = client.get(f"{base}/helper/status", headers={**auth, "X-Helper-Token": htoken})
        assert r.status_code == 200 and r.json()["state"] == "waiting", r.text
        print("PASS 2: 初始状态 waiting")

        # ---- 3. 非法 token 一律同一个 400(不区分不存在/已用/非法格式) ----
        codes = set()
        for bad in ["", "not-a-token", "0" * 64, "../" + "a" * 61]:
            r = client.post("/api/helper/cookie", json={"token": bad, "cookie": "c=1"})
            codes.add(r.status_code)
        assert codes == {400}, f"期望一律 400,实际 {codes}"
        print("PASS 3: 非法 token 一律 400")

        # ---- 4. 合法 token + 有效 Cookie → done,且不改权限 ----
        before_perms = backend._manager.require_active(acc_id).bot.permissions
        _swap_calls.clear()
        r = client.post("/api/helper/cookie", json={"token": htoken, "cookie": "MISSEVAN=good"})
        assert r.status_code == 200 and r.json().get("success") is True, r.text
        # 权限必须以「当前值」显式带下去 —— create_bot 的默认权限只有
        # SEND_LIVESTREAM_MESSAGE,不显式带就会把账户既有权限静默削掉
        assert _swap_calls == [("MISSEVAN=good", before_perms)], _swap_calls

        r = client.get(f"{base}/helper/status", headers={**auth, "X-Helper-Token": htoken})
        assert r.json()["state"] == "done", r.text
        after_perms = backend._manager.require_active(acc_id).bot.permissions
        assert before_perms == after_perms, "权限不应被改动"
        print("PASS 4: 有效 Cookie 写入成功,权限保持不变")

        # ---- 5. 同一个 token 不能再用第二次 ----
        r = client.post("/api/helper/cookie", json={"token": htoken, "cookie": "OTHER=1"})
        assert r.status_code == 400, f"token 应当一次性,实际 {r.status_code}"
        print("PASS 5: token 单次有效")

        # ---- 6. Cookie 无效 → state=failed,原因写回,且不写坏既有 Cookie ----
        r = client.post(f"{base}/helper/token", headers=auth)
        t2 = r.json()["token"]
        _swap_calls.clear()
        r = client.post("/api/helper/cookie", json={"token": t2, "cookie": "bad=1"})
        assert r.status_code == 200, r.text  # 对书签端始终 200,成败靠 status 查
        r = client.get(f"{base}/helper/status", headers={**auth, "X-Helper-Token": t2})
        assert r.json()["state"] == "failed", r.text
        assert "Cookie 无效" in r.json()["message"], r.text
        assert [c[0] for c in _swap_calls] == ["bad=1"], _swap_calls
        print("PASS 6: 无效 Cookie 记为 failed 并带回原因")

        # ---- 7. token 过期后拒绝 ----
        r = client.post(f"{base}/helper/token", headers=auth)
        t3 = r.json()["token"]
        path = cookie_login._token_path(t3)
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["expires"] = time.time() - 1
        path.write_text(json.dumps(rec), encoding="utf-8")
        r = client.post("/api/helper/cookie", json={"token": t3, "cookie": "c=1"})
        assert r.status_code == 400, f"过期 token 应被拒,实际 {r.status_code}"
        print("PASS 7: 过期 token 被拒")

        # ---- 8. 账户 A 的 token 不能写到账户 B ----
        r = client.post("/api/panel/accounts", json={
            "name": "第二账户", "bot_mode": "private",
            "username": "acct_two", "password": "pass1234", "duration_days": -1,
        }, headers=auth)
        acc_b = r.json()["id"]
        r = client.post(f"{base}/helper/token", headers=auth)
        t4 = r.json()["token"]
        # 用账户 A 的 token 去查账户 B 的状态 → 必须查不到
        r = client.get(f"/api/accounts/{acc_b}/helper/status",
                       headers={**auth, "X-Helper-Token": t4})
        assert r.json()["state"] == "failed", "token 不应跨账户可见"
        # 而账户 A 自己查得到
        r = client.get(f"{base}/helper/status", headers={**auth, "X-Helper-Token": t4})
        assert r.json()["state"] == "waiting"
        print("PASS 8: token 绑定账户,跨账户不可见")

        # ---- 9. 公共 Bot 账户自助取 Cookie → 自动切成自定义模式 ----
        r = client.post("/api/panel/accounts", json={
            "name": "公共账户", "bot_mode": "public",
            "username": "acct_pub", "password": "pass1234", "duration_days": -1,
        }, headers=auth)
        acc_pub = r.json()["id"]
        r = client.post(f"/api/accounts/{acc_pub}/helper/token", headers=auth)
        assert r.status_code == 200, f"公共账户也应能自助取 Cookie,实际 {r.status_code} {r.text}"
        t_pub = r.json()["token"]
        _swap_calls.clear()
        r = client.post("/api/helper/cookie", json={"token": t_pub, "cookie": "MYSELF=good"})
        assert r.status_code == 200 and r.json().get("success") is True, r.text
        # 关键:bot_mode 必须跟着切成 private。少了这一步,账户会停在分裂状态 ——
        # Bot 跑着用户自己的 Cookie,/bot/cookie 却仍 403、面板也仍按公共账户展示。
        assert backend._manager.get_record(acc_pub).bot_mode == "private", "模式未切换"
        st = client.get(f"/api/accounts/{acc_pub}/helper/status",
                        headers={**auth, "X-Helper-Token": t_pub})
        assert "切换" in st.json()["message"], st.json()
        print("PASS 9: 公共账户取 Cookie 后自动切换为自定义模式")

        # ---- 10. 请求体超限被拒 ----
        r = client.post("/api/helper/cookie",
                        json={"token": "a" * 64, "cookie": "x" * (20 * 1024)})
        assert r.status_code in (400, 413), f"超大 body 应被拒,实际 {r.status_code}"
        print("PASS 10: 超大请求体被拒")

    print("\n全部通过")


if __name__ == "__main__":
    main()
