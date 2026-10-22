"""API 基类。

所有 Missevan API 类的抽象父类，持有 :class:`HTTPClient` 并定义
统一的 :meth:`api` 入口方法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .client import HTTPClient
from .throttle import Lane


class API(ABC):
    """API 抽象基类。

    子类必须实现 :meth:`api` 方法作为唯一的请求入口。

    :param cookie: Cookie 字符串
    """

    #: 这条 API 的流量类别，决定它走哪条闸门车道（见 :class:`Lane`）。
    #:
    #: 默认取 ``INTERACTIVE`` 是**刻意保守**：万一新增端点忘了归类，它会按
    #: 关键路径处理（平台限流时只降速、不被跳过），而不是被静默丢弃。
    #: 纯轮询 / 刷新类端点请显式声明 ``lane = Lane.BACKGROUND``。
    lane: Lane = Lane.INTERACTIVE

    def __init__(self, cookie: str = "") -> None:
        self._cookie = cookie
        self._http = HTTPClient(cookie, lane=self.lane)

    # ------------------------------------------------------------------ #
    # 子类必须实现
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def api(self, *args: Any, **kwargs: Any) -> Any:
        """执行具体的 HTTP 请求。

        每个子类重写此方法，接受不同参数，返回对应类型的数据。

        :raises CoreApiException: 请求失败时
        """
        ...
