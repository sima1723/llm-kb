"""配置 API — 读写 config.yaml，验证 API Key"""
import time
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = ROOT / "config.yaml"


def _load() -> dict:
    return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}


def _save(cfg: dict):
    CONFIG_FILE.write_text(yaml.dump(cfg, allow_unicode=True, default_flow_style=False), encoding="utf-8")


@router.get("/config")
async def get_config():
    cfg = _load()
    return {
        "api_key_set": bool((cfg.get("api_key") or "").strip()),
        "model": cfg.get("llm", {}).get("model", ""),
        "budget_limit": cfg.get("compile", {}).get("budget_limit_usd", 5.0),
        "language": cfg.get("wiki", {}).get("language", "zh"),
        "git_auto_commit": cfg.get("compile", {}).get("git_auto_commit", False),
        "base_url": cfg.get("base_url", ""),
    }


@router.post("/config")
async def set_config(body: dict):
    cfg = _load()
    if "api_key" in body:
        cfg["api_key"] = body["api_key"].strip()
    if "model" in body:
        cfg.setdefault("llm", {})["model"] = body["model"]
    if "budget_limit" in body:
        cfg.setdefault("compile", {})["budget_limit_usd"] = float(body["budget_limit"])
    if "git_auto_commit" in body:
        cfg.setdefault("compile", {})["git_auto_commit"] = bool(body["git_auto_commit"])
    if "base_url" in body:
        cfg["base_url"] = body["base_url"].strip()
    _save(cfg)
    return {"ok": True}


@router.post("/config/test")
async def test_config():
    """用一个极小的请求验证 API Key 是否可用"""
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.llm_client import LLMClient
    cfg = _load()
    if not (cfg.get("api_key") or "").strip():
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {"ok": False, "error": "API Key 未设置"}
    try:
        client = LLMClient(cfg)
        t0 = time.time()
        resp = client.call("Reply with just the word: OK", max_tokens=5)
        latency_ms = int((time.time() - t0) * 1000)
        return {"ok": True, "model": cfg.get("llm", {}).get("model", ""), "latency_ms": latency_ms}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
