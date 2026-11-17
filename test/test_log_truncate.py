"""启动日志截断测试（子进程隔离，避免动到仓库 logs/）。

每次进程启动时 core.logging 会清空当天的 bot_/error_ 日志，
但保留历史日期文件。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mismiss-log-truncate-"))
    logs = tmp / "logs"
    logs.mkdir()
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = datetime.fromtimestamp(
        datetime.now().timestamp() - 86400
    ).strftime("%Y-%m-%d")
    today_bot = logs / f"bot_{today}.log"
    today_err = logs / f"error_{today}.log"
    old_bot = logs / f"bot_{yesterday}.log"
    today_bot.write_text("OLD-TODAY\n", encoding="utf-8")
    today_err.write_text("OLD-ERROR\n", encoding="utf-8")
    old_bot.write_text("OLD-YESTERDAY\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT / "src")
    subprocess.run(
        [sys.executable, "-c", "import core.logging"],
        cwd=str(tmp), env=env, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    check("当天 bot 日志被截断", today_bot.read_text(encoding="utf-8") == "")
    check("当天 error 日志被截断", today_err.read_text(encoding="utf-8") == "")
    check(
        "历史日期日志保留",
        old_bot.read_text(encoding="utf-8").strip() == "OLD-YESTERDAY",
    )
    print("\n全部通过")


if __name__ == "__main__":
    main()
