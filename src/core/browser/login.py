"""浏览器登录会话（猫耳用户名 + 验证码 / 密码）。

猫耳登录页：``https://www.missevan.com/member/login``。
页面提供验证码登录与密码登录；没有可用的扫码登录。

登录必须发生在真实浏览器页面里：登录接口依赖页面生成的
``X-M-DeviceSign``、访客 Cookie（FM_SESS/MSESSID 等）和完整的浏览器环境。
本模块用 :class:`BrowserBridge` 的浏览器进程创建独立 Context，填表并提交，
成功后抽取 Cookie，交给账户的私有 Cookie 流程保存。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .bridge import BrowserBridge, BrowserError, BrowserUnavailableError

LOGIN_URL = "https://www.missevan.com/member/login?backurl=https%3A%2F%2Ffm.missevan.com%2F"
USER_INFO_URL = "https://fm.missevan.com/api/user/info"
LOGIN_TTL = 300.0


@dataclass
class LoginSession:
    session_id: str
    context_id: str
    target_id: str
    cdp_session_id: str
    method: str
    phone: str
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class BrowserLoginResult:
    ok: bool
    cookie: str = ""
    user_id: int = 0
    username: str = ""
    reason: str = ""
    needs_captcha: bool = False


class BrowserLoginManager:
    """登录会话管理；一个浏览器进程，多个独立 Context。"""

    def __init__(self, bridge: BrowserBridge) -> None:
        self.bridge = bridge
        self._sessions: dict[str, LoginSession] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            await self._close_session(session)

    async def _close_session(self, session: LoginSession) -> None:
        cdp = self.bridge._cdp
        if not cdp:
            return
        with contextlib.suppress(Exception):
            await cdp.send(
                "Target.disposeBrowserContext",
                {"browserContextId": session.context_id},
            )

    async def _new_page(self) -> LoginSession:
        await self.bridge._ensure_browser()
        cdp = self.bridge._cdp
        if not cdp:
            raise BrowserUnavailableError("浏览器未启动")
        context_id = (
            await cdp.send("Target.createBrowserContext")
        )["browserContextId"]
        target_id = (
            await cdp.send(
                "Target.createTarget",
                {"url": "about:blank", "browserContextId": context_id},
            )
        )["targetId"]
        sid = (
            await cdp.send(
                "Target.attachToTarget", {"targetId": target_id, "flatten": True}
            )
        )["sessionId"]
        await cdp.send("Page.enable", {}, sid)
        await cdp.send("Runtime.enable", {}, sid)
        await cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1280, "height": 900, "deviceScaleFactor": 1, "mobile": False},
            sid,
        )
        await cdp.send("Page.navigate", {"url": LOGIN_URL}, sid)
        await asyncio.sleep(5)
        return LoginSession(
            session_id=secrets.token_urlsafe(24),
            context_id=context_id,
            target_id=target_id,
            cdp_session_id=sid,
            method="",
            phone="",
        )

    async def _eval(self, session: LoginSession, expression: str) -> Any:
        cdp = self.bridge._cdp
        if not cdp:
            raise BrowserUnavailableError("浏览器未启动")
        result = await cdp.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            session.cdp_session_id,
        )
        if "exceptionDetails" in result:
            raise BrowserError(str(result["exceptionDetails"])[:200])
        return result.get("result", {}).get("value")

    async def _click_text(self, session: LoginSession, text: str) -> bool:
        return bool(
            await self._eval(
                session,
                """(() => {
                  const norm = s => (s || '').replace(/\\s+/g, '');
                  const el = [...document.querySelectorAll('*')]
                    .find(e => norm(e.innerText) === norm(__TEXT__));
                  if (!el) return false;
                  (el.closest('button,a') || el).click();
                  return true;
                })()""".replace("__TEXT__", json.dumps(text)),
            )
        )

    async def _click_selector(self, session: LoginSession, selector: str) -> bool:
        return bool(
            await self._eval(
                session,
                """(() => {
                  const el = document.querySelector(__SELECTOR__);
                  if (!el) return false;
                  el.click();
                  return true;
                })()""".replace("__SELECTOR__", json.dumps(selector)),
            )
        )

    async def _fill(self, session: LoginSession, selector: str, value: str) -> bool:
        cdp = self.bridge._cdp
        if not cdp:
            raise BrowserUnavailableError("浏览器未启动")
        rect = await self._eval(
            session,
            """(() => {
              const el = document.querySelector(__SELECTOR__);
              if (!el) return null;
              el.scrollIntoView({block:'center'});
              el.focus();
              el.select?.();
              const r = el.getBoundingClientRect();
              return {x:r.left+r.width/2, y:r.top+r.height/2};
            })()""".replace("__SELECTOR__", json.dumps(selector)),
        )
        if not rect:
            return False
        await cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": rect["x"], "y": rect["y"], "button": "left", "clickCount": 1},
            session.cdp_session_id,
        )
        await cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": rect["x"], "y": rect["y"], "button": "left", "clickCount": 1},
            session.cdp_session_id,
        )
        await cdp.send(
            "Input.insertText", {"text": value}, session.cdp_session_id
        )
        return True

    async def _extract(self, session: LoginSession) -> BrowserLoginResult:
        cdp = self.bridge._cdp
        if not cdp:
            raise BrowserUnavailableError("浏览器未启动")
        cookies = (
            await cdp.send(
                "Network.getAllCookies", {}, session.cdp_session_id
            )
        ).get("cookies", [])
        pairs = [
            f"{c['name']}={c['value']}"
            for c in cookies
            if "missevan.com" in (c.get("domain") or "")
        ]
        cookie = "; ".join(pairs)
        if not cookie:
            return BrowserLoginResult(False, reason="登录后没有取到 Cookie")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    USER_INFO_URL,
                    headers={
                        "Cookie": cookie,
                        "Origin": "https://fm.missevan.com",
                        "Referer": "https://fm.missevan.com/",
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/158.0.0.0 Safari/537.36 Edg/158.0.0.0"
                        ),
                    },
                )
                body = resp.json()
                user = (body.get("info") or {}).get("user") or {}
                if not user.get("user_id"):
                    return BrowserLoginResult(False, reason="登录态无效")
                return BrowserLoginResult(
                    True,
                    cookie=cookie,
                    user_id=int(user["user_id"]),
                    username=str(user.get("username") or ""),
                )
        except Exception as exc:  # noqa: BLE001 —— 登录结果统一转成失败文案
            return BrowserLoginResult(False, reason=f"验证 Cookie 失败:{str(exc)[:120]}")

    async def start_sms(self, phone: str) -> tuple[str, str]:
        """打开验证码登录页、填写手机号并点击获取验证码。"""
        session = await self._new_page()
        session.method = "sms"
        session.phone = phone
        try:
            await self._click_text(session, "验证码登录")
            if not await self._fill(session, 'input[placeholder="请输入手机号"]', phone):
                raise BrowserError("找不到手机号输入框")
            if not await self._click_text(session, "获取验证码"):
                raise BrowserError("找不到获取验证码按钮")
            async with self._lock:
                self._sessions[session.session_id] = session
            return session.session_id, "验证码已发送"
        except Exception:
            await self._close_session(session)
            raise

    async def start_password(self, phone: str, password: str) -> BrowserLoginResult:
        """用户名(手机号) + 密码登录。"""
        session = await self._new_page()
        session.method = "password"
        session.phone = phone
        try:
            await self._click_text(session, "密码登录")
            await asyncio.sleep(1)
            account_selector = 'input[placeholder="请输入手机号"]'
            if "@" in phone:
                await self._click_text(session, "邮箱账号登录")
                await asyncio.sleep(1)
                account_selector = 'input[placeholder*="邮箱"]'
            if not await self._fill(session, account_selector, phone):
                raise BrowserError("找不到账号输入框")
            if not await self._fill(session, 'input[type="password"]', password):
                raise BrowserError("找不到密码输入框")
            if not await self._click_selector(session, ".login-btn"):
                raise BrowserError("找不到登录按钮")
            await asyncio.sleep(6)
            return await self._extract(session)
        finally:
            await self._close_session(session)

    async def submit_sms(self, session_id: str, code: str) -> BrowserLoginResult:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return BrowserLoginResult(False, reason="登录会话不存在或已过期")
            if time.time() - session.created_at > LOGIN_TTL:
                self._sessions.pop(session_id, None)
                await self._close_session(session)
                return BrowserLoginResult(False, reason="登录会话已过期，请重新获取验证码")
        try:
            if not await self._fill(session, 'input[placeholder="请输入验证码"]', code):
                return BrowserLoginResult(False, reason="找不到验证码输入框")
            if not await self._click_selector(session, ".login-btn"):
                return BrowserLoginResult(False, reason="找不到登录按钮")
            await asyncio.sleep(6)
            result = await self._extract(session)
            if result.ok:
                async with self._lock:
                    self._sessions.pop(session_id, None)
                await self._close_session(session)
            return result
        except Exception as exc:  # noqa: BLE001 —— 登录失败统一转成失败文案
            return BrowserLoginResult(False, reason=f"验证码登录失败:{str(exc)[:120]}")


__all__ = ["BrowserLoginManager", "BrowserLoginResult", "LoginSession"]
