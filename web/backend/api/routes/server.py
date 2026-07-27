"""服务器控制 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core import MissevanServer
from interfaces.bot import BotPermission
from api.deps import get_server
from api.schemas import ServerStatusResponse, StatusResponse

router = APIRouter()


@router.get("/status", response_model=ServerStatusResponse)
async def server_status(s: MissevanServer = Depends(get_server)):
    """获取服务器运行状态。"""
    await s._ensure_bot_restored()
    bot = s.bot
    plugins = s.plugins
    return ServerStatusResponse(
        running=True,
        bot_name=bot.name or "(未配置)",
        bot_available=s.bot_available,
        livestream_count=len(s.livestreams),
        plugin_count=len(plugins),
        enabled_plugin_count=sum(1 for p in plugins if p.enabled),
    )


@router.post("/reload", response_model=StatusResponse)
async def server_reload(s: MissevanServer = Depends(get_server)):
    """重载服务器（shutdown → start）。"""
    await s.reload()
    return StatusResponse(
        success=True,
        message=f"服务器已重载，{len(s.plugins)} 个插件",
    )


@router.post("/shutdown", response_model=StatusResponse)
async def server_shutdown(s: MissevanServer = Depends(get_server)):
    """关闭服务器。"""
    await s.shutdown()
    return StatusResponse(success=True, message="服务器已关闭")
