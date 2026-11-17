"""重启时「开播中的直播间优先恢复」测试（无网络）。

覆盖：
- 服务器内部多直播间按 is_streaming 排序；
- 账户启动前探测开播状态，只探未过期且已绑定的房间；
- start_all 按「开播中 → 其它启用 → 已过期」排序。
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.account import manager as manager_mod  # noqa: E402
from core.account.manager import AccountManager, AccountRecord  # noqa: E402
from core.config import ServerConfig  # noqa: E402
from core.server import MissevanServer  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def _record(rid: int, room_id: int | None, expires_at: str | None = None) -> AccountRecord:
    return AccountRecord(
        id=rid, name=f"账户{rid}", room_id=room_id, bot_mode="public",
        expires_at=expires_at, created_at="", updated_at="",
    )


async def main() -> None:
    # ---- 1. 服务器内部排序 ----
    tmp = tempfile.mkdtemp(prefix="mismiss-start-priority-")
    server = MissevanServer(data_dir=tmp, state_file="server_state.json")
    server._livestreams = {
        1: SimpleNamespace(live_id=1, is_streaming=False),
        2: SimpleNamespace(live_id=2, is_streaming=True),
        3: SimpleNamespace(live_id=3, is_streaming=True),
    }
    server._enabled_livestreams = {1, 2, 3}
    check(
        "开播中的直播间排在前面",
        server._ordered_enabled_livestream_ids() == [2, 3, 1],
        str(server._ordered_enabled_livestream_ids()),
    )

    # ---- 2. 启动前探测 ----
    mgr = AccountManager(ServerConfig({
        "server": {"data_dir": tmp},
        "ratelimit": {"startup_stagger": 0},
    }))
    records = [
        _record(1, 10),
        _record(2, 20),
        _record(3, None),
        _record(4, 30, expires_at="2000-01-01T00:00:00+00:00"),  # 已过期，不探测
    ]
    probed: list[int] = []

    class _FakeRoomInfo:
        async def api(self, room_id: int):
            probed.append(room_id)
            return {"code": 0, "info": {"room": {"status": {"open": 1 if room_id == 20 else 0}}}}

    manager_mod.RoomInfoAPI = _FakeRoomInfo  # type: ignore[assignment]
    live = await mgr._probe_streaming_rooms(records)
    check("只探测未过期且已绑定的房间", sorted(probed) == [10, 20], str(probed))
    check("识别出开播中的房间", live == {20}, str(live))

    # ---- 3. start_all 排序 ----
    mgr._records = {r.id: r for r in records}
    started: list[int] = []

    async def fake_probe(_records):
        return {20}

    async def fake_start(rec):
        started.append(rec.id)
        return None

    mgr._probe_streaming_rooms = fake_probe  # type: ignore[method-assign]
    mgr._start_account = fake_start  # type: ignore[method-assign]
    await mgr.start_all()
    check("开播中的账户最先启动", started[0] == 2, str(started))
    check("未开播的启用账户随后启动", started[1:3] == [1, 3], str(started))
    check("已过期账户最后启动", started[-1] == 4, str(started))

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
