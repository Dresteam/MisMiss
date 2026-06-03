"""事件系统演示。

展示事件继承、MRO 分发和事件总线的基本用法。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from abc import ABC
from dataclasses import dataclass

from interfaces.event import Event, Listener, event_handler
from core.events import EventBus


# ================================================================ #
# 事件类: A, B(继承A), C
# ================================================================ #

class A(Event, ABC):
    """顶层事件 A。"""

    @property
    def label(self) -> str:
        return "A"


@dataclass
class B(A):
    """事件 B — 继承 A，触发时会同时命中 B 和 A 两个处理器。"""

    _label: str = "B"

    @property
    def label(self) -> str:
        return self._label


@dataclass
class C(Event):
    """事件 C — 独立事件，仅命中自身处理器。"""

    _label: str = "C"

    @property
    def label(self) -> str:
        return self._label


# ================================================================ #
# 监听器
# ================================================================ #

class DemoListener(Listener):
    """演示监听器 — 分别监听 A、B、C 三种事件。"""

    @event_handler
    def on_a(self, event: A) -> None:
        print(f"  [A 处理器] 收到事件: label={event.label}, type={type(event).__name__}")

    @event_handler
    def on_b(self, event: B) -> None:
        print(f"  [B 处理器] 收到事件: label={event.label}, type={type(event).__name__}")

    @event_handler
    def on_c(self, event: C) -> None:
        print(f"  [C 处理器] 收到事件: label={event.label}, type={type(event).__name__}")


# ================================================================ #
# 主程序
# ================================================================ #

def main():
    print("事件继承关系: A(Event) <- B(A)    C(Event)")
    print("处理器注册:   on_a(A)  on_b(B)  on_c(C)")
    print()

    bus = EventBus()
    listener = DemoListener()
    bus.register_new_event(listener)

    print("触发 A: ")
    bus.call_event(A())
    print("触发 B: ")
    bus.call_event(B())
    print("触发 C: ")
    bus.call_event(C())


if __name__ == "__main__":
    main()
