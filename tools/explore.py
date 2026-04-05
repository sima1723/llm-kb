#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识探索建议工具 — 分析知识库覆盖范围，给出探索方向和待填充概念。

CLI:
  python tools/explore.py
  python tools/explore.py --add    # 为建议的概念自动创建 stub 条目
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import yaml

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from tools.llm_client import LLMClient
from tools.indexer import regenerate_index

console = Console() if HAS_RICH else None

WIKI_DIR = _HERE / "wiki"
CONFIG_FILE = _HERE / "config.yaml"

_EXPLORE_PROMPT = """\
你是一位知识库分析师。请分析以下知识库的覆盖范围，语言：{language}

<knowledge_base>
{kb_summary}
</knowledge_base>

## 任务
1. 列出 **5 个值得深入研究的方向**（知识库中有涉及但可以更深入的领域）
2. 列出 **5 个当前知识库中有提及但尚未独立成篇的概念**（这些概念在条目正文中出现了，但没有自己的页面）

## 输出格式（严格按此格式，方便解析）

### 深入研究方向
1. **方向名称**: 理由（1-2句）
2. **方向名称**: 理由
3. **方向名称**: 理由
4. **方向名称**: 理由
5. **方向名称**: 理由

### 待填充概念
1. 概念名称
2. 概念名称
3. 概念名称
4. 概念名称
5. 概念名称
"""


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def build_kb_summary(wiki_dir: Path) -> tuple[str, list[str]]:
    """构建知识库摘要（条目名 + 关联）供 LLM 分析"""
    lines = []
    all_stems = []

    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        if "answers" in str(md_file) or "slides" in str(md_file):
            continue
        raw = md_file.read_text(encoding="utf-8", errors="ignore")
        links = re.findall(r'\[\[(.+?)\]\]', raw)
        # 提取第一段定义
        defn_match = re.search(r'## 定义\n(.+?)(?=\n##|\Z)', raw, re.DOTALL)
        defn = defn_match.group(1).strip()[:100] if defn_match else ""
        defn = defn.replace('\n', ' ')
        all_stems.append(md_file.stem)
        links_sample = list(set(links))[:5]
        lines.append(f"**{md_file.stem}**: {defn}  →关联: {', '.join(links_sample)}")

    return "\n".join(lines), all_stems


def parse_stub_concepts(response: str) -> list[str]:
    """从 LLM 响应中解析「待填充概念」列表"""
    concepts = []
    in_section = False
    for line in response.split("\n"):
        if "待填充概念" in line:
            in_section = True
            continue
        if in_section:
            # 匹配 "1. 概念名称" 或 "- 概念名称"
            m = re.match(r'^\d+\.\s+(.+)$', line.strip())
            if not m:
                m = re.match(r'^[-*]\s+(.+)$', line.strip())
            if m:
                concept = m.group(1).strip().lstrip('**').rstrip('**').split(':')[0].strip()
                if concept:
                    concepts.append(concept)
            elif line.strip().startswith("###"):
                # 进入下一节，停止
                if concepts:
                    break
    return concepts[:5]


def create_stubs(concepts: list[str], wiki_dir: Path, dry_run: bool):
    """为概念列表创建 stub 条目"""
    today = datetime.now().strftime("%Y-%m-%d")
    created = []
    for concept in concepts:
        stub_path = wiki_dir / f"{concept}.md"
        if stub_path.exists():
            if HAS_RICH:
                console.print(f"  [dim]已存在: {concept}.md，跳过[/dim]")
            else:
                print(f"  已存在: {concept}.md，跳过")
            continue
        if dry_run:
            print(f"  [dry-run] 将创建 stub: {concept}.md")
            continue
        content = (
            f"---\nrelated_concepts: []\nsources: []\nlast_updated: {today}\ntags: [stub]\n---\n\n"
            f"# {concept}\n\n> ⚠️ 此条目为 explore 建议自动创建的 stub，尚待编译填充。\n\n"
            f"## 定义\n待补充。\n"
        )
        stub_path.write_text(content, encoding="utf-8")
        created.append(concept)
        if HAS_RICH:
            console.print(f"  [green]创建 stub: {concept}.md[/green]")
        else:
            print(f"  创建 stub: {concept}.md")
    return created


@click.command()
@click.option("--add", is_flag=True, help="为建议的概念自动创建 stub 条目")
@click.option("--dry-run", is_flag=True, help="显示将创建的 stub 但不执行")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def main(add: bool, dry_run: bool, wiki_dir: Optional[str]):
    """分析知识库覆盖范围，给出探索建议"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    config = _load_config()
    language = config.get("wiki", {}).get("language", "zh")

    if HAS_RICH:
        with console.status("[cyan]分析知识库结构...[/cyan]"):
            kb_summary, all_stems = build_kb_summary(wd)
    else:
        print("分析知识库结构...")
        kb_summary, all_stems = build_kb_summary(wd)

    if not kb_summary:
        msg = "知识库为空，请先编译 raw/ 文件"
        if HAS_RICH:
            console.print(f"[yellow]{msg}[/yellow]")
        else:
            print(msg)
        return

    prompt = _EXPLORE_PROMPT.format(language=language, kb_summary=kb_summary)

    client = LLMClient(config)
    explore_max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get("explore")
    if HAS_RICH:
        with console.status("[cyan]正在生成探索建议...[/cyan]"):
            response = client.call(prompt, max_tokens=explore_max_tokens)
    else:
        print("正在生成探索建议...")
        response = client.call(prompt, max_tokens=explore_max_tokens)

    # 显示建议
    if HAS_RICH:
        console.print()
        console.print(Panel(
            Markdown(response),
            title=f"[bold cyan]知识库探索建议（共 {len(all_stems)} 篇条目）[/bold cyan]",
            border_style="cyan",
        ))
    else:
        print(f"\n{'='*60}")
        print(f"知识库探索建议（共 {len(all_stems)} 篇条目）")
        print('='*60)
        print(response)
        print('='*60)

    summary = client.get_cost_summary()
    if HAS_RICH:
        console.print(f"[dim]费用: ${summary['cost_usd']:.4f}[/dim]")
    else:
        print(f"费用: ${summary['cost_usd']:.4f}")

    # 可选：创建 stub 条目
    if add or dry_run:
        concepts = parse_stub_concepts(response)
        if concepts:
            if HAS_RICH:
                console.print(f"\n[bold]将为以下概念创建 stub 条目:[/bold] {', '.join(concepts)}")
            else:
                print(f"\n将为以下概念创建 stub: {', '.join(concepts)}")
            created = create_stubs(concepts, wd, dry_run)
            # 重建 INDEX.md 使新 stub 立即可见
            if created and not dry_run:
                try:
                    regenerate_index(str(wd))
                except Exception:
                    pass
        else:
            if HAS_RICH:
                console.print("[yellow]未能解析出待填充概念，请手动创建[/yellow]")


if __name__ == "__main__":
    main()
