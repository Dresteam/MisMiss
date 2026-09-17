"""应用版本号与本地更新日志读取。

版本号来源优先级：``MISMISS_VERSION`` 环境变量（Docker 构建时注入）>
``pyproject.toml`` 的 ``version`` 字段 > ``"0.0.0"`` 兜底。

更新日志取自 ``docs/changelog/v{版本}.md``。该目录必须随部署包一同分发，
否则生产环境（Docker / 源码包 / PyInstaller）读取为空——打包链见
``Dockerfile``、``scripts/release.*``、``mismiss.spec``。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from core.logging import get_logger

_log = get_logger(__name__)

_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# 版本号白名单——它会被拼进文件路径，需挡住 ``../`` 之类的逃逸
_SAFE_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-]*$")


def project_root() -> Path:
    """项目根目录。

    本文件位于 ``<root>/src/core/version.py``，上溯 3 级即根。开发模式、
    Docker（``/app/src/core/``）与 PyInstaller（``_MEIPASS/src/core/``）
    三种部署下均成立。
    """
    return Path(__file__).resolve().parent.parent.parent


def _detect_version() -> str:
    """解析当前应用版本号。"""
    env = os.environ.get("MISMISS_VERSION", "").strip()
    if env:
        return env.lstrip("v")
    try:
        text = (project_root() / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = _VERSION_RE.search(text)
    return match.group(1) if match else "0.0.0"


CURRENT_VERSION: str = _detect_version()


def changelog_path(version: str) -> Path | None:
    """更新日志文件路径；版本号非法时返回 ``None``。"""
    cleaned = version.strip().lstrip("v")
    if not _SAFE_VERSION_RE.match(cleaned):
        return None
    return project_root() / "docs" / "changelog" / f"v{cleaned}.md"


def load_changelog(version: str) -> dict | None:
    """读取指定版本的更新日志。

    :param version: 版本号（可带 ``v`` 前缀）
    :return: ``{"version": ..., "title": ..., "body": ...}``；
        版本号非法或文件不存在时返回 ``None``
    """
    path = changelog_path(version)
    if path is None:
        _log.warning("版本号非法，无法定位更新日志: {!r}", version)
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        _log.debug("更新日志不存在: {}", path)
        return None

    # 首个一级标题作为弹窗标题，正文不再重复该行
    title = f"MisMiss v{version.lstrip('v')}"
    body = content
    match = _H1_RE.search(content)
    if match:
        title = match.group(1)
        body = content[: match.start()] + content[match.end() :]

    return {
        "version": version.lstrip("v"),
        "title": title,
        "body": body.strip(),
    }
