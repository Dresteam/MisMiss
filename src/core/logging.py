"""日志模块。

基于 ``loguru`` 提供统一的日志管理，支持：
- 按时间 / 大小自动分割日志文件
- 自动输出调用类名
- 控制台 + 文件双通道输出
- 异常堆栈自动美化
- 按级别 / 时间段 / 源文件 / 关键字筛选
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from loguru import logger as _logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from loguru import Record


# ================================================================ #
# 默认配置
# ================================================================ #

_LOG_DIR: Path = Path("logs")
_LOG_FORMAT: str = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[class_name]}</cyan>:<cyan>{extra[func_name]}</cyan> | "
    "<level>{message}</level>"
)

_initialized: bool = False


# ================================================================ #
# 协议 —— 消除 IDE 类型警告
# ================================================================ #

class LoggerProtocol(Protocol):
    """日志记录器协议——定义 _LoggerProxy 的公开接口。"""

    def debug(self, message: str, *args, **kwargs) -> None: ...
    def info(self, message: str, *args, **kwargs) -> None: ...
    def warning(self, message: str, *args, **kwargs) -> None: ...
    def warn(self, message: str, *args, **kwargs) -> None: ...
    def error(self, message: str, *args, **kwargs) -> None: ...
    def exception(self, message: str, *args, **kwargs) -> None: ...
    def critical(self, message: str, *args, **kwargs) -> None: ...


# ================================================================ #
# 过滤器
# ================================================================ #

@dataclass
class LogFilter:
    """日志过滤器。

    支持组合条件筛选，所有非 ``None`` / 非空条件为 AND 关系。
    传入 :func:`add_filter` 即可生效。

    用法::

        from core.logging import LogFilter, add_filter

        # 只看 DemoService 的 ERROR
        add_filter(LogFilter(level="ERROR", source="demo"))

        # 只看含关键字 "礼物" 的消息
        add_filter(LogFilter(keyword="礼物"))

        # 清除所有过滤器
        clear_filters()
    """

    level: str | None = None
    """最低显示级别（``"DEBUG"`` / ``"INFO"`` / ``"WARNING"`` / ``"ERROR"``）"""

    source: str | None = None
    """调用源文件过滤器（模糊匹配，如 ``"mis_bot"`` 可匹配 ``mis_bot.py``）"""

    keyword: str | None = None
    """消息关键字过滤器（模糊匹配日志内容）"""

    time_from: str | None = None
    """时间段起始，格式 ``"HH:MM"``，如 ``"08:00"``"""

    time_to: str | None = None
    """时间段结束，格式 ``"HH:MM"``，如 ``"22:00"``"""


def add_filter(f: LogFilter) -> None:
    """添加一个日志过滤器。

    过滤条件应用于 **所有已注册的 handler**（文件 + 控制台）。
    可多次调用以组合多个独立过滤器（OR 关系）。

    单个 :class:`LogFilter` 内多个条件为 **AND 关系**。

    :param f: 过滤器配置
    """
    _active_filters.append(f)


def clear_filters() -> None:
    """清除所有已添加的过滤器。"""
    _active_filters.clear()


_active_filters: list[LogFilter] = []


def _build_filter_func() -> "Callable[[Record], bool]":
    """构建 loguru 过滤函数。

    返回的函数在每次调用时检查当前的 ``_active_filters`` 列表，
    因此事后添加的过滤器也会生效。

    :return: 过滤函数（返回 True 表示通过）
    """

    def _filter(record: "Record") -> bool:
        if not _active_filters:
            return True
        now = record["time"]  # type: ignore[index]
        message = record["message"]  # type: ignore[index]
        level_name = record["level"].name  # type: ignore[index, union-attr]
        file_path = record["extra"].get("path", "")  # type: ignore[index]

        for f in _active_filters:
            match = True

            # 级别
            if f.level is not None:
                match = match and _match_level(level_name, f.level)

            # 源文件
            if f.source is not None:
                match = match and (f.source in file_path)

            # 关键字
            if f.keyword is not None:
                match = match and (f.keyword in message)

            # 时间段
            if f.time_from is not None:
                match = match and (now.strftime("%H:%M") >= f.time_from)
            if f.time_to is not None:
                match = match and (now.strftime("%H:%M") <= f.time_to)

            if match:
                return True

        return False

    return _filter


_LEVEL_ORDER: dict[str, int] = {
    "TRACE": 0, "DEBUG": 10, "INFO": 20,
    "SUCCESS": 25, "WARNING": 30, "ERROR": 40, "CRITICAL": 50,
}

def _match_level(actual: str, required: str) -> bool:
    return _LEVEL_ORDER.get(actual, 0) >= _LEVEL_ORDER.get(required.upper(), 0)


# ================================================================ #
# 公共 API
# ================================================================ #

def init(
    log_dir: str | Path = "logs",
    level: str = "DEBUG",
    rotation: str = "10 MB",
    retention: str = "7 days",
    console: bool = True,
) -> None:
    """初始化日志系统。

    应在程序入口处调用一次。

    :param log_dir: 日志文件存放目录
    :param level: 最低输出级别（DEBUG / INFO / WARNING / ERROR）
    :param rotation: 日志分割策略，例如 ``"10 MB"``、``"00:00"``（每天零点）
    :param retention: 日志保留时长，例如 ``"7 days"``、``"1 week"``
    :param console: 是否同时输出到控制台
    """
    global _initialized

    if _initialized:
        return

    global _LOG_DIR
    _LOG_DIR = Path(log_dir)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 抑制第三方库的 DEBUG 噪音（httpcore/httpx 连接层 open/close 等
    # 无价值信息），WARNING 及以上仍正常输出
    import logging as _stdlib_logging
    for _name in ("httpcore", "httpx", "websockets", "urllib3", "asyncio"):
        _stdlib_logging.getLogger(_name).setLevel(_stdlib_logging.WARNING)

    _logger.remove()

    # 文件输出 —— 按大小 + 时间双重分割
    _logger.add(
        _LOG_DIR / "bot_{time:YYYY-MM-DD}.log",
        format=_LOG_FORMAT,
        level=level,
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
        filter=_build_filter_func(),
    )

    # 错误日志单独文件
    _logger.add(
        _LOG_DIR / "error_{time:YYYY-MM-DD}.log",
        format=_LOG_FORMAT,
        level="ERROR",
        rotation=rotation,
        retention=retention * 2,
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
        filter=_build_filter_func(),
    )

    # 控制台输出（始终不过滤）
    if console:
        _logger.add(
            sys.stderr,
            format=_LOG_FORMAT,
            level=level,
            colorize=True,
            backtrace=False,
            diagnose=False,
        )

    _initialized = True


def get_logger(name: str = "") -> LoggerProtocol:
    """获取已绑定调用类名的日志记录器。

    用法::

        from core.logging import get_logger

        log = get_logger(__name__)

        class MyClass:
            def do_something(self):
                log.info("hello")         # 输出 [MyClass:do_something]
                log.error("something")    # 输出 [MyClass:do_something]

    :param name: 模块名称（通常传 ``__name__``）
    :return: 带自动上下文绑定的日志代理
    """
    return _LoggerProxy(name)  # type: ignore[return-value]


# ================================================================ #
# 代理 —— 每次调用自动注入调用类名
# ================================================================ #

class _LoggerProxy:
    """日志代理——每次调用前自动从调用栈提取类名和方法名。"""

    __slots__ = ("_module_name", "_bound")

    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._bound: dict = {}

    # ---- 标准级别 ----

    def debug(self, message: str, *args, **kwargs) -> None:
        ctx = _caller_context(file_path=True)
        ctx.update(self._bound)
        _logger.bind(**ctx).opt(depth=1).debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        ctx = _caller_context(file_path=True)
        ctx.update(self._bound)
        _logger.bind(**ctx).opt(depth=1).info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        ctx = _caller_context(file_path=True)
        ctx.update(self._bound)
        _logger.bind(**ctx).opt(depth=1).warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        ctx = _caller_context(file_path=True)
        ctx.update(self._bound)
        _logger.bind(**ctx).opt(depth=1).error(message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs) -> None:
        """记录异常（自动附加堆栈）。"""
        ctx = _caller_context(file_path=True)
        ctx.update(self._bound)
        _logger.bind(**ctx).opt(depth=1, exception=True).error(
            message, *args, **kwargs
        )

    # ---- 别名 ----

    def warn(self, message: str, *args, **kwargs) -> None:
        self.warning(message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs) -> None:
        ctx = _caller_context(file_path=True)
        ctx.update(self._bound)
        _logger.bind(**ctx).opt(depth=1).critical(message, *args, **kwargs)

    # ---- 辅助 ----

    def bind(self, **kwargs) -> _LoggerProxy:
        """返回一个新的代理，附加自定义上下文字段。"""
        new_proxy = _LoggerProxy(self._module_name)
        new_proxy._bound = {**self._bound, **kwargs}
        return new_proxy


# ================================================================ #
# 内部
# ================================================================ #

def _caller_context(file_path: bool = False) -> dict[str, str]:
    """从调用栈中提取类名和方法名。

    从当前帧向上遍历，跳过所有 ``core.logging`` 模块内的帧。

    :param file_path: 是否附加调用源文件路径
    :return: 含 ``class_name`` / ``func_name`` / ``path`` 的字典
    """
    import inspect

    frame = inspect.currentframe()
    try:
        if frame is not None:
            frame = frame.f_back

        while frame is not None:
            mod = frame.f_globals.get("__name__", "")
            if not mod.startswith("core.logging"):
                break
            frame = frame.f_back

        if frame is None:
            return {"class_name": "-", "func_name": "-", "path": "-"}

        func_name = frame.f_code.co_name

        self_obj = frame.f_locals.get("self")
        if self_obj is not None:
            class_name = type(self_obj).__name__
        else:
            cls_obj = frame.f_locals.get("cls")
            if cls_obj is not None:
                class_name = cls_obj.__name__
            else:
                class_name = frame.f_globals.get("__name__", "-").rpartition(".")[-1]

        ctx = {"class_name": class_name, "func_name": func_name}

        if file_path:
            ctx["path"] = frame.f_globals.get("__file__", "-")

        return ctx

    finally:
        del frame


# ================================================================ #
# 便捷函数
# ================================================================ #

def debug(message: str, *args, **kwargs) -> None:
    _logger.bind(**_caller_context()).opt(depth=1).debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs) -> None:
    _logger.bind(**_caller_context()).opt(depth=1).info(message, *args, **kwargs)


# ================================================================ #
# 自动初始化
# ================================================================ #

if not _initialized:
    init()
