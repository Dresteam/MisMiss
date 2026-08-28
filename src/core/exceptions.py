"""core 层异常定义。

本模块定义了 core 层所有异常类型。
异常直接向上抛出，不包含内部日志逻辑，
由调用方决定是否记录。
"""

class MissevanException(Exception):
    """功能已停用异常。

    当 :class:`Bot` 或 :class:`Livestream` 被停用时，
    调用其方法会抛出此异常。

    :param message: 异常描述
    """

    def __init__(self, message: str = "功能已停用") -> None:
        super().__init__(message)


class CoreApiException(MissevanException):
    """API 请求异常。

    当 HTTP 请求非 200、JSON 解析失败或连接中断时抛出。

    :param message: 异常描述
    :param status_code: HTTP 状态码（如有）
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class CoreWebSocketException(MissevanException):
    """WebSocket 连接异常。

    当 WebSocket 连接失败、断开或数据解析错误时抛出。

    :param message: 异常描述
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CoreBotException(MissevanException):
    """Bot 异常。

    当 :class:`Bot` 发生异常时，
    调用其方法会抛出此异常。

    :param message: 异常描述
    """

    def __init__(self, message: str = "Bot 异常") -> None:
        super().__init__(message)


class CoreCookieException(CoreBotException):
    """Cookie 无效异常。

    当 Cookie 已过期或无法通过验证时抛出。

    :param message: 异常描述
    """

    def __init__(self, message: str = "Cookie 已过期") -> None:
        super().__init__(message)


class CoreBrotliException(MissevanException):
    """Brotli 解压异常。

    当 WebSocket 收到的数据无法正确解压时抛出。

    :param message: 异常描述
    """

    def __init__(self, message: str = "Brotli 解压失败") -> None:
        super().__init__(message)


class CorePermissionException(MissevanException):
    """权限不足异常。

    当调用方法时权限不足时抛出。

    :param message: 异常描述
    :param required: 所需权限名称
    """

    def __init__(self, message: str = "权限不足", required: str = "") -> None:
        self.required = required
        super().__init__(message)


class CoreDisabledException(MissevanException):
    """功能已停用异常。

    当 :class:`Bot` 或 :class:`Livestream` 被停用时，
    调用其方法会抛出此异常。

    :param message: 异常描述
    """

    def __init__(self, message: str = "功能已停用") -> None:
        super().__init__(message)


class CorePluginException(MissevanException):
    """插件异常基类。

    插件相关所有异常的父类。

    :param message: 异常描述
    """

    def __init__(self, message: str = "插件异常") -> None:
        super().__init__(message)


class CorePluginNotFoundException(CorePluginException):
    """插件未找到异常。

    当操作一个不存在的插件时抛出。

    :param plugin_name: 插件名称
    """

    def __init__(self, plugin_name: str) -> None:
        self.plugin_name = plugin_name
        super().__init__(f"插件 '{plugin_name}' 未找到")


class CorePluginLoadException(CorePluginException):
    """插件加载失败异常。

    当插件导入、实例化或初始化过程中出现错误时抛出。

    :param plugin_name: 插件名称
    :param reason: 失败原因
    """

    def __init__(self, plugin_name: str, reason: str = "") -> None:
        self.plugin_name = plugin_name
        msg = f"插件 '{plugin_name}' 加载失败"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class CorePluginMetadataException(CorePluginException):
    """插件元数据异常。

    当 ``metadata.yaml`` 缺失或格式错误时抛出。

    :param plugin_name: 插件名称
    :param reason: 失败原因
    """

    def __init__(self, plugin_name: str, reason: str = "") -> None:
        self.plugin_name = plugin_name
        msg = f"插件 '{plugin_name}' 元数据错误"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class CorePluginConfigException(CorePluginException):
    """插件配置异常。

    当配置读写或 schema 校验失败时抛出。

    :param plugin_name: 插件名称
    :param reason: 失败原因
    """

    def __init__(self, plugin_name: str, reason: str = "") -> None:
        self.plugin_name = plugin_name
        msg = f"插件 '{plugin_name}' 配置错误"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class CorePluginInstallException(CorePluginException):
    """插件安装失败异常。

    当插件下载、解压或安装过程中出现错误时抛出。

    :param plugin_name: 插件名称
    :param reason: 失败原因
    """

    def __init__(self, plugin_name: str, reason: str = "") -> None:
        self.plugin_name = plugin_name
        msg = f"插件 '{plugin_name}' 安装失败"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class CorePluginPermissionException(CorePluginException):
    """插件权限配置异常。

    当权限配置读写或 schema 校验失败时抛出。

    :param plugin_name: 插件名称
    :param reason: 失败原因
    """

    def __init__(self, plugin_name: str, reason: str = "") -> None:
        self.plugin_name = plugin_name
        msg = f"插件 '{plugin_name}' 权限配置错误"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class CorePluginDependencyException(CorePluginException):
    """插件依赖安装失败异常。

    当 requirements.txt 中的依赖安装失败时抛出。

    :param plugin_name: 插件名称
    :param reason: 失败原因
    """

    def __init__(self, plugin_name: str, reason: str = "") -> None:
        self.plugin_name = plugin_name
        msg = f"插件 '{plugin_name}' 依赖安装失败"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


# ------------------------------------------------------------------ #
# 多账户面板
# ------------------------------------------------------------------ #

class CoreAccountException(MissevanException):
    """账户相关异常基类。"""

    def __init__(self, message: str = "账户异常") -> None:
        super().__init__(message)


class CoreAccountNotFoundException(CoreAccountException):
    """账户未找到异常。

    :param account_id: 账户 ID
    """

    def __init__(self, account_id: int) -> None:
        self.account_id = account_id
        super().__init__(f"账户 {account_id} 不存在")


class CoreAccountExpiredException(CoreAccountException):
    """账户已过期异常。

    过期账户的写操作被拒绝时抛出。

    :param account_id: 账户 ID
    """

    def __init__(self, account_id: int) -> None:
        self.account_id = account_id
        super().__init__(f"账户 {account_id} 已过期，请先续期")


class CoreLicenseException(MissevanException):
    """授权码异常。

    授权码生成、兑换、撤销过程中的错误。

    :param message: 异常描述
    """

    def __init__(self, message: str = "授权码错误") -> None:
        super().__init__(message)


