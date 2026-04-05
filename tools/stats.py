#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计仪表盘 — 显示知识库的整体健康状态和统计数字。

CLI:
  python tools/stats.py
"""

import json
import re
import sys
from pathlib import Path

import yaml

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

console = Console() if HAS_RICH else None

WIKI_DIR = _HERE / "wiki"
RAW_DIR = _HERE / "raw"
STATE_DIR = _HERE / ".state"
CONFIG_FILE = _HERE / "config.yaml"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def count_raw_files() -> dict:
    """统计 raw/ 下各子目录的文件数"""
    result = {"total": 0, "articles": 0, "papers": 0, "repos": 0, "media_notes": 0}
    if not RAW_DIR.exists():
        return result
    for sub in ["articles", "papers", "repos", "media-notes"]:
        count = len(list((RAW_DIR / sub).glob("*.md"))) if (RAW_DIR / sub).exists() else 0
        key = sub.replace("-", "_")
        result[key] = count
        result["total"] += count
    return result


def gather_wiki_stats() -> dict:
    """
    单趟扫描 wiki/，同时统计条目数、字数、链接数、断链、孤立条目。
    替代原来的 count_wiki_entries() + count_links() 两次独立扫描。
    """
    if not WIKI_DIR.exists():
        return {
            "total": 0, "answers": 0, "slides": 0, "avg_words": 0,
            "total_links": 0, "broken": 0, "orphans": 0, "avg_links": 0,
        }

    main_words: list[int] = []
    answers_count = 0
    slides_count = 0
    stems: set[str] = set()
    entries_links: list[tuple[str, list[str]]] = []  # (stem, [link, ...])

    for md_file in WIKI_DIR.rglob("*.md"):
        if md_file.name == "INDEX.md":
            continue
        rel_str = str(md_file.relative_to(WIKI_DIR))
        content = md_file.read_text(encoding="utf-8", errors="ignore")

        if "answers" in rel_str:
            answers_count += 1
        elif "slides" in rel_str:
            slides_count += 1
        else:
            main_words.append(len(content.replace(' ', '').replace('\n', '')))
            stems.add(md_file.stem)
            links = re.findall(r'\[\[(.+?)\]\]', content)
            entries_links.append((md_file.stem, links))

    total_links = sum(len(lks) for _, lks in entries_links)
    broken = sum(1 for _, lks in entries_links for lk in lks if lk not in stems)
    all_targets = {lk for _, lks in entries_links for lk in lks}
    orphans = sum(1 for stem, _ in entries_links if stem not in all_targets)
    avg_words = int(sum(main_words) / len(main_words)) if main_words else 0
    avg_links = round(total_links / len(entries_links), 1) if entries_links else 0

    return {
        "total": len(main_words),
        "answers": answers_count,
        "slides": slides_count,
        "avg_words": avg_words,
        "total_links": total_links,
        "broken": broken,
        "orphans": orphans,
        "avg_links": avg_links,
    }


# 保留向后兼容的薄包装，内部复用 gather_wiki_stats
def count_wiki_entries() -> dict:
    s = gather_wiki_stats()
    return {k: s[k] for k in ("total", "answers", "slides", "avg_words")}


def count_links() -> dict:
    s = gather_wiki_stats()
    return {k: s[k] for k in ("total_links", "broken", "orphans", "avg_links")}


def count_pending_raw() -> int:
    """统计待处理的 raw 文件数"""
    processed_file = STATE_DIR / "processed_files.json"
    if not processed_file.exists():
        return count_raw_files()["total"]

    try:
        processed = json.loads(processed_file.read_text(encoding="utf-8"))
    except Exception:
        return 0

    total = count_raw_files()["total"]
    done = sum(1 for md in RAW_DIR.rglob("*.md") if str(md.relative_to(_HERE)) in processed)
    return max(0, total - done)


def get_api_cost() -> float:
    """从 checkpoints.json 读取累计费用"""
    checkpoints_file = STATE_DIR / "checkpoints.json"
    if not checkpoints_file.exists():
        return 0.0
    try:
        data = json.loads(checkpoints_file.read_text(encoding="utf-8"))
        # 读 last_compile 和历史记录
        cost = 0.0
        for key, val in data.items():
            if isinstance(val, dict) and "cost_usd" in val:
                cost += float(val["cost_usd"])
        return cost
    except Exception:
        return 0.0


def print_dashboard():
    """输出统计仪表盘"""
    raw = count_raw_files()
    s = gather_wiki_stats()   # 单趟扫描获取所有 wiki 统计
    pending = count_pending_raw()
    cost = get_api_cost()

    if HAS_RICH:
        lines = [
            f"[bold]Raw 文件:[/bold]    {raw['total']:>4}  (articles: {raw['articles']}, papers: {raw['papers']}, repos: {raw['repos']}, notes: {raw['media_notes']})",
            f"[bold]Wiki 条目:[/bold]   {s['total']:>4}  (avg {s['avg_words']} 字/篇)",
            f"[bold]答案记录:[/bold]    {s['answers']:>4}",
            f"[bold]幻灯片:[/bold]      {s['slides']:>4}",
            f"[bold]内部链接:[/bold]    {s['total_links']:>4}  (avg {s['avg_links']}/篇)",
            f"[bold]断链:[/bold]        {s['broken']:>4}  {'[red]⚠[/red]' if s['broken'] > 0 else '[green]✓[/green]'}",
            f"[bold]孤立条目:[/bold]    {s['orphans']:>4}  {'[yellow]⚠[/yellow]' if s['orphans'] > 0 else '[green]✓[/green]'}",
            f"[bold]待处理:[/bold]      {pending:>4}  个 raw 文件",
            f"[bold]累计API费用:[/bold] ${cost:.4f}",
        ]
        console.print(Panel(
            "\n".join(lines),
            title="[bold cyan]知识库统计[/bold cyan]",
            border_style="cyan",
            expand=False,
        ))
    else:
        print("\n" + "─" * 40)
        print("  知识库统计")
        print("─" * 40)
        print(f"  Raw 文件:    {raw['total']:>4}  (articles:{raw['articles']} papers:{raw['papers']} repos:{raw['repos']} notes:{raw['media_notes']})")
        print(f"  Wiki 条目:   {s['total']:>4}  (avg {s['avg_words']} 字/篇)")
        print(f"  答案记录:    {s['answers']:>4}")
        print(f"  幻灯片:      {s['slides']:>4}")
        print(f"  内部链接:    {s['total_links']:>4}  (avg {s['avg_links']}/篇)")
        print(f"  断链:        {s['broken']:>4}")
        print(f"  孤立条目:    {s['orphans']:>4}")
        print(f"  待处理:      {pending:>4}  个 raw 文件")
        print(f"  累计API费用: ${cost:.4f}")
        print("─" * 40 + "\n")


if __name__ == "__main__":
    print_dashboard()
