"""定时消息队列管理 API(账户级,单队列)。

挂载于 ``/api/accounts/{account_id}/timer``。
账户仅一个直播间,定时消息统一使用 bot 的 global 队列(live_id=0),
skip/send 由后端自动传入账户房间 ID。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from api.deps import require_account, require_active_account
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


def _target_room(s: MissevanServer) -> int | None:
    """账户房间 ID(用于全局消息 skip/send 的目标)。"""
    room_id = getattr(s.account_record, "room_id", None)
    return int(room_id) if room_id else None


# ================================================================== #
# 路由
# ================================================================== #


@router.get("/list")
async def timer_list(account_id: int, s: MissevanServer = Depends(require_account)):
    """列出定时消息(账户单队列 = 账户直播间的房间队列,附加房间名)。

    响应兼容前端单队列展示:``global`` 字段承载账户直播间的消息列表。
    """
    await s._ensure_bot_restored()
    data = s.list_timer_messages()
    room_id = _target_room(s)
    room = s.livestreams.get(room_id) if room_id else None
    for room_item in data["rooms"]:
        if room is not None and room_item["live_id"] == room_id:
            room_item["room_name"] = room.room_name
    # 账户消息注册在账户直播间队列(live_id = room_id),提取为单队列返回
    if room_id:
        room_item = next((r for r in data["rooms"] if r["live_id"] == room_id), None)
        messages = room_item["messages"] if room_item else []
        for i, m in enumerate(messages):
            m["index"] = i
        data["global"] = messages
    else:
        data["global"] = data["global"]  # 无房间时保留原 global(通常为空)
    data["target_live_id"] = room_id
    return data


@router.put("/interval", response_model=StatusResponse)
async def timer_set_interval(
    account_id: int, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """修改定时消息发送间隔（秒,按账户持久化）。"""
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
async def timer_add(
    account_id: int, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """添加一条定时消息(注册到账户直播间队列,按合并轮转发送)。"""
    _require_bot(s)
    room_id = _target_room(s)
    if not room_id:
        raise HTTPException(status_code=400, detail="请先绑定直播间再添加定时消息")
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    mid = s.register_timer_message(room_id, message)
    return StatusResponse(success=True, message=f"已添加定时消息 {mid}")


@router.put("/{message_id}", response_model=StatusResponse)
async def timer_update(
    account_id: int, message_id: str, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """编辑定时消息内容。"""
    _require_bot(s)
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    if not s.update_timer_message(message_id, message):
        raise HTTPException(status_code=404, detail=f"定时消息 {message_id} 不存在")
    return StatusResponse(success=True, message="定时消息已更新")


@router.delete("/{message_id}", response_model=StatusResponse)
async def timer_delete(
    account_id: int, message_id: str, s: MissevanServer = Depends(require_active_account)
):
    """删除一条定时消息。"""
    _require_bot(s)
    s.unregister_timer_message(message_id)
    return StatusResponse(success=True, message=f"定时消息 {message_id} 已删除")


@router.post("/{message_id}/move", response_model=StatusResponse)
async def timer_move(
    account_id: int, message_id: str, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """上移/下移定时消息。"""
    _require_bot(s)
    direction = int(body.get("direction", 0))
    if direction not in (-1, 1):
        raise HTTPException(status_code=400, detail="direction 必须为 -1 或 1")
    if not s.move_timer_message(message_id, direction):
        raise HTTPException(status_code=400, detail="无法移动（不存在或已在边界）")
    return StatusResponse(success=True, message="顺序已调整")


@router.post("/{message_id}/skip", response_model=StatusResponse)
async def timer_skip(
    account_id: int, message_id: str, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """跳过当前指针处的定时消息(目标为账户直播间,后端自动传入)。"""
    _require_bot(s)
    target = _target_room(s)
    if not s.skip_timer_message_once(message_id, target):
        raise HTTPException(
            status_code=400,
            detail="无法跳过（消息不存在或不在当前指针处）",
        )
    return StatusResponse(success=True, message="已跳过，指针已后移")


@router.post("/{message_id}/send", response_model=StatusResponse)
async def timer_send_now(
    account_id: int, message_id: str, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """立即发送一条定时消息(目标为账户直播间,后端自动传入)。"""
    _require_bot(s)
    target = _target_room(s)
    try:
        ok = await s.send_timer_message_now(message_id, target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送失败: {e}")
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="发送失败（消息不存在,或账户未绑定直播间）",
        )
    return StatusResponse(success=True, message="已立即发送")
