"""跨房事件基类接口。

连麦 / 大厅场景下，**来自或发往对方直播间**的事件基类
（:class:`LiveCrossMessageEvent` / :class:`LiveCrossGiftEvent`）。

它刻意只是**分发分组标记**，不额外声明抽象成员。「对方直播间」四件套在两个子事件里
方向相反、字段名也不同（弹幕是 ``origin_*`` —— 对方是来源；礼物是 ``target_*`` ——
对方是去向），在这里统一命名只会与子类已有的语义字段重复。需要读取方向性字段时，
在 handler 内按具体类型分支即可。

**它与本房事件不构成继承关系**（子类不是 :class:`LiveMessageEvent` /
:class:`LiveGiftEvent` 的子类），因此监听本房弹幕或礼物的插件不会被跨房事件触达——
这是分组标记能安全存在的前提。
"""

from __future__ import annotations

from abc import ABC

from .livestream_user_event import LivestreamUserEvent


class LiveCrossEvent(LivestreamUserEvent, ABC):
    """跨房事件基类（连麦 / 大厅）。

    用于「连麦互动」这类需要收下**全部跨房事件**的插件：注册一个 handler 即可，
    且不会把本房弹幕或本房礼物漏进来。

    用法::

        from interfaces.event.livestream import LiveCrossEvent, LiveCrossGiftEvent

        class MyPlugin(Plugin):
            @event_handler
            def on_cross(self, event: LiveCrossEvent) -> None:
                # 「对方直播间」字段名按方向区分，故在此按类型分支
                if isinstance(event, LiveCrossGiftEvent):
                    print(f"{event.user.name} 送给 {event.target_creator_name} "
                          f"一个 {event.gift.name}")
                else:
                    print(f"[跨房] {event.user.name}: {event.message}")

    .. versionadded:: 1.3
    """
