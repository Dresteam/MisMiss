"""欢迎插件。

新用户进入直播间时自动发送随机欢迎消息。
支持拼音模式——在用户名上方附加拼音注音（基于 pypinyin 库）。

消息格式（拼音模式开启时）::

    ✐[shuì jué wéi dà]
    欢迎 @睡觉为大 来到直播间～
"""

from __future__ import annotations

import random

from pypinyin import pinyin, Style

from core.logging import get_logger
from interfaces.plugin import Plugin
from interfaces.event import event_handler
from interfaces.event.livestream import LiveJoinEvent

_log = get_logger(__name__)


def to_pinyin(text: str) -> str:
    """将中文字符串转为空格分隔的拼音（带声调）。

    :param text: 中文字符串
    :return: 拼音字符串，如 ``"shuì jué wéi dà"``
    """
    # 逐字转拼音（用户名多为非词典词组合，逐字更准确）
    result: list[str] = []
    for ch in text:
        if "一" <= ch <= "鿿":
            py = pinyin(ch, style=Style.TONE, heteronym=False)
            result.append(py[0][0] if py else ch)
        else:
            result.append(ch)
    return " ".join(result)


class WelcomePlugin(Plugin):
    """新用户进入直播间时自动发送随机欢迎消息，支持拼音模式。"""

    async def initialize(self) -> None:
        cfg = self.config or {}
        phrases = cfg.get("welcome_phrases", [])
        pinyin_on = cfg.get("pinyin_enabled", True)
        _log.info(
            "[WelcomePlugin] 就绪 (plugin_id={})  欢迎语={}条  拼音={}",
            self.plugin_id,
            len(phrases),
            "开启" if pinyin_on else "关闭",
        )

    @event_handler
    async def on_join(self, event: LiveJoinEvent) -> None:
        """用户进入直播间 → 发送欢迎消息。"""
        cfg = self.config or {}
        phrases: list[str] = cfg.get("welcome_phrases", [])
        if not phrases:
            return

        user_name = event.user.name
        phrase = random.choice(phrases).replace("{user}", user_name)

        pinyin_enabled = cfg.get("pinyin_enabled", True)
        if pinyin_enabled:
            py = to_pinyin(user_name)
            prefix = cfg.get("pinyin_prefix", "✐[拼音] ")
            message = f"{phrase}\n\n{prefix}[{py}]"
        else:
            message = phrase

        _log.info(
            "[WelcomePlugin] {} 进入 {}，已发送欢迎",
            user_name,
            event.livestream.room_name,
        )
        await event.livestream.send_message(message)
