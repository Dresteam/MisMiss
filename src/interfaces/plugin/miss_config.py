"""插件配置包装器。

提供类型安全的只读配置访问，同时保持与原生 dict 的兼容性。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class MissConfig:
    """插件配置的只读包装器。

    封装插件运行时配置字典，提供带默认值的类型化访问方法，
    同时支持 ``dict`` 风格的只读操作（``in``、迭代、``.items()`` 等）。

    配置由框架通过 :meth:`Plugin.initialize` 参数传入，
    插件若需在事件处理器中访问，应在 ``initialize`` 中保存为实例属性。

    用法示例::

        # initialize 钩子 —— 通过参数接收
        async def initialize(self, config: MissConfig) -> None:
            greeting = config.get("greeting", "Hello")
            if config.get("pinyin_enabled", False):
                ...
            # 保存供事件处理器使用
            self._config = config

        # 事件处理器 —— 通过自行保存的属性访问
        @event_handler
        def on_message(self, event: LiveMessageEvent) -> None:
            threshold = self._config.get("gift_threshold", 100.0)
            ...

    .. versionadded:: 1.2
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data if data is not None else {}

    # ------------------------------------------------------------------ #
    # 类型化访问
    # ------------------------------------------------------------------ #

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，键不存在时返回默认值。

        :param key: 配置键名
        :param default: 键不存在时的默认值
        :return: 配置值或默认值
        """
        return self._data.get(key, default)

    def get_str(self, key: str, default: str = "") -> str:
        """获取字符串类型的配置项。

        :param key: 配置键名
        :param default: 键不存在时的默认值
        :return: 字符串值
        """
        val = self._data.get(key, default)
        return str(val) if val is not None else default

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数类型的配置项。

        :param key: 配置键名
        :param default: 键不存在时的默认值
        :return: 整数值
        :raises ValueError: 值无法转换为 int
        """
        val = self._data.get(key)
        if val is None:
            return default
        return int(val)

    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点数类型的配置项。

        :param key: 配置键名
        :param default: 键不存在时的默认值
        :return: 浮点数值
        :raises ValueError: 值无法转换为 float
        """
        val = self._data.get(key)
        if val is None:
            return default
        return float(val)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔类型的配置项。

        :param key: 配置键名
        :param default: 键不存在时的默认值
        :return: 布尔值
        """
        val = self._data.get(key)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "on", "y")
        return bool(val)

    def get_list(self, key: str, default: list | None = None) -> list:
        """获取列表类型的配置项。

        :param key: 配置键名
        :param default: 键不存在时的默认值
        :return: 列表值
        """
        if default is None:
            default = []
        val = self._data.get(key)
        if val is None:
            return default
        if isinstance(val, list):
            return val
        return default

    # ------------------------------------------------------------------ #
    # 数据访问
    # ------------------------------------------------------------------ #

    @property
    def raw(self) -> dict[str, Any]:
        """获取原始配置字典的浅拷贝。

        用于需要直接操作 dict 的兼容场景。

        :return: 配置字典的浅拷贝
        """
        return dict(self._data)

    def to_dict(self) -> dict[str, Any]:
        """导出为普通 dict。

        :return: 配置字典的浅拷贝
        """
        return dict(self._data)

    # ------------------------------------------------------------------ #
    # dict 兼容协议（只读）
    # ------------------------------------------------------------------ #

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __bool__(self) -> bool:
        """空配置视为 falsy。"""
        return bool(self._data)

    def keys(self) -> Any:
        """返回配置键的视图。"""
        return self._data.keys()

    def values(self) -> Any:
        """返回配置值的视图。"""
        return self._data.values()

    def items(self) -> Any:
        """返回 (key, value) 对的视图。"""
        return self._data.items()

    # ------------------------------------------------------------------ #
    # dunder
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return f"MissConfig({self._data!r})"

    def __str__(self) -> str:
        return str(self._data)
