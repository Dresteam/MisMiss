"""浏览器兜底发送 CLI（调试 / 运维用）。

示例::

    python scripts/browser_send.py --account 6 --room 869230856 --message "dd"
    python scripts/browser_send.py --cookie "FM_SESS=..." --room 869230856 --message "dd"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.browser import BrowserBridge, BrowserConfig
from core.config import ServerConfig


def _load_cookie(account: str, config_path: str) -> str:
    panel_path = ROOT / "data" / "panel.json"
    if panel_path.is_file():
        panel = json.loads(panel_path.read_text(encoding="utf-8"))
        if not account:
            public = (panel.get("public_bot") or {}).get("cookie", "")
            if public:
                return str(public)
    if not account:
        return ""
    state_path = ROOT / "data" / "accounts" / account / "server_state.json"
    if not state_path.is_file():
        return ""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return str((state.get("bot") or {}).get("cookie", "") or "")


async def _main() -> int:
    parser = argparse.ArgumentParser(description="MisMiss 浏览器发送兜底")
    parser.add_argument("--account", default="", help="账户 id；不传则用面板公共 Cookie")
    parser.add_argument("--cookie", default="", help="直接指定 Cookie")
    parser.add_argument("--room", type=int, required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--config", default="config.yml")
    args = parser.parse_args()

    cfg = ServerConfig.load(str(ROOT / args.config))
    browser_cfg = replace(BrowserConfig.from_server_config(cfg), enabled=True)
    cookie = (
        args.cookie.strip()
        or os.environ.get("MIS_COOKIE", "").strip()
        or _load_cookie(args.account, args.config)
    )
    if not cookie:
        print(json.dumps({"ok": False, "reason": "cookie_not_found"}, ensure_ascii=False))
        return 2
    bridge = BrowserBridge(browser_cfg)
    try:
        result = await bridge.send(cookie, args.room, args.message)
        print(json.dumps(result.__dict__, ensure_ascii=False))
        return 0 if result.ok else 1
    finally:
        await bridge.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
