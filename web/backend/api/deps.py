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
    """FastAPI 依赖——获取并刷新当前 Server 实例。

    每次 API 请求自动调用 :meth:`MissevanServer._ensure_state_fresh`，
    通过 state 文件的 mtime 判断是否有其他 worker 修改了状态，
    保证 Docker 多 worker 下所有页面的数据一致。

    用法::

        @router.get("/...")
        async def handler(s: MissevanServer = Depends(get_server)):
            ...
    """
    if _server is None:
        raise RuntimeError("MissevanServer 尚未启动")
    _server._ensure_state_fresh()
    return _server
