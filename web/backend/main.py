"""MisMiss Web 控制台 —— FastAPI 后端入口。

启动方式::

    cd MisMiss/
    python -m web.backend.main

或::

    cd web/backend
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# ------------------------------------------------------------------ #
# 路径 & 工作目录
# ------------------------------------------------------------------ #

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND_ROOT = Path(__file__).resolve().parent
os.chdir(str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_BACKEND_ROOT))  # web/backend/ — for `from api.xxx import ...`

# ------------------------------------------------------------------ #
# 第三方
# ------------------------------------------------------------------ #

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# ------------------------------------------------------------------ #
# 项目
# ------------------------------------------------------------------ #

from core.logging import get_logger
from core import MissevanServer
from api.deps import set_server
from api.routes import bot, live, plugin, server, dashboard, ws, config, proxy, auth

_log = get_logger("web.api")

# ------------------------------------------------------------------ #
# 全局 Server 单例
# ------------------------------------------------------------------ #

_server: MissevanServer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期——启动/关闭 MissevanServer。"""
    global _server
    _log.info("正在启动 MissevanServer ...")
    _server = MissevanServer()
    await _server.start()
    set_server(_server)
    _log.info("MissevanServer 已启动，API 就绪")
    yield
    _log.info("正在关闭 MissevanServer ...")
    try:
        await _server.shutdown()
    except Exception:
        pass
    _server = None
    _log.info("MissevanServer 已关闭")


# ------------------------------------------------------------------ #
# FastAPI 应用
# ------------------------------------------------------------------ #

app = FastAPI(
    title="MisMiss Web Console",
    description="MisMiss Bot 管理控制台 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — 开发环境允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# 认证中间件 —— 保护所有 /api/* 路由（/api/auth/* 和 /api/health 除外）
# ------------------------------------------------------------------ #

PUBLIC_PATHS = {"/api/auth/login", "/api/auth/check", "/api/health"}
PUBLIC_PREFIXES = ("/api/auth/", "/api/proxy/", "/api/ws")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # 公开路径跳过
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    # 非 API 路径跳过（静态文件等）
    if not path.startswith("/api/"):
        return await call_next(request)

    # 检查 Authorization header
    from api.routes.auth import verify_token
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token or not verify_token(token):
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})

    return await call_next(request)


# ------------------------------------------------------------------ #
# 路由注册
# ------------------------------------------------------------------ #

app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(bot.router, prefix="/api/bot", tags=["Bot"])
app.include_router(live.router, prefix="/api/live", tags=["Livestream"])
app.include_router(plugin.router, prefix="/api/plugin", tags=["Plugin"])
app.include_router(server.router, prefix="/api/server", tags=["Server"])
app.include_router(ws.router, prefix="/api", tags=["WebSocket"])
app.include_router(config.router, prefix="/api", tags=["Config"])
app.include_router(proxy.router, prefix="/api", tags=["Proxy"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])

# 生产环境静态文件（前端构建产物）
_FRONTEND_DIST = _PROJECT_ROOT / "web" / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")


# ------------------------------------------------------------------ #
# 健康检查
# ------------------------------------------------------------------ #

@app.get("/api/health")
async def health():
    return {"status": "ok", "server_running": _server is not None}


# ------------------------------------------------------------------ #
# 入口
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="API 端口 (默认 8000)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "web.backend.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        reload_dirs=[str(_PROJECT_ROOT / "src"), str(_PROJECT_ROOT / "web" / "backend")],
    )
