"""MisMiss CLI 入口包装器。

当项目通过 ``pip install`` 安装后，此模块作为 ``mismiss`` 命令的入口点。
它会设置正确的 sys.path 以便 ``from core import ...`` 等导入正常工作。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def main() -> None:
    """CLI 主入口 —— 设置路径后委托给 ``src.cli.main``。"""
    _PKG_ROOT = Path(__file__).resolve().parent
    os.chdir(str(_PKG_ROOT))

    # 确保 src/ 在搜索路径中（flat-layout 项目结构）
    _src = _PKG_ROOT / "src"
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    if str(_PKG_ROOT) not in sys.path:
        sys.path.insert(0, str(_PKG_ROOT))

    from src.cli import main as _cli_main

    try:
        asyncio.run(_cli_main())
    except KeyboardInterrupt:
        print("")


if __name__ == "__main__":
    main()
