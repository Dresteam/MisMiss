"""仪表盘聚合 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core import MissevanServer
from interfaces.bot import BotPermission
from api.deps import get_server
from api.schemas import DashboardResponse, BotInfoResponse

router = APIRouter()


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(s: MissevanServer = Depends(get_server)):
    """仪表盘聚合数据——Bot、直播间、插件统计。"""
    bot = s.bot
    lives = s.livestreams
    plugins = s.plugins

    # Bot info
    bot_info = BotInfoResponse(
        name=bot.name,
        user_id=bot.id,
        introduction=bot.introduction,
        icon_url=bot.icon_url,
        enabled=bot.enabled,
        available=s.bot_available,
        permissions=[p.name for p in BotPermission if bot.permissions & p],
        cookie_length=0,
    )

    # 直播间统计
    online = sum(1 for live in lives.values() if live.is_connected)

    # 插件统计
    enabled = sum(1 for p in plugins if p.enabled)

    return DashboardResponse(
        bot=bot_info,
        livestream_count=len(lives),
        livestream_online=online,
        livestream_offline=len(lives) - online,
        plugin_count=len(plugins),
        plugin_enabled=enabled,
        plugin_disabled=len(plugins) - enabled,
        failed_plugin_count=len(s.get_failed_plugins()),
        timer_message_count=s.timer_message_count,
    )
