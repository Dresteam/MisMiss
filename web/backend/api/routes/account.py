"""账户级基础信息路由(账户持有者与面板管理员均可访问)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from core import MissevanServer
from core.exceptions import CoreAccountNotFoundException, CoreLicenseException
from api.deps import get_account_manager, require_account
from api.routes.auth import _clear_account_tokens, token_info
from api.schemas import (
    AccountPasswordChangeRequest,
    AccountPreferencesRequest,
    AccountSummary,
    RedeemRequest,
    StatusResponse,
)

router = APIRouter()


@router.get("/info", response_model=AccountSummary)
async def account_info(
    account_id: int,
    s: MissevanServer = Depends(require_account),
    authorization: str = Header(default=""),
):
    """账户详情快照(记录 + 运行时状态)。

    ``remark`` 是管理端备注，账户本人不可见 —— 这里按令牌角色剔除。
    """
    manager = get_account_manager()
    snap = manager._account_snapshot(manager.get_record(account_id))
    token = authorization.removeprefix("Bearer ")
    info = token_info(token) if token else None
    if (info or {}).get("role") != "admin":
        snap.pop("remark", None)
    return AccountSummary(**snap)


@router.post("/redeem", response_model=AccountSummary)
async def account_redeem(
    account_id: int, req: RedeemRequest, s: MissevanServer = Depends(require_account)
):
    """账户自助兑换授权码(过期账户也可兑换,兑换成功后自动恢复)。"""
    manager = get_account_manager()
    try:
        rec = await manager.redeem(account_id, req.code)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CoreLicenseException as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AccountSummary(**manager._account_snapshot(rec))


@router.post("/change-password", response_model=StatusResponse)
async def account_change_password(
    account_id: int,
    req: AccountPasswordChangeRequest,
    s: MissevanServer = Depends(require_account),
):
    """账户自助修改密码(需原密码,新密码与确认密码一致)。

    修改成功后清除该账户的全部登录 token,强制重新登录。
    """
    manager = get_account_manager()
    rec = manager.get_record(account_id)
    if manager.authenticate_account(rec.username, req.current_password) is None:
        raise HTTPException(status_code=403, detail="原密码错误")
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的新密码不一致")
    try:
        manager.change_account_password(account_id, req.current_password, req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 清除该账户的全部登录 token,强制重新登录
    _clear_account_tokens(account_id)
    return StatusResponse(success=True, message="密码已修改,请重新登录")


@router.post("/preferences", response_model=AccountSummary)
async def account_update_preferences(
    account_id: int,
    req: AccountPreferencesRequest,
    s: MissevanServer = Depends(require_account),
):
    """更新账户级偏好(账户持有者自助)。

    可选项按提交内容逐项更新：目前是「安装插件自动启用」与「开播临期提示」。
    偏好按账户独立存储于 panel.json。
    """
    manager = get_account_manager()
    try:
        rec = manager.get_record(account_id)
        if req.auto_enable_on_install is not None:
            rec = manager.set_auto_enable_on_install(
                account_id, req.auto_enable_on_install
            )
        if req.expiry_notice_enabled is not None:
            rec = manager.set_expiry_notice_enabled(
                account_id, req.expiry_notice_enabled
            )
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    return AccountSummary(**manager._account_snapshot(rec))
