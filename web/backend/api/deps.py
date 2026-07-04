"""FastAPI 依赖注入 —— 提供 MissevanServer 单例。"""

from __future__ import annotations

from core import MissevanServer

# ------------------------------------------------------------------ #
# 模块级单例存储
# ------------------------------------------------------------------ #

_server: MissevanServer | None = None


def set_server(s: MissevanServer) -> None:
    """由 lifespan 在启动时调用，注入 Server 实例。"""
    global _server
    _server = s


def get_server() -> MissevanServer:
    """FastAPI 依赖——获取当前 Server 实例。

    用法::

        @router.get("/...")
        async def handler(s: MissevanServer = Depends(get_server)):
            ...
    """
    if _server is None:
        raise RuntimeError("MissevanServer 尚未启动")
    return _server
