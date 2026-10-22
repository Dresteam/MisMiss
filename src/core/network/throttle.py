"""出站请求节流与全局退避。

面向猫耳平台的自我保护闸门。**所有**发往平台的请求都要先过 :func:`acquire`，
由此获得两个保证：

1. **速率上限** —— 全进程共享一个最小请求间隔，无论上层怎么调（启动惊群、
   插件高频调用、重试风暴）都不会在瞬时打出成百上千个请求。
2. **在途并发上限** —— 同时未完成的请求数有硬上限。**这一条才是防封 IP 的关键**：
   平台判定「请求过快」看的是瞬时并发，不是总次数。
3. **全局退避** —— 平台一旦明确表示限流，所有账户一起冷却。被限流时
   "继续按原速率猛打" 只会让封禁更久，宁可少发消息也要等窗口滑过去。

存在意义是兜底：分散在各处的单点修复（启动错峰、失败豁免、重连抖动）都可能
被将来新增的代码绕过，只有这里是一道绕不过去的闸。
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import Enum

from ..exceptions import CoreThrottledException
from ..logging import get_logger

_log = get_logger(__name__)

# 全进程默认最小请求间隔（秒）。0.1 ≈ 上限 10 req/s —— 对正常的场控负载
# 完全够用，同时把「一次性几百个请求」这种形态彻底挡住。
# 正式配置走 config.yml 的 ratelimit.min_interval；这里的环境变量是给测试与
# 临时排查用的旁路（测试里请求被打了桩，却仍要白等限速，会平白拖慢整个套件）。
_DEFAULT_MIN_INTERVAL = 0.1

# 同时在途请求数上限。**这是防封 IP 的那道闸，比速率更要紧。**
#
# 平台判定「请求过快」看的是**瞬时并发**，而不是一段时间里的总次数 ——
# 正常用了一个月没事、某一次放开一批并发就被封，就是这个道理。
#
# ⚠️ 只靠 min_interval 挡不住这件事：它拉开的是「出发时刻」，不限制在途数量。
# 32 个积压请求会被摊成每 0.1 秒出发一个，但它们**同时在途**，
# 平台看到的仍是 32 条并发连接。（退避解除时的惊群尤其明显。）
#
# 默认取 3：正常收发（请求耗时 0.2~0.5s、间隔 0.1s）的天然并发本来就在
# 2~5 之间，所以稳态不受影响，只是把突发削平。账户多、且确认平台容忍度更高
# 时可调大 —— 但**调大之前先想清楚你在拿 IP 换什么**。
_DEFAULT_MAX_CONCURRENCY = 3

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

# 平台被判定为在限流时，交互车道（发弹幕 / 送礼物）降到这个最小间隔继续放行。
#
# 为什么不是「一起停」：观众看得见的消息是产品本身，停 15 分钟等于直播间没人应声；
# 而这段时间里真正该被砍掉的是后台流量 —— 状态轮询陈旧五分钟没人会发现。
# 0.5 秒一条 ≈ 2 条/秒，比后台轮询的量小得多，不至于把平台继续激怒。
_LIMITED_INTERVAL = 0.5


class Lane(str, Enum):
    """出站流量类别。

    **分车道的理由**（线上踩过）：同一个熔断器管所有请求时，一个后台状态轮询
    失败 8 次就能让面向观众的欢迎语停发 15 分钟 —— 这两件事的风险等级完全不同，
    却共用一个失败计数和一个闸门。
    """

    #: 面向观众：发弹幕、送礼物/背包；还包含拿 Cookie 与 Bot 刷新 —— 它们不在
    #: 观众眼前，但断了整条链路就没了，属于关键路径。
    INTERACTIVE = "interactive"

    #: 后台：状态轮询、房间信息刷新、管理员名单。陈旧无所谓，平台一紧张就该整批停。
    BACKGROUND = "background"

# 两次「升档」之间的最短间隔（秒）。
#
# 一批并发请求会几乎同时失败，每个都调一次 note_failure —— 不去抖的话，
# 2.4 秒内就能把档位从 30 秒一路推到 900 秒上限。线上日志里就是这个形态：
#
#   03:48:23.619 | 连续失败 8 次，暂停 900 秒
#   03:48:24.272 | 连续失败 8 次，暂停 900 秒
#   03:48:25.073 | 连续失败 8 次，暂停 900 秒
#   03:48:25.805 | 连续失败 8 次，暂停 900 秒
#
# 同一批失败只该算**一次**。取 30 秒的含义是：真正的持续限流仍会按
# 30/60/120… 往上爬，只是不会再因为同一瞬间的几十个失败一次爬到底。
#
# ⚠️ **只对「连续失败 N 次」这条弱信号生效。** 平台明确报限流（429/418 等
# 命中特征）时不设冷却 —— 那是它真的在拒绝我们，越是被拒越该退得更深，
# 连升几级是刻意的（`test_outbound_pacing.py` 的「重复限流使退避升级」钉的就是它）。
# 线上那次 2.4 秒内四连升全是「连续失败」触发的，正是这条冷却要治的形态。
_ESCALATION_COOLDOWN = 30.0


class OutboundGate:
    """全进程共享的出站请求闸门。"""

    def __init__(self, name: str = "出站") -> None:
        self._name = name
        self._lock = asyncio.Lock()
        self._min_interval = _DEFAULT_MIN_INTERVAL
        # 下一次允许发出的时刻（monotonic）
        self._next_allowed = 0.0
        # 临时抬高的最小间隔下限（平台限流期间交互车道降速用，见 set_floor_interval）
        self._floor_interval = 0.0
        # 全局退避截止时刻（monotonic）
        self._backoff_until = 0.0
        # 连续失败计数与退避升级档位
        self._consecutive_failures = 0
        self._backoff_step = 0
        self._last_escalation_at = 0.0
        self._markers = _DEFAULT_RATE_LIMIT_MARKERS
        # 在途并发名额。信号量按事件循环惰性创建（见 _semaphore）
        self._max_concurrency = _DEFAULT_MAX_CONCURRENCY
        self._sem_obj: asyncio.Semaphore | None = None
        self._sem_loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ #
    # 配置
    # ------------------------------------------------------------------ #

    def configure(
        self,
        min_interval: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        """调整出站节流参数。``min_interval=0`` 表示不限速（仅供测试）。

        :param min_interval: 最小请求间隔（秒）
        :param max_concurrency: 同时在途请求数上限，至少 1
        """
        if min_interval is not None:
            self._min_interval = max(0.0, float(min_interval))
        if max_concurrency is not None:
            self._max_concurrency = max(1, int(max_concurrency))
            # 名额变了就丢掉旧的信号量，让它按新值重建
            self._sem_obj = None
            self._sem_loop = None

    @property
    def min_interval(self) -> float:
        return self._min_interval

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    def extend_markers(self, extra: tuple[str, ...]) -> None:
        """在默认限流特征之外追加特征（环境变量旁路用）。"""
        self._markers = _DEFAULT_RATE_LIMIT_MARKERS + extra

    def set_floor_interval(self, value: float | None) -> None:
        """临时抬高本车道的最小间隔下限。

        平台限流期间交互车道靠它**降速**而不是停摆 —— 拦住的是频率，不是消息。
        ``None`` 或 0 表示取消下限，回到 ``min_interval``。
        """
        self._floor_interval = max(0.0, float(value)) if value else 0.0

    @property
    def backoff_remaining(self) -> float:
        """当前全局退避还剩多少秒；0 表示没有退避。"""
        return max(0.0, self._backoff_until - time.monotonic())

    def reset(self) -> None:
        """清空全部状态（测试用）。"""
        self._next_allowed = 0.0
        self._floor_interval = 0.0
        self._backoff_until = 0.0
        self._consecutive_failures = 0
        self._backoff_step = 0
        self._last_escalation_at = 0.0
        self._min_interval = _DEFAULT_MIN_INTERVAL
        self._max_concurrency = _DEFAULT_MAX_CONCURRENCY
        self._sem_obj = None
        self._sem_loop = None

    # ------------------------------------------------------------------ #
    # 取号
    # ------------------------------------------------------------------ #

    async def acquire(self) -> None:
        """预约一个「出发时刻」；必要时在此等待。

        名额在锁内**预约**、在锁外 `sleep` —— 这样等待期间不持有锁，
        请求之间仍可并发在途，只是「出发时刻」被拉开了。

        ⚠️ **它只管速率，不管在途并发** —— 正是防封要治的那一项。
        真实请求请一律走 :meth:`slot`；直接用这个等于把并发上限绕过去了。
        """
        async with self._lock:
            interval = max(self._min_interval, self._floor_interval)
            start = max(time.monotonic(), self._next_allowed, self._backoff_until)
            self._next_allowed = start + interval
        wait = start - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

    def _semaphore(self) -> asyncio.Semaphore:
        """当前的并发信号量。

        惰性创建、并**按事件循环缓存**：信号量一旦用过就绑在那个循环上，
        换循环再用会抛错。测试与多循环场景下每个循环各拿一个，别互相牵连。
        """
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._sem_obj is None or self._sem_loop is not loop:
            self._sem_obj = asyncio.Semaphore(self._max_concurrency)
            self._sem_loop = loop
        return self._sem_obj

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """占用一个出站名额，**覆盖整段请求**（排队 + 在途）。

        真实请求一律走这个。进 with 就占住一个名额，离开才算这次请求结束 ——
        所以 ``_max_concurrency`` 约束的是**同时在途的请求数**，而不只是出发间隔。

        这一条专治「退避解除时的惊群」：一批积压的请求不会再一起冲出去，
        而是最多 N 个一起。

        .. code-block:: python

            async with gate.slot():
                resp = await client.get(url)
        """
        sem = self._semaphore()
        await sem.acquire()
        try:
            await self.acquire()
            yield
        finally:
            sem.release()

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
            _log.info("[{}] 平台请求恢复正常，已解除该车道退避", self._name)

    def note_failure(self, err: BaseException | None = None, context: str = "") -> None:
        """一次失败。命中限流特征或连续失败过多时进入/升级全局退避。

        :param err: 触发失败的异常；``None`` 表示只有失败事实（如网络层超时）
        :param context: 这次失败属于哪个请求（如 ``POST https://…``）。
            进退避时会连同 ``err`` 一起打进 WARNING —— 否则日志里只剩下
            「连续失败 8 次」这个**结论**，是谁失败的、错在哪一概查不到，
            线上排查时只能靠猜。
        """
        rate_limited = err is not None and self.is_rate_limit_error(err)
        self._consecutive_failures += 1

        if not (rate_limited or self._consecutive_failures >= _FAILURE_THRESHOLD):
            return

        now = time.monotonic()
        self._consecutive_failures = 0

        # 升档冷却**只作用于「连续失败」这条弱信号**（见 _ESCALATION_COOLDOWN）。
        #
        # 平台**明确**报限流（HTTP 429/418 等命中特征）时不设冷却：那是它真的在
        # 拒绝我们，越是被拒越该退得更深，连着多升几级是合理的 —— 原来那条
        # 「重复限流使退避升级」的断言就是钉这个行为的，别把它一起压掉。
        if rate_limited or now - self._last_escalation_at >= _ESCALATION_COOLDOWN:
            self._backoff_step = min(self._backoff_step + 1, 8)
            self._last_escalation_at = now

        penalty = min(_BACKOFF_BASE * (2 ** (self._backoff_step - 1)), _BACKOFF_MAX)
        self._backoff_until = now + penalty
        _log.warning(
            "[{}] {}，暂停该车道请求 {:.0f} 秒 | 触发: {} | 错误: {}",
            self._name,
            "平台报告限流" if rate_limited else f"连续失败 {_FAILURE_THRESHOLD} 次",
            penalty,
            context or "(未标注)",
            str(err)[:200] if err is not None else "无（超时 / 网络层失败）",
        )


class GateSet:
    """全进程出站闸门集合：按 :class:`Lane` 分成两条**互不牵连**的车道。

    分车道治的是「一个后台轮询把消息通道带崩」（线上踩过：511 次退避整夜不停，
    消息被压后 30 秒到 15 分钟）：

    1. **后台失败关不掉消息通道。** 两条车道各自记账、各自熔断。
    2. **平台明确报限流时先牺牲后台。** 那是整条 IP 被针对，后台请求直接
       **跳过**（抛 :class:`CoreThrottledException`，不排队、不重试），
       交互车道只降到 ``_LIMITED_INTERVAL`` 继续放行。
    3. **弱信号只影响自己。** 由「连续失败 N 次」触发的熔断只在本车道生效 ——
       超时说明我们自己有问题，说明不了平台想让我们慢下来。
    """

    def __init__(self) -> None:
        self._lanes: dict[Lane, OutboundGate] = {
            Lane.INTERACTIVE: OutboundGate("交互"),
            Lane.BACKGROUND: OutboundGate("后台"),
        }
        # 平台被判定为在限流的截止时刻（monotonic）。两条车道共享 ——
        # 平台针对的是 IP，不是某一类请求。
        self._platform_limited_until = 0.0
        self._limited_step = 0
        self._last_limited_escalation_at = 0.0

    def lane(self, lane: Lane) -> OutboundGate:
        """取某条车道（主要给测试用）。"""
        return self._lanes[lane]

    @property
    def platform_limited_remaining(self) -> float:
        """平台限流窗口还剩多少秒；0 表示没有。"""
        return max(0.0, self._platform_limited_until - time.monotonic())

    # ---- 闸门 ----

    @asynccontextmanager
    async def slot(self, lane: Lane = Lane.INTERACTIVE) -> AsyncIterator[None]:
        """占用一条车道的名额，覆盖整段请求。

        :raises CoreThrottledException: 平台正在限流，而这次是后台请求 ——
            该让路。**只有后台车道会抛**；交互车道只会降速，不会停。
        """
        if lane is Lane.BACKGROUND and self.platform_limited_remaining > 0:
            raise CoreThrottledException("平台限流中，后台请求让路")

        g = self._lanes[lane]
        if lane is Lane.INTERACTIVE:
            # 限流期间降速：拉长出发间隔，而不是拦在退避上
            g.set_floor_interval(
                _LIMITED_INTERVAL if self.platform_limited_remaining > 0 else None
            )

        async with g.slot():
            yield

    # ---- 反馈 ----

    def is_rate_limit_error(self, err: BaseException) -> bool:
        return self._lanes[Lane.INTERACTIVE].is_rate_limit_error(err)

    def note_success(self, lane: Lane = Lane.INTERACTIVE) -> None:
        """一次成功。顺带解除平台限流窗口 —— 能正常应答就说明平台消气了。"""
        self._lanes[lane].note_success()
        if self._platform_limited_until:
            self._platform_limited_until = 0.0
            self._limited_step = 0
            _log.info("平台请求恢复正常，后台车道恢复放行")

    def note_failure(
        self,
        err: BaseException | None = None,
        context: str = "",
        lane: Lane = Lane.INTERACTIVE,
    ) -> None:
        """一次失败。

        分两路走：

        - **平台明确报限流**（429/418/命中文案）→ 开全局限流窗口：后台让路、
          交互降速。这条路**刻意不走车道的硬退避** —— 硬退避会把消息一起冻住，
          而那正是这次改造要消灭的形态。
        - **其余失败** → 只记在它所属的车道里，攒够阈值熔断那一条车道。
          超时是我们自己的问题，说明不了平台想让我们慢下来。
        """
        g = self._lanes[lane]

        if err is not None and g.is_rate_limit_error(err):
            now = time.monotonic()
            # 与车道内一样去抖：同一批并发失败只算一次升档
            if now - self._last_limited_escalation_at >= _ESCALATION_COOLDOWN:
                self._limited_step = min(self._limited_step + 1, 8)
                self._last_limited_escalation_at = now
            penalty = min(_BACKOFF_BASE * (2 ** (self._limited_step - 1)), _BACKOFF_MAX)
            self._platform_limited_until = now + penalty
            _log.warning(
                "[全局限流] 平台报告限流，暂停后台请求、交互降速 {:.0f} 秒"
                " | 触发: {} | 错误: {}",
                penalty,
                context or "(未标注)",
                str(err)[:200],
            )
            return

        g.note_failure(err, context)

    # ---- 配置与状态 ----

    def configure(
        self,
        min_interval: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        for g in self._lanes.values():
            g.configure(min_interval, max_concurrency)

    def extend_markers(self, extra: tuple[str, ...]) -> None:
        """在两条车道上都追加限流特征。"""
        for g in self._lanes.values():
            g.extend_markers(extra)

    @property
    def min_interval(self) -> float:
        return self._lanes[Lane.INTERACTIVE].min_interval

    @property
    def max_concurrency(self) -> int:
        return self._lanes[Lane.INTERACTIVE].max_concurrency

    @property
    def backoff_remaining(self) -> float:
        return max(g.backoff_remaining for g in self._lanes.values())

    def reset(self) -> None:
        for g in self._lanes.values():
            g.reset()
        self._platform_limited_until = 0.0
        self._limited_step = 0
        self._last_limited_escalation_at = 0.0


# 全进程单例 —— 所有 HTTPClient / 端点共用
gate = GateSet()


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

    raw_conc = os.environ.get("MISMISS_RATE_LIMIT_MAX_CONCURRENCY", "").strip()
    if raw_conc:
        try:
            gate.configure(max_concurrency=int(raw_conc))
        except ValueError:
            pass

    raw = os.environ.get("MISMISS_RATE_LIMIT_MARKERS", "").strip()
    if raw:
        extra = tuple(m.strip() for m in raw.split(",") if m.strip())
        if extra:
            gate.extend_markers(extra)


configure_from_env()
