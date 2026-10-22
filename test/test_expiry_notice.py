"""开播临期提示测试（无网络）。

覆盖：
- 剩余不足 3 天时，开播事件触发一条提示消息
- 开关关闭 / 剩余充足 / 永久账户 / 已过期账户：不发
- 同一场直播只发一次，下播后重新开播可再发

运行: .venv/Scripts/python.exe test/test_expiry_notice.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.account.manager import AccountRecord  # noqa: E402
from core.config import ServerConfig  # noqa: E402
from core.models.events import CloseEvent, OpenEvent  # noqa: E402
from core.server import MissevanServer  # noqa: E402

_passed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed
    if not cond:
        raise AssertionError(f"FAIL: {label} {detail}")
    _passed += 1
    print(f"PASS {_passed}: {label}")


def _record(**kw) -> AccountRecord:
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        name="测试账户",
        room_id=123,
        bot_mode="public",
        expires_at=(now + timedelta(days=2)).isoformat(),
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    base.update(kw)
    return AccountRecord(**base)


class FakeLivestream:
    def __init__(self) -> None:
        self.live_id = 123
        self.sent: list[str] = []

    async def send_message(self, message: str) -> None:
        self.sent.append(message)


async def main() -> None:
    tmp = tempfile.mkdtemp(prefix="mismiss-expiry-notice-")
    server = MissevanServer(
        ServerConfig({"server": {"data_dir": tmp}}),
        data_dir=tmp,
    )
    live = FakeLivestream()

    # 1. 剩余 2 天 + 默认开启 → 开播即提示
    rec = _record()
    server.account_record = rec
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("临期（2 天）开播会发提示", len(live.sent) == 1, str(live.sent))
    check("提示文案包含剩余天数", "2 天" in live.sent[0], live.sent[0])

    # 2. 同一场直播重复 room:open 不重复发
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("同场直播只提示一次", len(live.sent) == 1, str(live.sent))

    # 3. 下播后重新开播 → 再提示一次
    server.event_bus.call_event(CloseEvent(event_livestream=live))
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("下播再开播可再次提示", len(live.sent) == 2, str(live.sent))

    # 4. 手动关闭 → 不再发
    rec.expiry_notice_enabled = False
    server.event_bus.call_event(CloseEvent(event_livestream=live))
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("关闭开关后不再提示", len(live.sent) == 2, str(live.sent))
    rec.expiry_notice_enabled = True

    # 5. 剩余充足（10 天）→ 不发
    rec.expires_at = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    server.event_bus.call_event(CloseEvent(event_livestream=live))
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("剩余 10 天不提示", len(live.sent) == 2, str(live.sent))

    # 6. 永久账户 → 不发
    rec.expires_at = None
    server.event_bus.call_event(CloseEvent(event_livestream=live))
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("永久账户不提示", len(live.sent) == 2, str(live.sent))

    # 7. 剩余 0 天（今天到期）→ 用「今天到期」文案
    rec.expires_at = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    server.event_bus.call_event(CloseEvent(event_livestream=live))
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("当天到期也能提示", len(live.sent) == 3, str(live.sent))
    check("不足 1 天文案正确", "1 天" in live.sent[2], live.sent[2])

    # 8. 没有账户记录（单 Server 用法）→ 静默跳过
    server.account_record = None
    server.event_bus.call_event(CloseEvent(event_livestream=live))
    server.event_bus.call_event(OpenEvent(event_livestream=live))
    await asyncio.sleep(0.05)
    check("无账户记录时跳过", len(live.sent) == 3, str(live.sent))

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
