"""命令路由器。

扫描插件上 ``@command`` 标记的方法，自动注册消息监听器，
将用户发送的文本消息解析为结构化指令调用。

消息格式::

    <指令名> [arg1] [arg2] ...

参数按位置匹配方法形参，类型通过注解转换。
"""

from __future__ import annotations

import inspect
import shlex
from collections import defaultdict
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from interfaces.command.command import Scope, _COMMAND_META_KEY
from interfaces.event import Listener, event_handler
from interfaces.event.livestream import LiveMessageEvent

if TYPE_CHECKING:
    from interfaces.plugin.plugin import Plugin

# ------------------------------------------------------------------ #
# 已注册指令的运行时描述
# ------------------------------------------------------------------ #


class _CommandEntry:
    """单个已注册指令的内部描述。"""

    __slots__ = (
        "name", "aliases", "scope", "plugin", "method",
        "param_names", "param_types", "has_varargs",
    )

    def __init__(
        self,
        name: str,
        aliases: list[str],
        scope: Scope,
        plugin: Plugin,
        method: Callable[..., Any],
    ) -> None:
        self.name = name
        self.aliases = aliases
        self.scope = scope
        self.plugin = plugin
        self.method = method

        # 解析方法签名
        # 注意：getattr(instance, 'method') 返回绑定方法，
        # inspect.signature 已自动去除 self，无需再次跳过
        sig = inspect.signature(method)
        params = list(sig.parameters.values())
        self.param_names: list[str] = []
        self.param_types: dict[str, type] = {}
        self.has_varargs = False

        for p in params:
            if p.kind in (inspect.Parameter.VAR_POSITIONAL,):
                self.has_varargs = True
                self.param_names.append("*")
                break
            self.param_names.append(p.name)
            ann = p.annotation
            if ann is inspect.Parameter.empty:
                self.param_types[p.name] = str
            else:
                self.param_types[p.name] = ann

    @property
    def all_names(self) -> list[str]:
        """返回主名 + 所有别名。"""
        return [self.name] + self.aliases


# ------------------------------------------------------------------ #
# 命令路由器
# ------------------------------------------------------------------ #


class CommandRouter:
    """命令路由器。

    扫描 ``Plugin`` 实例上 ``@command`` 标记的方法，
    注册为消息监听器，自动解析和路由指令。

    用法::

        router = CommandRouter(event_bus)
        router.register_plugin(plugin_instance)
    """

    def __init__(self, event_bus: Any) -> None:
        # name -> _CommandEntry
        self._commands: dict[str, _CommandEntry] = defaultdict()
        self._event_bus = event_bus
        self._listener: _CommandDispatchListener | None = None

    # ------------------------------------------------------------------ #
    # 注册 / 注销
    # ------------------------------------------------------------------ #

    def register_plugin(self, plugin: "Plugin") -> None:
        """扫描插件上所有 ``@command`` 方法并注册。

        :param plugin: 插件实例
        """
        count = 0
        for attr_name in dir(plugin):
            method = getattr(plugin, attr_name, None)
            if not callable(method):
                continue
            meta = getattr(method, _COMMAND_META_KEY, None)
            if meta is None:
                continue

            entry = _CommandEntry(
                name=meta["name"],
                aliases=meta["alias"],
                scope=meta["scope"],
                plugin=plugin,
                method=method,
            )

            # 注册主名和所有别名
            for name in entry.all_names:
                if name in self._commands:
                    existing = self._commands[name]
                    raise ValueError(
                        f"指令名冲突: '{name}' 已被 "
                        f"'{existing.plugin.name}.{existing.method.__name__}' 注册，"
                        f"'{plugin.name}.{method.__name__}' 无法覆盖"
                    )
                self._commands[name] = entry

            count += 1

        if count > 0:
            self._ensure_listener()

    def unregister_plugin(self, plugin: "Plugin") -> None:
        """移除插件的所有指令注册。

        :param plugin: 插件实例
        """
        to_remove = [
            name
            for name, entry in self._commands.items()
            if entry.plugin is plugin
        ]
        for name in to_remove:
            del self._commands[name]

        if not self._commands and self._listener is not None:
            self._event_bus.unregister_event(self._listener)
            self._listener = None

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def list_commands(self) -> dict[str, list[str]]:
        """列出所有已注册的指令（用于调试）。

        :return: 插件名 → 指令名列表 的映射
        """
        result: dict[str, list[str]] = defaultdict(list)
        seen: set[tuple[str, str]] = set()
        for name, entry in self._commands.items():
            key = (entry.plugin.name, entry.name)
            if key not in seen:
                result[entry.plugin.name].append(entry.name)
                seen.add(key)
        return dict(result)

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _ensure_listener(self) -> None:
        """确保消息监听器已注册到 EventBus。"""
        if self._listener is not None:
            return
        self._listener = _CommandDispatchListener(self)
        self._event_bus.register_new_event(self._listener)


# ------------------------------------------------------------------ #
# 消息监听器（内部类）
# ------------------------------------------------------------------ #


class _CommandDispatchListener(Listener):
    """内部监听器——拦截直播间/私信消息并分发到匹配的指令处理器。"""

    def __init__(self, router: CommandRouter) -> None:
        self._router = router

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        """收到直播间消息 → 匹配指令 → 调用处理器。"""
        text = event.message.strip()
        if not text:
            return

        # 解析指令名和参数
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()

        if not parts:
            return

        cmd_name = parts[0].lower()
        raw_args = parts[1:]

        # 查找匹配的指令
        entry = self._router._commands.get(cmd_name)  # noqa: SLF001
        if entry is None:
            return  # 不是指令，静默忽略

        if not (entry.scope & Scope.LIVEMESSAGE):
            return  # 作用域不匹配

        # 解析参数并调用
        parsed_args = _parse_args(entry, raw_args)
        entry.method(*parsed_args)


# ------------------------------------------------------------------ #
# 参数解析
# ------------------------------------------------------------------ #


def _parse_args(entry: _CommandEntry, raw_args: list[str]) -> list[Any]:
    """将字符串参数列表按方法签名转换为类型化参数。

    :param entry: 指令条目
    :param raw_args: 原始字符串参数
    :return: 转换后的参数列表
    """
    result: list[Any] = []

    for i, param_name in enumerate(entry.param_names):
        if param_name == "*":
            # 可变参数 —— 剩余全部作为字符串
            result.extend(raw_args[i:])
            break

        target_type = entry.param_types.get(param_name, str)

        if i < len(raw_args):
            result.append(_convert(raw_args[i], target_type))
        else:
            # 参数不足 —— 尝试取默认值
            # entry.method 是绑定方法，signature 已去除 self
            sig = inspect.signature(entry.method)
            param = list(sig.parameters.values())[i]
            if param.default is not inspect.Parameter.empty:
                result.append(param.default)
            else:
                raise TypeError(
                    f"指令 '{entry.name}' 缺少必需参数 '{param_name}'"
                )

    return result


def _convert(value: str, target_type: type) -> Any:
    """将字符串值转换为目标类型。

    :param value: 原始字符串
    :param target_type: 目标类型
    :return: 转换后的值
    """
    if target_type is str:
        return value
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is bool:
        return value.lower() in ("true", "1", "yes", "on", "y")
    # 未知类型，保持字符串
    return value
