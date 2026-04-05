#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TF-IDF 搜索引擎 — 不依赖外部搜索库，自实现简版 TF-IDF。
支持中文 bigram + 英文空格分词，标题/frontmatter/正文差异权重。

CLI:
  python tools/search.py query "关键词"    # 全文搜索
  python tools/search.py list              # 列出所有条目
  python tools/search.py show "条目名"     # 显示条目内容及关联
  python tools/search.py related "条目名"  # 显示关联图谱（文字版）
"""

import os
import re
import sys
import math
from pathlib import Path
from typing import Optional

import click

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ─── 路径 ──────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent.parent
WIKI_DIR = _HERE / "wiki"

console = Console() if HAS_RICH else None


# ─── 分词 ──────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    """
    混合分词：
    - 中文按字符 bigram 分词
    - 英文按空格分词（转小写），并保留单字
    """
    tokens = []
    # 英文单词（含数字）
    english_words = re.findall(r'[a-zA-Z0-9]+', text)
    tokens.extend(w.lower() for w in english_words)
    # 中文 bigram
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    for i in range(len(chinese_chars) - 1):
        tokens.append(chinese_chars[i] + chinese_chars[i + 1])
    # 单个中文字也加入（用于短词查询）
    tokens.extend(chinese_chars)
    return tokens


# ─── TF-IDF 实现 ───────────────────────────────────────────────────────────

def compute_tf(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    n = len(tokens)
    return {t: c / n for t, c in freq.items()}


def build_corpus(wiki_dir: Path) -> list[dict]:
    """
    扫描 wiki/ 下所有 .md 文件，解析为文档列表。
    每个文档：{filename, title, frontmatter_text, body_text, full_text, filepath}
    """
    docs = []
    pattern = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)

    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        rel = md_file.relative_to(wiki_dir)
        raw = md_file.read_text(encoding="utf-8", errors="ignore")

        fm_text = ""
        body_text = raw
        m = pattern.match(raw)
        if m:
            fm_text = m.group(1)
            body_text = raw[m.end():]

        # 提取标题（第一个 # 行 或 文件名）
        title_match = re.search(r'^#\s+(.+)', body_text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem

        docs.append({
            "filename": str(rel),
            "filepath": md_file,
            "title": title,
            "frontmatter_text": fm_text,
            "body_text": body_text,
            "full_text": raw,
        })
    return docs


def build_idf(corpus: list[dict]) -> dict[str, float]:
    """计算 IDF（基于全语料）"""
    N = len(corpus)
    df: dict[str, int] = {}
    for doc in corpus:
        tokens = set(tokenize(doc["full_text"]))
        for t in tokens:
            df[t] = df.get(t, 0) + 1
    return {t: math.log((N + 1) / (cnt + 1)) + 1 for t, cnt in df.items()}


def score_document(query_tokens: list[str], doc: dict, idf: dict[str, float]) -> float:
    """
    加权 TF-IDF：标题 x3, frontmatter x2, 正文 x1
    """
    title_tf = compute_tf(tokenize(doc["title"]))
    fm_tf = compute_tf(tokenize(doc["frontmatter_text"]))
    body_tf = compute_tf(tokenize(doc["body_text"]))

    score = 0.0
    for qt in query_tokens:
        idf_val = idf.get(qt, 1.0)
        score += 3.0 * title_tf.get(qt, 0.0) * idf_val
        score += 2.0 * fm_tf.get(qt, 0.0) * idf_val
        score += 1.0 * body_tf.get(qt, 0.0) * idf_val
    return score


def extract_snippet(text: str, query_tokens: list[str], window: int = 120) -> str:
    """提取包含查询词的上下文片段"""
    lower = text.lower()
    best_pos = -1
    for qt in query_tokens:
        pos = lower.find(qt)
        if pos != -1:
            best_pos = pos
            break
    if best_pos == -1:
        # 返回正文开头
        clean = re.sub(r'^---.*?---\n', '', text, flags=re.DOTALL).strip()
        return clean[:window]

    start = max(0, best_pos - window // 2)
    end = min(len(text), best_pos + window // 2)
    snippet = text[start:end].replace('\n', ' ').strip()
    if start > 0:
        snippet = '…' + snippet
    if end < len(text):
        snippet = snippet + '…'
    return snippet


def highlight_snippet(snippet: str, query_tokens: list[str]) -> "Text":
    """用 rich 高亮关键词（英文不区分大小写）"""
    if not HAS_RICH:
        return snippet
    text = Text(snippet)
    for qt in query_tokens:
        text.highlight_regex(re.escape(qt), style="bold yellow")
    return text


# ─── 语料库缓存（避免每次搜索重建，基于文件 mtime 失效）────────────────────

_cache: dict = {"wiki_dir": None, "corpus": None, "idf": None, "mtime_sum": 0}


def _get_mtime_sum(wiki_dir: Path) -> float:
    """所有 .md 文件的 mtime 之和，用于判断缓存是否失效。"""
    return sum(f.stat().st_mtime for f in wiki_dir.rglob("*.md") if f.is_file())


def _get_cached_corpus_idf(wiki_dir: Path) -> tuple[list[dict], dict]:
    """返回缓存的 (corpus, idf)，若 wiki 有更新则重建。"""
    mtime_sum = _get_mtime_sum(wiki_dir)
    if (
        _cache["wiki_dir"] == wiki_dir
        and _cache["corpus"] is not None
        and _cache["mtime_sum"] == mtime_sum
    ):
        return _cache["corpus"], _cache["idf"]

    corpus = build_corpus(wiki_dir)
    idf = build_idf(corpus)
    _cache.update({"wiki_dir": wiki_dir, "corpus": corpus, "idf": idf, "mtime_sum": mtime_sum})
    return corpus, idf


# ─── 公开 Python API ────────────────────────────────────────────────────────

def search_wiki(query: str, wiki_dir: str = None, top_k: int = 5) -> list[dict]:
    """
    搜索 wiki 条目。
    返回: [{"filename": "...", "score": 0.85, "snippet": "..."}]
    """
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    if not wd.exists():
        return []

    corpus, idf = _get_cached_corpus_idf(wd)
    if not corpus:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    scored = []
    for doc in corpus:
        s = score_document(query_tokens, doc, idf)
        if s > 0:
            snippet = extract_snippet(doc["body_text"], query_tokens)
            scored.append({
                "filename": doc["filename"],
                "title": doc["title"],
                "score": round(s, 4),
                "snippet": snippet,
                "filepath": str(doc["filepath"]),
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ─── CLI ───────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """LLM 知识库搜索工具"""
    pass


@cli.command()
@click.argument("query_text")
@click.option("--top", default=10, show_default=True, help="返回结果数量")
@click.option("--wiki-dir", default=None, help="wiki 目录路径（默认自动检测）")
def query(query_text: str, top: int, wiki_dir: Optional[str]):
    """全文搜索 wiki 条目"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    results = search_wiki(query_text, str(wd), top_k=top)

    if not results:
        if HAS_RICH:
            console.print(f"[yellow]未找到匹配 '{query_text}' 的条目[/yellow]")
        else:
            print(f"未找到匹配 '{query_text}' 的条目")
        return

    query_tokens = tokenize(query_text)

    if HAS_RICH:
        console.print(f"\n[bold cyan]搜索: {query_text}[/bold cyan]  找到 {len(results)} 条结果\n")
        for i, r in enumerate(results, 1):
            snippet_text = highlight_snippet(r["snippet"], query_tokens)
            panel = Panel(
                snippet_text,
                title=f"[bold]{i}. {r['title']}[/bold]  [dim]{r['filename']}[/dim]  [green]score={r['score']}[/green]",
                border_style="dim",
                expand=False,
            )
            console.print(panel)
    else:
        print(f"\n搜索: {query_text}  找到 {len(results)} 条结果\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['title']}  ({r['filename']})  score={r['score']}")
            print(f"   {r['snippet']}\n")


