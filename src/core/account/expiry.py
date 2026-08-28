"""账户到期调度器 —— 周期性检查并强制停用已到期账户。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from core.logging import get_logger

if TYPE_CHECKING:
    from core.account.manager import AccountManager

_log = get_logger(__name__)


class ExpiryScheduler:
    """每 ``interval`` 秒检查一次账户到期状态,到期即强制停用(幂等)。"""

    def __init__(self, manager: "AccountManager", interval: float = 60.0) -> None:
        self._manager = manager
        self._interval = max(5.0, float(interval))
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_event_loop().create_task(self._run())
            _log.info("账户到期调度器已启动 (每 {}s 检查)", self._interval)

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def tick(self) -> None:
        """执行一轮到期检查(供测试直接调用)。"""
        for rec in self._manager.list_records():
            if not rec.expired:
                continue
            if rec.paused_reason == "expiry":
                continue
            try:
                await self._manager.stop_for_expiry(rec.id)
            except Exception as e:
                _log.error("账户 {} 到期停用失败: {}", rec.id, e)

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                await self.tick()
        except asyncio.CancelledError:
            pass
        finally:
            _log.info("账户到期调度器已停止")
