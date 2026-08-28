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

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # PyInstaller --onefile 模式：运行时根目录由 pyinstaller_entry 设置
    _PROJECT_ROOT = Path(os.environ.get("MISMISS_HOME", os.getcwd()))
    _BUNDLE = Path(os.environ.get("MISMISS_BUNDLE", sys._MEIPASS))  # type: ignore[attr-defined]
    os.chdir(str(_PROJECT_ROOT))
    sys.path.insert(0, str(_PROJECT_ROOT))
    sys.path.insert(0, str(_BUNDLE / "src"))
    sys.path.insert(0, str(_BUNDLE / "web" / "backend"))
else:
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
from core.account import AccountManager, ExpiryScheduler, migrate_legacy_data
from core.config import ServerConfig
from api.deps import set_account_manager
from api.routes import (
    account, account_plugins, auth, bot, config, live, panel, plugin, proxy,
    server, timer, update, ws,
)

_log = get_logger("web.api")

# ------------------------------------------------------------------ #
# 全局 AccountManager 单例
# ------------------------------------------------------------------ #

_manager: AccountManager | None = None
_scheduler: ExpiryScheduler | None = None

# 数据目录(可由环境变量覆盖,便于数据卷分离与测试隔离)
_DATA_DIR = os.environ.get("MISMISS_DATA_DIR", "data")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期——迁移旧数据、启动账户管理器与到期调度器。"""
    global _manager, _scheduler
    _log.info("正在启动 MisMiss 多账户面板 ...")
    # 单服务器旧数据备份迁移(全新开始,幂等)
    migrate_legacy_data(_DATA_DIR)
    _manager = AccountManager(data_dir=_DATA_DIR)
    _manager.set_app(app)
    _manager.load()
    await _manager.start_all()
    _scheduler = ExpiryScheduler(_manager, interval=60.0)
    _scheduler.start()
    set_account_manager(_manager)
    _log.info("AccountManager 已启动,{} 个账户运行中", len(_manager.list_records()))
    yield
    _log.info("正在关闭 AccountManager ...")
    if _scheduler is not None:
        _scheduler.stop()
    try:
        await _manager.shutdown_all()
    except Exception:
        pass
    _manager = None
    _log.info("AccountManager 已关闭")


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

PUBLIC_PATHS = {"/api/auth/login", "/api/auth/check", "/api/auth/skip-first-login", "/api/health"}
PUBLIC_PREFIXES = ("/api/auth/", "/api/proxy/", "/api/ws", "/api/plugin/install", "/api/config/pip-install")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # OPTIONS 预检请求跳过（CORS preflight 不带 Authorization header）
    if request.method == "OPTIONS":
        return await call_next(request)

    # 公开路径跳过（含插件 UI 路由）
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)
    for prefix in ("/api/plugin/", "/api/accounts/"):
        if path.startswith(prefix) and "/plugin/" in path and "/ui/" in path:
            return await call_next(request)

    # 非 API 路径跳过（静态文件等）
    if not path.startswith("/api/"):
        return await call_next(request)

    # 检查 Authorization header
    from api.routes.auth import token_info
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    info = token_info(token) if token else None
    if info is None:
        return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})

    # 角色权限:
    # - admin 可访问全部
    # - account 仅可访问自己的账户级路径(/api/accounts/{自己的id}/...)
    if info.get("role") == "account":
        if path.startswith("/api/accounts/"):
            parts = path.split("/")
            # /api/accounts/{account_id}/...
            if len(parts) >= 4 and parts[3].isdigit():
                if int(parts[3]) != int(info.get("account_id") or -1):
                    return JSONResponse(status_code=403, content={"detail": "无权访问其他账户"})
        else:
            # 账户令牌仅允许:自己的账户路径、健康检查、认证、图片代理
            if not any(path.startswith(p) for p in ("/api/health", "/api/auth/", "/api/proxy/")):
                return JSONResponse(status_code=403, content={"detail": "账户登录无权访问面板功能"})

    return await call_next(request)


# ------------------------------------------------------------------ #
# 路由注册
# ------------------------------------------------------------------ #

app.include_router(panel.router, prefix="/api/panel", tags=["Panel"])
app.include_router(account.router, prefix="/api/accounts/{account_id}", tags=["Account"])
app.include_router(bot.router, prefix="/api/accounts/{account_id}/bot", tags=["Account-Bot"])
app.include_router(live.router, prefix="/api/accounts/{account_id}/live", tags=["Account-Live"])
app.include_router(timer.router, prefix="/api/accounts/{account_id}/timer", tags=["Account-Timer"])
app.include_router(
    account_plugins.router,
    prefix="/api/accounts/{account_id}/plugins",
    tags=["Account-Plugins"],
)
app.include_router(plugin.router, prefix="/api/plugin", tags=["PluginLibrary"])
app.include_router(server.router, prefix="/api/server", tags=["Server"])
app.include_router(ws.router, prefix="/api", tags=["WebSocket"])
app.include_router(config.router, prefix="/api", tags=["Config"])
app.include_router(proxy.router, prefix="/api", tags=["Proxy"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(update.router, prefix="/api/update", tags=["Update"])


# ------------------------------------------------------------------ #
# 健康检查（必须在 SPA fallback 之前注册，避免被兜底路由拦截）
# ------------------------------------------------------------------ #

@app.get("/api/health")
async def health():
    cfg = ServerConfig.load()
    return {
        "status": "ok",
        "server_running": _manager is not None,
        "account_count": len(_manager.list_records()) if _manager else 0,
        "api_port": cfg.get_int("server.api_port", 18080),
        "web_port": cfg.get_int("server.web_port", 15173),
    }


# 静态文件 & SPA fallback
# 开发模式：Vite(:5173) HMR 代理到本后端
# 单端口模式：npm run build 后，直接访问 8080 即可同时提供前端和 API
if _FROZEN:
    _FRONTEND_DIST = Path(os.environ.get("MISMISS_BUNDLE", sys._MEIPASS)) / "web" / "frontend" / "dist"  # type: ignore[attr-defined]
else:
    _FRONTEND_DIST = _PROJECT_ROOT / "web" / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        from fastapi.responses import FileResponse
        # 跳过 API 路径
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        file = _FRONTEND_DIST / full_path
        if file.is_file():
            return FileResponse(file)
        index = _FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not Found")


# ------------------------------------------------------------------ #
# 入口
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18080, help="API port (default 18080)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "web.backend.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
        reload_dirs=[str(_PROJECT_ROOT / "src"), str(_PROJECT_ROOT / "web" / "backend")],
    )
