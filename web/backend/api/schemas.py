"""Pydantic 请求/响应模型。

所有 API 的输入输出均在此定义，确保类型安全。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ================================================================== #
# 通用
# ================================================================== #


class StatusResponse(BaseModel):
    """通用操作结果。"""

    success: bool
    message: str = ""


class ErrorResponse(BaseModel):
    """错误响应。"""

    detail: str
    error_type: str = ""


# ================================================================== #
# Bot
# ================================================================== #


class BotCreateRequest(BaseModel):
    """创建 Bot 请求。"""

    cookie: str = Field(..., min_length=1, description="Missevan Cookie 字符串")
    permissions: list[str] = Field(
        default=["SEND_LIVESTREAM_MESSAGE"],
        description="权限名列表，如 ['SEND_LIVESTREAM_MESSAGE', 'EXPOSE_COOKIE']",
    )


class BotInfoResponse(BaseModel):
    """Bot 信息响应。"""

    name: str = ""
    user_id: int = 0
    introduction: str = ""
    icon_url: str = ""
    enabled: bool = False
    available: bool = False
    permissions: list[str] = []
    cookie_length: int = 0


class BotCookieResponse(BaseModel):
    """Cookie 查看响应（需 EXPOSE_COOKIE 权限）。"""

    cookie: str
    length: int


# ================================================================== #
# Livestream
# ================================================================== #


class LiveAddRequest(BaseModel):
    """添加直播间请求。"""

    live_id: int = Field(..., gt=0, description="直播间 ID")


class LiveMessageRequest(BaseModel):
    """发送弹幕请求(账户级路由下 live_id 由账户决定,可不传)。"""

    live_id: int | None = Field(default=None, gt=0)
    text: str = Field(..., min_length=1)
    priority: int = Field(default=0, ge=0)


class LivestreamInfo(BaseModel):
    """直播间信息。"""

    live_id: int
    room_name: str = ""
    room_description: str = ""
    score: int = 0
    online_count: int = 0
    creator_name: str = ""
    creator_id: int = 0
    creator_is_online: bool = False
    is_connected: bool = False
    enabled: bool = False
    medal_name: str | None = None
    medal_level: int | None = None
    cover_url: str = ""
    creator_avatar: str = ""
    creator_intro: str = ""
    is_streaming: bool = False


class LiveListResponse(BaseModel):
    """直播间列表。"""

    livestreams: list[LivestreamInfo]
    total: int


# ================================================================== #
# Plugin
# ================================================================== #


class PluginSummary(BaseModel):
    """插件摘要（列表用）。"""

    name: str
    plugin_id: str
    author: str
    version: str
    display_name: str | None = None
    short_desc: str | None = None
    desc: str = ""
    enabled: bool = False
    has_config: bool = False
    has_readme: bool = False
    has_changelog: bool = False
    has_ui: bool = False


class PluginEventHandler(BaseModel):
    """事件处理器信息。"""

    method_name: str
    event_type: str


class PluginPermissionInfo(BaseModel):
    """插件权限信息。"""

    permissions: dict[str, bool]
    effective_flag: int
    effective_names: list[str]
    bot_permissions: list[str]
    missing_in_bot: list[str]


class PluginDetailResponse(BaseModel):
    """插件详情。"""

    name: str
    plugin_id: str
    author: str
    version: str
    display_name: str | None = None
    short_desc: str | None = None
    desc: str = ""
    repo: str | None = None
    enabled: bool = False
    has_config: bool = False
    has_readme: bool = False
    has_changelog: bool = False
    handlers: list[PluginEventHandler] = []
    permissions: dict[str, bool] | None = None
    config_schema: dict[str, Any] | None = None
    config_values: dict[str, Any] | None = None
    ui_schema: dict[str, Any] | None = None


class PluginPermUpdateRequest(BaseModel):
    """更新插件权限请求。"""

    key: str = Field(..., description="权限名，如 SEND_GIFT")
    value: bool


class PluginConfigUpdateRequest(BaseModel):
    """更新插件配置请求。"""

    config: dict[str, Any] = Field(..., description="完整配置字典")


class FailedPluginInfo(BaseModel):
    """加载失败的插件信息。"""

    dir_name: str
    error: str
    traceback: str = ""


# ================================================================== #
# Dashboard
# ================================================================== #


class DashboardResponse(BaseModel):
    """仪表盘聚合数据。"""

    bot: BotInfoResponse | None = None
    livestream_count: int = 0
    livestream_online: int = 0
    livestream_offline: int = 0
    plugin_count: int = 0
    plugin_enabled: int = 0
    plugin_disabled: int = 0
    failed_plugin_count: int = 0
    timer_message_count: int = 0


# ================================================================== #
# Server
# ================================================================== #


class ServerStatusResponse(BaseModel):
    """服务器状态。"""

    running: bool
    bot_name: str = ""
    bot_available: bool = False
    livestream_count: int = 0
    plugin_count: int = 0
    enabled_plugin_count: int = 0


# ================================================================== #
# WebSocket
# ================================================================== #


class WSLogMessage(BaseModel):
    """WebSocket 日志消息。"""

    type: str = "log"  # log | status | error
    level: str = "INFO"
    message: str
    timestamp: float = 0.0


# ================================================================== #
# 多账户面板
# ================================================================== #


class AccountCreateRequest(BaseModel):
    """创建账户请求。"""

    name: str = Field(..., min_length=1, max_length=64)
    room_id: int | None = Field(default=None, gt=0, description="绑定的直播间 ID")
    bot_mode: str = Field(default="private", description="private | public")
    cookie: str = Field(default="", description="private 模式的 Cookie")
    permissions: list[str] = Field(default=["SEND_LIVESTREAM_MESSAGE"])
    duration_days: int = Field(
        default=-1,
        description="有效时长(天):N 为 N 天;-1 为永久",
    )
    username: str = Field(..., min_length=1, max_length=64, description="账户登录用户名(必填,全局唯一,用于账户分辨)")
    password: str = Field(default="", min_length=4, max_length=64, description="账户登录密码(至少 4 位)")


class AccountUpdateRequest(BaseModel):
    """更新账户请求(仅提交需要修改的字段)。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    room_id: int | None = Field(default=None, gt=0)
    bot_mode: str | None = Field(default=None, description="private | public")
    cookie: str | None = Field(default=None, description="切换 private 模式时的 Cookie")


