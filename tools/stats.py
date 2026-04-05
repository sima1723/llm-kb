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


def count_wiki_entries() -> dict:
    """统计 wiki 条目数及平均字数"""
    if not WIKI_DIR.exists():
        return {"total": 0, "answers": 0, "slides": 0, "avg_words": 0}

    main_entries = []
    answers = []
    slides = []

    for md_file in WIKI_DIR.rglob("*.md"):
        if md_file.name == "INDEX.md":
            continue
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        word_count = len(content.replace(' ', '').replace('\n', ''))
        rel = md_file.relative_to(WIKI_DIR)
        if "answers" in str(rel):
            answers.append(word_count)
        elif "slides" in str(rel):
            slides.append(word_count)
        else:
            main_entries.append(word_count)

    avg = int(sum(main_entries) / len(main_entries)) if main_entries else 0
    return {
        "total": len(main_entries),
        "answers": len(answers),
        "slides": len(slides),
        "avg_words": avg,
    }


def count_links() -> dict:
    """统计内部链接总数、断链数、孤立条目数"""
    if not WIKI_DIR.exists():
        return {"total_links": 0, "broken": 0, "orphans": 0, "avg_links": 0}

    all_entries = []
    stems = set()

    for md_file in WIKI_DIR.rglob("*.md"):
        if md_file.name == "INDEX.md":
            continue
        if "answers" in str(md_file) or "slides" in str(md_file):
            continue
        stems.add(md_file.stem)
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        links = re.findall(r'\[\[(.+?)\]\]', content)
        all_entries.append({"stem": md_file.stem, "links": links})

    total_links = sum(len(e["links"]) for e in all_entries)
    broken = sum(1 for e in all_entries for lk in e["links"] if lk not in stems)

    # 孤立条目：没有任何条目链接到它
    all_link_targets = set(lk for e in all_entries for lk in e["links"])
    orphans = sum(1 for e in all_entries if e["stem"] not in all_link_targets)

    avg = round(total_links / len(all_entries), 1) if all_entries else 0
    return {
        "total_links": total_links,
        "broken": broken,
        "orphans": orphans,
        "avg_links": avg,
    }


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
    wiki = count_wiki_entries()
    links = count_links()
    pending = count_pending_raw()
    cost = get_api_cost()

    if HAS_RICH:
        lines = [
            f"[bold]Raw 文件:[/bold]    {raw['total']:>4}  (articles: {raw['articles']}, papers: {raw['papers']}, repos: {raw['repos']}, notes: {raw['media_notes']})",
            f"[bold]Wiki 条目:[/bold]   {wiki['total']:>4}  (avg {wiki['avg_words']} 字/篇)",
            f"[bold]答案记录:[/bold]    {wiki['answers']:>4}",
            f"[bold]幻灯片:[/bold]      {wiki['slides']:>4}",
            f"[bold]内部链接:[/bold]    {links['total_links']:>4}  (avg {links['avg_links']}/篇)",
            f"[bold]断链:[/bold]        {links['broken']:>4}  {'[red]⚠[/red]' if links['broken'] > 0 else '[green]✓[/green]'}",
            f"[bold]孤立条目:[/bold]    {links['orphans']:>4}  {'[yellow]⚠[/yellow]' if links['orphans'] > 0 else '[green]✓[/green]'}",
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
        print(f"  Wiki 条目:   {wiki['total']:>4}  (avg {wiki['avg_words']} 字/篇)")
        print(f"  答案记录:    {wiki['answers']:>4}")
        print(f"  幻灯片:      {wiki['slides']:>4}")
        print(f"  内部链接:    {links['total_links']:>4}  (avg {links['avg_links']}/篇)")
        print(f"  断链:        {links['broken']:>4}")
        print(f"  孤立条目:    {links['orphans']:>4}")
        print(f"  待处理:      {pending:>4}  个 raw 文件")
        print(f"  累计API费用: ${cost:.4f}")
        print("─" * 40 + "\n")


if __name__ == "__main__":
    print_dashboard()
