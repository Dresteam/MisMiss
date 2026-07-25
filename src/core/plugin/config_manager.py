"""插件配置管理器。

管理每个插件的运行时配置，基于 ``_conf_schema.json`` 定义配置项，
实际值存储在 ``data/config/{plugin_name}_config.json``。
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.exceptions import CorePluginConfigException
from core.logging import get_logger

_log = get_logger(__name__)

# ------------------------------------------------------------------ #
# 类型 → 默认值映射
# ------------------------------------------------------------------ #

_DEFAULT_VALUE_MAP: dict[str, Any] = {
    "string": "",
    "text": "",
    "int": 0,
    "integer": 0,
    "float": 0.0,
    "number": 0.0,
    "bool": False,
    "boolean": False,
    "object": {},
    "array": [],
    "list": [],
    "template_list": [],
}


class PluginConfigManager:
    """插件配置管理器。

    负责加载配置 schema、读写运行时配置值、生成默认配置。

    配置目录结构::

        data/config/
        ├── my_plugin_config.json    # 运行时配置值
        └── ...

    用法::

        mgr = PluginConfigManager("data/config")
        schema = mgr.load_schema("plugins/my_plugin/_conf_schema.json")
        config = mgr.load_config_with_defaults("my_plugin", schema)
        mgr.update_config_value("my_plugin", "key", "value")

    :param config_dir: 配置文件存储目录路径
    """

    def __init__(self, config_dir: str) -> None:
        self._config_dir = config_dir
        if config_dir:
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

    @staticmethod
    def generate_default_config(schema: dict) -> dict[str, Any]:
        """从 JSON Schema 生成带默认值的配置字典。

        遍历 schema 的每一项：
        - 若定义了 ``default`` 字段，使用该值
        - 否则根据 ``type`` 字段使用类型默认值
        - 对于 ``object`` 类型，递归处理 ``items`` 子 schema

        :param schema: ``_conf_schema.json`` 的内容（顶层 key → 字段定义）
        :return: 默认配置字典
        """
        conf: dict[str, Any] = {}

        for key, field_def in schema.items():
            if not isinstance(field_def, dict):
                conf[key] = None
                continue

            field_type = field_def.get("type", "string")

            if "default" in field_def:
                # 使用深拷贝防止可变默认值被意外共享
                conf[key] = deepcopy(field_def["default"])
            elif field_type == "object" and "items" in field_def:
                # 递归处理嵌套对象
                conf[key] = PluginConfigManager.generate_default_config(
                    field_def["items"]
                )
            else:
                conf[key] = deepcopy(
                    _DEFAULT_VALUE_MAP.get(field_type, "")
                )

        return conf

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

    def load_config_with_defaults(
        self,
        plugin_name: str,
        schema: dict,
    ) -> dict[str, Any]:
        """加载插件配置并与 schema 默认值合并。

        流程：
        1. 从 schema 生成默认配置
        2. 加载已保存的配置文件
        3. 用已保存的值覆盖默认值（深度合并）
        4. 仅当 schema 有新字段（保存的配置中缺失）时才写回

        :param plugin_name: 插件名称
        :param schema: ``_conf_schema.json`` 的内容
        :return: 合并后的完整配置字典
        """
        defaults = self.generate_default_config(schema)
        saved = self.load_config(plugin_name)

        merged = deepcopy(defaults)
        self._deep_merge(merged, saved)

        # 仅在 schema 新增字段（保存的配置中缺失）时才写回
        # 这样用户手动修改的值不会被重置
        missing_keys = [k for k in defaults if k not in saved]
        if missing_keys:
            _log.debug(
                "插件 [{}] 配置发现新字段 {}，自动补充",
                plugin_name,
                missing_keys,
            )
            self.save_config(plugin_name, merged)

        return merged

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

    def get_config_value(
        self, plugin_name: str, key: str, default: Any = None
    ) -> Any:
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

    def delete_config_file(self, plugin_name: str) -> None:
        """删除插件的配置文件。

        :param plugin_name: 插件名称
        """
        path = self._config_path(plugin_name)
        if os.path.exists(path):
            os.remove(path)
            _log.info("配置文件已删除: {}", path)

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """深度合并 override 到 base（原地修改 base）。

        对于嵌套字典，递归合并；对于其他类型，直接覆盖。

        :param base: 基础字典（原地修改）
        :param override: 覆盖字典
        """
        for key, value in override.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                PluginConfigManager._deep_merge(base[key], value)
            else:
                base[key] = deepcopy(value)
