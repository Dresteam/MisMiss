"""Bot 管理 API 路由。"""

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
    """启用 Bot，恢复所有标记为已启用的插件。"""
    try:
        await s.enable_bot()
        await s._plugin_manager.resume_all()
        return StatusResponse(success=True, message="Bot 已启用，插件已恢复")
    except CoreCookieException as e:
        raise HTTPException(status_code=400, detail=f"Cookie 无效: {e}")


@router.delete("/", response_model=StatusResponse)
async def bot_delete(s: MissevanServer = Depends(get_server)):
    """删除 Bot，恢复为无 Bot 状态。"""
    s.bot.enabled = False
    s._bot = MissevanBot("", timer_interval=s._config.get_float("bot.timer_interval", 60.0))
    s._bot_available = False
    s._bot_cookie = ""
    s._bot_permissions = BotPermission.SEND_LIVESTREAM_MESSAGE
    s._save_state()
    return StatusResponse(success=True, message="Bot 已删除，服务器恢复为无 Bot 状态")


@router.put("/timer-interval", response_model=StatusResponse)
async def bot_timer_interval(body: dict, s: MissevanServer = Depends(get_server)):
    """动态修改定时消息间隔（秒）。"""
    interval = body.get("interval", 60)
    if not isinstance(interval, (int, float)) or interval < 1:
        raise HTTPException(status_code=400, detail="间隔必须 >= 1 秒")
    s.bot.timer_interval = float(interval)
    # 持久化到 config.yml
    import yaml
    import os
    from pathlib import Path
    config_path = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "config.yml")
    current = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f) or {}
    current.setdefault("bot", {})["timer_interval"] = int(interval)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return StatusResponse(success=True, message=f"定时消息间隔已设为 {int(interval)} 秒")


@router.post("/disable", response_model=StatusResponse)
async def bot_disable(s: MissevanServer = Depends(get_server)):
    """停用 Bot，暂停所有插件（不修改 enabled 标记和持久化状态）。"""
    s.bot.enabled = False
    await s._plugin_manager.suspend_all()
    return StatusResponse(success=True, message="Bot 已停用，插件已暂停（启停标记不变）")
