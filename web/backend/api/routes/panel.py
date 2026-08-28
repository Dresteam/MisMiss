"""面板级路由 —— 账户 CRUD、公共 Bot、授权码与总览。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core.account import AccountManager
from core.exceptions import (
    CoreAccountExpiredException,
    CoreAccountNotFoundException,
    CoreCookieException,
    CoreLicenseException,
)
from api.deps import get_account_manager
from api.schemas import (
    AccountCreateRequest,
    AccountCredentialsRequest,
    AccountSummary,
    AccountUpdateRequest,
    BotCookieResponse,
    LicenseGenerateRequest,
    LicenseInfo,
    PanelOverview,
    PublicBotResponse,
    PublicBotSetRequest,
    PublicBotVerifyResponse,
    RedeemRequest,
    RenewRequest,
    ServerStatusResponse,
    StatusResponse,
)

router = APIRouter()

_DEP = Depends(get_account_manager)


# ------------------------------------------------------------------ #
# 辅助
# ------------------------------------------------------------------ #

def _permission_names(value: int) -> list[str]:
    from interfaces.bot import BotPermission
    try:
        flag = BotPermission(int(value))
    except ValueError:
        return []
    return [p.name for p in BotPermission if flag & p]


def _summary(manager: AccountManager, account_id: int) -> AccountSummary:
    return AccountSummary(**manager._account_snapshot(manager.get_record(account_id)))


# ------------------------------------------------------------------ #
# 总览 & 状态
# ------------------------------------------------------------------ #


@router.get("/overview", response_model=PanelOverview)
async def panel_overview(manager: AccountManager = _DEP):
    """面板总览(账户列表聚合)。"""
    return PanelOverview(**manager.overview())


@router.get("/status", response_model=ServerStatusResponse)
async def panel_status(manager: AccountManager = _DEP):
    """面板级服务器状态。"""
    ov = manager.overview()
    running = sum(1 for a in ov["accounts"] if a["bot_enabled"] and a["bot_available"])
    return ServerStatusResponse(
        running=True,
        bot_name=f"{ov['total']} 个账户",
        bot_available=True,
        livestream_count=sum(1 for a in ov["accounts"] if a["room_id"]),
        plugin_count=ov["library_plugin_count"],
        enabled_plugin_count=sum(a["enabled_plugin_count"] for a in ov["accounts"]),
    )


# ------------------------------------------------------------------ #
# 账户 CRUD
# ------------------------------------------------------------------ #


@router.get("/accounts", response_model=list[AccountSummary])
async def accounts_list(manager: AccountManager = _DEP):
    """账户列表。"""
    return [_summary(manager, r.id) for r in manager.list_records()]


@router.post("/accounts", response_model=AccountSummary)
async def accounts_create(req: AccountCreateRequest, manager: AccountManager = _DEP):
    """创建账户。"""
    from interfaces.bot import BotPermission
    perms = BotPermission(0)
    for name in req.permissions:
        name = name.strip().upper()
        try:
            perms |= BotPermission[name]
        except KeyError:
            pass
    if not perms.value:
        perms = BotPermission.SEND_LIVESTREAM_MESSAGE
    try:
        rec = await manager.create_account(
            req.name,
            room_id=req.room_id,
            bot_mode=req.bot_mode,
            cookie=req.cookie,
            permissions=perms,
            duration_days=req.duration_days,
            username=req.username,
            password=req.password,
        )
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"账户创建失败: {e}")
    return _summary(manager, rec.id)


@router.get("/accounts/{account_id}", response_model=AccountSummary)
async def accounts_get(account_id: int, manager: AccountManager = _DEP):
    """账户详情(记录 + 运行时快照)。"""
    try:
        return _summary(manager, account_id)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/accounts/{account_id}", response_model=AccountSummary)
async def accounts_update(
    account_id: int, req: AccountUpdateRequest, manager: AccountManager = _DEP
):
    """更新账户(name / room_id / bot_mode 切换)。"""
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        rec = await manager.update_account(account_id, **fields)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _summary(manager, rec.id)


@router.post("/accounts/{account_id}/credentials", response_model=AccountSummary)
async def accounts_reset_credentials(
    account_id: int, req: AccountCredentialsRequest, manager: AccountManager = _DEP
):
    """重置账户登录凭据(用户名/密码)。"""
    try:
        rec = manager.reset_credentials(account_id, req.username, req.password)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _summary(manager, rec.id)


@router.delete("/accounts/{account_id}", response_model=StatusResponse)
async def accounts_delete(
    account_id: int, purge_data: bool = False, manager: AccountManager = _DEP
):
    """删除账户(purge_data=true 时清除数据目录)。"""
    try:
        await manager.delete_account(account_id, purge_data=purge_data)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    return StatusResponse(success=True, message=f"账户 {account_id} 已删除")


# ------------------------------------------------------------------ #
# 到期 / 续期 / 授权码
# ------------------------------------------------------------------ #


@router.post("/accounts/{account_id}/renew", response_model=AccountSummary)
async def accounts_renew(
    account_id: int, req: RenewRequest, manager: AccountManager = _DEP
):
    """续期:days(叠加天数)或 expires_at(直接设置)。"""
    try:
        if req.expires_at is not None:
            rec = await manager._apply_renewal(account_id, req.expires_at)
        elif req.days is not None:
            rec = await manager.renew_days(account_id, req.days)
        else:
            raise HTTPException(status_code=400, detail="必须提供 days 或 expires_at")
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _summary(manager, rec.id)


@router.post("/accounts/{account_id}/redeem", response_model=AccountSummary)
async def accounts_redeem(
    account_id: int, req: RedeemRequest, manager: AccountManager = _DEP
):
    """兑换授权码。"""
    try:
        rec = await manager.redeem(account_id, req.code)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CoreLicenseException as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _summary(manager, rec.id)


@router.get("/licenses", response_model=list[LicenseInfo])
async def licenses_list(manager: AccountManager = _DEP):
    """授权码列表。"""
    return [LicenseInfo(**item) for item in manager.list_licenses()]


@router.post("/licenses/generate", response_model=list[LicenseInfo])
async def licenses_generate(req: LicenseGenerateRequest, manager: AccountManager = _DEP):
    """批量生成授权码。"""
    try:
        codes = manager.generate_licenses(req.count, req.days, req.note)
    except CoreLicenseException as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [LicenseInfo(**item) for item in manager.list_licenses() if item["code"] in codes]


@router.delete("/licenses/{code}", response_model=StatusResponse)
async def licenses_revoke(code: str, manager: AccountManager = _DEP):
    """撤销未使用的授权码。"""
    try:
        manager.revoke_license(code)
    except CoreLicenseException as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StatusResponse(success=True, message=f"授权码 {code} 已撤销")


# ------------------------------------------------------------------ #
# 公共 Bot
# ------------------------------------------------------------------ #


@router.get("/public-bot", response_model=PublicBotResponse)
async def public_bot_get(manager: AccountManager = _DEP):
    """公共 Bot 信息(面板级,掩码长度与权限,含缓存 Bot 资料)。"""
    info = manager.get_public_bot()
    try:
        updated_at = float(info.get("updated_at", 0) or 0)
    except (TypeError, ValueError):
        updated_at = 0.0  # 兼容旧数据中非数字的 updated_at
    return PublicBotResponse(
        configured=bool(info.get("cookie")),
        cookie_length=len(info.get("cookie", "")),
        permissions=_permission_names(info.get("permissions", 1)),
        updated_at=updated_at,
        name=str(info.get("bot_name", "")),
        user_id=int(info.get("bot_id", 0) or 0),
        introduction=str(info.get("introduction", "")),
        icon_url=str(info.get("icon_url", "")),
        available=bool(info.get("bot_available", False)),
    )


@router.get("/public-bot/cookie", response_model=BotCookieResponse)
async def public_bot_cookie(manager: AccountManager = _DEP):
    """查看公共 Cookie 原文(面板管理员)。"""
    cookie = manager.get_public_bot().get("cookie", "")
    if not cookie:
        raise HTTPException(status_code=404, detail="公共 Cookie 未配置")
    return BotCookieResponse(cookie=cookie, length=len(cookie))


@router.post("/public-bot/refresh", response_model=PublicBotResponse)
async def public_bot_refresh(manager: AccountManager = _DEP):
    """刷新公共 Cookie 对应的 Bot 资料(缓存到面板)。"""
    from core.exceptions import CoreCookieException
    try:
        await manager.refresh_public_bot()
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")
    info = manager.get_public_bot()
    return PublicBotResponse(
        configured=True,
        cookie_length=len(info.get("cookie", "")),
        permissions=_permission_names(info.get("permissions", 1)),
        updated_at=float(info.get("updated_at", 0) or 0),
        name=str(info.get("bot_name", "")),
        user_id=int(info.get("bot_id", 0) or 0),
        introduction=str(info.get("introduction", "")),
        icon_url=str(info.get("icon_url", "")),
        available=bool(info.get("bot_available", False)),
    )


@router.post("/public-bot/verify", response_model=PublicBotVerifyResponse)
async def public_bot_verify(manager: AccountManager = _DEP):
    """验证公共 Cookie 有效性。"""
    return PublicBotVerifyResponse(**await manager.verify_public_bot())


@router.delete("/public-bot", response_model=StatusResponse)
async def public_bot_delete(manager: AccountManager = _DEP):
    """删除公共 Cookie(已运行的公共账户实例保持运行,重启后失效)。"""
    manager.clear_public_bot()
    return StatusResponse(success=True, message="公共 Cookie 已删除")


@router.put("/public-bot", response_model=StatusResponse)
async def public_bot_set(req: PublicBotSetRequest, manager: AccountManager = _DEP):
    """保存公共 Cookie(仅保存,不立即下发)。"""
    from interfaces.bot import BotPermission
    perms = BotPermission(0)
    for name in req.permissions:
        name = name.strip().upper()
        try:
            perms |= BotPermission[name]
        except KeyError:
            pass
    if not perms.value:
        perms = BotPermission.SEND_LIVESTREAM_MESSAGE
    await manager.set_public_bot(req.cookie, permissions=perms.value)
    return StatusResponse(success=True, message="公共 Cookie 已保存(尚未下发到账户)")


@router.post("/public-bot/apply", response_model=StatusResponse)
async def public_bot_apply(manager: AccountManager = _DEP):
    """将公共 Cookie 下发到所有 public 模式账户。"""
    try:
        result = await manager.apply_public_cookie()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    failed = result.get("failed", [])
    if failed:
        return StatusResponse(
            success=False,
            message=f"部分账户下发失败: {failed}",
        )
    return StatusResponse(success=True, message="公共 Cookie 已下发到全部 public 账户")