@cli.command(name="list")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def list_entries(wiki_dir: Optional[str]):
    """列出所有 wiki 条目"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    corpus = build_corpus(wd)

    if not corpus:
        print("wiki/ 目录为空，请先运行 compile_wiki.py")
        return

    if HAS_RICH:
        table = Table(title=f"wiki 条目列表（共 {len(corpus)} 篇）", box=box.SIMPLE)
        table.add_column("#", style="dim", width=4)
        table.add_column("文件名", style="cyan")
        table.add_column("标题")
        table.add_column("字数", justify="right", style="green")
        for i, doc in enumerate(corpus, 1):
            wc = len(doc["body_text"].replace(' ', '').replace('\n', ''))
            table.add_row(str(i), doc["filename"], doc["title"], str(wc))
        console.print(table)
    else:
        print(f"wiki 条目列表（共 {len(corpus)} 篇）")
        for i, doc in enumerate(corpus, 1):
            print(f"  {i}. {doc['filename']}  {doc['title']}")


@cli.command()
@click.argument("entry_name")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def show(entry_name: str, wiki_dir: Optional[str]):
    """显示条目内容及关联"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR

    # 模糊匹配文件名
    candidates = list(wd.rglob("*.md"))
    matched = None
    for f in candidates:
        if entry_name.lower() in f.stem.lower() or entry_name.lower() in f.name.lower():
            matched = f
            break

    if not matched:
        print(f"未找到条目: {entry_name}")
        return

    content = matched.read_text(encoding="utf-8", errors="ignore")

    # 提取关联
    links = re.findall(r'\[\[(.+?)\]\]', content)
    links_unique = sorted(set(links))

    if HAS_RICH:
        console.print(Panel(content, title=f"[bold]{matched.stem}[/bold]", border_style="cyan"))
        if links_unique:
            console.print("\n[bold]关联条目:[/bold]")
            for lk in links_unique:
                exists = (wd / f"{lk}.md").exists()
                status = "[green]✓[/green]" if exists else "[red]✗（断链）[/red]"
                console.print(f"  [[{lk}]] {status}")
    else:
        print(content)
        if links_unique:
            print("\n关联条目:")
            for lk in links_unique:
                exists = (wd / f"{lk}.md").exists()
                status = "✓" if exists else "✗（断链）"
                print(f"  [[{lk}]] {status}")


