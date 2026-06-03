"""Cookie 异常。

当 Cookie 相关操作出现问题时抛出。
"""


class CookieException(Exception):
    """Cookie 无效或过期时抛出。

    当机器人 Cookie 不合法、已过期或无法通过验证时抛出此异常。

    .. versionadded:: 1.0
    """

    def __init__(self, message: str = "Cookie 无效或已过期") -> None:
        """初始化 Cookie 异常。

        :param message: 异常描述信息
        """
        super().__init__(message)
