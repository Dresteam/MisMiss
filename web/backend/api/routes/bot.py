"""Bot 管理 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from core.exceptions import (
    CoreCookieException,
    CorePermissionException,
    CoreDisabledException,
    CoreApiException,
)
from interfaces.bot import BotPermission
from api.deps import get_server
from api.schemas import (
    BotCreateRequest,
    BotInfoResponse,
    BotCookieResponse,
    StatusResponse,
)

router = APIRouter()


# ------------------------------------------------------------------ #
# 辅助
# ------------------------------------------------------------------ #

def _parse_permissions(names: list[str]) -> BotPermission:
    """将权限名列表解析为 BotPermission Flag。"""
    flag = BotPermission(0)
    for name in names:
        name = name.strip().upper()
        if not name:
            continue
        try:
            flag |= BotPermission[name]
        except KeyError:
            pass  # 忽略无效权限名
    return flag if flag.value else BotPermission.SEND_LIVESTREAM_MESSAGE


def _bot_to_response(s: MissevanServer) -> BotInfoResponse:
    """将当前 Bot 序列化为响应模型。"""
    bot = s.bot
    return BotInfoResponse(
        name=bot.name,
        user_id=bot.id,
        introduction=bot.introduction,
        icon_url=bot.icon_url,
        enabled=bot.enabled,
        available=s.bot_available,
        permissions=[p.name for p in BotPermission if bot.permissions & p],
        cookie_length=len(bot.get_cookie()) if _has_permission(bot, BotPermission.EXPOSE_COOKIE) else 0,
    )


def _has_permission(bot, perm: BotPermission) -> bool:
    try:
        return bool(bot.permissions & perm)
    except Exception:
        return False


# ================================================================== #
# 路由
# ================================================================== #


@router.post("/create", response_model=BotInfoResponse)
async def create_bot(req: BotCreateRequest, s: MissevanServer = Depends(get_server)):
    """创建或更新 Bot——传入 Cookie 和权限列表。"""
    try:
        perms = _parse_permissions(req.permissions)
        bot = await s.create_bot(req.cookie, permissions=perms)
        return _bot_to_response(s)
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")


@router.get("/info", response_model=BotInfoResponse)
async def bot_info(s: MissevanServer = Depends(get_server)):
    """获取当前 Bot 信息。"""
    return _bot_to_response(s)


@router.post("/refresh", response_model=StatusResponse)
async def bot_refresh(s: MissevanServer = Depends(get_server)):
    """刷新 Bot 信息（验证 Cookie）。"""
    try:
        await s.bot.refresh()
        return StatusResponse(success=True, message=f"刷新完成: {s.bot.name}")
    except CoreCookieException:
        raise HTTPException(status_code=400, detail="Cookie 已过期，Bot 已自动停用")
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")


@router.get("/cookie", response_model=BotCookieResponse)
async def bot_cookie(s: MissevanServer = Depends(get_server)):
    """获取 Bot Cookie（需要 EXPOSE_COOKIE 权限）。"""
    try:
        cookie = s.bot.get_cookie()
        return BotCookieResponse(cookie=cookie, length=len(cookie))
    except CorePermissionException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CoreDisabledException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify", response_model=StatusResponse)
async def bot_verify(s: MissevanServer = Depends(get_server)):
    """验证 Cookie 是否有效。"""
    ok = await s.verify_bot()
    if ok:
        return StatusResponse(success=True, message="Cookie 有效")
    else:
        return StatusResponse(success=False, message="Cookie 已过期或网络错误")


@router.post("/enable", response_model=StatusResponse)
async def bot_enable(s: MissevanServer = Depends(get_server)):
    """启用 Bot。"""
    try:
        await s.enable_bot()
        return StatusResponse(success=True, message="Bot 已启用")
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")


@router.post("/disable", response_model=StatusResponse)
async def bot_disable(s: MissevanServer = Depends(get_server)):
    """停用 Bot。"""
    s.bot.enabled = False
    return StatusResponse(success=True, message="Bot 已停用")
