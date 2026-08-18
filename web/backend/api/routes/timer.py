"""定时消息队列管理 API。

提供定时消息的查看、添加、编辑、删除、排序和跳过功能。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from api.deps import get_server
from api.schemas import StatusResponse

router = APIRouter()


# ------------------------------------------------------------------ #
# 辅助
# ------------------------------------------------------------------ #

def _require_bot(s: MissevanServer):
    """确保 Bot 可用。"""
    if not s.bot_available:
        raise HTTPException(status_code=400, detail="Bot 未启用")
    return s.bot


# ================================================================== #
# 路由
# ================================================================== #


@router.get("/list")
async def timer_list(s: MissevanServer = Depends(get_server)):
    """列出所有定时消息（含倒计时与执行指针）。"""
    return s.list_timer_messages()


@router.put("/interval", response_model=StatusResponse)
async def timer_set_interval(body: dict, s: MissevanServer = Depends(get_server)):
    """修改定时消息发送间隔（秒）。

    请求体：``{"interval": 120}``
    实时生效，不重置各直播间的执行位置指针。
    """
    _require_bot(s)
    interval = body.get("interval")
    try:
        interval = float(interval)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="interval 必须为数字")
    if interval < 1:
        raise HTTPException(status_code=400, detail="间隔必须 >= 1 秒")
    s.set_timer_interval(interval)
    return StatusResponse(success=True, message=f"定时消息间隔已设为 {interval:g} 秒（已持久化）")


@router.post("/add", response_model=StatusResponse)
async def timer_add(body: dict, s: MissevanServer = Depends(get_server)):
    """添加一条定时消息。

    请求体：``{"live_id": 12345, "message": "..."}``
    ``live_id`` 为 ``0`` 时添加全局消息（适用于所有直播间）。
    """
    _require_bot(s)
    live_id = int(body.get("live_id", 0))
    message = str(body.get("message", "")).strip()
    if live_id < 0:
        raise HTTPException(status_code=400, detail="live_id 不能为负数")
    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    mid = s.register_timer_message(live_id, message)
    scope = "全局" if live_id == 0 else f"直播间 {live_id}"
    return StatusResponse(success=True, message=f"已添加{scope}定时消息 {mid}")


@router.put("/{message_id}", response_model=StatusResponse)
async def timer_update(message_id: str, body: dict, s: MissevanServer = Depends(get_server)):
    """编辑定时消息内容。

    请求体：``{"message": "新内容"}``
    """
    _require_bot(s)
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    if not s.update_timer_message(message_id, message):
        raise HTTPException(status_code=404, detail=f"定时消息 {message_id} 不存在")
    return StatusResponse(success=True, message="定时消息已更新")


@router.delete("/{message_id}", response_model=StatusResponse)
async def timer_delete(message_id: str, s: MissevanServer = Depends(get_server)):
    """删除一条定时消息。"""
    _require_bot(s)
    s.unregister_timer_message(message_id)
    return StatusResponse(success=True, message=f"定时消息 {message_id} 已删除")


@router.post("/{message_id}/move", response_model=StatusResponse)
async def timer_move(message_id: str, body: dict, s: MissevanServer = Depends(get_server)):
    """上移/下移定时消息。

    请求体：``{"direction": -1}``（-1 上移，1 下移）
    """
    _require_bot(s)
    direction = int(body.get("direction", 0))
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction 必须为 -1 或 1")
    if not s.move_timer_message(message_id, direction):
        raise HTTPException(status_code=400, detail="无法移动（不存在或已在边界）")
    return StatusResponse(success=True, message="顺序已调整")


@router.post("/{message_id}/skip", response_model=StatusResponse)
async def timer_skip(message_id: str, body: dict, s: MissevanServer = Depends(get_server)):
    """跳过当前指针处的定时消息（指针后移一位，计时器保持）。

    请求体：``{"live_id": 12345}``（全局消息需要目标直播间 ID）
    """
    _require_bot(s)
    target = None
    try:
        t = body.get("live_id")
        target = int(t) if t not in (None, "", 0) else None
    except (TypeError, ValueError):
        target = None
    if not s.skip_timer_message_once(message_id, target):
        raise HTTPException(
            status_code=400,
            detail="无法跳过（消息不存在或不在当前指针处）",
        )
    return StatusResponse(success=True, message="已跳过，指针已后移")


@router.post("/{message_id}/send", response_model=StatusResponse)
async def timer_send_now(message_id: str, body: dict, s: MissevanServer = Depends(get_server)):
    """立即发送一条定时消息（视为立即执行，指针推进）。

    请求体：``{"live_id": 12345}``（全局消息需要目标直播间 ID）
    """
    _require_bot(s)
    target = body.get("live_id")
    try:
        target = int(target) if target not in (None, "", 0) else None
    except (TypeError, ValueError):
        target = None
    try:
        ok = await s.send_timer_message_now(message_id, target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {e}")
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="发送失败（消息不存在，或全局消息未指定目标直播间）",
        )
    return StatusResponse(success=True, message="已立即发送")
