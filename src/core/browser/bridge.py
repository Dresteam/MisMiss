"""可选浏览器发送兜底。

猫耳的 ``/api/chatroom/message/send`` 对部分账号会返回成功但静默丢弃消息；
真实浏览器页面发送则正常。本模块用系统 Edge/Chromium 的 CDP 执行真实页面
输入与点击，并在发送后查询直播间历史确认送达。

设计约束：

- 可选、默认关闭；没有浏览器时只抛 :class:`BrowserUnavailableError`；
- 一个浏览器进程 + 每账户独立 Context，避免复制 Cookie；
- 并发由 ``Semaphore`` 限制，同一房间串行，避免重复发送；
- 每条消息发送后查历史；查不到就返回失败，不把 ``code=0`` 当成功；
- Docker 默认不内置浏览器，推荐独立 sidecar 或宿主 Edge。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import websockets
from loguru import logger

from core.config import ServerConfig

ROOM_URL = "https://fm.missevan.com/live/{room_id}"
SEND_PATH = "/api/chatroom/message/send"
HISTORY_URL = "https://fm.missevan.com/api/v2/chatroom/history/message"
SEND_URL = "https://fm.missevan.com/api/chatroom/message/send"


class BrowserError(RuntimeError):
    """浏览器兜底基础异常。"""


class BrowserDisabledError(BrowserError):
    """配置未启用浏览器兜底。"""


class BrowserUnavailableError(BrowserError):
    """没有可用的 Edge/Chromium 或 CDP 启动失败。"""


@dataclass(frozen=True)
class BrowserConfig:
    enabled: bool = False
    edge_path: str = ""
    headless: bool = True
    max_concurrency: int = 2
    timeout_seconds: float = 45.0

    @classmethod
    def from_server_config(cls, cfg: ServerConfig) -> BrowserConfig:
        return cls(
            enabled=bool(cfg.get("browser.enabled", False)),
            edge_path=str(cfg.get("browser.edge_path", "") or ""),
            headless=bool(cfg.get("browser.headless", True)),
            max_concurrency=max(1, int(cfg.get("browser.max_concurrency", 2) or 2)),
            timeout_seconds=max(10.0, float(cfg.get("browser.timeout_seconds", 45) or 45)),
        )


@dataclass(frozen=True)
class BrowserSendResult:
    ok: bool
    msg_id: str = ""
    message: str = ""
    reason: str = ""


@dataclass
class _CDP:
    ws: Any
    next_id: int = 0
    pending: dict[int, asyncio.Future] | None = None
    events: asyncio.Queue | None = None
    reader_task: asyncio.Task | None = None

    def __post_init__(self) -> None:
        self.pending = {}
        self.events = asyncio.Queue()

    async def start(self) -> None:
        self.reader_task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg:
                fut = self.pending.pop(msg["id"], None)  # type: ignore[union-attr]
                if fut and not fut.done():
                    fut.set_result(msg)
            else:
                await self.events.put(msg)  # type: ignore[union-attr]

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        self.next_id += 1
        mid = self.next_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[mid] = fut  # type: ignore[index]
        payload: dict[str, Any] = {"id": mid, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        await self.ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(fut, timeout)
        if "error" in msg:
            raise BrowserError(f"{method}: {msg['error']}")
        return msg.get("result", {})

    async def wait_event(self, method: str, timeout: float = 40.0) -> dict[str, Any]:
        end = asyncio.get_running_loop().time() + timeout
        while True:
            left = end - asyncio.get_running_loop().time()
            if left <= 0:
                raise TimeoutError(method)
            evt = await asyncio.wait_for(self.events.get(), left)  # type: ignore[union-attr]
            if evt.get("method") == method:
                return evt

    async def close(self) -> None:
        if self.reader_task:
            self.reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader_task
        await self.ws.close()


def _parse_cookies(raw: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            result.append((name, value.strip()))
    return result


def _find_browser(edge_path: str = "") -> str:
    candidates: list[str] = []
    if edge_path:
        candidates.append(edge_path)
    env = os.environ.get("MIS_BROWSER_PATH", "")
    if env:
        candidates.append(env)
    if sys.platform == "win32":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates.extend(
            [
                str(Path(program_files) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(program_files) / "Google/Chrome/Application/chrome.exe"),
                str(Path(program_files_x86) / "Google/Chrome/Application/chrome.exe"),
            ]
        )
    else:
        candidates.extend(["chromium", "chromium-browser", "google-chrome", "msedge"])
    for candidate in candidates:
        if not candidate:
            continue
        path = shutil.which(candidate) or candidate
        if Path(path).is_file():
            return path
    raise BrowserUnavailableError(
        "未找到 Edge/Chromium；请安装浏览器或配置 browser.edge_path"
    )


class BrowserBridge:
    """浏览器发送兜底（单进程、多 Context、可并发）。"""

    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self._browser: asyncio.subprocess.Process | None = None
        self._cdp: _CDP | None = None
        self._browser_ws = ""
        self._profile_dir = ""
        self._start_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(config.max_concurrency)
        self._room_locks: dict[int, asyncio.Lock] = {}
        self._history = httpx.AsyncClient(timeout=20, follow_redirects=True)

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    async def close(self) -> None:
        if self._cdp:
            await self._cdp.close()
            self._cdp = None
        if self._browser:
            self._browser.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._browser.wait(), 5)
            self._browser = None
        if self._profile_dir:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = ""

    async def _ensure_browser(self) -> None:
        if self._cdp:
            return
        async with self._start_lock:
            if self._cdp:
                return
            executable = _find_browser(self.config.edge_path)
            self._profile_dir = tempfile.mkdtemp(prefix="mismiss-browser-")
            args = [
                executable,
                "--headless=new" if self.config.headless else "--start-maximized",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--remote-debugging-port=0",
                f"--user-data-dir={self._profile_dir}",
                "--window-size=1280,900",
                "about:blank",
            ]
            self._browser = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            port_file = Path(self._profile_dir) / "DevToolsActivePort"
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if self._browser.returncode is not None:
                    raise BrowserUnavailableError("浏览器启动后立即退出")
                if port_file.is_file():
                    lines = port_file.read_text(encoding="utf-8").splitlines()
                    if len(lines) >= 2:
                        port = lines[0].strip()
                        self._browser_ws = f"ws://127.0.0.1:{port}{lines[1].strip()}"
                        break
                await asyncio.sleep(0.2)
            if not self._browser_ws:
                raise BrowserUnavailableError("等待浏览器 DevTools 端口超时")
            ws = await websockets.connect(
                self._browser_ws, max_size=32 * 1024 * 1024, open_timeout=15
            )
            self._cdp = _CDP(ws)
            await self._cdp.start()
            logger.debug("浏览器兜底已启动: {}", executable)

    def _room_lock(self, room_id: int) -> asyncio.Lock:
        lock = self._room_locks.get(room_id)
        if lock is None:
            lock = asyncio.Lock()
            self._room_locks[room_id] = lock
        return lock

    async def send(
        self,
        cookie: str,
        room_id: int,
        message: str,
        *,
        timeout: float | None = None,
    ) -> BrowserSendResult:
        if not self.enabled:
            raise BrowserDisabledError("浏览器兜底未启用")
        if not cookie.strip() or room_id <= 0 or not message.strip():
            return BrowserSendResult(False, reason="invalid_args")
        timeout = timeout or self.config.timeout_seconds
        async with self._sem, self._room_lock(room_id):
            try:
                return await asyncio.wait_for(
                    self._send_once(cookie, room_id, message), timeout
                )
            except BrowserUnavailableError:
                raise
            except TimeoutError:
                return BrowserSendResult(False, reason="timeout")
            except Exception as exc:  # noqa: BLE001 —— 顶层兜底必须返回失败而非拖垮 Bot
                logger.warning("浏览器发送失败 房间={} 原因={}", room_id, exc)
                return BrowserSendResult(False, reason=str(exc)[:200])

    async def _send_once(
        self, cookie: str, room_id: int, message: str
    ) -> BrowserSendResult:
        await self._ensure_browser()
        assert self._cdp is not None
        cdp = self._cdp
        context_id = ""
        target_id = ""
        session_id = ""
        sent_at = int(time.time() * 1000)
        try:
            context_id = (
                await cdp.send("Target.createBrowserContext")
            )["browserContextId"]
            target_id = (
                await cdp.send(
                    "Target.createTarget",
                    {
                        "url": "about:blank",
                        "browserContextId": context_id,
                    },
                )
            )["targetId"]
            session_id = (
                await cdp.send(
                    "Target.attachToTarget",
                    {"targetId": target_id, "flatten": True},
                )
            )["sessionId"]
            await cdp.send("Network.enable", {}, session_id)
            await cdp.send("Page.enable", {}, session_id)
            await cdp.send("Runtime.enable", {}, session_id)
            await cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1280,
                    "height": 900,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
                session_id,
            )
            for name, value in _parse_cookies(cookie):
                await cdp.send(
                    "Network.setCookie",
                    {
                        "name": name,
                        "value": value,
                        "domain": ".missevan.com",
                        "path": "/",
                        "secure": True,
                    },
                    session_id,
                )
            await cdp.send(
                "Page.navigate",
                {"url": ROOM_URL.format(room_id=room_id)},
                session_id,
            )
            await cdp.wait_event("Page.loadEventFired", timeout=20)
            await asyncio.sleep(5)

            setup = (
                await cdp.send(
                    "Runtime.evaluate",
                    {
                        "expression": """(() => {
                          const i = document.querySelector('input[placeholder="输入消息"]');
                          const b = document.querySelector('button.btn-send');
                          if (!i || !b) return {error:'input/button missing'};
                          i.scrollIntoView({block:'center'});
                          i.focus();
                          const ri = i.getBoundingClientRect();
                          const rb = b.getBoundingClientRect();
                          return {
                            ok:true,
                            bx:rb.left+rb.width/2, by:rb.top+rb.height/2,
                          };
                        })()""",
                        "returnByValue": True,
                    },
                    session_id,
                )
            )["result"]["value"]
            if not setup.get("ok"):
                return BrowserSendResult(False, reason="room_input_missing")

            await cdp.send("Input.insertText", {"text": message}, session_id)
            await asyncio.sleep(0.5)
            for event_type in ("mousePressed", "mouseReleased"):
                await cdp.send(
                    "Input.dispatchMouseEvent",
                    {
                        "type": event_type,
                        "x": setup["bx"],
                        "y": setup["by"],
                        "button": "left",
                        "clickCount": 1,
                    },
                    session_id,
                )
            await asyncio.sleep(3)
            return await self._verify(cookie, room_id, message, sent_at)
        finally:
            if context_id:
                with contextlib.suppress(Exception):
                    await cdp.send(
                        "Target.disposeBrowserContext",
                        {"browserContextId": context_id},
                    )

    async def _verify(
        self, cookie: str, room_id: int, message: str, sent_at: int
    ) -> BrowserSendResult:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie,
            "Origin": "https://fm.missevan.com",
            "Referer": ROOM_URL.format(room_id=room_id),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36 Edg/158.0.0.0"
            ),
        }
        try:
            for attempt in range(3):
                if attempt:
                    await asyncio.sleep(1)
                resp = await self._history.get(
                    HISTORY_URL, headers=headers, params={"room_id": room_id}
                )
                body = resp.json()
                history = ((body.get("info") or {}).get("history") or [])
                for item in history:
                    if (item.get("message") or "") != message:
                        continue
                    created = int(item.get("create_time") or 0)
                    if created >= sent_at - 5000:
                        return BrowserSendResult(
                            True,
                            msg_id=str(item.get("msg_id") or ""),
                            message=message,
                        )
            return BrowserSendResult(False, message=message, reason="history_not_found")
        except Exception as exc:  # noqa: BLE001 —— 校验失败只返回原因，不让调用方崩溃
            return BrowserSendResult(
                False, message=message, reason=f"verify_failed:{str(exc)[:120]}"
            )


__all__ = [
    "BrowserBridge",
    "BrowserConfig",
    "BrowserDisabledError",
    "BrowserError",
    "BrowserSendResult",
    "BrowserUnavailableError",
]
