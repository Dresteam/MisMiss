"""API 基类。

所有 Missevan API 类的抽象父类，持有 :class:`HTTPClient` 并定义
统一的 :meth:`api` 入口方法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .client import HTTPClient


class API(ABC):
    """API 抽象基类。

    子类必须实现 :meth:`api` 方法作为唯一的请求入口。

    :param cookie: Cookie 字符串
    """

    def __init__(self, cookie: str = "") -> None:
        self._cookie = cookie
        self._http = HTTPClient(cookie)

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