@cli.command()
@click.argument("entry_name")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def related(entry_name: str, wiki_dir: Optional[str]):
    """显示关联图谱（文字版）"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR

    # 找到目标条目
    candidates = list(wd.rglob("*.md"))
    matched = None
    for f in candidates:
        if entry_name.lower() in f.stem.lower():
            matched = f
            break

    if not matched:
        print(f"未找到条目: {entry_name}")
        return

    content = matched.read_text(encoding="utf-8", errors="ignore")
    direct_links = sorted(set(re.findall(r'\[\[(.+?)\]\]', content)))

    # 反向引用：哪些条目链接到了它
    backlinks = []
    for f in candidates:
        if f == matched or f.name == "INDEX.md":
            continue
        fc = f.read_text(encoding="utf-8", errors="ignore")
        if f"[[{matched.stem}]]" in fc:
            backlinks.append(f.stem)

    if HAS_RICH:
        console.print(f"\n[bold cyan]关联图谱: {matched.stem}[/bold cyan]\n")
        if direct_links:
            console.print("[bold]→ 链出（本条目引用了）:[/bold]")
            for lk in direct_links:
                exists = (wd / f"{lk}.md").exists()
                icon = "[green]✓[/green]" if exists else "[red]✗[/red]"
                console.print(f"   {icon} [[{lk}]]")
        if backlinks:
            console.print("\n[bold]← 链入（被以下条目引用）:[/bold]")
            for bl in backlinks:
                console.print(f"   [[{bl}]]")
        if not direct_links and not backlinks:
            console.print("[yellow]此条目没有任何关联（孤立条目）[/yellow]")
    else:
        print(f"\n关联图谱: {matched.stem}\n")
        if direct_links:
            print("→ 链出:")
            for lk in direct_links:
                print(f"   [[{lk}]]")
        if backlinks:
            print("← 链入:")
            for bl in backlinks:
                print(f"   [[{bl}]]")


if __name__ == "__main__":
    cli()
