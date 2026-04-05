"""摄入 API — URL clip + PDF 上传 + 待编译列表"""
import sys
import shutil
import tempfile
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


@router.post("/ingest/clip")
async def clip_url(body: dict):
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "url is required")

    from tools.web_to_md import clip_url as _clip
    output_dir = ROOT / "raw" / "articles"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result_path = _clip(url, output_dir)
    except Exception as e:
        raise HTTPException(500, str(e))

    if result_path is None:
        return {"skipped": True, "reason": "already clipped or dry-run"}

    content = result_path.read_text(encoding="utf-8")
    return {
        "filename": result_path.name,
        "title": _extract_title(content),
        "chars": len(content),
        "path": str(result_path.relative_to(ROOT)),
    }


@router.post("/ingest/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    papers_dir = ROOT / "raw" / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    dest = papers_dir / file.filename

    async with aiofiles.open(dest, "wb") as f:
        await f.write(await file.read())

    # 提取 PDF → Markdown
    try:
        from tools.pdf_to_md import extract_pdf
        md_path = extract_pdf(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"PDF extraction failed: {e}")

    content = md_path.read_text(encoding="utf-8") if md_path and Path(md_path).exists() else ""
    return {
        "filename": Path(md_path).name if md_path else dest.stem + ".md",
        "chars": len(content),
        "path": str(Path(md_path).relative_to(ROOT)) if md_path else "",
    }


@router.get("/ingest/pending")
async def get_pending():
    """返回 raw/ 中尚未编译的文件列表"""
    import json
    state_file = ROOT / ".state" / "processed_files.json"
    processed = {}
    if state_file.exists():
        try:
            processed = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    pending = []
    for md_file in sorted((ROOT / "raw").rglob("*.md")):
        rel = str(md_file.relative_to(ROOT))
        if rel not in processed:
            pending.append({
                "filename": md_file.name,
                "path": rel,
                "type": _guess_type(md_file),
                "size_kb": round(md_file.stat().st_size / 1024, 1),
            })
    return {"pending": pending, "count": len(pending)}


def _extract_title(content: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("title:"):
            return line.split(":", 1)[-1].strip().strip('"\'')
    return "(无标题)"


def _guess_type(path: Path) -> str:
    parts = path.parts
    if "papers" in parts:
        return "paper"
    if "media-notes" in parts:
        return "media"
    return "article"
