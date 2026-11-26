"""浏览器登录：用户名+验证码 / 用户名+密码。

猫耳没有可用的扫码登录；登录页的验证码/密码登录必须在真实浏览器里完成，
因为登录接口依赖页面生成的 X-M-DeviceSign、访客 Cookie 和完整浏览器环境。
本路由只负责驱动 BrowserLoginManager，成功后复用私有 Cookie 的保存流程。
"""

from __future__ import annotations

from dataclasses import replace

from api.routes.cookie_login import _apply_cookie
from api.schemas import (
    BrowserLoginSmsRequest,
    BrowserLoginSmsResponse,
    BrowserLoginStartRequest,
    BrowserLoginStartResponse,
)
from fastapi import APIRouter, HTTPException

from core.browser import BrowserBridge, BrowserConfig, BrowserError, BrowserUnavailableError
from core.browser.login import BrowserLoginManager
from core.config import ServerConfig

router = APIRouter()

_login_manager: BrowserLoginManager | None = None


def _get_login_manager() -> BrowserLoginManager:
    global _login_manager
    if _login_manager is None:
        cfg = ServerConfig.load()
        browser_cfg = replace(BrowserConfig.from_server_config(cfg), enabled=True)
        _login_manager = BrowserLoginManager(BrowserBridge(browser_cfg))
    return _login_manager


async def close_browser_login() -> None:
    global _login_manager
    if _login_manager is not None:
        await _login_manager.close()
        await _login_manager.bridge.close()
        _login_manager = None


@router.post("/browser-login/start", response_model=BrowserLoginStartResponse)
async def browser_login_start(account_id: int, req: BrowserLoginStartRequest):
    """开始登录：短信返回 session_id；密码直接完成。"""
    if req.method == "password" and not req.password:
        raise HTTPException(status_code=400, detail="请输入密码")
    manager = _get_login_manager()
    try:
        if req.method == "sms":
            session_id, message = await manager.start_sms(req.phone)
            return BrowserLoginStartResponse(
                ok=True, method="sms", session_id=session_id, message=message
            )
        result = await manager.start_password(req.phone, req.password)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.reason)
        await _apply_cookie(account_id, result.cookie)
        return BrowserLoginStartResponse(
            ok=True,
            method="password",
            message="登录成功，已更新账户 Cookie",
            username=result.username,
            user_id=result.user_id,
        )
    except HTTPException:
        raise
    except BrowserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BrowserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"浏览器登录失败:{exc}") from exc


@router.post("/browser-login/sms", response_model=BrowserLoginSmsResponse)
async def browser_login_sms(account_id: int, req: BrowserLoginSmsRequest):
    """提交短信验证码并保存登录 Cookie。"""
    manager = _get_login_manager()
    try:
        result = await manager.submit_sms(req.session_id, req.code)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.reason)
        await _apply_cookie(account_id, result.cookie)
        return BrowserLoginSmsResponse(
            ok=True,
            message="登录成功，已更新账户 Cookie",
            username=result.username,
            user_id=result.user_id,
        )
    except HTTPException:
        raise
    except BrowserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BrowserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"浏览器登录失败:{exc}") from exc
