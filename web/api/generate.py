"""生成 API — Slides + Report"""
import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = ROOT / "wiki"
sys.path.insert(0, str(ROOT))


@router.post("/generate")
async def generate(body: dict):
    topic = (body.get("topic") or "").strip()
    fmt = (body.get("format") or "report").strip()  # "slides" | "report" | "brief"
    if not topic:
        raise HTTPException(400, "topic is required")
    if fmt not in ("slides", "report", "brief"):
        raise HTTPException(400, "format must be slides, report, or brief")

    import yaml
    cfg_file = ROOT / "config.yaml"
    config = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) if cfg_file.exists() else {}

    try:
        if fmt == "slides":
            from tools.slides import _SLIDES_PROMPT
            from tools.search import search_wiki
            from tools.ask import _truncate_entry
            from tools.llm_client import LLMClient
            from datetime import datetime

            language = config.get("wiki", {}).get("language", "zh")
            results = search_wiki(topic, str(WIKI_DIR), top_k=6)
            if not results:
                raise HTTPException(422, "知识库中未找到相关条目，请先编译资料")

            entries_text = []
            for r in results:
                fp = Path(r["filepath"])
                if fp.exists():
                    content = _truncate_entry(fp.read_text(encoding="utf-8", errors="ignore"), 1500)
                    entries_text.append(f"=== {r['filename']} ===\n{content}")

            prompt = _SLIDES_PROMPT.format(
                topic=topic, language=language, wiki_entries="\n\n".join(entries_text)
            )
            client = LLMClient(config, tool="slides")
            max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get("slides")
            slides_content = await asyncio.to_thread(client.call, prompt, max_tokens=max_tokens)
            if "marp: true" not in slides_content:
                slides_content = "---\nmarp: true\ntheme: default\npaginate: true\n---\n\n" + slides_content

            from tools.slides import _slug as slug_fn
            (WIKI_DIR / "slides").mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            filename = f"{today}-{slug_fn(topic)}.md"
            filepath = WIKI_DIR / "slides" / filename
            filepath.write_text(slides_content, encoding="utf-8")

            cost = client.get_cost_summary()["cost_usd"]
            return {
                "format": "slides",
                "topic": topic,
                "filename": filename,
                "path": f"wiki/slides/{filename}",
                "content_md": slides_content,
                "cost_usd": round(cost, 5),
            }

        else:
            # report or brief
            from tools.report import _PROMPT_MD, _PROMPT_BRIEF, _slug as slug_fn
            from tools.search import search_wiki
            from tools.ask import _truncate_entry
            from tools.llm_client import LLMClient
            from datetime import datetime

            language = config.get("wiki", {}).get("language", "zh")
            results = search_wiki(topic, str(WIKI_DIR), top_k=8)
            if not results:
                raise HTTPException(422, "知识库中未找到相关条目，请先编译资料")

            MAX_CHARS = 2000 if fmt == "report" else 800
            entries_text = []
            for r in results:
                fp = Path(r["filepath"])
                if fp.exists():
                    content = _truncate_entry(fp.read_text(encoding="utf-8", errors="ignore"), MAX_CHARS)
                    entries_text.append(f"=== {r['filename']} ===\n{content}")

            wiki_entries = "\n\n".join(entries_text)
            template = _PROMPT_MD if fmt == "report" else _PROMPT_BRIEF
            prompt = template.format(topic=topic, language=language, wiki_entries=wiki_entries)

            client = LLMClient(config, tool="brief" if fmt == "brief" else "report")
            max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get(
                "brief" if fmt == "brief" else "report")
            report_content = await asyncio.to_thread(client.call, prompt, max_tokens=max_tokens)

            if fmt == "report":
                answers_dir = WIKI_DIR / "answers"
                answers_dir.mkdir(parents=True, exist_ok=True)
                today = datetime.now().strftime("%Y-%m-%d")
                filename = f"{today}-report-{slug_fn(topic)}.md"
                filepath = answers_dir / filename
                filepath.write_text(report_content, encoding="utf-8")
                saved_path = f"wiki/answers/{filename}"
            else:
                filename = None
                saved_path = None

            cost = client.get_cost_summary()["cost_usd"]
            return {
                "format": fmt,
                "topic": topic,
                "filename": filename,
                "path": saved_path,
                "content_md": report_content,
                "cost_usd": round(cost, 5),
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
