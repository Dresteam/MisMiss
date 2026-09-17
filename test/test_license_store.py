"""LicenseStore 与数据迁移测试(无网络)。

运行: docker run --rm -v <repo>:/src -w /src mismiss:latest python /src/test/test_license_store.py
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.account import AccountManager, migrate_legacy_data  # noqa: E402
from core.account.license import LicenseStore  # noqa: E402
from core.config import ServerConfig  # noqa: E402
from core.exceptions import CoreLicenseException  # noqa: E402


def test_license_pure_logic():
    store = LicenseStore({})
    codes = store.generate(5, 30, "测试批次")
    assert len(codes) == 5 and len(set(codes)) == 5
    assert all(c.startswith("MM-") and len(c) == 17 for c in codes)  # MM-XXXX-XXXX-XXXX
    assert all(ch not in "0O1IL" for ch in "".join(codes).replace("-", "").replace("M", ""))
    # 兑换
    days = store.redeem(codes[0], 1)
    assert days == 30
    try:
        store.redeem(codes[0], 2)
        raise AssertionError("FAIL: 已用码再次兑换未报错")
    except CoreLicenseException:
        pass
    # 撤销
    store.revoke(codes[1])
    assert codes[1] not in store.all
    try:
        store.revoke(codes[0])
        raise AssertionError("FAIL: 已用码撤销未报错")
    except CoreLicenseException:
        pass
    # 批量上限
    try:
        store.generate(101, 1)
        raise AssertionError("FAIL: 超量生成未报错")
    except CoreLicenseException:
        pass
    print("PASS 1: LicenseStore 生成/兑换/撤销/边界")


async def test_manager_redeem():
    tmp = tempfile.mkdtemp(prefix="mismiss-license-test-")
    cfg = ServerConfig({"server": {"data_dir": tmp}})
    manager = AccountManager(cfg)
    manager.load()
    # 必须用限期账户——永久账户兑换会被拒绝且不消耗码（见 test_permanent_account.py）
    rec = await manager.create_account(
        "兑换账户", bot_mode="public", username="redeemer", duration_days=1
    )
    codes = manager.generate_licenses(2, 7)
    result = await manager.redeem(rec.id, codes[0])
    assert result.days_left == 8, f"FAIL: 1+7 应为 8, 实际 {result.days_left}"
    assert manager.list_licenses()[0]["used_by_account_id"] == rec.id or \
        any(x["used_by_account_id"] == rec.id for x in manager.list_licenses())
    # 叠加
    result2 = await manager.redeem(rec.id, codes[1])
    assert result2.days_left == 15, f"FAIL: 8+7 应为 15, 实际 {result2.days_left}"
    print("PASS 2: 兑换叠加天数")


def test_migration():
    tmp = tempfile.mkdtemp(prefix="mismiss-migration-test-")
    # 构造旧版数据目录
    with open(os.path.join(tmp, "server_state.json"), "w", encoding="utf-8") as f:
        json.dump({"livestreams": [123], "bot": {"cookie": "old", "permissions": 1}}, f)
    os.makedirs(os.path.join(tmp, "config"))
    with open(os.path.join(tmp, "config", "welcome_config.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    os.makedirs(os.path.join(tmp, "tokens"))
    with open(os.path.join(tmp, "tokens", "abc123"), "w", encoding="utf-8") as f:
        json.dump({"username": "MisMiss", "expires": 9999999999}, f)
    with open(os.path.join(tmp, "auth.json"), "w", encoding="utf-8") as f:
        json.dump({"username": "MisMiss", "password": "x", "first_login": False}, f)

    moved = migrate_legacy_data(tmp)
    assert moved is True
    assert os.path.exists(os.path.join(tmp, "auth.json")), "FAIL: auth.json 未保留"
    assert os.path.exists(os.path.join(tmp, "panel.json"))
    assert not os.path.exists(os.path.join(tmp, "server_state.json"))
    backups = [d for d in os.listdir(os.path.join(tmp, "backup"))
               if d.startswith("pre-multiaccount-")]
    assert len(backups) == 1
    bdir = os.path.join(tmp, "backup", backups[0])
    assert os.path.exists(os.path.join(bdir, "server_state.json"))
    assert os.path.exists(os.path.join(bdir, "config", "welcome_config.json"))
    assert os.path.exists(os.path.join(bdir, "tokens"))
    # 幂等
    assert migrate_legacy_data(tmp) is False
    print("PASS 3: 迁移备份(含幂等与 auth.json 保留)")


if __name__ == "__main__":
    test_license_pure_logic()
    asyncio.run(test_manager_redeem())
    test_migration()
    print("\n全部通过")
