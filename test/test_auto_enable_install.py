"""「安装插件自动启用」账户级偏好测试(TestClient,隔离数据目录,无网络)。

覆盖:默认关闭、账户自助开关、按偏好自动启用、启用失败不影响安装结果、
偏好按账户独立、账户不能改他人偏好（中间件 403）。

运行: .venv/Scripts/python.exe test/test_auto_enable_install.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))

_TMP_DATA = tempfile.mkdtemp(prefix="mismiss-autoenable-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP_DATA

from fastapi.testclient import TestClient  # noqa: E402

import web.backend.main as main_mod  # noqa: E402
from api.deps import get_account_manager  # noqa: E402

# 用真实的插件库目录：关键词回复用于「启用成功」，error_plugin 用于「启用失败」
_OK_PLUGIN = "keyword_reply"
_FAIL_PLUGIN = "error_plugin"
_LIB = os.path.join(os.path.dirname(__file__), "..", "plugins")


def _mk(client, h, name: str, username: str) -> int:
    r = client.post("/api/panel/accounts", headers=h,
                    json={"name": name, "bot_mode": "public",
                          "username": username, "password": "test1234"})
    assert r.status_code == 200, f"FAIL: 创建账户失败 {r.text}"
    return r.json()["id"]


def _enabled(manager, aid: int, plugin: str) -> bool:
    meta = manager.get_server(aid)._plugin_manager.get_plugin(plugin)
    return bool(meta and meta.enabled)


def main():
    with TestClient(main_mod.app) as client:
        manager = get_account_manager()
        r = client.post("/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"})
        assert r.status_code == 200, f"FAIL: 管理员登录失败 {r.text}"
        ah = {"Authorization": f"Bearer {r.json()['token']}"}

        a = _mk(client, ah, "甲账户", "alpha")
        b = _mk(client, ah, "乙账户", "beta")

        # ---- 1. 默认关闭 ----
        r = client.get(f"/api/accounts/{a}/info", headers=ah)
        assert r.status_code == 200, f"FAIL: {r.text}"
        assert r.json()["auto_enable_on_install"] is False, "FAIL: 该偏好应默认关闭"
        print("PASS 1: 偏好默认关闭")

        # ---- 2. 关闭时安装 → 保持停用 ----
        r = client.post(f"/api/accounts/{a}/plugins/install", headers=ah,
                        json={"name": _OK_PLUGIN})
        assert r.status_code == 200, f"FAIL: {r.text}"
        assert "默认停用" in r.json()["message"], f"FAIL: 提示未说明停用 {r.json()}"
        assert _enabled(manager, a, _OK_PLUGIN) is False, "FAIL: 关闭偏好时不应自动启用"
        print("PASS 2: 关闭偏好安装后保持停用")

        # ---- 3. 账户持有者自助开启偏好 ----
        r = client.post("/api/auth/login", json={"username": "alpha", "password": "test1234"})
        assert r.status_code == 200, f"FAIL: 账户登录失败 {r.text}"
        h_a = {"Authorization": f"Bearer {r.json()['token']}"}
        r = client.post(f"/api/accounts/{a}/preferences", headers=h_a,
                        json={"auto_enable_on_install": True})
        assert r.status_code == 200, f"FAIL: 账户自助设置偏好失败 {r.text}"
        assert r.json()["auto_enable_on_install"] is True
        assert manager.get_record(a).auto_enable_on_install is True, "FAIL: 未落盘"
        print("PASS 3: 账户持有者可自助开启该偏好")

        # ---- 4. 账户不能改他人偏好（中间件按账户 ID 拦截）----
        r = client.post(f"/api/accounts/{b}/preferences", headers=h_a,
                        json={"auto_enable_on_install": True})
        assert r.status_code == 403, f"FAIL: 跨账户改偏好应 403, 实际 {r.status_code}"
        assert manager.get_record(b).auto_enable_on_install is False, "FAIL: 乙账户被改动"
        print("PASS 4: 账户无法修改他人偏好（403）")

        # ---- 5. 偏好按账户独立 ----
        r = client.get(f"/api/accounts/{b}/info", headers=ah)
        assert r.json()["auto_enable_on_install"] is False, "FAIL: 偏好串账户了"
        print("PASS 5: 偏好按账户独立（乙账户不受甲账户影响）")

        # ---- 6. 管理员为甲账户安装也遵循其偏好 ----
        r = client.post(f"/api/accounts/{a}/plugins/install", headers=ah,
                        json={"name": "checkin"})
        assert r.status_code == 200, f"FAIL: {r.text}"
        assert "已安装并启用" in r.json()["message"], f"FAIL: {r.json()}"
        assert _enabled(manager, a, "checkin") is True, \
            "FAIL: 管理员安装也应遵循账户偏好"
        print("PASS 6: 管理员安装同样遵循该账户的偏好")

        # ---- 7. 自动启用失败：保留安装 + 提示，不回滚 ----
        if not os.path.isdir(os.path.join(_LIB, _FAIL_PLUGIN)):
            print(f"SKIP 7: 本地无 {_FAIL_PLUGIN}（该插件被插件库 gitignore，不随仓库分发）")
        else:
            r = client.post(f"/api/accounts/{a}/plugins/install", headers=ah,
                            json={"name": _FAIL_PLUGIN})
            assert r.status_code == 200, f"FAIL: 启用失败不应让安装报错 {r.text}"
            msg = r.json()["message"]
            assert "已安装" in msg and "自动启用失败" in msg, f"FAIL: 提示不对 {msg}"
            meta = manager.get_server(a)._plugin_manager.get_plugin(_FAIL_PLUGIN)
            assert meta is not None, "FAIL: 失败的插件被回滚删除了"
            assert meta.enabled is False, "FAIL: 失败的插件不应处于启用态"
            assert meta.last_error, "FAIL: 未记录 last_error"
            print(f"PASS 7: 自动启用失败时保留安装并提示（last_error={meta.last_error!r}）")

        # ---- 8. 偏好持久化 ----
        m2 = manager.__class__(data_dir=_TMP_DATA)
        m2.load()
        assert m2.get_record(a).auto_enable_on_install is True, "FAIL: 偏好未持久化"
        print("PASS 8: 偏好持久化到 panel.json")

        print("\n全部通过")


if __name__ == "__main__":
    main()
