"""日志系统 —— 环形缓冲区 + HTTP 历史查询 + WebSocket 实时推送。

架构:
    RingBuffer (10,000 条, 线程安全, 全局递增 seq_id)
        ├── GET  /api/logs/history?since=0&limit=50   历史查询
        ├── GET  /api/logs/gap?from=100&to=200         断线补发
        └── WS   /api/ws?last_seq=xxx                   实时推送 + 重连补发
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()

# ================================================================== #
# ANSI 清理
# ================================================================== #

_ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


# ================================================================== #
# 日志条目
# ================================================================== #

@dataclass
class LogEntry:
    seq_id: int
    timestamp: float
    level: str
    message: str


# ================================================================== #
# RingBuffer —— 线程安全环形缓冲区
# ================================================================== #

class RingBuffer:
    """固定容量环形缓冲区，全局递增 seq_id，线程安全。"""

    def __init__(self, capacity: int = 10_000) -> None:
        self._capacity = capacity
        self._buffer: deque[LogEntry] = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()

    def append(self, level: str, message: str) -> LogEntry:
        with self._lock:
            self._seq += 1
            entry = LogEntry(
                seq_id=self._seq,
                timestamp=time.time(),
                level=level,
                message=_strip_ansi(str(message)),
            )
            self._buffer.append(entry)
            return entry

    def get_since(
        self, since_seq: int, limit: int = 50, levels: set[str] | None = None
    ) -> tuple[list[dict], bool, int]:
        """获取 since_seq **之前** 的日志（用于向上翻页加载更早历史）。

        返回 limit 条 seq_id <= since_seq 的最新日志，按 seq_id 升序排列。
        首次加载传入 0 则返回最新 limit 条。
        传入 ``levels`` 时仅返回指定级别的日志（源头过滤）。

        :return: ``(entries, has_more, filtered_total)``
        """
        with self._lock:
            all_entries = list(self._buffer)
            if levels:
                all_entries = [e for e in all_entries if e.level in levels]
            if since_seq <= 0:
                # 首次加载：返回最新 limit 条
                result = all_entries[-limit:]
            else:
                # 向上翻页：返回 seq_id < since_seq 的最近 limit 条
                older = [e for e in all_entries if e.seq_id < since_seq]
                result = older[-limit:]
            has_more = (
                bool(result) and bool(all_entries)
                and result[0].seq_id > all_entries[0].seq_id
            )
            return (
                [_entry_to_dict(e) for e in result],
                has_more,
                len(all_entries),
            )

    def get_range(self, from_seq: int, to_seq: int) -> list[dict] | None:
        """获取 [from_seq, to_seq] 范围内的日志。若数据已被淘汰返回 None。"""
        with self._lock:
            if not self._buffer:
                return []
            oldest = self._buffer[0].seq_id
            if from_seq < oldest:
                return None  # 数据已淘汰
            result = [e for e in self._buffer if from_seq <= e.seq_id <= to_seq]
            return [_entry_to_dict(e) for e in result]

    @property
    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    @property
    def oldest_seq(self) -> int:
        with self._lock:
            return self._buffer[0].seq_id if self._buffer else 0

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def stats(self) -> dict:
        with self._lock:
            return {
                "capacity": self._capacity,
                "count": len(self._buffer),
                "latest_seq": self._seq,
                "oldest_seq": self._buffer[0].seq_id if self._buffer else 0,
            }


def _entry_to_dict(e: LogEntry) -> dict:
    return {
        "seq_id": e.seq_id,
        "timestamp": e.timestamp,
        "level": e.level,
        "message": e.message,
    }


# ------------------------------------------------------------------ #
# 全局 RingBuffer 实例
# ------------------------------------------------------------------ #

_buffer = RingBuffer(capacity=2_000)


def get_buffer() -> RingBuffer:
    return _buffer


# ================================================================== #
# WebSocket 客户端管理
# ================================================================== #

_clients: dict[int, WebSocket] = {}
_client_levels: dict[int, set[str] | None] = {}  # 客户端源头级别过滤（None=全部）
_client_id_seq = 0


async def _broadcast_entries(entries: list[dict]) -> None:
    """批量广播日志条目（每 200ms 合并一次），按客户端级别过滤。"""
    dead: list[int] = []
    for cid, ws in _clients.items():
        try:
            levels = _client_levels.get(cid)
            payload = (
                entries if levels is None
                else [e for e in entries if e["level"] in levels]
            )
            if not payload:
                continue
            await ws.send_json({"type": "logs", "entries": payload})
        except Exception:
            dead.append(cid)
    for cid in dead:
        _clients.pop(cid, None)
        _client_levels.pop(cid, None)


# ================================================================== #
# loguru & stdlib 集成
# ================================================================== #

_WS_SINK_ID: int | None = None

# ------------------------------------------------------------------ #
# 批量推送：日志先入待发队列，由事件循环内的 flush 任务每 200ms
# 合并广播一次（大幅减少 WebSocket 帧数；同时保证线程安全）
# ------------------------------------------------------------------ #

_BATCH_INTERVAL: float = 0.2
_pending: list[LogEntry] = []
_pending_lock = threading.Lock()
_flush_task: asyncio.Task | None = None


def _enqueue(entry: LogEntry) -> None:
    """将日志条目加入待发队列（任意线程可调用）。"""
    with _pending_lock:
        _pending.append(entry)


async def _flush_loop() -> None:
    """待发队列消费任务——每 200ms 合并广播一批。

    无客户端且队列清空时自动退出，下次客户端连接时重新启动。
    """
    global _pending, _flush_task
    try:
        while True:
            await asyncio.sleep(_BATCH_INTERVAL)
            with _pending_lock:
                if not _pending:
                    if not _clients:
                        break
                    continue
                batch = _pending
                _pending = []
            await _broadcast_entries([_entry_to_dict(e) for e in batch])
    finally:
        _flush_task = None


def _ensure_flush_task() -> None:
    """确保批量推送任务运行（仅在事件循环内调用）。"""
    global _flush_task
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_flush_loop())


try:
    from loguru import logger as _loguru_logger

    def _loguru_sink(message: str) -> None:
        record = message.record
        _enqueue(_buffer.append(record["level"].name, str(record["message"])))

    # 从 config.yml 读取持久化的日志等级
    _initial_level = "DEBUG"
    try:
        import yaml as _y
        _cfg_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "config.yml"
        if _cfg_path.exists():
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                _cfg = _y.safe_load(_f) or {}
            _initial_level = _cfg.get("logging", {}).get("level", "DEBUG")
    except Exception:
        pass

    _WS_SINK_ID = _loguru_logger.add(_loguru_sink, level=_initial_level)
except ImportError:
    pass


def set_ws_log_level(level_name: str) -> None:
    """动态修改 WebSocket sink 的日志等级。"""
    global _WS_SINK_ID
    if _WS_SINK_ID is None:
        return
    try:
        from loguru import logger as _loguru_logger
        level_no = {"DEBUG": 10, "INFO": 20, "SUCCESS": 25, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        if level_name in level_no:
            _loguru_logger._core.handlers[_WS_SINK_ID]._levelno = level_no[level_name]
    except Exception:
        pass


class _WSLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _enqueue(_buffer.append(record.levelname, self.format(record)))

_std_handler = _WSLogHandler()
_std_handler.setLevel(logging.DEBUG)
_std_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%H:%M:%S"
))
logging.getLogger().addHandler(_std_handler)


# ================================================================== #
# HTTP API —— 历史日志
# ================================================================== #

@router.get("/logs/history")
async def logs_history(
    since: int = Query(default=0, description="起始 seq_id（不包含）"),
    limit: int = Query(default=50, le=500),
    levels: str | None = Query(default=None, description="逗号分隔的级别过滤，如 DEBUG,ERROR"),
):
    """拉取 since_seq 之后的历史日志（支持源头级别过滤）。"""
    level_set = None
    if levels:
        level_set = {lv.strip().upper() for lv in levels.split(",") if lv.strip()}
    entries, has_more, total = _buffer.get_since(since, limit, levels=level_set)
    return {
        "entries": entries,
        "latest_seq": _buffer.latest_seq,
        "oldest_seq": _buffer.oldest_seq,
        "total": total,
        "has_more": has_more,
    }


@router.get("/logs/gap")
async def logs_gap(
    from_seq: int = Query(...),
    to_seq: int = Query(...),
):
    """断线重连时补发 [from_seq, to_seq] 范围日志。"""
    entries = _buffer.get_range(from_seq, to_seq)
    if entries is None:
        return {"status": "expired", "message": "请求的日志已被淘汰，请使用 /logs/history"}
    return {"status": "ok", "entries": entries}


@router.get("/logs/stats")
async def logs_stats():
    return _buffer.stats()


# ================================================================== #
# WebSocket —— 实时推送 + 断线补发
# ================================================================== #

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _client_id_seq

    await ws.accept()
    _client_id_seq += 1
    cid = _client_id_seq
    _clients[cid] = ws

    # 解析客户端携带的 last_seq 与级别过滤
    last_seq = 0
    level_set: set[str] | None = None
    if ws.query_params:
        try:
            last_seq = int(ws.query_params.get("last_seq", "0"))
        except ValueError:
            last_seq = 0
        levels_str = ws.query_params.get("levels", "")
        if levels_str:
            level_set = {lv.strip().upper() for lv in levels_str.split(",") if lv.strip()}
    _client_levels[cid] = level_set

    # 启动批量推送任务（若尚未运行）
    _ensure_flush_task()

    # 断线补发（按级别过滤，批量单帧）
    if last_seq > 0:
        gap, _, _ = _buffer.get_since(last_seq, limit=500, levels=level_set)
        if gap:
            try:
                await ws.send_json({"type": "logs", "entries": gap})
            except Exception:
                pass

    # 确认连接
    await ws.send_json({
        "type": "status",
        "level": "INFO",
        "message": "已连接",
        "seq_id": _buffer.latest_seq,
        "timestamp": time.time(),
    })

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=15.0)
                if data == "ping":
                    await ws.send_json({
                        "type": "status", "level": "DEBUG",
                        "message": "pong", "timestamp": time.time(),
                    })
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({
                        "type": "status", "level": "DEBUG",
                        "message": "ping", "timestamp": time.time(),
                    })
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _clients.pop(cid, None)
        _client_levels.pop(cid, None)
