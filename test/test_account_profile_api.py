"""管理端账户资料 API 测试（无网络）。

覆盖：
- PATCH /api/panel/accounts/{id} 可改昵称、备注、临期提示开关
- POST /api/accounts/{id}/preferences 两项偏好都可单独更新
- 返回的 AccountSummary 带 remark / expiry_notice_enabled

运行: .venv/Scripts/python.exe test/test_account_profile_api.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="mismiss-profile-api-")
os.environ["MISMISS_DATA_DIR"] = _TMP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

import web.backend.main as backend  # noqa: E402
from api.deps import set_account_manager  # noqa: E402
from api.routes.auth import _save_token  # noqa: E402
from core.account import AccountManager  # noqa: E402
from core.config import ServerConfig  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def main() -> None:
    async def setup():
        manager = AccountManager(ServerConfig({"server": {"data_dir": _TMP}}))
        manager.load()
        set_account_manager(manager)
        rec = await manager.create_account(
            "接口昵称", bot_mode="public", username="acct_profile",
        )
        return manager, rec

    manager, rec = asyncio.run(setup())

    token = "c" * 64
    _save_token(token, "MisMiss", 9e9, role="admin")
    headers = {"Authorization": f"Bearer {token}"}
    client = TestClient(backend.app)

    # 1. PATCH：昵称 + 备注 + 开关
    r = client.patch(
        f"/api/panel/accounts/{rec.id}",
        headers=headers,
        json={
            "name": "改过的昵称",
            "remark": "API 备注",
            "expiry_notice_enabled": False,
        },
    )
    check("PATCH 账户资料成功", r.status_code == 200, f"实际 {r.status_code}: {r.text}")
    body = r.json()
    check("响应昵称已更新", body["name"] == "改过的昵称", str(body.get("name")))
    check("响应带备注", body["remark"] == "API 备注", str(body.get("remark")))
    check("响应带开关", body["expiry_notice_enabled"] is False)

    # 2. 登录用户名不受影响
    check("登录用户名未变", manager.get_record(rec.id).username == "acct_profile")

    # 2.1 备注仅管理端可见：账户本人读 /info 时被剔除
    account_token = "d" * 64
    _save_token(account_token, rec.username, 9e9, role="account", account_id=rec.id)
    r = client.get(f"/api/accounts/{rec.id}/info", headers=headers)
    check("管理员能读到备注", r.status_code == 200 and r.json()["remark"] == "API 备注")
    r = client.get(
        f"/api/accounts/{rec.id}/info",
        headers={"Authorization": f"Bearer {account_token}"},
    )
    check("账户本人读不到备注", r.status_code == 200 and r.json()["remark"] == "")

    # 3. 偏好接口：只改临期提示，不动自动启用
    r = client.post(
        f"/api/accounts/{rec.id}/preferences",
        headers=headers,
        json={"expiry_notice_enabled": True},
    )
    check("偏好接口成功", r.status_code == 200, f"实际 {r.status_code}: {r.text}")
    check("临期提示重新开启", r.json()["expiry_notice_enabled"] is True)
    check(
        "自动启用偏好未被误改",
        r.json()["auto_enable_on_install"] is False,
    )

    # 4. 只改自动启用，不动临期提示
    r = client.post(
        f"/api/accounts/{rec.id}/preferences",
        headers=headers,
        json={"auto_enable_on_install": True},
    )
    check("自动启用已开启", r.json()["auto_enable_on_install"] is True)
    check("临期提示保持开启", r.json()["expiry_notice_enabled"] is True)

    # 5. 备注可清空
    r = client.patch(
        f"/api/panel/accounts/{rec.id}",
        headers=headers,
        json={"remark": ""},
    )
    check("备注可清空", r.status_code == 200 and r.json()["remark"] == "")

    # 6. 插件名带路径穿越必须被拒（否则 join/rmtree 会跑出账户目录）
    r = client.post(
        f"/api/accounts/{rec.id}/plugins/install",
        headers=headers,
        json={"name": "../../evil"},
    )
    check("插件安装拒绝路径穿越", r.status_code == 400, f"实际 {r.status_code}: {r.text}")
    check(
        "未在账户目录外写入",
        not os.path.exists(os.path.join(_TMP, "evil")),
    )

    asyncio.run(manager.shutdown_all())
    print("\n全部通过")


if __name__ == "__main__":
    main()
