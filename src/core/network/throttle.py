"""出站请求节流与全局退避。

面向猫耳平台的自我保护闸门。**所有**发往平台的请求都要先过 :func:`acquire`，
由此获得两个保证：

1. **速率上限** —— 全进程共享一个最小请求间隔，无论上层怎么调（启动惊群、
   插件高频调用、重试风暴）都不会在瞬时打出成百上千个请求。
2. **全局退避** —— 平台一旦明确表示限流，所有账户一起冷却。被限流时
   "继续按原速率猛打" 只会让封禁更久，宁可少发消息也要等窗口滑过去。

存在意义是兜底：分散在各处的单点修复（启动错峰、失败豁免、重连抖动）都可能
被将来新增的代码绕过，只有这里是一道绕不过去的闸。
"""

from __future__ import annotations

import asyncio
import os
import time

from ..logging import get_logger

_log = get_logger(__name__)

# 全进程默认最小请求间隔（秒）。0.1 ≈ 上限 10 req/s —— 对正常的场控负载
# 完全够用，同时把「一次性几百个请求」这种形态彻底挡住。
# 正式配置走 config.yml 的 ratelimit.min_interval；这里的环境变量是给测试与
# 临时排查用的旁路（测试里请求被打了桩，却仍要白等限速，会平白拖慢整个套件）。
_DEFAULT_MIN_INTERVAL = 0.1

# 判定为「平台在限流」的错误特征。命中即触发全局退避。
# 用户若从日志里确认到猫耳专用的限流错误码，加到这里即可（用 MISMISS_RATE_LIMIT_MARKERS
# 环境变量可以不改代码临时追加，逗号分隔）。
_DEFAULT_RATE_LIMIT_MARKERS: tuple[str, ...] = (
    # 猫耳实际返回的风控响应（2026-09-30 从线上服务器日志确认）：
    #   HTTP 418: {"code":100010017,"success":false,
    #              "info":"https://www.missevan.com/standalone/403/403.html"}
    # 418 是「I'm a teapot」，被拿来当反爬标记用 —— 盯状态码比盯文案可靠。
    "418",
    "100010017",
    # 通用兜底
    "429",
    "too many requests",
    "rate limit",
    "限流",
    "频率",
    "操作频繁",
    "请求过快",
)

# 连续失败多少次后开始保守退避（无法识别限流错误码时的兜底）
_FAILURE_THRESHOLD = 8

# 全局退避的初始时长与上限（秒）
_BACKOFF_BASE = 30.0
_BACKOFF_MAX = 900.0


class OutboundGate:
    """全进程共享的出站请求闸门。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._min_interval = _DEFAULT_MIN_INTERVAL
        # 下一次允许发出的时刻（monotonic）
        self._next_allowed = 0.0
        # 全局退避截止时刻（monotonic）
        self._backoff_until = 0.0
        # 连续失败计数与退避升级档位
        self._consecutive_failures = 0
        self._backoff_step = 0
        self._markers = _DEFAULT_RATE_LIMIT_MARKERS

    # ------------------------------------------------------------------ #
    # 配置
    # ------------------------------------------------------------------ #

    def configure(self, min_interval: float | None = None) -> None:
        """调整最小请求间隔（秒）。0 表示不限速（仅供测试）。"""
        if min_interval is None:
            return
        self._min_interval = max(0.0, float(min_interval))

    @property
    def min_interval(self) -> float:
        return self._min_interval

    @property
    def backoff_remaining(self) -> float:
        """当前全局退避还剩多少秒；0 表示没有退避。"""
        return max(0.0, self._backoff_until - time.monotonic())

    def reset(self) -> None:
        """清空全部状态（测试用）。"""
        self._next_allowed = 0.0
        self._backoff_until = 0.0
        self._consecutive_failures = 0
        self._backoff_step = 0
        self._min_interval = _DEFAULT_MIN_INTERVAL

    # ------------------------------------------------------------------ #
    # 取号
    # ------------------------------------------------------------------ #

    async def acquire(self) -> None:
        """占用一个发送名额；必要时在此等待。

        名额在锁内**预约**、在锁外 `sleep` —— 这样等待期间不持有锁，
        请求之间仍可并发在途，只是「出发时刻」被拉开了。
        """
        async with self._lock:
            start = max(time.monotonic(), self._next_allowed, self._backoff_until)
            self._next_allowed = start + self._min_interval
        wait = start - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

    # ------------------------------------------------------------------ #
    # 反馈
    # ------------------------------------------------------------------ #

    def is_rate_limit_error(self, err: BaseException) -> bool:
        """该异常是否表示平台在限流。"""
        status_code = getattr(err, "status_code", None)
        if status_code == 429:
            return True
        text = str(err).lower()
        return any(m.lower() in text for m in self._markers)

    def note_success(self) -> None:
        """一次成功 —— 计数清零并逐步解除退避。"""
        self._consecutive_failures = 0
        if self._backoff_until:
            self._backoff_until = 0.0
            self._backoff_step = 0
            _log.info("平台请求恢复正常，已解除全局退避")

    def note_failure(self, err: BaseException | None = None) -> None:
        """一次失败。命中限流特征或连续失败过多时进入/升级全局退避。"""
        rate_limited = err is not None and self.is_rate_limit_error(err)
        self._consecutive_failures += 1

        if rate_limited or self._consecutive_failures >= _FAILURE_THRESHOLD:
            self._backoff_step = min(self._backoff_step + 1, 8)
            penalty = min(_BACKOFF_BASE * (2 ** (self._backoff_step - 1)), _BACKOFF_MAX)
            self._backoff_until = time.monotonic() + penalty
            self._consecutive_failures = 0
            _log.warning(
                "{}，暂停所有平台请求 {:.0f} 秒",
                "平台报告限流" if rate_limited else f"连续失败 {_FAILURE_THRESHOLD} 次",
                penalty,
            )


# 全进程单例 —— 所有 HTTPClient / 端点共用
gate = OutboundGate()


def configure_from_env() -> None:
    """按环境变量调整（供测试与临时排查使用）。"""
    global _DEFAULT_MIN_INTERVAL

    raw_interval = os.environ.get("MISMISS_RATE_LIMIT_MIN_INTERVAL", "").strip()
    if raw_interval:
        try:
            _DEFAULT_MIN_INTERVAL = max(0.0, float(raw_interval))
            gate.configure(_DEFAULT_MIN_INTERVAL)
        except ValueError:
            pass

    raw = os.environ.get("MISMISS_RATE_LIMIT_MARKERS", "").strip()
    if raw:
        extra = tuple(m.strip() for m in raw.split(",") if m.strip())
        if extra:
            gate._markers = _DEFAULT_RATE_LIMIT_MARKERS + extra


configure_from_env()
