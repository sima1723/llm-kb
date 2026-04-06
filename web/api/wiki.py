"""Wiki API — 知识图谱数据 + 条目内容"""
import re
import sys
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = ROOT / "wiki"
sys.path.insert(0, str(ROOT))


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (meta, body)"""
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            try:
                meta = yaml.safe_load(content[3:end]) or {}
            except Exception:
                meta = {}
            return meta, content[end + 4:].lstrip()
    return {}, content


def _extract_links(content: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'\[\[(.+?)\]\]', content)))


def _entry_type(meta: dict, body_preview: str = "") -> str:
    tags = meta.get("tags", [])
    if isinstance(tags, list) and "stub" in tags:
        return "stub"
    if "待补充" in body_preview[:200]:
        return "stub"
    source_type = str(meta.get("source_type", ""))
    if source_type == "answer":
        return "answer"
    return "entry"


@router.get("/wiki/graph")
async def get_graph():
    """返回 d3-force 所需的 nodes + edges 数据"""
    nodes = []
    edges = []
    entry_names: set[str] = set()

    # 第一遍：收集所有条目名
    for md in WIKI_DIR.glob("*.md"):
        if md.name == "INDEX.md":
            continue
        entry_names.add(md.stem)

    # 把 answers 也加进来（用不同类型标记）
    for md in (WIKI_DIR / "answers").glob("*.md") if (WIKI_DIR / "answers").exists() else []:
        entry_names.add(f"answers/{md.stem}")

    # 第二遍：构建节点和边
    link_counts: dict[str, int] = {}
    for md in WIKI_DIR.glob("*.md"):
        if md.name == "INDEX.md":
            continue
        content = md.read_text(encoding="utf-8", errors="ignore")
        meta, body = _parse_frontmatter(content)
        links = _extract_links(content)

        # 统计每个条目被引用次数
        for lk in links:
            link_counts[lk] = link_counts.get(lk, 0) + 1

        node_type = _entry_type(meta, body)
        desc = ""
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-") and not line.startswith(">"):
                desc = line[:80]
                break

        nodes.append({
            "id": md.stem,
            "label": md.stem,
            "type": node_type,
            "description": desc,
            "link_count": len(links),
        })

        for lk in links:
            if lk in entry_names:
                edges.append({"source": md.stem, "target": lk})

    # answers 节点
    answers_dir = WIKI_DIR / "answers"
    if answers_dir.exists():
        for md in answers_dir.glob("*.md"):
            content = md.read_text(encoding="utf-8", errors="ignore")
            meta, body = _parse_frontmatter(content)
            q = meta.get("question", md.stem)[:60]
            nodes.append({
                "id": f"answers/{md.stem}",
                "label": q,
                "type": "answer",
                "description": q,
                "link_count": 0,
            })

    # 用被引用次数更新 link_count（节点大小基准）
    for node in nodes:
        node["cited_count"] = link_counts.get(node["id"], 0)

    return {"nodes": nodes, "edges": edges}


@router.get("/wiki/entry/{name:path}")
async def get_entry(name: str):
    """返回条目内容（HTML + 元数据 + 链接关系）"""
    # 安全：防止路径穿越
    try:
        if name.startswith("answers/"):
            md_path = (WIKI_DIR / "answers" / (name[8:] + ".md")).resolve()
            allowed_root = (WIKI_DIR / "answers").resolve()
        else:
            md_path = (WIKI_DIR / (name + ".md")).resolve()
            allowed_root = WIKI_DIR.resolve()
        if not md_path.is_relative_to(allowed_root):
            raise HTTPException(403, "Access denied")
    except ValueError:
        raise HTTPException(400, "Invalid entry name")

    if not md_path.exists():
        raise HTTPException(404, f"Entry '{name}' not found")

    content = md_path.read_text(encoding="utf-8", errors="ignore")
    meta, body = _parse_frontmatter(content)
    links = _extract_links(body)

    # 反向引用
    backlinks = []
    for other in WIKI_DIR.glob("*.md"):
        if other.name == "INDEX.md" or other == md_path:
            continue
        if f"[[{name}]]" in other.read_text(encoding="utf-8", errors="ignore"):
            backlinks.append(other.stem)

    # 渲染 [[链接]] 为 HTML span（前端负责点击跳转）
    html_body = _render_wiki_links(body)

    return {
        "name": name,
        "label": meta.get("title", name) if "title" in meta else name,
        "frontmatter": meta,
        "body_md": body,
        "body_html": html_body,
        "links": links,
        "backlinks": backlinks,
    }


@router.get("/wiki/index")
async def get_index():
    entries = []
    for md in sorted(WIKI_DIR.glob("*.md")):
        if md.name == "INDEX.md":
            continue
        content = md.read_text(encoding="utf-8", errors="ignore")
        meta, body = _parse_frontmatter(content)
        desc = ""
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                desc = line[:100]
                break
        entries.append({
            "name": md.stem,
            "description": desc,
            "link_count": len(_extract_links(content)),
            "source_count": len(meta.get("sources", [])) if isinstance(meta.get("sources"), list) else 0,
            "type": _entry_type(meta, body),
        })
    return {"entries": entries, "total": len(entries)}


def _render_wiki_links(md: str) -> str:
    """把 [[链接]] 替换为带 data-entry 属性的 span，保留 Markdown 其余格式"""
    return re.sub(
        r'\[\[(.+?)\]\]',
        r'<span class="wiki-link" data-entry="\1">[[\1]]</span>',
        md
    )
