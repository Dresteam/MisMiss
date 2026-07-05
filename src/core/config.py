"""服务器配置加载。

从项目根目录 ``config.yml`` 读取配置，提供嵌套键的便捷访问。
缺失的键自动回退到内置默认值。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml


# ------------------------------------------------------------------ #
# 内置默认值
# ------------------------------------------------------------------ #

_DEFAULTS: dict[str, Any] = {
    "server": {
        "data_dir": "data",
        "state_file": "server_state.json",
        "api_port": 18080,
        "web_port": 15173,
    },
    "bot": {
        "timer_interval": 60,
    },
    "plugin": {
        "pip_mirror": "https://pypi.tuna.tsinghua.edu.cn/simple",
    },
    "logging": {
        "dir": "logs",
    },
}


class ServerConfig:
    """服务器配置的只读包装。

    加载 ``config.yml``，缺失值回退到内置默认值。
    支持以点分隔路径访问嵌套键。

    用法::

        cfg = ServerConfig.load("config.yml")
        data_dir = cfg.get("server.data_dir")       # "data"
        interval = cfg.get("bot.timer_interval")     # 60
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        merged = _deep_copy(_DEFAULTS)
        if data:
            _deep_merge(merged, data)
        self._data = merged

    @classmethod
    def load(cls, config_path: str | None = None) -> "ServerConfig":
        """从 YAML 文件加载配置，合并默认值。

        :param config_path: 配置文件路径，默认为项目根目录的 ``config.yml``
        :return: 配置实例
        """
        if config_path is None:
            # PyInstaller --onefile: 从用户工作目录读取（可写副本）
            # 正常模式: 从项目根目录读取
            if getattr(sys, "frozen", False):
                config_path = str(Path(os.getcwd()) / "config.yml")
            else:
                config_path = str(
                    Path(__file__).resolve().parent.parent.parent / "config.yml"
                )

        loaded: dict[str, Any] = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    parsed = yaml.safe_load(f)
                if isinstance(parsed, dict):
                    loaded = parsed
            except (yaml.YAMLError, OSError) as e:
                import logging
                _log = logging.getLogger(__name__)
                _log.warning("配置文件加载失败，使用默认值: %s", e)

        return cls(loaded)

    # ------------------------------------------------------------------ #
    # 访问
    # ------------------------------------------------------------------ #

    def get(self, path: str, default: Any = None) -> Any:
        """以点分隔路径获取配置值。

        :param path: 点分隔的配置路径，如 ``"server.data_dir"``
        :param default: 路径不存在时的默认值
        :return: 配置值
        """
        keys = path.split(".")
        node: Any = self._data
        for key in keys:
            if isinstance(node, dict):
                node = node.get(key)
                if node is None:
                    return default
            else:
                return default
        return node

    def get_str(self, path: str, default: str = "") -> str:
        """获取字符串类型的配置值。"""
        val = self.get(path, default)
        return str(val) if val is not None else default

    def get_int(self, path: str, default: int = 0) -> int:
        """获取整数类型的配置值。"""
        val = self.get(path, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def get_float(self, path: str, default: float = 0.0) -> float:
        """获取浮点数类型的配置值。"""
        val = self.get(path, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def get_bool(self, path: str, default: bool = False) -> bool:
        """获取布尔类型的配置值。"""
        val = self.get(path, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "on", "y")
        return bool(val)

    # ------------------------------------------------------------------ #
    # dunder
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return f"ServerConfig({self._data!r})"


# ------------------------------------------------------------------ #
# 内部工具
# ------------------------------------------------------------------ #


def _deep_copy(data: dict[str, Any]) -> dict[str, Any]:
    """浅拷贝外层 + 深拷贝内层字典。"""
    import copy
    result: dict[str, Any] = {}
    for k, v in data.items():
        result[k] = copy.deepcopy(v) if isinstance(v, dict) else v
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """深度合并 override 到 base（原地修改）。"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
