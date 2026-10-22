"""账户备注 / 昵称 / 临期提示开关的持久化测试（无网络）。

运行: .venv/Scripts/python.exe test/test_account_remark.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.account import AccountManager  # noqa: E402
from core.config import ServerConfig  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


async def main() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-remark-test-")
    cfg = ServerConfig({"server": {"data_dir": tmp}})
    manager = AccountManager(cfg)
    manager.load()

    rec = await manager.create_account(
        "原昵称", bot_mode="public", username="acct_remark",
    )
    check("新建账户默认开启临期提示", rec.expiry_notice_enabled is True)
    check("新建账户备注为空", rec.remark == "")

    # 备注 + 昵称 + 关闭提示
    updated = await manager.update_account(
        rec.id,
        name="新昵称",
        remark="这是管理端备注",
        expiry_notice_enabled=False,
    )
    check("昵称已更新", updated.name == "新昵称")
    check("备注已写入", updated.remark == "这是管理端备注")
    check("临期提示已关闭", updated.expiry_notice_enabled is False)

    snap = manager._account_snapshot(manager.get_record(rec.id))
    check("快照包含备注", snap["remark"] == "这是管理端备注")
    check("快照包含开关", snap["expiry_notice_enabled"] is False)

    # 重新加载：必须从 panel.json 恢复
    manager2 = AccountManager(cfg)
    manager2.load()
    reloaded = manager2.get_record(rec.id)
    check("重启后备注仍在", reloaded.remark == "这是管理端备注")
    check("重启后昵称仍在", reloaded.name == "新昵称")
    check("重启后开关仍关闭", reloaded.expiry_notice_enabled is False)

    # 备注可以清空（空串必须被写回，不能按「有值才更新」）
    await manager2.start_all()
    await manager2.update_account(rec.id, remark="")
    await manager2.shutdown_all()
    manager3 = AccountManager(cfg)
    manager3.load()
    check("备注可清空并落盘", manager3.get_record(rec.id).remark == "")

    # 账户自助开关
    manager3.set_expiry_notice_enabled(rec.id, True)
    manager4 = AccountManager(cfg)
    manager4.load()
    check("账户自助重新开启并落盘", manager4.get_record(rec.id).expiry_notice_enabled is True)

    await manager.shutdown_all()
    await manager4.shutdown_all()
    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
