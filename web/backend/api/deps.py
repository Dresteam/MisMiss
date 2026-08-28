"""FastAPI 依赖注入 —— 提供 AccountManager 与账户级运行时。"""

from __future__ import annotations

from fastapi import HTTPException

from core import MissevanServer
from core.account import AccountManager
from core.exceptions import (
    CoreAccountExpiredException,
    CoreAccountNotFoundException,
)

# ------------------------------------------------------------------ #
# 模块级单例存储
# ------------------------------------------------------------------ #

_manager: AccountManager | None = None


def set_account_manager(m: AccountManager) -> None:
    """由 lifespan 在启动时调用,注入 AccountManager 实例。"""
    global _manager
    _manager = m


def get_account_manager() -> AccountManager:
    """面板级依赖 —— 获取 AccountManager(账户 CRUD / 公共 Bot / 授权码)。"""
    if _manager is None:
        raise RuntimeError("AccountManager 尚未启动")
    return _manager


def _to_http(e: Exception) -> HTTPException:
    if isinstance(e, CoreAccountNotFoundException):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, CoreAccountExpiredException):
        return HTTPException(status_code=403, detail=str(e))
    return HTTPException(status_code=500, detail=str(e))


def require_account(account_id: int) -> MissevanServer:
    """账户级依赖(读/写通用)—— 返回账户运行时并同步跨 worker 状态。

    不做过期检查(读端点可用,便于查看已过期账户状态)。
    """
    try:
        server = _manager.get_server(account_id)
    except CoreAccountNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    server._ensure_state_fresh()
    return server


def require_active_account(account_id: int) -> MissevanServer:
    """账户级依赖(写操作)—— 过期账户拒绝(403)。"""
    try:
        server = _manager.require_active(account_id)
    except (CoreAccountNotFoundException, CoreAccountExpiredException) as e:
        raise _to_http(e)
    return server
