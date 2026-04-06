"""系统日志 API — 内存缓冲 + SSE 实时推流"""
import asyncio
import json
import logging
import time
from collections import deque
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

# ── 内存日志缓冲 ─────────────────────────────────────────────
_LOG_BUFFER: deque = deque(maxlen=2000)
_SSE_QUEUES: set = set()


class UILogHandler(logging.Handler):
    """拦截所有 Python 日志，写入内存缓冲并推送给 SSE 订阅者。"""

    LEVEL_MAP = {
        "DEBUG":    "debug",
        "INFO":     "info",
        "WARNING":  "warn",
        "ERROR":    "error",
        "CRITICAL": "error",
    }

    def emit(self, record: logging.LogRecord):
        try:
            entry = {
                "ts":    round(record.created, 3),
                "level": self.LEVEL_MAP.get(record.levelname, "info"),
                "name":  record.name,
                "msg":   self.format(record),
            }
            _LOG_BUFFER.append(entry)
            dead = set()
            for q in _SSE_QUEUES:
                try:
                    q.put_nowait(entry)
                except Exception:
                    dead.add(q)
            _SSE_QUEUES.difference_update(dead)
        except Exception:
            pass


def install_ui_handler(level: int = logging.DEBUG):
    """在应用启动时调用一次，安装到根 logger。"""
    handler = UILogHandler(level=level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger()
    # 避免重复安装
    if not any(isinstance(h, UILogHandler) for h in root.handlers):
        root.addHandler(handler)
    # 确保 root level 不过滤掉 DEBUG
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)


# ── REST 接口 ────────────────────────────────────────────────

@router.get("/logs")
async def get_logs(level: Optional[str] = None, limit: int = 500):
    """
    返回内存缓冲中的日志。
    level: debug | info | warn | error（不传则返回全部）
    limit: 最多返回最近 N 条
    """
    LEVELS = ["debug", "info", "warn", "error"]
    min_idx = LEVELS.index(level) if level in LEVELS else 0
    filtered = [
        e for e in _LOG_BUFFER
        if LEVELS.index(e["level"]) >= min_idx
    ]
    return {"logs": list(filtered)[-limit:], "total": len(filtered)}


# ── SSE 实时推流 ─────────────────────────────────────────────

@router.get("/logs/stream")
async def stream_logs(level: Optional[str] = None):
    """SSE：实时推送新产生的日志，按 level 过滤。"""
    LEVELS = ["debug", "info", "warn", "error"]
    min_idx = LEVELS.index(level) if level in LEVELS else 0

    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _SSE_QUEUES.add(q)

    async def generator():
        try:
            # 先推送缓冲中已有的最近 200 条
            recent = [e for e in _LOG_BUFFER if LEVELS.index(e["level"]) >= min_idx]
            for entry in list(recent)[-200:]:
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"

            # 实时推送新日志
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=25)
                    if LEVELS.index(entry["level"]) >= min_idx:
                        yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"ping\"}\n\n"
        finally:
            _SSE_QUEUES.discard(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
