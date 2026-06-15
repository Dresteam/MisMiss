"""插件配置管理器。

管理每个插件的运行时配置，基于 ``_conf_schema.json`` 定义配置项，
实际值存储在 ``data/config/{plugin_name}_config.json``。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.exceptions import CorePluginConfigException
from core.logging import get_logger

_log = get_logger(__name__)


class PluginConfigManager:
    """插件配置管理器。

    负责加载配置 schema、读写运行时配置值。

    配置目录结构::

        data/config/
        ├── my_plugin_config.json    # 运行时配置值
        └── ...

    用法::

        mgr = PluginConfigManager("data/config")
        config = mgr.load_config("my_plugin")
        mgr.update_config_value("my_plugin", "key", "value")

    :param config_dir: 配置文件存储目录路径
    """

    def __init__(self, config_dir: str) -> None:
        self._config_dir = config_dir
        Path(self._config_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #

    @staticmethod
    def load_schema(schema_path: str) -> dict[str, Any]:
        """加载 ``_conf_schema.json``。

        若文件不存在则返回空字典。

        :param schema_path: schema 文件的绝对路径
        :return: schema 字典
        :raises CorePluginConfigException: JSON 解析失败
        """
        if not os.path.exists(schema_path):
            _log.debug("Schema 文件不存在: {}", schema_path)
            return {}

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            if not isinstance(schema, dict):
                _log.warning("Schema 格式无效（非对象），返回空字典")
                return {}
            return schema
        except json.JSONDecodeError as e:
            raise CorePluginConfigException(
                plugin_name=os.path.basename(os.path.dirname(schema_path)),
                reason=f"Schema JSON 解析失败: {e}",
            )

    # ------------------------------------------------------------------ #
    # 配置读写
    # ------------------------------------------------------------------ #

    def _config_path(self, plugin_name: str) -> str:
        """获取插件配置文件路径。

        :param plugin_name: 插件名称
        :return: 配置文件绝对路径
        """
        safe_name = plugin_name.replace("/", "_").replace("\\", "_")
        return os.path.join(self._config_dir, f"{safe_name}_config.json")

    def load_config(self, plugin_name: str) -> dict[str, Any]:
        """加载插件的运行时配置。

        若配置文件不存在则返回空字典。

        :param plugin_name: 插件名称
        :return: 配置字典
        :raises CorePluginConfigException: JSON 解析失败
        """
        path = self._config_path(plugin_name)
        if not os.path.exists(path):
            _log.debug("配置文件不存在，返回空字典: {}", path)
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                _log.warning("配置文件格式无效（非对象）: {}", path)
                return {}
            return data
        except json.JSONDecodeError as e:
            raise CorePluginConfigException(
                plugin_name=plugin_name,
                reason=f"配置 JSON 解析失败: {e}",
            )

    def save_config(self, plugin_name: str, config: dict[str, Any]) -> None:
        """保存插件的运行时配置。

        :param plugin_name: 插件名称
        :param config: 配置字典
        :raises CorePluginConfigException: 写入失败
        """
        path = self._config_path(plugin_name)
        try:
            Path(self._config_dir).mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            _log.debug("配置已保存: {}", path)
        except OSError as e:
            raise CorePluginConfigException(
                plugin_name=plugin_name,
                reason=f"保存配置失败: {e}",
            )

    def get_config_value(self, plugin_name: str, key: str, default: Any = None) -> Any:
        """获取单个配置项的值。

        :param plugin_name: 插件名称
        :param key: 配置键
        :param default: 默认值（键不存在时返回）
        :return: 配置值或默认值
        """
        config = self.load_config(plugin_name)
        return config.get(key, default)

    def update_config_value(
        self, plugin_name: str, key: str, value: Any
    ) -> None:
        """更新单个配置项的值。

        :param plugin_name: 插件名称
        :param key: 配置键
        :param value: 新值
        """
        config = self.load_config(plugin_name)
        config[key] = value
        self.save_config(plugin_name, config)

    def delete_config_value(self, plugin_name: str, key: str) -> None:
        """删除单个配置项。

        :param plugin_name: 插件名称
        :param key: 配置键
        """
        config = self.load_config(plugin_name)
        if key in config:
            del config[key]
            self.save_config(plugin_name, config)
