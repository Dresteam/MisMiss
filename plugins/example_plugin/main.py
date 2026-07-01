"""示例插件。

演示插件系统的完整功能：
- 事件监听（开播/下播/消息/礼物/用户进入）
- 配置管理（``_conf_schema.json`` → config 注入）
- 权限配置（``_permission.json`` → permission_config）
- 数据目录（``self.data_dir`` 专属存储空间）
"""

from __future__ import annotations

import json
import os

from core.logging import get_logger
from interfaces.plugin import Plugin
from interfaces.event import event_handler
from interfaces.event.livestream import (
    LiveMessageEvent,
    LiveGiftEvent,
    LiveOpenEvent,
    LiveCloseEvent,
    LiveJoinEvent,
)

_log = get_logger(__name__)

# ------------------------------------------------------------------ #
# 常量
# ------------------------------------------------------------------ #

_STATS_FILE = "stats.json"
"""统计数据文件名，存储在插件数据目录下。"""


class ExamplePlugin(Plugin):
    """示例插件 —— 监听多种直播间事件，演示 config / permission / data_dir 用法。

    配置项（来自 ``_conf_schema.json``）：
        - ``greeting_enabled`` — 是否输出初始化问候
        - ``max_message_length`` — 弹幕截断长度
        - ``gift_threshold`` — 礼物价值过滤阈值
        - ``allowed_rooms`` — 允许监听的直播间 ID 列表

    权限项（来自 ``_permission.json``）：
        - ``admin_only`` — 是否仅管理员可用
        - ``max_daily_messages`` — 每日消息上限
    """

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    async def initialize(self) -> None:
        """插件初始化 —— 演示 config 读取和 data_dir 写入。"""
        cfg = self.config or {}

        # -- 使用配置 --
        if cfg.get("greeting_enabled", True):
            _log.info(
                "[ExamplePlugin] 你好！插件 v{} 已就绪 (plugin_id={})",
                "1.1.0",
                self.plugin_id,
            )
        else:
            _log.info("[ExamplePlugin] 插件已加载（问候语已关闭）")

        _log.info("[ExamplePlugin] 配置: {}", json.dumps(cfg, ensure_ascii=False))
        _log.info("[ExamplePlugin] 数据目录: {}", self.data_dir)

        # -- 使用数据目录保存状态 --
        self._load_stats()

    async def terminate(self) -> None:
        """插件终止 —— 保存统计到数据目录。"""
        self._save_stats()
        _log.info(
            "[ExamplePlugin] 已终止。统计数据已保存到 {}",
            os.path.join(self.data_dir, _STATS_FILE),
        )

    # ------------------------------------------------------------------ #
    # 事件处理器
    # ------------------------------------------------------------------ #

    @event_handler
    def on_open(self, event: LiveOpenEvent) -> None:
        room = event.livestream.room_name
        if not self._is_room_allowed(event.livestream.live_id):
            return
        _log.info("[ExamplePlugin] [OPEN] 直播间 {} 开播了！", room)
        self._stats["opens"] += 1

    @event_handler
    def on_close(self, event: LiveCloseEvent) -> None:
        room = event.livestream.room_name
        if not self._is_room_allowed(event.livestream.live_id):
            return
        _log.info("[ExamplePlugin] [CLOSE] 直播间 {} 下播了。", room)
        self._stats["closes"] += 1

    @event_handler
    def on_message(self, event: LiveMessageEvent) -> None:
        if not self._is_room_allowed(event.livestream.live_id):
            return

        cfg = self.config or {}
        max_len = cfg.get("max_message_length", 500)
        msg = event.message
        if len(msg) > max_len:
            msg = msg[:max_len] + "..."

        _log.info(
            "[ExamplePlugin] [MSG] [{}] {}: {}",
            event.livestream.room_name,
            event.user.name,
            msg,
        )
        self._stats["messages"] += 1

    @event_handler
    def on_gift(self, event: LiveGiftEvent) -> None:
        if not self._is_room_allowed(event.livestream.live_id):
            return

        gift = event.gift
        total_value = gift.price * gift.num
        cfg = self.config or {}
        threshold = cfg.get("gift_threshold", 100.0)

        if total_value < threshold:
            _log.debug(
                "[ExamplePlugin] 礼物价值 {} 低于阈值 {}，跳过",
                total_value,
                threshold,
            )
            return

        _log.info(
            "[ExamplePlugin] [GIFT] {} 赠送了 {} 个 {} (价值 {} 电池)",
            event.user.name,
            gift.num,
            gift.name,
            total_value,
        )
        self._stats["gifts"] += 1

    @event_handler
    def on_join(self, event: LiveJoinEvent) -> None:
        if not self._is_room_allowed(event.livestream.live_id):
            return
        _log.info("[ExamplePlugin] [JOIN] {} 进入了直播间", event.user.name)
        self._stats["joins"] += 1

    # ------------------------------------------------------------------ #
    # 内部：房间过滤 & 统计
    # ------------------------------------------------------------------ #

    def _is_room_allowed(self, live_id: int) -> bool:
        """检查直播间是否在允许列表中。"""
        cfg = self.config or {}
        allowed: list[int] = cfg.get("allowed_rooms", [])
        if not allowed:
            return True  # 空列表 = 全部允许
        return live_id in allowed

    def _load_stats(self) -> None:
        """从数据目录加载统计数据。"""
        path = os.path.join(self.data_dir, _STATS_FILE)
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._stats: dict[str, int] = json.load(f)
            _log.debug("[ExamplePlugin] 统计数据已加载: {}", self._stats)
        except (FileNotFoundError, json.JSONDecodeError):
            self._stats = {"messages": 0, "gifts": 0, "opens": 0, "closes": 0, "joins": 0}

    def _save_stats(self) -> None:
        """保存统计数据到数据目录。"""
        path = os.path.join(self.data_dir, _STATS_FILE)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except OSError as e:
            _log.warning("[ExamplePlugin] 保存统计数据失败: {}", e)
