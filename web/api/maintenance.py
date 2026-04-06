"""维护 API — Stub 列表 + 填充"""
import asyncio
import json
import sys
from pathlib import Path

import yaml
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = ROOT / "wiki"
sys.path.insert(0, str(ROOT))

# 全局填充状态
_fill_state: dict = {"running": False, "log": [], "done": False}


def _load_config() -> dict:
    cfg_file = ROOT / "config.yaml"
    if cfg_file.exists():
        return yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
    return {}


@router.get("/stub/list")
async def list_stubs():
    """列出所有 stub 条目（tags 含 stub 或内容含"待补充"）"""
    stubs = []
    for md_file in sorted(WIKI_DIR.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        is_stub = False
        fm_end = text.find("---", 3)
        if text.startswith("---") and fm_end > 0:
            fm = text[3:fm_end]
            if "stub" in fm:
                is_stub = True
        if not is_stub and "待补充" in text[:500]:
            is_stub = True
        if is_stub:
            stubs.append({
                "name": md_file.stem,
                "filename": md_file.name,
                "size": md_file.stat().st_size,
            })
    return {"stubs": stubs, "count": len(stubs)}


@router.post("/stub/fill")
async def fill_stubs(body: dict):
    """异步触发 stub 填充（返回 202，进度通过 /stub/stream SSE 获取）"""
    global _fill_state
    if _fill_state.get("running"):
        return {"ok": False, "message": "already running"}

    entry = (body.get("entry") or "").strip() or None
    _fill_state = {"running": True, "log": [], "done": False, "entry": entry}

    asyncio.get_running_loop().run_in_executor(None, _run_fill, entry)
    return {"ok": True, "message": "stub fill started"}


def _run_fill(entry=None):
    global _fill_state
    try:
        import subprocess
        cmd = [sys.executable, str(ROOT / "tools" / "stub_fill.py")]
        if entry:
            cmd += ["--entry", entry]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(ROOT),
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _fill_state["log"].append(line)
        proc.wait()
    except Exception as e:
        _fill_state["log"].append(f"✗ 错误: {e}")
    finally:
        _fill_state["running"] = False
        _fill_state["done"] = True


@router.get("/stub/stream")
async def stream_fill():
    """SSE 推送 stub 填充进度（只跟踪当前正在运行的任务）"""
    # 快照启动时刻的状态标识，避免交付上一次运行的 done 信号
    start_running = _fill_state.get("running", False)
    start_done = _fill_state.get("done", False)

    async def generator():
        # 如果当前没有任务在跑（且已完成），直接返回空流
        if start_done and not start_running:
            yield f"data: {json.dumps({'type': 'idle'})}\n\n"
            return

        sent = 0
        while True:
            logs = _fill_state.get("log", [])
            while sent < len(logs):
                line = logs[sent]
                sent += 1
                yield f"data: {json.dumps({'type': 'log', 'line': line})}\n\n"
            if _fill_state.get("done") and sent >= len(_fill_state.get("log", [])):
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/stub/status")
async def stub_status():
    return {
        "running": _fill_state.get("running", False),
        "done": _fill_state.get("done", False),
        "log_lines": len(_fill_state.get("log", [])),
    }
