"""Pydantic 请求/响应模型。

所有 API 的输入输出均在此定义，确保类型安全。
"""

from __future__ import annotations

from enum import Enum
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
    """发送弹幕请求。"""

    live_id: int = Field(..., gt=0)
    text: str = Field(..., min_length=1)
    priority: int = Field(default=0, ge=0)


class LivestreamInfo(BaseModel):
    """直播间信息。"""

    live_id: int
    room_name: str = ""
    room_description: str = ""
    score: int = 0
    creator_name: str = ""
    creator_id: int = 0
    creator_is_online: bool = False
    is_connected: bool = False
    enabled: bool = False
    medal_name: str | None = None
    medal_level: int | None = None


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
