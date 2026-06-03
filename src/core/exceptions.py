"""core 层异常定义。

本模块定义了 core 层所有异常类型。
异常直接向上抛出，不包含内部日志逻辑，
由调用方决定是否记录。
"""


class CoreApiException(Exception):
    """API 请求异常。

    当 HTTP 请求非 200、JSON 解析失败或连接中断时抛出。

    :param message: 异常描述
    :param status_code: HTTP 状态码（如有）
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class CoreWebSocketException(Exception):
    """WebSocket 连接异常。

    当 WebSocket 连接失败、断开或数据解析错误时抛出。

    :param message: 异常描述
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CoreCookieException(Exception):
    """Cookie 无效异常。

    当 Cookie 已过期或无法通过验证时抛出。

    :param message: 异常描述
    """

    def __init__(self, message: str = "Cookie 已过期") -> None:
        super().__init__(message)


class CoreBrotliException(Exception):
    """Brotli 解压异常。

    当 WebSocket 收到的数据无法正确解压时抛出。

    :param message: 异常描述
    """

    def __init__(self, message: str = "Brotli 解压失败") -> None:
        super().__init__(message)


class CorePermissionException(Exception):
    """权限不足异常。

    当调用方法时权限不足时抛出。

    :param message: 异常描述
    :param required: 所需权限名称
    """

    def __init__(self, message: str = "权限不足", required: str = "") -> None:
        self.required = required
        super().__init__(message)
