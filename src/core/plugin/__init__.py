"""MIST 直播平台机器人框架 —— 插件核心实现层。

提供插件系统的完整实现：

- :class:`PluginManager` — 插件全生命周期管理
- :class:`PluginConfigManager` — 插件配置读写
- :class:`PluginPermissionManager` — 插件权限配置管理

.. versionadded:: 1.1
"""

from core.plugin.plugin_manager import PluginManager
from core.plugin.config_manager import PluginConfigManager
from core.plugin.permission_manager import PluginPermissionManager

__all__ = [
    "PluginManager",
    "PluginConfigManager",
    "PluginPermissionManager",
]
