"""PyInstaller 入口点 —— 将 MisMiss Web 控制台打包为独立可执行文件。

由 ``scripts/build.sh exe`` 或 ``scripts/build.ps1 -Mode Exe`` 调用。
构建产物为 ``dist/mismiss`` (Linux) 或 ``dist/mismiss.exe`` (Windows)，
目标机器无需安装 Python 或 Node.js。

**运行时目录策略**

PyInstaller ``--onefile`` 将所有文件解压到临时目录 ``sys._MEIPASS``，
程序退出后临时目录被清理。为避免丢失数据，本入口：

1. 以 **exe 所在目录** 为运行时根目录（数据始终在 exe 旁边）
2. 首次运行时从 bundle 中复制 ``config.yml`` 到 exe 目录
3. 自动创建 ``data/`` ``logs/`` ``plugins/`` ``permissions/`` 目录
4. 端口默认读取 ``config.yml`` 中的 ``server.api_port``，``--port`` 可覆盖
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _bundle_dir() -> Path:
    """PyInstaller 解压目录（只读，存放源码和前端）。"""
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", "."))
    return Path(__file__).resolve().parent.parent


def _bootstrap(runtime_home: Path, bundle: Path) -> Path:
    """首次运行引导：复制 config.yml，创建运行时目录。

    :returns: config.yml 的路径（始终指向 runtime_home 中的副本）
    """
    # ---- config.yml ----
    bundled_cfg = bundle / "config.yml"
    target_cfg = runtime_home / "config.yml"
    if not target_cfg.exists() and bundled_cfg.exists():
        print(f"[bootstrap] copy config.yml -> {target_cfg}")
        shutil.copy2(bundled_cfg, target_cfg)

    # ---- 运行时目录 ----
    for d in ("data", "logs", "plugins", "permissions"):
        p = runtime_home / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            print(f"[bootstrap] mkdir {p}/")

    return target_cfg


def _read_config_port(config_path: Path) -> int:
    """从 config.yml 读取 ``server.api_port``。"""
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        port = data.get("server", {}).get("api_port", 18080)
        return int(port)
    except Exception:
        return 18080


def main() -> None:
    # ---------------------------------------------------------------- #
    # 0. 确定运行时目录
    # ---------------------------------------------------------------- #
    if _is_frozen():
        runtime_home = Path(sys.executable).resolve().parent
    else:
        runtime_home = Path.cwd().resolve()
    bundle = _bundle_dir()

    # 首次引导（复制 config.yml、创建目录）
    config_path = _bootstrap(runtime_home, bundle)

    # ---------------------------------------------------------------- #
    # 1. 解析参数（默认端口从 config.yml 读取）
    # ---------------------------------------------------------------- #
    _default_port = _read_config_port(config_path)

    parser = argparse.ArgumentParser(
        description="MisMiss Web Console — 猫耳FM 直播场控机器人"
    )
    parser.add_argument(
        "--port", type=int, default=_default_port,
        help=f"端口 (默认 {_default_port}，来自 config.yml)"
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0",
        help="绑定地址 (默认 0.0.0.0)"
    )
    args = parser.parse_args()

    # ---------------------------------------------------------------- #
    # 2. 设置运行时环境
    # ---------------------------------------------------------------- #
    os.chdir(str(runtime_home))

    # 源码路径 → bundle（只读代码）
    for p in (bundle / "src", bundle / "web" / "backend"):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)

    # 环境变量 → 下游模块
    os.environ["MISMISS_HOME"] = str(runtime_home)
    os.environ["MISMISS_BUNDLE"] = str(bundle)
    os.environ["MISMISS_PROD"] = "1"

    # ---------------------------------------------------------------- #
    # 3. 启动
    # ---------------------------------------------------------------- #
    import uvicorn

    _host_display = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    _url = f"http://{_host_display}:{args.port}"

    print()
    print("=" * 60)
    print("  MisMiss Web Console v1.0.0")
    print("=" * 60)
    print()
    print(f"  >>  Web UI:  {_url}")
    print(f"  >>  API:     {_url}/docs")
    print()
    print(f"  Config:   {config_path}")
    print(f"  Data:     {runtime_home / 'data'}")
    print(f"  Logs:     {runtime_home / 'logs'}")
    print("=" * 60)
    print()

    uvicorn.run(
        "web.backend.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
