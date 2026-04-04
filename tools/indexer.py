#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INDEX.md 生成器：扫描 wiki/ 条目，生成可读的索引文件。

用法：
  python tools/indexer.py
  python tools/indexer.py --wiki-dir wiki/
"""

import re
import sys
from datetime import date
from pathlib import Path
from collections import defaultdict

import click
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


def parse_frontmatter(content: str) -> tuple:
    """
    解析 YAML frontmatter。
    返回 (frontmatter_dict, body_str)。
    """
    if not content.startswith('---'):
        return {}, content

    end = content.find('\n---', 3)
    if end == -1:
        return {}, content

    fm_text = content[4:end]
    body = content[end + 4:].lstrip('\n')
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def extract_first_paragraph(body: str) -> str:
    """提取正文中 ## 定义 下的第一段，或正文第一段。"""
    # 尝试找 ## 定义 段落
    m = re.search(r'## 定义\s*\n+(.*?)(?:\n##|\Z)', body, re.DOTALL)
    if m:
        text = m.group(1).strip()
        # 取第一句（句号/换行截断）
        first = re.split(r'[。\n]', text)[0].strip()
        return first[:80] + ('…' if len(first) > 80 else '')

    # 回退：正文第一个非空行
    for line in body.split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('-'):
            return line[:80] + ('…' if len(line) > 80 else '')
    return ''


def count_links(content: str) -> int:
    """统计 [[链接]] 数量。"""
    return len(re.findall(r'\[\[.*?\]\]', content))


def count_sources(fm: dict) -> int:
    """统计来源数量。"""
    sources = fm.get('sources', [])
    return len(sources) if isinstance(sources, list) else 0


def regenerate_index(wiki_dir: str) -> str:
    """
    扫描 wiki/ 下所有 .md 文件（排除 INDEX.md、answers/、slides/）
    生成 INDEX.md 内容字符串并写入文件。

    返回写入的内容。
    """
    wiki_path = Path(wiki_dir)
    today = date.today().isoformat()

    # 收集条目（只扫描顶层，排除子目录 answers/ slides/）
    entries_data = []
    for md_file in sorted(wiki_path.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        description = extract_first_paragraph(body)
        link_count = count_links(content)
        source_count = count_sources(fm)
        related = fm.get('related_concepts', [])
        if isinstance(related, str):
            related = [related]

        entries_data.append({
            'name': md_file.stem,
            'filename': md_file.name,
            'description': description,
            'links': link_count,
            'sources': source_count,
            'related': related if isinstance(related, list) else [],
        })

    n = len(entries_data)

    # 构建条目表格
    table_rows = []
    for e in entries_data:
        table_rows.append(
            f"| [[{e['name']}]] | {e['description'] or '—'} "
            f"| {e['links']} | {e['sources']} |"
        )

    table = (
        "| 条目 | 一句话描述 | 关联数 | 来源数 |\n"
        "|------|-----------|--------|--------|\n"
        + "\n".join(table_rows)
    ) if table_rows else "_（暂无条目）_"

    # 按 related_concepts 聚类（简单归类）
    clusters = defaultdict(list)
    unclustered = []
    for e in entries_data:
        if e['related']:
            # 用第一个关联概念作为分类键
            clusters[e['related'][0]].append(e['name'])
        else:
            unclustered.append(e['name'])

    cluster_section = ""
    if clusters or unclustered:
        cluster_section = "\n## 按主题分类\n\n"
        for topic, names in sorted(clusters.items()):
            cluster_section += f"**{topic}**：" + "、".join(f"[[{n}]]" for n in names) + "\n\n"
        if unclustered:
            cluster_section += "**其他**：" + "、".join(f"[[{n}]]" for n in unclustered) + "\n\n"

    index_content = f"""# 知识库索引

最后更新：{today} | 共 {n} 篇条目

## 条目列表

{table}
{cluster_section}"""

    index_path = wiki_path / "INDEX.md"
    index_path.write_text(index_content, encoding="utf-8")
    return index_content


@click.command()
@click.option("--wiki-dir", default="wiki", help="wiki 目录路径")
def main(wiki_dir):
    """重新生成 wiki/INDEX.md。"""
    from rich.console import Console
    c = Console()
    content = regenerate_index(wiki_dir)
    n = content.count('\n[[')
    c.print(f"[green]✓[/green] INDEX.md 已更新，共 {n} 篇条目")


if __name__ == "__main__":
    main()
