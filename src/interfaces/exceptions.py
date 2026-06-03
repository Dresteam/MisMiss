"""接口层异常定义。

本模块定义了框架中可能抛出的异常类型。
"""


class RequestFailedException(Exception):
    """当向服务器发送请求失败时抛出。

    所有与直播平台 API 交互的方法（如发送消息、赠送礼物等）
    在网络请求失败或服务端返回错误时应抛出此异常。

    .. versionadded:: 1.0
    """

    def __init__(self, message: str = "请求失败") -> None:
        """初始化请求失败异常。

        :param message: 异常描述信息
        """
        super().__init__(message)
