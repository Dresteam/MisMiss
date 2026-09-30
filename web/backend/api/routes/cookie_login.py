"""私有 Cookie 自助登录(账户级)。

私有 Cookie 账户原本只能由用户从浏览器开发者工具里手动复制 Cookie，
对非技术用户门槛很高。本模块负责取回 Cookie 的那一半：

1. 面板签发一个一次性 token（``/helper/token``），前端把它内嵌进书签；
2. 用户把书签拖到书签栏，在**猫耳页面**上点一下；
3. 书签把 Cookie 回传给匿名端点（``/api/helper/cookie``）；
4. 本模块校验 token、把 Cookie 装到账户上。

**不能由面板后端代发登录请求** —— 登录必须由用户在自己的浏览器里、在猫耳
自己的页面上完成。曾经实现过一版后端代发的短信登录，实测一律回
``100010007 滑动验证失败``；对照浏览器抓包，原因是猫耳的登录接口至少有三道
服务端无法伪造的门槛（2026-09-29 逐项核对）：

1. ``Content-Type: application/x-www-form-urlencoded``（body 却是 JSON 文本）；
2. 每个请求都带 ``X-M-DeviceSign`` —— 由猫耳的指纹库算出 ``visitorId``
   再对 URL 签名，天生要求请求方是个有真实指纹的浏览器；
3. 一整套登录页访客会话 Cookie（``FM_SESS`` / ``FM_SESS.sig`` / ``MSESSID``
   / ``buvid3`` / ``buvid4`` …），其中 ``FM_SESS.sig`` 还是签过名的。

验证码多半就绑在第 3 条那个会话上：题发给谁、就只认谁提交。这也意味着
**后端模拟浏览器同样走不通**，那等于用自动化手段去骗过指纹与风控。

成功取到 Cookie 后会**把账户切成私有模式**（``bot_mode="private"``）——
自助换号的典型场景就是「原本用着面板公共 Cookie，想换回自己的号」。
本模块自身不读取面板的共享 Cookie，所以公共账户走这条路不存在越权。
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core import MissevanServer
from core.exceptions import (
    CoreAccountExpiredException,
    CoreAccountNotFoundException,
    CoreApiException,
    CoreCookieException,
)
from api.deps import get_account_manager, require_account, require_active_account
from api.routes.auth import _DATA_ROOT
from api.schemas import HelperStatusResponse, HelperTokenResponse

# 账户级路由:挂载于 /api/accounts/{account_id},认证中间件按归属校验。
# 注意路径必须带 {account_id} —— 中间件仅在 parts[3].isdigit() 时才比对归属,
# 字面量子路径(如 /api/accounts/helper/...)对任意账户令牌都是敞开的。
router = APIRouter()

# 匿名路由:挂载于 /api/helper,只服务于书签回传。
# 在 main.py 的 PUBLIC_PATHS 里登记精确路径,不要放进 PUBLIC_PREFIXES。
public_router = APIRouter()


# ------------------------------------------------------------------ #
# 常量与存储
# ------------------------------------------------------------------ #

_HELPER_TOKEN_DIR = _DATA_ROOT / "helper_tokens"
_HELPER_TTL = 300.0           # token 5 分钟有效,足够用户切到猫耳点一下书签
_MAX_HELPER_BODY = 16 * 1024  # 书签只发一个 Cookie 串,16KB 绰绰有余

# 失败计数只是纵深防御 —— token 本身是 32 字节随机、一次性、5 分钟过期,
# 穷举不可行。刻意不做按 IP 限流:应用跑在 nginx 后面,request.client.host
# 恒为反代地址,而 X-Forwarded-For 可伪造,按 IP 限流反而制造出
# 「伪造 XFF 即可绕过」或「误伤全部用户」的两难。全局计数不撒谎。
_helper_failures: list[float] = []
_HELPER_FAILURE_WINDOW = 300.0
_HELPER_FAILURE_MAX = 100


def _token_path(token: str):
    return _HELPER_TOKEN_DIR / f"{token}.json"


def _is_valid_helper_token(token: str) -> bool:
    """token 必须是 ``secrets.token_hex(32)`` 的 64 位十六进制串。

    token 会被直接拼进文件名,必须挡住 ``../`` 之类的路径穿越。
    """
    return len(token) == 64 and all(c in "0123456789abcdef" for c in token)


def _write_helper_record(token: str, data: dict) -> None:
    _HELPER_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    path = _token_path(token)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_helper_record(token: str) -> dict | None:
    if not _is_valid_helper_token(token):
        return None
    try:
        data = json.loads(_token_path(token).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() > float(data.get("expires", 0)):
        return None
    return data


def _sweep_helper_tokens() -> None:
    """顺手清掉过期记录。惰性清扫,不引入后台任务。"""
    now = time.time()
    try:
        paths = list(_HELPER_TOKEN_DIR.glob("*.json"))
    except OSError:
        return
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if now <= float(data.get("expires", 0)):
            continue
        for target in (path, path.with_suffix(".claim")):
            try:
                target.unlink()
            except OSError:
                pass


def _mint_helper_token(account_id: int) -> tuple[str, float]:
    _sweep_helper_tokens()
    token = secrets.token_hex(32)
    expires = time.time() + _HELPER_TTL
    _write_helper_record(token, {
        "account_id": int(account_id),
        "expires": expires,
        "state": "waiting",
        "message": "",
    })
    return token, expires


def _claim_helper_token(token: str) -> bool:
    """原子地抢占 token,返回 False 表示已被消费过。

    用 ``O_CREAT|O_EXCL`` 建标记文件 —— 多 worker 下也只有一个进程能建成,
    从而保证「一次性」。单靠读改写会两边都读到 waiting。
    """
    _HELPER_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    claim = _HELPER_TOKEN_DIR / f"{token}.claim"
    try:
        os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    return True


def _helper_failure_allows() -> bool:
    now = time.time()
    _helper_failures[:] = [t for t in _helper_failures if now - t < _HELPER_FAILURE_WINDOW]
    return len(_helper_failures) < _HELPER_FAILURE_MAX


def _bad_helper_request() -> HTTPException:
    """失败一律同一个响应,不区分「token 不存在」与「已使用」,免得变成探测器。"""
    return HTTPException(status_code=400, detail="请求无效")


# ------------------------------------------------------------------ #
# 公共逻辑
# ------------------------------------------------------------------ #

# 每账户一把锁:create_bot 逐个停用/启用插件并非原子操作,并发调用会互相踩
_swap_locks: dict[int, asyncio.Lock] = {}


def _lock_for(account_id: int) -> asyncio.Lock:
    lock = _swap_locks.get(account_id)
    if lock is None:
        lock = asyncio.Lock()
        _swap_locks[account_id] = lock
    return lock


async def _resolve_target_server(account_id: int) -> MissevanServer:
    """取出可写 Cookie 的账户运行时。

    **不拒绝公共模式账户** —— 自助取 Cookie 的典型场景正是「原本用着面板公共
    Cookie,想换回自己的号」,``_apply_cookie`` 会顺带把模式切成 private。

    过期账户仍一律拒绝:``create_bot`` 会重新启用全部插件,而到期停用走的是
    ``suspend_all()``(注销 handler 但**保留启用标记**),放行会让已暂停
    账户的插件复活。先续期再取 Cookie 即可。
    """
    manager = get_account_manager()
    try:
        server = manager.require_active(account_id)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CoreAccountExpiredException as e:
        raise HTTPException(status_code=403, detail=str(e))
    return server


async def _apply_cookie(account_id: int, cookie: str) -> tuple[str, str]:
    """把新 Cookie 装到账户上,返回 ``(Bot 名, 给用户看的成功文案)``。

    走 ``switch_bot_mode(..., "private", ...)``:它一步完成「换 Cookie + 把
    ``bot_mode`` 改成 private + 落盘 panel.json」。少了切模式那一步,从公共
    Cookie 自助换号的账户会停在**分裂状态** —— Bot 实际跑着用户自己的 Cookie,
    记录里却仍是公共模式,于是 ``/bot/cookie`` 继续 403、面板也仍按公共账户展示。

    权限沿用当前 Bot 的(``BotPermission`` 空集是假值,会被 ``update_cookie``
    当成「下发 0 权限」,故折成 None 表示保留):账户持有者不该经由「获取
    Cookie」改变权限位。

    ``refresh()`` 在插件被动到之前就抛异常,所以 Cookie 无效时什么都不会变。
    """
    server = await _resolve_target_server(account_id)
    was_public = getattr(server.account_record, "bot_mode", "private") == "public"
    perms = server.bot.permissions or None
    async with _lock_for(account_id):
        try:
            await get_account_manager().switch_bot_mode(
                account_id, "private", cookie, permissions=perms,
            )
        except CoreCookieException as e:
            raise HTTPException(status_code=400, detail=f"Cookie 无效:{e}")
        except CoreApiException as e:
            raise HTTPException(status_code=502, detail=f"验证 Cookie 时平台接口出错:{e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    name = server.bot.name or "Bot"
    note = "(已从公共 Cookie 切换为自定义 Cookie)" if was_public else ""
    return name, f"已更新 Bot「{name}」的 Cookie{note}"


async def _read_body_capped(request: Request) -> bytes:
    """流式读 body 并设上限。Starlette 的 ``request.body()`` 会把任意大小的
    请求体整个收进内存,这里按块累计,超限立刻断开。"""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _MAX_HELPER_BODY:
            raise HTTPException(status_code=413, detail="请求体过大")
        chunks.append(chunk)
    return b"".join(chunks)


# ------------------------------------------------------------------ #
# 书签助手 —— 账户级
# ------------------------------------------------------------------ #

@router.post("/helper/token", response_model=HelperTokenResponse)
async def helper_issue_token(
    account_id: int, s: MissevanServer = Depends(require_active_account)
):
    """签发一个一次性 token,由前端内嵌进书签链接。

    ``s`` 只为过期守卫而声明(公共模式账户同样可以自助取 Cookie)。
    """
    token, expires = _mint_helper_token(account_id)
    return HelperTokenResponse(token=token, expires_at=expires)


@router.get("/helper/status", response_model=HelperStatusResponse)
async def helper_status(
    account_id: int,
    request: Request,
    s: MissevanServer = Depends(require_account),
):
    """查询 token 是否已被书签消费。

    书签端是 ``no-cors``,拿不到任何响应,所以「成没成功」只能由页面轮询这里得知。
    token 走 ``X-Helper-Token`` 头而非查询参数 —— 生产环境开了
    ``--access-logfile``,查询参数会被原样写进访问日志。
    """
    token = request.headers.get("X-Helper-Token", "").strip()
    data = _read_helper_record(token)
    if data is None or int(data.get("account_id", -1)) != int(account_id):
        return HelperStatusResponse(state="failed", message="凭证已失效,请重新生成")
    return HelperStatusResponse(
        state=str(data.get("state", "waiting")),
        message=str(data.get("message", "")),
    )


# ------------------------------------------------------------------ #
# 书签助手 —— 匿名回传
# ------------------------------------------------------------------ #

@public_router.post("/cookie")
async def helper_receive(request: Request):
    """接收书签推来的 Cookie(匿名端点,靠 token 授权)。

    书签端只能用 ``fetch(..., {mode:'no-cors'})``:该模式不允许触发预检,
    因此只能发 ``text/plain``,走不了 Pydantic 的 JSON body 模型 ——
    这里直接读原始 body 自行解析。

    处理结果写回 token 记录,由页面轮询 ``/helper/status`` 呈现;
    本端点对书签端始终返回 200(反正它也读不到),只有请求本身非法才回错。
    """
    raw = await _read_body_capped(request)
    try:
        payload = json.loads(raw.decode("utf-8"))
        token = str(payload["token"])
        cookie = str(payload["cookie"]).strip()
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise _bad_helper_request()

    if not _helper_failure_allows():
        raise HTTPException(status_code=429, detail="尝试过于频繁,请稍后再试")

    # 先校验格式与存在性,再抢占 —— 顺序反了会拿非法 token 去建文件
    if not cookie:
        raise _bad_helper_request()
    data = _read_helper_record(token)
    if data is None or not _claim_helper_token(token):
        _helper_failures.append(time.time())
        raise _bad_helper_request()

    account_id = int(data["account_id"])
    try:
        _name, message = await _apply_cookie(account_id, cookie)
    except HTTPException as e:
        _write_helper_record(token, {**data, "state": "failed", "message": str(e.detail)})
        return JSONResponse(status_code=200, content={"success": False})

    _write_helper_record(token, {**data, "state": "done", "message": message})
    return JSONResponse(status_code=200, content={"success": True})


