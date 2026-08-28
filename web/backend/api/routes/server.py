"""服务器控制 API 路由(面板级)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.account import AccountManager
from api.deps import get_account_manager
from api.schemas import ServerStatusResponse, StatusResponse

router = APIRouter()


@router.get("/status", response_model=ServerStatusResponse)
async def server_status(manager: AccountManager = Depends(get_account_manager)):
    """获取面板运行状态(账户聚合)。"""
    ov = manager.overview()
    return ServerStatusResponse(
        running=True,
        bot_name=f"{ov['total']} 个账户",
        bot_available=True,
        livestream_count=sum(1 for a in ov["accounts"] if a["room_id"]),
        plugin_count=ov["library_plugin_count"],
        enabled_plugin_count=sum(a["enabled_plugin_count"] for a in ov["accounts"]),
    )


@router.post("/reload", response_model=StatusResponse)
async def server_reload(manager: AccountManager = Depends(get_account_manager)):
    """重载全部账户(shutdown_all + start_all)。"""
    await manager.reload_all()
    return StatusResponse(
        success=True,
        message=f"面板已重载，{len(manager.list_records())} 个账户",
    )


@router.post("/shutdown", response_model=StatusResponse)
async def server_shutdown(manager: AccountManager = Depends(get_account_manager)):
    """关闭全部账户运行时。"""
    await manager.shutdown_all()
    return StatusResponse(success=True, message="全部账户已关闭")
