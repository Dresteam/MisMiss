"""Bot 管理 API 路由(账户级)。

挂载于 ``/api/accounts/{account_id}/bot``。

- private 模式:账户私有 Cookie,可查看/更新
- public 模式:使用面板公共 Cookie,账户内不可查看/修改 Cookie
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import MissevanServer
from core.bot.mis_bot import MissevanBot
from core.exceptions import (
    CoreCookieException,
    CorePermissionException,
    CoreDisabledException,
    CoreApiException,
)
from interfaces.bot import BotPermission
from api.deps import require_account, require_active_account
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


def _is_public(s: MissevanServer) -> bool:
    return bool(getattr(s.account_record, "bot_mode", "private") == "public")


def _reject_public_cookie_op() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail="该账户使用面板公共 Cookie,不可在账户内查看/修改",
    )


# ================================================================== #
# 路由
# ================================================================== #


@router.post("/create", response_model=BotInfoResponse)
async def create_bot(
    account_id: int,
    req: BotCreateRequest,
    s: MissevanServer = Depends(require_active_account),
):
    """创建或更新 Bot——传入 Cookie 和权限列表(private 模式)。"""
    if _is_public(s):
        raise _reject_public_cookie_op()
    try:
        perms = _parse_permissions(req.permissions)
        bot = await s.create_bot(req.cookie, permissions=perms)
        return _bot_to_response(s)
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")


@router.post("/mode", response_model=BotInfoResponse)
async def bot_set_mode(
    account_id: int, body: dict, s: MissevanServer = Depends(require_active_account)
):
    """切换 Bot 模式:public(面板公共 Cookie)/ private(自定义 Cookie)。

    - public:权限强制为仅发送直播间消息
    - private:可传 ``permissions`` 名称列表做完整权限设置
    """
    mode = str(body.get("mode", "")).strip()
    cookie = str(body.get("cookie", "")).strip()
    if mode not in ("public", "private"):
        raise HTTPException(status_code=400, detail="mode 必须为 public 或 private")
    from api.deps import get_account_manager
    permissions = _parse_permissions(body.get("permissions", []))
    try:
        await get_account_manager().switch_bot_mode(
            account_id, mode, cookie, permissions=permissions
        )
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _bot_to_response(s)


@router.get("/info", response_model=BotInfoResponse)
async def bot_info(account_id: int, s: MissevanServer = Depends(require_account)):
    """获取当前 Bot 信息。"""
    await s._ensure_bot_restored()
    return _bot_to_response(s)


@router.post("/refresh", response_model=StatusResponse)
async def bot_refresh(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """刷新 Bot 信息（验证 Cookie）。"""
    await s._ensure_bot_restored()
    try:
        await s.bot.refresh()
        return StatusResponse(success=True, message=f"刷新完成: {s.bot.name}")
    except CoreCookieException:
        raise HTTPException(status_code=400, detail="Cookie 已过期，Bot 已自动停用")
    except CoreApiException as e:
        raise HTTPException(status_code=502, detail=f"API 错误: {e}")


@router.get("/cookie", response_model=BotCookieResponse)
async def bot_cookie(account_id: int, s: MissevanServer = Depends(require_account)):
    """获取 Bot Cookie（需要 EXPOSE_COOKIE 权限,仅 private 模式）。"""
    if _is_public(s):
        raise _reject_public_cookie_op()
    await s._ensure_bot_restored()
    try:
        cookie = s.bot.get_cookie()
        return BotCookieResponse(cookie=cookie, length=len(cookie))
    except CorePermissionException as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CoreDisabledException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify", response_model=StatusResponse)
async def bot_verify(account_id: int, s: MissevanServer = Depends(require_account)):
    """验证 Cookie 是否有效。"""
    await s._ensure_bot_restored()
    ok = await s.verify_bot()
    if ok:
        return StatusResponse(success=True, message="Cookie 有效")
    else:
        return StatusResponse(success=False, message="Cookie 已过期或网络错误")


@router.post("/enable", response_model=StatusResponse)
async def bot_enable(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """启用 Bot，恢复所有标记为已启用的插件。"""
    await s._ensure_bot_restored()
    try:
        await s.enable_bot()
        s._plugin_manager.resume_all()
        return StatusResponse(success=True, message="Bot 已启用，插件已恢复")
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")


@router.delete("/", response_model=StatusResponse)
async def bot_delete(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """删除 Bot(private)或仅停用(public,公共 Cookie 由面板管理)。"""
    if _is_public(s):
        s.bot.enabled = False
        s._save_state()
        s._plugin_manager.suspend_all()
        return StatusResponse(
            success=True,
            message="公共模式 Bot 已停用（公共 Cookie 请在面板设置中管理）",
        )
    s.bot.enabled = False
    s._bot = MissevanBot("", timer_interval=s._config.get_float("bot.timer_interval", 60.0))
    s._bot_available = False
    s._bot_cookie = ""
    s._bot_permissions = BotPermission.SEND_LIVESTREAM_MESSAGE
    s._save_state()
    return StatusResponse(success=True, message="Bot 已删除，账户恢复为无 Bot 状态")


@router.post("/disable", response_model=StatusResponse)
async def bot_disable(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """停用 Bot，暂停所有插件（不修改 enabled 标记和持久化状态）。"""
    s.bot.enabled = False
    s._save_state()
    s._plugin_manager.suspend_all()
    return StatusResponse(success=True, message="Bot 已停用，插件已暂停")
