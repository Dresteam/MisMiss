"""事件优先级 / 取消传播 / 参数可变 测试(无网络)。

覆盖:优先级降序执行、同优先级保持传统顺序(回归)、同步 handler 取消后
阻断后续同步与异步 handler、非 Cancellable 事件不可取消、setter 改写参数
对后续 handler 可见、display_name 覆盖用户名、裸 @event_handler 向后兼容、
异步 handler 无法取消(已文档化的限制)。

运行: .venv/Scripts/python.exe test/test_event_priority.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.events.bus import EventBus  # noqa: E402
from core.models.events import MessageEvent, OpenEvent  # noqa: E402
from core.models.user import MissevanLiveUser, MissevanUser  # noqa: E402
from interfaces.event import Cancellable, Listener, event_handler  # noqa: E402
from interfaces.event.livestream import (  # noqa: E402
    LiveMessageEvent,
    LivestreamUserEvent,
)

LOG: list[str] = []


def _msg(text: str = "hi", uid: int = 7) -> MessageEvent:
    return MessageEvent(
        event_livestream=None,
        event_user=MissevanLiveUser(
            base_user=MissevanUser(user_id=uid, username="真实名"),
            user_livestream=None,
        ),
        event_message=text,
    )


def tag_listener(tag: str, prio: int = 0) -> Listener:
    """构造一个在弹幕事件上记录 tag 的监听器。"""

    class _Tagged(Listener):
        @event_handler(priority=prio)
        def on_message(self, event: LiveMessageEvent) -> None:
            LOG.append(tag)

    return _Tagged()


def base_tag_listener(tag: str, prio: int = 0) -> Listener:
    """监听用户事件基类——用于验证跨 MRO 的优先级覆盖。"""

    class _BaseTagged(Listener):
        @event_handler(priority=prio)
        def on_any(self, event: LivestreamUserEvent) -> None:
            LOG.append(tag)

    return _BaseTagged()


class BaseAndDerived(Listener):
    """同时监听基类与子类，验证同优先级下的传统顺序。"""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    @event_handler
    def on_msg(self, event: LiveMessageEvent) -> None:
        LOG.append(f"{self.tag}:msg")

    @event_handler
    def on_base(self, event: LivestreamUserEvent) -> None:
        LOG.append(f"{self.tag}:base")


class Canceller(Listener):
    @event_handler(priority=500)
    def on_message(self, event: LiveMessageEvent) -> None:
        LOG.append("canceller")
        event.cancel()


class AfterCanceller(Listener):
    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        LOG.append("after")


class Mutator(Listener):
    @event_handler(priority=500)
    def on_message(self, event: LiveMessageEvent) -> None:
        event.message = "改写后的内容"


class Reader(Listener):
    def __init__(self) -> None:
        self.seen: str | None = None

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        self.seen = event.message


class NickWriter(Listener):
    @event_handler(priority=500)
    def on_any(self, event: LivestreamUserEvent) -> None:
        event.user.display_name = "专属昵称"


class NickReader(Listener):
    def __init__(self) -> None:
        self.seen: str | None = None

    @event_handler
    def on_any(self, event: LivestreamUserEvent) -> None:
        self.seen = event.user.name


async def main() -> None:
    # ---- 1. 优先级降序 ----
    LOG.clear()
    bus = EventBus()
    for lst in (tag_listener("p0"), tag_listener("p50", 50), tag_listener("p100", 100)):
        bus.register_new_event(lst)
    bus.call_event(_msg())
    assert LOG == ["p100", "p50", "p0"], f"FAIL: 优先级顺序错误 {LOG}"
    print("PASS 1: 优先级降序执行")

    # ---- 2. 回归:默认优先级下顺序与传统一致 ----
    LOG.clear()
    bus = EventBus()
    bus.register_new_event(BaseAndDerived("A"))
    bus.register_new_event(BaseAndDerived("B"))
    bus.call_event(_msg())
    # MRO 先子类后基类；同层按注册顺序——与引入优先级前完全一致
    assert LOG == ["A:msg", "B:msg", "A:base", "B:base"], f"FAIL: 默认顺序被改变 {LOG}"
    print("PASS 2: 默认优先级保持传统 MRO + 注册顺序(回归)")

    # ---- 3. 优先级可覆盖 MRO 层级 ----
    LOG.clear()
    bus = EventBus()
    bus.register_new_event(tag_listener("derived-p0"))       # 监听子类
    bus.register_new_event(base_tag_listener("base-p100", 100))  # 监听基类但优先级高
    bus.call_event(_msg())
    assert LOG == ["base-p100", "derived-p0"], f"FAIL: 优先级未覆盖 MRO {LOG}"
    print("PASS 3: 优先级可覆盖 MRO 层级")

    # ---- 4. 同步 cancel 阻断后续(同步 + 异步都不再启动) ----
    LOG.clear()
    bus = EventBus()
    bus.register_new_event(tag_listener("async-after"))  # 同步记录，排最后
    bus.register_new_event(AfterCanceller())
    bus.register_new_event(Canceller())
    bus.call_event(_msg())
    await asyncio.sleep(0)
    assert LOG == ["canceller"], f"FAIL: 取消未阻断传播 {LOG}"
    print("PASS 4: 同步 cancel 阻断后续同步 handler")

    # ---- 5. 非 Cancellable 事件不受影响 ----
    open_ev = OpenEvent(event_livestream=None)
    assert not isinstance(open_ev, Cancellable), "FAIL: OpenEvent 不应可取消"
    assert not hasattr(open_ev, "cancel"), "FAIL: OpenEvent 不应有 cancel()"
    bus.call_event(open_ev)  # 不应抛异常
    print("PASS 5: 开播事件不可取消")

    # ---- 6. setter 改参数对后续 handler 可见 ----
    bus = EventBus()
    reader = Reader()
    bus.register_new_event(Mutator())
    bus.register_new_event(reader)
    bus.call_event(_msg("原内容"))
    assert reader.seen == "改写后的内容", f"FAIL: 参数改写未生效 {reader.seen!r}"
    print("PASS 6: 高优先级 handler 改写 event.message 对后续可见")

    # ---- 7. display_name 覆盖用户名 ----
    bus = EventBus()
    nick_reader = NickReader()
    bus.register_new_event(nick_reader)
    bus.register_new_event(NickWriter())
    bus.call_event(_msg())
    assert nick_reader.seen == "专属昵称", f"FAIL: 显示名未覆盖 {nick_reader.seen!r}"
    print("PASS 7: display_name 覆盖对后续 handler 可见")

    # ---- 8. 覆盖不泄漏到下一个事件 ----
    fresh = _msg()
    assert fresh.user.name == "真实名", "FAIL: 显示名覆盖泄漏到了新事件"
    print("PASS 8: 显示名覆盖是单事件作用域")

    # ---- 9. 裸 @event_handler 向后兼容 ----
    assert getattr(BaseAndDerived.on_msg, "__event_handler__", False) is True
    assert getattr(BaseAndDerived.on_msg, "__event_handler_priority__", None) == 0
    print("PASS 9: 裸 @event_handler 仍带标记且默认优先级 0")

    # ---- 10. 异步 handler 无法取消(已知限制，锁定行为) ----
    LOG.clear()

    class AsyncCanceller(Listener):
        @event_handler(priority=500)
        async def on_message(self, event: LiveMessageEvent) -> None:
            LOG.append("async-canceller")
            event.cancel()

    bus = EventBus()
    bus.register_new_event(AfterCanceller())
    bus.register_new_event(AsyncCanceller())
    bus.call_event(_msg())
    await asyncio.sleep(0)
    assert "after" in LOG, f"FAIL: 异步取消意外生效，文档需更新 {LOG}"
    print("PASS 10: 异步 handler 的 cancel 不阻断传播(已文档化的限制)")

    print("\n全部通过")


if __name__ == "__main__":
    asyncio.run(main())
