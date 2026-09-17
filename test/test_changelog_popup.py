"""更新日志弹窗测试(TestClient,隔离数据目录,无网络)。

覆盖:版本日志读取与路径逃逸防护、AccountRecord 旧数据兼容、
新账户不弹、存量账户弹一次、确认后不再弹、管理员始终不弹、
first_login 不泄漏给账户角色。

运行: .venv/Scripts/python.exe test/test_changelog_popup.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))

# 必须在导入 main 之前设置隔离数据目录
_TMP_DATA = tempfile.mkdtemp(prefix="mismiss-changelog-test-")
os.environ["MISMISS_DATA_DIR"] = _TMP_DATA

from fastapi.testclient import TestClient  # noqa: E402

import web.backend.main as main_mod  # noqa: E402
from api.deps import get_account_manager  # noqa: E402
from core.version import CURRENT_VERSION, load_changelog  # noqa: E402


def _load_changelog_unit():
    """版本日志读取器的纯逻辑。"""
    doc = load_changelog(CURRENT_VERSION)
    assert doc is not None, f"FAIL: 读不到 v{CURRENT_VERSION} 的更新日志"
    assert doc["version"] == CURRENT_VERSION
    assert doc["title"] and doc["body"], "FAIL: 标题/正文为空"
    assert not doc["body"].lstrip().startswith("# "), "FAIL: 正文未剥离一级标题"
    print(f"PASS 1: 读取 v{CURRENT_VERSION} 更新日志 (标题={doc['title'][:24]}...)")

    assert load_changelog("9.9.9") is None, "FAIL: 不存在的版本应返回 None"
    for bad in ("../../etc/passwd", "..\\..\\win.ini", "/etc/passwd", "a/b"):
        assert load_changelog(bad) is None, f"FAIL: 非法版本号未被拒绝: {bad!r}"
    assert load_changelog(f"../{CURRENT_VERSION}") is None, "FAIL: 路径逃逸未被拒绝"
    print("PASS 2: 非法版本号 / 路径逃逸均被拒绝")


def main():
    _load_changelog_unit()

    with TestClient(main_mod.app) as client:
        manager = get_account_manager()

        # ---- 管理员登录:不弹窗 ----
        r = client.post("/api/auth/login", json={"username": "MisMiss", "password": "MisMiss"})
        assert r.status_code == 200, f"FAIL: 管理员登录失败 {r.text}"
        admin_token = r.json()["token"]
        assert r.json()["role"] == "admin"
        assert r.json()["pending_changelog"] is None, "FAIL: 管理员不应收到更新日志"
        ah = {"Authorization": f"Bearer {admin_token}"}

        r = client.get("/api/auth/check", headers=ah)
        assert r.json()["pending_changelog"] is None, "FAIL: 管理员 check 不应带日志"
        print("PASS 3: 管理员登录与 check 均无更新日志")

        # ---- 新建账户:全新账户不弹(它没经历过本次更新) ----
        r = client.post("/api/panel/accounts", headers=ah,
                        json={"name": "日志账户", "bot_mode": "public",
                              "username": "chglog", "password": "test1234"})
        assert r.status_code == 200, f"FAIL: 创建账户失败 {r.text}"
        aid = r.json()["id"]

        r = client.post("/api/auth/login", json={"username": "chglog", "password": "test1234"})
        assert r.status_code == 200, f"FAIL: 账户登录失败 {r.text}"
        assert r.json()["role"] == "account", "FAIL: 角色应为 account"
        assert r.json()["pending_changelog"] is None, "FAIL: 全新账户不应弹更新日志"
        print("PASS 4: 全新账户登录不弹更新日志")

        # ---- 模拟存量账户(升级前创建,seen_changelog_version 为空) ----
        rec = manager.get_record(aid)
        rec.seen_changelog_version = ""
        manager._save_panel()

        r = client.post("/api/auth/login", json={"username": "chglog", "password": "test1234"})
        pending = r.json()["pending_changelog"]
        assert pending is not None, "FAIL: 存量账户登录应收到更新日志"
        assert pending["version"] == CURRENT_VERSION and pending["body"], "FAIL: 日志内容为空"
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        print(f"PASS 5: 存量账户登录弹出 v{pending['version']} 更新日志")

        r = client.get("/api/auth/check", headers=h)
        assert r.json()["pending_changelog"] is not None, "FAIL: check 也应带日志"
        print("PASS 6: /auth/check 同样返回待读日志")

        # ---- 确认后不再弹(核心验收点) ----
        r = client.post("/api/auth/ack-changelog", headers=h)
        assert r.status_code == 200, f"FAIL: 确认失败 {r.text}"
        assert r.json()["version"] == CURRENT_VERSION
        assert manager.get_record(aid).seen_changelog_version == CURRENT_VERSION, \
            "FAIL: 已读版本未落盘"

        r = client.post("/api/auth/login", json={"username": "chglog", "password": "test1234"})
        assert r.json()["pending_changelog"] is None, "FAIL: 已确认后不应再弹"
        r = client.get("/api/auth/check", headers=h)
        assert r.json()["pending_changelog"] is None, "FAIL: 已确认后 check 不应再带"
        print("PASS 7: 确认后不再弹出(只弹一次)")

        # ---- 确认接口的边界 ----
        assert client.post("/api/auth/ack-changelog").status_code == 401, \
            "FAIL: 无 token 应 401"
        assert client.post("/api/auth/ack-changelog", headers=ah).status_code == 200, \
            "FAIL: 管理员确认应安全无操作"
        assert manager.get_record(aid).seen_changelog_version == CURRENT_VERSION
        print("PASS 8: 无 token 401 / 管理员确认为无操作")

        # ---- first_login 不泄漏给账户角色 ----
        r = client.get("/api/auth/check", headers=h)
        assert r.json()["first_login"] is False, \
            "FAIL: 账户角色不应拿到管理员的 first_login"
        print("PASS 9: first_login 不泄漏给账户角色")

        # ---- 旧 panel.json 数据兼容 ----
        old = {"id": 999, "name": "旧", "room_id": None, "bot_mode": "public",
               "expires_at": None, "created_at": "x", "updated_at": "y"}
        from core.account.manager import AccountRecord
        assert AccountRecord.from_dict(old).seen_changelog_version == ""
        print("PASS 10: 旧 panel.json 记录反序列化兼容")

        print("\n全部通过")


if __name__ == "__main__":
    main()
