#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出报告工具 — 基于 wiki 知识库生成结构化报告或摘要。

CLI:
  python tools/report.py "主题" --format md     # Markdown 完整报告
  python tools/report.py "主题" --format brief  # 一段话摘要
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

from tools.search import search_wiki
from tools.llm_client import LLMClient
from tools.ask import _truncate_entry

console = Console() if HAS_RICH else None

WIKI_DIR = _HERE / "wiki"
ANSWERS_DIR = WIKI_DIR / "answers"
CONFIG_FILE = _HERE / "config.yaml"

_PROMPT_MD = """\
你是一位技术文档作者。请根据以下知识库条目，撰写一份关于"{topic}"的完整 Markdown 报告。语言：{language}

<wiki_entries>
{wiki_entries}
</wiki_entries>

## 报告要求
1. 包含标题（# 级别）、摘要段落、多个子标题（## 级别）
2. 在正文中用 [[条目名]] 格式引用相关 wiki 条目
3. 结尾包含"## 参考资料"，列出引用的知识库条目
4. 报告长度 500-1500 字，内容深度适中
5. 语言专业、结构清晰

请直接输出报告内容，不要额外说明：
"""

_PROMPT_BRIEF = """\
你是一位知识库助手。请根据以下知识库条目，用一段话（200字以内）概述"{topic}"。语言：{language}

<wiki_entries>
{wiki_entries}
</wiki_entries>

请用简洁的语言直接输出摘要，不要额外说明：
"""


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def _slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r'[^\w\u4e00-\u9fff]', '-', text)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:max_len]


@click.command()
@click.argument("topic")
@click.option("--format", "fmt", default="md", type=click.Choice(["md", "brief"]),
              show_default=True, help="报告格式：md=完整报告，brief=一段话摘要")
@click.option("--top-k", default=5, show_default=True, help="参考条目数量")
@click.option("--wiki-dir", default=None, help="wiki 目录路径")
def main(topic: str, fmt: str, top_k: int, wiki_dir: Optional[str]):
    """生成主题报告"""
    wd = Path(wiki_dir) if wiki_dir else WIKI_DIR
    config = _load_config()
    language = config.get("wiki", {}).get("language", "zh")

    # 搜索相关条目
    if HAS_RICH:
        with console.status(f"[cyan]搜索「{topic}」相关条目...[/cyan]"):
            results = search_wiki(topic, str(wd), top_k=top_k)
    else:
        print(f"搜索「{topic}」相关条目...")
        results = search_wiki(topic, str(wd), top_k=top_k)

    if not results:
        msg = "未找到相关条目，请先编译知识库"
        if HAS_RICH:
            console.print(f"[yellow]{msg}[/yellow]")
        else:
            print(msg)
        return

    # brief 只需摘要，1000 字符/条目够用；完整报告保留 3000 字符
    max_chars_per_entry = 1000 if fmt == "brief" else 3000
    entries_text = []
    source_files = []
    for r in results:
        fp = Path(r["filepath"])
        if fp.exists():
            content = _truncate_entry(fp.read_text(encoding="utf-8", errors="ignore"), max_chars_per_entry)
            entries_text.append(f"=== {r['filename']} ===\n{content}")
            source_files.append(r["filename"])

    wiki_entries = "\n\n".join(entries_text)

    # 选择 prompt 和 max_tokens
    tool_key = "report_brief" if fmt == "brief" else "report_md"
    report_max_tokens = config.get("llm", {}).get("max_tokens_by_tool", {}).get(tool_key)
    if fmt == "md":
        prompt = _PROMPT_MD.format(topic=topic, language=language, wiki_entries=wiki_entries)
    else:
        prompt = _PROMPT_BRIEF.format(topic=topic, language=language, wiki_entries=wiki_entries)

    # 调用 LLM
    client = LLMClient(config)
    if HAS_RICH:
        with console.status("[cyan]正在生成报告...[/cyan]"):
            report_content = client.call(prompt, max_tokens=report_max_tokens)
    else:
        print("正在生成报告...")
        report_content = client.call(prompt, max_tokens=report_max_tokens)

    # 打印报告
    if HAS_RICH:
        console.print()
        if fmt == "md":
            console.print(Panel(Markdown(report_content), title=f"[bold]报告: {topic}[/bold]", border_style="blue"))
        else:
            console.print(Panel(report_content, title=f"[bold]摘要: {topic}[/bold]", border_style="blue"))
    else:
        print(f"\n{'='*60}\n报告: {topic}\n{'='*60}")
        print(report_content)
        print('='*60)

    # 费用
    summary = client.get_cost_summary()
    cost_msg = f"费用: ${summary['cost_usd']:.4f}"
    if HAS_RICH:
        console.print(f"[dim]{cost_msg}[/dim]")
    else:
        print(cost_msg)

    # 保存到 wiki/answers/
    ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    slug = _slug(topic)
    suffix = "brief" if fmt == "brief" else "report"
    filename = f"{today}-{suffix}-{slug}.md"
    filepath = ANSWERS_DIR / filename

    frontmatter = {
        "topic": topic,
        "format": fmt,
        "sources": source_files,
        "generated_at": today,
        "source_type": "report",
    }
    fm_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip()
    file_content = f"---\n{fm_str}\n---\n\n{report_content}\n"
    filepath.write_text(file_content, encoding="utf-8")

    if HAS_RICH:
        console.print(f"[green]报告已保存: wiki/answers/{filename}[/green]")
    else:
        print(f"报告已保存: wiki/answers/{filename}")


if __name__ == "__main__":
    main()
