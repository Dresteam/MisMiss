"""直播间管理 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from core.exceptions import (
    CoreApiException,
    CoreBotException,
    CoreCookieException,
    CoreDisabledException,
    CorePermissionException,
    CoreWebSocketException,
)
from api.deps import get_server
from api.schemas import (
    LiveAddRequest,
    LiveMessageRequest,
    LivestreamInfo,
    LiveListResponse,
    StatusResponse,
)

router = APIRouter()


# ------------------------------------------------------------------ #
# 辅助
# ------------------------------------------------------------------ #

def _live_to_info(live) -> LivestreamInfo:
    """将 MissevanLivestream 实例转为响应模型。"""
    medal_name = None
    medal_level = None
    if live.medal:
        medal_name = live.medal.name
        medal_level = live.medal.level
    creator_online = False
    try:
        if live.creator:
            creator_online = live.creator.is_online
    except Exception:
        pass
    return LivestreamInfo(
        live_id=live.live_id,
        room_name=live.room_name or "",
        room_description=live.room_description or "",
        score=getattr(live, "score", 0) or 0,
        creator_name=live.creator_name or "",
        creator_id=getattr(live, "creator_id", 0) or 0,
        creator_is_online=creator_online,
        is_connected=live.is_connected,
        enabled=live.enabled,
        medal_name=medal_name,
        medal_level=medal_level,
    )


# ================================================================== #
# 路由
# ================================================================== #


@router.post("/{live_id}/refresh", response_model=LivestreamInfo)
async def live_refresh(live_id: int, s: MissevanServer = Depends(get_server)):
    """刷新单个直播间的房间信息。"""
    lives = s.livestreams
    if live_id not in lives:
        raise HTTPException(status_code=404, detail=f"直播间 {live_id} 不存在")
    try:
        await lives[live_id]._refresh()
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")
    return _live_to_info(lives[live_id])


@router.get("/list", response_model=LiveListResponse)
async def live_list(s: MissevanServer = Depends(get_server)):
    """列出所有直播间。"""
    lives = s.livestreams
    items = [_live_to_info(live) for live in lives.values()]
    return LiveListResponse(livestreams=items, total=len(items))


@router.get("/{live_id}", response_model=LivestreamInfo)
async def live_info(live_id: int, s: MissevanServer = Depends(get_server)):
    """获取直播间详情。"""
    lives = s.livestreams
    if live_id not in lives:
        raise HTTPException(status_code=404, detail=f"直播间 {live_id} 不存在")
    return _live_to_info(lives[live_id])


@router.post("/add", response_model=LivestreamInfo)
async def live_add(req: LiveAddRequest, s: MissevanServer = Depends(get_server)):
    """添加直播间。"""
    try:
        live = await s.add_livestream(req.live_id)
        return _live_to_info(live)
    except CoreBotException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")


@router.post("/{live_id}/enable", response_model=StatusResponse)
async def live_enable(live_id: int, s: MissevanServer = Depends(get_server)):
    """启用直播间并连接 WebSocket。"""
    try:
        await s.enable_livestream(live_id)
        return StatusResponse(success=True, message=f"直播间 {live_id} 已启用")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"直播间 {live_id} 不存在")
    except CoreWebSocketException as e:
        raise HTTPException(status_code=502, detail=f"连接失败（403 错误可能为 Cookie 已过期）: {e}")
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")


@router.post("/{live_id}/disable", response_model=StatusResponse)
async def live_disable(live_id: int, s: MissevanServer = Depends(get_server)):
    """停用直播间并断开连接。"""
    try:
        s.disable_livestream(live_id)
        return StatusResponse(success=True, message=f"直播间 {live_id} 已停用")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"直播间 {live_id} 不存在")


@router.post("/{live_id}/join", response_model=StatusResponse)
async def live_join(live_id: int, s: MissevanServer = Depends(get_server)):
    """进入直播间（建立 WebSocket 连接）。"""
    lives = s.livestreams
    if live_id not in lives:
        raise HTTPException(status_code=404, detail=f"直播间 {live_id} 不存在，请先添加")
    try:
        await lives[live_id].join()
        return StatusResponse(success=True, message=f"已进入直播间 {live_id}: {lives[live_id].room_name}")
    except CoreDisabledException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/{live_id}/quit", response_model=StatusResponse)
async def live_quit(live_id: int, s: MissevanServer = Depends(get_server)):
    """退出直播间（断开 WebSocket 连接）。"""
    lives = s.livestreams
    if live_id not in lives:
        raise HTTPException(status_code=404, detail=f"直播间 {live_id} 不存在")
    try:
        await lives[live_id].quit()
        return StatusResponse(success=True, message=f"已退出直播间 {live_id}")
    except CoreDisabledException:
        # 已经停用/断开，视为成功
        return StatusResponse(success=True, message=f"直播间 {live_id} 已处于断开状态")


@router.delete("/{live_id}", response_model=StatusResponse)
async def live_remove(live_id: int, s: MissevanServer = Depends(get_server)):
    """移除直播间。"""
    try:
        await s.remove_livestream(live_id)
        return StatusResponse(success=True, message=f"直播间 {live_id} 已移除")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"直播间 {live_id} 不存在")


@router.post("/message", response_model=StatusResponse)
async def live_send_message(req: LiveMessageRequest, s: MissevanServer = Depends(get_server)):
    """向直播间发送弹幕消息。"""
    lives = s.livestreams
    if req.live_id not in lives:
        raise HTTPException(status_code=404, detail=f"直播间 {req.live_id} 不存在")
    try:
        await lives[req.live_id].send_message(
            req.text, priority=req.priority
        )
        return StatusResponse(
            success=True,
            message=f"已发送 → {req.live_id}: {req.text[:50]}{'...' if len(req.text) > 50 else ''}",
        )
    except CoreDisabledException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CorePermissionException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=str(e))
