"""MIST 直播平台机器人框架 —— 插件接口层。

本包定义了插件系统的全部抽象接口：

- :class:`Plugin` — 插件基类（继承 :class:`Listener`）
- :class:`PluginMetadata` — 插件元数据

用法示例::

    from interfaces.plugin import Plugin, PluginMetadata

.. versionadded:: 1.1
"""

from interfaces.plugin.plugin import Plugin
from interfaces.plugin.plugin_metadata import PluginMetadata

__all__ = [
    "Plugin",
    "PluginMetadata",
]
