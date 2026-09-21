"""服务器控制 API 路由(面板级)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.account import BROADCAST_MAX_LEN, AccountManager, clip_broadcast
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
        broadcast_max_len=BROADCAST_MAX_LEN,
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


@router.post("/broadcast", response_model=StatusResponse)
async def server_broadcast(
    body: dict, manager: AccountManager = Depends(get_account_manager)
):
    """用各账户的机器人向所有直播间发送一条全局消息。

    请求体：``{"message": "..."}``

    只发给**已启用且正在开播**的直播间（与程序更新的提示消息同一通道）：
    未绑定 / 未启用 / 未开播 / 已过期的账户自动跳过。单个账户发送失败只影响
    它自己，不会中断其余账户。

    消息会被压掉多余空白并截断到 ``BROADCAST_MAX_LEN`` 个字符（直播弹幕有长度
    上限，超出会被平台拒绝）—— 因此实际发出的文本可能与传入的略有出入。
    """
    raw = body.get("message", "")
    text = clip_broadcast(raw)
    if not text:
        raise HTTPException(status_code=400, detail="消息不能为空")

    result = await manager.broadcast_to_livestreams(text)
    sent, skipped, failed = result["sent"], result["skipped"], result["failed"]
    if sent == 0 and failed == 0:
        message = f"没有可发送的直播间（跳过 {skipped} 个：未绑定 / 未启用 / 未开播 / 已过期）"
    else:
        message = f"已发送到 {sent} 个直播间"
        if skipped:
            message += f"，跳过 {skipped} 个"
        if failed:
            message += f"，失败 {failed} 个"
    return StatusResponse(success=True, message=message)