class AccountCredentialsRequest(BaseModel):
    """重置账户登录凭据请求。"""

    username: str = Field(default="", max_length=64, description="新用户名(留空保持不变)")
    password: str = Field(default="", min_length=4, max_length=64, description="新密码(至少 4 位)")


class AccountPasswordChangeRequest(BaseModel):
    """账户自助修改密码请求(需原密码与确认密码)。"""

    current_password: str = Field(..., min_length=1, description="当前(原)密码")
    new_password: str = Field(..., min_length=4, max_length=64, description="新密码(至少 4 位)")
    confirm_password: str = Field(..., min_length=1, description="确认新密码(须与新密码一致)")


class RenewRequest(BaseModel):
    """续期请求:days 与 expires_at 二选一。"""

    days: int | None = Field(default=None, gt=0)
    expires_at: str | None = Field(default=None, description="直接设置到期时间")


class RedeemRequest(BaseModel):
    """兑换授权码请求。"""

    code: str = Field(..., min_length=1)


class AccountSummary(BaseModel):
    """账户摘要(面板列表用)。"""

    id: int
    name: str
    username: str = ""
    room_id: int | None = None
    bot_mode: str = "private"
    expires_at: str | None = None
    expired: bool = False
    days_left: int | None = None
    paused_reason: str | None = None
    resume_error: str | None = None
    bot_enabled: bool = False
    bot_available: bool = False
    bot_name: str = ""
    bot_public: bool = False
    room_connected: bool = False
    room_enabled: bool = False
    room_name: str = ""
    plugin_count: int = 0
    enabled_plugin_count: int = 0
    timer_message_count: int = 0


class PanelOverview(BaseModel):
    """面板总览。"""

    accounts: list[AccountSummary] = []
    total: int = 0
    expired_count: int = 0
    running_count: int = 0
    public_bot_configured: bool = False
    library_plugin_count: int = 0
    license_unused: int = 0


class PublicBotResponse(BaseModel):
    """公共 Bot 信息(面板级可见,账户上下文不可见)。"""

    configured: bool
    cookie_length: int = 0
    permissions: list[str] = []
    updated_at: float = 0.0
    name: str = ""
    user_id: int = 0
    introduction: str = ""
    icon_url: str = ""
    available: bool = False


class PublicBotVerifyResponse(BaseModel):
    """公共 Cookie 验证结果。"""

    valid: bool
    name: str = ""
    message: str = ""


class PublicBotSetRequest(BaseModel):
    """设置公共 Bot 请求。"""

    cookie: str = Field(..., min_length=1)
    permissions: list[str] = Field(default=["SEND_LIVESTREAM_MESSAGE"])


class LicenseInfo(BaseModel):
    """授权码信息。"""

    code: str
    days: int
    batch: str = ""
    note: str = ""
    generated_at: str = ""
    used_at: str | None = None
    used_by_account_id: int | None = None


class LicenseGenerateRequest(BaseModel):
    """生成授权码请求。"""

    count: int = Field(default=1, ge=1, le=100)
    days: int = Field(..., gt=0)
    note: str = ""
