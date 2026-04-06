"""编译 API — 后台运行 compile_wiki.py，SSE 推送进度"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent

# 全局编译状态（单实例，MVP 够用）
_compile_state = {
    "running": False,
    "last_run": None,       # ISO timestamp
    "last_success": 0,
    "last_failed": 0,
    "last_cost_usd": 0.0,
    "log": [],              # 最近日志行
}


@router.get("/compile/status")
async def compile_status():
    import json as _json
    state_file = ROOT / ".state" / "processed_files.json"
    processed_count = 0
    if state_file.exists():
        try:
            processed_count = len(_json.loads(state_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    # 统计待编译
    pending = 0
    processed_keys: set = set()
    if state_file.exists():
        try:
            processed_keys = set(_json.loads(state_file.read_text(encoding="utf-8")).keys())
        except Exception:
            pass
    for md_file in (ROOT / "raw").rglob("*.md"):
        rel = str(md_file.relative_to(ROOT))
        if rel not in processed_keys:
            pending += 1

    # 读取累计花费
    cost_total = 0.0
    checkpoint_file = ROOT / ".state" / "checkpoints.json"
    if checkpoint_file.exists():
        try:
            ckpt = _json.loads(checkpoint_file.read_text(encoding="utf-8"))
            if isinstance(ckpt, dict):
                last = ckpt.get("last_compile", {})
                cost_total = last.get("cost_usd", 0.0)
        except Exception:
            pass

    return {
        **_compile_state,
        "files_pending": pending,
        "cost_total_usd": cost_total,
    }


@router.post("/compile")
async def start_compile(body: dict = {}):
    if _compile_state["running"]:
        return {"ok": False, "reason": "already running"}
    mode = body.get("mode", "incremental")
    # 先设 running=True，防止 SSE 在 task 启动前就看到 running=False 发出 done
    _compile_state["running"] = True
    _compile_state["log"] = []
    asyncio.create_task(_run_compile(full=(mode == "full")))
    return {"ok": True, "mode": mode}


async def _run_compile(full: bool = False):
    # running already set to True in start_compile
    try:
        cmd = [sys.executable, str(ROOT / "tools" / "compile_wiki.py")]
        if full:
            cmd.append("--full")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
        )
        async for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").rstrip()
            _compile_state["log"].append(text)
            if len(_compile_state["log"]) > 200:
                _compile_state["log"] = _compile_state["log"][-200:]
        await proc.wait()
        _compile_state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    finally:
        _compile_state["running"] = False


async def _sse_generator() -> AsyncGenerator[str, None]:
    """SSE 流：每 0.5 秒推送最新日志行"""
    last_idx = 0
    sent_done = False

    while True:
        log = _compile_state["log"]
        if len(log) > last_idx:
            for line in log[last_idx:]:
                data = json.dumps({"type": "log", "line": line})
                yield f"data: {data}\n\n"
            last_idx = len(log)

        if not _compile_state["running"] and not sent_done:
            data = json.dumps({
                "type": "done",
                "last_run": _compile_state["last_run"],
            })
            yield f"data: {data}\n\n"
            sent_done = True
            break

        await asyncio.sleep(0.5)


@router.get("/compile/stream")
async def compile_stream():
    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
