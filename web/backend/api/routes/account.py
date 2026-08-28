"""账户级基础信息路由(账户持有者与面板管理员均可访问)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from core.exceptions import CoreAccountNotFoundException, CoreLicenseException
from api.deps import get_account_manager, require_account
from api.schemas import AccountSummary, RedeemRequest, StatusResponse

router = APIRouter()


@router.get("/info", response_model=AccountSummary)
async def account_info(account_id: int, s: MissevanServer = Depends(require_account)):
    """账户详情快照(记录 + 运行时状态)。"""
    manager = get_account_manager()
    return AccountSummary(**manager._account_snapshot(manager.get_record(account_id)))


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
