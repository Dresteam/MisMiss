"""插件权限管理器。

Server 自动为每个插件分配默认权限（对标 ``BotPermission`` 默认值），
实际权限值持久化存储在 ``data/permissions/{name}_permissions.json``，
管理员可通过 Server API 逐项修改。

权限生效规则
------------
1. 首次加载 → Server 自动分配默认权限（与 Bot 默认一致，仅 ``SEND_LIVESTREAM_MESSAGE``）
2. 管理员通过 ``update_plugin_permission`` 修改 → 立即持久化
3. 最终生效 = 已启用的权限 ∩ Bot 实际拥有的权限（Bot 为天花板）

.. versionchanged:: 1.2
    去掉 ``_permission.json`` 声明文件，改为 Server 自动配置默认权限。
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from interfaces.bot import BotPermission
from core.exceptions import CorePluginPermissionException
from core.logging import get_logger

if TYPE_CHECKING:
    from interfaces.bot.bot import Bot

_log = get_logger(__name__)


class PluginPermissionManager:
    """插件权限管理器。

    管理每个插件的 ``BotPermission`` 权限字典（key → bool），
    支持本地持久化和逐项修改。

    插件不再需要 ``_permission.json``——Server 自动分配默认权限，
    与 Bot 自身权限体系内聚。

    用法::

        ppm = PluginPermissionManager("data/permissions")
        perms = ppm.ensure_permissions("my_plugin")        # 自动分配默认值
        ppm.update_permission("my_plugin", "SEND_GIFT", True)  # 授予权限
        flag = ppm.to_bot_permission(perms)                     # 转为 Flag

    :param permission_dir: 权限配置文件存储目录
    """

    def __init__(self, permission_dir: str) -> None:
        self._permission_dir = permission_dir
        Path(self._permission_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 默认权限
    # ------------------------------------------------------------------ #

    @staticmethod
    def default_permissions() -> dict[str, bool]:
        """生成插件默认权限字典。

        对标 Bot 默认权限：仅 ``SEND_LIVESTREAM_MESSAGE`` 为 ``True``，
        其余所有 ``BotPermission`` 成员默认为 ``False``。

        :return: 权限字典（key → bool）
        """
        return PluginPermissionManager.to_dict(
            BotPermission.SEND_LIVESTREAM_MESSAGE
        )

    # ------------------------------------------------------------------ #
    # 权限读写（持久化）
    # ------------------------------------------------------------------ #

    def _permission_path(self, plugin_name: str) -> str:
        """获取插件权限配置文件路径。"""
        safe_name = plugin_name.replace("/", "_").replace("\\", "_")
        return os.path.join(
            self._permission_dir, f"{safe_name}_permissions.json"
        )

    def load_permissions(self, plugin_name: str) -> dict[str, bool] | None:
        """加载已持久化的权限值。

        :param plugin_name: 插件名称
        :return: 权限字典，文件不存在或格式无效则返回 ``None``
        """
        path = self._permission_path(plugin_name)
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                _log.warning("权限配置文件格式无效: {}", path)
                return None
            # 确保值都是 bool
            return {str(k): bool(v) for k, v in data.items()}
        except json.JSONDecodeError as e:
            _log.warning("权限配置文件 JSON 解析失败 [{}]: {}", plugin_name, e)
            return None

    def ensure_permissions(self, plugin_name: str) -> dict[str, bool]:
        """获取插件的权限配置，首次访问时自动分配默认值。

        流程：
        1. 尝试从磁盘加载已持久化的权限
        2. 若不存在，生成默认权限并保存
        3. 若已存在但缺少新的 ``BotPermission`` 成员，自动补充（默认 ``False``）

        :param plugin_name: 插件名称
        :return: 完整的权限字典
        """
        saved = self.load_permissions(plugin_name)
        defaults = self.default_permissions()

        if saved is None:
            # 首次加载 — 使用默认值
            merged = deepcopy(defaults)
            self.save_permissions(plugin_name, merged)
            _log.info(
                "插件 [{}] 首次加载，已分配默认权限: {}",
                plugin_name,
                [k for k, v in merged.items() if v],
            )
            return merged

        # 已持久化 — 合并可能新增的权限项
        merged = deepcopy(defaults)
        self._deep_merge(merged, saved)

        # 若 schema 有新权限项，写回
        new_keys = [k for k in defaults if k not in saved]
        if new_keys:
            _log.debug(
                "插件 [{}] 发现新权限项 {}，自动补充（默认 False）",
                plugin_name,
                new_keys,
            )
            self.save_permissions(plugin_name, merged)

        return merged

    def save_permissions(
        self, plugin_name: str, permissions: dict[str, bool]
    ) -> None:
        """保存权限配置到磁盘。

        :param plugin_name: 插件名称
        :param permissions: 权限字典
        :raises CorePluginPermissionException: 写入失败
        """
        path = self._permission_path(plugin_name)
        try:
            Path(self._permission_dir).mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(permissions, f, ensure_ascii=False, indent=2)
            _log.debug("权限配置已保存: {}", path)
        except OSError as e:
            raise CorePluginPermissionException(
                plugin_name=plugin_name,
                reason=f"保存权限配置失败: {e}",
            )

    def update_permission(
        self, plugin_name: str, key: str, value: bool
    ) -> None:
        """更新单个权限项并立即持久化。

        :param plugin_name: 插件名称
        :param key: 权限键名（如 ``"SEND_GIFT"``，必须为 ``BotPermission`` 成员名）
        :param value: ``True`` 启用，``False`` 禁用
        :raises CorePluginPermissionException: 无效的权限名
        """
        # 确保已初始化
        perms = self.ensure_permissions(plugin_name)

        if key not in perms:
            raise CorePluginPermissionException(
                plugin_name=plugin_name,
                reason=(
                    f"无效的权限名 '{key}'，"
                    f"有效值: {list(perms.keys())}"
                ),
            )

        perms[key] = value
        self.save_permissions(plugin_name, perms)

    def delete_permissions(self, plugin_name: str) -> None:
        """删除插件的权限配置文件（卸载时调用）。

        :param plugin_name: 插件名称
        """
        path = self._permission_path(plugin_name)
        if os.path.exists(path):
            os.remove(path)
            _log.info("权限配置文件已删除: {}", path)

    # ------------------------------------------------------------------ #
    # BotPermission Flag 转换
    # ------------------------------------------------------------------ #

    @staticmethod
    def to_bot_permission(permissions: dict[str, bool]) -> BotPermission:
        """将权限字典中所有值为 ``True`` 的键转换为 ``BotPermission`` Flag。

        :param permissions: 权限字典（key → bool）
        :return: ``BotPermission`` Flag 组合
        """
        result = BotPermission(0)
        for key, enabled in permissions.items():
            if not enabled:
                continue
            try:
                result |= BotPermission[key]
            except KeyError:
                _log.warning("跳过无效的权限名: {}", key)
        return result

    @staticmethod
    def to_dict(flag: BotPermission) -> dict[str, bool]:
        """将 ``BotPermission`` Flag 展开为权限字典（所有已知成员）。

        :param flag: 权限 Flag
        :return: 权限字典（key → bool）
        """
        return {perm.name: bool(flag & perm) for perm in BotPermission}

    # ------------------------------------------------------------------ #
    # 校验（以 Bot 实际权限为天花板）
    # ------------------------------------------------------------------ #

    @staticmethod
    def check_bot_permissions(
        bot: "Bot",
        required: BotPermission,
        plugin_name: str = "",
    ) -> list[str]:
        """校验 Bot 是否满足所需的权限。

        :param bot: 当前 Bot 实例
        :param required: 插件生效的权限 Flag
        :param plugin_name: 插件名称（日志用）
        :return: 缺失的权限名列表（空列表 = 全部满足）
        """
        missing: list[str] = []
        for perm in BotPermission:
            if (required & perm) and not (bot.permissions & perm):
                missing.append(perm.name)

        if missing:
            _log.warning(
                "插件 [{}] 需要 {} 权限，但 Bot 尚未授予",
                plugin_name or "(unknown)",
                missing,
            )

        return missing

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """深度合并 override 到 base（原地修改 base）。"""
        for key, value in override.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                PluginPermissionManager._deep_merge(base[key], value)
            else:
                base[key] = deepcopy(value)
