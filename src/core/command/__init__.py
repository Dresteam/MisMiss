"""MIST 直播平台机器人框架 —— 命令系统实现。

提供 ``@command`` 装饰器的运行时支持：
- :class:`CommandRouter` — 扫描、注册、路由指令调用
"""

from core.command.router import CommandRouter

__all__ = ["CommandRouter"]
