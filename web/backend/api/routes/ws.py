"""日志系统 —— 环形缓冲区 + HTTP 历史查询 + WebSocket 实时推送。

架构:
    RingBuffer (10,000 条, 线程安全, 全局递增 seq_id)
        ├── GET  /api/logs/history?since=0&limit=50   历史查询
        ├── GET  /api/logs/gap?from=100&to=200         断线补发
        └── WS   /api/ws?last_seq=xxx                   实时推送 + 重连补发
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import re
from collections import deque
from typing import Any
from dataclasses import dataclass

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

    def get_since(self, since_seq: int, limit: int = 50) -> list[dict]:
        """获取 since_seq 之后的日志（不含 since_seq 本身）。"""
        with self._lock:
            result = [e for e in self._buffer if e.seq_id > since_seq]
            return [_entry_to_dict(e) for e in result[-limit:]]

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

_buffer = RingBuffer(capacity=10_000)


def get_buffer() -> RingBuffer:
    return _buffer


# ================================================================== #
# WebSocket 客户端管理
# ================================================================== #

_clients: dict[int, WebSocket] = {}
_client_id_seq = 0


async def _broadcast(entry: LogEntry) -> None:
    msg = {"type": "log", **_entry_to_dict(entry)}
    dead: list[int] = []
    for cid, ws in _clients.items():
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(cid)
    for cid in dead:
        _clients.pop(cid, None)


# ================================================================== #
# loguru & stdlib 集成
# ================================================================== #

try:
    from loguru import logger as _loguru_logger

    def _loguru_sink(message: str) -> None:
        record = message.record
        entry = _buffer.append(record["level"].name, str(record["message"]))
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_broadcast(entry), loop)
        except RuntimeError:
            pass

    _loguru_logger.add(_loguru_sink, level="DEBUG")
except ImportError:
    pass

import logging

class _WSLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        entry = _buffer.append(record.levelname, self.format(record))
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_broadcast(entry), loop)
        except RuntimeError:
            pass

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
    limit: int = Query(default=50, le=200),
):
    """拉取 since_seq 之后的历史日志。"""
    entries = _buffer.get_since(since, limit)
    return {
        "entries": entries,
        "latest_seq": _buffer.latest_seq,
        "oldest_seq": _buffer.oldest_seq,
        "has_more": len(entries) > 0 and entries[0]["seq_id"] > _buffer.oldest_seq,
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

    # 解析客户端携带的 last_seq
    last_seq = 0
    if ws.query_params:
        try:
            last_seq = int(ws.query_params.get("last_seq", "0"))
        except ValueError:
            last_seq = 0

    # 断线补发
    if last_seq > 0:
        gap = _buffer.get_since(last_seq, limit=500)
        for entry in gap:
            try:
                await ws.send_json({"type": "log", **entry})
            except Exception:
                break

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
