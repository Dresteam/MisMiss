"""单服务器旧数据迁移 —— 多账户升级时备份旧运行时数据(全新开始)。

保留 ``auth.json``(面板管理员登录无缝延续),其余旧运行时数据
(server_state.json、data/config、data/plugins、data/permissions、tokens)
移动到 ``data/backup/pre-multiaccount-<时间戳>/``。
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

from core.logging import get_logger

_log = get_logger(__name__)

_LEGACY_ITEMS = ("server_state.json", "config", "plugins", "permissions", "tokens")


def migrate_legacy_data(root: str) -> bool:
    """执行旧数据备份迁移(幂等)。

    :param root: data 目录路径
    :return: 是否执行了迁移
    """
    panel_path = os.path.join(root, "panel.json")
    if os.path.exists(panel_path):
        return False  # 已迁移过(或全新安装后已初始化)

    def _non_empty(name: str) -> bool:
        """目录仅在非空时视为旧数据(空目录如 tokens/ 可能是运行时刚创建的)。"""
        path = os.path.join(root, name)
        if not os.path.exists(path):
            return False
        if os.path.isfile(path):
            return True
        return bool(os.listdir(path))

    existing = [n for n in _LEGACY_ITEMS if _non_empty(n)]
    if not existing:
        # 全新安装:只创建账户目录,不产生备份
        os.makedirs(os.path.join(root, "accounts"), exist_ok=True)
        return False

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(root, "backup", f"pre-multiaccount-{ts}")
    os.makedirs(backup_dir, exist_ok=True)
    for name in existing:
        shutil.move(os.path.join(root, name), os.path.join(backup_dir, name))

    os.makedirs(os.path.join(root, "accounts"), exist_ok=True)
    # 写初始空面板(与 AccountManager.load 的初始化一致)
    initial = {
        "schema_version": 1,
        "next_account_id": 1,
        "public_bot": {"cookie": "", "permissions": 1, "updated_at": 0},
        "accounts": {},
        "licenses": {},
    }
    tmp_path = panel_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(initial, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, panel_path)

    _log.info(
        "旧单服务器数据已备份到 {} ({} 项),面板将全新开始",
        backup_dir, len(existing),
    )
    return True
