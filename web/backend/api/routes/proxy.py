"""图片代理 —— 绕过 CDN Referer 校验导致的 403。

前端以 ``<img src="/api/proxy/image?url=...">`` 的形式使用本端点,
``<img>`` 无法携带 Authorization header,因此本端点保持匿名可访问;
作为替代,通过「域名白名单 + 内网地址拦截 + 重定向逐跳校验」限制
可请求的目标,避免沦为 SSRF / 开放代理。

白名单可在 ``config.yml`` 中扩展(不配置则用内置默认值):

    proxy:
      allowed_hosts:
        - static.maoercdn.com
        - "*.maoercdn.com"
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter()

# 不自动跟随重定向——改为手动逐跳校验后再请求,避免「白名单域名 302 到内网」
_client = httpx.AsyncClient(timeout=10.0, follow_redirects=False)

#: 默认允许的图片 CDN 域名,支持 ``*.`` 前缀通配
_DEFAULT_ALLOWED_HOSTS = (
    "static.maoercdn.com",
    "*.maoercdn.com",
    "*.missevan.com",
)

_MAX_REDIRECTS = 3
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


# ------------------------------------------------------------------ #
# 目标校验
# ------------------------------------------------------------------ #

def _allowed_hosts() -> tuple[str, ...]:
    """读取白名单配置,缺省或配置非法时回退到内置列表。"""
    try:
        from core.config import ServerConfig

        configured = ServerConfig.load().get("proxy.allowed_hosts")
        if isinstance(configured, list):
            hosts = tuple(str(h).strip().lower() for h in configured if str(h).strip())
            if hosts:
                return hosts
    except Exception:
        pass
    return _DEFAULT_ALLOWED_HOSTS


def _host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    """判断主机名是否命中白名单(支持 ``*.example.com`` 形式)。"""
    host = host.lower().rstrip(".")
    for pattern in allowed:
        if pattern.startswith("*."):
            suffix = pattern[1:]  # ".example.com"
            # 通配不匹配裸域本身(裸域需显式列出)
            if host.endswith(suffix) and host != suffix[1:]:
                return True
        elif host == pattern:
            return True
    return False


def _is_public_ip(ip: str) -> bool:
    """判断 IP 是否为公网地址。

    ``is_global`` 为 False 覆盖私有 / 环回 / 链路本地 / 保留 / 多播 /
    未指定地址,以及 CGNAT(100.64.0.0/10)。
    """
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


async def _resolves_to_public(host: str, port: int) -> bool:
    """解析主机名,确认**所有**解析结果都是公网地址。

    注意:此处解析与 httpx 实际建连是两次独立解析,理论上存在 DNS
    rebinding 窗口;域名白名单才是本端点的主要防线,这一步属纵深防御。
    """
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, port, type=socket.SOCK_STREAM
        )
    except (socket.gaierror, OSError):
        return False
    if not infos:
        return False
    return all(_is_public_ip(info[4][0]) for info in infos)


async def _validate_url(url: str) -> None:
    """校验目标 URL——scheme / 白名单 / 解析地址任一不合规即抛 403。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=403, detail="仅支持 http/https 图片地址")

    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=403, detail="图片地址缺少主机名")

    if not _host_allowed(host, _allowed_hosts()):
        raise HTTPException(status_code=403, detail=f"域名不在图片代理白名单中: {host}")

    try:
        port = parsed.port
    except ValueError:
        raise HTTPException(status_code=403, detail="图片地址端口非法")
    port = port or (443 if parsed.scheme == "https" else 80)

    if not await _resolves_to_public(host, port):
        raise HTTPException(status_code=403, detail="目标地址解析到内网或不可用地址")


# ------------------------------------------------------------------ #
# 路由
# ------------------------------------------------------------------ #

@router.get("/proxy/image")
async def proxy_image(url: str = Query(...)):
    """代理获取远程图片:设置空 Referer 绕过防盗链,并限制可请求目标。"""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        await _validate_url(current)
        try:
            async with _client.stream("GET", current, headers={"Referer": ""}) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        raise HTTPException(status_code=502, detail="重定向缺少 Location")
                    current = str(httpx.URL(current).join(location))
                    continue

                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="获取图片失败")

                content_type = resp.headers.get("content-type", "image/png")
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_BYTES:
                        raise HTTPException(status_code=413, detail="图片超过 10MB 上限")
                    chunks.append(chunk)
                return Response(content=b"".join(chunks), media_type=content_type)
        except HTTPException:
            raise
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=str(e))

    raise HTTPException(status_code=502, detail="重定向次数过多")
