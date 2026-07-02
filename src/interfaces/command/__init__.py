"""命令注解接口。

提供 ``@command`` 装饰器将插件方法声明为指令处理器，
自动解析直播间（或私信）消息为结构化指令调用。
"""

from interfaces.command.command import command, Scope

__all__ = ["command", "Scope"]
