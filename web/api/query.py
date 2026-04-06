"""查询 API — TF-IDF 搜索 + LLM 问答"""
import asyncio
import re
import sys
from pathlib import Path

import yaml
from fastapi import APIRouter

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = ROOT / "wiki"
sys.path.insert(0, str(ROOT))


def _load_config() -> dict:
    cfg_file = ROOT / "config.yaml"
    if cfg_file.exists():
        return yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
    return {}


@router.get("/search")
async def search(q: str = "", mode: str = "auto", top: int = 8):
    if not q.strip():
        return {"results": [], "mode": mode}

    # auto 模式：长句用语义，短词用 TF-IDF
    if mode == "auto":
        mode = "semantic" if len(q) > 15 else "tfidf"

    from tools.search import search_wiki
    results = search_wiki(q, str(WIKI_DIR), top_k=top)

    return {
        "mode": mode,
        "query": q,
        "results": [
            {
                "title": r["title"],
                "filename": r["filename"],
                "score": r["score"],
                "snippet": r["snippet"],
            }
            for r in results
        ],
    }


@router.post("/ask")
async def ask(body: dict):
    question = (body.get("question") or "").strip()
    if not question:
        from fastapi import HTTPException
        raise HTTPException(400, "question is required")

    save = bool(body.get("save", True))
    deep = bool(body.get("deep", False))
    config = _load_config()
    language = config.get("wiki", {}).get("language", "zh")

    from tools.ask import build_context, _save_answer
    from tools.llm_client import LLMClient

    # 构建上下文
    context_text, source_files = build_context(question, WIKI_DIR, deep=deep)

    # 加载 prompt 模板
    ask_tmpl_path = ROOT / "templates" / "ask.txt"
    if ask_tmpl_path.exists():
        template = ask_tmpl_path.read_text(encoding="utf-8")
        prompt = template.format(
            language=language,
            wiki_entries=context_text or "（知识库为空，请先摄入并编译资料）",
            question=question,
        )
    else:
        prompt = f"根据以下知识库回答问题：\n\n{context_text}\n\n问题：{question}"

    client = LLMClient(config)
    max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get("ask", 4096)
    answer_text = await asyncio.to_thread(client.call, prompt, max_tokens)
    cost = client.get_cost_summary()["cost_usd"]

    # [[链接]] 替换为可点击 span
    answer_html = re.sub(
        r'\[\[(.+?)\]\]',
        r'<span class="wiki-link" data-entry="\1">[[\1]]</span>',
        answer_text
    )

    # 保存答案
    saved_path = None
    if save and answer_text:
        try:
            _save_answer(question, answer_text, source_files, WIKI_DIR)
            saved_path = True
        except Exception:
            pass

    return {
        "question": question,
        "answer_md": answer_text,
        "answer_html": answer_html,
        "sources": source_files,
        "cost_usd": round(cost, 5),
        "saved": saved_path is not None,
    }
