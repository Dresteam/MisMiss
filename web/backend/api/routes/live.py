"""直播间管理 API 路由(账户级,单房间)。

挂载于 ``/api/accounts/{account_id}/live``。
每个账户仅允许绑定一个直播间(room_id 存于账户记录)。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from core.exceptions import (
    CoreApiException,
    CoreBotException,
    CoreDisabledException,
    CorePermissionException,
    CoreWebSocketException,
)
from api.deps import require_account, require_active_account
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
    creator_avatar = ""
    creator_intro = ""
    try:
        if live.creator:
            creator_online = live.creator.is_online
            creator_avatar = live.creator.icon_url or ""
            creator_intro = live.creator.introduction or ""
    except Exception:
        pass
    return LivestreamInfo(
        live_id=live.live_id,
        room_name=live.room_name or "",
        room_description=live.room_description or "",
        score=getattr(live, "score", 0) or 0,
        online_count=getattr(live, "online_count", 0) or 0,
        creator_name=live.creator_name or "",
        creator_id=getattr(live, "creator_id", 0) or 0,
        creator_is_online=creator_online,
        is_connected=live.is_connected,
        enabled=live.enabled,
        medal_name=medal_name,
        medal_level=medal_level,
        cover_url=getattr(live, "cover_url", "") or "",
        creator_avatar=creator_avatar,
        creator_intro=creator_intro,
        is_streaming=getattr(live, "is_streaming", False),
    )


def _room(s: MissevanServer):
    """账户唯一直播间(未绑定返回 None)。"""
    room_id = getattr(s.account_record, "room_id", None)
    if not room_id:
        return None
    return s.livestreams.get(int(room_id))


def _require_room(s: MissevanServer):
    room = _room(s)
    if room is None:
        raise HTTPException(status_code=404, detail="账户尚未绑定直播间,请先添加")
    return room


# ================================================================== #
# 路由
# ================================================================== #


@router.get("/", response_model=LivestreamInfo | None)
async def live_info(account_id: int, s: MissevanServer = Depends(require_account)):
    """账户唯一直播间信息(未绑定返回 null)。"""
    await s._ensure_bot_restored()
    room = _room(s)
    return _live_to_info(room) if room else None


@router.post("/add", response_model=LivestreamInfo)
async def live_add(
    account_id: int, req: LiveAddRequest, s: MissevanServer = Depends(require_active_account)
):
    """绑定/更换直播间(每个账户仅一个;已绑定时自动替换旧房间)。"""
    old = getattr(s.account_record, "room_id", None)
    if old == req.live_id:
        raise HTTPException(status_code=400, detail="已绑定该直播间")
    # 先添加新房间(失败则旧房间不受影响),成功后再移除旧的
    try:
        live = await s.add_livestream(req.live_id)
    except CoreBotException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")
    if old:
        try:
            await s.remove_livestream(int(old))
        except KeyError:
            pass
    # 写入账户记录
    s.account_record.room_id = req.live_id
    from api.deps import get_account_manager
    get_account_manager()._save_panel()
    return _live_to_info(live)


@router.delete("/", response_model=StatusResponse)
async def live_remove(account_id: int, s: MissevanServer = Depends(require_active_account)):
    """解除直播间绑定(断开连接并移除)。"""
    room = _require_room(s)
    try:
        await s.remove_livestream(room.live_id)
    except KeyError:
        pass
    s.account_record.room_id = None
    from api.deps import get_account_manager
    get_account_manager()._save_panel()
    return StatusResponse(success=True, message=f"直播间 {room.live_id} 已解除绑定")


@router.post("/refresh", response_model=LivestreamInfo)
async def live_refresh(account_id: int, s: MissevanServer = Depends(require_account)):
    """刷新直播间房间信息。"""
    room = _require_room(s)
    try:
        await room._refresh()
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")
    return _live_to_info(room)


@router.post("/enable", response_model=StatusResponse)
async def live_enable(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """启用直播间并连接 WebSocket。"""
    room = _require_room(s)
    try:
        await s.enable_livestream(room.live_id)
        return StatusResponse(success=True, message=f"直播间 {room.live_id} 已启用")
    except CoreWebSocketException as e:
        raise HTTPException(status_code=502, detail=f"连接失败（403 错误可能为 Cookie 已过期）: {e}")
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")


@router.post("/disable", response_model=StatusResponse)
async def live_disable(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """停用直播间并断开连接。"""
    room = _require_room(s)
    s.disable_livestream(room.live_id)
    return StatusResponse(success=True, message=f"直播间 {room.live_id} 已停用")


@router.post("/join", response_model=StatusResponse)
async def live_join(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """进入直播间（建立 WebSocket 连接）。"""
    await s._ensure_bot_restored()
    room = _require_room(s)
    try:
        await room.join()
        return StatusResponse(success=True, message=f"已进入直播间 {room.live_id}: {room.room_name}")
    except CoreDisabledException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/quit", response_model=StatusResponse)
async def live_quit(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """退出直播间（断开 WebSocket 连接）。"""
    room = _require_room(s)
    try:
        await room.quit()
        return StatusResponse(success=True, message=f"已退出直播间 {room.live_id}")
    except CoreDisabledException:
        return StatusResponse(success=True, message=f"直播间 {room.live_id} 已处于断开状态")


@router.post("/message", response_model=StatusResponse)
async def live_send_message(
    account_id: int,
    req: LiveMessageRequest,
    s: MissevanServer = Depends(require_active_account),
):
    """向账户直播间发送弹幕消息。"""
    room = _require_room(s)
    try:
        await room.send_message(
            req.text, priority=req.priority
        )
        return StatusResponse(
            success=True,
            message=f"已发送 → {room.live_id}: {req.text[:50]}{'...' if len(req.text) > 50 else ''}",
        )
    except CoreDisabledException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CorePermissionException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=str(e))
